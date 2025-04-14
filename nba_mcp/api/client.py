from datetime import datetime
import os
from typing import Optional, Dict, Any
import httpx

class NBAApiClient:
    # Updated API base URL
    NBA_API_BASE = "https://api.balldontlie.io/v1"
    NBA_STATS_API_BASE = "https://stats.nba.com/stats"
    NBA_LIVE_API_BASE = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/liveData"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the NBA API client.

        Args:
            api_key: Optional API key for balldontlie API. If not provided, will look for NBA_API_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("NBA_API_KEY", "")

    async def make_request(self, endpoint: str, base_url: Optional[str] = None) -> Dict[str, Any]:
        """Make a request to the NBA API."""
        if base_url is None:
            base_url = self.NBA_API_BASE

        url = f"{base_url}/{endpoint}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://www.nba.com/',
            'x-nba-stats-origin': 'stats',
            'x-nba-stats-token': 'true'
        }

        # Add API key for balldontlie API if available and using that API
        if base_url == self.NBA_API_BASE and self.api_key:
            headers['Authorization'] = self.api_key

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                
                # Enhanced error handling for 404 responses
                if response.status_code == 404:
                    return {
                        "error": f"No data available for the requested resource: {url}",
                        "status_code": 404
                    }
                
                # Raise for other error status codes
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # Handle specific HTTP errors
                return {
                    "error": f"HTTP Error: {e.response.status_code} - {e.response.reason_phrase}",
                    "status_code": e.response.status_code
                }
            except httpx.RequestError as e:
                # Handle request errors (connection, timeout, etc.)
                return {
                    "error": f"Request Error: {str(e)}",
                    "status_code": None
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
            endpoint = f"games?dates[]={date_str}"
            response = await self.make_request(endpoint)

            # Check for error in response from enhanced error handling
            if "error" in response:
                return {
                    "error": response["error"],
                    "data": None
                }

            # Validate response format
            if not isinstance(response, dict):
                return {"error": "Invalid response format", "data": None}

            if "data" not in response:
                return {"error": "No data field in response", "data": None}

            # Check if data is empty
            if not response["data"]:
                return {"error": f"No games found for date: {date_str}", "data": []}

            return response

        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}", "data": None}

    @staticmethod
    def get_season_from_date(date_str: str) -> int:
        """
        Convert a date to the corresponding NBA season year.
        NBA seasons span two years, but are referred to by the year they start in.
        The season typically starts in October and ends in June.
        """
        date = datetime.strptime(date_str, "%Y-%m-%d")
        year = date.year
        # If date is between July and December, it's the start of a new season
        if date.month >= 7:
            return year
        # If date is between January and June, it's the previous year's season
        return year - 1

    async def get_player_stats(self, player_name: str, season: Optional[int] = None) -> dict:
        """
        Get player stats for a specific season or current season if none specified.
        """
        if season is None:
            # Default to current season based on date
            today = datetime.now().strftime("%Y-%m-%d")
            season = self.get_season_from_date(today)

        # First search for the player
        search_url = f"players?search={player_name}"
        player_data = await self.make_request(search_url)

        # Check for error in response from enhanced error handling
        if "error" in player_data:
            return {"error": f"Error searching for player '{player_name}': {player_data['error']}"}

        if not player_data or not player_data.get("data"):
            return {"error": f"No player found matching '{player_name}'"}

        # Find exact match or closest match
        player = None
        for p in player_data["data"]:
            full_name = f"{p['first_name']} {p['last_name']}".lower()
            if player_name.lower() in full_name:
                player = p
                break

        if not player:
            return {"error": f"No exact match found for '{player_name}'"}

        # Get stats for the season
        stats_url = f"season_averages?season={season}&player_ids[]={player['id']}"
        stats = await self.make_request(stats_url)

        # Check for error in response from enhanced error handling
        if "error" in stats:
            return {
                "error": f"Error fetching stats for {player['first_name']} {player['last_name']}, season {season}: {stats['error']}",
                "player": f"{player['first_name']} {player['last_name']}",
                "season": season,
                "stats": None
            }

        # Check if stats data is empty
        if not stats.get("data"):
            return {
                "player": f"{player['first_name']} {player['last_name']}",
                "season": season,
                "stats": None,
                "error": f"No stats available for {player['first_name']} {player['last_name']} in season {season}"
            }

        return {
            "player": f"{player['first_name']} {player['last_name']}",
            "season": season,
            "stats": stats.get("data", [{}])[0] if stats and stats.get("data") else None
        }

    async def get_multi_season_stats(self, player_name: str, num_seasons: int = 5) -> list:
        """
        Get player stats for multiple seasons.
        """
        current_season = self.get_season_from_date(datetime.now().strftime("%Y-%m-%d"))
        seasons = range(current_season - num_seasons + 1, current_season + 1)

        stats = []
        for season in seasons:
            result = await self.get_player_stats(player_name, season)
            if result.get("stats"):
                stats.append(result)

        return stats

    async def get_live_scoreboard(self) -> Dict[str, Any]:
        """
        Get live scoreboard data from the NBA API.

        Returns:
            Dictionary containing live scoreboard data with game details
        """
        try:
            # The NBA live scoreboard endpoint URL
            endpoint = "scoreboard/todaysScoreboard_00.json"
            response = await self.make_request(endpoint, self.NBA_LIVE_API_BASE)
            
            # Check for error in response from enhanced error handling
            if "error" in response:
                return response  # Return the error directly

            # Validate response structure
            if not response or not isinstance(response, dict):
                return {"error": "Invalid response format from live scoreboard API"}
                
            # Check for expected data structure
            if "scoreboard" not in response:
                return {"error": "Expected 'scoreboard' field missing from response"}
                
            return response
        except httpx.HTTPError as e:
            return {"error": f"HTTP error: {str(e)}", "status_code": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    async def get_player_career_stats(self, player_id: str) -> Dict[str, Any]:
        """
        Get career statistics for a specific player.

        Args:
            player_id: NBA player ID (e.g., '203999' for Nikola Jokić)

        Returns:
            Dictionary containing player career statistics
        """
        try:
            # PerMode can be 'Totals', 'PerGame', 'Per36', etc.
            endpoint = f"playercareerstats?PlayerID={player_id}&PerMode=Totals"
            response = await self.make_request(endpoint, self.NBA_STATS_API_BASE)
            
            # Check for error in response from enhanced error handling
            if "error" in response:
                return response
                
            # Validate response structure
            if not response or not isinstance(response, dict):
                return {"error": "Invalid response format from player career stats API"}
                
            # Check for expected data in response
            if "resultSets" not in response or not response["resultSets"]:
                return {"error": "No result sets found in player career stats response"}
                
            return response
        except httpx.HTTPError as e:
            return {"error": f"HTTP error: {str(e)}", "status_code": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    async def get_league_leaders(self, season: str = "2024-25", stat_category: str = "PTS") -> Dict[str, Any]:
        """
        Get league leaders for a specific statistical category.

        Args:
            season: Season in format '2024-25'
            stat_category: Statistical category (PTS, AST, REB, etc.)

        Returns:
            Dictionary containing league leaders data
        """
        try:
            # Convert season format from "2024-25" to "2024-25" required by the API
            season_formatted = season

            # StatCategory can be 'PTS', 'AST', 'REB', etc.
            endpoint = f"leagueleaders?LeagueID=00&PerMode=PerGame&Scope=S&Season={season_formatted}&SeasonType=Regular+Season&StatCategory={stat_category}"
            response = await self.make_request(endpoint, self.NBA_STATS_API_BASE)
            
            # Check for error in response from enhanced error handling
            if "error" in response:
                return response
                
            # Validate response structure
            if not response or not isinstance(response, dict):
                return {"error": "Invalid response format from league leaders API"}
                
            # Check for expected data in response
            if "resultSets" not in response or not response["resultSets"]:
                return {"error": "No result sets found in league leaders response"}
                
            return response
        except httpx.HTTPError as e:
            return {"error": f"HTTP error: {str(e)}", "status_code": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    async def get_league_game_log(self, season: str = "2024-25", team_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get game log data for the league or a specific team.

        Args:
            season: Season in format '2024-25'
            team_id: Optional team ID to filter results

        Returns:
            Dictionary containing game log data
        """
        try:
            # Convert season format from "2024-25" to "2024" format required by the API
            # The API uses the start year of the season
            season_year = season.split('-')[0]

            # Construct endpoint based on whether team_id is provided
            if team_id:
                endpoint = f"leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=DESC&LeagueID=00&PlayerOrTeam=T&Season={season_year}&SeasonType=Regular+Season&TeamID={team_id}"
            else:
                endpoint = f"leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=DESC&LeagueID=00&PlayerOrTeam=T&Season={season_year}&SeasonType=Regular+Season"

            response = await self.make_request(endpoint, self.NBA_STATS_API_BASE)
            
            # Check for error in response from enhanced error handling
            if "error" in response:
                return response
                
            # Validate response structure
            if not response or not isinstance(response, dict):
                return {"error": "Invalid response format from league game log API"}
                
            # Check for expected data in response
            if "resultSets" not in response or not response["resultSets"]:
                return {"error": "No result sets found in league game log response"}
                
            return response
        except httpx.HTTPError as e:
            return {"error": f"HTTP error: {str(e)}", "status_code": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}


