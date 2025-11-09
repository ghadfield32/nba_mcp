"""
Data Grouping System for NBA MCP

Provides standardized interfaces for accessing NBA data at different aggregation levels:
- player/game, player/team/game, player/season, player/team/season
- team/game, team/season
- play-by-play with lineup tracking
- shot charts (spatial grouping)

Each grouping level has specific granularity constraints and column sets.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class GranularityLevel(str, Enum):
    """Time/spatial precision levels for NBA data"""
    SECOND = "second"           # Play-by-play events (PT09M28.50S)
    DAY = "day"                # Game logs (YYYY-MM-DD)
    SEASON = "season"           # Season aggregations (YYYY-YY)
    COMBINATION = "combination" # Lineup/matchup groupings
    SPATIAL = "spatial"         # Shot charts (X, Y coordinates + zones)


class GroupingLevel(str, Enum):
    """Data aggregation/grouping levels"""
    PLAYER_GAME = "player/game"
    PLAYER_TEAM_GAME = "player/team/game"
    PLAYER_SEASON = "player/season"
    PLAYER_TEAM_SEASON = "player/team/season"
    TEAM_GAME = "team/game"
    TEAM_SEASON = "team/season"
    PLAY_BY_PLAY_PLAYER = "play_by_play/player"
    PLAY_BY_PLAY_TEAM = "play_by_play/team"
    SHOT_CHART_PLAYER = "shot_chart/player"
    SHOT_CHART_TEAM = "shot_chart/team"
    LINEUP = "lineup"


class AggregationMethod(str, Enum):
    """Methods for aggregating stats across games/possessions"""
    SUM = "sum"                    # Total counting stats (PTS, REB, AST)
    MEAN = "mean"                  # Simple average
    WEIGHTED_MEAN = "weighted_mean" # Weighted by minutes/possessions
    RATE = "rate"                  # Per-game, per-36, per-100 possessions
    PERCENTAGE = "percentage"       # Shooting percentages (recalculated)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class GroupingMetadata:
    """Metadata describing a data grouping"""
    grouping_level: GroupingLevel
    granularity: GranularityLevel
    endpoint: str
    time_fields: List[str]
    required_params: List[str]
    optional_filters: List[str] = field(default_factory=list)
    special_columns: List[str] = field(default_factory=list)
    aggregation_methods: Dict[str, AggregationMethod] = field(default_factory=dict)

    @property
    def description(self) -> str:
        return f"{self.grouping_level.value} at {self.granularity.value} granularity via {self.endpoint}"


# Grouping catalog - defines all available grouping levels
GROUPING_CATALOG: Dict[GroupingLevel, GroupingMetadata] = {
    GroupingLevel.PLAYER_GAME: GroupingMetadata(
        grouping_level=GroupingLevel.PLAYER_GAME,
        granularity=GranularityLevel.DAY,
        endpoint="playergamelogs",
        time_fields=["GAME_DATE"],
        required_params=["SEASON_YEAR"],
        optional_filters=["PLAYER_ID", "TEAM_ID", "DATE_FROM", "DATE_TO"],
        aggregation_methods={
            "PTS": AggregationMethod.SUM,
            "REB": AggregationMethod.SUM,
            "AST": AggregationMethod.SUM,
            "FG_PCT": AggregationMethod.PERCENTAGE,
        }
    ),
    GroupingLevel.PLAYER_TEAM_GAME: GroupingMetadata(
        grouping_level=GroupingLevel.PLAYER_TEAM_GAME,
        granularity=GranularityLevel.DAY,
        endpoint="playergamelogs",
        time_fields=["GAME_DATE"],
        required_params=["SEASON_YEAR", "TEAM_ID"],
        optional_filters=["PLAYER_ID", "DATE_FROM", "DATE_TO"],
    ),
    GroupingLevel.TEAM_GAME: GroupingMetadata(
        grouping_level=GroupingLevel.TEAM_GAME,
        granularity=GranularityLevel.DAY,
        endpoint="teamgamelogs",
        time_fields=["GAME_DATE"],
        required_params=["SEASON_YEAR"],
        optional_filters=["TEAM_ID", "DATE_FROM", "DATE_TO"],
    ),
    GroupingLevel.PLAYER_SEASON: GroupingMetadata(
        grouping_level=GroupingLevel.PLAYER_SEASON,
        granularity=GranularityLevel.SEASON,
        endpoint="playergamelogs_aggregated",  # Virtual endpoint
        time_fields=["SEASON_YEAR"],
        required_params=["SEASON_YEAR", "PLAYER_ID"],
        optional_filters=[],
        aggregation_methods={
            "PTS": AggregationMethod.SUM,
            "GP": AggregationMethod.SUM,
            "MIN": AggregationMethod.MEAN,
            "FG_PCT": AggregationMethod.PERCENTAGE,
        }
    ),
    GroupingLevel.TEAM_SEASON: GroupingMetadata(
        grouping_level=GroupingLevel.TEAM_SEASON,
        granularity=GranularityLevel.SEASON,
        endpoint="teamgamelogs_aggregated",  # Virtual endpoint
        time_fields=["SEASON_YEAR"],
        required_params=["SEASON_YEAR", "TEAM_ID"],
        optional_filters=[],
    ),
    GroupingLevel.PLAY_BY_PLAY_TEAM: GroupingMetadata(
        grouping_level=GroupingLevel.PLAY_BY_PLAY_TEAM,
        granularity=GranularityLevel.SECOND,
        endpoint="playbyplayv3",
        time_fields=["PERIOD", "CLOCK"],
        required_params=["GAME_ID"],
        optional_filters=["START_PERIOD", "END_PERIOD"],
        special_columns=["CURRENT_LINEUP_HOME", "CURRENT_LINEUP_AWAY", "LINEUP_ID_HOME", "LINEUP_ID_AWAY"],
    ),
    GroupingLevel.SHOT_CHART_PLAYER: GroupingMetadata(
        grouping_level=GroupingLevel.SHOT_CHART_PLAYER,
        granularity=GranularityLevel.SPATIAL,
        endpoint="shotchartdetail",
        time_fields=["GAME_DATE"],
        required_params=["PLAYER_ID", "SEASON"],
        optional_filters=["TEAM_ID", "DATE_FROM", "DATE_TO", "GAME_ID"],
        special_columns=["LOC_X", "LOC_Y", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"],
    ),
    GroupingLevel.SHOT_CHART_TEAM: GroupingMetadata(
        grouping_level=GroupingLevel.SHOT_CHART_TEAM,
        granularity=GranularityLevel.SPATIAL,
        endpoint="shotchartdetail",
        time_fields=["GAME_DATE"],
        required_params=["TEAM_ID", "SEASON"],
        optional_filters=["DATE_FROM", "DATE_TO", "GAME_ID"],
        special_columns=["LOC_X", "LOC_Y", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"],
    ),
}


# ============================================================================
# ABSTRACT BASE CLASS
# ============================================================================

class DataGrouping(ABC):
    """
    Abstract base class for all data grouping interfaces.

    Each grouping level (player/game, team/season, etc.) implements this interface
    to provide standardized access to NBA data.
    """

    def __init__(self, metadata: GroupingMetadata):
        self.metadata = metadata

    @abstractmethod
    async def fetch(self, **filters) -> pd.DataFrame:
        """
        Fetch data for this grouping level with optional filters.

        Returns:
            DataFrame with standardized columns for this grouping level
        """
        pass

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate that all required parameters are present"""
        pass

    def get_required_params(self) -> List[str]:
        """Get list of required parameters for this grouping"""
        return self.metadata.required_params

    def get_optional_filters(self) -> List[str]:
        """Get list of optional filter parameters"""
        return self.metadata.optional_filters

    def get_granularity(self) -> GranularityLevel:
        """Get the time/spatial granularity of this grouping"""
        return self.metadata.granularity

    def get_grouping_level(self) -> GroupingLevel:
        """Get the aggregation level of this grouping"""
        return self.metadata.grouping_level


# ============================================================================
# CONCRETE IMPLEMENTATIONS
# ============================================================================

class PlayerGameGrouping(DataGrouping):
    """
    player/game grouping - individual game logs for players

    Granularity: Day (GAME_DATE)
    Source: NBA Stats API playergamelogs endpoint
    """

    def __init__(self):
        super().__init__(GROUPING_CATALOG[GroupingLevel.PLAYER_GAME])

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate required params: SEASON_YEAR"""
        return "SEASON_YEAR" in params or "season" in params

    async def fetch(self, **filters) -> pd.DataFrame:
        """
        Fetch player game logs with comprehensive filtering support

        Phase 2H: Now uses unified_fetch for automatic caching (239x speedup),
        filter pushdown (50-90% data reduction), and provenance tracking.

        Three-tier filtering architecture:
        - Tier 1: NBA API filters (reduces data transfer at source) - via unified_fetch filter pushdown
        - Tier 2: DuckDB statistical filters (100x faster than pandas) - via unified_fetch post-filtering
        - Tier 3: Parquet storage (35.7x smaller, 6.7x faster reads) - ready for future

        API Filters (Tier 1 - passed to NBA Stats API):
            season (str): Season in YYYY-YY format (e.g., "2023-24")
            player_id (int, optional): Specific player ID
            team_id (int, optional): Specific team ID
            date_from (str, optional): Start date in YYYY-MM-DD format
            date_to (str, optional): End date in YYYY-MM-DD format
            game_segment (str, optional): First Half, Second Half, Overtime
            location (str, optional): Home, Road
            outcome (str, optional): W (wins), L (losses)
            last_n_games (int, optional): Last N games (e.g., 10)
            league_id (str, optional): NBA league ID (default: "00")
            measure_type (str, optional): Base, Advanced, Misc, Scoring, Usage
            month (int, optional): Month number (1-12)
            opp_team_id (int, optional): Opponent team ID
            po_round (int, optional): Playoff round (0-4)
            per_mode (str, optional): Totals, PerGame, Per36, Per48, Per40
            period (int, optional): Quarter/period number (1-4)
            season_segment (str, optional): Pre All-Star, Post All-Star
            season_type (str, optional): Regular Season, Playoffs, All Star
            shot_clock_range (str, optional): 24-22, 22-18 Very Early, etc.
            vs_conference (str, optional): East, West
            vs_division (str, optional): Atlantic, Central, Southeast, etc.

        Statistical Filters (Tier 2 - post-fetch DuckDB filtering):
            Pass as tuples: (operator, value)
            Examples:
                MIN: (">=", 10)  # Minutes >= 10
                PTS: (">", 20)   # Points > 20
                FG_PCT: (">=", 0.5)  # FG% >= 50%

        Returns:
            DataFrame with player game logs + metadata columns

        Performance Benefits (Phase 2H):
            ✅ 239x cache speedup for repeated queries
            ✅ 50-90% data reduction with filter pushdown
            ✅ Provenance tracking for debugging
            ✅ Optimized DuckDB filtering (Phase 2G fixes)
            ✅ Empty table optimization (10-50ms saved)
        """
        from nba_mcp.api.data_filtering import split_filters
        from nba_mcp.data.unified_fetch import unified_fetch

        # Separate API parameters from statistical filters
        api_filters, stat_filters = split_filters(filters)

        # Extract season (required parameter)
        season = api_filters.get("season") or api_filters.get("SEASON_YEAR")
        if not season:
            raise ValueError("season parameter is required for player/game grouping")

        # Build unified_fetch parameters
        # unified_fetch uses the player_game_log endpoint which requires player_name
        # NOTE: The player_game_log endpoint cannot query "all players" - it requires a player
        # Therefore, queries without player_id will use the direct API path
        params = {"season": season}

        # Handle player_id - unified_fetch endpoint prefers player_name but we have player_id
        # For now, if player_id is specified, we'll use extended params (direct API call)
        # This ensures we can query specific players by ID
        # ALSO: If no player_id at all, we must use direct API (can't query all players via unified_fetch)
        has_player_filter = "player_id" in api_filters

        # Add optional parameters that unified_fetch endpoint supports
        if "date_from" in api_filters:
            params["date_from"] = api_filters["date_from"]
        if "date_to" in api_filters:
            params["date_to"] = api_filters["date_to"]
        if "last_n_games" in api_filters:
            params["last_n_games"] = api_filters["last_n_games"]
        if "season_type" in api_filters:
            params["season_type"] = api_filters["season_type"]

        # For parameters not supported by unified_fetch endpoint or when player_id is used,
        # we'll use direct API call with unified_fetch's filtering benefits
        extended_params = {}

        # Phase 2H-B: Entity Resolution - Convert player_id → player_name for caching
        if has_player_filter:
            player_id = api_filters["player_id"]

            # Try to resolve player_id → player_name to enable unified_fetch caching
            from nba_mcp.api.tools.nba_api_utils import get_player_name
            player_name = get_player_name(player_id)

            if player_name:
                # Success! Add to unified_fetch params (enables caching)
                params["player_name"] = player_name
                logger.info(
                    f"[Phase 2H-B] Resolved player_id {player_id} → '{player_name}' "
                    f"(unified_fetch path - caching enabled)"
                )
            else:
                # Fallback: Could not resolve player_id, use direct API
                extended_params["player_id"] = player_id
                logger.warning(
                    f"[Phase 2H-B] Could not resolve player_id {player_id}, "
                    f"using direct API (no caching)"
                )
        if "team_id" in api_filters:
            extended_params["team_id"] = api_filters["team_id"]

        for key in ['game_segment', 'location', 'outcome', 'league_id', 'measure_type',
                    'month', 'opp_team_id', 'po_round', 'per_mode', 'period',
                    'season_segment', 'shot_clock_range', 'vs_conference', 'vs_division']:
            if key in api_filters:
                extended_params[key] = api_filters[key]

        # Convert stat_filters from tuple format to list format for unified_fetch
        # unified_fetch expects {"PTS": [">=", 30]} not {"PTS": (">=", 30)}
        unified_filters = {}
        for column, filter_spec in stat_filters.items():
            if isinstance(filter_spec, tuple):
                unified_filters[column] = list(filter_spec)
            else:
                unified_filters[column] = filter_spec

        logger.info(
            f"[unified_fetch] Fetching with {len(params)} params, "
            f"{len(extended_params)} extended params, {len(unified_filters)} stat filters"
        )

        # Phase 2H-C: Three query paths for optimal caching:
        # 1. No player + no extended params → league_player_games (ALL players, caching enabled)
        # 2. Has player + no extended params → player_game_log (specific player, Phase 2H-B caching)
        # 3. Extended params exist → direct API (complex filters, no caching)
        use_league_endpoint = not has_player_filter and not extended_params
        use_direct_api = bool(extended_params)

        # Track which path was successful
        df = None

        if use_league_endpoint:
            # Phase 2H-C: Use league_player_games for all-player queries
            # This enables caching for league-wide data
            logger.info(
                f"[Phase 2H-C] Using league_player_games endpoint for all-player query "
                f"(caching enabled)"
            )

            try:
                result = await unified_fetch(
                    endpoint="league_player_games",
                    params=params,
                    filters=unified_filters
                )

                # Convert PyArrow Table to pandas DataFrame
                df = result.data.to_pandas()

                logger.info(
                    f"[unified_fetch] Retrieved {len(df)} rows "
                    f"(cache: {'HIT' if result.from_cache else 'MISS'}, "
                    f"endpoint: league_player_games)"
                )

            except Exception as e:
                # Fallback to direct API if league endpoint fails
                logger.warning(
                    f"[Phase 2H-C] league_player_games failed ({e}), falling back to direct API"
                )
                use_direct_api = True
                df = None

        if use_direct_api and df is None:
            # Fallback to direct API call for extended parameters (temporary)
            # Still benefits from DuckDB filtering via unified_fetch
            from nba_api.stats.endpoints import PlayerGameLogs

            # Map parameters to NBA API format
            param_mapping = {
                'season': 'season_nullable',
                'player_id': 'player_id_nullable',
                'team': 'team_id_nullable',
                'date_from': 'date_from_nullable',
                'date_to': 'date_to_nullable',
                'game_segment': 'game_segment_nullable',
                'location': 'location_nullable',
                'outcome': 'outcome_nullable',
                'last_n_games': 'last_n_games_nullable',
                'league_id': 'league_id_nullable',
                'measure_type': 'measure_type_detailed_defense_nullable',
                'month': 'month_nullable',
                'opp_team_id': 'opp_team_id_nullable',
                'po_round': 'po_round_nullable',
                'per_mode': 'per_mode_detailed_nullable',
                'period': 'period_nullable',
                'season_segment': 'season_segment_nullable',
                'season_type': 'season_type_nullable',
                'shot_clock_range': 'shot_clock_range_nullable',
                'vs_conference': 'vs_conference_nullable',
                'vs_division': 'vs_division_nullable',
            }

            api_params = {"season_nullable": season}
            all_params = {**params, **extended_params}

            for user_param, api_param_name in param_mapping.items():
                if user_param in all_params and user_param != 'season':
                    value = all_params[user_param]
                    # Handle team parameter (unified uses "team", NBA API uses team_id)
                    if user_param == 'team' and not isinstance(value, int):
                        # If it's a team name/abbr, we need to resolve it
                        continue  # Skip for now, TODO: add team resolution
                    api_params[api_param_name] = value

            logger.warning(
                f"Using direct API call for extended parameters: {list(extended_params.keys())}. "
                f"Caching not available for this query."
            )
            result = PlayerGameLogs(**api_params)
            df = result.get_data_frames()[0]

            # Apply stat filters via unified_fetch's apply_filters if any
            if unified_filters:
                import pyarrow as pa
                from nba_mcp.data.unified_fetch import apply_filters

                # Convert to PyArrow for filtering
                table = pa.Table.from_pandas(df)
                filtered_table = apply_filters(table, unified_filters)
                df = filtered_table.to_pandas()

        elif df is None:
            # Use unified_fetch for standard parameters (gets full benefits)
            # This path is for specific player queries (Phase 2H-B)
            result = await unified_fetch(
                endpoint="player_game_log",
                params=params,
                filters=unified_filters if unified_filters else None
            )

            # Convert PyArrow Table to pandas DataFrame
            df = result.data.to_pandas()

            logger.info(
                f"[unified_fetch] Retrieved {len(df)} rows "
                f"(cache: {'HIT' if result.from_cache else 'MISS'}, "
                f"endpoint: {result.provenance.source_endpoints[0] if result.provenance.source_endpoints else 'unknown'})"
            )

        # Add metadata columns
        df["_grouping_level"] = self.metadata.grouping_level.value
        df["_granularity"] = self.metadata.granularity.value

        return df


class TeamGameGrouping(DataGrouping):
    """
    team/game grouping - team game logs

    Granularity: Day (GAME_DATE)
    Source: NBA Stats API teamgamelogs endpoint
    """

    def __init__(self):
        super().__init__(GROUPING_CATALOG[GroupingLevel.TEAM_GAME])

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate required params: SEASON_YEAR"""
        return "SEASON_YEAR" in params or "season" in params

    async def fetch(self, **filters) -> pd.DataFrame:
        """
        Fetch team game logs with comprehensive filtering support

        Phase 2H: Now uses unified_fetch for automatic caching (239x speedup),
        filter pushdown (50-90% data reduction), and provenance tracking.

        Three-tier filtering architecture:
        - Tier 1: NBA API filters (reduces data transfer at source) - via unified_fetch filter pushdown
        - Tier 2: DuckDB statistical filters (100x faster than pandas) - via unified_fetch post-filtering
        - Tier 3: Parquet storage (35.7x smaller, 6.7x faster reads) - ready for future

        API Filters (Tier 1 - passed to NBA Stats API):
            season (str): Season in YYYY-YY format (e.g., "2023-24")
            team_id (int, optional): Specific team ID
            date_from (str, optional): Start date in YYYY-MM-DD format
            date_to (str, optional): End date in YYYY-MM-DD format
            game_segment (str, optional): First Half, Second Half, Overtime
            location (str, optional): Home, Road
            outcome (str, optional): W (wins), L (losses)
            last_n_games (int, optional): Last N games (e.g., 10)
            league_id (str, optional): NBA league ID (default: "00")
            measure_type (str, optional): Base, Advanced, Misc, Scoring, Usage
            month (int, optional): Month number (1-12)
            opp_team_id (int, optional): Opponent team ID
            po_round (int, optional): Playoff round (0-4)
            per_mode (str, optional): Totals, PerGame, Per36, Per48, Per40
            period (int, optional): Quarter/period number (1-4)
            season_segment (str, optional): Pre All-Star, Post All-Star
            season_type (str, optional): Regular Season, Playoffs, All Star
            shot_clock_range (str, optional): 24-22, 22-18 Very Early, etc.
            vs_conference (str, optional): East, West
            vs_division (str, optional): Atlantic, Central, Southeast, etc.

        Statistical Filters (Tier 2 - post-fetch DuckDB filtering):
            Pass as tuples: (operator, value)
            Examples:
                PTS: (">=", 100)  # Team scored >= 100 points
                W_PCT: (">", 0.5) # Win percentage > 50%
                PLUS_MINUS: (">", 0)  # Positive point differential

        Returns:
            DataFrame with team game logs + metadata columns

        Performance Benefits (Phase 2H):
            ✅ 239x cache speedup for repeated queries
            ✅ 50-90% data reduction with filter pushdown
            ✅ Provenance tracking for debugging
            ✅ Optimized DuckDB filtering (Phase 2G fixes)
            ✅ Empty table optimization (10-50ms saved)
        """
        from nba_mcp.api.data_filtering import split_filters
        from nba_mcp.data.unified_fetch import unified_fetch

        # Separate API parameters from statistical filters
        api_filters, stat_filters = split_filters(filters)

        # Extract season (required parameter)
        season = api_filters.get("season") or api_filters.get("SEASON_YEAR")
        if not season:
            raise ValueError("season parameter is required for team/game grouping")

        # Build unified_fetch parameters
        # unified_fetch uses the team_game_log endpoint which handles basic parameters
        params = {"season": season}

        # Handle team_id - check if unified_fetch endpoint supports it or use extended params
        has_team_filter = "team_id" in api_filters

        # Add optional parameters that unified_fetch endpoint supports
        if "date_from" in api_filters:
            params["date_from"] = api_filters["date_from"]
        if "date_to" in api_filters:
            params["date_to"] = api_filters["date_to"]
        if "season_type" in api_filters:
            params["season_type"] = api_filters["season_type"]

        # For parameters not supported by unified_fetch endpoint or when team_id is used,
        # we'll use direct API call with unified_fetch's filtering benefits
        extended_params = {}

        # Phase 2H-B: Entity Resolution - Convert team_id → team name for caching
        if has_team_filter:
            team_id = api_filters["team_id"]

            # Try to resolve team_id → team name to enable unified_fetch caching
            from nba_mcp.api.tools.nba_api_utils import get_team_name
            team_name = get_team_name(team_id)

            if team_name:
                # Success! Add to unified_fetch params (enables caching)
                # team_game_log endpoint expects "team" parameter
                params["team"] = team_name
                logger.info(
                    f"[Phase 2H-B] Resolved team_id {team_id} → '{team_name}' "
                    f"(unified_fetch path - caching enabled)"
                )
            else:
                # Fallback: Could not resolve team_id, use direct API
                extended_params["team_id"] = team_id
                logger.warning(
                    f"[Phase 2H-B] Could not resolve team_id {team_id}, "
                    f"using direct API (no caching)"
                )

        for key in ['game_segment', 'location', 'outcome', 'last_n_games', 'league_id',
                    'measure_type', 'month', 'opp_team_id', 'po_round', 'per_mode',
                    'period', 'season_segment', 'shot_clock_range', 'vs_conference', 'vs_division']:
            if key in api_filters:
                extended_params[key] = api_filters[key]

        # Convert stat_filters from tuple format to list format for unified_fetch
        # unified_fetch expects {"PTS": [">=", 100]} not {"PTS": (">=", 100)}
        unified_filters = {}
        for column, filter_spec in stat_filters.items():
            if isinstance(filter_spec, tuple):
                unified_filters[column] = list(filter_spec)
            else:
                unified_filters[column] = filter_spec

        logger.info(
            f"[unified_fetch] Fetching with {len(params)} params, "
            f"{len(extended_params)} extended params, {len(unified_filters)} stat filters"
        )

        # Phase 2H-C: Three query paths for optimal caching:
        # 1. No team + no extended params → league_team_games (ALL teams, caching enabled)
        # 2. Has team + no extended params → team_game_log (specific team, Phase 2H-B caching)
        # 3. Extended params exist → direct API (complex filters, no caching)
        use_league_endpoint = not has_team_filter and not extended_params
        use_direct_api = bool(extended_params)

        # Track which path was successful
        df = None

        if use_league_endpoint:
            # Phase 2H-C: Use league_team_games for all-team queries
            # This enables caching for league-wide data
            logger.info(
                f"[Phase 2H-C] Using league_team_games endpoint for all-team query "
                f"(caching enabled)"
            )

            try:
                result = await unified_fetch(
                    endpoint="league_team_games",
                    params=params,
                    filters=unified_filters
                )

                # Convert PyArrow Table to pandas DataFrame
                df = result.data.to_pandas()

                logger.info(
                    f"[unified_fetch] Retrieved {len(df)} rows "
                    f"(cache: {'HIT' if result.from_cache else 'MISS'}, "
                    f"endpoint: league_team_games)"
                )

            except Exception as e:
                # Fallback to direct API if league endpoint fails
                logger.warning(
                    f"[Phase 2H-C] league_team_games failed ({e}), falling back to direct API"
                )
                use_direct_api = True
                df = None

        if use_direct_api and df is None:
            # Fallback to direct API call for extended parameters (temporary)
            # Still benefits from DuckDB filtering via unified_fetch
            from nba_api.stats.endpoints import TeamGameLogs

            # Map parameters to NBA API format
            param_mapping = {
                'season': 'season_nullable',
                'team_id': 'team_id_nullable',
                'date_from': 'date_from_nullable',
                'date_to': 'date_to_nullable',
                'game_segment': 'game_segment_nullable',
                'location': 'location_nullable',
                'outcome': 'outcome_nullable',
                'last_n_games': 'last_n_games_nullable',
                'league_id': 'league_id_nullable',
                'measure_type': 'measure_type_detailed_defense_nullable',
                'month': 'month_nullable',
                'opp_team_id': 'opp_team_id_nullable',
                'po_round': 'po_round_nullable',
                'per_mode': 'per_mode_detailed_nullable',
                'period': 'period_nullable',
                'season_segment': 'season_segment_nullable',
                'season_type': 'season_type_nullable',
                'shot_clock_range': 'shot_clock_range_nullable',
                'vs_conference': 'vs_conference_nullable',
                'vs_division': 'vs_division_nullable',
            }

            api_params = {"season_nullable": season}
            all_params = {**params, **extended_params}

            for user_param, api_param_name in param_mapping.items():
                if user_param in all_params and user_param != 'season':
                    api_params[api_param_name] = all_params[user_param]

            logger.warning(
                f"Using direct API call for extended parameters: {list(extended_params.keys())}. "
                f"Caching not available for this query."
            )
            result = TeamGameLogs(**api_params)
            df = result.get_data_frames()[0]

            # Apply stat filters via unified_fetch's apply_filters if any
            if unified_filters:
                import pyarrow as pa
                from nba_mcp.data.unified_fetch import apply_filters

                # Convert to PyArrow for filtering
                table = pa.Table.from_pandas(df)
                filtered_table = apply_filters(table, unified_filters)
                df = filtered_table.to_pandas()

        elif df is None:
            # Use unified_fetch for standard parameters (gets full benefits)
            # This path is for specific team queries (Phase 2H-B)
            result = await unified_fetch(
                endpoint="team_game_log",
                params=params,
                filters=unified_filters if unified_filters else None
            )

            # Convert PyArrow Table to pandas DataFrame
            df = result.data.to_pandas()

            logger.info(
                f"[unified_fetch] Retrieved {len(df)} rows "
                f"(cache: {'HIT' if result.from_cache else 'MISS'}, "
                f"endpoint: {result.provenance.source_endpoints[0] if result.provenance.source_endpoints else 'unknown'})"
            )

        # Add metadata columns
        df["_grouping_level"] = self.metadata.grouping_level.value
        df["_granularity"] = self.metadata.granularity.value

        return df


class PlayerTeamGameGrouping(DataGrouping):
    """
    player/team/game grouping - player game logs filtered by team

    Granularity: Day (GAME_DATE)
    Source: NBA Stats API playergamelogs endpoint with team filter
    """

    def __init__(self):
        super().__init__(GROUPING_CATALOG[GroupingLevel.PLAYER_TEAM_GAME])

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate required params: SEASON_YEAR, TEAM_ID"""
        has_season = "SEASON_YEAR" in params or "season" in params
        has_team = "TEAM_ID" in params or "team_id" in params
        return has_season and has_team

    async def fetch(self, **filters) -> pd.DataFrame:
        """
        Fetch player game logs for a specific team with comprehensive filtering

        This grouping inherits all filtering capabilities from PlayerGameGrouping
        (21 API parameters + statistical filters). See PlayerGameGrouping.fetch()
        for complete documentation.

        Required Filters:
            season (str): Season in YYYY-YY format (e.g., "2023-24")
            team_id (int): Team ID to filter (required for this grouping level)

        Optional Filters:
            All filters from PlayerGameGrouping are supported, including:
            - API filters: player_id, date_from, date_to, location, outcome, etc.
            - Statistical filters: MIN, PTS, AST, etc. (pass as tuples)

        Returns:
            DataFrame with player game logs filtered by team + metadata columns
        """
        # Reuse PlayerGameGrouping but enforce team_id
        # All filters (API + statistical) are passed through automatically
        player_game = PlayerGameGrouping()
        df = await player_game.fetch(**filters)

        # Update metadata to reflect player/team/game grouping
        df["_grouping_level"] = self.metadata.grouping_level.value

        return df


# ============================================================================
# GROUPING FACTORY
# ============================================================================

class GroupingFactory:
    """Factory for creating data grouping instances"""

    _registry: Dict[GroupingLevel, type[DataGrouping]] = {
        GroupingLevel.PLAYER_GAME: PlayerGameGrouping,
        GroupingLevel.TEAM_GAME: TeamGameGrouping,
        GroupingLevel.PLAYER_TEAM_GAME: PlayerTeamGameGrouping,
        # More groupings will be registered as implemented
    }

    @classmethod
    def create(cls, grouping_level: Union[GroupingLevel, str]) -> DataGrouping:
        """
        Create a data grouping instance

        Args:
            grouping_level: GroupingLevel enum or string (e.g., "player/game")

        Returns:
            DataGrouping instance for the specified level

        Raises:
            ValueError: If grouping level is not supported
        """
        if isinstance(grouping_level, str):
            try:
                grouping_level = GroupingLevel(grouping_level)
            except ValueError:
                raise ValueError(f"Unknown grouping level: {grouping_level}")

        grouping_class = cls._registry.get(grouping_level)
        if not grouping_class:
            raise ValueError(f"Grouping level {grouping_level.value} not yet implemented")

        return grouping_class()

    @classmethod
    def get_available_groupings(cls) -> List[GroupingLevel]:
        """Get list of all available grouping levels"""
        return list(cls._registry.keys())

    @classmethod
    def register(cls, grouping_level: GroupingLevel, grouping_class: type[DataGrouping]):
        """Register a new grouping implementation"""
        cls._registry[grouping_level] = grouping_class


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def fetch_grouping(
    grouping_level: Union[GroupingLevel, str],
    enrich: bool = True,
    enrichments: Optional[List[str]] = None,
    exclude_enrichments: Optional[List[str]] = None,
    **filters
) -> pd.DataFrame:
    """
    Convenience function to fetch data at a specific grouping level with optional enrichment.

    Args:
        grouping_level: Grouping level (e.g., "player/game", GroupingLevel.PLAYER_GAME)
        enrich: Whether to apply default enrichments (default: True)
        enrichments: Specific enrichments to apply (overrides defaults)
        exclude_enrichments: Enrichments to exclude from defaults
        **filters: Filters for the grouping (season, player_id, team_id, etc.)

    Returns:
        DataFrame with data at the specified grouping level (enriched by default)

    Example:
        # Fetch with default enrichments (recommended)
        df = await fetch_grouping("player/game", season="2023-24", player_id=2544)

        # Fetch without enrichment
        df = await fetch_grouping("player/game", season="2023-24", enrich=False)

        # Fetch with specific enrichments
        df = await fetch_grouping(
            "player/game",
            season="2023-24",
            enrichments=["advanced_metrics", "shot_chart"]
        )

        # Fetch with defaults except shot charts
        df = await fetch_grouping(
            "player/game",
            season="2023-24",
            exclude_enrichments=["shot_chart"]
        )
    """
    grouping = GroupingFactory.create(grouping_level)

    if not grouping.validate_params(filters):
        required = grouping.get_required_params()
        raise ValueError(f"Missing required parameters for {grouping_level}: {required}")

    # Fetch base data
    df = await grouping.fetch(**filters)

    # Apply enrichment if requested
    if enrich and not df.empty:
        from nba_mcp.data.enrichment_strategy import (
            enrich_dataset,
            EnrichmentType,
        )

        # Convert string enrichment names to EnrichmentType
        enrichment_types = None
        if enrichments:
            enrichment_types = [EnrichmentType(e) for e in enrichments]

        exclude_types = None
        if exclude_enrichments:
            exclude_types = [EnrichmentType(e) for e in exclude_enrichments]

        # Enrich the dataset
        df = await enrich_dataset(
            df,
            grouping_level=GroupingLevel(grouping_level) if isinstance(grouping_level, str) else grouping_level,
            enrichments=enrichment_types,
            use_defaults=(enrichments is None),  # Use defaults if no specific enrichments requested
            exclude=exclude_types,
        )

    return df


async def fetch_grouping_multi_season(
    grouping_level: Union[GroupingLevel, str],
    seasons: List[str],
    enrich: bool = True,
    enrichments: Optional[List[str]] = None,
    exclude_enrichments: Optional[List[str]] = None,
    **filters
) -> pd.DataFrame:
    """
    Fetch data for multiple seasons concurrently and combine results with optional enrichment.

    Uses asyncio.gather() for parallel API calls - approximately N times faster
    than sequential fetching for N seasons.

    Args:
        grouping_level: Grouping level (e.g., "player/game")
        seasons: List of season strings (e.g., ["2021-22", "2022-23", "2023-24"])
        enrich: Whether to apply default enrichments (default: True)
        enrichments: Specific enrichments to apply (overrides defaults)
        exclude_enrichments: Enrichments to exclude from defaults
        **filters: Additional filters (player_id, team_id, etc.) - do NOT include season

    Returns:
        Combined DataFrame with all seasons (enriched by default)

    Example:
        # Fetch LeBron's games for last 3 seasons with enrichment (concurrent)
        df = await fetch_grouping_multi_season(
            "player/game",
            seasons=["2021-22", "2022-23", "2023-24"],
            player_id=2544
        )

        # Fetch without enrichment
        df = await fetch_grouping_multi_season(
            "player/game",
            seasons=["2021-22", "2022-23", "2023-24"],
            player_id=2544,
            enrich=False
        )
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    # Remove 'season' from filters if accidentally passed
    if 'season' in filters:
        logger.warning("Removing 'season' from filters - use seasons parameter instead")
        del filters['season']

    # Create tasks for concurrent fetching
    async def fetch_season(season_str: str) -> pd.DataFrame:
        """Fetch data for a single season"""
        try:
            season_filters = {
                **filters,
                "season": season_str,
                "enrich": enrich,
                "enrichments": enrichments,
                "exclude_enrichments": exclude_enrichments,
            }
            df = await fetch_grouping(grouping_level, **season_filters)
            logger.info(f"Fetched {season_str}: {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Failed to fetch {season_str}: {e}")
            return pd.DataFrame()  # Return empty DataFrame on error

    # Execute all season fetches concurrently
    logger.info(f"Fetching {len(seasons)} seasons concurrently: {seasons}")
    dfs = await asyncio.gather(*[fetch_season(s) for s in seasons])

    # Filter out empty DataFrames
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        logger.warning(f"No data found for any season: {seasons}")
        return pd.DataFrame()

    # Concatenate all results
    combined = pd.concat(dfs, ignore_index=True)
    logger.info(f"Combined {len(dfs)} seasons: {len(combined)} total rows")

    return combined


def get_grouping_info(grouping_level: Union[GroupingLevel, str]) -> GroupingMetadata:
    """
    Get metadata information about a grouping level

    Args:
        grouping_level: Grouping level to query

    Returns:
        GroupingMetadata with description, granularity, required params, etc.

    Example:
        info = get_grouping_info("player/game")
        print(info.description)
        print(info.required_params)
    """
    if isinstance(grouping_level, str):
        grouping_level = GroupingLevel(grouping_level)

    return GROUPING_CATALOG[grouping_level]


def list_available_groupings() -> List[str]:
    """
    List all available grouping levels

    Returns:
        List of grouping level strings (e.g., ["player/game", "team/game", ...])
    """
    return [level.value for level in GroupingFactory.get_available_groupings()]


# ============================================================================
# MERGE INTEGRATION FUNCTIONS
# ============================================================================

def merge_with_advanced_metrics(
    game_data: Union[pd.DataFrame, Any],
    grouping_level: Union[GroupingLevel, str],
    metrics: Optional[List[str]] = None,
    how: Literal["left", "inner"] = "left",
    validation_level: str = "warn",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Merge advanced metrics onto game-level or season-level data.

    This function computes advanced metrics (Game Score, True Shooting %, etc.)
    from the base data and merges them back at the appropriate granularity.

    Args:
        game_data: Base game data (must include PTS, FGA, FTA, etc.)
        grouping_level: Target grouping level (e.g., "player/game", "player/season")
        metrics: Specific metrics to compute (default: all available)
        how: Join type - "left" (preserve all base rows) or "inner" (only matched)
        validation_level: "strict", "warn", or "minimal"

    Returns:
        Tuple of (data_with_metrics, merge_statistics_dict)

    Example:
        # Add advanced metrics to player game logs
        game_logs = await fetch_grouping("player/game", season="2023-24")
        merged_df, stats = merge_with_advanced_metrics(
            game_logs,
            grouping_level="player/game"
        )
        print(f"Added metrics with {stats['match_rate_pct']:.1f}% match rate")
    """
    from nba_mcp.data.merge_manager import MergeManager, MergeValidationLevel

    # Map string to validation level
    validation_map = {
        "strict": MergeValidationLevel.STRICT,
        "warn": MergeValidationLevel.WARN,
        "minimal": MergeValidationLevel.MINIMAL,
    }
    validation_enum = validation_map.get(validation_level.lower(), MergeValidationLevel.WARN)

    manager = MergeManager(validation_level=validation_enum)
    result_data, merge_stats = manager.merge_advanced_metrics(
        game_data=game_data,
        grouping_level=grouping_level,
        metrics=metrics,
        how=how,
    )

    return result_data, merge_stats.to_dict()


def merge_with_shot_chart_data(
    game_data: Union[pd.DataFrame, Any],
    shot_chart_data: Union[pd.DataFrame, Any],
    grouping_level: Union[GroupingLevel, str],
    aggregation: Literal["count", "avg", "zone_summary"] = "zone_summary",
    how: Literal["left", "inner"] = "left",
    validation_level: str = "warn",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Merge shot chart data onto game-level data with spatial aggregation.

    This function aggregates shot chart data (with LOC_X, LOC_Y coordinates)
    and merges it onto game-level data at the appropriate granularity.

    Args:
        game_data: Base game data
        shot_chart_data: Raw shot chart data with LOC_X, LOC_Y columns
        grouping_level: Target grouping level (must be game-level)
        aggregation: How to aggregate shots:
            - "count": Total shot count per game
            - "avg": Average shot statistics (made, %, distance)
            - "zone_summary": Breakdown by zone (paint, mid-range, 3PT)
        how: Join type
        validation_level: "strict", "warn", or "minimal"

    Returns:
        Tuple of (data_with_shots, merge_statistics_dict)

    Example:
        # Fetch game logs and shot chart data
        game_logs = await fetch_grouping("player/game", season="2023-24", player_id=2544)
        shot_data = get_shot_chart("LeBron James", season="2023-24")

        # Merge with zone summary
        merged_df, stats = merge_with_shot_chart_data(
            game_logs,
            shot_data,
            grouping_level="player/game",
            aggregation="zone_summary"
        )
        print(f"Added shot zones: {merged_df['PAINT_PCT'].mean():.1%} from paint")
    """
    from nba_mcp.data.merge_manager import MergeManager, MergeValidationLevel

    validation_map = {
        "strict": MergeValidationLevel.STRICT,
        "warn": MergeValidationLevel.WARN,
        "minimal": MergeValidationLevel.MINIMAL,
    }
    validation_enum = validation_map.get(validation_level.lower(), MergeValidationLevel.WARN)

    manager = MergeManager(validation_level=validation_enum)
    result_data, merge_stats = manager.merge_shot_chart_data(
        game_data=game_data,
        shot_chart_data=shot_chart_data,
        grouping_level=grouping_level,
        aggregation=aggregation,
        how=how,
    )

    return result_data, merge_stats.to_dict()


def merge_datasets_by_grouping(
    base_data: Union[pd.DataFrame, Any],
    merge_data: Union[pd.DataFrame, Any],
    grouping_level: Union[GroupingLevel, str],
    how: Literal["inner", "left", "right", "outer"] = "left",
    identifier_columns: Optional[List[str]] = None,
    validation_level: str = "warn",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Generic merge of two datasets at a specific grouping level with validation.

    This function provides a flexible way to merge any two datasets at the
    correct granularity, with automatic identifier column selection and
    comprehensive validation.

    Args:
        base_data: Base dataset (left side of join)
        merge_data: Dataset to merge (right side of join)
        grouping_level: Grouping level (e.g., "player/game", "team/season")
        how: Join type (inner, left, right, outer)
        identifier_columns: Override default identifier columns (optional)
        validation_level: "strict", "warn", or "minimal"

    Returns:
        Tuple of (merged_data, merge_statistics_dict)

    Example:
        # Merge team game logs with team advanced stats
        team_games = await fetch_grouping("team/game", season="2023-24")
        team_advanced = get_team_advanced_stats("Lakers", season="2023-24")

        merged_df, stats = merge_datasets_by_grouping(
            team_games,
            team_advanced,
            grouping_level="team/game",
            how="left"
        )
        print(f"Merged {stats['result_rows']} rows with {stats['result_columns']} columns")
    """
    from nba_mcp.data.merge_manager import MergeManager, MergeValidationLevel

    validation_map = {
        "strict": MergeValidationLevel.STRICT,
        "warn": MergeValidationLevel.WARN,
        "minimal": MergeValidationLevel.MINIMAL,
    }
    validation_enum = validation_map.get(validation_level.lower(), MergeValidationLevel.WARN)

    manager = MergeManager(validation_level=validation_enum)
    result_data, merge_stats = manager.merge(
        base_data=base_data,
        merge_data=merge_data,
        grouping_level=grouping_level,
        how=how,
        identifier_columns=identifier_columns,
        validate=True,
    )

    return result_data, merge_stats.to_dict()


def get_merge_identifier_columns(grouping_level: Union[GroupingLevel, str]) -> Dict[str, List[str]]:
    """
    Get the identifier columns used for merging at a specific grouping level.

    Args:
        grouping_level: Grouping level to query

    Returns:
        Dictionary with 'required' and 'optional' identifier columns

    Example:
        identifiers = get_merge_identifier_columns("player/game")
        print(f"Required: {identifiers['required']}")
        print(f"Optional: {identifiers['optional']}")
    """
    from nba_mcp.data.merge_manager import get_merge_config

    config = get_merge_config(grouping_level)
    return {
        "required": config.identifier_columns,
        "optional": config.optional_identifier_columns,
        "special": config.special_columns,
        "granularity": config.granularity.value,
    }


def list_all_merge_configs() -> Dict[str, Dict[str, Any]]:
    """
    List all available merge configurations for all grouping levels.

    Returns:
        Dictionary mapping grouping levels to their merge configurations

    Example:
        configs = list_all_merge_configs()
        for level, config in configs.items():
            print(f"{level}:")
            print(f"  Required IDs: {config['identifier_columns']}")
            print(f"  Granularity: {config['granularity']}")
    """
    from nba_mcp.data.merge_manager import list_merge_configs

    return list_merge_configs()
