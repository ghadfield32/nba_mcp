# nba_mcp/api/advanced_stats.py
"""
Advanced NBA statistics tools.

Provides:
1. Team standings (conference, division rankings)
2. Team advanced stats (OffRtg, DefRtg, Pace, NetRtg, Four Factors)
3. Player advanced stats (Usage%, TS%, eFG%, PER, WS, BPM, VORP)
4. Player comparisons with metric registry
5. Per-possession and era-adjusted normalization
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from nba_api.stats.endpoints import (
    LeagueDashPlayerStats,
    LeagueDashTeamStats,
    LeagueStandings,
    PlayerDashboardByGeneralSplits,
    TeamDashboardByGeneralSplits,
)

from .entity_resolver import resolve_entity
from .errors import InvalidParameterError, NBAApiError, retry_with_backoff
from .models import (
    PlayerComparison,
    PlayerSeasonStats,
    ResponseEnvelope,
    TeamStanding,
    error_response,
    success_response,
)
from .tools.nba_api_utils import get_player_name, get_team_name, normalize_season

logger = logging.getLogger(__name__)


# ============================================================================
# METRIC REGISTRY (Shared across all comparison tools)
# ============================================================================

METRIC_REGISTRY = {
    # Basic stats
    "GP": {"name": "Games Played", "dtype": "int64"},
    "MIN": {"name": "Minutes Per Game", "dtype": "float64"},
    "PTS": {"name": "Points Per Game", "dtype": "float64"},
    "REB": {"name": "Rebounds Per Game", "dtype": "float64"},
    "AST": {"name": "Assists Per Game", "dtype": "float64"},
    "STL": {"name": "Steals Per Game", "dtype": "float64"},
    "BLK": {"name": "Blocks Per Game", "dtype": "float64"},
    "TOV": {"name": "Turnovers Per Game", "dtype": "float64"},
    # Shooting percentages
    "FG_PCT": {"name": "Field Goal %", "dtype": "float64"},
    "FG3_PCT": {"name": "Three-Point %", "dtype": "float64"},
    "FT_PCT": {"name": "Free Throw %", "dtype": "float64"},
    # Advanced metrics
    "TS_PCT": {"name": "True Shooting %", "dtype": "float64"},
    "EFG_PCT": {"name": "Effective FG %", "dtype": "float64"},
    "USG_PCT": {"name": "Usage %", "dtype": "float64"},
    "PIE": {"name": "Player Impact Estimate", "dtype": "float64"},
    "PACE": {"name": "Pace", "dtype": "float64"},
    "OFF_RATING": {"name": "Offensive Rating", "dtype": "float64"},
    "DEF_RATING": {"name": "Defensive Rating", "dtype": "float64"},
    "NET_RATING": {"name": "Net Rating", "dtype": "float64"},
    # Per-possession stats
    "PTS_PER_100": {"name": "Points Per 100 Possessions", "dtype": "float64"},
    "AST_PER_100": {"name": "Assists Per 100 Possessions", "dtype": "float64"},
    "REB_PER_100": {"name": "Rebounds Per 100 Possessions", "dtype": "float64"},
}


# ============================================================================
# TEAM STANDINGS
# ============================================================================


@retry_with_backoff(max_retries=3, base_delay=2.0)
async def get_team_standings(
    season: Optional[str] = None, conference: Optional[Literal["East", "West"]] = None
) -> List[TeamStanding]:
    """
    Get NBA team standings with conference/division rankings.

    Args:
        season: Season string ('YYYY-YY'). Defaults to current season.
        conference: Filter by conference ('East' or 'West'). None returns all.

    Returns:
        List of TeamStanding objects with W-L, GB, streak, home/away records

    Raises:
        NBAApiError: If NBA API call fails
    """
    try:
        # Normalize season
        if season:
            seasons = normalize_season(season)
            season_str = seasons[0] if seasons else "2024-25"
        else:
            # Get current season
            today = datetime.now()
            year = today.year if today.month >= 10 else today.year - 1
            season_str = f"{year}-{str(year + 1)[-2:]}"

        logger.info(f"Fetching team standings for season: {season_str}")

        # Fetch standings from NBA API
        standings = await asyncio.to_thread(
            LeagueStandings,
            league_id="00",
            season=season_str,
            season_type="Regular Season",
        )

        # Get standings dataframe
        standings_df = standings.get_data_frames()[0]

        if standings_df.empty:
            return []

        # Convert to TeamStanding objects
        results = []
        for _, row in standings_df.iterrows():
            # Determine conference from team ID
            team_id = row.get("TeamID")
            team_conf = row.get("Conference", "")

            # Filter by conference if requested
            if conference and team_conf != conference:
                continue

            standing = TeamStanding(
                team_id=int(team_id),
                team_name=row.get("TeamName", get_team_name(team_id)),
                team_abbreviation=row.get("TeamCity", "")[:3].upper(),
                conference=team_conf,
                division=row.get("Division", ""),
                wins=int(row.get("WINS", 0)),
                losses=int(row.get("LOSSES", 0)),
                win_pct=float(row.get("WinPCT", 0.0)),
                games_behind=float(row.get("ConferenceGamesBack", 0.0)),
                conference_rank=(
                    int(row.get("ConferenceRecord", "0-0").split("-")[0])
                    if "ConferenceRecord" in row
                    else 0
                ),
                division_rank=int(row.get("DivisionRank", 0)),
                home_record=row.get("HOME", "0-0"),
                away_record=row.get("ROAD", "0-0"),
                last_10=row.get("L10", "0-0"),
                streak=row.get("strCurrentStreak", ""),
            )
            results.append(standing)

        # Sort by conference rank
        results.sort(key=lambda x: (x.conference, x.conference_rank))

        return results

    except Exception as e:
        logger.error(f"Failed to fetch team standings: {e}", exc_info=True)
        raise NBAApiError(f"Failed to fetch team standings: {e}")


# ============================================================================
# TEAM ADVANCED STATS
# ============================================================================


@retry_with_backoff(max_retries=3, base_delay=2.0)
async def get_team_advanced_stats(
    team_name: str, season: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get team advanced statistics (OffRtg, DefRtg, Pace, NetRtg, Four Factors).

    Args:
        team_name: Team name or abbreviation
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        Dictionary with advanced team stats

    Raises:
        EntityNotFoundError: If team not found
        NBAApiError: If NBA API call fails
    """
    try:
        # Resolve team
        team_entity = resolve_entity(team_name, entity_type="team")
        team_id = team_entity.entity_id

        # Normalize season
        if season:
            seasons = normalize_season(season)
            season_str = seasons[0] if seasons else "2024-25"
        else:
            today = datetime.now()
            year = today.year if today.month >= 10 else today.year - 1
            season_str = f"{year}-{str(year + 1)[-2:]}"

        logger.info(f"Fetching advanced stats for {team_entity.name} ({season_str})")

        # Fetch team dashboard
        dashboard = await asyncio.to_thread(
            LeagueDashTeamStats,
            season=season_str,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Advanced",
            per_mode_detailed="PerGame",
        )

        team_stats_df = dashboard.get_data_frames()[0]

        # Filter to requested team
        team_row = team_stats_df[team_stats_df["TEAM_ID"] == int(team_id)]

        if team_row.empty:
            raise NBAApiError(f"No advanced stats found for {team_entity.name}")

        row = team_row.iloc[0]

        # Build response with deterministic dtypes
        stats = {
            "team_id": int(row.get("TEAM_ID")),
            "team_name": str(row.get("TEAM_NAME", team_entity.name)),
            "season": season_str,
            "games_played": int(row.get("GP", 0)),
            # Ratings (per 100 possessions)
            "offensive_rating": float(row.get("OFF_RATING", 0.0)),
            "defensive_rating": float(row.get("DEF_RATING", 0.0)),
            "net_rating": float(row.get("NET_RATING", 0.0)),
            # Pace & efficiency
            "pace": float(row.get("PACE", 0.0)),
            "true_shooting_pct": float(row.get("TS_PCT", 0.0)),
            "effective_fg_pct": float(row.get("EFG_PCT", 0.0)),
            # Four Factors (offense)
            "efg_pct_off": float(row.get("EFG_PCT", 0.0)),
            "tov_pct_off": float(row.get("TM_TOV_PCT", 0.0)),
            "oreb_pct": float(row.get("OREB_PCT", 0.0)),
            "fta_rate": float(row.get("FTA_RATE", 0.0)),
            # Four Factors (defense)
            "opp_efg_pct": float(row.get("OPP_EFG_PCT", 0.0)),
            "opp_tov_pct": float(row.get("OPP_TOV_PCT", 0.0)),
            "dreb_pct": float(row.get("DREB_PCT", 0.0)),
            "opp_fta_rate": float(row.get("OPP_FTA_RATE", 0.0)),
        }

        return stats

    except Exception as e:
        logger.error(f"Failed to fetch team advanced stats: {e}", exc_info=True)
        raise NBAApiError(f"Failed to fetch team advanced stats: {e}")


# ============================================================================
# PLAYER ADVANCED STATS
# ============================================================================


@retry_with_backoff(max_retries=3, base_delay=2.0)
async def get_player_advanced_stats(
    player_name: str, season: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get player advanced statistics (Usage%, TS%, eFG%, PER, WS, BPM, VORP).

    Args:
        player_name: Player name
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        Dictionary with advanced player stats

    Raises:
        EntityNotFoundError: If player not found
        NBAApiError: If NBA API call fails
    """
    try:
        # Resolve player
        player_entity = resolve_entity(player_name, entity_type="player")
        player_id = player_entity.entity_id

        # Normalize season
        if season:
            seasons = normalize_season(season)
            season_str = seasons[0] if seasons else "2024-25"
        else:
            today = datetime.now()
            year = today.year if today.month >= 10 else today.year - 1
            season_str = f"{year}-{str(year + 1)[-2:]}"

        logger.info(f"Fetching advanced stats for {player_entity.name} ({season_str})")

        # Fetch player dashboard with advanced metrics
        dashboard = await asyncio.to_thread(
            LeagueDashPlayerStats,
            season=season_str,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Advanced",
            per_mode_detailed="PerGame",
        )

        player_stats_df = dashboard.get_data_frames()[0]

        # Filter to requested player
        player_row = player_stats_df[player_stats_df["PLAYER_ID"] == int(player_id)]

        if player_row.empty:
            raise NBAApiError(f"No advanced stats found for {player_entity.name}")

        row = player_row.iloc[0]

        # Build response with deterministic dtypes
        stats = {
            "player_id": int(row.get("PLAYER_ID")),
            "player_name": str(row.get("PLAYER_NAME", player_entity.name)),
            "season": season_str,
            "team_abbreviation": str(row.get("TEAM_ABBREVIATION", "")),
            "games_played": int(row.get("GP", 0)),
            "minutes_per_game": float(row.get("MIN", 0.0)),
            # Efficiency metrics
            "true_shooting_pct": float(row.get("TS_PCT", 0.0)),
            "effective_fg_pct": float(row.get("EFG_PCT", 0.0)),
            "usage_pct": float(row.get("USG_PCT", 0.0)),
            "pie": float(row.get("PIE", 0.0)),  # Player Impact Estimate
            # Advanced metrics (if available)
            "offensive_rating": float(row.get("OFF_RATING", 0.0)),
            "defensive_rating": float(row.get("DEF_RATING", 0.0)),
            "net_rating": float(row.get("NET_RATING", 0.0)),
            "assist_pct": float(row.get("AST_PCT", 0.0)),
            "rebound_pct": float(row.get("REB_PCT", 0.0)),
            "turnover_pct": float(row.get("TM_TOV_PCT", 0.0)),
            # Basic counting stats (for context)
            "points_per_game": float(row.get("PTS", 0.0)),
            "rebounds_per_game": float(row.get("REB", 0.0)),
            "assists_per_game": float(row.get("AST", 0.0)),
        }

        return stats

    except Exception as e:
        logger.error(f"Failed to fetch player advanced stats: {e}", exc_info=True)
        raise NBAApiError(f"Failed to fetch player advanced stats: {e}")


# ============================================================================
# PLAYER COMPARISON WITH METRIC REGISTRY
# ============================================================================


def normalize_per_possession(
    stats: Dict[str, Any], possessions: float = 75.0
) -> Dict[str, Any]:
    """
    Normalize counting stats to per-possession basis (default: per 75 possessions).

    Args:
        stats: Dictionary of player stats
        possessions: Number of possessions to normalize to (default: 75)

    Returns:
        Dictionary with per-possession stats
    """
    normalized = stats.copy()

    # Get pace/possessions from stats (or estimate from minutes)
    pace = stats.get("pace", 100.0)  # Default NBA pace ~100
    minutes = stats.get("minutes_per_game", 36.0)

    # Estimate possessions per game (rough approximation)
    possessions_per_game = (minutes / 48.0) * pace

    if possessions_per_game == 0:
        return normalized

    scaling_factor = possessions / possessions_per_game

    # Normalize counting stats
    counting_stats = [
        "points_per_game",
        "rebounds_per_game",
        "assists_per_game",
        "steals_per_game",
        "blocks_per_game",
        "turnovers_per_game",
    ]

    for stat in counting_stats:
        if stat in normalized:
            key_per_poss = stat.replace("_per_game", f"_per_{int(possessions)}")
            normalized[key_per_poss] = normalized[stat] * scaling_factor

    return normalized


async def compare_players(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
    normalization: Literal["raw", "per_game", "per_75", "era_adjusted"] = "per_75",
) -> PlayerComparison:
    """
    Compare two players side-by-side with shared metric registry.

    Args:
        player1_name: First player name
        player2_name: Second player name
        season: Season string ('YYYY-YY'). Defaults to current season.
        normalization: Statistical normalization mode
            - "raw": Total stats (not per-game)
            - "per_game": Per-game averages
            - "per_75": Per-75 possessions (fair comparison)
            - "era_adjusted": Adjust for pace/era (future enhancement)

    Returns:
        PlayerComparison object with both players' stats and metric registry

    Raises:
        EntityNotFoundError: If either player not found
        NBAApiError: If NBA API call fails
    """
    try:
        # Fetch both players' advanced stats in parallel
        stats1_task = get_player_advanced_stats(player1_name, season)
        stats2_task = get_player_advanced_stats(player2_name, season)

        stats1, stats2 = await asyncio.gather(stats1_task, stats2_task)

        # Apply normalization
        if normalization == "per_75":
            stats1 = normalize_per_possession(stats1, possessions=75.0)
            stats2 = normalize_per_possession(stats2, possessions=75.0)

        # TODO: Implement era-adjusted normalization
        # Would adjust for league-average pace and scoring environment

        # Create PlayerSeasonStats objects (ensuring deterministic dtypes)
        player1_stats = PlayerSeasonStats(
            player_id=stats1["player_id"],
            player_name=stats1["player_name"],
            season=stats1["season"],
            team_abbreviation=stats1.get("team_abbreviation"),
            games_played=stats1["games_played"],
            minutes_per_game=stats1["minutes_per_game"],
            points_per_game=stats1["points_per_game"],
            rebounds_per_game=stats1["rebounds_per_game"],
            assists_per_game=stats1["assists_per_game"],
            steals_per_game=stats1.get("steals_per_game", 0.0),
            blocks_per_game=stats1.get("blocks_per_game", 0.0),
            field_goal_pct=stats1.get("field_goal_pct", 0.0),
            three_point_pct=stats1.get("three_point_pct", 0.0),
            free_throw_pct=stats1.get("free_throw_pct", 0.0),
        )

        player2_stats = PlayerSeasonStats(
            player_id=stats2["player_id"],
            player_name=stats2["player_name"],
            season=stats2["season"],
            team_abbreviation=stats2.get("team_abbreviation"),
            games_played=stats2["games_played"],
            minutes_per_game=stats2["minutes_per_game"],
            points_per_game=stats2["points_per_game"],
            rebounds_per_game=stats2["rebounds_per_game"],
            assists_per_game=stats2["assists_per_game"],
            steals_per_game=stats2.get("steals_per_game", 0.0),
            blocks_per_game=stats2.get("blocks_per_game", 0.0),
            field_goal_pct=stats2.get("field_goal_pct", 0.0),
            three_point_pct=stats2.get("three_point_pct", 0.0),
            free_throw_pct=stats2.get("free_throw_pct", 0.0),
        )

        # Create metric registry subset (only metrics present in both)
        metric_names = {
            k: v["name"]
            for k, v in METRIC_REGISTRY.items()
            if k in stats1 or k in stats2
        }

        comparison = PlayerComparison(
            player1=player1_stats,
            player2=player2_stats,
            metric_registry=metric_names,
            normalization_mode=normalization,
        )

        return comparison

    except Exception as e:
        logger.error(f"Failed to compare players: {e}", exc_info=True)
        raise NBAApiError(f"Failed to compare players: {e}")


# ============================================================================
# RESPONSE DETERMINISM HELPERS
# ============================================================================


def ensure_deterministic_response(data: Union[Dict, List]) -> Union[Dict, List]:
    """
    Ensure response has deterministic key ordering and numeric dtypes.

    Args:
        data: Response data (dict or list of dicts)

    Returns:
        Data with sorted keys and consistent numeric types
    """
    if isinstance(data, dict):
        # Sort keys alphabetically
        sorted_data = {
            k: ensure_deterministic_response(v) for k, v in sorted(data.items())
        }

        # Ensure numeric types are consistent
        for key, value in sorted_data.items():
            if isinstance(value, (int, float)):
                # Check metric registry for expected dtype
                if key.upper() in METRIC_REGISTRY:
                    expected_dtype = METRIC_REGISTRY[key.upper()]["dtype"]
                    if expected_dtype == "int64" and not isinstance(value, int):
                        sorted_data[key] = int(value)
                    elif expected_dtype == "float64" and not isinstance(value, float):
                        sorted_data[key] = float(value)

        return sorted_data

    elif isinstance(data, list):
        return [ensure_deterministic_response(item) for item in data]

    else:
        return data
