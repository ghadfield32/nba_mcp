"""
Raw data fetching from NBA API endpoints.

Fetches data as PyArrow tables with provenance tracking.
Integrates with existing NBA API client and tools.
"""

import time
import asyncio
from typing import Any, Dict, Optional, Union, Tuple
import pandas as pd
import pyarrow as pa
from datetime import datetime
import logging

from nba_mcp.api.entity_resolver import resolve_entity
from nba_mcp.api.tools.playercareerstats_leagueleaders_tools import (
    get_player_career_stats,
    get_league_leaders,
)
from nba_mcp.api.advanced_stats import (
    get_player_advanced_stats,
    get_team_advanced_stats,
    get_team_standings,
)
from nba_mcp.api.tools.leaguegamelog_tools import fetch_league_game_log
from nba_mcp.api.errors import EntityNotFoundError, NBAApiError
from nba_mcp.data.catalog import get_catalog
from nba_mcp.data.dataset_manager import ProvenanceInfo

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when data fetching fails."""

    pass


async def fetch_endpoint(
    endpoint: str, params: Dict[str, Any], as_arrow: bool = True
) -> Tuple[Union[pa.Table, pd.DataFrame], ProvenanceInfo]:
    """
    Fetch raw data from an NBA API endpoint.

    Args:
        endpoint: Endpoint name from the catalog
        params: Parameters for the endpoint
        as_arrow: If True, return PyArrow Table; if False, return pandas DataFrame

    Returns:
        Tuple of (data, provenance)

    Raises:
        FetchError: If endpoint not found or fetch fails
        ValueError: If required parameters are missing

    Examples:
        # Fetch player career stats
        table, prov = await fetch_endpoint(
            "player_career_stats",
            {"player_name": "LeBron James"}
        )

        # Fetch league leaders
        table, prov = await fetch_endpoint(
            "league_leaders",
            {"stat_category": "PTS", "season": "2023-24"}
        )
    """
    # Validate endpoint exists
    catalog = get_catalog()
    endpoint_meta = catalog.get_endpoint(endpoint)

    if endpoint_meta is None:
        available = [e.name for e in catalog.list_endpoints()]
        raise FetchError(
            f"Endpoint '{endpoint}' not found. Available endpoints: {', '.join(available)}"
        )

    # Track provenance
    provenance = ProvenanceInfo(
        source_endpoints=[endpoint],
        operations=["fetch"],
        parameters=params,
    )

    start_time = time.time()

    try:
        # Route to appropriate fetcher based on endpoint
        if endpoint == "player_career_stats":
            data = await _fetch_player_career_stats(params, provenance)

        elif endpoint == "player_advanced_stats":
            data = await _fetch_player_advanced_stats(params, provenance)

        elif endpoint == "team_standings":
            data = await _fetch_team_standings(params, provenance)

        elif endpoint == "team_advanced_stats":
            data = await _fetch_team_advanced_stats(params, provenance)

        elif endpoint == "team_game_log":
            data = await _fetch_team_game_log(params, provenance)

        elif endpoint == "league_leaders":
            data = await _fetch_league_leaders(params, provenance)

        elif endpoint == "shot_chart":
            data = await _fetch_shot_chart(params, provenance)

        elif endpoint == "live_scores":
            data = await _fetch_live_scores(params, provenance)

        elif endpoint == "play_by_play":
            # Play-by-play requires more complex handling
            raise FetchError(
                f"Endpoint '{endpoint}' requires special handling. "
                "Use the play_by_play() tool directly for now."
            )

        else:
            raise FetchError(f"Endpoint '{endpoint}' fetch not yet implemented")

        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000
        provenance.execution_time_ms = execution_time_ms

        # Convert to Arrow if requested
        if as_arrow:
            if isinstance(data, pd.DataFrame):
                table = pa.Table.from_pandas(data)
            else:
                # Handle dict or list of dicts
                table = pa.Table.from_pandas(pd.DataFrame(data))

            # Add provenance as metadata
            metadata = {
                "endpoint": endpoint,
                "fetched_at": datetime.utcnow().isoformat(),
                "row_count": str(table.num_rows),
                "column_count": str(table.num_columns),
            }
            table = table.replace_schema_metadata(metadata)

            return table, provenance
        else:
            return data, provenance

    except (EntityNotFoundError, NBAApiError, ValueError) as e:
        # Re-raise known errors with better context
        execution_time_ms = (time.time() - start_time) * 1000
        provenance.execution_time_ms = execution_time_ms
        logger.error(f"Failed to fetch from '{endpoint}': {e}")
        raise FetchError(f"Failed to fetch from '{endpoint}': {str(e)}") from e

    except Exception as e:
        # Catch unexpected errors
        execution_time_ms = (time.time() - start_time) * 1000
        provenance.execution_time_ms = execution_time_ms
        logger.exception(f"Unexpected error fetching from '{endpoint}'")
        raise FetchError(
            f"Unexpected error fetching from '{endpoint}': {str(e)}"
        ) from e


async def _fetch_player_career_stats(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch player career stats."""
    player_name = params.get("player_name")
    season = params.get("season")

    if not player_name:
        raise ValueError("player_name is required")

    # Use existing tool - it already handles entity resolution
    try:
        # Run synchronous function in thread pool
        result = await asyncio.to_thread(
            get_player_career_stats, player_name, season if season else []
        )
        provenance.nba_api_calls += 1

        if result.empty:
            logger.warning(f"No career stats found for {player_name}")

        return result

    except ValueError as e:
        # Player not found
        raise EntityNotFoundError(str(e))
    except Exception as e:
        raise NBAApiError(f"Failed to fetch player career stats: {e}")


async def _fetch_player_advanced_stats(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch player advanced stats."""
    player_name = params.get("player_name")
    season = params.get("season")

    if not player_name:
        raise ValueError("player_name is required")

    try:
        # This function already handles async and entity resolution
        stats_dict = await get_player_advanced_stats(player_name, season)
        provenance.nba_api_calls += 2  # Entity resolution + stats fetch

        # Convert dict to DataFrame
        return pd.DataFrame([stats_dict])

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch player advanced stats: {e}")


async def _fetch_team_standings(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch team standings."""
    season = params.get("season")
    conference = params.get("conference")

    try:
        # This function already handles async
        standings_list = await get_team_standings(season=season, conference=conference)
        provenance.nba_api_calls += 1

        # Convert TeamStanding objects to DataFrame
        data = [s.model_dump() for s in standings_list]
        return pd.DataFrame(data)

    except Exception as e:
        raise NBAApiError(f"Failed to fetch team standings: {e}")


async def _fetch_team_advanced_stats(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch team advanced stats."""
    team_name = params.get("team_name")
    season = params.get("season")

    if not team_name:
        raise ValueError("team_name is required")

    try:
        # This function already handles async and entity resolution
        stats_dict = await get_team_advanced_stats(team_name, season)
        provenance.nba_api_calls += 2  # Entity resolution + stats fetch

        # Convert dict to DataFrame
        return pd.DataFrame([stats_dict])

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch team advanced stats: {e}")


async def _fetch_team_game_log(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch team game log."""
    team_name = params.get("team")
    season = params.get("season")
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not team_name:
        raise ValueError("team is required")
    if not season:
        raise ValueError("season is required")

    try:
        # Use fetch_league_game_log with team filtering
        result = await asyncio.to_thread(
            fetch_league_game_log,
            season=season,
            team_name=team_name,
            date_from=date_from,
            date_to=date_to,
        )
        provenance.nba_api_calls += 1

        if result.empty:
            logger.warning(f"No game log found for {team_name} in {season}")

        return result

    except Exception as e:
        raise NBAApiError(f"Failed to fetch team game log: {e}")


async def _fetch_live_scores(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch live scores.

    Note: The live_scores tool returns formatted text, not structured data.
    This implementation returns a minimal DataFrame for compatibility.
    For production use, this should be refactored to use the NBA API directly.
    """
    target_date = params.get("target_date")

    # TODO: Refactor to use nba_api.live.nba.endpoints.scoreboard.ScoreBoard directly
    # For now, return a placeholder to indicate the limitation
    logger.warning(
        "live_scores endpoint returns formatted text, not structured data. "
        "Use the get_live_scores() tool directly for now."
    )

    provenance.nba_api_calls += 0  # No API call made

    return pd.DataFrame(
        {
            "MESSAGE": [
                "live_scores requires special handling. Use get_live_scores() tool directly."
            ],
            "TARGET_DATE": [target_date or "today"],
        }
    )


async def _fetch_league_leaders(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch league leaders."""
    stat_category = params.get("stat_category")
    season = params.get("season")
    per_mode = params.get("per_mode", "PerGame")
    limit = params.get("limit", 10)

    if not stat_category:
        raise ValueError("stat_category is required")

    try:
        # Use existing tool
        result = await asyncio.to_thread(
            get_league_leaders,
            season=season or "2024-25",  # Default to current season
            stat_category=stat_category,
            per_mode=per_mode,
        )
        provenance.nba_api_calls += 1

        # Apply limit if specified
        if limit and limit < len(result):
            result = result.head(limit)

        if result.empty:
            logger.warning(f"No league leaders found for {stat_category}")

        return result

    except Exception as e:
        raise NBAApiError(f"Failed to fetch league leaders: {e}")


async def _fetch_shot_chart(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch shot chart data.

    Note: The shot_chart tool (get_shot_chart) returns a complex nested structure.
    This implementation returns raw shot data for simplicity.
    """
    entity_name = params.get("entity_name")
    entity_type = params.get("entity_type", "player")
    season = params.get("season")
    granularity = params.get("granularity", "raw")
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not entity_name:
        raise ValueError("entity_name is required")

    try:
        # Resolve entity
        entity = resolve_entity(entity_name, entity_type=entity_type)
        provenance.nba_api_calls += 1

        # Import here to avoid circular dependency
        from nba_mcp.api.shot_charts import fetch_shot_chart_data

        # Fetch raw shot data
        shot_df = await fetch_shot_chart_data(
            entity_id=entity.entity_id,
            entity_type=entity_type,
            season=season or "2024-25",
            date_from=date_from,
            date_to=date_to,
        )
        provenance.nba_api_calls += 1

        if shot_df.empty:
            logger.warning(f"No shot chart data found for {entity_name}")

        # Return based on granularity
        if granularity == "raw":
            return shot_df
        elif granularity == "summary":
            # Simple summary aggregation
            if shot_df.empty:
                return pd.DataFrame()

            summary = {
                "TOTAL_SHOTS": len(shot_df),
                "SHOTS_MADE": shot_df["SHOT_MADE_FLAG"].sum(),
                "FG_PCT": (
                    shot_df["SHOT_MADE_FLAG"].mean() * 100 if not shot_df.empty else 0
                ),
                "THREE_PT_ATTEMPTS": len(shot_df[shot_df["SHOT_TYPE"] == "3PT Field Goal"]),
                "THREE_PT_MADE": shot_df[shot_df["SHOT_TYPE"] == "3PT Field Goal"][
                    "SHOT_MADE_FLAG"
                ].sum(),
            }
            return pd.DataFrame([summary])
        else:
            # For hexbin and both, return raw data
            # (hexbin aggregation can be done post-fetch)
            return shot_df

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch shot chart: {e}")


def validate_parameters(endpoint: str, params: Dict[str, Any]) -> None:
    """
    Validate parameters against endpoint schema.

    Args:
        endpoint: Endpoint name
        params: Parameters to validate

    Raises:
        ValueError: If required parameters are missing or invalid
    """
    catalog = get_catalog()
    endpoint_meta = catalog.get_endpoint(endpoint)

    if endpoint_meta is None:
        raise ValueError(f"Unknown endpoint: {endpoint}")

    # Check required parameters
    for param_schema in endpoint_meta.parameters:
        if param_schema.required and param_schema.name not in params:
            raise ValueError(
                f"Required parameter '{param_schema.name}' missing for endpoint '{endpoint}'"
            )

        # Check enum values if specified
        if param_schema.enum and param_schema.name in params:
            if params[param_schema.name] not in param_schema.enum:
                raise ValueError(
                    f"Invalid value for '{param_schema.name}': {params[param_schema.name]}. "
                    f"Must be one of: {', '.join(param_schema.enum)}"
                )
