#client.py
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Union
import logging
import sys
import traceback
import re
import asyncio
import pandas as pd
import logging
import json
from pathlib import Path


# Import from nba_api package
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog,
    PlayerProfileV2,
    CommonPlayerInfo,
    PlayerGameLog,
    scoreboardv2
)
from nba_api.stats.static import players, teams
from nba_mcp.api.tools.nba_api_utils import (
    get_player_id, get_team_id, get_team_name, get_player_name,
    get_static_lookup_schema, normalize_stat_category, normalize_per_mode, 
    normalize_season, normalize_date, format_game, normalize_season_type
)


from .tools.scoreboardv2tools import fetch_scoreboard_v2_full
from .tools.live_nba_endpoints import fetch_live_boxsc_odds_playbyplaydelayed_livescores
from .tools.playercareerstats_leagueleaders_tools import (
    get_player_career_stats as _fetch_player_career_stats,
    get_league_leaders as _fetch_league_leaders
)
from .tools.leaguegamelog_tools import fetch_league_game_log
from .tools.playbyplayv3_or_realtime import get_today_games, GameStream
from .tools.playbyplayv3_or_realtime import PastGamesPlaybyPlay

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
            "status_code": getattr(e, "status_code", None)
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
            docs_path = Path('nba_mcp/api_documentation/endpoints.json')
            
            if docs_path.exists():
                logger.info("Loading API documentation from saved file.")
                with open(docs_path, 'r') as f:
                    docs = json.load(f)
                return docs
            else:
                logger.info("Saved API documentation not found, generating documentation.")
                # Import functions from our local api_documentation.py module.
                from .tools.api_documentation import analyze_api_structure
                docs = analyze_api_structure()
                # Save the generated documentation for future use
                docs_path.parent.mkdir(parents=True, exist_ok=True)
                with open(docs_path, 'w') as f:
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
            print(f"DEBUG: Searching for player: '{player_name}'", file=sys.stderr)
            
            if not player_name or not player_name.strip():
                print(f"ERROR: Empty player name provided", file=sys.stderr)
                return None
                
            # Get all players
            print(f"DEBUG: Loading player roster data...", file=sys.stderr)
            all_players = players.get_players()
            print(f"DEBUG: Loaded {len(all_players)} players from roster data", file=sys.stderr)
            
            # Try exact match first (case insensitive)
            player_name_lower = player_name.lower().strip()
            print(f"DEBUG: Attempting exact match for: '{player_name_lower}'", file=sys.stderr)
            
            for player in all_players:
                full_name = f"{player['first_name']} {player['last_name']}".lower()
                if player_name_lower == full_name:
                    print(f"DEBUG: Found exact match for player: {player['first_name']} {player['last_name']} (ID: {player['id']})", file=sys.stderr)
                    return player
            
            # Try matching last name only if no full name match
            for player in all_players:
                if player_name_lower == player['last_name'].lower():
                    print(f"DEBUG: Found match by last name: {player['first_name']} {player['last_name']} (ID: {player['id']})", file=sys.stderr)
                    return player
            
            # If no exact match, try partial match
            print(f"DEBUG: No exact match found, trying partial match...", file=sys.stderr)
            matched_players = []
            for player in all_players:
                full_name = f"{player['first_name']} {player['last_name']}".lower()
                if player_name_lower in full_name:
                    matched_players.append(player)
            
            # Return the most likely match or None
            if matched_players:
                # Sort by name length (shorter names are more likely to be exact matches)
                matched_players.sort(key=lambda p: len(f"{p['first_name']} {p['last_name']}"))
                best_match = matched_players[0]
                print(f"DEBUG: Found best partial match: {best_match['first_name']} {best_match['last_name']} (ID: {best_match['id']})", file=sys.stderr)
                return best_match
            
            print(f"DEBUG: No player match found for '{player_name}'", file=sys.stderr)
            return None
            
        except Exception as e:
            print(f"ERROR: Exception while finding player: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            logger.error(f"Error finding player: {str(e)}")
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
        self,
        player_name: str,
        season: str,
        as_dataframe: bool = True
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
                _fetch_player_career_stats,
                player_name,
                season
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
        season: Optional[str] = None,
        stat_category: str = "PTS",
        per_mode: str = "Totals",
        as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch top league leaders for a season and stat category.

        Args:
            season:      Season string 'YYYY-YY'. Defaults to current season.
            stat_category: e.g. "PTS", "REB", "AST" (synonyms allowed).
            per_mode:    "Totals", "PerGame", or "Per48" (synonyms allowed).
            as_dataframe: If False, returns list of dicts; if True, returns DataFrame or message.

        Returns:
            DataFrame of leader rows, or list‑of‑dicts, or a user-friendly message.
        """
        try:
            # Use current season if none provided
            season_str = season or self.get_season_string()

            df: pd.DataFrame = await asyncio.to_thread(
                _fetch_league_leaders,
                season_str,
                stat_category,
                per_mode
            )

            if not as_dataframe:
                return df.to_dict("records")

            if df.empty:
                return (
                    f"No league leaders found for stat '{stat_category}' "
                    f"in season {season_str}."
                )

            return df

        except Exception as e:
            return self._handle_response_error(e, "get_league_leaders")



    async def get_live_scoreboard(
        self,
        target_date: Optional[Union[str, date, datetime]] = None,
        day_offset: int = 0,              # no longer used by fetch_all_games
        league_id: str = "00",            # ditto
        as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch NBA games (live or by-date) using our unified fetch_all_games helper.
        """
        try:
            # 1) Delegate to our synchronous fetch_all_games
            payload = await asyncio.to_thread(
                fetch_live_boxsc_odds_playbyplaydelayed_livescores,
                target_date and str(target_date) or None
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
                records.append({
                    "gameId": summary["gameId"],
                    "date": payload["date"],
                    "home_team": home.get("teamName") or home.get("TEAM_NAME"),
                    "away_team": away.get("teamName") or away.get("TEAM_NAME"),
                    "home_pts": home.get("score") or home.get("PTS"),
                    "away_pts": away.get("score") or away.get("PTS"),
                    "status": summary.get("gameStatusText") or summary.get("gameStatus"),
                    "period": summary.get("period"),
                    "clock": summary.get("gameClock")
                })

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
        as_dataframe: bool = True
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
                sorter
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



    async def get_today_games(self, as_dataframe: bool = True) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
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


    async def get_game_stream(
        self,
        game_id: str
    ) -> Union[Dict[str, Any], str]:
        """
        Returns either:
          • dict: {
              "gameId": …,
              "markdown": …,
              "snapshot": …,
              "events": …
            }
          • str: an error message
        """
        try:
            # instantiate on background thread
            stream = await asyncio.to_thread(GameStream, game_id)

            # fetch today’s games once (to build the "1. Today’s Games" block)
            games_today = await asyncio.to_thread(GameStream.get_today_games)

            # build the combined payload
            return stream.build_payload(games_today)

        except Exception as e:
            return self._handle_response_error(e, "get_game_stream")
        
        
    async def get_past_play_by_play(
        self,
        *,
        game_id: Optional[str] = None,
        game_date: Optional[str] = None,
        team: Optional[str] = None,
        start_period: int = 1,
        end_period: int = 4,
        start_clock: Optional[str] = None,
        as_records: bool = True,
        timeout: float = 10.0
    ) -> dict[str, Any] | str:
        """
        Fetch historical play-by-play for a past game.

        You may supply **either**:
          • `game_id` (10‑digit NBA game code), or
          • `game_date` (YYYY‑MM‑DD) + `team` name/abbr.

        Optional:
          • `start_period`, `end_period` to limit quarters,
          • `start_clock` to begin mid‑quarter.

        Returns a dict with keys:
          • "AvailableVideo": list of video records  
          • "PlayByPlay"    : list of play records  

        Note: Play‑by‑play is available back to the 1996–97 NBA season.
        """
        try:
            # 1) build the helper (normalizes IDs and dates under the hood)
            pbp = PastGamesPlaybyPlay.from_game_id(
                game_id=game_id,
                game_date=game_date,
                team=team,
                start_period=start_period,
                start_clock=start_clock,
                show_choices=False,
                timeout=timeout
            )

            # 2) fetch the data
            data = pbp.get_pbp(
                start_period=start_period,
                end_period=end_period,
                as_records=as_records,
                timeout=timeout
            )
            return data
        except Exception as e:
            logger.error(f"Error in get_past_play_by_play: {e}")
            return {"error": str(e)}
