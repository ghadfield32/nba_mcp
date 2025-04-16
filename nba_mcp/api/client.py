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
from .tools.playercareerstats_leagueleaders_tools import (
    get_player_career_stats as _fetch_player_career_stats,
    get_league_leaders as _fetch_league_leaders
)
from .tools.leaguegamelog_tools import fetch_league_game_log


# ---------------------------------------------------
# Load static lookups once and create reverse lookups
# ---------------------------------------------------
_TEAM_LOOKUP: Dict[int, str] = {
    t["id"]: t["full_name"] 
    for t in teams.get_teams()
}
_PLAYER_LOOKUP: Dict[int, str] = {
    p["id"]: f"{p['first_name']} {p['last_name']}" 
    for p in players.get_players()
}

# Create reverse lookups (name -> id)
_TEAM_NAME_TO_ID = {name: id for id, name in _TEAM_LOOKUP.items()}
_PLAYER_NAME_TO_ID = {name: id for id, name in _PLAYER_LOOKUP.items()}


def get_player_id(player_name: str) -> Optional[int]:
    """Convert player name to ID, with case-insensitive partial matching."""
    if not player_name:
        return None
    
    player_name_lower = player_name.lower()
    # Try exact match first
    for name, id in _PLAYER_NAME_TO_ID.items():
        if name.lower() == player_name_lower:
            return id
    
    # Try partial match
    for name, id in _PLAYER_NAME_TO_ID.items():
        if player_name_lower in name.lower():
            return id
    
    return None

def get_team_id(team_name: str) -> Optional[int]:
    """Convert team name to ID, with case-insensitive partial matching."""
    if not team_name:
        return None
    
    team_name_lower = team_name.lower()
    # Try exact match first
    for name, id in _TEAM_NAME_TO_ID.items():
        if name.lower() == team_name_lower:
            return id
    
    # Try partial match
    for name, id in _TEAM_NAME_TO_ID.items():
        if team_name_lower in name.lower():
            return id
    
    return None


def normalize_stat_category(stat_category: str) -> str:
    """
    Normalize various string formats of a stat category to the NBA API's expected abbreviation.
    
    For example:
      - "pts", "points" -> "PTS"
      - "reb", "rebound", or "rebounds" -> "REB"
    
    Extend the mapping as needed.
    """
    # Mapping from API abbreviation to a list of acceptable synonyms (all in lower case, spaces removed)
    mapping = {
        "PTS": ["pts", "points"],
        "REB": ["reb", "rebound", "rebounds"],
        "AST": ["ast", "assist", "assists"],
        "STL": ["stl", "steal", "steals"],
        "BLK": ["blk", "block", "blocks"],
        "FGM": ["fgm", "fieldgoalsmade"],
        "FGA": ["fga", "fieldgoalattempts"],
        "FG_PCT": ["fg_pct", "fieldgoalpercentage", "fgpercentage"],
        "FG3M": ["fg3m", "threepointsmade", "3pm"],
        "FG3A": ["fg3a", "threepointsattempted", "3pa"],
        "FG3_PCT": ["fg3_pct", "threepointpercentage", "3ppct"],
        "FTM": ["ftm", "freethrowsmade"],
        "FTA": ["fta", "freethrowsattempted"],
        "FT_PCT": ["ft_pct", "freethrowpercentage"],
        "OREB": ["oreb", "offensiverebounds"],
        "DREB": ["dreb", "defensiverebounds"],
        "EFF": ["eff", "efficiency"],
        "AST_TOV": ["ast_tov", "assistturnover"],
        "STL_TOV": ["stl_tov", "stealturnover"]
    }
    
    # Build a reverse lookup dictionary from each synonym to its API abbreviation.
    synonym_lookup = {}
    for abbr, synonyms in mapping.items():
        for syn in synonyms:
            synonym_lookup[syn] = abbr

    # Normalize the input by trimming whitespace, lowering case, and removing spaces.
    normalized_key = stat_category.strip().lower().replace(" ", "")
    if normalized_key in synonym_lookup:
        return synonym_lookup[normalized_key]
    else:
        raise ValueError(f"Unsupported stat category: {stat_category}")

def normalize_per_mode(per_mode: str) -> str:
    """
    Normalize the per_mode parameter to one of the allowed values:
    "Totals", "PerGame", or "Per48".
    
    Accepts variations such as lower or upper case, and common synonyms.
    """
    normalized = per_mode.strip().lower()
    if normalized in ["totals", "total", "total stats", "total per season", "total per game"]:
        return "Totals"
    elif normalized in ["avg", "average", "pergame", "per game", "per game average", "per game average stats", "per game per season"]:
        return "PerGame"
    elif normalized in ["per48", "per 48", "per 48 average", "per 48 average stats", "per 48 per season", "per 48 minutes"]:
        return "Per48"
    else:
        raise ValueError(f"Unsupported per_mode value: {per_mode}")


def normalize_season(season: str) -> str:
    """
    Normalize the season parameter to the expected format:
    "YYYY-YY" (e.g. "2024-25").
    
    Handles various inputs:
    - 2-digit year (e.g., "24") - interpreted as 2000s for values < 59
    - 4-digit year (e.g., "2024")
    - Already formatted "YYYY-YY" season
    """
    # Strip any whitespace
    season = season.strip()
    season = season.replace("'", "").replace("_", "")
    
    # Handle 2-digit year (e.g., "24")
    if len(season) == 2 and season.isdigit():
        year = int(season)
        # Interpret years below 59 as 2000s, otherwise as 1900s
        full_year = 2000 + year if year < 59 else 1900 + year
        next_year = str(full_year + 1)[2:]
        return f"{full_year}-{next_year}"
    
    # Handle 4-digit year (e.g., "2024")
    elif len(season) == 4 and season.isdigit():
        year = int(season)
        next_year = str(year + 1)[2:]
        return f"{year}-{next_year}"
    
    # Handle already formatted season (e.g., "2024-25" or "24-25")
    elif "-" in season and len(season.split("-")) == 2:
        parts = season.split("-")
        
        # If it's a short format like "24-25", convert to "2024-25"
        if len(parts[0]) == 2 and parts[0].isdigit():
            year = int(parts[0])
            full_year = 2000 + year if year < 59 else 1900 + year
            return f"{full_year}-{parts[1]}"
        
        # If it's already in "YYYY-YY" format, return as is
        return season
    
    # Unsupported format
    else:
        raise ValueError(f"Unsupported season value: {season}")
    
    
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
        day_offset: int = 0,
        league_id: str = "00",
        as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]], str]:
        """
        Fetch the NBA scoreboard (live or any specific date) using the
        full-featured ScoreboardV2 helper.
        
        Args:
            target_date: Date for which to fetch games (string, date, datetime).
            day_offset: Day offset (e.g. -1 for yesterday).
            league_id: League code ("00" for NBA).
            as_dataframe: If False, returns a list of dicts; if True, returns DataFrame or message.
        
        Returns:
            DataFrame of game records, a list of dicts, or a user-friendly message.
        """
        try:
            # Delegate to synchronous fetcher in a background thread
            df = await asyncio.to_thread(
                fetch_scoreboard_v2_full,
                target_date,
                day_offset,
                league_id
            )

            # Return raw records if requested
            if not as_dataframe:
                return df.to_dict("records")

            # If no games found, notify user
            if df.empty:
                return "No games found for that date."

            # Otherwise, return the DataFrame
            return df

        except Exception as e:
            # Route through your standard error‐handler for consistency
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

