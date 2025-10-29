"""
Season Aggregation Layer for NBA MCP

Aggregates game-level data into season-level statistics with proper handling of:
- Counting stats (sum): PTS, REB, AST, etc.
- Rate stats (recalculated): FG%, 3P%, FT%, etc.
- Averages (mean): Per-game averages
- Weighted averages: Per-minute, per-possession stats

Supports multiple aggregation methods and handles edge cases like
missing data, zero denominators, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from nba_mcp.api.data_groupings import (
    AggregationMethod,
    GroupingFactory,
    GroupingLevel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# AGGREGATION CONFIGURATION
# ============================================================================

# Define how each stat should be aggregated
STAT_AGGREGATION_MAP: Dict[str, AggregationMethod] = {
    # Counting stats (sum)
    "GP": AggregationMethod.SUM,
    "W": AggregationMethod.SUM,
    "L": AggregationMethod.SUM,
    "MIN": AggregationMethod.SUM,
    "PTS": AggregationMethod.SUM,
    "FGM": AggregationMethod.SUM,
    "FGA": AggregationMethod.SUM,
    "FG3M": AggregationMethod.SUM,
    "FG3A": AggregationMethod.SUM,
    "FTM": AggregationMethod.SUM,
    "FTA": AggregationMethod.SUM,
    "OREB": AggregationMethod.SUM,
    "DREB": AggregationMethod.SUM,
    "REB": AggregationMethod.SUM,
    "AST": AggregationMethod.SUM,
    "STL": AggregationMethod.SUM,
    "BLK": AggregationMethod.SUM,
    "TOV": AggregationMethod.SUM,
    "PF": AggregationMethod.SUM,
    "PLUS_MINUS": AggregationMethod.SUM,
    "DD2": AggregationMethod.SUM,  # Double-doubles
    "TD3": AggregationMethod.SUM,  # Triple-doubles

    # Percentage stats (recalculated from totals)
    "FG_PCT": AggregationMethod.PERCENTAGE,
    "FG3_PCT": AggregationMethod.PERCENTAGE,
    "FT_PCT": AggregationMethod.PERCENTAGE,

    # Rate stats that should be averaged
    "NBA_FANTASY_PTS": AggregationMethod.MEAN,

    # Identifiers/metadata (keep first)
    "PLAYER_ID": AggregationMethod.SUM,  # Special: keep first
    "PLAYER_NAME": AggregationMethod.SUM,  # Special: keep first
    "TEAM_ID": AggregationMethod.SUM,  # Special: can change mid-season
    "TEAM_ABBREVIATION": AggregationMethod.SUM,  # Special: can change mid-season
    "SEASON_YEAR": AggregationMethod.SUM,  # Special: keep first
}


# Stats that need special handling for recalculation
PERCENTAGE_STATS: Dict[str, tuple[str, str]] = {
    "FG_PCT": ("FGM", "FGA"),
    "FG3_PCT": ("FG3M", "FG3A"),
    "FT_PCT": ("FTM", "FTA"),
}


# ============================================================================
# AGGREGATION FUNCTIONS
# ============================================================================

def _aggregate_counting_stat(series: pd.Series) -> float:
    """Sum a counting stat, handling NaN values"""
    return float(series.sum()) if not series.isna().all() else 0.0


def _aggregate_percentage_stat(
    made_series: pd.Series,
    attempted_series: pd.Series
) -> float:
    """
    Recalculate percentage from totals

    Returns:
        Percentage (0.0-1.0) or 0.0 if no attempts
    """
    total_made = made_series.sum()
    total_attempted = attempted_series.sum()

    if total_attempted == 0:
        return 0.0

    return float(total_made / total_attempted)


def _aggregate_mean_stat(series: pd.Series) -> float:
    """Calculate mean, handling NaN values"""
    return float(series.mean()) if not series.isna().all() else 0.0


def _aggregate_weighted_mean_stat(
    stat_series: pd.Series,
    weight_series: pd.Series
) -> float:
    """
    Calculate weighted mean (e.g., per-minute stats)

    Returns:
        Weighted average or 0.0 if no weight
    """
    total_weight = weight_series.sum()
    if total_weight == 0:
        return 0.0

    # Multiply stat by weight for each game, then divide by total weight
    weighted_sum = (stat_series * weight_series).sum()
    return float(weighted_sum / total_weight)


# ============================================================================
# MAIN AGGREGATOR CLASS
# ============================================================================

@dataclass
class SeasonStats:
    """Container for aggregated season statistics"""
    season: str
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    team_id: Optional[int] = None
    team_abbreviation: Optional[str] = None

    games_played: int = 0
    wins: int = 0
    losses: int = 0

    # Totals
    minutes: float = 0.0
    points: float = 0.0
    rebounds: float = 0.0
    assists: float = 0.0
    steals: float = 0.0
    blocks: float = 0.0
    turnovers: float = 0.0

    # Shooting totals
    fgm: float = 0.0
    fga: float = 0.0
    fg_pct: float = 0.0
    fg3m: float = 0.0
    fg3a: float = 0.0
    fg3_pct: float = 0.0
    ftm: float = 0.0
    fta: float = 0.0
    ft_pct: float = 0.0

    # Per-game averages
    ppg: float = 0.0
    rpg: float = 0.0
    apg: float = 0.0
    spg: float = 0.0
    bpg: float = 0.0

    # Additional
    plus_minus: float = 0.0
    double_doubles: int = 0
    triple_doubles: int = 0

    # Metadata
    grouping_level: str = "player/season"
    granularity: str = "season"

    # Awards (optional - only populated if include_awards=True)
    awards: Optional[Dict[str, bool]] = None
    awards_won: Optional[List[str]] = None
    awards_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "SEASON_YEAR": self.season,
            "PLAYER_ID": self.player_id,
            "PLAYER_NAME": self.player_name,
            "TEAM_ID": self.team_id,
            "TEAM_ABBREVIATION": self.team_abbreviation,
            "GP": self.games_played,
            "W": self.wins,
            "L": self.losses,
            "MIN": self.minutes,
            "PTS": self.points,
            "REB": self.rebounds,
            "AST": self.assists,
            "STL": self.steals,
            "BLK": self.blocks,
            "TOV": self.turnovers,
            "FGM": self.fgm,
            "FGA": self.fga,
            "FG_PCT": self.fg_pct,
            "FG3M": self.fg3m,
            "FG3A": self.fg3a,
            "FG3_PCT": self.fg3_pct,
            "FTM": self.ftm,
            "FTA": self.fta,
            "FT_PCT": self.ft_pct,
            "PPG": self.ppg,
            "RPG": self.rpg,
            "APG": self.apg,
            "SPG": self.spg,
            "BPG": self.bpg,
            "PLUS_MINUS": self.plus_minus,
            "DD2": self.double_doubles,
            "TD3": self.triple_doubles,
            "_grouping_level": self.grouping_level,
            "_granularity": self.granularity,
        }

        # Add awards if present
        if self.awards is not None:
            result["AWARDS"] = self.awards
            result["AWARDS_WON"] = self.awards_won if self.awards_won else []
            result["AWARDS_COUNT"] = self.awards_count

        return result


class SeasonAggregator:
    """
    Aggregates game-level data into season-level statistics

    Handles multiple aggregation methods and properly recalculates
    derived stats like shooting percentages.
    """

    def __init__(self):
        self.stat_map = STAT_AGGREGATION_MAP

    async def aggregate_player_season(
        self,
        season: str,
        player_id: Optional[int] = None,
        team_id: Optional[int] = None,
        **additional_filters
    ) -> Union[SeasonStats, List[SeasonStats]]:
        """
        Aggregate player game logs into season statistics with comprehensive filtering

        Supports all PlayerGameGrouping filters (21 NBA API parameters + statistical filters).
        Games are filtered first, then aggregated into season statistics.

        Args:
            season: Season in YYYY-YY format (e.g., "2023-24")
            player_id: Optional player ID to filter (if None, aggregates all players)
            team_id: Optional team ID to filter
            **additional_filters: All filters from PlayerGameGrouping are supported:
                - API filters: location, outcome, date_from, date_to, last_n_games,
                  game_segment, month, opp_team_id, season_type, etc.
                - Statistical filters: MIN, PTS, FG_PCT, etc. (pass as tuples)

        Returns:
            SeasonStats object or list of SeasonStats if player_id not specified

        Examples:
            # Season stats for home games only
            stats = await aggregator.aggregate_player_season(
                "2023-24", player_id=2544, location="Home"
            )

            # Season stats for games with 20+ minutes played
            stats = await aggregator.aggregate_player_season(
                "2023-24", player_id=2544, MIN=(">=", 20)
            )

            # Season stats for winning games in playoffs
            stats = await aggregator.aggregate_player_season(
                "2023-24", player_id=2544, outcome="W", season_type="Playoffs"
            )
        """
        # Fetch game logs with comprehensive filtering
        grouping = GroupingFactory.create(GroupingLevel.PLAYER_GAME)
        filters = {"season": season, **additional_filters}
        if player_id:
            filters["player_id"] = player_id
        if team_id:
            filters["team_id"] = team_id

        game_logs = await grouping.fetch(**filters)

        if game_logs.empty:
            logger.warning(f"No game logs found for season={season}, player_id={player_id}, team_id={team_id}")
            return [] if player_id is None else None

        # Determine grouping level
        grouping_level = "player/team/season" if (player_id and team_id) else "player/season"

        # Group by player if aggregating multiple players
        if player_id is None:
            # Group by PLAYER_ID and aggregate each
            results = []
            for pid, player_games in game_logs.groupby("PLAYER_ID"):
                season_stats = self._aggregate_games(player_games, season, grouping_level=grouping_level)
                results.append(season_stats)
            return results
        else:
            # Aggregate single player
            return self._aggregate_games(game_logs, season, grouping_level=grouping_level)

    async def aggregate_team_season(
        self,
        season: str,
        team_id: Optional[int] = None,
        **additional_filters
    ) -> Union[SeasonStats, List[SeasonStats]]:
        """
        Aggregate team game logs into season statistics with comprehensive filtering

        Supports all TeamGameGrouping filters (21 NBA API parameters + statistical filters).
        Games are filtered first, then aggregated into season statistics.

        Args:
            season: Season in YYYY-YY format (e.g., "2023-24")
            team_id: Optional team ID to filter (if None, aggregates all teams)
            **additional_filters: All filters from TeamGameGrouping are supported:
                - API filters: location, outcome, date_from, date_to, last_n_games,
                  game_segment, month, opp_team_id, season_type, etc.
                - Statistical filters: PTS, W_PCT, PLUS_MINUS, etc. (pass as tuples)

        Returns:
            SeasonStats object or list of SeasonStats if team_id not specified

        Examples:
            # Team season stats for home games only
            stats = await aggregator.aggregate_team_season(
                "2023-24", team_id=1610612747, location="Home"
            )

            # Team season stats for games scoring 100+ points
            stats = await aggregator.aggregate_team_season(
                "2023-24", team_id=1610612747, PTS=(">=", 100)
            )
        """
        grouping = GroupingFactory.create(GroupingLevel.TEAM_GAME)
        filters = {"season": season, **additional_filters}
        if team_id:
            filters["team_id"] = team_id

        game_logs = await grouping.fetch(**filters)

        if game_logs.empty:
            logger.warning(f"No team game logs found for season={season}, team_id={team_id}")
            return [] if team_id is None else None

        # Group by team if aggregating multiple teams
        if team_id is None:
            results = []
            for tid, team_games in game_logs.groupby("TEAM_ID"):
                season_stats = self._aggregate_games(team_games, season, is_team=True)
                results.append(season_stats)
            return results
        else:
            return self._aggregate_games(game_logs, season, is_team=True)

    def _aggregate_games(
        self,
        game_logs: pd.DataFrame,
        season: str,
        is_team: bool = False,
        grouping_level: Optional[str] = None
    ) -> SeasonStats:
        """
        Aggregate a DataFrame of game logs into season totals

        Args:
            game_logs: DataFrame with game-level stats
            season: Season year
            is_team: Whether this is team-level aggregation
            grouping_level: Optional explicit grouping level (overrides is_team logic)

        Returns:
            SeasonStats object with aggregated data
        """
        # Initialize season stats container
        if grouping_level is None:
            grouping_level = "team/season" if is_team else "player/season"

        stats = SeasonStats(
            season=season,
            grouping_level=grouping_level
        )

        # Extract identifiers (use first row values)
        first_row = game_logs.iloc[0]
        if not is_team:
            stats.player_id = int(first_row.get("PLAYER_ID", 0))
            stats.player_name = str(first_row.get("PLAYER_NAME", ""))
        stats.team_id = int(first_row.get("TEAM_ID", 0))
        stats.team_abbreviation = str(first_row.get("TEAM_ABBREVIATION", ""))

        # Games played
        stats.games_played = len(game_logs)

        # Wins/Losses (if available)
        if "WL" in game_logs.columns:
            stats.wins = int((game_logs["WL"] == "W").sum())
            stats.losses = int((game_logs["WL"] == "L").sum())

        # Aggregate counting stats
        stats.minutes = _aggregate_counting_stat(game_logs.get("MIN", pd.Series([0])))
        stats.points = _aggregate_counting_stat(game_logs.get("PTS", pd.Series([0])))
        stats.rebounds = _aggregate_counting_stat(game_logs.get("REB", pd.Series([0])))
        stats.assists = _aggregate_counting_stat(game_logs.get("AST", pd.Series([0])))
        stats.steals = _aggregate_counting_stat(game_logs.get("STL", pd.Series([0])))
        stats.blocks = _aggregate_counting_stat(game_logs.get("BLK", pd.Series([0])))
        stats.turnovers = _aggregate_counting_stat(game_logs.get("TOV", pd.Series([0])))
        stats.plus_minus = _aggregate_counting_stat(game_logs.get("PLUS_MINUS", pd.Series([0])))

        # Shooting totals
        stats.fgm = _aggregate_counting_stat(game_logs.get("FGM", pd.Series([0])))
        stats.fga = _aggregate_counting_stat(game_logs.get("FGA", pd.Series([0])))
        stats.fg3m = _aggregate_counting_stat(game_logs.get("FG3M", pd.Series([0])))
        stats.fg3a = _aggregate_counting_stat(game_logs.get("FG3A", pd.Series([0])))
        stats.ftm = _aggregate_counting_stat(game_logs.get("FTM", pd.Series([0])))
        stats.fta = _aggregate_counting_stat(game_logs.get("FTA", pd.Series([0])))

        # Recalculate shooting percentages from totals
        stats.fg_pct = _aggregate_percentage_stat(
            game_logs.get("FGM", pd.Series([0])),
            game_logs.get("FGA", pd.Series([0]))
        )
        stats.fg3_pct = _aggregate_percentage_stat(
            game_logs.get("FG3M", pd.Series([0])),
            game_logs.get("FG3A", pd.Series([0]))
        )
        stats.ft_pct = _aggregate_percentage_stat(
            game_logs.get("FTM", pd.Series([0])),
            game_logs.get("FTA", pd.Series([0]))
        )

        # Per-game averages
        if stats.games_played > 0:
            stats.ppg = stats.points / stats.games_played
            stats.rpg = stats.rebounds / stats.games_played
            stats.apg = stats.assists / stats.games_played
            stats.spg = stats.steals / stats.games_played
            stats.bpg = stats.blocks / stats.games_played

        # Special stats
        stats.double_doubles = int(_aggregate_counting_stat(game_logs.get("DD2", pd.Series([0]))))
        stats.triple_doubles = int(_aggregate_counting_stat(game_logs.get("TD3", pd.Series([0]))))

        return stats

    def aggregate_to_dataframe(
        self,
        game_logs: pd.DataFrame,
        group_by: Union[str, List[str]] = "PLAYER_ID"
    ) -> pd.DataFrame:
        """
        Aggregate game logs into season stats as a DataFrame

        Args:
            game_logs: DataFrame with game-level data
            group_by: Column(s) to group by (default: PLAYER_ID)

        Returns:
            DataFrame with aggregated season stats
        """
        if game_logs.empty:
            return pd.DataFrame()

        # Ensure group_by is a list
        if isinstance(group_by, str):
            group_by = [group_by]

        results = []
        for group_values, group_df in game_logs.groupby(group_by):
            season = group_df.iloc[0].get("SEASON_YEAR", "Unknown")
            is_team = "TEAM_ID" in group_by and "PLAYER_ID" not in group_by
            season_stats = self._aggregate_games(group_df, season, is_team=is_team)
            results.append(season_stats.to_dict())

        return pd.DataFrame(results)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# ============================================================================
# AWARDS ENRICHMENT
# ============================================================================

def _enrich_with_awards(season_stats: SeasonStats, season: str):
    """
    Enrich a SeasonStats object with awards data.

    Modifies the SeasonStats object in-place, adding:
    - awards: Dict of award_type -> bool (e.g., {"mvp": True, "dpoy": False})
    - awards_won: List of human-readable award names (e.g., ["MVP", "Finals MVP"])
    - awards_count: Total number of awards won

    Args:
        season_stats: SeasonStats object to enrich
        season: Season in YYYY-YY format (e.g., "2023-24")

    Example:
        >>> stats = SeasonStats(season="2023-24", player_id=203999)
        >>> _enrich_with_awards(stats, "2023-24")
        >>> stats.awards
        {"mvp": True, "dpoy": False, "finals_mvp": False, ...}
        >>> stats.awards_won
        ["MVP"]
    """
    from nba_mcp.api.awards_loader import (
        get_player_awards_for_season,
        format_awards_human_readable
    )

    # Only enrich if player_id is available
    if season_stats.player_id:
        try:
            # Get awards for this player/season
            awards = get_player_awards_for_season(season_stats.player_id, season)

            # Add to stats object
            season_stats.awards = awards
            season_stats.awards_won = format_awards_human_readable(awards)
            season_stats.awards_count = sum(awards.values())

            logger.debug(
                f"Enriched player {season_stats.player_id} with {season_stats.awards_count} awards"
            )
        except Exception as e:
            logger.warning(f"Failed to enrich awards for player {season_stats.player_id}: {e}")
            # Leave awards as None on error
            pass


# ============================================================================
# PUBLIC API FUNCTIONS
# ============================================================================

async def get_player_season_stats(
    season: str,
    player_id: Optional[int] = None,
    team_id: Optional[int] = None,
    include_awards: bool = False,
    **filters
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Get aggregated player season statistics with comprehensive filtering

    Supports all PlayerGameGrouping filters (21 NBA API parameters + statistical filters).
    Games are filtered first, then aggregated into season statistics.

    Args:
        season: Season in YYYY-YY format (e.g., "2023-24")
        player_id: Optional player ID (if None, returns all players)
        team_id: Optional team ID filter
        include_awards: If True, includes awards won in this season (default: False)
        **filters: All filters from PlayerGameGrouping are supported:
            - API filters: location, outcome, date_from, date_to, last_n_games,
              game_segment, month, opp_team_id, season_type, etc.
            - Statistical filters: MIN, PTS, FG_PCT, etc. (pass as tuples)

    Returns:
        DataFrame (if player_id=None) or dict (if player_id specified)
        If include_awards=True, adds AWARDS, AWARDS_WON, and AWARDS_COUNT fields

    Examples:
        # Single player - all games
        stats = await get_player_season_stats("2023-24", player_id=2544)

        # Single player - home games only
        stats = await get_player_season_stats("2023-24", player_id=2544, location="Home")

        # Single player - games with 20+ minutes
        stats = await get_player_season_stats("2023-24", player_id=2544, MIN=(">=", 20))

        # Single player - with awards data
        stats = await get_player_season_stats("2023-24", player_id=203999, include_awards=True)
        # Returns: {...stats..., "AWARDS": {"mvp": True, ...}, "AWARDS_WON": ["MVP"], "AWARDS_COUNT": 1}

        # All players
        all_stats = await get_player_season_stats("2023-24")
    """
    aggregator = SeasonAggregator()
    result = await aggregator.aggregate_player_season(season, player_id, team_id, **filters)

    # Enrich with awards if requested
    if include_awards:
        if isinstance(result, list):
            # Multiple players - enrich each
            for stats in result:
                _enrich_with_awards(stats, season)
        elif result:
            # Single player - enrich
            _enrich_with_awards(result, season)

    if isinstance(result, list):
        # Multiple players - return as DataFrame
        return pd.DataFrame([s.to_dict() for s in result])
    elif result is None:
        return {}
    else:
        # Single player - return as dict
        return result.to_dict()


async def get_team_season_stats(
    season: str,
    team_id: Optional[int] = None,
    **filters
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Get aggregated team season statistics with comprehensive filtering

    Supports all TeamGameGrouping filters (21 NBA API parameters + statistical filters).
    Games are filtered first, then aggregated into season statistics.

    Args:
        season: Season in YYYY-YY format (e.g., "2023-24")
        team_id: Optional team ID (if None, returns all teams)
        **filters: All filters from TeamGameGrouping are supported:
            - API filters: location, outcome, date_from, date_to, last_n_games,
              game_segment, month, opp_team_id, season_type, etc.
            - Statistical filters: PTS, W_PCT, PLUS_MINUS, etc. (pass as tuples)

    Returns:
        DataFrame (if team_id=None) or dict (if team_id specified)

    Examples:
        # Single team - all games
        stats = await get_team_season_stats("2023-24", team_id=1610612747)

        # Single team - home games only
        stats = await get_team_season_stats("2023-24", team_id=1610612747, location="Home")

        # Single team - games scoring 100+ points
        stats = await get_team_season_stats("2023-24", team_id=1610612747, PTS=(">=", 100))

        # All teams
        all_stats = await get_team_season_stats("2023-24")
    """
    aggregator = SeasonAggregator()
    result = await aggregator.aggregate_team_season(season, team_id, **filters)

    if isinstance(result, list):
        return pd.DataFrame([s.to_dict() for s in result])
    elif result is None:
        return {}
    else:
        return result.to_dict()
