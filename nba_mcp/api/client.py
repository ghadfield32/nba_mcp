# client.py
import asyncio
import json
import logging
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

# Import from nba_api package
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    CommonPlayerInfo,
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
            # 1) Delegate to our synchronous fetch_all_games
            payload = await asyncio.to_thread(
                fetch_live_boxsc_odds_playbyplaydelayed_livescores,
                target_date and str(target_date) or None,
            )
            games = payload["games"]  # list of game‐dicts
            if not as_dataframe:
                return games

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
