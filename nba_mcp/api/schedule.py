"""
NBA Schedule Fetcher

Fetches NBA schedule data from the official NBA CDN endpoint.
Supports automated current season detection and comprehensive filtering.

Data Source:
    https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json

Features:
    - Auto-detect current season based on date
    - Filter by season, team, date range, season stage
    - Support for preseason, regular season, and playoffs
    - Idempotent upsert support for schedule updates
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# NBA CDN Schedule Endpoint
NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

# Season Stage IDs
SEASON_STAGE_MAP = {
    "preseason": 1,
    "pre": 1,
    "regular": 2,
    "regular_season": 2,
    "playoffs": 4,
    "post": 4,
}


def get_current_season_year() -> int:
    """
    Determine the current NBA season ending year.

    Logic:
        - If month >= August (8): season_end_year = current_year + 1
        - Otherwise: season_end_year = current_year

    Examples:
        - Date: 2025-10-30 → Season: 2025-26 → Returns: 2026
        - Date: 2025-07-15 → Season: 2024-25 → Returns: 2025

    Returns:
        int: Season ending year (e.g., 2026 for 2025-26 season)
    """
    today = datetime.now()
    # If we're past August, we're in the new season
    if today.month >= 8:
        return today.year + 1
    return today.year


def fetch_nba_schedule_raw(timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch raw NBA schedule data from the official NBA CDN.

    Args:
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Raw JSON data from NBA CDN

    Raises:
        requests.RequestException: If the request fails

    Example Response Structure:
        {
            "leagueSchedule": {
                "seasonYear": "2025",
                "leagueId": "00",
                "gameDates": [
                    {
                        "gameDate": "10/22/2025",
                        "games": [
                            {
                                "gameId": "0022500001",
                                "gameCode": "20251022/LALBOS",
                                "gameStatus": 1,
                                "gameStatusText": "Scheduled",
                                "period": 0,
                                "gameDateTimeUTC": "2025-10-22T23:30:00Z",
                                "gameTimeUTC": "23:30:00",
                                "gameEt": "07:30 PM ET",
                                "regulationPeriods": 4,
                                "seriesGameNumber": "",
                                "seriesText": "",
                                "ifNecessary": false,
                                "gameLeaders": {...},
                                "teamLeaders": {...},
                                "broadcasters": {...},
                                "homeTeam": {
                                    "teamId": 1610612738,
                                    "teamName": "Celtics",
                                    "teamCity": "Boston",
                                    "teamTricode": "BOS",
                                    "teamSlug": "celtics",
                                    "wins": 0,
                                    "losses": 0,
                                    "score": 0,
                                    "seed": null,
                                    "inBonus": null,
                                    "timeoutsRemaining": 0,
                                    "periods": []
                                },
                                "awayTeam": {
                                    "teamId": 1610612747,
                                    "teamName": "Lakers",
                                    "teamCity": "Los Angeles",
                                    "teamTricode": "LAL",
                                    "teamSlug": "lakers",
                                    "wins": 0,
                                    "losses": 0,
                                    "score": 0,
                                    "seed": null,
                                    "inBonus": null,
                                    "timeoutsRemaining": 0,
                                    "periods": []
                                },
                                "pointsLeaders": [],
                                "seasonStageId": 2,
                                "seasonYear": 2025,
                                "arenaName": "TD Garden",
                                "arenaCity": "Boston",
                                "arenaState": "MA",
                                "arenaCountry": "USA",
                                "arenaTimezone": "America/New_York"
                            }
                        ]
                    }
                ]
            }
        }
    """
    logger.info(f"Fetching NBA schedule from {NBA_SCHEDULE_URL}")
    response = requests.get(NBA_SCHEDULE_URL, timeout=timeout)
    response.raise_for_status()
    return response.json()


def parse_schedule_to_dataframe(
    raw_data: Dict[str, Any],
    season_year: Optional[int] = None,
    season_stage_id: Optional[int] = None,
    team_abbr: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> pd.DataFrame:
    """
    Parse raw NBA schedule JSON into a structured DataFrame with filtering.

    Args:
        raw_data: Raw JSON data from fetch_nba_schedule_raw()
        season_year: Filter by season ending year (e.g., 2026 for 2025-26)
        season_stage_id: Filter by stage (1=preseason, 2=regular, 4=playoffs)
        team_abbr: Filter by team abbreviation (e.g., "LAL", "BOS")
        date_from: Filter by start date (YYYY-MM-DD format)
        date_to: Filter by end date (YYYY-MM-DD format)

    Returns:
        DataFrame with columns:
            - game_id: Unique game identifier
            - season_year: Season ending year (2025 = 2025-26 season)
            - season_stage_id: 1=preseason, 2=regular, 4=playoffs
            - game_status: Current game status (Scheduled, In Progress, Final, etc.)
            - game_date_utc: Game date/time in UTC
            - game_date_local: Game date in local time (extracted from game_date_utc)
            - arena: Arena name
            - arena_city: Arena city
            - arena_state: Arena state
            - home_id: Home team ID
            - home_name: Home team name
            - home_abbr: Home team abbreviation
            - home_score: Home team score (0 if not started)
            - away_id: Away team ID
            - away_name: Away team name
            - away_abbr: Away team abbreviation
            - away_score: Away team score (0 if not started)
            - broadcasters_national: National TV broadcasters (comma-separated)
            - series_text: Playoff series info (if applicable)

    Example:
        raw_data = fetch_nba_schedule_raw()

        # Get 2025-26 regular season
        df = parse_schedule_to_dataframe(raw_data, season_year=2026, season_stage_id=2)

        # Get Lakers games
        df = parse_schedule_to_dataframe(raw_data, team_abbr="LAL")

        # Get games in January 2026
        df = parse_schedule_to_dataframe(
            raw_data,
            date_from="2026-01-01",
            date_to="2026-01-31"
        )
    """
    league_schedule = raw_data.get("leagueSchedule", {})
    game_dates = league_schedule.get("gameDates", [])

    rows = []
    for gd in game_dates:
        game_date = gd.get("gameDate")
        games = gd.get("games", [])

        for g in games:
            # Extract game data
            game_year = g.get("seasonYear")
            game_stage = g.get("seasonStageId")
            game_date_utc_str = g.get("gameDateTimeUTC")

            # Apply filters
            if season_year is not None and game_year != season_year:
                continue

            if season_stage_id is not None and game_stage != season_stage_id:
                continue

            # Team filter
            home_team = g.get("homeTeam", {})
            away_team = g.get("awayTeam", {})
            home_abbr_val = home_team.get("teamTricode", "")
            away_abbr_val = away_team.get("teamTricode", "")

            if team_abbr:
                team_upper = team_abbr.upper()
                if team_upper not in [home_abbr_val, away_abbr_val]:
                    continue

            # Date filter
            if game_date_utc_str:
                try:
                    game_dt = datetime.fromisoformat(game_date_utc_str.replace("Z", "+00:00"))
                    game_date_local = game_dt.date()

                    if date_from:
                        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
                        if game_date_local < date_from_obj:
                            continue

                    if date_to:
                        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
                        if game_date_local > date_to_obj:
                            continue
                except (ValueError, AttributeError):
                    game_date_local = None
            else:
                game_date_local = None

            # Extract broadcasters
            broadcasters = g.get("broadcasters", {})
            national_tv = broadcasters.get("nationalBroadcasters", [])
            if national_tv:
                national_tv_str = ", ".join([b.get("broadcastDisplay", "") for b in national_tv if b.get("broadcastDisplay")])
            else:
                national_tv_str = None

            # Build row
            row = {
                "game_id": g.get("gameId"),
                "season_year": game_year,
                "season_stage_id": game_stage,
                "game_status": g.get("gameStatusText"),
                "game_date_utc": game_date_utc_str,
                "game_date_local": str(game_date_local) if game_date_local else None,
                "arena": g.get("arenaName"),
                "arena_city": g.get("arenaCity"),
                "arena_state": g.get("arenaState"),
                "home_id": home_team.get("teamId"),
                "home_name": home_team.get("teamName"),
                "home_abbr": home_abbr_val,
                "home_score": home_team.get("score", 0),
                "away_id": away_team.get("teamId"),
                "away_name": away_team.get("teamName"),
                "away_abbr": away_abbr_val,
                "away_score": away_team.get("score", 0),
                "broadcasters_national": national_tv_str,
                "series_text": g.get("seriesText") or None,
            }
            rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by game date
    if not df.empty and "game_date_utc" in df.columns:
        df = df.sort_values("game_date_utc").reset_index(drop=True)

    logger.info(f"Parsed {len(df)} games from schedule data")
    return df


async def get_nba_schedule(
    season: Optional[Union[str, int]] = None,
    season_stage: Optional[str] = None,
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    timeout: int = 30,
) -> pd.DataFrame:
    """
    Fetch and filter NBA schedule data from the official NBA CDN.

    This is the main entry point for fetching schedule data. It handles:
    - Automatic current season detection
    - Filtering by season, team, date range, and season stage
    - Data normalization and sorting

    Args:
        season: Season identifier (optional, defaults to current season)
                Can be:
                - Season ending year as int (2026 for 2025-26)
                - Season string "YYYY-YY" (e.g., "2025-26")
                - None (uses current season)
        season_stage: Season stage filter (optional)
                     Values: "preseason", "regular", "playoffs"
                     Aliases: "pre", "regular_season", "post"
        team: Team filter by abbreviation (e.g., "LAL", "BOS") (optional)
        date_from: Start date filter in YYYY-MM-DD format (optional)
        date_to: End date filter in YYYY-MM-DD format (optional)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        DataFrame with filtered schedule data

        Columns:
            - game_id: Unique game identifier
            - season_year: Season ending year
            - season_stage_id: 1=preseason, 2=regular, 4=playoffs
            - game_status: Current status (Scheduled, In Progress, Final)
            - game_date_utc: Game date/time in UTC
            - game_date_local: Game date in local time
            - arena, arena_city, arena_state: Venue information
            - home_id, home_name, home_abbr, home_score: Home team data
            - away_id, away_name, away_abbr, away_score: Away team data
            - broadcasters_national: National TV info
            - series_text: Playoff series info (if applicable)

    Examples:
        # Get current season schedule (auto-detects 2025-26)
        schedule = get_nba_schedule()

        # Get 2025-26 regular season
        schedule = get_nba_schedule(season="2025-26", season_stage="regular")

        # Get Lakers schedule for current season
        schedule = get_nba_schedule(team="LAL")

        # Get playoffs schedule
        schedule = get_nba_schedule(season_stage="playoffs")

        # Get games in a specific date range
        schedule = get_nba_schedule(
            date_from="2026-01-01",
            date_to="2026-01-31"
        )

        # Combine filters
        schedule = get_nba_schedule(
            season="2025-26",
            season_stage="regular",
            team="LAL",
            date_from="2025-12-01",
            date_to="2025-12-31"
        )

    Raises:
        requests.RequestException: If fetching schedule data fails
        ValueError: If season format is invalid
    """
    # Determine season year
    if season is None:
        season_year = get_current_season_year()
        logger.info(f"Auto-detected current season: {season_year-1}-{str(season_year)[2:]}")
    elif isinstance(season, int):
        season_year = season
    elif isinstance(season, str):
        # Parse "YYYY-YY" format
        if "-" in season:
            parts = season.split("-")
            if len(parts) == 2:
                try:
                    # Extract the ending year
                    start_year = int(parts[0])
                    end_year_suffix = parts[1]

                    # Handle both "2025-26" and "2025-2026" formats
                    if len(end_year_suffix) == 2:
                        end_year = int(f"{str(start_year)[:2]}{end_year_suffix}")
                    else:
                        end_year = int(end_year_suffix)

                    season_year = end_year
                except ValueError:
                    raise ValueError(f"Invalid season format: {season}. Expected 'YYYY-YY' (e.g., '2025-26')")
            else:
                raise ValueError(f"Invalid season format: {season}. Expected 'YYYY-YY' (e.g., '2025-26')")
        else:
            raise ValueError(f"Invalid season format: {season}. Expected 'YYYY-YY' (e.g., '2025-26')")
    else:
        raise ValueError(f"Invalid season type: {type(season)}. Expected int, str, or None")

    # Map season stage to ID
    season_stage_id = None
    if season_stage:
        season_stage_lower = season_stage.lower()
        season_stage_id = SEASON_STAGE_MAP.get(season_stage_lower)
        if season_stage_id is None:
            valid_stages = list(set(SEASON_STAGE_MAP.keys()))
            raise ValueError(
                f"Invalid season_stage: {season_stage}. "
                f"Valid values: {valid_stages}"
            )

    # Fetch raw data (run sync function in thread pool)
    loop = asyncio.get_event_loop()
    raw_data = await loop.run_in_executor(None, fetch_nba_schedule_raw, timeout)

    # Parse and filter
    df = parse_schedule_to_dataframe(
        raw_data,
        season_year=season_year,
        season_stage_id=season_stage_id,
        team_abbr=team,
        date_from=date_from,
        date_to=date_to,
    )

    return df


def format_schedule_markdown(df: pd.DataFrame, max_games: int = 100) -> str:
    """
    Format schedule DataFrame as human-readable markdown.

    Args:
        df: Schedule DataFrame from get_nba_schedule()
        max_games: Maximum number of games to display (default: 100)

    Returns:
        Formatted markdown string

    Example Output:
        NBA Schedule: 2025-26 Regular Season | 82 games

        Date         Matchup              Time (UTC)    Arena              Status
        -----------  -------------------  ------------  -----------------  -----------
        2025-10-22   LAL @ BOS            23:30         TD Garden          Scheduled
        2025-10-23   GSW @ NYK            23:00         Madison Square G.  Scheduled
        ...
    """
    if df.empty:
        return "No games found matching the criteria."

    # Build header
    season_year = df["season_year"].iloc[0] if "season_year" in df.columns and not df.empty else "Unknown"
    season_stage_id = df["season_stage_id"].iloc[0] if "season_stage_id" in df.columns and not df.empty else None

    stage_map = {1: "Preseason", 2: "Regular Season", 4: "Playoffs"}
    stage_name = stage_map.get(season_stage_id, "All Stages")

    header = f"NBA Schedule: {season_year-1}-{str(season_year)[2:]} {stage_name} | {len(df)} games"

    if len(df) > max_games:
        header += f" (showing first {max_games})"
        df_display = df.head(max_games)
    else:
        df_display = df

    # Build table
    lines = [header, ""]
    lines.append(f"{'Date':<12} {'Matchup':<24} {'Time (ET)':<12} {'Arena':<25} {'Status':<12}")
    lines.append("-" * 90)

    for _, row in df_display.iterrows():
        # Parse date
        game_date = row.get("game_date_local", "N/A")
        if pd.isna(game_date):
            game_date = "N/A"

        # Build matchup string
        away_abbr = row.get("away_abbr", "???")
        home_abbr = row.get("home_abbr", "???")
        matchup = f"{away_abbr} @ {home_abbr}"

        # Extract time from UTC timestamp
        game_time_utc = row.get("game_date_utc", "")
        if game_time_utc and isinstance(game_time_utc, str):
            try:
                dt = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00"))
                # Note: This shows UTC time, not ET. For accurate ET conversion,
                # we'd need timezone info. For simplicity, we show UTC.
                game_time = dt.strftime("%H:%M UTC")
            except (ValueError, AttributeError):
                game_time = "TBD"
        else:
            game_time = "TBD"

        # Arena (truncate if too long)
        arena = row.get("arena", "N/A")
        if isinstance(arena, str) and len(arena) > 25:
            arena = arena[:22] + "..."

        # Status
        status = row.get("game_status", "N/A")

        lines.append(f"{game_date:<12} {matchup:<24} {game_time:<12} {str(arena):<25} {str(status):<12}")

    return "\n".join(lines)
