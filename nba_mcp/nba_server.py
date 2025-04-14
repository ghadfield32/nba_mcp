from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback

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
    print(f"DEBUG: Attempting to get game scores for date: {date}", file=sys.stderr)
    client = NBAApiClient()
    try:
        data = await client.get_games_by_date(date)
        
        if "error" in data:
            print(f"ERROR: Failed to get game scores: {data['error']}", file=sys.stderr)
            return f"Error: {data['error']}"

        if not data.get("data"):
            print(f"DEBUG: No games found for date: {date}", file=sys.stderr)
            return f"No games found for {date}."

        games = data["data"]
        print(f"DEBUG: Successfully found {len(games)} games for date: {date}", file=sys.stderr)
        formatted_games = [format_game(game) for game in games]
        return "\n---\n".join(formatted_games)
    except Exception as e:
        error_msg = f"Unexpected error in get_game_scores: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"

@mcp.tool()
async def get_player_stats(player: str) -> str:
    """
    Get season averages for an NBA player by their name.

    Args:
        player: The name of the player (e.g. "LeBron James")
    """
    print(f"DEBUG: Attempting to get player stats for: {player}", file=sys.stderr)
    client = NBAApiClient()
    try:
        result = await client.get_player_stats(player)

        if "error" in result:
            print(f"ERROR: Failed to get player stats: {result['error']}", file=sys.stderr)
            return f"Error: {result['error']}"

        player_name = result["player"]
        season = result["season"]
        stats = result["stats"]

        if not stats:
            print(f"DEBUG: No stats found for player: {player_name}", file=sys.stderr)
            return f"No stats found for {player_name} for season {season}."
        
        print(f"DEBUG: Successfully retrieved stats for {player_name}", file=sys.stderr)
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
    except Exception as e:
        error_msg = f"Unexpected error in get_player_stats: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"

@mcp.tool()
async def get_league_leaders(stat_category: str = "PTS") -> str:
    """
    Get NBA league leaders for a specified stat category.

    Args:
        stat_category: Statistical category (PTS, AST, REB, STL, BLK, etc.)
    """
    print(f"DEBUG: Attempting to get league leaders for stat: {stat_category}", file=sys.stderr)
    client = NBAApiClient()
    try:
        result = await client.get_league_leaders(stat_category=stat_category)

        if "error" in result:
            print(f"ERROR: Failed to get league leaders: {result['error']}", file=sys.stderr)
            return f"Error: {result['error']}"

        # Check if we have leader data
        if "resultSet" not in result or "rowSet" not in result["resultSet"] or not result["resultSet"]["rowSet"]:
            print(f"DEBUG: No league leaders found for stat: {stat_category}", file=sys.stderr)
            return f"No league leaders found for {stat_category}."

        # Format the top 5 leaders
        headers = result["resultSet"]["headers"]
        rows = result["resultSet"]["rowSet"]
        
        player_idx = headers.index("PLAYER") if "PLAYER" in headers else -1
        team_idx = headers.index("TEAM") if "TEAM" in headers else -1
        stat_idx = headers.index(stat_category) if stat_category in headers else -1
        
        if player_idx < 0 or stat_idx < 0:
            print(f"ERROR: Could not find {stat_category} data in the response", file=sys.stderr)
            return f"Could not find {stat_category} data in the response."
        
        print(f"DEBUG: Successfully retrieved {len(rows)} league leaders", file=sys.stderr)
        formatted_leaders = []
        for i, row in enumerate(rows[:5]):
            player_name = row[player_idx] if player_idx >= 0 else "Unknown"
            team = row[team_idx] if team_idx >= 0 else ""
            stat_value = row[stat_idx] if stat_idx >= 0 else 0
            
            formatted_leaders.append(f"{i+1}. {player_name} ({team}): {stat_value}")
        
        return f"Top 5 {stat_category} Leaders:\n" + "\n".join(formatted_leaders)
    except Exception as e:
        error_msg = f"Unexpected error in get_league_leaders: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"

#########################################
# Running the Server
#########################################

def main():
    """Entry point for the NBA MCP server."""
    try:
        print("NBA MCP server starting...", file=sys.stderr)
        print("Initializing server transport...", file=sys.stderr)
        mcp.run(transport="stdio")
    except Exception as e:
        print(f"FATAL ERROR: Server crashed unexpectedly: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
