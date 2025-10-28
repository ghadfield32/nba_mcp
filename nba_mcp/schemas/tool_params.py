"""
Parameter models for all NBA MCP tools.

This module defines Pydantic models for every MCP tool's parameters,
enabling automatic JSON Schema generation for LLM function calling.

Each model includes:
- Type validation via Pydantic
- Field descriptions for schema documentation
- Examples for LLM guidance
- Default values where appropriate
- Constraints (Literal types, Optional, etc.)

Usage:
    # Generate JSON Schema for a tool
    schema = ResolveNBAEntityParams.model_json_schema()

    # Validate parameters
    params = ResolveNBAEntityParams(query="LeBron", entity_type="player")
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ============================================================================
# Tool 1: resolve_nba_entity
# ============================================================================


class ResolveNBAEntityParams(BaseModel):
    """
    Parameters for resolving ambiguous player/team names to specific entities.

    Uses fuzzy string matching with confidence scoring to handle partial names,
    abbreviations, and nicknames. Includes LRU caching for performance.
    """

    query: str = Field(
        ...,
        description="Player or team name to resolve (supports partial names, abbreviations, nicknames)",
        examples=["LeBron", "LAL", "Durant", "Los Angeles Lakers"],
        min_length=1,
    )
    entity_type: Optional[Literal["player", "team"]] = Field(
        None,
        description="Optional filter to search only players or teams. If None, searches both.",
    )
    return_suggestions: bool = Field(
        True,
        description="If True, returns alternative suggestions when no exact match found",
    )


# ============================================================================
# Tool 2: get_player_career_information
# ============================================================================


class GetPlayerCareerInformationParams(BaseModel):
    """
    Parameters for retrieving a player's career statistics.

    Returns comprehensive career stats including games played, minutes,
    points, rebounds, assists, shooting percentages, and more.
    """

    player_name: str = Field(
        ...,
        description="Player name (full or partial, e.g., 'LeBron James', 'LeBron', 'James')",
        examples=["LeBron James", "Stephen Curry", "Giannis Antetokounmpo"],
        min_length=2,
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, returns career totals.",
        examples=["2023-24", "2015-16", "2010-11"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )


# ============================================================================
# Tool 3: get_league_leaders_info
# ============================================================================


class LeagueLeadersParams(BaseModel):
    """
    Parameters for retrieving NBA league leaders by statistical category.

    Returns the top players for a given stat (points, rebounds, assists, etc.)
    with flexible aggregation modes (totals, per-game, per-48).
    """

    season: Optional[Union[str, List[str]]] = Field(
        None,
        description="Season(s) in 'YYYY-YY' format, or list of seasons. None defaults to current season.",
        examples=["2023-24", ["2022-23", "2023-24"]],
    )
    stat_category: Literal[
        "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"
    ] = Field(
        ...,
        description=(
            "Statistical category to rank by. "
            "PTS=Points, REB=Rebounds, AST=Assists, STL=Steals, BLK=Blocks, "
            "FG_PCT=Field Goal %, FG3_PCT=3-Point %, FT_PCT=Free Throw %"
        ),
    )
    per_mode: Literal["Totals", "PerGame", "Per48"] = Field(
        ...,
        description=(
            "Statistical aggregation mode. "
            "'Totals'=Season totals, 'PerGame'=Per-game averages, 'Per48'=Per-48-minutes rate"
        ),
    )


# ============================================================================
# Tool 4: get_live_scores
# ============================================================================


class GetLiveScoresParams(BaseModel):
    """
    Parameters for retrieving live or historical NBA game scores.

    Returns game summaries with scores, teams, and game status (live, final, scheduled).
    """

    target_date: Optional[str] = Field(
        None,
        description="Date in 'YYYY-MM-DD' format. If None, uses today's date.",
        examples=["2024-01-15", "2023-12-25"],
        pattern=r"^\d{4}-\d{2}-\d{2}$|^$",
    )


# ============================================================================
# Tool 5: get_date_range_game_log_or_team_game_log
# ============================================================================


class GetDateRangeGameLogParams(BaseModel):
    """
    Parameters for retrieving game logs within a date range.

    Returns game-by-game results for a team or entire league, including
    scores, stats, and outcomes across regular season, playoffs, and more.
    """

    season: str = Field(
        ...,
        description="Season in 'YYYY-YY' format (e.g., '2023-24')",
        examples=["2023-24", "2022-23"],
        pattern=r"^\d{4}-\d{2}$",
    )
    team: Optional[str] = Field(
        None,
        description="Team name or abbreviation. If None, returns logs for all teams.",
        examples=["Lakers", "LAL", "Boston Celtics", "BOS"],
    )
    date_from: Optional[str] = Field(
        None,
        description="Start date in 'YYYY-MM-DD' format. If None, starts from season beginning.",
        examples=["2024-01-01", "2023-10-15"],
        pattern=r"^\d{4}-\d{2}-\d{2}$|^$",
    )
    date_to: Optional[str] = Field(
        None,
        description="End date in 'YYYY-MM-DD' format. If None, includes through season end.",
        examples=["2024-04-15", "2024-06-30"],
        pattern=r"^\d{4}-\d{2}-\d{2}$|^$",
    )


# ============================================================================
# Tool 6: play_by_play
# ============================================================================


class PlayByPlayParams(BaseModel):
    """
    Parameters for retrieving detailed play-by-play data for NBA games.

    Returns chronological game events with timestamps, scores, and descriptions.
    Supports both live games (recent plays) and historical games (full detail).
    """

    game_date: Optional[str] = Field(
        None,
        description="Game date in 'YYYY-MM-DD' format. If None, uses today's date for live games.",
        examples=["2024-01-15", "2023-12-25"],
        pattern=r"^\d{4}-\d{2}-\d{2}$|^$",
    )
    team: Optional[str] = Field(
        None,
        description="Team name or abbreviation. If None, returns all games for the date.",
        examples=["Lakers", "LAL", "Warriors"],
    )
    start_period: int = Field(
        1,
        description="Starting quarter/period (1-4 for regulation, 5+ for OT)",
        ge=1,
        le=10,
    )
    end_period: int = Field(
        4, description="Ending quarter/period (1-4 for regulation)", ge=1, le=10
    )
    start_clock: Optional[str] = Field(
        None,
        description="Starting game clock in 'MM:SS' format (e.g., '7:30'). If None, starts from period beginning.",
        examples=["12:00", "7:30", "2:15"],
        pattern=r"^\d{1,2}:\d{2}$|^$",
    )
    recent_n: int = Field(
        5,
        description="For live games, number of most recent plays to include",
        ge=1,
        le=100,
    )
    max_lines: int = Field(
        200,
        description="Maximum number of output lines to return (prevents excessive data)",
        ge=10,
        le=1000,
    )


# ============================================================================
# Tool 7: get_team_standings
# ============================================================================


class GetTeamStandingsParams(BaseModel):
    """
    Parameters for retrieving NBA team standings.

    Returns comprehensive standings with win-loss records, games behind,
    conference/division rankings, home/away splits, and current streaks.
    """

    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, uses current season.",
        examples=["2023-24", "2022-23"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )
    conference: Optional[Literal["East", "West"]] = Field(
        None,
        description="Filter by conference ('East' or 'West'). If None, returns both conferences.",
    )


# ============================================================================
# Tool 8: get_team_advanced_stats
# ============================================================================


class GetTeamAdvancedStatsParams(BaseModel):
    """
    Parameters for retrieving team advanced statistics.

    Returns comprehensive team metrics including Offensive/Defensive/Net Rating,
    Pace, True Shooting %, and Four Factors (eFG%, TOV%, OREB%, FTA Rate).
    """

    team_name: str = Field(
        ...,
        description="Team name or abbreviation (e.g., 'Lakers', 'LAL', 'Los Angeles Lakers')",
        examples=["Lakers", "LAL", "Boston Celtics", "BOS"],
        min_length=2,
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, uses current season.",
        examples=["2023-24", "2015-16"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )


# ============================================================================
# Tool 9: get_player_advanced_stats
# ============================================================================


class GetPlayerAdvancedStatsParams(BaseModel):
    """
    Parameters for retrieving player advanced statistics.

    Returns comprehensive efficiency metrics including Usage%, TS%, eFG%,
    PER, Offensive/Defensive Rating, and percentage-based stats.
    """

    player_name: str = Field(
        ...,
        description="Player name (full or partial, e.g., 'LeBron James', 'LeBron', 'James')",
        examples=["LeBron James", "Stephen Curry", "Giannis"],
        min_length=2,
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, uses current season.",
        examples=["2023-24", "2015-16"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )


# ============================================================================
# Tool 10: compare_players
# ============================================================================


class ComparePlayersParams(BaseModel):
    """
    Parameters for comparing two players side-by-side.

    Returns fair comparison with shared metric definitions, per-possession
    normalization, and optional era adjustments for historical comparisons.
    """

    player1_name: str = Field(
        ...,
        description="First player name (full or partial)",
        examples=["LeBron James", "Michael Jordan"],
        min_length=2,
    )
    player2_name: str = Field(
        ...,
        description="Second player name (full or partial)",
        examples=["Kevin Durant", "Kobe Bryant"],
        min_length=2,
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format for comparison. If None, uses current season.",
        examples=["2023-24", "2012-13"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )
    normalization: Literal["raw", "per_game", "per_75", "era_adjusted"] = Field(
        "per_75",
        description=(
            "Statistical normalization mode. "
            "'raw'=Season totals, 'per_game'=Per-game averages, "
            "'per_75'=Per-75 possessions (fairest), 'era_adjusted'=Adjust for pace/era"
        ),
    )


# ============================================================================
# Tool 11: compare_players_era_adjusted
# ============================================================================


class ComparePlayersEraAdjustedParams(BaseModel):
    """
    Parameters for comparing two players across different eras with adjustments.

    Returns fair cross-era comparison accounting for league-wide pace and scoring
    environment changes. Allows comparing players from vastly different eras
    (e.g., Michael Jordan 1990s vs LeBron James 2010s).
    """

    player1_name: str = Field(
        ...,
        description="First player name (full or partial)",
        examples=["Michael Jordan", "LeBron James"],
        min_length=2,
    )
    player2_name: str = Field(
        ...,
        description="Second player name (full or partial)",
        examples=["LeBron James", "Kobe Bryant"],
        min_length=2,
    )
    season1: str = Field(
        ...,
        description="Season for player 1 in 'YYYY-YY' format (e.g., '1995-96')",
        examples=["1995-96", "2012-13"],
        pattern=r"^\d{4}-\d{2}$",
    )
    season2: str = Field(
        ...,
        description="Season for player 2 in 'YYYY-YY' format (e.g., '2012-13')",
        examples=["2012-13", "2023-24"],
        pattern=r"^\d{4}-\d{2}$",
    )


# ============================================================================
# Tool 12: answer_nba_question
# ============================================================================


class AnswerNBAQuestionParams(BaseModel):
    """
    Parameters for the natural language query (NLQ) pipeline.

    Processes natural language questions and automatically orchestrates
    the right NBA API calls to provide formatted, human-readable answers.
    """

    question: str = Field(
        ...,
        description="Natural language question about NBA data",
        examples=[
            "Who leads the NBA in assists?",
            "Compare LeBron James and Kevin Durant",
            "Show me Giannis stats from 2023-24",
            "Eastern Conference standings",
            "What games are on today?",
        ],
        min_length=5,
    )


# ============================================================================
# Tool 13: get_metrics_info
# ============================================================================


class GetMetricsInfoParams(BaseModel):
    """
    Parameters for retrieving server metrics and observability information.

    Note: This tool takes no parameters. This model exists for consistency
    and schema completeness.
    """

    pass  # No parameters for this tool


# ============================================================================
# Export All Models
# ============================================================================

__all__ = [
    "ResolveNBAEntityParams",
    "GetPlayerCareerInformationParams",
    "LeagueLeadersParams",
    "GetLiveScoresParams",
    "GetDateRangeGameLogParams",
    "PlayByPlayParams",
    "GetTeamStandingsParams",
    "GetTeamAdvancedStatsParams",
    "GetPlayerAdvancedStatsParams",
    "ComparePlayersParams",
    "ComparePlayersEraAdjustedParams",
    "AnswerNBAQuestionParams",
    "GetMetricsInfoParams",
]
