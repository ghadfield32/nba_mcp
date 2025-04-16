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
                from tools.api_documentation import analyze_api_structure
                docs = analyze_api_structure()
                # Save the generated documentation for future use
                docs_path.parent.mkdir(parents=True, exist_ok=True)
                with open(docs_path, 'w') as f:
                    json.dump(docs, f, indent=2)
                return docs
        except Exception as e:
            logger.error(f"Error in get_api_documentation: {str(e)}")
            return {"error": f"Failed to load API documentation: {str(e)}"}
        
    async def get_games_by_date(
        target_date: Optional[date] = None,
        max_days_back: int = 7
    ) -> pd.DataFrame:
        """
        Find the most recent day (within max_days_back days) that had NBA games and return game details.
        
        Args:
            target_date: Specific date to start searching from (defaults to today).
            max_days_back: Maximum number of days to search back if no games on target_date.
        
        Returns:
            A pandas DataFrame containing game data.
        """
        if target_date is None:
            target_date = date.today()
        
        for days_back in range(max_days_back):
            check_date = target_date - timedelta(days=days_back)
            date_str = check_date.strftime("%m/%d/%Y")
            
            try:
                sb2 = scoreboardv2.ScoreboardV2(game_date=date_str)
                headers = sb2.game_header.get_data_frame()
                lines = sb2.line_score.get_data_frame()
            except Exception as e:
                logger.warning(f"Error fetching data for {date_str}: {str(e)}")
                continue

            if headers.empty:
                continue

            # Merge headers with line scores
            merged = headers.merge(lines, on="GAME_ID", suffixes=("", "_line"))
            games_list = []

            for game_id in merged["GAME_ID"].unique():
                game_data = merged[merged["GAME_ID"] == game_id]
                try:
                    home_row = game_data[game_data["HOME_TEAM_ID"] == game_data["TEAM_ID"]].iloc[0]
                    away_row = game_data[game_data["VISITOR_TEAM_ID"] == game_data["TEAM_ID"]].iloc[0]
                except IndexError as ie:
                    logger.warning(f"Could not find complete data for game {game_id}: {str(ie)}")
                    continue
                    
                games_list.append({
                    "date": pd.to_datetime(home_row["GAME_DATE_EST"]).date(),
                    "game_id": game_id,
                    "status": home_row["GAME_STATUS_TEXT"],
                    "home_team": _TEAM_LOOKUP.get(int(home_row["TEAM_ID"])),
                    "home_pts": home_row["PTS"],
                    "home_fg_pct": home_row.get("FG_PCT", 0),
                    "away_team": _TEAM_LOOKUP.get(int(away_row["TEAM_ID"])),
                    "away_pts": away_row["PTS"],
                    "away_fg_pct": away_row.get("FG_PCT", 0),
                    "game_time": home_row.get("GAME_STATUS_TEXT", ""),
                    "attendance": home_row.get("ATTENDANCE", 0),
                    "game_duration": home_row.get("GAME_TIME", "")
                })

            if games_list:
                df = pd.DataFrame(games_list)
                # Convert fraction values to percentage format for readability.
                pct_columns = [col for col in df.columns if 'pct' in col.lower()]
                for col in pct_columns:
                    df[col] = df[col].multiply(100).round(1)
                logger.info(f"Found games on {date_str}")
                return df
        # If no games found, return an empty DataFrame with standard columns.
        columns = [
            "date", "game_id", "status",
            "home_team", "home_pts", "home_fg_pct",
            "away_team", "away_pts", "away_fg_pct",
            "game_time", "attendance", "game_duration"
        ]
        logger.warning("No games found in the lookback window.")
        return pd.DataFrame(columns=columns)


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

    async def get_player_stats(self, player_name: str, season: Optional[int] = None) -> Dict[str, Any]:
        """
        Get player stats for a specific season or current season if none specified.
        
        Args:
            player_name: Name of the player
            season: Season year (e.g., 2023 for the 2023-24 season)
            
        Returns:
            Dictionary with player stats
        """
        try:
            # Get player ID using the lookup function
            player_id = get_player_id(player_name)
            
            if not player_id:
                error_msg = f"No player found matching '{player_name}'"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return {"error": error_msg}
            
            # Get player name from the lookup for display
            player_name_display = player_name
            # We could also retrieve the full name from the PLAYER_LOOKUP if needed
            
            # Get season string
            if season is None:
                season_string = self.get_season_string()
                season_year = int(season_string.split('-')[0])
                print(f"DEBUG: Using current season: {season_string}", file=sys.stderr)
            else:
                season_string = self.get_season_string(season)
                season_year = season
                print(f"DEBUG: Using specified season: {season_string}", file=sys.stderr)
            
            # Get player game averages
            try:
                print(f"DEBUG: Fetching stats for player ID {player_id} ({player_name})", file=sys.stderr)
                
                # Use PlayerProfileV2 to get season averages
                print(f"DEBUG: Calling PlayerProfileV2 API...", file=sys.stderr)
                profile = PlayerProfileV2(player_id=player_id, per_mode36="PerGame")
                
                # Extract season averages from the response
                print(f"DEBUG: Getting response data from API...", file=sys.stderr)
                profile_data = profile.get_dict()
                
                # Find the season stats from the profile data
                season_stats = None
                
                print(f"DEBUG: Searching for season {season_string} in profile data...", file=sys.stderr)
                
                # Check if we have valid result sets
                if not profile_data.get("resultSets") or len(profile_data.get("resultSets", [])) == 0:
                    error_msg = "No data returned from player profile API"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    return {"error": error_msg}
                
                if "seasonTotalsRegularSeason" in profile_data.get("resultSets", [{}])[0]:
                    headers = profile_data["resultSets"][0]["headers"]
                    rows = profile_data["resultSets"][0]["rowSet"]
                    
                    print(f"DEBUG: Found {len(rows)} season records in profile data", file=sys.stderr)
                    
                    # Find index of SEASON_ID column
                    season_id_index = headers.index("SEASON_ID") if "SEASON_ID" in headers else -1
                    
                    if season_id_index == -1:
                        print(f"WARNING: Could not find SEASON_ID column in headers: {headers}", file=sys.stderr)
                    
                    # Convert season string to NBA API format (e.g., "2023-24" -> "2023-24")
                    target_season_id = season_string
                    
                    # Find the row matching the season
                    for row in rows:
                        if season_id_index >= 0 and row[season_id_index] == target_season_id:
                            # Create a dictionary with stats
                            print(f"DEBUG: Found matching season: {target_season_id}", file=sys.stderr)
                            season_stats = {header.lower(): value for header, value in zip(headers, row)}
                            break
                 
                # If we couldn't find stats in the profile, try PlayerGameLog
                if not season_stats:
                    print(f"DEBUG: No season stats found in profile data, trying PlayerGameLog...", file=sys.stderr)
                    game_log = PlayerGameLog(player_id=player_id, season=season_string)
                    games_data = game_log.get_dict()
                    
                    if games_data.get("resultSets", [{}])[0].get("rowSet"):
                        # Calculate averages from game logs
                        headers = games_data["resultSets"][0]["headers"]
                        rows = games_data["resultSets"][0]["rowSet"]
                        
                        # Create stats from game logs
                        games_played = len(rows)
                        print(f"DEBUG: Found {games_played} games in player game log", file=sys.stderr)
                        
                        if games_played > 0:
                            # Get indices for the stats we care about
                            pts_index = headers.index("PTS") if "PTS" in headers else -1
                            reb_index = headers.index("REB") if "REB" in headers else -1
                            ast_index = headers.index("AST") if "AST" in headers else -1
                            min_index = headers.index("MIN") if "MIN" in headers else -1
                            
                            print(f"DEBUG: Calculating averages from game logs", file=sys.stderr)
                            # Calculate averages
                            pts_sum = sum(row[pts_index] for row in rows if pts_index >= 0)
                            reb_sum = sum(row[reb_index] for row in rows if reb_index >= 0)
                            ast_sum = sum(row[ast_index] for row in rows if ast_index >= 0)
                            
                            season_stats = {
                                "season_id": season_string,
                                "player_id": player_id,
                                "games_played": games_played,
                                "pts": round(pts_sum / games_played, 1) if games_played > 0 else 0,
                                "reb": round(reb_sum / games_played, 1) if games_played > 0 else 0,
                                "ast": round(ast_sum / games_played, 1) if games_played > 0 else 0,
                            }
                
                # If we still don't have stats, return error
                if not season_stats:
                    return {
                        "player": f"{player_name_display}",
                        "season": season_year,
                        "stats": None,
                        "error": f"No stats available for {player_name_display} in season {season_string}"
                    }
                
                # Return the player stats
                return {
                    "player": f"{player_name_display}",
                    "season": season_year,
                    "stats": season_stats
                }
                
            except Exception as e:
                return {
                    "error": f"Error fetching stats for {player_name_display}, season {season_string}: {str(e)}",
                    "player": f"{player_name_display}",
                    "season": season_year,
                    "stats": None
                }
                
        except Exception as e:
            return self._handle_response_error(e, "get_player_stats")

    async def get_live_scoreboard(self, as_dataframe: bool = True) -> Union[Dict[str, Any], pd.DataFrame]:
        """
        Fetch the current NBA scoreboard with live game data.
        
        Args:
            as_dataframe: If True, returns a pandas DataFrame; otherwise, returns raw dict data.
            
        Returns:
            The scoreboard data in the specified format.
            
        Note:
            The response contains:
                - meta: API metadata including version, request URL, timestamp, and status code
                - scoreboard: Game data including gameDate, leagueId, leagueName, and games array
        """
        
        try:
            # Create scoreboard instance - no date parameter needed for live
            sb = scoreboard.ScoreBoard()
            
            # Get raw data dictionary
            data = sb.get_dict()
            
            # Validate response structure
            if not data:
                return {"error": "Empty response from live scoreboard API"}
                
            # The response should contain both meta and scoreboard sections
            if "meta" not in data:
                return {"error": "Missing meta section in scoreboard response"}
                
            if "scoreboard" not in data:
                return {"error": "Missing scoreboard section in response"}
                
            # Check for expected data structure in scoreboard section
            if "gameDate" not in data["scoreboard"] or "games" not in data["scoreboard"]:
                return {"error": "Invalid scoreboard data structure"}
                
            # If not requesting DataFrame, return the complete raw data
            if not as_dataframe:
                return data
            
            # Extract games for DataFrame conversion
            games = data.get("scoreboard", {}).get("games", [])
            
            # Return as DataFrame
            return pd.DataFrame(games)
                
        except Exception as e:
            return self._handle_response_error(e, "get_live_scoreboard")

    async def get_player_career_stats(self, player_name_or_id: str, as_dataframe: bool = True) -> Union[Dict[str, Any], pd.DataFrame]:
        """
        Retrieve career stats for an NBA player, given either name or ID.
        
        Args:
            player_name_or_id: Player name (e.g., "LeBron James") or numeric string ID.
            as_dataframe: If True, return a pandas DataFrame; otherwise, return the raw dict.
            
        Returns:
            The career statistics as DataFrame or dict.
            
        Raises:
            ValueError: If the player cannot be found.
        """
        # Resolve player ID: if already numeric use it; otherwise use the lookup function
        if player_name_or_id.isdigit():
            pid = player_name_or_id
        else:
            # Find the player ID using the lookup function
            pid = get_player_id(player_name_or_id)
            if not pid:
                raise ValueError(f"No player found matching '{player_name_or_id}'")
        
        try:
            career = playercareerstats.PlayerCareerStats(player_id=pid)
            if as_dataframe:
                df = career.get_data_frames()[0]
                logger.info(f"Retrieved career stats for player ID {pid}")
                return df
            else:
                return career.get_dict()
        except Exception as e:
            logger.error(f"Error in get_player_career_stats: {str(e)}")
            return {"error": f"Error fetching career stats: {str(e)}"}

    async def get_league_leaders(
        self, 
        season: str, 
        stat_category: str = "PTS", 
        as_dataframe: bool = True
    ) -> Union[Dict[str, Any], pd.DataFrame]:
        """
        Retrieve league leaders for a specified season and statistical category.
        
        Args:
            season: Season string in the format 'YYYY-YY' (e.g. '2024-25').
            stat_category: Statistical category such as "PTS", "AST", etc. Accepts various synonyms.
            as_dataframe: If True, returns a pandas DataFrame; otherwise, returns raw dict data.
            
        Returns:
            League leaders data in the desired format.
        """
        try:
            # Normalize the input stat_category
            normalized_stat = normalize_stat_category(stat_category)
            
            # Create the parameters expected by the NBA API endpoint
            leaders = LeagueLeaders(
                league_id="00",
                per_mode48="Totals",
                scope="S",
                season=season,
                season_type_all_star="Regular Season",
                stat_category_abbreviation=normalized_stat,
                active_flag_nullable=""
            )
            
            if as_dataframe:
                df = leaders.get_data_frames()[0]
                logger.info(f"Retrieved league leaders for season {season}, category {normalized_stat}")
                return df
            else:
                return leaders.get_dict()
        except Exception as e:
            logger.error(f"Error in get_league_leaders: {str(e)}")
            return {"error": f"Error fetching league leaders: {str(e)}"}

    async def get_league_game_log(self, 
        season: str,
        team_name_or_id: Optional[str] = None,
        as_dataframe: bool = True
    ) -> Union[Dict[str, Any], pd.DataFrame]:
        """
        Retrieve the league game log for a given season and optionally filter by team.
        
        Args:
            season: Season string in format 'YYYY-YY' (e.g., '2024-25').
            team_name_or_id: Optional team name or numeric ID.
            as_dataframe: If True, returns a pandas DataFrame; otherwise, returns the raw dictionary.
        
        Returns:
            League game log data in the selected format.
            
        Raises:
            ValueError: If team lookup fails.
        """
        tid: Optional[Union[int, str]] = None
        if team_name_or_id:
            if team_name_or_id.isdigit():
                tid = team_name_or_id
            else:
                # Use the team lookup function
                tid = get_team_id(team_name_or_id)
                if tid is None:
                    raise ValueError(f"No team found matching '{team_name_or_id}'")

        try:
            if tid:
                log = LeagueGameLog(season=season, team_id=int(tid))
            else:
                log = LeagueGameLog(season=season)
                
            if as_dataframe:
                df = log.get_data_frames()[0]
                # If filtering by team and no rows found, patch log to return an empty dataframe.
                if df.empty:
                    def _empty_get_frames():
                        return [pd.DataFrame(columns=df.columns)]
                    log.get_data_frames = _empty_get_frames  # type: ignore
                    return log.get_data_frames()[0]
                return df
            else:
                return log.get_dict()
        except Exception as e:
            logger.error(f"Error in get_league_game_log: {str(e)}")
            return {"error": f"Error fetching game log: {str(e)}"}
        
    async def get_most_recent_game_date(self, lookback_days: int = 7) -> Dict[str, Any]:
        """
        Find the most recent date that had NBA games, looking back up to lookback_days.

        Args:
            lookback_days: Maximum number of days to look back (default: 7)

        Returns:
            Dictionary containing either:
              - date:        "YYYY-MM-DD"
              - formatted_date: "Month DD, YYYY"
              - games:       [ ... list of game dicts ... ]
            or, on failure:
              - error:       error message
        """
        print(f"DEBUG: Looking for most recent games (up to {lookback_days} days back)", file=sys.stderr)

        today = date.today()

        for days_back in range(lookback_days):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%Y-%m-%d")

            print(f"DEBUG: Checking for games on {date_str}", file=sys.stderr)
            result = await self.get_games_by_date(date_str)

            # If the API returned an error, skip this date
            if "error" in result:
                print(f"DEBUG: Error checking {date_str}: {result['error']}", file=sys.stderr)
                continue

            # If we found non-empty data, return it immediately
            if result.get("data"):
                print(f"DEBUG: Found games on {date_str}", file=sys.stderr)
                return {
                    "date": date_str,
                    "formatted_date": check_date.strftime("%B %d, %Y"),
                    "games": result["data"]
                }

        # No games found in the lookback window
        return {
            "error": f"No games found in the last {lookback_days} days"
        }

    async def get_player_stats_bulk(self, player_name: str, seasons: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Get player stats for multiple seasons efficiently.
        
        Args:
            player_name: Name of the player
            seasons: List of season years (e.g., [2023, 2022, 2021] for recent seasons)
                    If None, returns the last 5 seasons
                    
        Returns:
            Dictionary with player stats for multiple seasons
        """
        try:
            # Find the player once for all seasons
            print(f"DEBUG: Starting bulk player stats lookup for '{player_name}'", file=sys.stderr)
            player = self.find_player_by_name(player_name)
            
            if not player:
                error_msg = f"No player found matching '{player_name}'"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return {"error": error_msg}
            
            # If no seasons provided, use the last 5 seasons
            current_season_year = int(self.get_season_string().split('-')[0])
            
            if not seasons:
                # Default to the last 5 seasons
                seasons = list(range(current_season_year, current_season_year - 5, -1))
                print(f"DEBUG: No seasons specified, using last 5 seasons: {seasons}", file=sys.stderr)
            
            # Get player career stats - this gives us all seasons in one request
            player_id = player["id"]
            print(f"DEBUG: Fetching career stats for player ID {player_id} ({player['first_name']} {player['last_name']})", file=sys.stderr)
            
            try:
                # Use PlayerCareerStats to get stats for all seasons at once
                career = playercareerstats.PlayerCareerStats(player_id=player_id, per_mode36="PerGame")
                
                # Extract the stats from the response
                career_data = career.get_dict()
                
                if "resultSets" not in career_data or len(career_data["resultSets"]) == 0:
                    return {
                        "error": "No career data available for this player",
                        "player": f"{player['first_name']} {player['last_name']}",
                        "seasons": seasons
                    }
                
                # Find regular season totals in the result sets
                season_stats_list = []
                
                # Look for the season totals in the result sets
                for result_set in career_data["resultSets"]:
                    if result_set.get("name") == "SeasonTotalsRegularSeason":
                        headers = result_set["headers"]
                        rows = result_set["rowSet"]
                        
                        # Find index of SEASON_ID column
                        season_id_index = headers.index("SEASON_ID") if "SEASON_ID" in headers else -1
                        
                        if season_id_index == -1:
                            print(f"WARNING: Could not find SEASON_ID column in headers", file=sys.stderr)
                            continue
                        
                        # Process all rows in the result set
                        for row in rows:
                            # Convert season_id to year (e.g., "2023-24" -> 2023)
                            season_id = row[season_id_index]
                            try:
                                season_year = int(season_id.split('-')[0])
                                
                                # Skip seasons we don't want
                                if seasons and season_year not in seasons:
                                    continue
                                    
                                # Create a dictionary with stats for this season
                                season_stats = {
                                    "season_id": season_id,
                                    "season_year": season_year,
                                    "stats": {header.lower(): value for header, value in zip(headers, row)}
                                }
                                season_stats_list.append(season_stats)
                            except (ValueError, IndexError, AttributeError) as e:
                                print(f"WARNING: Error processing season {season_id}: {str(e)}", file=sys.stderr)
                                continue
                
                # Sort seasons by year (newest first)
                season_stats_list.sort(key=lambda x: x["season_year"], reverse=True)
                
                # Return the stats
                return {
                    "player": f"{player['first_name']} {player['last_name']}",
                    "seasons_requested": seasons,
                    "seasons_found": [s["season_year"] for s in season_stats_list],
                    "season_stats": season_stats_list
                }
                
            except Exception as e:
                return {
                    "error": f"Error fetching stats for {player['first_name']} {player['last_name']}: {str(e)}",
                    "player": f"{player['first_name']} {player['last_name']}",
                    "seasons": seasons
                }
                
        except Exception as e:
            return self._handle_response_error(e, "get_player_stats_bulk")
        


