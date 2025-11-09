"""
Raw data fetching from NBA API endpoints.

Fetches data as PyArrow tables with provenance tracking.
Integrates with existing NBA API client and tools.

UPDATED (2025-11-05): Integrated with unified fetching system
- Added endpoint registry integration
- Registered all endpoint handlers
- Backward compatible with existing code
- Can now use unified_fetch() or batch_fetch() for advanced operations
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
from nba_mcp.data.endpoint_registry import register_endpoint, get_registry

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when data fetching fails."""

    pass


async def fetch_endpoint(
    endpoint: str, params: Dict[str, Any], as_arrow: bool = True
) -> Tuple[Union[pa.Table, pd.DataFrame], ProvenanceInfo]:
    """
    Fetch raw data from an NBA API endpoint.

    NOTE: This function now uses the unified endpoint registry system!
    All endpoints are auto-registered using decorators, making it easy
    to add new endpoints or modify existing ones.

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

        # For advanced usage, use unified_fetch() for filters
        # from nba_mcp.data.unified_fetch import unified_fetch
        # result = await unified_fetch(
        #     "team_game_log",
        #     {"team": "Lakers", "season": "2023-24"},
        #     filters={"WL": ["==", "W"]}
        # )
    """
    # Use the registry to get the handler
    registry = get_registry()
    handler = registry.get_handler(endpoint)

    if handler is None:
        # Fallback to catalog check for better error message
        catalog = get_catalog()
        endpoint_meta = catalog.get_endpoint(endpoint)

        if endpoint_meta is None:
            available = [e.name for e in catalog.list_endpoints()]
            raise FetchError(
                f"Endpoint '{endpoint}' not found. Available endpoints: {', '.join(available)}"
            )
        else:
            # Endpoint exists in catalog but not registered
            raise FetchError(
                f"Endpoint '{endpoint}' found in catalog but handler not registered. "
                f"This is a bug - please report it."
            )

    # Track provenance
    provenance = ProvenanceInfo(
        source_endpoints=[endpoint],
        operations=["fetch"],
        parameters=params,
    )

    start_time = time.time()

    try:
        # Call the registered handler
        data = await handler(params, provenance)

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


@register_endpoint(
    "player_career_stats",
    required_params=["player_name"],
    optional_params=["season"],
    description="Get comprehensive career statistics for a player across all seasons",
    tags={"player", "stats", "career"}
)
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


@register_endpoint(
    "player_advanced_stats",
    required_params=["player_name"],
    optional_params=["season"],
    description="Get advanced efficiency metrics for a player (TS%, Usage%, PER, etc.)",
    tags={"player", "stats", "advanced"}
)
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


@register_endpoint(
    "team_standings",
    required_params=[],
    optional_params=["season", "conference"],
    description="Get conference and division standings with win/loss records",
    tags={"team", "standings", "league"}
)
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


@register_endpoint(
    "team_advanced_stats",
    required_params=["team_name"],
    optional_params=["season"],
    description="Get team efficiency metrics (OffRtg, DefRtg, Pace, Four Factors)",
    tags={"team", "stats", "advanced"}
)
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


@register_endpoint(
    "team_game_log",
    required_params=["team", "season"],
    optional_params=["date_from", "date_to", "outcome"],
    description="Get historical game-by-game results for a team",
    tags={"team", "game", "log"}
)
async def _fetch_team_game_log(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch team game log."""
    team_name = params.get("team")
    season = params.get("season")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    outcome = params.get("outcome")  # W/L filter pushed from filter_pushdown

    if not team_name:
        raise ValueError("team is required")
    if not season:
        raise ValueError("season is required")

    try:
        # Use fetch_league_game_log with team filtering and outcome filter
        result = await asyncio.to_thread(
            fetch_league_game_log,
            season=season,
            team_name=team_name,
            date_from=date_from,
            date_to=date_to,
            outcome=outcome,  # Pass outcome to enable W/L filtering at API level
        )
        provenance.nba_api_calls += 1

        if result.empty:
            logger.warning(f"No game log found for {team_name} in {season}")

        return result

    except Exception as e:
        raise NBAApiError(f"Failed to fetch team game log: {e}")


@register_endpoint(
    "live_scores",
    required_params=[],
    optional_params=["target_date"],
    description="Get current or historical game scores and status",
    tags={"game", "live", "scores"}
)
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


@register_endpoint(
    "league_leaders",
    required_params=["stat_category"],
    optional_params=["season", "per_mode", "limit"],
    description="Get top performers in any statistical category",
    tags={"league", "leaders", "stats"}
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


@register_endpoint(
    "shot_chart",
    required_params=["entity_name"],
    optional_params=["entity_type", "season", "granularity", "date_from", "date_to"],
    description="Get shot location data with optional hexagonal binning",
    tags={"shot", "chart", "spatial"}
)
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


@register_endpoint(
    "player_game_log",
    required_params=["player_name"],
    optional_params=["season", "season_type", "last_n_games", "date_from", "date_to"],
    description="Get game-by-game statistics for a specific player",
    tags={"player", "game", "log", "stats"}
)
async def _fetch_player_game_log(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch player game log.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - SEASON_TYPE: Regular Season or Playoffs
    """
    player_name = params.get("player_name")
    season = params.get("season")
    season_type = params.get("season_type", "Regular Season")
    last_n_games = params.get("last_n_games")

    # Phase 2F: Support filter pushdown for date range
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not player_name:
        raise ValueError("player_name is required")

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()
        result = await client.get_player_game_log(
            player_name=player_name,
            season=season,
            season_type=season_type,
            last_n_games=last_n_games,
            date_from=date_from,  # Phase 2F: Pass date filter
            date_to=date_to,      # Phase 2F: Pass date filter
            as_dataframe=True
        )
        provenance.nba_api_calls += 1

        if isinstance(result, dict) and "error" in result:
            raise NBAApiError(result["error"])

        if result.empty:
            logger.warning(f"No game log found for {player_name}")

        return result

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch player game log: {e}")


@register_endpoint(
    "box_score",
    required_params=["game_id"],
    optional_params=[],
    description="Get full box score with player stats and quarter-by-quarter breakdowns",
    tags={"game", "box_score", "stats"}
)
async def _fetch_box_score(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch box score data."""
    game_id = params.get("game_id")

    if not game_id:
        raise ValueError("game_id is required")

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()
        result = await client.get_box_score(
            game_id=game_id,
            as_dataframe=True
        )
        provenance.nba_api_calls += 1

        if isinstance(result, dict) and "error" in result:
            raise NBAApiError(result["error"])

        # Return player_stats as the main table (most commonly used)
        # Other tables (team_stats, line_score) are in the dict
        player_stats = result.get("player_stats", pd.DataFrame())

        if player_stats.empty:
            logger.warning(f"No box score data found for game_id={game_id}")

        return player_stats

    except Exception as e:
        raise NBAApiError(f"Failed to fetch box score: {e}")


@register_endpoint(
    "clutch_stats",
    required_params=["entity_name"],
    optional_params=["entity_type", "season", "per_mode", "date_from", "date_to", "outcome", "location"],
    description="Get clutch time statistics (final 5 minutes, score within 5 points)",
    tags={"stats", "clutch", "player", "team"}
)
async def _fetch_clutch_stats(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch clutch statistics.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - SEASON_TYPE: Regular Season or Playoffs
    - WL: Win/Loss filtering (converted to outcome parameter)
    - MATCHUP: Home/Away filtering (converted to location parameter)
    - PER_MODE: Per game or totals
    """
    entity_name = params.get("entity_name")
    entity_type = params.get("entity_type", "player")
    season = params.get("season")
    per_mode = params.get("per_mode", "PerGame")

    # Phase 2F: Support filter pushdown for date range, outcome, location
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    outcome = params.get("outcome")
    location = params.get("location")

    if not entity_name:
        raise ValueError("entity_name is required")

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()
        result = await client.get_clutch_stats(
            entity_name=entity_name,
            entity_type=entity_type,
            season=season,
            per_mode=per_mode,
            date_from=date_from,  # Phase 2F: Pass date filter
            date_to=date_to,      # Phase 2F: Pass date filter
            outcome=outcome,      # Phase 2F: Pass W/L filter
            location=location     # Phase 2F: Pass Home/Away filter
        )
        provenance.nba_api_calls += 2  # Entity resolution + stats fetch

        if isinstance(result, dict) and "error" in result:
            raise NBAApiError(result["error"])

        if result.empty:
            logger.warning(f"No clutch stats found for {entity_name}")

        return result

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch clutch stats: {e}")


@register_endpoint(
    "player_head_to_head",
    required_params=["player1_name", "player2_name"],
    optional_params=["season", "date_from", "date_to"],
    description="Get head-to-head matchup stats for two players",
    tags={"player", "matchup", "comparison", "stats"}
)
async def _fetch_player_head_to_head(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch player head-to-head matchup stats.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - SEASON_TYPE: Regular Season or Playoffs
    """
    player1_name = params.get("player1_name")
    player2_name = params.get("player2_name")
    season = params.get("season")

    # Phase 2F: Support filter pushdown for date range
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not player1_name or not player2_name:
        raise ValueError("Both player1_name and player2_name are required")

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()
        result = await client.get_player_head_to_head(
            player1_name=player1_name,
            player2_name=player2_name,
            season=season,
            date_from=date_from,  # Phase 2F: Pass date filter
            date_to=date_to       # Phase 2F: Pass date filter
        )
        provenance.nba_api_calls += 3  # 2 player game logs + entity resolutions

        if isinstance(result, dict) and "error" in result:
            raise NBAApiError(result["error"])

        # Combine both player stats into a single DataFrame
        player1_stats = result.get("player1_stats", pd.DataFrame())
        player2_stats = result.get("player2_stats", pd.DataFrame())

        # Concatenate into single table
        combined_stats = pd.concat([player1_stats, player2_stats], ignore_index=True)

        if combined_stats.empty:
            logger.warning(f"No head-to-head matchups found for {player1_name} vs {player2_name}")

        return combined_stats

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch player head-to-head: {e}")


@register_endpoint(
    "player_performance_splits",
    required_params=["player_name"],
    optional_params=["season", "last_n_games", "date_from", "date_to"],
    description="Get performance splits with home/away, win/loss, and trend analysis",
    tags={"player", "splits", "analysis", "stats"}
)
async def _fetch_player_performance_splits(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch player performance splits.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - SEASON_TYPE: Regular Season or Playoffs
    """
    player_name = params.get("player_name")
    season = params.get("season")
    last_n_games = params.get("last_n_games", 10)

    # Phase 2F: Support filter pushdown for date range
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not player_name:
        raise ValueError("player_name is required")

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()
        result = await client.get_player_performance_splits(
            player_name=player_name,
            season=season,
            last_n_games=last_n_games,
            date_from=date_from,  # Phase 2F: Pass date filter
            date_to=date_to       # Phase 2F: Pass date filter
        )
        provenance.nba_api_calls += 2  # Entity resolution + game log fetch

        if isinstance(result, dict) and "error" in result:
            raise NBAApiError(result["error"])

        # Convert dict of splits into DataFrame
        splits_data = []
        for split_name, split_stats in result.items():
            if isinstance(split_stats, dict) and not split_name.startswith("_"):
                row = {"split_type": split_name}
                row.update(split_stats)
                splits_data.append(row)

        splits_df = pd.DataFrame(splits_data)

        if splits_df.empty:
            logger.warning(f"No performance splits found for {player_name}")

        return splits_df

    except EntityNotFoundError:
        raise
    except Exception as e:
        raise NBAApiError(f"Failed to fetch player performance splits: {e}")


@register_endpoint(
    "play_by_play",
    required_params=[],
    optional_params=["game_date", "team", "start_period", "end_period", "start_clock", "include_lineups"],
    description="Get play-by-play event data for games with optional lineup tracking",
    tags={"game", "play_by_play", "events", "lineups"}
)
async def _fetch_play_by_play(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """Fetch play-by-play data."""
    game_date = params.get("game_date")
    team = params.get("team")
    start_period = params.get("start_period", 1)
    end_period = params.get("end_period", 4)
    start_clock = params.get("start_clock")
    include_lineups = params.get("include_lineups", False)

    try:
        # Import client here to avoid circular dependency
        from nba_mcp.api.client import NBAApiClient

        client = NBAApiClient()

        # Note: The play_by_play method returns formatted text, not structured data
        # For structured data, we need to use the underlying API directly
        if game_date and team:
            # Get game_id from date and team
            from nba_mcp.api.tools.playbyplayv3_or_realtime import PastGamesPlaybyPlay

            pbp_instance = PastGamesPlaybyPlay.from_team_date(
                when=game_date,
                team=team,
                show_choices=False
            )

            if pbp_instance and pbp_instance.game_id:
                # Fetch using PlayByPlayFetcher
                from nba_mcp.api.tools.playbyplayv3_or_realtime import PlayByPlayFetcher

                fetcher = PlayByPlayFetcher(
                    game_id=pbp_instance.game_id,
                    start_period=start_period,
                    end_period=end_period
                )

                df = fetcher.fetch()
                provenance.nba_api_calls += 1

                if df.empty:
                    logger.warning(f"No play-by-play data found for {team} on {game_date}")

                return df
            else:
                raise NBAApiError(f"No game found for {team} on {game_date}")
        else:
            # Return placeholder indicating special handling needed
            logger.warning(
                "play_by_play requires game_date and team for structured data. "
                "Use the play_by_play() tool directly for formatted output."
            )

            provenance.nba_api_calls += 0  # No API call made

            return pd.DataFrame(
                {
                    "MESSAGE": [
                        "play_by_play requires game_date and team parameters for structured data"
                    ],
                    "GAME_DATE": [game_date or "not specified"],
                    "TEAM": [team or "not specified"],
                }
            )

    except Exception as e:
        raise NBAApiError(f"Failed to fetch play-by-play: {e}")


# ============================================================================
# Phase 2H-C: League-Wide Endpoints for Caching
# ============================================================================


@register_endpoint(
    "league_player_games",
    required_params=["season"],
    optional_params=["season_type", "date_from", "date_to", "outcome", "location"],
    description="Get game-by-game statistics for ALL players in a season (league-wide query)",
    tags={"league", "player", "game", "log", "stats", "all"}
)
async def _fetch_league_player_games(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch league-wide player game logs (all players).

    Phase 2H-C: This endpoint enables caching for "all players" queries
    that were previously forced to use direct API calls.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - SEASON_TYPE: Regular Season or Playoffs
    - OUTCOME: W/L filtering
    - LOCATION: Home/Road filtering

    Args:
        params: Must contain 'season', optional filters
        provenance: Provenance tracking

    Returns:
        DataFrame with all player games for the season
    """
    season = params.get("season")
    season_type = params.get("season_type", "Regular Season")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    outcome = params.get("outcome")
    location = params.get("location")

    if not season:
        raise ValueError("season is required for league_player_games")

    try:
        # Use PlayerGameLogs with no player_id filter (league-wide)
        from nba_api.stats.endpoints import PlayerGameLogs

        # Map season format if needed
        if isinstance(season, list):
            season = season[0] if season else None

        # Build API parameters
        api_params = {
            "season_nullable": season,
            "season_type_nullable": season_type,
            "date_from_nullable": date_from or "",
            "date_to_nullable": date_to or "",
            "outcome_nullable": outcome or "",
            "location_nullable": location or "",
            "player_id_nullable": "",  # Empty = all players
        }

        # Fetch from NBA API
        result = await asyncio.to_thread(
            PlayerGameLogs,
            **api_params
        )
        df = result.get_data_frames()[0]
        provenance.nba_api_calls += 1

        if df.empty:
            logger.warning(
                f"No player games found for season {season} "
                f"(season_type={season_type}, date_from={date_from}, date_to={date_to})"
            )

        logger.info(
            f"[league_player_games] Retrieved {len(df)} player games for {season}"
        )

        return df

    except Exception as e:
        raise NBAApiError(f"Failed to fetch league player games: {e}")


@register_endpoint(
    "league_team_games",
    required_params=["season"],
    optional_params=["season_type", "date_from", "date_to", "outcome"],
    description="Get game-by-game results for ALL teams in a season (league-wide query)",
    tags={"league", "team", "game", "log", "all"}
)
async def _fetch_league_team_games(
    params: Dict[str, Any], provenance: ProvenanceInfo
) -> pd.DataFrame:
    """
    Fetch league-wide team game logs (all teams).

    Phase 2H-C: This endpoint enables caching for "all teams" queries
    that were previously forced to use direct API calls.

    Supports filter pushdown for:
    - GAME_DATE: Converts to date_from/date_to parameters
    - SEASON: Season filtering
    - OUTCOME: W/L filtering

    Args:
        params: Must contain 'season', optional filters
        provenance: Provenance tracking

    Returns:
        DataFrame with all team games for the season
    """
    season = params.get("season")
    season_type = params.get("season_type", "Regular Season")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    outcome = params.get("outcome")

    if not season:
        raise ValueError("season is required for league_team_games")

    try:
        # Reuse existing fetch_league_game_log function (no team_name = all teams)
        result = await asyncio.to_thread(
            fetch_league_game_log,
            season=season,
            team_name=None,  # None = all teams
            season_type=season_type,
            date_from=date_from,
            date_to=date_to,
            outcome=outcome,
        )
        provenance.nba_api_calls += 1

        if result.empty:
            logger.warning(
                f"No team games found for season {season} "
                f"(season_type={season_type}, date_from={date_from}, date_to={date_to})"
            )

        logger.info(
            f"[league_team_games] Retrieved {len(result)} team games for {season}"
        )

        return result

    except Exception as e:
        raise NBAApiError(f"Failed to fetch league team games: {e}")


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
