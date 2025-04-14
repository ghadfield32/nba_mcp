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
    
    # Add game status information
    status_text = ""
    if game.get("status") == 3:  # Finished game
        status_text = " (Final)"
    elif game.get("period") > 0:
        period = game.get("period", 0)
        time = game.get("time", "")
        status_text = f" (Period {period}, {time})"
    
    return f"{home_team} vs {visitor_team} - Score: {home_score} to {visitor_score}{status_text}"

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

    if "error" in data:
        return f"Error: {data['error']}"

    if not data.get("data"):
        return f"No games found for {date}."

    games = data["data"]
    formatted_games = [format_game(game) for game in games]
    return "\n---\n".join(formatted_games)

@mcp.tool()
async def get_player_stats(player: str) -> str:
    """
    Get season averages for an NBA player by their name.

    Args:
        player: The name of the player (e.g. "LeBron James")
    """
    client = NBAApiClient()
    result = await client.get_player_stats(player)

    if "error" in result:
        return f"Error: {result['error']}"

    player_name = result["player"]
    season = result["season"]
    stats = result["stats"]

    if not stats:
        return f"No stats found for {player_name} for season {season}."
    
    # Format stats based on available fields
    stats_text = f"""
Player: {player_name}
Season: {season}
"""
    
    # Add stats fields if they exist in the response
    stats_fields = {
        "games_played": "Games Played",
        "pts": "Points Per Game",
        "reb": "Rebounds Per Game",
        "ast": "Assists Per Game",
        "stl": "Steals Per Game",
        "blk": "Blocks Per Game",
        "fg_pct": "Field Goal %",
        "fg3_pct": "3-Point %",
        "ft_pct": "Free Throw %"
    }
    
    for field_key, field_name in stats_fields.items():
        field_key_lower = field_key.lower()
        if field_key_lower in stats:
            stats_text += f"{field_name}: {stats.get(field_key_lower, 'N/A')}\n"
    
    return stats_text

@mcp.tool()
async def get_league_leaders(stat_category: str = "PTS") -> str:
    """
    Get NBA league leaders for a specified stat category.

    Args:
        stat_category: Statistical category (PTS, AST, REB, STL, BLK, etc.)
    """
    client = NBAApiClient()
    result = await client.get_league_leaders(stat_category=stat_category)

    if "error" in result:
        return f"Error: {result['error']}"

    # Check if we have leader data
    if "resultSet" not in result or "rowSet" not in result["resultSet"] or not result["resultSet"]["rowSet"]:
        return f"No league leaders found for {stat_category}."

    # Format the top 5 leaders
    headers = result["resultSet"]["headers"]
    rows = result["resultSet"]["rowSet"]
    
    player_idx = headers.index("PLAYER") if "PLAYER" in headers else -1
    team_idx = headers.index("TEAM") if "TEAM" in headers else -1
    stat_idx = headers.index(stat_category) if stat_category in headers else -1
    
    if player_idx < 0 or stat_idx < 0:
        return f"Could not find {stat_category} data in the response."
    
    formatted_leaders = []
    for i, row in enumerate(rows[:5]):
        player_name = row[player_idx] if player_idx >= 0 else "Unknown"
        team = row[team_idx] if team_idx >= 0 else ""
        stat_value = row[stat_idx] if stat_idx >= 0 else 0
        
        formatted_leaders.append(f"{i+1}. {player_name} ({team}): {stat_value}")
    
    return f"Top 5 {stat_category} Leaders:\n" + "\n".join(formatted_leaders)

#########################################
# Running the Server
#########################################

def main():
    """Entry point for the NBA MCP server."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
