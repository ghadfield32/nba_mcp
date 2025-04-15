from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Union
import logging
import sys
import traceback
import re
import asyncio


# Import from nba_api package
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog,
    PlayerProfileV2,
    CommonPlayerInfo,
    PlayerGameLog
)
from nba_api.stats.static import players, teams

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

    async def get_games_by_date(self, date_str: str) -> Dict[str, Any]:
        """
        Get NBA games for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Dictionary containing game data
        """
        try:
            # Parse the date string to date object
            try:
                game_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return {"error": f"Invalid date format: {date_str}. Please use YYYY-MM-DD format.", "data": None, "query_date": date_str}
            
            # Get scoreboard data for the date - ScoreBoard doesn't accept game_date but uses date as a property
            try:
                # First create the scoreboard without parameters, then set date if needed
                sb = scoreboard.ScoreBoard()
                if game_date != date.today():
                    # Update the internal date property - this is what the API actually uses
                    sb.game_date = game_date
                data = sb.get_dict()
            except Exception as e:
                return {"error": f"Failed to retrieve scoreboard: {str(e)}", "data": None, "query_date": date_str}
            
            # Check if data exists and has the expected structure
            if not data or "scoreboard" not in data or "games" not in data["scoreboard"]:
                return {"error": "No games data available for this date", "data": None, "query_date": date_str}
                
            # Format the data to match the expected structure
            formatted_games = []
            games_list = data["scoreboard"]["games"]
            
            if not games_list:
                # Return empty array but with clear indication there were no games scheduled
                return {"data": [], "message": f"No games scheduled on {game_date.strftime('%B %d, %Y')}.", "query_date": date_str}
                
            for game in games_list:
                try:
                    home_team = {
                        "full_name": game["homeTeam"]["teamName"],
                        "id": game["homeTeam"]["teamId"]
                    }
                    visitor_team = {
                        "full_name": game["awayTeam"]["teamName"],
                        "id": game["awayTeam"]["teamId"]
                    }
                    
                    formatted_game = {
                        "id": game["gameId"],
                        "home_team": home_team,
                        "visitor_team": visitor_team,
                        "home_team_score": int(game.get("homeTeam", {}).get("score", 0)),
                        "visitor_team_score": int(game.get("awayTeam", {}).get("score", 0)),
                        "status": game["gameStatus"],
                        "period": game.get("period", 0),
                        "time": game.get("gameClock", ""),
                        "date": date_str
                    }
                    formatted_games.append(formatted_game)
                except (KeyError, TypeError) as e:
                    logger.warning(f"Error formatting game data: {str(e)}")
                    continue
            
            return {"data": formatted_games, "query_date": date_str}
            
        except Exception as e:
            return self._handle_response_error(e, "get_games_by_date")

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
            # Find the player
            print(f"DEBUG: Starting player stats lookup for '{player_name}'", file=sys.stderr)
            player = self.find_player_by_name(player_name)
            
            if not player:
                error_msg = f"No player found matching '{player_name}'"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return {"error": error_msg}
            
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
                player_id = player["id"]
                print(f"DEBUG: Fetching stats for player ID {player_id} ({player['first_name']} {player['last_name']})", file=sys.stderr)
                
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
                    game_log = PlayerGameLog(player_id=player["id"], season=season_string)
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
                                "player_id": player["id"],
                                "games_played": games_played,
                                "pts": round(pts_sum / games_played, 1) if games_played > 0 else 0,
                                "reb": round(reb_sum / games_played, 1) if games_played > 0 else 0,
                                "ast": round(ast_sum / games_played, 1) if games_played > 0 else 0,
                            }
                
                # If we still don't have stats, return error
                if not season_stats:
                    return {
                        "player": f"{player['first_name']} {player['last_name']}",
                        "season": season_year,
                        "stats": None,
                        "error": f"No stats available for {player['first_name']} {player['last_name']} in season {season_string}"
                    }
                
                # Return the player stats
                return {
                    "player": f"{player['first_name']} {player['last_name']}",
                    "season": season_year,
                    "stats": season_stats
                }
                
            except Exception as e:
                return {
                    "error": f"Error fetching stats for {player['first_name']} {player['last_name']}, season {season_string}: {str(e)}",
                    "player": f"{player['first_name']} {player['last_name']}",
                    "season": season_year,
                    "stats": None
                }
                
        except Exception as e:
            return self._handle_response_error(e, "get_player_stats")

    async def get_live_scoreboard(self) -> Dict[str, Any]:
        """
        Get live scoreboard data from the NBA API.

        Returns:
            Dictionary containing live scoreboard data with game details including:
            - meta: API metadata including version, request URL, timestamp, and status code
            - scoreboard: Game data including gameDate, leagueId, leagueName, and games array
        """
        
        try:
            # Create scoreboard instance
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
                
            # Return the complete data structure (includes meta and scoreboard)
            return data
            
        except Exception as e:
            return self._handle_response_error(e, "get_live_scoreboard")

    async def get_player_career_stats(self, player_id: str) -> Dict[str, Any]:
        """
        Get career statistics for a specific player.

        Args:
            player_id: NBA player ID (e.g., '203999' for Nikola Jokić)

        Returns:
            Dictionary containing player career statistics
        """
        try:
            # Convert string player_id to integer if needed
            if isinstance(player_id, str) and player_id.isdigit():
                player_id = int(player_id)
                
            career = playercareerstats.PlayerCareerStats(player_id=player_id)
            data = career.get_dict()
            
            # Validate response structure
            if not data or "resultSets" not in data:
                return {"error": "Invalid response format from player career stats API"}
                
            # Check for expected data in response
            if not data["resultSets"]:
                return {"error": "No result sets found in player career stats response"}
                
            return data
            
        except Exception as e:
            return self._handle_response_error(e, "get_player_career_stats")

    async def get_league_leaders(self, season: str = None, stat_category: str = "PTS") -> Dict[str, Any]:
        """
        Get league leaders for a specific statistical category.

        Args:
            season: Season in format 'YYYY-YY' (e.g., '2023-24')
            stat_category: Statistical category (PTS, AST, REB, etc.)

        Returns:
            Dictionary containing league leaders data
        """
        try:
            # Get season string if not provided
            if season is None:
                season = self.get_season_string()
                
            leaders = LeagueLeaders(season=season, stat_category=stat_category)
            data = leaders.get_dict()
            
            # Validate response structure
            if not data or "resultSet" not in data:
                return {"error": "Invalid response format from league leaders API"}
                
            # Check for expected data in response
            if "rowSet" not in data["resultSet"] or not data["resultSet"]["rowSet"]:
                return {"error": "No leaders data found in response"}
                
            return data
            
        except Exception as e:
            return self._handle_response_error(e, "get_league_leaders")

    async def get_league_game_log(self, season: str = None, team_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get game log data for the league or a specific team.

        Args:
            season: Season in format 'YYYY-YY' (e.g., '2023-24')
            team_id: Optional team ID to filter results

        Returns:
            Dictionary containing game log data
        """
        try:
            # Get season string if not provided
            if season is None:
                season = self.get_season_string()
                
            # Convert team_id to integer if provided as string
            if team_id and isinstance(team_id, str) and team_id.isdigit():
                team_id = int(team_id)
                
            # Get game log data
            if team_id:
                game_log = LeagueGameLog(season=season, team_id_nullable=team_id)
            else:
                game_log = LeagueGameLog(season=season)
                
            data = game_log.get_dict()
            
            # Validate response structure
            if not data or "resultSets" not in data:
                return {"error": "Invalid response format from league game log API"}
                
            # Check for expected data in response
            if not data["resultSets"] or "rowSet" not in data["resultSets"][0]:
                return {"error": "No game log data found in response"}
                
            return data
            
        except Exception as e:
            return self._handle_response_error(e, "get_league_game_log")
        
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


