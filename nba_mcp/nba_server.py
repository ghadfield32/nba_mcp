from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient

# Initialize FastMCP server with the name "nba"
mcp = FastMCP("nba")

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
    client = NBAApiClient()
    data = await client.get_games_by_date(date)

    if not data or "error" in data or not data.get("data"):
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
    client = NBAApiClient()
    result = await client.get_player_stats(player)

    if "error" in result:
        return result["error"]

    player_name = result["player"]
    season = result["season"]
    stats = result["stats"]

    if not stats:
        return f"No stats found for {player_name} for season {season}."

    return f"""
Player: {player_name}
Season: {season}
Games Played: {stats.get('games_played', 'N/A')}
Points Per Game: {stats.get('pts', 'N/A')}
Rebounds Per Game: {stats.get('reb', 'N/A')}
Assists Per Game: {stats.get('ast', 'N/A')}
"""

#########################################
# Running the Server
#########################################

def main():
    """Entry point for the NBA MCP server."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
