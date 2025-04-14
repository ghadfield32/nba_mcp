from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server with the name "nba"
mcp = FastMCP("nba")

# Constants for the NBA API
NBA_API_BASE = "https://www.balldontlie.io/api/v1"

#########################################
# Helper function to make API requests
#########################################

async def make_nba_request(url: str) -> dict[str, Any] | None:
    """
    Make a request to the NBA API with proper error handling.
    Returns the JSON response as a dictionary, or None if the request fails.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None

#########################################
# Formatting functions
#########################################

def format_game(game: dict) -> str:
    """
    Format a game record into a readable string.
    """
    home_team = game["home_team"]["full_name"]
    visitor_team = game["visitor_team"]["full_name"]
    home_score = game["home_team_score"]
    visitor_score = game["visitor_team_score"]
    return f"{home_team} vs {visitor_team} - Score: {home_score} to {visitor_score}"

#########################################
# MCP Tools
#########################################

@mcp.tool()
async def get_game_scores(date: str) -> str:
    """
    Get NBA game scores for the specified date (in YYYY-MM-DD format).

    Args:
        date: The date of the games, e.g. "2022-12-25"
    """
    url = f"{NBA_API_BASE}/games?dates[]={date}"
    data = await make_nba_request(url)

    if not data or not data.get("data"):
        return "Unable to fetch game data for that date."

    games = data["data"]
    if not games:
        return "No games found for this date."

    formatted_games = [format_game(game) for game in games]
    return "\n---\n".join(formatted_games)

@mcp.tool()
async def get_player_stats(player: str) -> str:
    """
    Get season averages for an NBA player by their name.

    Args:
        player: The (partial) name of the player (e.g. "LeBron")
    """
    # Search for players matching the given name.
    search_url = f"{NBA_API_BASE}/players?search={player}"
    search_data = await make_nba_request(search_url)

    if not search_data or not search_data.get("data"):
        return f"No player found with the name '{player}'."

    players = search_data["data"]
    # For simplicity, use the first player in the results.
    selected_player = players[0]
    player_id = selected_player["id"]

    # Use a fixed season for demonstration (adjust as needed).
    season = 2021
    stats_url = f"{NBA_API_BASE}/season_averages?season={season}&player_ids[]={player_id}"
    stats_data = await make_nba_request(stats_url)

    if not stats_data or not stats_data.get("data"):
        return f"No season averages available for {selected_player['first_name']} {selected_player['last_name']} for season {season}."

    stats_list = stats_data["data"]
    if not stats_list:
        return f"No stats found for {selected_player['first_name']} {selected_player['last_name']} for season {season}."
    
    stats = stats_list[0]
    return f"""
Player: {selected_player['first_name']} {selected_player['last_name']}
Season: {season}
Games Played: {stats.get('games_played', 'N/A')}
Points Per Game: {stats.get('pts', 'N/A')}
Rebounds Per Game: {stats.get('reb', 'N/A')}
Assists Per Game: {stats.get('ast', 'N/A')}
"""

#########################################
# Running the Server
#########################################

if __name__ == "__main__":
    # Run the MCP server using stdio transport
    mcp.run(transport="stdio")
