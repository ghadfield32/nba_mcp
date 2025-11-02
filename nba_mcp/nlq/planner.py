# nba_mcp/nlq/planner.py
"""
Execution Planner for NBA MCP NLQ.

Maps parsed queries to sequences of MCP tool calls using answer pack templates.
Identifies parallelizable operations and handles dependencies.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .parser import ParsedQuery, TimeRange

logger = logging.getLogger(__name__)


# ============================================================================
# PARAMETER NORMALIZATION (Phase 5.2: P3 - Small Model Compatibility)
# ============================================================================


# Parameter name aliases for LLM-generated tool calls
PARAMETER_ALIASES = {
    # Stat category aliases
    "stat": "stat_category",
    "category": "stat_category",
    "stat_type": "stat_category",
    "statistic": "stat_category",

    # Season type aliases
    "season_type": "season_type_all_star",
    "playoff": "season_type_all_star",
    "regular": "season_type_all_star",
    "postseason": "season_type_all_star",

    # Per mode aliases
    "mode": "per_mode",
    "aggregation": "per_mode",
    "per": "per_mode",

    # Normalization aliases
    "norm": "normalization",
    "normalize": "normalization",

    # Team/player name aliases (Phase 5.2 P6: Fixed for get_lineup_stats)
    "player": "player_name",
    "team_name": "team",  # LLMs often use team_name instead of team
    "team_abbr": "team",  # Team abbreviation alias
    "player1": "player1_name",
    "player2": "player2_name",

    # Season aliases (Phase 5.2 P6: Added season_year)
    "year": "season",
    "season_year": "season",  # LLMs often use season_year

    # Limit aliases
    "top": "top_n",
    "count": "top_n",
    "limit": "top_n",

    # Minutes filter aliases (Phase 5.2 P6: Added for get_lineup_stats)
    "minimum_minutes": "min_minutes",
    "min_mins": "min_minutes",
    "minutes_threshold": "min_minutes",
    "minutes_filter": "min_minutes",

    # Lineup filter aliases (Phase 5.2 P6 Phase 2: Added for lineup modifiers)
    "type": "lineup_type",
    "lineup_filter": "lineup_type",
    "including_player": "with_player",
    "player": "with_player",
    "excluding_player": "without_player",
    "except_player": "without_player",
}


def normalize_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize parameter names using aliases.

    Phase 5.2 (P3): Small Model Compatibility (2025-11-01)

    Small models often use different parameter names than the canonical ones
    expected by MCP tools. This function maps alternative names to their
    canonical equivalents.

    Args:
        params: Raw parameters from LLM (may use alternative names)

    Returns:
        Normalized parameters with canonical names

    Examples:
        >>> normalize_parameters({"stat": "PTS", "player": "LeBron James"})
        {'stat_category': 'PTS', 'player_name': 'LeBron James'}

        >>> normalize_parameters({"mode": "PerGame", "top": 10})
        {'per_mode': 'PerGame', 'top_n': 10}

        >>> normalize_parameters({"category": "AST", "limit": 25})
        {'stat_category': 'AST', 'top_n': 25}
    """
    normalized = {}

    for key, value in params.items():
        # Check if key has an alias
        normalized_key = PARAMETER_ALIASES.get(key, key)
        normalized[normalized_key] = value

    return normalized


# ============================================================================
# TOOL CALL SPECIFICATION
# ============================================================================


@dataclass
class ToolCall:
    """Specification for an MCP tool call."""

    tool_name: str
    params: Dict[str, Any]
    depends_on: Optional[List[str]] = None  # Tool names this depends on
    parallel_group: int = 0  # Tools with same group can run in parallel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "depends_on": self.depends_on or [],
            "parallel_group": self.parallel_group,
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan for a query."""

    parsed_query: ParsedQuery
    tool_calls: List[ToolCall]
    template_used: str
    can_parallelize: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parsed_query": self.parsed_query.to_dict(),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "template_used": self.template_used,
            "can_parallelize": self.can_parallelize,
        }


# ============================================================================
# ANSWER PACK TEMPLATES
# ============================================================================

ANSWER_PACK_TEMPLATES = {
    # Template 1: League Leaders
    # Phase 5.3 (NLQ Enhancement - Phase 2): Enhanced with new modifiers (2025-11-01)
    "leaders": {
        "description": "Get top players in a stat category",
        "required": ["stat_types"],
        "optional": ["time_range", "modifiers.top_n", "modifiers.min_games", "modifiers.worst_n"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_league_leaders_info",
                params={
                    "stat_category": (
                        parsed.stat_types[0] if parsed.stat_types else "PTS"
                    ),
                    "season": _extract_season(parsed.time_range),
                    "per_mode": _extract_per_mode(parsed.modifiers),
                    "season_type_all_star": _extract_season_type(parsed.modifiers),
                    "limit": parsed.modifiers.get("worst_n") or parsed.modifiers.get("top_n", 10),  # Phase 5.3: worst_n support
                    "min_games_played": parsed.modifiers.get("min_games"),  # Phase 5.3: min_games support
                },
                parallel_group=0,
            )
        ],
    },
    # Template 2: Player Comparison (2 players)
    "comparison_players": {
        "description": "Compare two players side-by-side",
        "required": ["entities"],  # 2 players
        "optional": ["time_range", "modifiers.normalization"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="compare_players",
                params={
                    "player1_name": parsed.entities[0]["name"],
                    "player2_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                    "normalization": parsed.modifiers.get("normalization", "per_75"),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 3: Team Comparison (Game Context)
    "comparison_teams": {
        "description": "Compare two teams with standings and advanced stats",
        "required": ["entities"],  # 2 teams
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_team_standings",
                params={
                    "season": _extract_season(parsed.time_range),
                    "conference": None,
                },
                parallel_group=0,
            ),
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=1,
            ),
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=1,
            ),
        ],
    },
    # Template 4: Tonight's Game
    "game_context": {
        "description": "Get live scores and game context",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_live_scores",
                params={"target_date": _extract_date(parsed.time_range)},
                parallel_group=0,
            )
        ],
    },
    # Template 5: Player Season Stats
    "player_stats": {
        "description": "Get a player's season statistics",
        "required": ["entities"],  # 1 player
        "optional": ["time_range", "stat_types"],
        "tools": lambda parsed: _build_multi_season_player_stats(parsed),  # Phase 5.2 (P2): Multi-season support
    },
    # Template 6: Team Season Stats
    "team_stats": {
        "description": "Get a team's season statistics",
        "required": ["entities"],  # 1 team
        "optional": ["time_range"],
        "tools": lambda parsed: _build_multi_season_team_stats(parsed),  # Phase 5.2 (P2): Multi-season support
    },
    # Template 7: Conference Standings
    "standings": {
        "description": "Get team standings",
        "required": [],
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_team_standings",
                params={
                    "season": _extract_season(parsed.time_range),
                    "conference": _extract_conference(parsed.raw_query),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 8: Season Comparison (same player, different seasons)
    "season_comparison": {
        "description": "Compare a player across multiple seasons",
        "required": ["entities"],  # 1 player
        "optional": ["time_range"],
        "tools": lambda parsed: _build_season_comparison_tools(parsed),
    },
    # ========================================================================
    # Phase 1: 12 New Templates Added (2025-11-01)
    # ========================================================================
    # Template 9: Shot Chart (player or team shooting visualization)
    "shot_chart": {
        "description": "Get shot chart data for player or team",
        "required": ["entities"],  # 1 player or team
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_shot_chart",
                params={
                    "entity_name": parsed.entities[0]["name"],
                    "entity_type": parsed.entities[0]["entity_type"],
                    "season": _extract_season(parsed.time_range),
                    "granularity": "summary",  # Default to zone summary
                },
                parallel_group=0,
            )
        ],
    },
    # Template 10: Schedule (team or league schedule)
    "schedule": {
        "description": "Get NBA schedule for team or league",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_nba_schedule",
                params={
                    "season": _extract_season(parsed.time_range),
                    "team": (
                        parsed.entities[0]["abbreviation"]
                        if parsed.entities and parsed.entities[0]["entity_type"] == "team"
                        else None
                    ),
                    "date_from": _extract_date_from(parsed.time_range),
                    "date_to": _extract_date_to(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 11: Player Game Stats (recent games or specific game)
    # Phase 5.3 (NLQ Enhancement - Phase 2): Enhanced with last_n_games modifier (2025-11-01)
    "player_game_stats": {
        "description": "Get player's recent game statistics",
        "required": ["entities"],  # 1 player
        "optional": ["time_range", "modifiers.last_n_games"],
        "tools": lambda parsed: _build_multi_season_player_game_stats(parsed),  # Phase 5.2 (P2): Multi-season support (includes last_n_games)
    },
    # Template 12: Box Score (game box score)
    "box_score": {
        "description": "Get box score for a specific game",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_box_score",
                params={
                    "team": (
                        parsed.entities[0]["name"]
                        if parsed.entities and parsed.entities[0]["entity_type"] == "team"
                        else None
                    ),
                    "game_date": _extract_date(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 13: Clutch Stats (late-game performance)
    "clutch_stats": {
        "description": "Get clutch time statistics for player or team",
        "required": ["entities"],  # 1 player or team
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_clutch_stats",
                params={
                    "entity_name": parsed.entities[0]["name"],
                    "entity_type": parsed.entities[0]["entity_type"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 14: Player Head-to-Head (player vs player matchups)
    "player_head_to_head": {
        "description": "Compare two players in their head-to-head games",
        "required": ["entities"],  # 2 players
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_player_head_to_head",
                params={
                    "player1_name": parsed.entities[0]["name"],
                    "player2_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 15: Player Performance Splits (home/away, win/loss, etc.)
    "player_performance_splits": {
        "description": "Get player performance splits and trends",
        "required": ["entities"],  # 1 player
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_player_performance_splits",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                    "last_n_games": _extract_last_n_games(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 16: Play-by-Play (detailed game events)
    "play_by_play": {
        "description": "Get play-by-play data for a game",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="play_by_play",
                params={
                    "game_date": _extract_date(parsed.time_range),
                    "team": (
                        parsed.entities[0]["name"]
                        if parsed.entities and parsed.entities[0]["entity_type"] == "team"
                        else None
                    ),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 17: Advanced Metrics (comprehensive player analytics)
    "advanced_metrics": {
        "description": "Get advanced metrics for a player",
        "required": ["entities"],  # 1 player
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_advanced_metrics",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 18: Era-Adjusted Player Comparison (cross-era analysis)
    "era_adjusted_comparison": {
        "description": "Compare two players from different eras",
        "required": ["entities"],  # 2 players
        "optional": ["time_range"],
        "tools": lambda parsed: _build_era_adjusted_comparison_tools(parsed),
    },
    # Template 19: Season Stats (aggregated season statistics)
    "season_stats_aggregate": {
        "description": "Get aggregated season statistics for player or team",
        "required": ["entities"],  # 1 player or team
        "optional": ["time_range"],
        "tools": lambda parsed: _build_multi_season_season_stats(parsed),  # Phase 5.2 (P2): Multi-season support
    },
    # Template 20: Full Game Context (comprehensive matchup analysis)
    "full_game_context": {
        "description": "Get comprehensive game context for team matchup",
        "required": ["entities"],  # 2 teams
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_game_context",
                params={
                    "team1_name": parsed.entities[0]["name"],
                    "team2_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # ========================================================================
    # Phase 2.2: 4 New Intent Templates (2025-11-01)
    # ========================================================================
    # Template 21: Rankings (player/team rankings in various categories)
    # Phase 5.3 (NLQ Enhancement - Phase 2): Enhanced with new modifiers (2025-11-01)
    "rankings": {
        "description": "Get player or team rankings",
        "required": [],
        "optional": ["entities", "stat_types", "time_range", "modifiers"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_league_leaders_info",
                params={
                    "stat_category": (
                        parsed.stat_types[0] if parsed.stat_types else "PTS"
                    ),
                    "season": _extract_season(parsed.time_range),
                    "per_mode": _extract_per_mode(parsed.modifiers),
                    "limit": parsed.modifiers.get("worst_n") or parsed.modifiers.get("top_n", 25),  # Phase 5.3: worst_n support
                    "conference": parsed.modifiers.get("conference"),
                    "season_type_all_star": _extract_season_type(parsed.modifiers),
                    "min_games_played": parsed.modifiers.get("min_games"),  # Phase 5.3: min_games support
                },
                parallel_group=0,
            )
        ],
    },
    # Template 22: Streaks (winning/losing streaks, performance streaks)
    "streaks": {
        "description": "Get team winning/losing streaks or player performance streaks",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name=(
                    "get_team_standings"
                    if parsed.entities and parsed.entities[0]["entity_type"] == "team"
                    else "get_player_performance_splits"
                ),
                params=(
                    {"season": _extract_season(parsed.time_range), "conference": None}
                    if parsed.entities and parsed.entities[0]["entity_type"] == "team"
                    else {
                        "player_name": parsed.entities[0]["name"] if parsed.entities else None,
                        "season": _extract_season(parsed.time_range),
                        "last_n_games": 10,
                    }
                ),
                parallel_group=0,
            )
        ],
    },
    # Template 23: Milestones (career highs, records, achievements)
    "milestones": {
        "description": "Get player career milestones and records",
        "required": [],
        "optional": ["entities", "stat_types"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_player_career_information",
                params={
                    "player_name": (
                        parsed.entities[0]["name"] if parsed.entities else None
                    ),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 24: Awards (MVP, DPOY, All-NBA, etc.)
    "awards": {
        "description": "Get NBA awards and accolades",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: _build_awards_tools(parsed),
    },
    # ========================================================================
    # Phase 5.1: Filtered Game Queries (2025-11-01 - Audit Improvements)
    # ========================================================================
    # Template 25: Filtered Player Games (games with statistical filters)
    "filtered_games": {
        "description": "Get player games with statistical filters",
        "required": ["entities"],  # 1 player
        "optional": ["time_range", "modifiers.stat_filters", "modifiers.location", "modifiers.opponent", "modifiers.outcome"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="fetch_player_games",
                params={
                    "player": parsed.entities[0]["name"] if parsed.entities else None,
                    "season": _extract_season(parsed.time_range),
                    "stat_filters": _extract_stat_filters_json(parsed.modifiers),
                    "location": _extract_location(parsed.modifiers),
                    "opponent_team": _extract_opponent_team(parsed.modifiers),
                    "outcome": _extract_outcome(parsed.modifiers),
                    "season_type": _extract_season_type(parsed.modifiers),
                    "last_n_games": _extract_last_n_games(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # ========================================================================
    # Phase 5.2 (P4): All-Time Leaders (2025-11-01)
    # ========================================================================
    # Template 26: All-Time Leaders (career statistical leaders)
    "all_time_leaders": {
        "description": "Get all-time NBA career leaders for a stat category",
        "required": ["stat_types"],  # Stat category required
        "optional": ["modifiers.top_n", "modifiers.active_only"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_all_time_leaders",
                params={
                    "stat_category": (
                        parsed.stat_types[0] if parsed.stat_types else "PTS"
                    ),
                    "top_n": parsed.modifiers.get("top_n", 10),
                    "active_only": parsed.modifiers.get("active_only", False),
                },
                parallel_group=0,
            )
        ],
    },
    # Phase 5.2 (P6): Lineup Analysis (2025-11-01) - Template 27
    # Phase 5.2 (P6 Stress Test Fix #3): Removed fallback, require team entity
    # Phase 5.2 (P6 Phase 2): Enhanced with lineup modifiers
    # Phase 5.2 (P6 Phase 3): Enhanced with season range detection
    "lineup_analysis": {
        "description": "Get 5-man lineup statistics for a team with optional modifiers and season range support",
        "required": ["entities"],  # Team required
        "optional": ["time_range", "modifiers.min_minutes", "modifiers.lineup_type", "modifiers.with_player", "modifiers.without_player"],
        "tools": lambda parsed: [
            # Phase 5.2 (P6 Phase 3): Detect season range and use appropriate tool
            ToolCall(
                tool_name=(
                    "get_lineup_stats_multi_season"
                    if parsed.time_range and ":" in str(parsed.time_range)
                    else "get_lineup_stats"
                ),
                params=(
                    # Multi-season parameters
                    {
                        "team": parsed.entities[0]["name"],
                        "seasons": str(parsed.time_range),  # Will be parsed by get_lineup_stats_multi_season
                        "min_minutes": parsed.modifiers.get("min_minutes", 10),
                        "aggregation": "separate",
                    }
                    if parsed.time_range and ":" in str(parsed.time_range)
                    else
                    # Single-season parameters
                    {
                        "team": parsed.entities[0]["name"],
                        "season": _extract_season(parsed.time_range),
                        "min_minutes": parsed.modifiers.get("min_minutes", 10),
                        "lineup_type": parsed.modifiers.get("lineup_type", "all"),
                        "with_player": parsed.modifiers.get("with_player"),
                        "without_player": parsed.modifiers.get("without_player"),
                    }
                ),
                parallel_group=0,
            )
        ],
    },
    # Phase 5.2 (P6 Phase 2): Lineup Comparison (2025-11-01) - Template 28
    "lineup_comparison": {
        "description": "Compare best lineups for two teams side-by-side",
        "required": ["entities"],  # 2 teams required
        "optional": ["time_range", "modifiers.min_minutes"],
        "tools": lambda parsed: [
            # Fetch lineup data for both teams in parallel
            ToolCall(
                tool_name="get_lineup_stats",
                params={
                    "team": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                    "min_minutes": parsed.modifiers.get("min_minutes", 10),
                    "lineup_type": parsed.modifiers.get("lineup_type", "all"),
                },
                parallel_group=0,  # Execute in parallel
            ),
            ToolCall(
                tool_name="get_lineup_stats",
                params={
                    "team": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                    "min_minutes": parsed.modifiers.get("min_minutes", 10),
                    "lineup_type": parsed.modifiers.get("lineup_type", "all"),
                },
                parallel_group=0,  # Execute in parallel
            ),
        ],
    },
    # ========================================================================
    # Phase 5.3 (NLQ Enhancement - Phase 2): New Templates (2025-11-01)
    # ========================================================================
    # Template 29: Highlight (players/teams meeting specific criteria)
    "highlight": {
        "description": "Get players or teams meeting specific statistical criteria",
        "required": [],
        "optional": ["entities", "stat_types", "time_range", "modifiers.stat_filters", "modifiers.min_games"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name=(
                    # If stat_filters present and has player entity, use fetch_player_games
                    "fetch_player_games"
                    if parsed.modifiers.get("stat_filters") and parsed.entities and parsed.entities[0]["entity_type"] == "player"
                    # If stat_filters present but no player, use get_league_leaders_info with filters
                    else "get_league_leaders_info"
                ),
                params=(
                    # fetch_player_games parameters
                    {
                        "player": parsed.entities[0]["name"] if parsed.entities else None,
                        "season": _extract_season(parsed.time_range),
                        "stat_filters": _extract_stat_filters_json(parsed.modifiers),
                        "location": _extract_location(parsed.modifiers),
                        "opponent_team": _extract_opponent_team(parsed.modifiers),
                        "outcome": _extract_outcome(parsed.modifiers),
                    }
                    if parsed.modifiers.get("stat_filters") and parsed.entities and parsed.entities[0]["entity_type"] == "player"
                    # get_league_leaders_info parameters
                    else {
                        "stat_category": (
                            parsed.stat_types[0] if parsed.stat_types else "PTS"
                        ),
                        "season": _extract_season(parsed.time_range),
                        "per_mode": _extract_per_mode(parsed.modifiers),
                        "limit": parsed.modifiers.get("top_n", 25),
                        "min_games_played": parsed.modifiers.get("min_games"),
                        "season_type_all_star": _extract_season_type(parsed.modifiers),
                    }
                ),
                parallel_group=0,
            )
        ],
    },
}


# ============================================================================
# HELPER FUNCTIONS FOR PARAMETER EXTRACTION
# ============================================================================


def _extract_season(time_range: Optional[TimeRange]) -> Optional[str]:
    """Extract season string from time range."""
    if not time_range:
        return None
    return time_range.season


def _extract_seasons(time_range: Optional[TimeRange]) -> Optional[List[str]]:
    """
    Extract list of seasons from time range for multi-season queries.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Args:
        time_range: TimeRange with seasons field populated

    Returns:
        List of season strings or None if single-season query

    Examples:
        >>> _extract_seasons(TimeRange(seasons=["2020-21", "2021-22"]))
        ["2020-21", "2021-22"]

        >>> _extract_seasons(TimeRange(season="2023-24"))
        None  # Single season, use _extract_season() instead
    """
    if not time_range:
        return None

    # Return seasons list if present (multi-season query)
    if time_range.seasons and len(time_range.seasons) > 1:
        return time_range.seasons

    return None


def _extract_date(time_range: Optional[TimeRange]) -> Optional[str]:
    """Extract date string from time range."""
    if not time_range:
        return None
    if time_range.start_date:
        return time_range.start_date.isoformat()
    if time_range.relative == "tonight":
        from datetime import date

        return date.today().isoformat()
    return None


def _extract_per_mode(modifiers: Dict[str, Any]) -> str:
    """Extract per-mode from modifiers."""
    normalization = modifiers.get("normalization", "per_game")
    if normalization == "per_game":
        return "PerGame"
    elif normalization == "per_75":
        return "Per48"  # NBA API doesn't have Per75, use Per48 as closest
    elif normalization == "per_100":
        return "PerGame"  # Will normalize in post-processing
    return "PerGame"


def _extract_season_type(modifiers: Dict[str, Any]) -> str:
    """
    Extract season type from modifiers.

    Phase 5.2 (P5): Enhanced to support all season types consistently.

    Args:
        modifiers: Parsed modifiers dict

    Returns:
        Season type string: "Regular Season", "Playoffs", "Pre Season", "All Star"

    Examples:
        >>> _extract_season_type({"season_type": "playoffs"})
        "Playoffs"
        >>> _extract_season_type({"season_type": "regular"})
        "Regular Season"
    """
    season_type = modifiers.get("season_type", "regular")

    if season_type == "playoffs":
        return "Playoffs"
    elif season_type == "preseason":
        return "Pre Season"
    elif season_type == "allstar":
        return "All Star"

    return "Regular Season"


def _extract_conference(query: str) -> Optional[str]:
    """Extract conference filter from query."""
    query_lower = query.lower()
    if "eastern" in query_lower or "east" in query_lower:
        return "East"
    elif "western" in query_lower or "west" in query_lower:
        return "West"
    return None


# ============================================================================
# MULTI-SEASON TOOL BUILDERS (Phase 5.2 P2: Multi-Season Support)
# ============================================================================


def _build_multi_season_player_stats(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for single or multi-season player stats queries.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)
    Handles both:
    - Single season: "LeBron stats this season" → 1 tool call
    - Multi-season: "LeBron stats from 2020-21 to 2023-24" → 4 tool calls (parallel)

    Args:
        parsed: Parsed query with entities and time_range

    Returns:
        List of ToolCall objects (1 for single season, N for multi-season)

    Examples:
        >>> # Single season
        >>> _build_multi_season_player_stats(ParsedQuery(
        ...     entities=[{"name": "LeBron James"}],
        ...     time_range=TimeRange(season="2023-24")
        ... ))
        [ToolCall(tool_name="get_player_advanced_stats", params={"player_name": "LeBron James", "season": "2023-24"})]

        >>> # Multi-season (parallel execution)
        >>> _build_multi_season_player_stats(ParsedQuery(
        ...     entities=[{"name": "LeBron James"}],
        ...     time_range=TimeRange(seasons=["2020-21", "2021-22", "2022-23"])
        ... ))
        [
            ToolCall(..., parallel_group=0),
            ToolCall(..., parallel_group=1),
            ToolCall(..., parallel_group=2)
        ]
    """
    seasons = _extract_seasons(parsed.time_range)

    if seasons and len(seasons) > 1:
        # Multi-season query: create parallel tool calls for each season
        return [
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": season,
                },
                parallel_group=i,  # Parallel execution (all seasons at once)
            )
            for i, season in enumerate(seasons)
        ]
    else:
        # Single season query: original behavior
        return [
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ]


def _build_multi_season_team_stats(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for single or multi-season team stats queries.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Args:
        parsed: Parsed query with entities and time_range

    Returns:
        List of ToolCall objects
    """
    seasons = _extract_seasons(parsed.time_range)

    if seasons and len(seasons) > 1:
        # Multi-season query: parallel tool calls
        return [
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[0]["name"],
                    "season": season,
                },
                parallel_group=i,
            )
            for i, season in enumerate(seasons)
        ]
    else:
        # Single season query
        return [
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ]


def _build_multi_season_player_game_stats(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for single or multi-season player game stats queries.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Args:
        parsed: Parsed query with entities and time_range

    Returns:
        List of ToolCall objects
    """
    seasons = _extract_seasons(parsed.time_range)

    if seasons and len(seasons) > 1:
        # Multi-season query: parallel tool calls
        return [
            ToolCall(
                tool_name="get_player_game_stats",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": season,
                    "last_n_games": _extract_last_n_games(parsed.time_range),
                },
                parallel_group=i,
            )
            for i, season in enumerate(seasons)
        ]
    else:
        # Single season query
        return [
            ToolCall(
                tool_name="get_player_game_stats",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                    "last_n_games": _extract_last_n_games(parsed.time_range),
                },
                parallel_group=0,
            )
        ]


def _build_multi_season_season_stats(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for single or multi-season aggregated stats queries.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Args:
        parsed: Parsed query with entities and time_range

    Returns:
        List of ToolCall objects
    """
    seasons = _extract_seasons(parsed.time_range)

    if seasons and len(seasons) > 1:
        # Multi-season query: parallel tool calls
        return [
            ToolCall(
                tool_name="get_season_stats",
                params={
                    "entity_type": parsed.entities[0]["entity_type"],
                    "entity_name": parsed.entities[0]["name"],
                    "season": season,
                },
                parallel_group=i,
            )
            for i, season in enumerate(seasons)
        ]
    else:
        # Single season query
        return [
            ToolCall(
                tool_name="get_season_stats",
                params={
                    "entity_type": parsed.entities[0]["entity_type"],
                    "entity_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ]


def _build_season_comparison_tools(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for season comparison.

    Extracts multiple seasons from query (e.g., "2023 vs 2020" or "this season vs last season").
    """
    # Parse multiple seasons from query
    import re

    seasons = re.findall(r"(\d{4})-?(\d{2})?", parsed.raw_query)

    if len(seasons) >= 2:
        # Found explicit season years
        season1 = f"{seasons[0][0]}-{seasons[0][1] or str(int(seasons[0][0]) + 1)[-2:]}"
        season2 = f"{seasons[1][0]}-{seasons[1][1] or str(int(seasons[1][0]) + 1)[-2:]}"

        return [
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={"player_name": parsed.entities[0]["name"], "season": season1},
                parallel_group=0,
            ),
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={"player_name": parsed.entities[0]["name"], "season": season2},
                parallel_group=0,
            ),
        ]

    # Default: current season only
    return [
        ToolCall(
            tool_name="get_player_advanced_stats",
            params={
                "player_name": parsed.entities[0]["name"],
                "season": _extract_season(parsed.time_range),
            },
            parallel_group=0,
        )
    ]


# ============================================================================
# Phase 1: New Helper Functions for Time Filters (2025-11-01)
# ============================================================================


def _extract_date_from(time_range: Optional[TimeRange]) -> Optional[str]:
    """
    Extract start date from time range.

    Args:
        time_range: Parsed time range

    Returns:
        Start date in YYYY-MM-DD format or None
    """
    if not time_range:
        return None
    if time_range.start_date:
        return time_range.start_date.isoformat()
    return None


def _extract_date_to(time_range: Optional[TimeRange]) -> Optional[str]:
    """
    Extract end date from time range.

    Args:
        time_range: Parsed time range

    Returns:
        End date in YYYY-MM-DD format or None
    """
    if not time_range:
        return None
    if time_range.end_date:
        return time_range.end_date.isoformat()
    return None


def _extract_last_n_games(time_range: Optional[TimeRange]) -> Optional[int]:
    """
    Extract 'last N games' filter from time range.

    Handles time_range.relative values like:
    - "last_10_games" → 10
    - "last_5_games" → 5
    - "last_game" → 1

    Args:
        time_range: Parsed time range

    Returns:
        Number of games or None
    """
    if not time_range or not time_range.relative:
        return None

    # Match "last_N_games" pattern
    import re

    match = re.match(r"last_(\d+)_games?", time_range.relative)
    if match:
        return int(match.group(1))

    return None


def _build_era_adjusted_comparison_tools(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for era-adjusted player comparison.

    Extracts seasons from query for each player, then builds comparison.
    Falls back to current season if no explicit seasons found.

    Args:
        parsed: Parsed query with 2 player entities

    Returns:
        List of ToolCall objects
    """
    # Parse seasons from query
    import re

    seasons = re.findall(r"(\d{4})-?(\d{2})?", parsed.raw_query)

    if len(seasons) >= 2 and len(parsed.entities) >= 2:
        # Found explicit seasons for both players
        season1 = f"{seasons[0][0]}-{seasons[0][1] or str(int(seasons[0][0]) + 1)[-2:]}"
        season2 = f"{seasons[1][0]}-{seasons[1][1] or str(int(seasons[1][0]) + 1)[-2:]}"

        return [
            ToolCall(
                tool_name="compare_players_era_adjusted",
                params={
                    "player1_name": parsed.entities[0]["name"],
                    "player2_name": parsed.entities[1]["name"],
                    "season1": season1,
                    "season2": season2,
                },
                parallel_group=0,
            )
        ]

    # Fallback: use regular player comparison
    if len(parsed.entities) >= 2:
        return [
            ToolCall(
                tool_name="compare_players",
                params={
                    "player1_name": parsed.entities[0]["name"],
                    "player2_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ]

    return []


# ============================================================================
# Phase 5.1: Helper Functions for Filtered Games (2025-11-01)
# ============================================================================


def _extract_stat_filters_json(modifiers: Dict[str, Any]) -> Optional[str]:
    """
    Extract statistical filters as JSON string for fetch_player_games.

    Args:
        modifiers: Parsed modifiers dict

    Returns:
        JSON string like '{"PTS": [">=", 30], "FG3_PCT": [">=", 0.5]}'
        or None if no filters

    Phase 5.1: Added for filtered game queries.
    """
    stat_filters = modifiers.get("stat_filters")
    if not stat_filters:
        return None

    import json
    return json.dumps(stat_filters)


def _extract_location(modifiers: Dict[str, Any]) -> Optional[str]:
    """
    Extract location filter from modifiers.

    Args:
        modifiers: Parsed modifiers dict

    Returns:
        "Home" or "Road" or None

    Phase 5.1: Added for filtered game queries.
    """
    location = modifiers.get("location")
    if location == "home":
        return "Home"
    elif location == "away":
        return "Road"
    return None


def _extract_opponent_team(modifiers: Dict[str, Any]) -> Optional[str]:
    """
    Extract opponent team filter from modifiers.

    Args:
        modifiers: Parsed modifiers dict

    Returns:
        Team name or None

    Phase 5.1: Added for filtered game queries.
    """
    return modifiers.get("opponent")


def _extract_outcome(modifiers: Dict[str, Any]) -> Optional[str]:
    """
    Extract win/loss outcome filter from modifiers.

    Args:
        modifiers: Parsed modifiers dict

    Returns:
        "W" or "L" or None

    Phase 5.1: Added for filtered game queries.
    """
    return modifiers.get("outcome")


def _build_awards_tools(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for awards queries.

    Handles both player-specific awards and award type queries.
    Examples:
    - "LeBron James awards" → player_name parameter
    - "Who won MVP in 2023?" → award_type + season parameters

    Phase 2.2: Added for awards intent type.

    Args:
        parsed: Parsed query

    Returns:
        List of ToolCall objects
    """
    import re

    params = {}

    # Check if player name specified
    if parsed.entities:
        params["player_name"] = parsed.entities[0]["name"]

    # Extract award type from query
    query_lower = parsed.raw_query.lower()
    if "mvp" in query_lower or "most valuable" in query_lower:
        params["award_type"] = "mvp"
    elif "dpoy" in query_lower or "defensive player" in query_lower:
        params["award_type"] = "dpoy"
    elif "roy" in query_lower or "rookie of the year" in query_lower:
        params["award_type"] = "roy"
    elif "sixth man" in query_lower:
        params["award_type"] = "smoy"
    elif "most improved" in query_lower or "mip" in query_lower:
        params["award_type"] = "mip"
    elif "coach of the year" in query_lower or "coy" in query_lower:
        params["award_type"] = "coy"
    elif "all-nba" in query_lower or "all nba" in query_lower:
        if "first" in query_lower:
            params["award_type"] = "all_nba_first"
        elif "second" in query_lower:
            params["award_type"] = "all_nba_second"
        elif "third" in query_lower:
            params["award_type"] = "all_nba_third"
        else:
            params["award_type"] = "all_nba_first"  # Default to first team
    elif "all-defensive" in query_lower or "all defensive" in query_lower:
        if "first" in query_lower:
            params["award_type"] = "all_defensive_first"
        elif "second" in query_lower:
            params["award_type"] = "all_defensive_second"
        else:
            params["award_type"] = "all_defensive_first"
    elif "all-rookie" in query_lower or "all rookie" in query_lower:
        if "first" in query_lower:
            params["award_type"] = "all_rookie_first"
        elif "second" in query_lower:
            params["award_type"] = "all_rookie_second"
        else:
            params["award_type"] = "all_rookie_first"

    # Extract season if specified
    if parsed.time_range and parsed.time_range.season:
        params["season"] = parsed.time_range.season

    # Extract last N if specified (e.g., "last 5 MVP winners")
    last_n_match = re.search(r"last (\d+)", query_lower)
    if last_n_match and not parsed.entities:  # Only use if not player-specific
        params["last_n"] = int(last_n_match.group(1))

    return [
        ToolCall(
            tool_name="get_nba_awards",
            params=params,
            parallel_group=0,
        )
    ]


# ============================================================================
# TEMPLATE VALIDATION (Phase 5.3: NLQ Enhancement - Phase 2.3)
# ============================================================================


def validate_template_match(parsed: ParsedQuery, template_name: str) -> List[str]:
    """
    Validate that a parsed query has required fields for a template.

    Phase 5.3 (NLQ Enhancement - Phase 2.3): Template validation (2025-11-01)

    Args:
        parsed: Parsed query
        template_name: Template name to validate against

    Returns:
        List of validation warnings (empty if valid)

    Examples:
        >>> warnings = validate_template_match(parsed, "leaders")
        >>> if warnings:
        ...     print(f"Missing: {', '.join(warnings)}")
    """
    warnings = []

    if template_name not in ANSWER_PACK_TEMPLATES:
        return [f"Unknown template: {template_name}"]

    template = ANSWER_PACK_TEMPLATES[template_name]
    required = template.get("required", [])

    # Check required fields
    for field in required:
        # Parse field path (e.g., "entities", "modifiers.top_n")
        parts = field.split(".")
        value = parsed

        # Traverse field path
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = None
                break

        # Check if value is present
        if value is None or (isinstance(value, (list, dict, str)) and not value):
            warnings.append(f"Missing required field: {field}")

    return warnings


# ============================================================================
# TEMPLATE MATCHING
# ============================================================================


def match_template(parsed: ParsedQuery) -> Optional[str]:
    """
    Match parsed query to best answer pack template.

    Args:
        parsed: Parsed query

    Returns:
        Template name or None if no match
    """
    intent = parsed.intent
    num_entities = len(parsed.entities)
    entity_types = (
        [e["entity_type"] for e in parsed.entities] if parsed.entities else []
    )

    logger.debug(
        f"Matching template: intent={intent}, entities={num_entities}, types={entity_types}"
    )

    # Leaders query
    if intent == "leaders":
        return "leaders"

    # Comparison queries
    if intent == "comparison":
        # Phase 5.2 (P6 Phase 2): Lineup comparison detection (2025-11-01)
        # Check if this is a lineup-specific comparison
        if "lineup" in parsed.raw_query.lower():
            if num_entities == 2 and all(t == "team" for t in entity_types):
                return "lineup_comparison"
        # Check if query contains lineup keywords with team comparison
        if num_entities == 2 and all(t == "team" for t in entity_types):
            if any(keyword in parsed.raw_query.lower() for keyword in ["five-man", "5-man", "rotation"]):
                return "lineup_comparison"

        if num_entities == 2:
            # Determine if player or team comparison
            if all(t == "player" for t in entity_types):
                return "comparison_players"
            elif all(t == "team" for t in entity_types):
                return "comparison_teams"

        # Season comparison (same player, different seasons)
        elif num_entities == 1 and entity_types[0] == "player":
            # Check if query mentions multiple seasons
            import re

            if len(re.findall(r"\d{4}", parsed.raw_query)) >= 2:
                return "season_comparison"

    # Game context
    if intent == "game_context":
        return "game_context"

    # Player stats
    if intent == "player_stats" and num_entities == 1 and entity_types[0] == "player":
        return "player_stats"

    # Team stats
    if intent == "team_stats" and num_entities == 1 and entity_types[0] == "team":
        return "team_stats"

    # Standings
    if intent == "standings":
        return "standings"

    # Phase 2.2: New intent types (2025-11-01)
    # Rankings
    if intent == "rankings":
        return "rankings"

    # Streaks
    if intent == "streaks":
        return "streaks"

    # Milestones
    if intent == "milestones":
        return "milestones"

    # Awards
    if intent == "awards":
        return "awards"

    # Phase 5.3 (NLQ Enhancement - Phase 2): Missing intent routing (2025-11-01)
    # Filtered games (games with statistical filters)
    if intent == "filtered_games":
        return "filtered_games"

    # All-time leaders (career statistical leaders)
    if intent == "all_time_leaders":
        return "all_time_leaders"

    # Lineup analysis (5-man lineup statistics)
    if intent == "lineup_analysis":
        return "lineup_analysis"

    # Highlight intent (players/teams meeting specific criteria)
    if intent == "highlight":
        return "highlight"

    logger.warning(f"No template matched for intent={intent}, entities={num_entities}")
    return None


# ============================================================================
# PLAN GENERATION
# ============================================================================


async def generate_execution_plan(parsed: ParsedQuery) -> Optional[ExecutionPlan]:
    """
    Generate execution plan from parsed query.

    Args:
        parsed: Parsed query

    Returns:
        ExecutionPlan or None if no template matches

    Examples:
        >>> parsed = ParsedQuery(intent="leaders", stat_types=["AST"])
        >>> plan = generate_execution_plan(parsed)
        >>> plan.tool_calls[0].tool_name
        'get_league_leaders_info'
    """
    logger.info(f"Generating execution plan for query: '{parsed.raw_query}'")

    # Match template
    template_name = match_template(parsed)

    # Phase 3.6: LLM fallback for unknown intents
    # If no template matches, attempt to generate plan using LLM
    if not template_name:
        from .llm_fallback import generate_plan

        logger.warning(
            f"No template matched for intent '{parsed.intent}', attempting LLM plan generation..."
        )
        tool_calls = await generate_plan(parsed)

        if tool_calls:
            logger.info(
                f"LLM plan generation successful: {len(tool_calls)} tool calls"
            )
            # Determine if tools can be parallelized
            can_parallelize = len(set(tc.parallel_group for tc in tool_calls)) > 1

            plan = ExecutionPlan(
                parsed_query=parsed,
                tool_calls=tool_calls,
                template_used="llm_generated",
                can_parallelize=can_parallelize,
            )

            logger.debug(f"LLM-generated execution plan: {plan.to_dict()}")
            return plan
        else:
            logger.error("No template matched and LLM plan generation failed - cannot generate plan")
            return None

    logger.info(f"Matched template: {template_name}")

    # Phase 5.3 (NLQ Enhancement - Phase 2.3): Validate template match (2025-11-01)
    validation_warnings = validate_template_match(parsed, template_name)
    if validation_warnings:
        logger.warning(f"Template validation warnings for '{template_name}': {validation_warnings}")
        # Add warnings to parsed query suggestions
        if not parsed.validation_issues:
            parsed.validation_issues = []
        if not parsed.suggestions:
            parsed.suggestions = []
        parsed.validation_issues.extend(validation_warnings)
        # Suggest what's missing
        for warning in validation_warnings:
            if "Missing required field: entities" in warning:
                parsed.suggestions.append("Try adding a player or team name to your query")
            elif "Missing required field: stat_types" in warning:
                parsed.suggestions.append("Try specifying a statistic (e.g., 'points', 'assists', 'rebounds')")

    # Get template
    template = ANSWER_PACK_TEMPLATES[template_name]

    # Generate tool calls using template function
    try:
        tool_calls = template["tools"](parsed)
        logger.info(f"Generated {len(tool_calls)} tool calls")

        # Determine if tools can be parallelized
        can_parallelize = len(set(tc.parallel_group for tc in tool_calls)) > 1

        plan = ExecutionPlan(
            parsed_query=parsed,
            tool_calls=tool_calls,
            template_used=template_name,
            can_parallelize=can_parallelize,
        )

        logger.debug(f"Execution plan: {plan.to_dict()}")
        return plan

    except Exception as e:
        logger.error(f"Failed to generate tool calls from template: {e}", exc_info=True)
        return None


# ============================================================================
# PLAN VALIDATION
# ============================================================================


def _detect_dependency_cycles(plan: ExecutionPlan) -> Optional[List[str]]:
    """
    Detect circular dependencies in execution plan.

    Phase 6.8: Added dependency cycle detection (2025-11-02)

    Uses depth-first search to detect cycles in the dependency graph.
    Returns the cycle path if found, None otherwise.

    Args:
        plan: Execution plan to check

    Returns:
        List of tool names forming a cycle, or None if no cycles

    Examples:
        >>> # No cycle
        >>> plan = ExecutionPlan(tool_calls=[
        ...     ToolCall("tool1", {}, depends_on=None),
        ...     ToolCall("tool2", {}, depends_on=["tool1"])
        ... ])
        >>> _detect_dependency_cycles(plan)
        None

        >>> # Cycle detected: tool1 → tool2 → tool1
        >>> plan = ExecutionPlan(tool_calls=[
        ...     ToolCall("tool1", {}, depends_on=["tool2"]),
        ...     ToolCall("tool2", {}, depends_on=["tool1"])
        ... ])
        >>> _detect_dependency_cycles(plan)
        ["tool1", "tool2", "tool1"]
    """
    # Build dependency graph: {tool_name: [dependencies]}
    graph = {}
    for tc in plan.tool_calls:
        graph[tc.tool_name] = tc.depends_on or []

    # Track visited nodes and recursion stack
    visited = set()
    rec_stack = set()
    path = []

    def dfs(node: str) -> Optional[List[str]]:
        """DFS traversal to detect cycles."""
        if node in rec_stack:
            # Cycle detected! Build cycle path
            cycle_start_idx = path.index(node)
            return path[cycle_start_idx:] + [node]

        if node in visited:
            # Already explored this branch, no cycle here
            return None

        # Mark as visited and add to recursion stack
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        # Check all dependencies
        for dependency in graph.get(node, []):
            if dependency not in graph:
                # Dependency references non-existent tool (will be caught by other validation)
                continue

            cycle = dfs(dependency)
            if cycle:
                return cycle

        # Remove from recursion stack
        rec_stack.remove(node)
        path.pop()
        return None

    # Check each tool as potential starting point
    for tool_name in graph:
        if tool_name not in visited:
            cycle = dfs(tool_name)
            if cycle:
                return cycle

    return None


def validate_execution_plan(plan: ExecutionPlan) -> bool:
    """
    Validate that execution plan is sound.

    Checks:
    - All tool calls have required parameters
    - Dependencies are resolvable
    - No circular dependencies

    Args:
        plan: Execution plan

    Returns:
        True if valid, False otherwise
    """
    if not plan.tool_calls:
        logger.error("Execution plan has no tool calls")
        return False

    # Check that all tool calls have tool_name and params
    for tc in plan.tool_calls:
        if not tc.tool_name:
            logger.error("Tool call missing tool_name")
            return False
        if tc.params is None:
            logger.error(f"Tool call {tc.tool_name} missing params")
            return False

    # Phase 6.8: Validate dependencies (detect circular dependencies)
    cycle = _detect_dependency_cycles(plan)
    if cycle:
        cycle_path = " → ".join(cycle)
        logger.error(f"Circular dependency detected: {cycle_path}")
        return False

    return True


# ============================================================================
# MAIN PLANNER FUNCTION
# ============================================================================


async def plan_query_execution(parsed: ParsedQuery) -> ExecutionPlan:
    """
    Main planner function: generate and validate execution plan.

    Args:
        parsed: Parsed query

    Returns:
        Valid execution plan

    Raises:
        ValueError: If no plan can be generated or validation fails
    """
    plan = await generate_execution_plan(parsed)

    if not plan:
        raise ValueError(
            f"No execution plan could be generated for query: '{parsed.raw_query}'"
        )

    if not validate_execution_plan(plan):
        raise ValueError(
            f"Generated plan failed validation for query: '{parsed.raw_query}'"
        )

    return plan
