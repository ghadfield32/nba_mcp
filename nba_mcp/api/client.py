# client.py
import asyncio
import json
import logging
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

# ── APPLY NBA API PATCHES FIRST (before importing nba_api endpoints) ─────────────────────
from .nba_api_patches import apply_all_patches
apply_all_patches()

# Import from nba_api package
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    BoxScoreTraditionalV2,
    CommonPlayerInfo,
    LeagueDashPlayerClutch,
    LeagueDashTeamClutch,
    LeagueGameLog,
    LeagueLeaders,
    PlayerGameLog,
    PlayerProfileV2,
    playercareerstats,
    scoreboardv2,
)
from nba_api.stats.static import players, teams

from .tools.leaguegamelog_tools import fetch_league_game_log
from .tools.live_nba_endpoints import fetch_live_boxsc_odds_playbyplaydelayed_livescores
from .tools.nba_api_utils import (
    format_game,
    get_player_id,
    get_player_name,
    get_static_lookup_schema,
    get_team_id,
    get_team_name,
    normalize_date,
    normalize_per_mode,
    normalize_season,
    normalize_season_type,
    normalize_stat_category,
)
from .tools.playbyplayv3_or_realtime import PlaybyPlayLiveorPast, get_today_games
from .tools.playercareerstats_leagueleaders_tools import (
    get_league_leaders as _fetch_league_leaders,
)
from .tools.playercareerstats_leagueleaders_tools import (
    get_player_career_stats as _fetch_player_career_stats,
)
from .tools.scoreboardv2tools import fetch_scoreboard_v2_full

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NBAApiClient:
    """Client for interacting with the NBA API."""

    def __init__(self):
        """Initialize the NBA API client."""
        pass

    def _handle_response_error(self, e: Exception, context: str) -> Dict[str, Any]:
        """Handle API errors and return a standardized error response."""
        logger.error(f"Error in {context}: {str(e)}")
        return {
            "error": f"API error in {context}: {str(e)}",
            "status_code": getattr(e, "status_code", None),
        }

    async def get_api_documentation(self) -> Dict[str, Any]:
        """
        Retrieve the NBA API documentation using the local api_documentation module.
        This method calls the analyze_api_structure function to generate a guide of endpoints,
        required parameters, available datasets, and static data.

        Returns:
            A dictionary containing the API documentation.
        """
        try:
            # Define the documentation file path
            docs_path = Path("nba_mcp/api_documentation/endpoints.json")

            if docs_path.exists():
                logger.info("Loading API documentation from saved file.")
                with open(docs_path, "r") as f:
                    docs = json.load(f)
                return docs
            else:
                logger.info(
                    "Saved API documentation not found, generating documentation."
                )
                # Import functions from our local api_documentation.py module.
                from .tools.api_documentation import analyze_api_structure

                docs = analyze_api_structure()
                # Save the generated documentation for future use
                docs_path.parent.mkdir(parents=True, exist_ok=True)
                with open(docs_path, "w") as f:
                    json.dump(docs, f, indent=2)
                return docs
        except Exception as e:
            logger.error(f"Error in get_api_documentation: {str(e)}")
            return {"error": f"Failed to load API documentation: {str(e)}"}

    def find_player_by_name(self, player_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a player by name using the NBA API's static players data.
        Args:
            player_name: Full or partial player name
        Returns:
            Player dictionary or None if not found
        """
        try:
            logger.debug("Searching for player: '%s'", player_name)
            if not player_name or not player_name.strip():
                logger.error("Empty player name provided")
                return None

            logger.debug("Loading player roster data...")
            all_players = players.get_players()
            logger.debug("Loaded %d players from roster data", len(all_players))

            player_name_lower = player_name.lower().strip()
            logger.debug("Attempting exact match for: '%s'", player_name_lower)

            # 1) Exact full‐name match
            for player in all_players:
                full_name = f"{player['first_name']} {player['last_name']}".lower()
                if player_name_lower == full_name:
                    logger.debug(
                        "Found exact match: %s (ID: %s)", full_name, player["id"]
                    )
                    return player

            # 2) Exact last‑name match
            for player in all_players:
                if player_name_lower == player["last_name"].lower():
                    logger.debug(
                        "Found by last name: %s %s (ID: %s)",
                        player["first_name"],
                        player["last_name"],
                        player["id"],
                    )
                    return player

            # 3) Partial match
            logger.debug("No exact match; trying partial match…")
            matched = [
                p
                for p in all_players
                if player_name_lower in f"{p['first_name']} {p['last_name']}".lower()
            ]

            if matched:
                matched.sort(key=lambda p: len(f"{p['first_name']} {p['last_name']}"))
                best = matched[0]
                logger.debug(
                    "Best partial match: %s %s (ID: %s)",
                    best["first_name"],
                    best["last_name"],
                    best["id"],
                )
                return best

            logger.debug("No player match found for '%s'", player_name)
            return None

        except Exception as e:
            logger.exception("Exception while finding player '%s'", player_name)
            return None

    def get_season_string(self, year: Optional[int] = None) -> str:
        """
        Convert a year to NBA season format (e.g., 2023 -> "2023-24").
        If no year provided, returns current season.
        """
        if year is None:
            today = date.today()
            # NBA season typically starts in October
            if today.month >= 10:
                year = today.year
            else:
                year = today.year - 1

        return f"{year}-{str(year + 1)[-2:]}"

    async def get_player_career_stats(
        self, player_name: str, season: str, as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch a player's career stats for a given season.

        Args:
            player_name: Full or partial player name.
            season:      Season string 'YYYY-YY' (e.g. '2024-25').
            as_dataframe: If False, returns list of dicts; if True, returns DataFrame or message.

        Returns:
            DataFrame of career stats rows, or list-of‑dicts, or a user-friendly message.
        """
        try:
            # Offload the blocking call
            df: pd.DataFrame = await asyncio.to_thread(
                _fetch_player_career_stats, player_name, season
            )

            # If caller wants raw JSON‑style records
            if not as_dataframe:
                return df.to_dict("records")

            # If no rows returned, inform the user
            if df.empty:
                return f"No career stats found for '{player_name}' in season {season}."

            return df

        except Exception as e:
            # Route through your standard error‐handler
            return self._handle_response_error(e, "get_player_career_stats")

    async def get_league_leaders(
        self,
        season: Optional[Union[str, List[str]]] = None,
        stat_category: str = "PTS",
        per_mode: str = "Totals",
        season_type_all_star: str = "Regular Season",
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch top league leaders for one or more seasons.

        Args:
            season: Season(s) in 'YYYY-YY' format
            stat_category: Statistical category (e.g., 'PTS', 'AST')
            per_mode: Aggregation mode ('Totals', 'PerGame', 'Per48')
            season_type_all_star: Season type ('Regular Season', 'Playoffs', 'All Star')
            as_dataframe: Return as DataFrame (True) or list of dicts (False)
        """
        stat_category_norm = normalize_stat_category(stat_category)
        per_mode_norm = normalize_per_mode(per_mode)

        # --- handle single vs multi-season ---
        seasons = normalize_season(season)
        if seasons is None:
            # default to current season if none provided
            seasons = [self.get_season_string()]

        results = []
        for s in seasons:
            df: pd.DataFrame = await asyncio.to_thread(
                _fetch_league_leaders, s, stat_category_norm, per_mode_norm, season_type_all_star
            )
            if df.empty:
                continue
            # ensure PLAYER_NAME column
            if "PLAYER_NAME" not in df.columns and "PLAYER_ID" in df.columns:
                df["PLAYER_NAME"] = df["PLAYER_ID"].map(get_player_name)
            df["SEASON"] = s
            results.append(df)

        if not results:
            msg = f"No league leaders for '{stat_category}' in seasons: {seasons}."
            return msg if as_dataframe else []

        full_df = pd.concat(results, ignore_index=True)
        return full_df if as_dataframe else full_df.to_dict("records")

    async def get_live_scoreboard(
        self,
        target_date: Optional[Union[str, date, datetime]] = None,
        day_offset: int = 0,  # no longer used by fetch_all_games
        league_id: str = "00",  # ditto
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch NBA games (live or by-date) using our unified fetch_all_games helper.
        """
        try:
            date_str = target_date and str(target_date) or None
            logger.debug(f"[DEBUG] get_live_scoreboard: Received target_date={target_date}, converted to date_str={date_str}")

            # 1) Delegate to our synchronous fetch_all_games
            payload = await asyncio.to_thread(
                fetch_live_boxsc_odds_playbyplaydelayed_livescores,
                date_str,
            )
            logger.debug(f"[DEBUG] get_live_scoreboard: Received payload with date={payload.get('date')}, games count={len(payload.get('games', []))}")
            games = payload["games"]  # list of game‐dicts
            if not as_dataframe:
                # Return dict with both date and games to preserve date information
                return {"date": payload["date"], "games": games}

            # 2) Build a flat DataFrame of summary fields
            records = []
            for g in games:
                # pick either live summary or historical snapshot
                summary = g.get("scoreBoardSummary") or g.get("scoreBoardSnapshot")
                # flatten out the teams and scores
                home = summary["homeTeam"]
                away = summary["awayTeam"]
                records.append(
                    {
                        "gameId": summary["gameId"],
                        "date": payload["date"],
                        "home_team": home.get("teamName") or home.get("TEAM_NAME"),
                        "away_team": away.get("teamName") or away.get("TEAM_NAME"),
                        "home_pts": home.get("score") or home.get("PTS"),
                        "away_pts": away.get("score") or away.get("PTS"),
                        "status": summary.get("gameStatusText")
                        or summary.get("gameStatus"),
                        "period": summary.get("period"),
                        "clock": summary.get("gameClock"),
                    }
                )

            df = pd.DataFrame(records)
            if df.empty:
                return "No games found for that date."
            return df

        except Exception as e:
            return self._handle_response_error(e, "get_live_scoreboard")

    async def get_league_game_log(
        self,
        season: str,
        team_name: Optional[str] = None,
        season_type: str = "Regular Season",
        date_from: Optional[Union[str, date, datetime]] = None,
        date_to: Optional[Union[str, date, datetime]] = None,
        direction: str = "DESC",
        sorter: str = "DATE",
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch a full or filtered NBA game log via LeagueGameLog helper.

        Args:
            season:      Season string "YYYY-YY".
            team_name:   Optional full/partial team name filter.
            season_type: One of "Regular Season","Playoffs","Pre Season","All Star", etc.
            date_from:   Optional start date (string/date/datetime).
            date_to:     Optional end date (string/date/datetime).
            direction:   "ASC" or "DESC" for sort order.
            sorter:      Field to sort by (e.g. "PTS","DATE").
            as_dataframe: If False, returns list of dicts; otherwise DataFrame or message.

        Returns:
            pd.DataFrame | List[dict] | str
        """
        try:
            # Offload the blocking call to a thread
            df: pd.DataFrame = await asyncio.to_thread(
                fetch_league_game_log,
                season,
                team_name,
                season_type,
                date_from,
                date_to,
                direction,
                sorter,
            )
            # Raw list if requested
            if not as_dataframe:
                return df.to_dict("records")

            # Friendly message if no rows
            if df.empty:
                return "No game‐log rows found for those filters."

            return df

        except Exception as e:
            return self._handle_response_error(e, "get_league_game_log")

    async def get_today_games(
        self, as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        try:
            games = await asyncio.to_thread(get_today_games)

            # Explicit type handling for robustness
            if not isinstance(games, list):
                # Return clearly if games is dict or unexpected type
                return "Unexpected data format received for today's games."

            if not games:  # Empty list scenario
                return "No NBA games scheduled today."

            df = pd.DataFrame(games)
            return df if as_dataframe else games

        except Exception as e:
            return self._handle_response_error(e, "get_today_games")

    async def get_play_by_play(
        self,
        *,
        game_date: str,
        team: str,
        start_period: int = 1,
        end_period: int = 4,
        start_clock: Optional[str] = None,
        recent_n: int = 5,
        max_lines: int = 200,
    ) -> Union[str, Dict[str, Any]]:
        """
        Unified play-by-play (pregame / live / historical).

        Requires:
          • game_date (YYYY-MM-DD)
          • team name (e.g., "Lakers")

        Optional:
          - start_period, end_period, start_clock for historical slicing
          - recent_n, max_lines for live snapshots
        """
        try:
            # Delegate directly to the orchestrator
            def build_md():
                orch = PlaybyPlayLiveorPast(
                    when=game_date,
                    team=team,
                    start_period=start_period,
                    end_period=end_period,
                    start_clock=start_clock,
                    recent_n=recent_n,
                    max_lines=max_lines,
                )
                return orch.to_markdown()

            md = await asyncio.to_thread(build_md)
            return md
        except Exception as e:
            return self._handle_response_error(e, "get_play_by_play")

    async def get_games_by_date(
        self,
        target_date: Optional[Union[str, date, datetime]] = None,
        league_id: str = "00",
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch games for a specific date using ScoreboardV2.

        Args:
            target_date: Date in 'YYYY-MM-DD' format, date object, or datetime
            league_id: League ID ('00' for NBA)
            as_dataframe: If True, returns DataFrame; otherwise list of dicts

        Returns:
            DataFrame, list of game dictionaries, or error message
        """
        try:
            # Normalize the date
            norm_date = normalize_date(target_date)
            date_str = norm_date.strftime("%Y-%m-%d")

            # Use scoreboardv2 with the correct parameter name
            sb = await asyncio.to_thread(
                scoreboardv2.ScoreboardV2, game_date=date_str, league_id=league_id
            )

            # Get DataFrames
            game_header = sb.game_header.get_data_frame()

            if game_header.empty:
                return f"No games found for {date_str}."

            # Format the response
            games = []
            for _, row in game_header.iterrows():
                home_team_id = row["HOME_TEAM_ID"]
                visitor_team_id = row["VISITOR_TEAM_ID"]

                game_data = {
                    "game_id": row["GAME_ID"],
                    "game_date": row["GAME_DATE_EST"],
                    "status": row["GAME_STATUS_TEXT"],
                    "home_team": {
                        "id": home_team_id,
                        "full_name": get_team_name(home_team_id),
                    },
                    "visitor_team": {
                        "id": visitor_team_id,
                        "full_name": get_team_name(visitor_team_id),
                    },
                    "home_team_score": 0,  # Will be populated from line_score if available
                    "visitor_team_score": 0,
                }
                games.append(game_data)

            # Try to get scores from line_score if available
            line_score = sb.line_score.get_data_frame()
            if not line_score.empty:
                for game in games:
                    home_rows = line_score[
                        line_score["TEAM_ID"] == game["home_team"]["id"]
                    ]
                    away_rows = line_score[
                        line_score["TEAM_ID"] == game["visitor_team"]["id"]
                    ]

                    if not home_rows.empty:
                        game["home_team_score"] = home_rows.iloc[0].get("PTS", 0)
                    if not away_rows.empty:
                        game["visitor_team_score"] = away_rows.iloc[0].get("PTS", 0)

            if not as_dataframe:
                return {"data": games}

            # Convert to DataFrame
            return pd.DataFrame(games)

        except Exception as e:
            return self._handle_response_error(e, "get_games_by_date")

    async def get_player_game_log(
        self,
        player_name: str,
        season: Optional[str] = None,
        season_type: str = "Regular Season",
        last_n_games: Optional[int] = None,
        date_from: Optional[str] = None,  # Phase 2F: Filter pushdown support
        date_to: Optional[str] = None,    # Phase 2F: Filter pushdown support
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, Dict[str, Any]]:
        """
        Get game-by-game stats for a specific player.

        This method provides individual game statistics for a player, supporting:
        - Full season game logs
        - Last N games filtering
        - Regular season and playoffs
        - Date range filtering (Phase 2F)

        Args:
            player_name: Player name (supports fuzzy matching)
            season: Season in 'YYYY-YY' format (defaults to current season)
            season_type: "Regular Season" or "Playoffs" (default: "Regular Season")
            last_n_games: Optional limit to most recent N games
            date_from: Start date for filtering (YYYY-MM-DD format) - Phase 2F
            date_to: End date for filtering (YYYY-MM-DD format) - Phase 2F
            as_dataframe: Return DataFrame if True, dict if False

        Returns:
            DataFrame with columns: GAME_DATE, MATCHUP, WL, MIN, PTS, REB, AST, etc.
            Or dict with error information if request fails

        Example:
            # Get LeBron's last 10 games
            df = await client.get_player_game_log("LeBron James", last_n_games=10)

            # Get full season stats
            df = await client.get_player_game_log("Stephen Curry", season="2023-24")

            # Get games in date range (Phase 2F)
            df = await client.get_player_game_log(
                "LeBron James",
                date_from="2024-01-01",
                date_to="2024-01-31"
            )
        """
        try:
            # Get player ID
            player_id = get_player_id(player_name)
            if not player_id:
                return {"error": f"Player not found: {player_name}"}

            # Default to current season if not specified
            if season is None:
                # Import here to avoid circular dependency
                from nba_mcp.api.season_context import get_current_season
                season = get_current_season()

            # Normalize season format
            season = normalize_season(season)

            # Fetch game log from NBA API
            logger.debug(f"Fetching game log for player_id={player_id}, season={season}")

            # Phase 2F: Pass date filters to NBA API if provided
            game_log = await asyncio.to_thread(
                PlayerGameLog,
                player_id=player_id,
                season=season,
                season_type_all_star=season_type,
                date_from_nullable=date_from or "",  # Phase 2F: Filter pushdown
                date_to_nullable=date_to or ""       # Phase 2F: Filter pushdown
            )

            # Get DataFrame
            df = game_log.get_data_frames()[0]

            if df.empty:
                return {"error": f"No games found for {player_name} in {season} {season_type}"}

            # Sort by date (most recent first)
            if "GAME_DATE" in df.columns:
                df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
                df = df.sort_values("GAME_DATE", ascending=False)

            # Apply last_n_games filter if specified
            if last_n_games and last_n_games > 0:
                df = df.head(last_n_games)

            if as_dataframe:
                return df
            else:
                return {"data": df.to_dict(orient="records")}

        except Exception as e:
            logger.error(f"Error fetching player game log: {str(e)}")
            return self._handle_response_error(e, "get_player_game_log")

    async def get_box_score(
        self,
        game_id: str,
        as_dataframe: bool = False,
    ) -> Union[Dict[str, Any], pd.DataFrame]:
        """
        Get full box score for a specific game with quarter-by-quarter breakdowns.

        This method provides comprehensive game statistics including:
        - Player stats for both teams
        - Team totals
        - Quarter-by-quarter scores
        - Starter/bench breakdowns

        Args:
            game_id: 10-digit game ID (e.g., "0022300500")
            as_dataframe: Return DataFrames if True, dict if False

        Returns:
            Dict with keys: player_stats, team_stats, line_score
            Or DataFrames if as_dataframe=True

        Example:
            # Get box score for specific game
            box_score = await client.get_box_score("0022300500")
            print(box_score['team_stats'])  # Team totals
            print(box_score['line_score'])  # Quarter scores
        """
        try:
            # Fetch box score from NBA API
            logger.debug(f"Fetching box score for game_id={game_id}")

            box_score = await asyncio.to_thread(
                BoxScoreTraditionalV2,
                game_id=game_id
            )

            # Get DataFrames
            dfs = box_score.get_data_frames()

            # Extract the different data tables
            player_stats = dfs[0] if len(dfs) > 0 else pd.DataFrame()
            team_stats = dfs[1] if len(dfs) > 1 else pd.DataFrame()
            team_starter_bench = dfs[2] if len(dfs) > 2 else pd.DataFrame()
            line_score = dfs[3] if len(dfs) > 3 else pd.DataFrame()

            if player_stats.empty:
                return {"error": f"No box score data found for game_id={game_id}"}

            if as_dataframe:
                return {
                    "player_stats": player_stats,
                    "team_stats": team_stats,
                    "team_starter_bench": team_starter_bench,
                    "line_score": line_score
                }
            else:
                return {
                    "player_stats": player_stats.to_dict(orient="records"),
                    "team_stats": team_stats.to_dict(orient="records"),
                    "team_starter_bench": team_starter_bench.to_dict(orient="records"),
                    "line_score": line_score.to_dict(orient="records")
                }

        except Exception as e:
            logger.error(f"Error fetching box score: {str(e)}")
            return self._handle_response_error(e, "get_box_score")

    async def get_clutch_stats(
        self,
        entity_name: str,
        entity_type: str = "player",
        season: Optional[str] = None,
        per_mode: str = "PerGame",
        date_from: Optional[str] = None,  # Phase 2F: Filter pushdown support
        date_to: Optional[str] = None,    # Phase 2F: Filter pushdown support
        outcome: Optional[str] = None,    # Phase 2F: W/L filtering
        location: Optional[str] = None,   # Phase 2F: Home/Away filtering
    ) -> Union[pd.DataFrame, Dict[str, Any]]:
        """
        Get clutch time statistics (final 5 minutes, score within 5 points).

        This method provides clutch performance metrics including:
        - Points, rebounds, assists in clutch situations
        - Shooting percentages in clutch time
        - Win-loss record in clutch games
        - Clutch time efficiency ratings
        - Date range filtering (Phase 2F)
        - W/L and Home/Away filtering (Phase 2F)

        Args:
            entity_name: Player or team name
            entity_type: "player" or "team" (default: "player")
            season: Season in 'YYYY-YY' format (defaults to current season)
            per_mode: "PerGame" or "Totals" (default: "PerGame")
            date_from: Start date for filtering (YYYY-MM-DD format) - Phase 2F
            date_to: End date for filtering (YYYY-MM-DD format) - Phase 2F
            outcome: W/L filtering ("W" or "L") - Phase 2F
            location: Home/Away filtering ("Home" or "Road") - Phase 2F

        Returns:
            DataFrame with clutch statistics
            Or dict with error information if request fails

        Example:
            # Get LeBron's clutch stats
            df = await client.get_clutch_stats("LeBron James", entity_type="player")

            # Get Lakers' clutch stats
            df = await client.get_clutch_stats("Lakers", entity_type="team")

            # Get clutch stats with filters (Phase 2F)
            df = await client.get_clutch_stats(
                "LeBron James",
                date_from="2024-01-01",
                date_to="2024-01-31",
                outcome="W"
            )
        """
        try:
            # Default to current season if not specified
            if season is None:
                from nba_mcp.api.season_context import get_current_season
                season = get_current_season()

            # Normalize season format
            season = normalize_season(season)

            logger.debug(f"Fetching clutch stats for {entity_name} ({entity_type}), season={season}")

            if entity_type == "player":
                # For players, we get league-wide clutch stats and filter
                # Phase 2F: Pass filter parameters to NBA API
                clutch_data = await asyncio.to_thread(
                    LeagueDashPlayerClutch,
                    season=season,
                    per_mode_detailed=per_mode,
                    clutch_time="Last 5 Minutes",
                    point_diff="5",
                    date_from_nullable=date_from or "",  # Phase 2F: Filter pushdown
                    date_to_nullable=date_to or "",      # Phase 2F: Filter pushdown
                    outcome_nullable=outcome or "",      # Phase 2F: W/L filter
                    location_nullable=location or ""     # Phase 2F: Home/Away filter
                )

                df = clutch_data.get_data_frames()[0]

                if df.empty:
                    return {"error": f"No clutch stats found for season {season}"}

                # Filter for specific player
                player_id = get_player_id(entity_name)
                if not player_id:
                    return {"error": f"Player not found: {entity_name}"}

                df = df[df["PLAYER_ID"] == player_id]

                if df.empty:
                    return {"error": f"No clutch stats found for {entity_name} in {season}"}

            elif entity_type == "team":
                # For teams, get league-wide team clutch stats and filter
                # Phase 2F: Pass filter parameters to NBA API
                clutch_data = await asyncio.to_thread(
                    LeagueDashTeamClutch,
                    season=season,
                    per_mode_detailed=per_mode,
                    clutch_time="Last 5 Minutes",
                    point_diff="5",
                    date_from_nullable=date_from or "",  # Phase 2F: Filter pushdown
                    date_to_nullable=date_to or "",      # Phase 2F: Filter pushdown
                    outcome_nullable=outcome or "",      # Phase 2F: W/L filter
                    location_nullable=location or ""     # Phase 2F: Home/Away filter
                )

                df = clutch_data.get_data_frames()[0]

                if df.empty:
                    return {"error": f"No clutch stats found for season {season}"}

                # Filter for specific team
                team_id = get_team_id(entity_name)
                if not team_id:
                    return {"error": f"Team not found: {entity_name}"}

                df = df[df["TEAM_ID"] == team_id]

                if df.empty:
                    return {"error": f"No clutch stats found for {entity_name} in {season}"}

            else:
                return {"error": f"Invalid entity_type: {entity_type}. Must be 'player' or 'team'"}

            return df

        except Exception as e:
            logger.error(f"Error fetching clutch stats: {str(e)}")
            return self._handle_response_error(e, "get_clutch_stats")

    async def get_player_head_to_head(
        self,
        player1_name: str,
        player2_name: str,
        season: Optional[str] = None,
        date_from: Optional[str] = None,  # Phase 2F: Filter pushdown support
        date_to: Optional[str] = None,    # Phase 2F: Filter pushdown support
    ) -> Dict[str, Any]:
        """
        Get head-to-head matchup stats for two players.

        Finds all games where both players participated and compares their performance
        in those specific matchups.

        Args:
            player1_name: First player name
            player2_name: Second player name
            season: Season in 'YYYY-YY' format (defaults to current season)
            date_from: Start date for filtering (YYYY-MM-DD format) - Phase 2F
            date_to: End date for filtering (YYYY-MM-DD format) - Phase 2F

        Returns:
            Dict with keys:
            - player1_stats: DataFrame of player 1's stats in matchup games
            - player2_stats: DataFrame of player 2's stats in matchup games
            - common_games: List of game IDs where both played
            - player1_record: Win-loss record for player 1
            - player2_record: Win-loss record for player 2
            - matchup_count: Number of games they faced each other

        Example:
            # Get LeBron vs Durant head-to-head
            h2h = await client.get_player_head_to_head("LeBron James", "Kevin Durant")

            # With date filtering (Phase 2F)
            h2h = await client.get_player_head_to_head(
                "LeBron James",
                "Kevin Durant",
                date_from="2024-01-01",
                date_to="2024-01-31"
            )
        """
        try:
            # Default to current season if not specified
            if season is None:
                from nba_mcp.api.season_context import get_current_season
                season = get_current_season()

            # Normalize season format
            season = normalize_season(season)

            logger.debug(f"Fetching head-to-head: {player1_name} vs {player2_name}, season={season}")

            # Get player IDs and names (for proper name resolution)
            player1_id = get_player_id(player1_name)
            player2_id = get_player_id(player2_name)

            # Get full player names from ID lookup
            from nba_api.stats.static import players
            all_players = players.get_players()
            player1_full = next((p["full_name"] for p in all_players if p["id"] == player1_id), player1_name)
            player2_full = next((p["full_name"] for p in all_players if p["id"] == player2_id), player2_name)

            # Fetch game logs for both players
            # Phase 2F: Pass date filters to game log fetching
            player1_games = await self.get_player_game_log(
                player_name=player1_name,
                season=season,
                date_from=date_from,  # Phase 2F: Filter pushdown
                date_to=date_to,      # Phase 2F: Filter pushdown
                as_dataframe=True
            )

            player2_games = await self.get_player_game_log(
                player_name=player2_name,
                season=season,
                date_from=date_from,  # Phase 2F: Filter pushdown
                date_to=date_to,      # Phase 2F: Filter pushdown
                as_dataframe=True
            )

            # Check for errors
            if isinstance(player1_games, dict) and "error" in player1_games:
                return {"error": f"Player 1: {player1_games['error']}"}

            if isinstance(player2_games, dict) and "error" in player2_games:
                return {"error": f"Player 2: {player2_games['error']}"}

            if player1_games.empty or player2_games.empty:
                return {"error": "One or both players have no games in this season"}

            # Add player names to the DataFrames
            player1_games["PLAYER_NAME"] = player1_full
            player2_games["PLAYER_NAME"] = player2_full

            # Find common games (where both players participated)
            player1_game_ids = set(player1_games["Game_ID"].tolist())
            player2_game_ids = set(player2_games["Game_ID"].tolist())

            common_game_ids = player1_game_ids.intersection(player2_game_ids)

            if not common_game_ids:
                return {
                    "error": f"No head-to-head matchups found between {player1_name} and {player2_name} in {season}",
                    "matchup_count": 0
                }

            # Filter to only common games
            player1_matchup_games = player1_games[player1_games["Game_ID"].isin(common_game_ids)]
            player2_matchup_games = player2_games[player2_games["Game_ID"].isin(common_game_ids)]

            # Sort by date
            player1_matchup_games = player1_matchup_games.sort_values("GAME_DATE", ascending=False)
            player2_matchup_games = player2_matchup_games.sort_values("GAME_DATE", ascending=False)

            # Calculate records
            player1_wins = len(player1_matchup_games[player1_matchup_games["WL"] == "W"])
            player1_losses = len(player1_matchup_games[player1_matchup_games["WL"] == "L"])

            player2_wins = len(player2_matchup_games[player2_matchup_games["WL"] == "W"])
            player2_losses = len(player2_matchup_games[player2_matchup_games["WL"] == "L"])

            return {
                "player1_stats": player1_matchup_games,
                "player2_stats": player2_matchup_games,
                "common_games": list(common_game_ids),
                "player1_record": {"wins": player1_wins, "losses": player1_losses},
                "player2_record": {"wins": player2_wins, "losses": player2_losses},
                "matchup_count": len(common_game_ids),
                "season": season
            }

        except Exception as e:
            logger.error(f"Error fetching head-to-head stats: {str(e)}")
            return self._handle_response_error(e, "get_player_head_to_head")

    async def get_player_performance_splits(
        self,
        player_name: str,
        season: Optional[str] = None,
        last_n_games: Optional[int] = None,
        date_from: Optional[str] = None,  # Phase 2F: Filter pushdown support
        date_to: Optional[str] = None,    # Phase 2F: Filter pushdown support
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance splits and advanced analytics for a player.

        Provides detailed performance breakdowns including:
        - Recent form analysis (last N games vs season average)
        - Home vs Away splits
        - Win vs Loss performance
        - Per-100 possessions normalization
        - Trend detection (hot/cold streaks)
        - Date range filtering (Phase 2F)

        Args:
            player_name: Player name
            season: Season in 'YYYY-YY' format (defaults to current season)
            last_n_games: Analyze last N games (default: 10)
            date_from: Start date for filtering (YYYY-MM-DD format) - Phase 2F
            date_to: End date for filtering (YYYY-MM-DD format) - Phase 2F

        Returns:
            Dict with keys:
            - season_stats: Full season averages
            - last_n_stats: Last N games averages
            - home_stats: Home games averages
            - away_stats: Away games averages
            - wins_stats: Performance in wins
            - losses_stats: Performance in losses
            - trends: Hot/cold streak analysis
            - per_100_stats: Per-100 possessions stats

        Example:
            # Get LeBron's performance splits
            splits = await client.get_player_performance_splits("LeBron James", last_n_games=10)

            # With date filtering (Phase 2F)
            splits = await client.get_player_performance_splits(
                "LeBron James",
                date_from="2024-01-01",
                date_to="2024-01-31"
            )
        """
        try:
            # Default to current season if not specified
            if season is None:
                from nba_mcp.api.season_context import get_current_season
                season = get_current_season()

            # Normalize season format
            season = normalize_season(season)

            # Default to last 10 games if not specified
            if last_n_games is None:
                last_n_games = 10

            logger.debug(f"Fetching performance splits: {player_name}, season={season}, last_n={last_n_games}")

            # Fetch full season game log
            # Phase 2F: Pass date filters to game log fetching
            game_log = await self.get_player_game_log(
                player_name=player_name,
                season=season,
                date_from=date_from,  # Phase 2F: Filter pushdown
                date_to=date_to,      # Phase 2F: Filter pushdown
                as_dataframe=True
            )

            # Check for errors
            if isinstance(game_log, dict) and "error" in game_log:
                return {"error": game_log["error"]}

            if game_log.empty:
                return {"error": f"No games found for {player_name} in {season}"}

            # Sort by date (most recent first)
            game_log = game_log.sort_values("GAME_DATE", ascending=False)

            # Helper function to calculate averages
            def calc_averages(df: pd.DataFrame) -> Dict[str, float]:
                """Calculate statistical averages from game log"""
                if df.empty:
                    return {}

                return {
                    "games": len(df),
                    "ppg": df["PTS"].mean(),
                    "rpg": df["REB"].mean(),
                    "apg": df["AST"].mean(),
                    "spg": df["STL"].mean() if "STL" in df.columns else 0.0,
                    "bpg": df["BLK"].mean() if "BLK" in df.columns else 0.0,
                    "tpg": df["TOV"].mean() if "TOV" in df.columns else 0.0,
                    "fg_pct": df["FG_PCT"].mean(),
                    "fg3_pct": df["FG3_PCT"].mean() if "FG3_PCT" in df.columns else 0.0,
                    "ft_pct": df["FT_PCT"].mean() if "FT_PCT" in df.columns else 0.0,
                    "mpg": df["MIN"].mean(),
                    "plus_minus": df["PLUS_MINUS"].mean() if "PLUS_MINUS" in df.columns else 0.0,
                }

            # Calculate season averages
            season_stats = calc_averages(game_log)

            # Calculate last N games averages
            last_n_df = game_log.head(last_n_games)
            last_n_stats = calc_averages(last_n_df)

            # Calculate home vs away splits
            # MATCHUP format: "TEAM vs. OPPONENT" (home) or "TEAM @ OPPONENT" (away)
            home_games = game_log[game_log["MATCHUP"].str.contains("vs\\.", na=False, regex=True)]
            away_games = game_log[game_log["MATCHUP"].str.contains("@", na=False, regex=False)]

            home_stats = calc_averages(home_games)
            away_stats = calc_averages(away_games)

            # Calculate win vs loss splits
            wins = game_log[game_log["WL"] == "W"]
            losses = game_log[game_log["WL"] == "L"]

            wins_stats = calc_averages(wins)
            losses_stats = calc_averages(losses)

            # Trend analysis (comparing last N to season average)
            trends = {}
            if last_n_stats and season_stats:
                trends = {
                    "ppg_trend": last_n_stats["ppg"] - season_stats["ppg"],
                    "rpg_trend": last_n_stats["rpg"] - season_stats["rpg"],
                    "apg_trend": last_n_stats["apg"] - season_stats["apg"],
                    "fg_pct_trend": last_n_stats["fg_pct"] - season_stats["fg_pct"],
                    "is_hot_streak": last_n_stats["ppg"] > season_stats["ppg"] * 1.1,  # >10% above average
                    "is_cold_streak": last_n_stats["ppg"] < season_stats["ppg"] * 0.9,  # >10% below average
                }

            # Per-100 possessions calculation
            # Estimate possessions: FGA + 0.44*FTA + TOV
            def calc_per_100(df: pd.DataFrame) -> Dict[str, float]:
                """Calculate per-100 possession stats"""
                if df.empty or "FGA" not in df.columns:
                    return {}

                # Estimate possessions per game
                fga = df["FGA"].mean() if "FGA" in df.columns else 0
                fta = df["FTA"].mean() if "FTA" in df.columns else 0
                tov = df["TOV"].mean() if "TOV" in df.columns else 0

                possessions_per_game = fga + (0.44 * fta) + tov

                if possessions_per_game == 0:
                    return {}

                scaling_factor = 100.0 / possessions_per_game

                return {
                    "pts_per_100": df["PTS"].mean() * scaling_factor,
                    "reb_per_100": df["REB"].mean() * scaling_factor,
                    "ast_per_100": df["AST"].mean() * scaling_factor,
                    "tov_per_100": tov * scaling_factor,
                }

            per_100_stats = calc_per_100(game_log)

            # Build response
            return {
                "player_name": player_name,
                "season": season,
                "season_stats": season_stats,
                "last_n_stats": last_n_stats,
                "last_n_games": last_n_games,
                "home_stats": home_stats,
                "away_stats": away_stats,
                "wins_stats": wins_stats,
                "losses_stats": losses_stats,
                "trends": trends,
                "per_100_stats": per_100_stats,
                "home_games_count": len(home_games),
                "away_games_count": len(away_games),
                "wins_count": len(wins),
                "losses_count": len(losses),
            }

        except Exception as e:
            logger.error(f"Error fetching performance splits: {str(e)}")
            return self._handle_response_error(e, "get_player_performance_splits")

    # ═══════════════════════════════════════════════════════════════════════════════
    # NBA Awards Methods
    # ═══════════════════════════════════════════════════════════════════════════════

    @staticmethod
    @lru_cache(maxsize=1)
    def load_historical_awards() -> Dict[str, List[Dict]]:
        """
        Load historical awards data from static JSON file.

        This method loads major NBA awards from a static data file containing
        historical winners from 2004-05 through 2023-24. The data is cached
        in memory using LRU cache for instant access on subsequent calls.

        Awards included:
        - MVP (Most Valuable Player)
        - Finals MVP
        - DPOY (Defensive Player of the Year)
        - ROY (Rookie of the Year)
        - SMOY (Sixth Man of the Year)
        - MIP (Most Improved Player)
        - COY (Coach of the Year)

        Returns:
            Dict mapping award types to lists of winners, where each winner
            contains: season, player_name (or coach_name), team, player_id

        Example:
            >>> awards = NBAApiClient.load_historical_awards()
            >>> mvp_winners = awards['mvp']
            >>> print(mvp_winners[0])
            {'season': '2023-24', 'player_name': 'Nikola Jokić', 'team': 'DEN', ...}

        Note:
            - Static method for shared access across all instances
            - LRU cache ensures file is loaded only once
            - File path is relative to this module's location
        """
        # Construct path relative to this file's location
        # Path: nba_mcp/api/client.py → api_documentation/awards_data.json (at project root)
        # __file__ = .../nba_mcp/api/client.py
        # parent = .../nba_mcp/api
        # parent.parent = .../nba_mcp
        # parent.parent.parent = .../ (project root)
        awards_file = Path(__file__).parent.parent.parent / "api_documentation" / "awards_data.json"

        try:
            with open(awards_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Awards data file not found: {awards_file}")
            raise FileNotFoundError(
                f"Awards data file not found at {awards_file}. "
                "Please ensure api_documentation/awards_data.json exists."
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in awards data file: {e}")
            raise ValueError(f"Invalid JSON format in awards data file: {e}")

    def get_award_winners(
        self,
        award_type: str,
        start_season: Optional[str] = None,
        end_season: Optional[str] = None,
        last_n: Optional[int] = None
    ) -> List[Dict]:
        """
        Get award winners from historical data with flexible filtering.

        This method queries the historical awards data with various filtering options:
        - Get last N winners (most recent first)
        - Filter by season range (start and/or end season)
        - Get specific season winner

        Args:
            award_type: Award type identifier. Valid options:
                - "mvp": Most Valuable Player
                - "finals_mvp": Finals MVP
                - "dpoy": Defensive Player of the Year
                - "roy": Rookie of the Year
                - "smoy": Sixth Man of the Year
                - "mip": Most Improved Player
                - "coy": Coach of the Year
            start_season: Filter from this season (inclusive), format "YYYY-YY" (e.g., "2015-16")
            end_season: Filter to this season (inclusive), format "YYYY-YY" (e.g., "2020-21")
            last_n: Get last N winners (most recent first). Overrides season filters if specified.

        Returns:
            List of award winner dictionaries, sorted by season (newest first).
            Each dict contains: season, player_name/coach_name, team, player_id (for players)

        Raises:
            ValueError: If award_type is invalid

        Examples:
            >>> client = NBAApiClient()

            # Get last 10 MVP winners
            >>> mvps = client.get_award_winners("mvp", last_n=10)
            >>> print(len(mvps))  # 10

            # Get DPOY winners from 2018-19 to 2022-23
            >>> dpoy = client.get_award_winners("dpoy", start_season="2018-19", end_season="2022-23")

            # Get 2023-24 ROY winner
            >>> roy = client.get_award_winners("roy", start_season="2023-24", end_season="2023-24")
            >>> print(roy[0]['player_name'])  # "Victor Wembanyama"

        Performance:
            - <10ms response time (in-memory cache)
            - No API calls required
        """
        # Load cached awards data
        awards_data = self.load_historical_awards()

        # Validate award type
        valid_awards = [k for k in awards_data.keys() if k != "metadata"]
        if award_type not in valid_awards:
            available = ", ".join(valid_awards)
            raise ValueError(
                f"Invalid award type '{award_type}'. "
                f"Available awards: {available}"
            )

        # Get winners (copy to avoid modifying cached data)
        winners = awards_data[award_type].copy()

        # Filter by season range if specified
        if start_season or end_season:
            filtered = []
            for winner in winners:
                season = winner.get("season", "")

                # Skip if before start_season
                if start_season and season < start_season:
                    continue

                # Skip if after end_season
                if end_season and season > end_season:
                    continue

                filtered.append(winner)

            winners = filtered

        # Get last N winners (data is already sorted newest first)
        if last_n:
            winners = winners[:last_n]

        return winners

    async def get_player_awards(
        self,
        player_name: str,
        award_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get all awards for a specific player from NBA API.

        This method fetches comprehensive award data for a player directly from
        the NBA API, including major awards, All-NBA/All-Defensive teams, and
        weekly/monthly honors.

        Args:
            player_name: Player name (will be resolved to ID using fuzzy matching)
            award_filter: Optional filter for award description (case-insensitive substring match)
                         Examples: "MVP", "All-NBA", "Player of the Month"

        Returns:
            DataFrame with columns:
            - PERSON_ID: NBA player ID
            - FIRST_NAME, LAST_NAME: Player names
            - TEAM: Team at time of award
            - DESCRIPTION: Award description (e.g., "NBA Most Valuable Player")
            - SEASON: Season in "YYYY-YY" format
            - TYPE: Award type (usually "Award")
            - Additional metadata columns

        Raises:
            ValueError: If player not found

        Examples:
            >>> client = NBAApiClient()

            # Get all LeBron James awards
            >>> lebron_awards = await client.get_player_awards("LeBron James")
            >>> print(len(lebron_awards))  # 100+ awards

            # Get only MVP awards for LeBron
            >>> mvp_awards = await client.get_player_awards("LeBron James", award_filter="MVP")
            >>> print(mvp_awards[['SEASON', 'DESCRIPTION']])

            # Get All-NBA selections
            >>> all_nba = await client.get_player_awards("LeBron James", award_filter="All-NBA")

        Performance:
            - Single API call (cached via Redis)
            - Typical response time: <500ms with cache
            - Cache TTL: 7 days (awards don't change frequently)

        Note:
            - Uses existing player name resolution system
            - Leverages NBA API caching infrastructure
            - Returns empty DataFrame if no awards found (not an error)
        """
        from nba_api.stats.endpoints import playerawards

        # Resolve player name to ID using existing method
        player = self.find_player_by_name(player_name)
        if not player:
            raise ValueError(
                f"Player '{player_name}' not found. "
                "Please check spelling or try a different name variant."
            )

        player_id = player['id']
        logger.debug(f"Fetching awards for {player_name} (ID: {player_id})")

        try:
            # Fetch awards from NBA API (runs in thread to avoid blocking)
            awards_response = await asyncio.to_thread(
                playerawards.PlayerAwards,
                player_id=player_id
            )

            # Extract DataFrame
            awards_df = awards_response.get_data_frames()[0]

            # Apply optional filter
            if award_filter and len(awards_df) > 0:
                awards_df = awards_df[
                    awards_df['DESCRIPTION'].str.contains(
                        award_filter,
                        case=False,
                        na=False
                    )
                ]

            logger.debug(f"Found {len(awards_df)} awards for {player_name}")
            return awards_df

        except Exception as e:
            logger.error(f"Error fetching player awards: {str(e)}")
            raise ValueError(f"Failed to fetch awards for {player_name}: {str(e)}")
