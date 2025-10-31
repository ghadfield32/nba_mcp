# -*- coding: utf-8 -*-
"""
NBA MCP Tool Schemas

This module defines Pydantic models for all MCP tool inputs and outputs.
These schemas provide:
- Automatic input validation
- Clear documentation for each parameter
- Type safety and IDE autocomplete
- Easy schema generation for AI models
- Comprehensive examples for each field

Usage:
    from nba_mcp.api.tool_schemas import FetchPlayerGamesInput, FetchPlayerGamesOutput

    # Create input with validation
    input_data = FetchPlayerGamesInput(
        season="2023-24",
        player="LeBron James",
        last_n_games=10
    )

    # Access validated fields
    print(input_data.season)  # "2023-24"
    print(input_data.player)  # "LeBron James"
"""

from typing import Optional, Union, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import date


# ============================================================================
# COMMON TYPES AND CONSTANTS
# ============================================================================

SeasonType = Literal["Regular Season", "Playoffs", "All Star"]
LocationType = Literal["Home", "Road"]
OutcomeType = Literal["W", "L"]
PerModeType = Literal["Totals", "PerGame", "Per36", "Per48", "Per40"]
EntityType = Literal["player", "team"]
ConferenceType = Literal["East", "West"]

class Examples:
    """Common example values for fields"""
    SEASONS = ["2023-24", "2024-25", "2022-23"]
    PLAYER_NAMES = ["LeBron James", "Stephen Curry", "Giannis Antetokounmpo", "Luka Doncic"]
    PLAYER_IDS = [2544, 201939, 203507, 1629029]
    TEAM_NAMES = ["Lakers", "Warriors", "Celtics", "Nuggets"]
    TEAM_ABBREVIATIONS = ["LAL", "GSW", "BOS", "DEN"]
    TEAM_IDS = [1610612747, 1610612744, 1610612738, 1610612743]
    DATES = ["2024-01-15", "2023-12-25", "2024-03-01"]


# ============================================================================
# TOOL SCHEMA 1: fetch_player_games
# ============================================================================

class FetchPlayerGamesInput(BaseModel):
    """
    Input schema for fetch_player_games tool.

    This tool fetches game-by-game statistics for NBA players with powerful filtering.
    It's the primary tool for getting detailed player performance data.

    Common Use Cases:
        - Get a player's last N games
        - Get all games for a specific season
        - Filter by opponent, location, or outcome
        - Compare performance across date ranges
        - Get playoff vs regular season stats
    """

    season: str = Field(
        ...,
        description=(
            "Season in YYYY-YY format. Examples: '2023-24', '2024-25'. "
            "Supports single season ('2023-24'), range ('2021-22:2023-24'), "
            "or JSON array ('[\"2021-22\", \"2022-23\"]'). "
            "REQUIRED"
        ),
        examples=Examples.SEASONS
    )

    player: Optional[Union[int, str]] = Field(
        None,
        description=(
            "Player identifier - either ID (int) or name (str). "
            "Supports full names ('LeBron James'), first names ('LeBron'), "
            "or nicknames. Fuzzy matching enabled. "
            "Examples: 2544, 'LeBron James', 'Steph Curry'. "
            "Optional - if not provided, fetches all players"
        ),
        examples=Examples.PLAYER_NAMES + Examples.PLAYER_IDS
    )

    team: Optional[Union[int, str]] = Field(
        None,
        description=(
            "Team identifier - ID (int), name (str), or abbreviation. "
            "Examples: 1610612747, 'Lakers', 'LAL'. "
            "Filters games to specific team. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES + Examples.TEAM_ABBREVIATIONS
    )

    date_from: Optional[str] = Field(
        None,
        description=(
            "Start date for date range filter in 'YYYY-MM-DD' format. "
            "Examples: '2024-01-01', '2023-12-25'. "
            "Must be used with date_to for range filtering. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    date_to: Optional[str] = Field(
        None,
        description=(
            "End date for date range filter in 'YYYY-MM-DD' format. "
            "Examples: '2024-01-31', '2024-03-31'. "
            "Must be used with date_from for range filtering. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    location: Optional[LocationType] = Field(
        None,
        description=(
            "Filter by game location. "
            "'Home' = home games only, 'Road' = away games only. "
            "Optional"
        )
    )

    outcome: Optional[OutcomeType] = Field(
        None,
        description=(
            "Filter by game outcome. "
            "'W' = wins only, 'L' = losses only. "
            "Optional"
        )
    )

    last_n_games: Optional[int] = Field(
        None,
        description=(
            "Fetch only the most recent N games. "
            "Examples: 1 (last game), 10 (last 10 games), 20. "
            "Useful for recent performance analysis. "
            "Optional"
        ),
        examples=[1, 5, 10, 20],
        ge=1,
        le=82
    )

    opponent_team: Optional[Union[int, str]] = Field(
        None,
        description=(
            "Filter by opponent team - ID, name, or abbreviation. "
            "Examples: 'Lakers', 'LAL', 1610612747. "
            "Get games against specific opponent. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    season_type: Optional[SeasonType] = Field(
        None,
        description=(
            "Type of season. "
            "'Regular Season' (default), 'Playoffs', or 'All Star'. "
            "Optional"
        )
    )

    per_mode: Optional[PerModeType] = Field(
        None,
        description=(
            "Statistical aggregation mode. "
            "'Totals' (game totals), 'PerGame' (per game averages), "
            "'Per36' (per 36 minutes), 'Per48', 'Per40'. "
            "Default: Totals. "
            "Optional"
        )
    )

    @field_validator('season')
    @classmethod
    def validate_season_format(cls, v: str) -> str:
        """Validate season format"""
        # Single season: "2023-24"
        if len(v) == 7 and v[4] == '-':
            year1, year2 = v.split('-')
            if len(year1) == 4 and len(year2) == 2 and year1.isdigit() and year2.isdigit():
                return v
        # Range: "2021-22:2023-24"
        if ':' in v:
            return v
        # JSON array: '["2021-22", "2022-23"]'
        if v.startswith('[') and v.endswith(']'):
            return v
        raise ValueError(
            f"Invalid season format: {v}. "
            f"Expected 'YYYY-YY' (e.g., '2023-24'), range ('2021-22:2023-24'), "
            f"or JSON array ('[\"2021-22\", \"2022-23\"]')"
        )

    @field_validator('date_from', 'date_to')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format"""
        if v is None:
            return v
        try:
            # Try to parse as YYYY-MM-DD
            parts = v.split('-')
            if len(parts) != 3:
                raise ValueError
            year, month, day = parts
            date(int(year), int(month), int(day))
            return v
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid date format: {v}. Expected 'YYYY-MM-DD' (e.g., '2024-01-15')"
            )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "season": "2023-24",
                    "player": "LeBron James",
                    "last_n_games": 10
                },
                {
                    "season": "2024-25",
                    "player": 201939,
                    "opponent_team": "Lakers",
                    "season_type": "Regular Season"
                },
                {
                    "season": "2023-24",
                    "player": "Giannis",
                    "date_from": "2024-01-01",
                    "date_to": "2024-01-31",
                    "location": "Home"
                }
            ]
        }


class FetchPlayerGamesOutput(BaseModel):
    """
    Output schema for fetch_player_games tool.

    Returns a ResponseEnvelope with player game logs as JSON.
    """

    status: Literal["success", "error", "partial"]
    data: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "List of game logs. Each game is a dict with ~78 columns including: "
            "GAME_ID, GAME_DATE, MATCHUP, WL (win/loss), MIN (minutes), "
            "PTS, REB, AST, FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, "
            "FTM, FTA, FT_PCT, STL, BLK, TOV, PF, PLUS_MINUS, "
            "and enriched metrics like TRUE_SHOOTING_PCT, USAGE_RATE, etc."
        )
    )
    metadata: Dict[str, Any] = Field(
        ...,
        description=(
            "Response metadata including: "
            "version, timestamp, source, cache_status, execution_time_ms"
        )
    )
    errors: Optional[List[Dict[str, Any]]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": [
                    {
                        "GAME_ID": "0022300500",
                        "GAME_DATE": "2024-01-15",
                        "MATCHUP": "LAL vs. GSW",
                        "WL": "W",
                        "MIN": 35.2,
                        "PTS": 28,
                        "REB": 8,
                        "AST": 7,
                        "FG_PCT": 0.526,
                        "TRUE_SHOOTING_PCT": 0.612
                    }
                ],
                "metadata": {
                    "version": "v1",
                    "timestamp": "2025-01-30T12:34:56Z",
                    "source": "historical",
                    "execution_time_ms": 532.1
                }
            }
        }


# ============================================================================
# TOOL SCHEMA 2: get_season_stats
# ============================================================================

class GetSeasonStatsInput(BaseModel):
    """
    Input schema for get_season_stats tool.

    Aggregates season-level statistics for players or teams.
    Perfect for comparing performance across seasons.

    Common Use Cases:
        - Get a player's season averages
        - Compare player performance across multiple seasons
        - Get team season totals
        - Filter player stats by team (for players who changed teams)
    """

    entity_type: EntityType = Field(
        ...,
        description=(
            "Type of entity to fetch stats for. "
            "'player' for player stats, 'team' for team stats. "
            "REQUIRED"
        )
    )

    entity_name: str = Field(
        ...,
        description=(
            "Name of player or team. "
            "For players: full name ('LeBron James'), first name ('LeBron'), or nickname. "
            "For teams: full name ('Los Angeles Lakers'), city ('Lakers'), or abbreviation ('LAL'). "
            "Fuzzy matching enabled. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES + Examples.TEAM_NAMES
    )

    season: str = Field(
        ...,
        description=(
            "Season in YYYY-YY format. Examples: '2023-24', '2024-25'. "
            "REQUIRED"
        ),
        examples=Examples.SEASONS
    )

    team_filter: Optional[str] = Field(
        None,
        description=(
            "Filter player stats by team (only applicable when entity_type='player'). "
            "Useful for players who changed teams mid-season. "
            "Examples: 'Lakers', 'LAL', 'Los Angeles Lakers'. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    @field_validator('season')
    @classmethod
    def validate_season_format(cls, v: str) -> str:
        """Validate season format"""
        if len(v) == 7 and v[4] == '-':
            year1, year2 = v.split('-')
            if len(year1) == 4 and len(year2) == 2 and year1.isdigit() and year2.isdigit():
                return v
        raise ValueError(f"Invalid season format: {v}. Expected 'YYYY-YY' (e.g., '2023-24')")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "entity_type": "player",
                    "entity_name": "LeBron James",
                    "season": "2023-24"
                },
                {
                    "entity_type": "player",
                    "entity_name": "James Harden",
                    "season": "2023-24",
                    "team_filter": "Clippers"
                },
                {
                    "entity_type": "team",
                    "entity_name": "Lakers",
                    "season": "2024-25"
                }
            ]
        }


class GetSeasonStatsOutput(BaseModel):
    """
    Output schema for get_season_stats tool.

    Returns aggregated season statistics.
    """

    status: Literal["success", "error"]
    data: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Season statistics dict with fields including: "
            "GP (games played), W (wins), L (losses), MIN (minutes), "
            "PTS (points), REB (rebounds), AST (assists), STL, BLK, TOV, "
            "FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, FTM, FTA, FT_PCT, "
            "PLUS_MINUS, and calculated averages (PPG, RPG, APG, etc.)"
        )
    )
    metadata: Dict[str, Any]
    errors: Optional[List[Dict[str, Any]]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "SEASON_YEAR": "2023-24",
                    "GP": 82,
                    "W": 55,
                    "L": 27,
                    "PTS": 2057.0,
                    "REB": 587.0,
                    "AST": 662.0,
                    "FG_PCT": 0.518,
                    "FG3_PCT": 0.412,
                    "FT_PCT": 0.772,
                    "PPG": 25.1,
                    "RPG": 7.2,
                    "APG": 8.1
                },
                "metadata": {
                    "version": "v1",
                    "timestamp": "2025-01-30T12:34:56Z",
                    "source": "composed",
                    "execution_time_ms": 421.5
                }
            }
        }


# ============================================================================
# TOOL SCHEMA 3: get_date_range_game_log_or_team_game_log
# ============================================================================

class GetTeamGameLogInput(BaseModel):
    """
    Input schema for get_date_range_game_log_or_team_game_log tool.

    Fetches game-by-game logs for NBA teams.
    Similar to fetch_player_games but for teams.

    Common Use Cases:
        - Get a team's full season schedule and results
        - Filter games by date range
        - Analyze team performance over specific periods
        - Get win/loss patterns
    """

    season: str = Field(
        ...,
        description=(
            "Season in YYYY-YY format. Examples: '2023-24', '2024-25'. "
            "REQUIRED"
        ),
        examples=Examples.SEASONS
    )

    team: Optional[str] = Field(
        None,
        description=(
            "Team identifier - name, abbreviation, or city. "
            "Examples: 'Lakers', 'LAL', 'Los Angeles Lakers'. "
            "Optional - if not provided, fetches all teams"
        ),
        examples=Examples.TEAM_NAMES + Examples.TEAM_ABBREVIATIONS
    )

    date_from: Optional[str] = Field(
        None,
        description=(
            "Start date for filtering in 'YYYY-MM-DD' or 'MM/DD/YYYY' format. "
            "Examples: '2024-01-01', '01/01/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    date_to: Optional[str] = Field(
        None,
        description=(
            "End date for filtering in 'YYYY-MM-DD' or 'MM/DD/YYYY' format. "
            "Examples: '2024-01-31', '01/31/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "season": "2024-25",
                    "team": "Lakers"
                },
                {
                    "season": "2023-24",
                    "team": "Celtics",
                    "date_from": "2023-12-01",
                    "date_to": "2023-12-31"
                }
            ]
        }


class GetTeamGameLogOutput(BaseModel):
    """
    Output schema for get_date_range_game_log_or_team_game_log tool.

    Returns list of team game logs.
    """

    status: Literal["success", "error"]
    data: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "List of team game logs. Each game includes: "
            "GAME_ID, GAME_DATE, MATCHUP, WL, MIN, PTS, FGM, FGA, FG_PCT, "
            "FG3M, FG3A, FG3_PCT, FTM, FTA, FT_PCT, OREB, DREB, REB, "
            "AST, STL, BLK, TOV, PF, PLUS_MINUS"
        )
    )
    metadata: Dict[str, Any]
    errors: Optional[List[Dict[str, Any]]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": [
                    {
                        "GAME_ID": "0022400500",
                        "GAME_DATE": "2025-01-15",
                        "MATCHUP": "LAL vs. GSW",
                        "WL": "W",
                        "PTS": 115,
                        "FG_PCT": 0.489,
                        "REB": 45,
                        "AST": 27
                    }
                ],
                "metadata": {
                    "version": "v1",
                    "timestamp": "2025-01-30T12:34:56Z"
                }
            }
        }


# ============================================================================
# TOOL SCHEMA REGISTRY
# ============================================================================

TOOL_SCHEMAS = {
    "fetch_player_games": {
        "input": FetchPlayerGamesInput,
        "output": FetchPlayerGamesOutput,
        "description": "Fetch game-by-game player statistics with advanced filtering"
    },
    "get_season_stats": {
        "input": GetSeasonStatsInput,
        "output": GetSeasonStatsOutput,
        "description": "Get aggregated season statistics for players or teams"
    },
    "get_date_range_game_log_or_team_game_log": {
        "input": GetTeamGameLogInput,
        "output": GetTeamGameLogOutput,
        "description": "Fetch game-by-game team logs with date filtering"
    },
    # Additional tools will be added here incrementally
}


def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """
    Get the Pydantic schema for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Dict with 'input', 'output', and 'description' schemas

    Raises:
        KeyError: If tool not found in registry
    """
    if tool_name not in TOOL_SCHEMAS:
        available = ", ".join(TOOL_SCHEMAS.keys())
        raise KeyError(
            f"Tool '{tool_name}' not found in schema registry. "
            f"Available tools: {available}"
        )
    return TOOL_SCHEMAS[tool_name]


def list_available_schemas() -> List[str]:
    """
    List all tools with available Pydantic schemas.

    Returns:
        List of tool names
    """
    return list(TOOL_SCHEMAS.keys())
