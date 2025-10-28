"""
Shot chart data fetching and aggregation.
Provides functions to:
1. Fetch raw shot chart data from NBA API
"""

import logging
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd
from nba_api.stats.endpoints import shotchartdetail

from .entity_resolver import resolve_entity
from .errors import (
    EntityNotFoundError,
    InvalidParameterError,
    NBAApiError,
    retry_with_backoff,
)
from .tools.nba_api_utils import normalize_season

logger = logging.getLogger(__name__)

# Data Fetching

@retry_with_backoff(max_retries=3)
async def fetch_shot_chart_data(
    entity_id: int,
    entity_type: Literal["player", "team"],
    season: str,
    season_type: str = "Regular Season",
) -> pd.DataFrame:
    """
    Fetch raw shot chart data from NBA API.

    Uses nba_api.stats.endpoints.shotchartdetail.ShotChartDetail.

    Args:
        entity_id: Player ID or Team ID
        entity_type: "player" or "team"
        season: Season in YYYY-YY format (e.g., "2023-24")
        season_type: "Regular Season", "Playoffs", etc.

    Returns:
        DataFrame with columns:
        - LOC_X: X coordinate (tenths of feet)
        - LOC_Y: Y coordinate (tenths of feet)
        - SHOT_MADE_FLAG: 1 if made, 0 if missed
        - SHOT_DISTANCE: Distance from basket in feet
        - SHOT_TYPE: "2PT Field Goal" or "3PT Field Goal"
        - PERIOD: Quarter (1-4) or OT period
        - MINUTES_REMAINING: Minutes left in period
        - SECONDS_REMAINING: Seconds left in period
        - And more...

    Raises:
        NBAApiError: If API call fails after retries
        InvalidParameterError: If parameters invalid
    """
    try:
        logger.info(
            f"Fetching shot chart: entity_id={entity_id}, type={entity_type}, season={season}"
        )

        # ShotChartDetail requires both team_id and player_id
        if entity_type == "player":
            # For players, set team_id to 0 (all teams)
            shot_data = shotchartdetail.ShotChartDetail(
                team_id=0,
                player_id=entity_id,
                season_nullable=season,
                season_type_all_star=season_type,
                context_measure_simple="FGA",  # Field Goal Attempts
            )
        else:
            # For teams, set player_id to 0 (all players)
            shot_data = shotchartdetail.ShotChartDetail(
                team_id=entity_id,
                player_id=0,
                season_nullable=season,
                season_type_all_star=season_type,
                context_measure_simple="FGA",
            )

        # Get DataFrame
        df = shot_data.get_data_frames()[0]  # Shot_Chart_Detail dataset

        if df.empty:
            logger.warning(
                f"No shot data found for entity_id={entity_id}, season={season}"
            )
            return pd.DataFrame()

        logger.info(f"Fetched {len(df)} shots")
        return df

    except Exception as e:
        logger.error(f"Error fetching shot chart data: {e}")
        raise NBAApiError(
            message=f"Failed to fetch shot chart data: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="shotchartdetail",
        )

# Coordinate Validation

def validate_shot_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and filter shot coordinates.

    NBA court coordinates:
    - X-axis: -250 to +250 (left to right, tenths of feet)
    - Y-axis: -52.5 to +417.5 (baseline to opposite baseline)

    Args:
        df: DataFrame with LOC_X and LOC_Y columns

    Returns:
        Filtered DataFrame with only valid coordinates

    Logs:
        Warning for any invalid coordinates found
    """
    if df.empty:
        return df

    # Check for required columns
    if "LOC_X" not in df.columns or "LOC_Y" not in df.columns:
        logger.error("DataFrame missing LOC_X or LOC_Y columns")
        return df

    # Count invalid coordinates
    invalid_x = ~df["LOC_X"].between(-250, 250)
    invalid_y = ~df["LOC_Y"].between(-52.5, 417.5)
    invalid_mask = invalid_x | invalid_y

    invalid_count = invalid_mask.sum()
    if invalid_count > 0:
        logger.warning(
            f"Found {invalid_count} shots with invalid coordinates (filtered out)"
        )
        logger.debug(
            f"Invalid X coords: {invalid_x.sum()}, Invalid Y coords: {invalid_y.sum()}"
        )

    # Filter to valid coordinates
    valid_df = df[~invalid_mask].copy()

    return valid_df

# Hexbin Aggregation

def aggregate_to_hexbin(
    shots: pd.DataFrame, grid_size: int = 10, min_shots: int = 5
) -> List[Dict[str, Any]]:
    """
    Aggregate shots into hexagonal bins for heat map visualization.

    Algorithm:
    1. Create 2D grid (default: 10 tenths of feet = 1 foot bins)
    2. Map each shot to grid cell: bin_x = (LOC_X + 250) // grid_size
    3. Group shots by cell, calculate FG% per cell
    4. Filter cells with < min_shots (statistical significance)

    Args:
        shots: DataFrame with LOC_X, LOC_Y, SHOT_MADE_FLAG
        grid_size: Size of each bin in tenths of feet (default: 10 = 1 foot)
        min_shots: Minimum shots per bin to include (default: 5)

    Returns:
        List of bins with structure:
        {
            "bin_x": int,  # X coordinate of bin center
            "bin_y": int,  # Y coordinate of bin center
            "shot_count": int,  # Number of shots in bin
            "made_count": int,  # Number of makes in bin
            "fg_pct": float,  # Field goal percentage (0.0-1.0)
            "distance_avg": float,  # Average shot distance in feet
        }

    if shots.empty:
        return []

    # Check for required columns
    required_cols = ["LOC_X", "LOC_Y", "SHOT_MADE_FLAG"]
    missing_cols = [col for col in required_cols if col not in shots.columns]
    if missing_cols:
        logger.error(f"Missing required columns for hexbin: {missing_cols}")
        return []

    # Create bin assignments (vectorized for performance)
    bin_x = ((shots["LOC_X"] + 250) // grid_size).astype(int)
    bin_y = ((shots["LOC_Y"] + 52.5) // grid_size).astype(int)

    # Add bins to dataframe
    shots_with_bins = shots.copy()
    shots_with_bins["bin_x"] = bin_x
    shots_with_bins["bin_y"] = bin_y

    # Group by bin and aggregate
    agg_dict = {
        "SHOT_MADE_FLAG": ["count", "sum"],  # count = attempts, sum = makes
    }

    # Add distance if available
    if "SHOT_DISTANCE" in shots.columns:
        agg_dict["SHOT_DISTANCE"] = "mean"

    bins_grouped = shots_with_bins.groupby(["bin_x", "bin_y"]).agg(agg_dict)

    # Flatten multi-level columns
    bins_grouped.columns = ["_".join(col).strip() for col in bins_grouped.columns]
    bins_grouped = bins_grouped.reset_index()

    # Rename for clarity
    bins_grouped = bins_grouped.rename(
        columns={
            "SHOT_MADE_FLAG_count": "shot_count",
            "SHOT_MADE_FLAG_sum": "made_count",
        }
    )

    # Filter by minimum shots
    bins_grouped = bins_grouped[bins_grouped["shot_count"] >= min_shots]

    # Calculate FG%
    bins_grouped["fg_pct"] = bins_grouped["made_count"] / bins_grouped["shot_count"]

    # Convert bin coordinates to court coordinates (bin center)
    bins_grouped["bin_x"] = (bins_grouped["bin_x"] * grid_size) - 250 + (grid_size // 2)
    bins_grouped["bin_y"] = (
        (bins_grouped["bin_y"] * grid_size) - 52.5 + (grid_size // 2)
    )

    # Prepare output
    result = []
    for _, row in bins_grouped.iterrows():
        bin_dict = {
            "bin_x": int(row["bin_x"]),
            "bin_y": int(row["bin_y"]),
            "shot_count": int(row["shot_count"]),
            "made_count": int(row["made_count"]),
            "fg_pct": round(float(row["fg_pct"]), 3),
        }

        # Add average distance if available
        if "SHOT_DISTANCE_mean" in row:
            bin_dict["distance_avg"] = round(float(row["SHOT_DISTANCE_mean"]), 1)

        result.append(bin_dict)

    logger.info(
        f"Aggregated {len(shots)} shots into {len(result)} bins (min_shots={min_shots})"
    )
    return result

# Zone Summary

def calculate_zone_summary(shots: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate summary statistics by shot zone.

    Zones:
    - Paint: Distance < 8 feet
    - Short Mid-Range: 8-16 feet
    - Long Mid-Range: 16-23.75 feet (non-3PT)
    - Three-Point: Distance >= 23.75 feet (corner 3 = 22 feet)

    Args:
        shots: DataFrame with SHOT_DISTANCE, SHOT_MADE_FLAG, SHOT_TYPE

    Returns:
        Dict with zone-level statistics:
        {
            "paint": {"attempts": int, "made": int, "pct": float},
            "short_mid": {...},
            "long_mid": {...},
            "three": {...},
            "overall": {...}
        }
    """
    if shots.empty:
        return {
            "paint": {"attempts": 0, "made": 0, "pct": 0.0},
            "short_mid": {"attempts": 0, "made": 0, "pct": 0.0},
            "long_mid": {"attempts": 0, "made": 0, "pct": 0.0},
            "three": {"attempts": 0, "made": 0, "pct": 0.0},
            "overall": {"attempts": 0, "made": 0, "pct": 0.0},
        }

    # Check for required columns
    if "SHOT_DISTANCE" not in shots.columns or "SHOT_MADE_FLAG" not in shots.columns:
        logger.error("Missing required columns for zone summary")
        return {}

    def calc_zone_stats(zone_shots):
        """Helper to calculate stats for a zone."""
        if len(zone_shots) == 0:
            return {"attempts": 0, "made": 0, "pct": 0.0}

        attempts = len(zone_shots)
        made = zone_shots["SHOT_MADE_FLAG"].sum()
        pct = made / attempts if attempts > 0 else 0.0

        return {"attempts": int(attempts), "made": int(made), "pct": round(pct, 3)}

    # Define zones by distance
    paint = shots[shots["SHOT_DISTANCE"] < 8]
    short_mid = shots[(shots["SHOT_DISTANCE"] >= 8) & (shots["SHOT_DISTANCE"] < 16)]

    # Long mid-range: 16-23.75 feet, but exclude 3-pointers
    # Check if SHOT_TYPE column exists
    if "SHOT_TYPE" in shots.columns:
        long_mid = shots[
            (shots["SHOT_DISTANCE"] >= 16)
            & (shots["SHOT_DISTANCE"] < 23.75)
            & (shots["SHOT_TYPE"] != "3PT Field Goal")
        ]
        three = shots[shots["SHOT_TYPE"] == "3PT Field Goal"]
    else:
        # Fallback: assume >= 23.75 is three (not perfect for corner 3s)
        long_mid = shots[
            (shots["SHOT_DISTANCE"] >= 16) & (shots["SHOT_DISTANCE"] < 23.75)
        ]
        three = shots[shots["SHOT_DISTANCE"] >= 23.75]

    # Calculate stats for each zone
    zone_summary = {
        "paint": calc_zone_stats(paint),
        "short_mid": calc_zone_stats(short_mid),
        "long_mid": calc_zone_stats(long_mid),
        "three": calc_zone_stats(three),
        "overall": calc_zone_stats(shots),
    }

    return zone_summary

# Main Entry Point

async def get_shot_chart(
    entity_name: str,
    entity_type: Literal["player", "team"],
    season: str,
    season_type: str = "Regular Season",
    granularity: Literal["raw", "hexbin", "both", "summary"] = "both",
) -> Dict[str, Any]:
    """
    Get shot chart data with optional hexbin aggregation.

    This is the main entry point called by the MCP tool.

    Args:
        entity_name: Player or team name (fuzzy matching supported)
        entity_type: "player" or "team"
        season: Season in YYYY-YY format (e.g., "2023-24")
        season_type: "Regular Season", "Playoffs", etc.
        granularity: Output format
            - "raw": Individual shot coordinates only
            - "hexbin": Aggregated hexbin data only
            - "both": Both raw and hexbin (default)
            - "summary": Zone summary statistics only

    Returns:
        Dict with structure based on granularity:
        {
            "entity": {"id": int, "name": str, "type": str},
            "season": str,
            "season_type": str,
            "raw_shots": List[Dict] (if granularity includes raw),
            "hexbin": List[Dict] (if granularity includes hexbin),
            "zone_summary": Dict (if granularity includes summary),
            "metadata": {
                "total_shots": int,
                "made_shots": int,
                "fg_pct": float,
                "coordinate_system": str,
            }
        }

    Raises:
        EntityNotFoundError: If entity not found
        InvalidParameterError: If parameters invalid
        NBAApiError: If API call fails
    """
    # Normalize season format
    normalized_seasons = normalize_season(season)

    # ShotChartDetail only supports single season, take first if multiple provided
    if normalized_seasons is None:
        # Use current season if None provided
        from nba_mcp.api.tools.nba_api_client import NBAApiClient

        client = NBAApiClient()
        season_str = client.get_season_string()
    elif isinstance(normalized_seasons, list):
        season_str = normalized_seasons[0]  # Take first season
    else:
        season_str = normalized_seasons

    # Resolve entity (player or team)
    entity = resolve_entity(query=entity_name, entity_type=entity_type)

    logger.info(
        f"Fetching shot chart for {entity.name} ({entity.entity_type}) - {season_str}"
    )

    # Fetch raw shot data
    shots_df = await fetch_shot_chart_data(
        entity_id=entity.entity_id,
        entity_type=entity_type,
        season=season_str,
        season_type=season_type,
    )

    # Validate coordinates
    shots_df = validate_shot_coordinates(shots_df)

    # Calculate metadata
    total_shots = len(shots_df)
    made_shots = shots_df["SHOT_MADE_FLAG"].sum() if not shots_df.empty else 0
    fg_pct = (made_shots / total_shots) if total_shots > 0 else 0.0

    # Build response based on granularity
    result = {
        "entity": {
            "id": entity.entity_id,
            "name": entity.name,
            "type": entity_type,
        },
        "season": season_str,
        "season_type": season_type,
        "metadata": {
            "total_shots": int(total_shots),
            "made_shots": int(made_shots),
            "fg_pct": round(fg_pct, 3),
            "coordinate_system": "NBA API standard (origin at basket center, tenths of feet)",
        },
    }

    # Add requested data based on granularity
    if granularity in ["raw", "both"]:
        # Convert shots to list of dicts
        if not shots_df.empty:
            # Select relevant columns
            shot_cols = [
                "LOC_X",
                "LOC_Y",
                "SHOT_MADE_FLAG",
                "SHOT_DISTANCE",
                "SHOT_TYPE",
            ]
            # Only include columns that exist
            available_cols = [col for col in shot_cols if col in shots_df.columns]
            raw_shots = shots_df[available_cols].to_dict("records")
        else:
            raw_shots = []

        result["raw_shots"] = raw_shots

    if granularity in ["hexbin", "both"]:
        # Aggregate to hexbin
        hexbin_data = aggregate_to_hexbin(shots_df, grid_size=10, min_shots=5)
        result["hexbin"] = hexbin_data

    if granularity in ["summary", "both"]:
        # Calculate zone summary
        zone_summary = calculate_zone_summary(shots_df)
        result["zone_summary"] = zone_summary

    return result
