# -*- coding: utf-8 -*-
"""
NBA MCP Tool Schemas - Extended (Part 2)

This file contains Pydantic schemas for the remaining 32 MCP tools.
Import this alongside tool_schemas.py for complete coverage.

Organization:
- Category 1: Entity Resolution
- Category 2: Player Stats (Advanced)
- Category 3: Team Stats
- Category 4: League Data
- Category 5: Advanced Analytics
- Category 6: Game Data
- Category 7: Contextual
- Category 8: System/Meta
- Category 9: Data Operations
- Category 10: Data Persistence
"""

from typing import Optional, Union, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import date
from .tool_schemas import SeasonType, LocationType, OutcomeType, PerModeType, EntityType, ConferenceType, Examples


# ============================================================================
# CATEGORY 1: ENTITY RESOLUTION
# ============================================================================

class ResolveNbaEntityInput(BaseModel):
    """
    Input schema for resolve_nba_entity tool.

    Universal entity resolver with fuzzy matching for player/team names.
    Perfect for handling ambiguous queries, nicknames, and typos.

    Common Use Cases:
        - Find player by partial name: "LeBron"
        - Disambiguate common names: "Jordan" (Michael vs DeAndre)
        - Fuzzy match typos: "Steph Curry" → "Stephen Curry"
        - Validate team abbreviations: "LAL" → "Los Angeles Lakers"
        - Get alternate names/nicknames
    """

    query: str = Field(
        ...,
        description=(
            "Player or team name to search for. "
            "Supports partial names, nicknames, abbreviations, and fuzzy matching. "
            "Examples: 'LeBron', 'Steph', 'Lakers', 'LAL', 'King James'. "
            "REQUIRED"
        ),
        examples=["LeBron", "Steph Curry", "Lakers", "LAL", "King James", "Giannis"]
    )

    entity_type: Optional[Literal["player", "team"]] = Field(
        None,
        description=(
            "Filter by entity type. "
            "'player' = search players only, 'team' = search teams only. "
            "If None, searches both. "
            "Optional"
        )
    )

    return_suggestions: bool = Field(
        True,
        description=(
            "Return suggestions if no exact match found. "
            "True (default) = show similar names, False = error if no match. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"query": "LeBron"},
                {"query": "Lakers", "entity_type": "team"},
                {"query": "Giannis", "return_suggestions": False}
            ]
        }


class ResolveNbaEntityOutput(BaseModel):
    """Output schema for resolve_nba_entity tool"""

    status: Literal["success", "error"]
    data: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Resolved entity with fields: "
            "entity_type, entity_id, name, confidence (0.0-1.0), "
            "abbreviation (teams only), alternate_names, metadata"
        )
    )
    metadata: Dict[str, Any]
    errors: Optional[List[Dict[str, Any]]] = None


# ============================================================================
# CATEGORY 2: PLAYER STATS (ADVANCED)
# ============================================================================

class GetPlayerCareerInformationInput(BaseModel):
    """
    Input schema for get_player_career_information tool.

    Get complete career statistics and history for an NBA player.

    Common Use Cases:
        - Full career overview
        - Career totals and averages
        - Teams played for
        - Awards and accolades
        - Specific season from career

    Granularity: player/career
    Filters Available: season (optional - for specific season only)
    """

    player_name: str = Field(
        ...,
        description=(
            "Player name. Supports full names, first names, or nicknames. "
            "Fuzzy matching enabled. "
            "Examples: 'LeBron James', 'LeBron', 'King James'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Optional season filter in YYYY-YY format. "
            "If provided, returns career info up to and including this season. "
            "If None, returns complete career. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player_name": "LeBron James"},
                {"player_name": "Stephen Curry", "season": "2023-24"}
            ]
        }


class GetPlayerGameStatsInput(BaseModel):
    """
    Input schema for get_player_game_stats tool.

    Get individual game statistics for a player with flexible filtering.
    Simpler than fetch_player_games - focused on common queries.

    Common Use Cases:
        - "Show me LeBron's last game"
        - "How did Curry perform vs the Lakers?"
        - "Get Giannis stats from January 15th"
        - "Show Jokic's last 10 games"

    Granularity: player/game
    Filters Available: season, last_n_games, opponent, game_date, season_type
    """

    player_name: str = Field(
        ...,
        description=(
            "Player name with fuzzy matching support. "
            "Examples: 'LeBron James', 'LeBron', 'Steph Curry'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    last_n_games: Optional[int] = Field(
        None,
        description=(
            "Get only the most recent N games. "
            "Examples: 1 (last game), 5 (last 5 games), 10. "
            "Useful for recent performance. "
            "Optional"
        ),
        examples=[1, 5, 10],
        ge=1,
        le=82
    )

    opponent: Optional[str] = Field(
        None,
        description=(
            "Filter by opponent team name or abbreviation. "
            "Examples: 'Lakers', 'LAL', 'Boston Celtics'. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    game_date: Optional[str] = Field(
        None,
        description=(
            "Specific game date in YYYY-MM-DD or MM/DD/YYYY format. "
            "Examples: '2024-01-15', '01/15/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    season_type: str = Field(
        "Regular Season",
        description=(
            "Type of season games to include. "
            "'Regular Season' (default), 'Playoffs', or 'All Star'. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player_name": "LeBron James", "last_n_games": 1},
                {"player_name": "Stephen Curry", "opponent": "Lakers"},
                {"player_name": "Giannis", "game_date": "2024-01-15"}
            ]
        }


class GetPlayerAdvancedStatsInput(BaseModel):
    """
    Input schema for get_player_advanced_stats tool.

    Get advanced efficiency metrics for a player's season.

    Advanced Metrics Included:
        - True Shooting % (TS%) - Shooting efficiency with 3PT and FT value
        - Effective Field Goal % (eFG%) - FG% adjusted for 3-pointers
        - Usage Rate (USG%) - Percentage of team plays used
        - Player Impact Estimate (PIE) - Overall impact metric
        - Offensive/Defensive/Net Rating - Per 100 possession metrics
        - Assist %, Rebound %, Turnover % - Percentage stats

    Common Use Cases:
        - "What's Curry's true shooting percentage?"
        - "Show me Giannis's usage rate"
        - "Get Jokic's offensive rating"

    Granularity: player/season
    Filters Available: season
    """

    player_name: str = Field(
        ...,
        description=(
            "Player name with fuzzy matching. "
            "Examples: 'LeBron James', 'Steph Curry', 'Giannis'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player_name": "Stephen Curry"},
                {"player_name": "Giannis Antetokounmpo", "season": "2023-24"}
            ]
        }


class GetPlayerPerformanceSplitsInput(BaseModel):
    """
    Input schema for get_player_performance_splits tool.

    Comprehensive performance analysis with splits and trends.

    Analysis Includes:
        - Season averages (baseline)
        - Last N games performance
        - Home vs Away splits
        - Win vs Loss splits
        - Trend detection (hot/cold streaks)
        - Per-100 possession normalized stats

    Common Use Cases:
        - "How has LeBron been playing lately?"
        - "Show Curry's home vs away performance"
        - "Is Giannis on a hot streak?"

    Granularity: player/season with splits
    Filters Available: season, last_n_games
    """

    player_name: str = Field(
        ...,
        description=(
            "Player name with fuzzy matching. "
            "Examples: 'LeBron James', 'Stephen Curry'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    last_n_games: int = Field(
        10,
        description=(
            "Number of recent games to analyze for trends. "
            "Default: 10. Examples: 5, 10, 15, 20. "
            "Optional"
        ),
        ge=1,
        le=82
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player_name": "LeBron James"},
                {"player_name": "Stephen Curry", "last_n_games": 15}
            ]
        }


class GetPlayerHeadToHeadInput(BaseModel):
    """
    Input schema for get_player_head_to_head tool.

    Compare two players in games where BOTH played.
    Shows head-to-head matchup statistics, not season averages.

    Common Use Cases:
        - "LeBron vs Durant head to head"
        - "Curry vs Lillard matchups this season"
        - "Compare Giannis and Embiid in their matchups"

    Granularity: player/game (matchup filtered)
    Filters Available: season
    """

    player1_name: str = Field(
        ...,
        description=(
            "First player name. "
            "Examples: 'LeBron James', 'Kevin Durant'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    player2_name: str = Field(
        ...,
        description=(
            "Second player name. "
            "Examples: 'Stephen Curry', 'Damian Lillard'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player1_name": "LeBron James", "player2_name": "Kevin Durant"},
                {"player1_name": "Stephen Curry", "player2_name": "Damian Lillard", "season": "2023-24"}
            ]
        }


# ============================================================================
# CATEGORY 3: TEAM STATS
# ============================================================================

class GetTeamStandingsInput(BaseModel):
    """
    Input schema for get_team_standings tool.

    Get current NBA standings with conference/division rankings.

    Standings Include:
        - Win-Loss records and percentages
        - Conference rank
        - Division rank
        - Games Behind (GB) conference leader
        - Home/Away records
        - Last 10 games record
        - Current streak (W/L)

    Common Use Cases:
        - "Show me Eastern Conference standings"
        - "What's the Western Conference playoff race?"
        - "Where do the Lakers rank?"

    Granularity: team/season (standings view)
    Filters Available: season, conference
    """

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    conference: Optional[ConferenceType] = Field(
        None,
        description=(
            "Filter by conference. "
            "'East' = Eastern Conference only, 'West' = Western Conference only. "
            "If None, returns both conferences. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {},
                {"season": "2023-24", "conference": "East"},
                {"conference": "West"}
            ]
        }


class GetTeamAdvancedStatsInput(BaseModel):
    """
    Input schema for get_team_advanced_stats tool.

    Get advanced efficiency metrics for a team.

    Advanced Metrics Include:
        - Offensive Rating (OffRtg) - Points per 100 possessions
        - Defensive Rating (DefRtg) - Points allowed per 100 possessions
        - Net Rating (NetRtg) - Point differential per 100 possessions
        - Pace - Possessions per 48 minutes
        - True Shooting % and Effective FG %
        - Four Factors (eFG%, TOV%, OREB%, FTA Rate) - Offense and Defense

    Common Use Cases:
        - "What's the Lakers' offensive rating?"
        - "Show me Warriors defense stats"
        - "Compare Celtics pace to league average"

    Granularity: team/season
    Filters Available: season
    """

    team_name: str = Field(
        ...,
        description=(
            "Team name, city, or abbreviation. "
            "Examples: 'Lakers', 'Los Angeles Lakers', 'LAL'. "
            "Fuzzy matching enabled. "
            "REQUIRED"
        ),
        examples=Examples.TEAM_NAMES + Examples.TEAM_ABBREVIATIONS
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"team_name": "Lakers"},
                {"team_name": "GSW", "season": "2023-24"}
            ]
        }


# ============================================================================
# CATEGORY 4: LEAGUE DATA
# ============================================================================

class GetLeagueLeadersInfoInput(BaseModel):
    """
    Input schema for get_league_leaders_info tool.

    Get top performers in any statistical category.

    Supported Stat Categories:
        - Scoring: PTS, FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, FTM, FTA, FT_PCT
        - Rebounding: REB, OREB, DREB
        - Playmaking: AST, AST_TO
        - Defense: STL, BLK
        - Other: TOV, PF, PLUS_MINUS

    Common Use Cases:
        - "Who leads the NBA in scoring?"
        - "Top 10 rebounders"
        - "Best three-point shooters"
        - "Highest assist-to-turnover ratio"

    Granularity: player/season (league-wide aggregation)
    Filters Available: stat_category, season, per_mode, season_type, limit, min_games_played, conference, team
    """

    stat_category: str = Field(
        ...,
        description=(
            "Statistical category to rank by. "
            "Examples: 'PTS' (points), 'AST' (assists), 'REB' (rebounds), "
            "'FG_PCT' (field goal %), 'FG3M' (3-pointers made), 'STL' (steals). "
            "REQUIRED"
        ),
        examples=["PTS", "AST", "REB", "FG_PCT", "FG3M", "STL", "BLK"]
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    per_mode: str = Field(
        "PerGame",
        description=(
            "Statistical aggregation mode. "
            "'Totals' (season totals), 'PerGame' (per game averages - default), "
            "'Per48' (per 48 minutes), 'Per36', 'Per40'. "
            "Optional"
        )
    )

    season_type_all_star: str = Field(
        "Regular Season",
        description=(
            "Season type to include. "
            "'Regular Season' (default), 'Playoffs', 'All Star'. "
            "Optional"
        )
    )

    limit: int = Field(
        10,
        description=(
            "Maximum number of leaders to return. "
            "Default: 10. Examples: 5, 10, 20, 50. "
            "Optional"
        ),
        ge=1,
        le=100
    )

    min_games_played: Optional[int] = Field(
        None,
        description=(
            "Minimum games played requirement. "
            "Filter out players with too few games. "
            "Examples: 20, 40, 58 (70% of season). "
            "Optional"
        ),
        ge=1,
        le=82
    )

    conference: Optional[str] = Field(
        None,
        description=(
            "Filter by conference. 'East' or 'West'. "
            "Optional"
        )
    )

    team: Optional[str] = Field(
        None,
        description=(
            "Filter by specific team. "
            "Examples: 'Lakers', 'LAL'. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"stat_category": "PTS"},
                {"stat_category": "AST", "limit": 20},
                {"stat_category": "FG3_PCT", "min_games_played": 40},
                {"stat_category": "REB", "conference": "West"}
            ]
        }


class GetLiveScoresInput(BaseModel):
    """
    Input schema for get_live_scores tool.

    Get live or historical NBA scores for a specific date.

    Returns:
        - Game matchups
        - Current/Final scores
        - Game status (scheduled, in progress, final)
        - Quarter/time remaining (if live)

    Common Use Cases:
        - "What games are on today?"
        - "Show me yesterday's scores"
        - "Games on Christmas Day"

    Granularity: game/date
    Filters Available: target_date
    """

    target_date: Optional[str] = Field(
        None,
        description=(
            "Date in YYYY-MM-DD format. "
            "If None, defaults to today. "
            "Examples: '2024-01-15', '2024-12-25'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {},
                {"target_date": "2024-12-25"}
            ]
        }


class GetNbaAwardsInput(BaseModel):
    """
    Input schema for get_nba_awards tool.

    Get NBA awards data - historical winners or player-specific awards.

    Award Types:
        Individual:
        - mvp: Most Valuable Player
        - finals_mvp: Finals MVP
        - dpoy: Defensive Player of the Year
        - roy: Rookie of the Year
        - smoy: Sixth Man of the Year
        - mip: Most Improved Player
        - coy: Coach of the Year

        Team Selections (5 players each):
        - all_nba_first/second/third: All-NBA Teams
        - all_defensive_first/second: All-Defensive Teams
        - all_rookie_first/second: All-Rookie Teams

    Query Modes:
        1. Historical winners: award_type + last_n
        2. Season winners: award_type + season
        3. Player awards: player_name
        4. Player + award filter: player_name + award_type

    Common Use Cases:
        - "Who won MVP last 10 years?"
        - "Show LeBron's awards"
        - "2023-24 All-NBA First Team"

    Granularity: league/season (awards)
    Filters Available: award_type, player_name, season, last_n
    """

    award_type: Optional[str] = Field(
        None,
        description=(
            "Award type to filter by. "
            "Individual: 'mvp', 'finals_mvp', 'dpoy', 'roy', 'smoy', 'mip', 'coy'. "
            "Team selections: 'all_nba_first', 'all_defensive_first', etc. "
            "Optional"
        ),
        examples=["mvp", "dpoy", "roy", "all_nba_first"]
    )

    player_name: Optional[str] = Field(
        None,
        description=(
            "Get all awards for specific player. "
            "Uses live API data for complete career awards. "
            "Examples: 'LeBron James', 'Stephen Curry'. "
            "Optional"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Filter by specific season. "
            "Format: YYYY-YY. Examples: '2023-24', '2022-23'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    last_n: Optional[int] = Field(
        None,
        description=(
            "Get last N award winners (for historical queries). "
            "Examples: 5, 10, 20. "
            "Optional"
        ),
        ge=1,
        le=50
    )

    format: str = Field(
        "text",
        description=(
            "Output format. 'text' (default) or 'json'. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"award_type": "mvp", "last_n": 10},
                {"player_name": "LeBron James"},
                {"award_type": "roy", "season": "2023-24"}
            ]
        }


class GetNbaScheduleInput(BaseModel):
    """
    Input schema for get_nba_schedule tool.

    Get NBA schedule from official NBA CDN with automatic current season detection.

    Data Source:
        https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json
        - Official NBA endpoint (same as NBA.com)
        - Auto-updates for schedule changes, postponements, flex scheduling
        - Pre-published for future seasons
        - Real-time updates during season

    Schedule Includes:
        - Game IDs, dates/times (UTC and local)
        - Teams (home/away with IDs, names, abbreviations)
        - Venue info (arena, city, state)
        - Game status (Scheduled, In Progress, Final)
        - Scores (for completed games)
        - National TV broadcasters
        - Playoff series info (if applicable)

    Auto-Detection:
        - If month >= August: Uses next season (e.g., Oct 2025 → 2025-26)
        - Otherwise: Uses current season (e.g., Jul 2025 → 2024-25)
        - Automatically rolls over to new season each year

    Season Stages:
        - Preseason (stage_id=1): Exhibition games in October
        - Regular Season (stage_id=2): 82-game season (Oct-Apr)
        - Playoffs (stage_id=4): Postseason (Apr-Jun)

    Common Use Cases:
        - "What's the schedule for this season?"
        - "Show me Lakers games in December"
        - "When are the playoffs?"
        - "Get 2025-26 regular season schedule"

    Granularity: game/date (individual games)
    Filters Available: season, season_stage, team, date_from, date_to
    """

    season: Optional[str] = Field(
        None,
        description=(
            "Season identifier. Defaults to current season (auto-detected). "
            "Format: 'YYYY-YY'. Examples: '2025-26', '2024-25'. "
            "Auto-detection: Aug+ → next season, before Aug → current season. "
            "Optional"
        ),
        examples=["2025-26", "2024-25", "2026-27"]
    )

    season_stage: Optional[str] = Field(
        None,
        description=(
            "Filter by season stage. "
            "Values: 'preseason', 'regular', 'playoffs'. "
            "Aliases: 'pre', 'regular_season', 'post'. "
            "Optional"
        ),
        examples=["preseason", "regular", "playoffs", "pre", "post"]
    )

    team: Optional[str] = Field(
        None,
        description=(
            "Filter by team abbreviation. "
            "Examples: 'LAL', 'BOS', 'GSW'. "
            "Case-insensitive. "
            "Optional"
        ),
        examples=Examples.TEAM_ABBREVIATIONS
    )

    date_from: Optional[str] = Field(
        None,
        description=(
            "Start date filter (inclusive). "
            "Format: YYYY-MM-DD. Examples: '2025-12-01', '2026-01-15'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    date_to: Optional[str] = Field(
        None,
        description=(
            "End date filter (inclusive). "
            "Format: YYYY-MM-DD. Examples: '2025-12-31', '2026-01-31'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    format: str = Field(
        "markdown",
        description=(
            "Output format. 'markdown' (default) for human-readable table, 'json' for structured data. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {},  # Current season, all stages
                {"season": "2025-26", "season_stage": "regular"},
                {"team": "LAL"},
                {"season_stage": "playoffs"},
                {"date_from": "2025-12-01", "date_to": "2025-12-31"},
                {"season": "2025-26", "season_stage": "regular", "team": "LAL", "date_from": "2025-12-01"}
            ]
        }

    @field_validator("season")
    @classmethod
    def validate_season(cls, v: Optional[str]) -> Optional[str]:
        """Validate season format if provided"""
        if v is not None and not isinstance(v, str):
            raise ValueError(f"Season must be a string, got {type(v)}")
        if v is not None and "-" in v:
            parts = v.split("-")
            if len(parts) != 2:
                raise ValueError(f"Invalid season format: {v}. Expected 'YYYY-YY' (e.g., '2025-26')")
        return v

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format if provided"""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError(f"Date must be a string, got {type(v)}")
        # Basic format check (YYYY-MM-DD)
        if len(v) == 10 and v[4] == '-' and v[7] == '-':
            try:
                year, month, day = int(v[:4]), int(v[5:7]), int(v[8:10])
                if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
                    raise ValueError(f"Invalid date: {v}")
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD (e.g., '2025-12-01')")
        else:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD (e.g., '2025-12-01')")
        return v


# ============================================================================
# CATEGORY 5: ADVANCED ANALYTICS
# ============================================================================

class GetAdvancedMetricsInput(BaseModel):
    """
    Input schema for get_advanced_metrics tool.

    Calculate sophisticated basketball metrics beyond basic box score.

    Advanced Metrics Provided:
        - Game Score (Total, Per Game, Per 36 minutes)
        - True Shooting % (TS%)
        - Effective Field Goal % (eFG%)
        - Usage Rate
        - Offensive Win Shares
        - Defensive Win Shares
        - Win Shares (total)
        - Win Shares per 48 minutes
        - Estimated Wins Added (EWA)

    Common Use Cases:
        - "Calculate LeBron's win shares"
        - "What's Jokic's game score?"
        - "Show me Curry's true shooting percentage"

    Granularity: player/season
    Filters Available: season, metrics (list to filter specific metrics)
    """

    player_name: str = Field(
        ...,
        description=(
            "Player name with fuzzy matching. "
            "Examples: 'LeBron James', 'Nikola Jokic'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: str = Field(
        ...,
        description=(
            "Season in YYYY-YY format. "
            "Examples: '2023-24', '2024-25'. "
            "REQUIRED"
        ),
        examples=Examples.SEASONS
    )

    metrics: Optional[List[str]] = Field(
        None,
        description=(
            "Optional list of specific metrics to return. "
            "If None, returns all metrics. "
            "Available: GAME_SCORE_TOTAL, GAME_SCORE_PER_GAME, GAME_SCORE_PER_36, "
            "TRUE_SHOOTING_PCT, EFFECTIVE_FG_PCT, USAGE_RATE, "
            "OFFENSIVE_WIN_SHARES, DEFENSIVE_WIN_SHARES, WIN_SHARES, "
            "WIN_SHARES_PER_48, EWA. "
            "Optional"
        ),
        examples=[["WIN_SHARES", "TRUE_SHOOTING_PCT"], ["GAME_SCORE_PER_36"]]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player_name": "LeBron James", "season": "2023-24"},
                {"player_name": "Nikola Jokic", "season": "2023-24", "metrics": ["WIN_SHARES", "GAME_SCORE_PER_36"]}
            ]
        }


class ComparePlayersInput(BaseModel):
    """
    Input schema for compare_players tool.

    Side-by-side player comparison with normalized statistics.

    Normalization Modes:
        - raw: Season totals (no normalization)
        - per_game: Per-game averages
        - per_75_poss: Per 75 possessions (DEFAULT - fairest for comparing different minutes)
        - era_adjusted: Adjust for pace and scoring environment differences

    Common Use Cases:
        - "Compare LeBron James and Kevin Durant"
        - "LeBron vs Jordan this season"
        - "Show Curry vs Lillard per 75 possessions"

    Granularity: player/season (comparison)
    Filters Available: season, normalization mode
    """

    player1_name: str = Field(
        ...,
        description=(
            "First player name. "
            "Examples: 'LeBron James', 'Kevin Durant'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    player2_name: str = Field(
        ...,
        description=(
            "Second player name. "
            "Examples: 'Stephen Curry', 'Damian Lillard'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    normalization: str = Field(
        "per_75_poss",
        description=(
            "Statistical normalization mode. "
            "'raw' = season totals, 'per_game' = per-game averages, "
            "'per_75_poss' or 'per_75' = per 75 possessions (DEFAULT - fairest), "
            "'era_adjusted' = adjust for pace/era. "
            "Optional"
        ),
        examples=["per_75_poss", "per_game", "raw", "era_adjusted"]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player1_name": "LeBron James", "player2_name": "Kevin Durant"},
                {"player1_name": "Stephen Curry", "player2_name": "Damian Lillard", "normalization": "per_game"}
            ]
        }


class ComparePlayersEraAdjustedInput(BaseModel):
    """
    Input schema for compare_players_era_adjusted tool.

    Compare players across different eras with pace and scoring adjustments.

    Adjustments Applied:
        - League-wide pace differences (possessions per game)
        - Scoring environment changes (points per game)
        - Different era playing styles

    Common Use Cases:
        - "Compare Michael Jordan 1995-96 to LeBron James 2012-13"
        - "Kobe Bryant 2005-06 vs Luka Doncic 2023-24"
        - "Compare Magic Johnson's prime to Luka's current season"

    Granularity: player/season (cross-era)
    Filters Available: season1, season2 (different eras required)
    """

    player1_name: str = Field(
        ...,
        description=(
            "First player name. "
            "Examples: 'Michael Jordan', 'Kobe Bryant'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES + ["Michael Jordan", "Kobe Bryant", "Magic Johnson"]
    )

    player2_name: str = Field(
        ...,
        description=(
            "Second player name. "
            "Examples: 'LeBron James', 'Luka Doncic'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES
    )

    season1: str = Field(
        ...,
        description=(
            "Season for player 1 in YYYY-YY format. "
            "Examples: '1995-96', '2005-06'. "
            "REQUIRED"
        ),
        examples=["1995-96", "2005-06", "1991-92"]
    )

    season2: str = Field(
        ...,
        description=(
            "Season for player 2 in YYYY-YY format. "
            "Examples: '2012-13', '2023-24'. "
            "REQUIRED"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"player1_name": "Michael Jordan", "player2_name": "LeBron James", "season1": "1995-96", "season2": "2012-13"},
                {"player1_name": "Kobe Bryant", "player2_name": "Luka Doncic", "season1": "2005-06", "season2": "2023-24"}
            ]
        }


# ============================================================================
# CATEGORY 6: GAME DATA
# ============================================================================

class PlayByPlayInput(BaseModel):
    """
    Input schema for play_by_play tool.

    Get play-by-play events for NBA games with optional lineup tracking.

    Returns:
        - Event-by-event game log
        - Scores after each play
        - Play descriptions
        - Time and period
        - Optional: Current 5-player lineups

    Common Use Cases:
        - "Show me today's play-by-play"
        - "Get Lakers game events from last night"
        - "4th quarter play-by-play with lineups"

    Granularity: game/event
    Filters Available: game_date, team, period range (start_period, end_period),
                       start_clock, recent_n, max_lines, include_lineups
    """

    game_date: Optional[str] = Field(
        None,
        description=(
            "Game date in YYYY-MM-DD format. "
            "If None, defaults to today. "
            "Examples: '2024-01-15', '2024-12-25'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    team: Optional[str] = Field(
        None,
        description=(
            "Team name or abbreviation to filter games. "
            "If None with game_date, returns all games on that date. "
            "Examples: 'Lakers', 'LAL'. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    start_period: int = Field(
        1,
        description=(
            "Starting period (quarter) to show. "
            "1-4 for regulation, 5+ for overtime. "
            "Default: 1. "
            "Optional"
        ),
        ge=1,
        le=10
    )

    end_period: int = Field(
        4,
        description=(
            "Ending period (quarter) to show. "
            "1-4 for regulation, 5+ for overtime. "
            "Default: 4. "
            "Optional"
        ),
        ge=1,
        le=10
    )

    start_clock: Optional[str] = Field(
        None,
        description=(
            "Start time within period in MM:SS format. "
            "Examples: '05:00', '02:30'. "
            "Filter plays starting from this time. "
            "Optional"
        ),
        examples=["05:00", "02:30", "00:30"]
    )

    recent_n: int = Field(
        5,
        description=(
            "Number of recent plays to show in summary. "
            "Default: 5. "
            "Optional"
        ),
        ge=1,
        le=50
    )

    max_lines: int = Field(
        200,
        description=(
            "Maximum lines of output to return. "
            "Prevents extremely large responses. "
            "Default: 200. "
            "Optional"
        ),
        ge=10,
        le=1000
    )

    include_lineups: bool = Field(
        False,
        description=(
            "Include current 5-player lineups for each event. "
            "Adds lineup columns: CURRENT_LINEUP_HOME, CURRENT_LINEUP_AWAY, "
            "LINEUP_ID_HOME, LINEUP_ID_AWAY. "
            "Default: False. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {},
                {"game_date": "2024-01-15", "team": "Lakers"},
                {"team": "Warriors", "start_period": 4, "include_lineups": True}
            ]
        }


class GetBoxScoreInput(BaseModel):
    """
    Input schema for get_box_score tool.

    Get full box score for a specific game with quarter-by-quarter breakdowns.

    Returns:
        - Quarter-by-quarter scores (Q1, Q2, Q3, Q4, OT)
        - Player statistics for both teams
        - Team totals
        - Starters vs bench breakdowns

    Lookup Methods:
        1. By game ID: game_id (10-digit NBA ID)
        2. By team + date: team + game_date

    Common Use Cases:
        - "Get box score for game ID 0022300500"
        - "Show Lakers box score from last night"
        - "Box score for Warriors game on 2024-01-15"

    Granularity: game (complete box score)
    Filters Available: game_id OR (team + game_date)
    """

    game_id: Optional[str] = Field(
        None,
        description=(
            "10-digit NBA game ID. "
            "Examples: '0022300500', '0042300401'. "
            "Format: 00[2=regular season|4=playoffs]YYSSGGG. "
            "If provided, this takes precedence over team + game_date. "
            "Optional"
        ),
        examples=["0022300500", "0042300401"]
    )

    team: Optional[str] = Field(
        None,
        description=(
            "Team name or abbreviation for date lookup. "
            "Used with game_date to find game. "
            "Examples: 'Lakers', 'LAL'. "
            "Optional"
        ),
        examples=Examples.TEAM_NAMES
    )

    game_date: Optional[str] = Field(
        None,
        description=(
            "Game date in YYYY-MM-DD or MM/DD/YYYY format. "
            "Used with team to find game. "
            "Examples: '2024-01-15', '01/15/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"game_id": "0022300500"},
                {"team": "Lakers", "game_date": "2024-01-15"}
            ]
        }


class GetShotChartInput(BaseModel):
    """
    Input schema for get_shot_chart tool.

    Get shot location data with make/miss for players or teams.

    Granularity Options:
        - raw: Individual shot coordinates (X, Y, make/miss)
        - hexbin: Aggregated 50x50 grid with FG% per zone
        - both: Both raw and hexbin data (DEFAULT)
        - summary: Zone summary (paint, mid-range, three-point stats)

    Common Use Cases:
        - "Show me Curry's shot chart"
        - "Warriors shooting zones this season"
        - "LeBron's shot locations vs Lakers"

    Granularity: player/game or team/game (shot locations)
    Filters Available: entity_type, season, season_type, date_from, date_to, granularity
    """

    entity_name: str = Field(
        ...,
        description=(
            "Player or team name. "
            "Examples: 'Stephen Curry', 'Lakers', 'Joel Embiid'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES + Examples.TEAM_NAMES
    )

    entity_type: EntityType = Field(
        "player",
        description=(
            "Entity type: 'player' (default) or 'team'. "
            "Optional"
        )
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    season_type: SeasonType = Field(
        "Regular Season",
        description=(
            "Season type: 'Regular Season' (default) or 'Playoffs'. "
            "Optional"
        )
    )

    date_from: Optional[str] = Field(
        None,
        description=(
            "Start date in YYYY-MM-DD or MM/DD/YYYY format. "
            "Filter shots from this date forward. "
            "Examples: '2024-01-01', '01/01/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    date_to: Optional[str] = Field(
        None,
        description=(
            "End date in YYYY-MM-DD or MM/DD/YYYY format. "
            "Filter shots up to this date. "
            "Examples: '2024-01-31', '01/31/2024'. "
            "Optional"
        ),
        examples=Examples.DATES
    )

    granularity: Literal["raw", "hexbin", "both", "summary"] = Field(
        "both",
        description=(
            "Output format: "
            "'raw' = individual shot coordinates (X, Y, make/miss), "
            "'hexbin' = 50x50 grid aggregation with FG% per zone, "
            "'both' = both raw and hexbin (DEFAULT), "
            "'summary' = zone summary (paint, mid-range, three-point). "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"entity_name": "Stephen Curry"},
                {"entity_name": "Lakers", "entity_type": "team", "granularity": "hexbin"},
                {"entity_name": "Joel Embiid", "date_from": "2024-01-01", "date_to": "2024-01-31"}
            ]
        }


class GetClutchStatsInput(BaseModel):
    """
    Input schema for get_clutch_stats tool.

    Get clutch time statistics (final 5 minutes, score within 5 points).

    Clutch Time Definition:
        - Final 5 minutes of 4th quarter or overtime
        - Score differential of 5 points or less

    Returns:
        - Games played in clutch situations
        - Clutch time win-loss record
        - Points, assists, rebounds in clutch
        - Shooting percentages in clutch
        - Clutch efficiency metrics

    Common Use Cases:
        - "Show me LeBron's clutch stats"
        - "How do the Lakers perform in clutch time?"
        - "Get Curry's clutch shooting"

    Granularity: player/season or team/season (clutch filtered)
    Filters Available: entity_type, season, per_mode
    """

    entity_name: str = Field(
        ...,
        description=(
            "Player or team name with fuzzy matching. "
            "Examples: 'LeBron James', 'Lakers', 'Damian Lillard'. "
            "REQUIRED"
        ),
        examples=Examples.PLAYER_NAMES + Examples.TEAM_NAMES
    )

    entity_type: EntityType = Field(
        "player",
        description=(
            "Entity type: 'player' (default) or 'team'. "
            "Optional"
        )
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    per_mode: PerModeType = Field(
        "PerGame",
        description=(
            "Statistical mode: 'PerGame' (default) or 'Totals'. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"entity_name": "LeBron James"},
                {"entity_name": "Lakers", "entity_type": "team"},
                {"entity_name": "Stephen Curry", "per_mode": "Totals"}
            ]
        }


class GetGameContextInput(BaseModel):
    """
    Input schema for get_game_context tool.

    Get comprehensive matchup analysis between two teams.

    Context Includes:
        - Team standings (conference/division rank, records)
        - Advanced statistics (OffRtg, DefRtg, NetRtg, Pace)
        - Recent form (last 10 games, streaks)
        - Head-to-head record (season series)
        - Auto-generated narrative with storylines

    Perfect For:
        - Game previews
        - Pre-game analysis
        - Matchup context

    Common Use Cases:
        - "Lakers vs Warriors matchup"
        - "Celtics vs Heat game context"
        - "Give me context for tonight's Nuggets game"

    Granularity: team/season (composite view)
    Filters Available: season
    """

    team1_name: str = Field(
        ...,
        description=(
            "First team name or abbreviation. "
            "Examples: 'Lakers', 'Los Angeles Lakers', 'LAL'. "
            "REQUIRED"
        ),
        examples=Examples.TEAM_NAMES
    )

    team2_name: str = Field(
        ...,
        description=(
            "Second team name or abbreviation. "
            "Examples: 'Warriors', 'Golden State Warriors', 'GSW'. "
            "REQUIRED"
        ),
        examples=Examples.TEAM_NAMES
    )

    season: Optional[str] = Field(
        None,
        description=(
            "Season in YYYY-YY format. Defaults to current season. "
            "Examples: '2023-24', '2024-25'. "
            "Optional"
        ),
        examples=Examples.SEASONS
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"team1_name": "Lakers", "team2_name": "Warriors"},
                {"team1_name": "Boston Celtics", "team2_name": "Miami Heat", "season": "2023-24"}
            ]
        }


# ============================================================================
# CATEGORY 7: CONTEXTUAL/COMPOSITE
# ============================================================================

class AnswerNbaQuestionInput(BaseModel):
    """
    Input schema for answer_nba_question tool.

    Natural language query processing - routes to appropriate tools automatically.

    This tool understands natural language and orchestrates the right NBA API calls.
    Perfect for conversational queries where you don't know which specific tool to use.

    Supported Question Types:
        1. Leaders: "Who leads the NBA in assists?", "Top 10 scorers"
        2. Player Comparison: "Compare LeBron James and Kevin Durant"
        3. Team Comparison: "Lakers vs Celtics", "Warriors vs Bucks tonight"
        4. Player Stats: "Show me Giannis stats", "How is Luka doing?"
        5. Team Stats: "What is the Warriors offensive rating?", "Celtics defense"
        6. Standings: "Eastern Conference standings", "Western Conference playoff race"
        7. Game Context: "Lakers vs Celtics tonight", "What games are on today?"

    Common Use Cases:
        - "Who leads the NBA in assists?"
        - "Compare LeBron James and Kevin Durant"
        - "Show me Giannis stats from 2023-24"
        - "Eastern Conference standings"

    Granularity: Dynamic (routes to appropriate tools)
    Filters Available: None (determined from question)
    """

    question: str = Field(
        ...,
        description=(
            "Natural language question about NBA data. "
            "The tool will parse the question and route to appropriate endpoints. "
            "Examples: 'Who leads the NBA in assists?', "
            "'Compare LeBron and Durant', 'Show me Giannis stats'. "
            "REQUIRED"
        ),
        examples=[
            "Who leads the NBA in assists?",
            "Compare LeBron James and Kevin Durant",
            "Show me Giannis stats from 2023-24",
            "Eastern Conference standings",
            "Lakers vs Warriors tonight"
        ]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"question": "Who leads the NBA in assists?"},
                {"question": "Compare LeBron James and Kevin Durant"},
                {"question": "Show me Giannis stats from 2023-24"}
            ]
        }


class GetMetricsInfoInput(BaseModel):
    """
    Input schema for get_metrics_info tool.

    Get server health, performance metrics, and observability information.

    Returns:
        - Server uptime
        - Cache hit rate and size
        - Quota usage and remaining
        - Recent request statistics
        - Metrics endpoint information

    Common Use Cases:
        - "Show me server metrics"
        - "Check cache performance"
        - "How much quota do I have left?"

    Granularity: N/A (system)
    Filters Available: None
    """

    # This tool takes no parameters
    class Config:
        json_schema_extra = {
            "examples": [{}]
        }


# ============================================================================
# CATEGORY 8: SYSTEM/META TOOLS
# ============================================================================

class ListEndpointsInput(BaseModel):
    """
    Input schema for list_endpoints tool.

    List available NBA API endpoints with schemas and capabilities.

    Returns:
        - Endpoint names
        - Parameter requirements
        - Primary keys
        - Sample usage
        - Data categories

    Common Use Cases:
        - "What player stats endpoints are available?"
        - "Show me all endpoints"
        - "List team statistics endpoints"

    Granularity: N/A (meta)
    Filters Available: category (filter by endpoint category)
    """

    category: Optional[str] = Field(
        None,
        description=(
            "Optional filter by category. "
            "Categories: 'player_stats', 'team_stats', 'game_data', "
            "'league_data', 'advanced_analytics'. "
            "If None, returns all endpoints. "
            "Optional"
        ),
        examples=["player_stats", "team_stats", "game_data"]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {},
                {"category": "player_stats"}
            ]
        }


class CatalogInput(BaseModel):
    """
    Input schema for catalog tool.

    Get complete data catalog with schema information and join relationships.

    Returns:
        - Endpoint schemas with parameters and columns
        - Primary and foreign key relationships
        - Join recommendations with examples
        - Complete join workflow examples

    Perfect For:
        - Understanding available data
        - Planning multi-source queries
        - Learning how to join datasets

    Common Use Cases:
        - "Show me the complete data catalog"
        - "What data is available?"
        - "How do I join player and team data?"

    Granularity: N/A (meta)
    Filters Available: None
    """

    # This tool takes no parameters
    class Config:
        json_schema_extra = {
            "examples": [{}]
        }


class DiscoverNbaEndpointsInput(BaseModel):
    """
    Input schema for discover_nba_endpoints tool.

    Discover all available NBA API endpoints with capabilities.

    Returns:
        - Endpoint names organized by category
        - Parameter schemas
        - Capabilities (date ranges, seasons, pagination)
        - Typical dataset sizes
        - Recommended use cases

    Common Use Cases:
        - "What endpoints are available?"
        - "Show me all NBA API capabilities"
        - "Discover available data sources"

    Granularity: N/A (meta)
    Filters Available: None
    """

    # This tool takes no parameters
    class Config:
        json_schema_extra = {
            "examples": [{}]
        }


class ConfigureLimitsInput(BaseModel):
    """
    Input schema for configure_limits tool.

    Configure dataset size limits for fetch operations.

    Controls maximum size of datasets that can be fetched to prevent
    excessive memory usage and unexpected large downloads.

    Default limit: 1024 MB (1 GB)
    Set to -1 for unlimited (use with caution)

    Common Use Cases:
        - "Show current size limits"
        - "Increase fetch limit to 2 GB"
        - "What's my current fetch limit?"

    Granularity: N/A (system config)
    Filters Available: None
    """

    max_fetch_mb: Optional[float] = Field(
        None,
        description=(
            "New maximum fetch size in MB. "
            "-1 for unlimited (use with caution). "
            "If None with show_current=False, shows current limit without changing. "
            "Examples: 512, 1024, 2048, -1. "
            "Optional"
        ),
        examples=[512, 1024, 2048, -1]
    )

    show_current: bool = Field(
        False,
        description=(
            "Just show current limits without changing. "
            "True = show only, False = update if max_fetch_mb provided. "
            "Default: False. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"show_current": True},
                {"max_fetch_mb": 2048},
                {"max_fetch_mb": -1}
            ]
        }


class InspectEndpointInput(BaseModel):
    """
    Input schema for inspect_endpoint tool.

    Inspect an NBA API endpoint to discover capabilities and metadata.

    Returns:
        - Available columns and data types
        - Estimated row count for given parameters
        - Supported date ranges (if applicable)
        - Available seasons (if applicable)
        - Recommended chunking strategy for large datasets
        - Notes and warnings

    Perfect For:
        - Understanding endpoint structure before fetching
        - Planning large data fetches
        - Discovering what data is available

    Common Use Cases:
        - "Inspect shot_chart endpoint"
        - "What columns does player_career_stats return?"
        - "How big is this dataset?"

    Granularity: N/A (meta)
    Filters Available: None
    """

    endpoint: str = Field(
        ...,
        description=(
            "Endpoint name to inspect. "
            "Examples: 'player_career_stats', 'shot_chart', 'team_standings'. "
            "REQUIRED"
        ),
        examples=["player_career_stats", "shot_chart", "team_standings", "play_by_play"]
    )

    params: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Optional parameters to test with for size estimation. "
            "Helps estimate row counts for specific queries. "
            "Examples: {'player_name': 'LeBron James'}, {'season': '2023-24'}. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"endpoint": "shot_chart", "params": {"entity_name": "Stephen Curry"}},
                {"endpoint": "team_standings", "params": {"season": "2023-24"}},
                {"endpoint": "play_by_play"}
            ]
        }


# ============================================================================
# CATEGORY 9: DATA OPERATIONS
# ============================================================================

class FetchInput(BaseModel):
    """
    Input schema for fetch tool.

    Fetch raw data from an NBA API endpoint as an Arrow table.

    Returns data in standardized table format with provenance tracking.
    The dataset is stored in memory and returns a handle for further operations.

    Common Use Cases:
        - "Fetch player career stats for LeBron"
        - "Get team standings for 2023-24"
        - "Fetch league leaders in scoring"

    Granularity: Dynamic (depends on endpoint)
    Filters Available: Varies by endpoint
    """

    endpoint: str = Field(
        ...,
        description=(
            "Endpoint name from catalog. "
            "Examples: 'player_career_stats', 'team_standings', 'league_leaders'. "
            "REQUIRED"
        ),
        examples=["player_career_stats", "team_standings", "league_leaders"]
    )

    params: Dict[str, Any] = Field(
        ...,
        description=(
            "Parameters dictionary matching endpoint schema. "
            "Varies by endpoint. "
            "Examples: {'player_name': 'LeBron James'}, "
            "{'season': '2023-24', 'conference': 'East'}. "
            "REQUIRED"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"endpoint": "player_career_stats", "params": {"player_name": "LeBron James"}},
                {"endpoint": "team_standings", "params": {"season": "2023-24", "conference": "East"}},
                {"endpoint": "league_leaders", "params": {"stat_category": "PTS", "season": "2023-24"}}
            ]
        }


class JoinInput(BaseModel):
    """
    Input schema for join tool.

    Join multiple datasets using SQL join operations.

    Performs in-memory joins using DuckDB with automatic validation.
    Returns a new dataset handle with the joined result.

    Join Types:
        - inner: Only matching rows from both tables
        - left: All rows from first table, matching from second
        - right: All rows from second table, matching from first
        - outer: All rows from both tables
        - cross: Cartesian product (all combinations)

    Common Use Cases:
        - "Join player stats with team standings"
        - "Combine regular season and playoff data"
        - "Merge player and team data on TEAM_ID"

    Granularity: N/A (data operation)
    Filters Available: None (operates on existing data)
    """

    handles: List[str] = Field(
        ...,
        description=(
            "List of dataset UUIDs to join (2 or more required). "
            "Get handles from fetch/build_dataset tool results. "
            "Examples: ['uuid1', 'uuid2'], ['abc123', 'def456', 'ghi789']. "
            "REQUIRED"
        ),
        min_length=2
    )

    on: Union[str, List[str], Dict[str, str]] = Field(
        ...,
        description=(
            "Join columns. Three formats supported: "
            "1. str: Single column name (must exist in all tables) - 'PLAYER_ID' "
            "2. List[str]: Multiple columns (must exist in all tables) - ['PLAYER_ID', 'SEASON'] "
            "3. Dict[str, str]: Column mapping for 2 tables - {'TEAM_ID': 'ID'} "
            "REQUIRED"
        ),
        examples=["PLAYER_ID", ["PLAYER_ID", "SEASON"], {"TEAM_ID": "ID"}]
    )

    how: str = Field(
        "left",
        description=(
            "Join type: 'inner', 'left', 'right', 'outer', or 'cross'. "
            "Default: 'left'. "
            "Optional"
        ),
        examples=["inner", "left", "right", "outer"]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"handles": ["uuid1", "uuid2"], "on": "PLAYER_ID", "how": "inner"},
                {"handles": ["uuid1", "uuid2"], "on": ["PLAYER_ID", "SEASON"], "how": "left"},
                {"handles": ["uuid1", "uuid2"], "on": {"TEAM_ID": "ID"}, "how": "left"}
            ]
        }


class BuildDatasetInput(BaseModel):
    """
    Input schema for build_dataset tool.

    Build a complete dataset from multiple sources with joins, filters, and column selection.

    Executes a multi-step dataset pipeline in a single call:
        1. Fetch from multiple endpoints
        2. Join datasets
        3. Apply filters
        4. Select columns

    Perfect For:
        - Complex multi-source queries
        - Building custom analytical datasets
        - Data pipeline automation

    Common Use Cases:
        - "Build dataset with player stats and team standings joined"
        - "Fetch and merge multiple seasons of data"
        - "Create analytical dataset with filters"

    Granularity: Dynamic (composite operation)
    Filters Available: Specified in spec
    """

    spec: Dict[str, Any] = Field(
        ...,
        description=(
            "Dataset specification with: "
            "- sources: List of {endpoint, params} dicts "
            "- joins: List of {on, how} dicts (optional) "
            "- filters: List of {column, op, value} dicts (optional) "
            "- select: List of column names to keep (optional) "
            "REQUIRED"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "spec": {
                        "sources": [
                            {"endpoint": "player_career_stats", "params": {"player_name": "LeBron James"}},
                            {"endpoint": "team_standings", "params": {"season": "2023-24"}}
                        ],
                        "joins": [{"on": {"TEAM_ID": "TEAM_ID"}, "how": "left"}],
                        "filters": [{"column": "PTS", "op": ">", "value": 20}],
                        "select": ["PLAYER_NAME", "SEASON", "PTS", "TEAM_NAME", "W", "L"]
                    }
                }
            ]
        }


class FetchChunkedInput(BaseModel):
    """
    Input schema for fetch_chunked tool.

    Fetch large NBA datasets in chunks to handle any dataset size.

    Automatically splits large datasets into manageable chunks and returns
    multiple dataset handles (one per chunk). Enables fetching datasets
    that would be too large to retrieve all at once.

    Chunking Strategies:
        - date: Split by date ranges (monthly chunks)
        - season: Split by NBA seasons
        - game: Split by individual games
        - none: Fetch all at once (no chunking)
        - None (default): Auto-select based on endpoint

    Common Use Cases:
        - "Fetch all of Curry's shot data chunked by month"
        - "Get complete play-by-play for season in chunks"
        - "Fetch large datasets without memory issues"

    Granularity: Dynamic (chunked)
    Filters Available: Varies by endpoint
    """

    endpoint: str = Field(
        ...,
        description=(
            "Endpoint name to fetch from. "
            "Examples: 'shot_chart', 'play_by_play', 'team_game_log'. "
            "REQUIRED"
        ),
        examples=["shot_chart", "play_by_play", "team_game_log"]
    )

    params: Dict[str, Any] = Field(
        ...,
        description=(
            "Base parameters for the endpoint. "
            "Chunking applied on top of these. "
            "Examples: {'entity_name': 'Stephen Curry', 'season': '2023-24'}. "
            "REQUIRED"
        )
    )

    chunk_strategy: Optional[str] = Field(
        None,
        description=(
            "Chunking strategy to use. "
            "'date', 'season', 'game', 'none', or None (auto-select). "
            "Default: None (auto). "
            "Optional"
        ),
        examples=["date", "season", "game", "none"]
    )

    progress: bool = Field(
        False,
        description=(
            "Show progress information for each chunk. "
            "True = show progress, False = silent. "
            "Default: False. "
            "Optional"
        )
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"endpoint": "shot_chart", "params": {"entity_name": "Stephen Curry", "season": "2023-24"}, "chunk_strategy": "date"},
                {"endpoint": "play_by_play", "params": {"game_date": "2024-03-15"}, "chunk_strategy": "game"},
                {"endpoint": "team_game_log", "params": {"team": "Lakers", "season": "2023-24"}}
            ]
        }


# ============================================================================
# CATEGORY 10: DATA PERSISTENCE
# ============================================================================

class SaveNbaDataInput(BaseModel):
    """
    Input schema for save_nba_data tool.

    Save NBA data to organized mcp_data/ folder with descriptive filenames.

    Automatically generates meaningful filenames based on data content
    (team/player names, dates, data type), or uses custom filename if provided.

    File Organization:
        - Organized by date: mcp_data/YYYY-MM-DD/
        - Timestamped: filename_HHMMSS.json
        - Auto-named: {player/team}_{type}_{date}.json

    Common Use Cases:
        - "Save this shot chart data"
        - "Save game context to file"
        - "Export player stats"

    Granularity: N/A (persistence)
    Filters Available: None
    """

    data_json: str = Field(
        ...,
        description=(
            "JSON string from any NBA MCP tool response. "
            "Pass the complete tool output JSON. "
            "REQUIRED"
        )
    )

    custom_filename: Optional[str] = Field(
        None,
        description=(
            "Optional custom filename (without extension or timestamp). "
            "If None, auto-generates descriptive filename from data. "
            "Examples: 'my_analysis', 'curry_shots', 'lakers_game'. "
            "Optional"
        ),
        examples=["my_analysis", "curry_shots", "lakers_game"]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"data_json": "{...}", "custom_filename": "my_analysis"},
                {"data_json": "{...}"}
            ]
        }


class SaveDatasetInput(BaseModel):
    """
    Input schema for save_dataset tool.

    Save a dataset to disk in various formats.

    Exports a dataset from memory to a file on disk.
    Supports multiple formats with automatic compression.

    When path not specified, organizes in mcp_data/ folder:
        mcp_data/YYYY-MM-DD/dataset_HHMMSS.format

    Supported Formats:
        - parquet: Columnar format, highly compressed (RECOMMENDED)
        - csv: Comma-separated values
        - feather: Fast binary format
        - json: JSON format

    Common Use Cases:
        - "Save this dataset as parquet"
        - "Export to CSV"
        - "Save dataset to custom path"

    Granularity: N/A (persistence)
    Filters Available: None
    """

    handle: str = Field(
        ...,
        description=(
            "Dataset UUID to save. "
            "Get from fetch/join/build_dataset tool results. "
            "Examples: 'abc123', 'def456'. "
            "REQUIRED"
        )
    )

    path: Optional[str] = Field(
        None,
        description=(
            "Output file path. "
            "If None, auto-generates in mcp_data/YYYY-MM-DD/. "
            "Examples: 'data/player_stats.parquet', 'custom/path/data.csv'. "
            "Optional"
        ),
        examples=["data/player_stats.parquet", "custom/path/data.csv"]
    )

    format: str = Field(
        "parquet",
        description=(
            "Output format: 'parquet' (default, RECOMMENDED), 'csv', 'feather', or 'json'. "
            "Optional"
        ),
        examples=["parquet", "csv", "feather", "json"]
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"handle": "abc123"},
                {"handle": "abc123", "format": "csv"},
                {"handle": "abc123", "path": "data/player_stats.parquet", "format": "parquet"}
            ]
        }


# ============================================================================
# TOOL SCHEMA REGISTRY EXTENSION
# ============================================================================

TOOL_SCHEMAS_EXTENDED = {
    # ========================================================================
    # CATEGORY 1: ENTITY RESOLUTION
    # ========================================================================
    "resolve_nba_entity": {
        "input": ResolveNbaEntityInput,
        "output": ResolveNbaEntityOutput,
        "description": "Fuzzy matching resolver for player/team names with confidence scores"
    },

    # ========================================================================
    # CATEGORY 2: PLAYER STATS (ADVANCED)
    # ========================================================================
    "get_player_career_information": {
        "input": GetPlayerCareerInformationInput,
        "output": BaseModel,
        "description": "Get complete career statistics and history for a player"
    },
    "get_player_game_stats": {
        "input": GetPlayerGameStatsInput,
        "output": BaseModel,
        "description": "Get individual game statistics for a player with simple filtering"
    },
    "get_player_advanced_stats": {
        "input": GetPlayerAdvancedStatsInput,
        "output": BaseModel,
        "description": "Get advanced efficiency metrics (TS%, eFG%, USG%, PIE, Rating)"
    },
    "get_player_performance_splits": {
        "input": GetPlayerPerformanceSplitsInput,
        "output": BaseModel,
        "description": "Performance analysis with home/away, W/L splits, and trend detection"
    },
    "get_player_head_to_head": {
        "input": GetPlayerHeadToHeadInput,
        "output": BaseModel,
        "description": "Compare two players in games where both played"
    },

    # ========================================================================
    # CATEGORY 3: TEAM STATS
    # ========================================================================
    "get_team_standings": {
        "input": GetTeamStandingsInput,
        "output": BaseModel,
        "description": "Get NBA standings with conference/division rankings"
    },
    "get_team_advanced_stats": {
        "input": GetTeamAdvancedStatsInput,
        "output": BaseModel,
        "description": "Get team efficiency metrics (OffRtg, DefRtg, NetRtg, Pace)"
    },

    # ========================================================================
    # CATEGORY 4: LEAGUE DATA
    # ========================================================================
    "get_league_leaders_info": {
        "input": GetLeagueLeadersInfoInput,
        "output": BaseModel,
        "description": "Get top performers in any statistical category"
    },
    "get_live_scores": {
        "input": GetLiveScoresInput,
        "output": BaseModel,
        "description": "Get live or historical NBA scores for a date"
    },
    "get_nba_awards": {
        "input": GetNbaAwardsInput,
        "output": BaseModel,
        "description": "Get NBA awards (MVP, DPOY, ROY, All-NBA, etc.)"
    },
    "get_nba_schedule": {
        "input": GetNbaScheduleInput,
        "output": BaseModel,
        "description": "Get NBA schedule with auto-season detection and comprehensive filtering"
    },

    # ========================================================================
    # CATEGORY 5: ADVANCED ANALYTICS
    # ========================================================================
    "get_advanced_metrics": {
        "input": GetAdvancedMetricsInput,
        "output": BaseModel,
        "description": "Calculate sophisticated basketball metrics (Game Score, Win Shares, EWA)"
    },
    "compare_players": {
        "input": ComparePlayersInput,
        "output": BaseModel,
        "description": "Side-by-side player comparison with normalized statistics"
    },
    "compare_players_era_adjusted": {
        "input": ComparePlayersEraAdjustedInput,
        "output": BaseModel,
        "description": "Compare players across different eras with pace and scoring adjustments"
    },

    # ========================================================================
    # CATEGORY 6: GAME DATA
    # ========================================================================
    "play_by_play": {
        "input": PlayByPlayInput,
        "output": BaseModel,
        "description": "Get play-by-play events for games with optional lineup tracking"
    },
    "get_box_score": {
        "input": GetBoxScoreInput,
        "output": BaseModel,
        "description": "Get full box score with quarter-by-quarter breakdowns"
    },
    "get_shot_chart": {
        "input": GetShotChartInput,
        "output": BaseModel,
        "description": "Get shot location data with make/miss for players or teams"
    },
    "get_clutch_stats": {
        "input": GetClutchStatsInput,
        "output": BaseModel,
        "description": "Get clutch time statistics (final 5 minutes, score within 5 points)"
    },
    "get_game_context": {
        "input": GetGameContextInput,
        "output": BaseModel,
        "description": "Get comprehensive matchup analysis between two teams"
    },

    # ========================================================================
    # CATEGORY 7: CONTEXTUAL/COMPOSITE
    # ========================================================================
    "answer_nba_question": {
        "input": AnswerNbaQuestionInput,
        "output": BaseModel,
        "description": "Natural language query processing - routes to appropriate tools automatically"
    },
    "get_metrics_info": {
        "input": GetMetricsInfoInput,
        "output": BaseModel,
        "description": "Get server health, performance metrics, and observability information"
    },

    # ========================================================================
    # CATEGORY 8: SYSTEM/META TOOLS
    # ========================================================================
    "list_endpoints": {
        "input": ListEndpointsInput,
        "output": BaseModel,
        "description": "List available NBA API endpoints with schemas and capabilities"
    },
    "catalog": {
        "input": CatalogInput,
        "output": BaseModel,
        "description": "Get complete data catalog with schema information and join relationships"
    },
    "discover_nba_endpoints": {
        "input": DiscoverNbaEndpointsInput,
        "output": BaseModel,
        "description": "Discover all available NBA API endpoints with capabilities"
    },
    "configure_limits": {
        "input": ConfigureLimitsInput,
        "output": BaseModel,
        "description": "Configure dataset size limits for fetch operations"
    },
    "inspect_endpoint": {
        "input": InspectEndpointInput,
        "output": BaseModel,
        "description": "Inspect an NBA API endpoint to discover capabilities and metadata"
    },

    # ========================================================================
    # CATEGORY 9: DATA OPERATIONS
    # ========================================================================
    "fetch": {
        "input": FetchInput,
        "output": BaseModel,
        "description": "Fetch raw data from an NBA API endpoint as an Arrow table"
    },
    "join": {
        "input": JoinInput,
        "output": BaseModel,
        "description": "Join multiple datasets using SQL join operations"
    },
    "build_dataset": {
        "input": BuildDatasetInput,
        "output": BaseModel,
        "description": "Build a complete dataset from multiple sources with joins and filters"
    },
    "fetch_chunked": {
        "input": FetchChunkedInput,
        "output": BaseModel,
        "description": "Fetch large NBA datasets in chunks to handle any dataset size"
    },

    # ========================================================================
    # CATEGORY 10: DATA PERSISTENCE
    # ========================================================================
    "save_nba_data": {
        "input": SaveNbaDataInput,
        "output": BaseModel,
        "description": "Save NBA data to organized mcp_data/ folder with descriptive filenames"
    },
    "save_dataset": {
        "input": SaveDatasetInput,
        "output": BaseModel,
        "description": "Save a dataset to disk in various formats (parquet, csv, feather, json)"
    },
}


def merge_with_base_schemas(base_schemas: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge extended schemas with base schemas.

    Args:
        base_schemas: Base TOOL_SCHEMAS dict from tool_schemas.py

    Returns:
        Combined schema dictionary
    """
    combined = base_schemas.copy()
    combined.update(TOOL_SCHEMAS_EXTENDED)
    return combined
