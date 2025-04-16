#nba_server.py
from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback
from datetime import datetime
from typing import Optional, List, Dict

from nba_api.stats.static import teams, players

# Initialize FastMCP server with the name "nba"
mcp = FastMCP("nba_mcp")



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
    
    # Load API documentation at the beginning
    await client.get_api_documentation()
    
    try:
        data = await client.get_games_by_date(date)
        
        # Include the query date in the response for context
        query_date = data.get("query_date", date)
        formatted_date = ""
        try:
            # Try to format the date nicely (April 15, 2025)
            date_obj = datetime.strptime(query_date, "%Y-%m-%d").date()
            formatted_date = date_obj.strftime("%B %d, %Y")
        except ValueError:
            formatted_date = query_date
        
        # Check for custom message first
        if "message" in data:
            return f"Date: {formatted_date}\n{data['message']}"
            
        if "error" in data:
            error_msg = data['error']
            print(
                "ERROR: Failed to get game scores: "
                f"{error_msg}", 
                file=sys.stderr
            )
            return f"Error for {formatted_date}: {error_msg}"

        if not data.get("data"):
            print(
                "DEBUG: No games found for date: "
                f"{query_date}", 
                file=sys.stderr
            )
            return f"No games found for {formatted_date}."

        games = data["data"]
        print(
            "DEBUG: Successfully found "
            f"{len(games)} games for date: {query_date}", 
            file=sys.stderr
        )
        formatted_games = [format_game(game) for game in games]
        
        # Include the date in the response header
        return f"NBA Games for {formatted_date}:\n" + "\n---\n".join(formatted_games)
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
    
    # Load API documentation at the beginning
    await client.get_api_documentation()
    
    try:
        # First check if we can find the player
        player_id = get_player_id(player)
        if not player_id:
            return f"Error: No player found matching '{player}'"
            
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
async def get_league_leaders(season: str = "2024-25", stat_category: str = "PTS") -> str:
    """
    Get NBA league leaders for a specified stat category.

    Args:
        stat_category: Statistical category (PTS, AST, REB, STL, BLK, etc.)
    """
    print(f"DEBUG: Attempting to get league leaders for stat: {stat_category}", file=sys.stderr)
    client = NBAApiClient()
    
    # Load API documentation at the beginning
    await client.get_api_documentation()
    
    try:
        result = await client.get_league_leaders(season=season, stat_category=stat_category)

        if "error" in result:
            print(f"ERROR: Failed to get league leaders: {result['error']}", file=sys.stderr)
            return f"Error: {result['error']}"

        # Check if we have leader data
        if (
            "resultSet" not in result 
            or "rowSet" not in result["resultSet"] 
            or not result["resultSet"]["rowSet"]
        ):
            print(
                "DEBUG: No league leaders found for stat: "
                f"{stat_category}", 
                file=sys.stderr
            )
            return f"No league leaders found for {stat_category}."

        # Format the top 5 leaders
        headers = result["resultSet"]["headers"]
        rows = result["resultSet"]["rowSet"]
        
        player_idx = headers.index("PLAYER") if "PLAYER" in headers else -1
        team_idx = headers.index("TEAM") if "TEAM" in headers else -1
        stat_idx = (
            headers.index(stat_category) 
            if stat_category in headers else -1
        )
        
        if player_idx < 0 or stat_idx < 0:
            error_str = (
                f"Could not find {stat_category} data in the response."
            )
            print(
                f"ERROR: {error_str}",
                file=sys.stderr
            )
            return error_str
        
        print(
            "DEBUG: Successfully retrieved "
            f"{len(rows)} league leaders", 
            file=sys.stderr
        )
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

@mcp.tool()
async def get_live_scores() -> str:
    """
    Get live NBA game scores for today.
    """
    print(f"DEBUG: Attempting to get live game scores", file=sys.stderr)
    try:
        client = NBAApiClient()
        
        # Load API documentation at the beginning
        await client.get_api_documentation()
        
        games_df = await client.get_live_scoreboard(as_dataframe=True)
        
        if games_df.empty:
            print("DEBUG: No live games found today", file=sys.stderr)
            return "No live games found today."
        
        formatted_games = []
        for _, game in games_df.iterrows():
            home_team = game.get("homeTeam", {}).get("teamName", "Unknown")
            away_team = game.get("awayTeam", {}).get("teamName", "Unknown")
            home_score = game.get("homeTeam", {}).get("score", 0)
            away_score = game.get("awayTeam", {}).get("score", 0)
            
            game_status = game.get("gameStatus", 0)
            period = game.get("period", 0)
            game_clock = game.get("gameClock", "")
            
            status_text = ""
            if game_status == 3:  # Finished game
                status_text = " (Final)"
            elif game_status == 2:  # In progress
                status_text = f" (Period {period}, {game_clock})"
            elif game_status == 1:  # Not started
                status_text = f" (Not started)"
            
            formatted_games.append(f"{home_team} vs {away_team} - Score: {home_score} to {away_score}{status_text}")
        
        return "\n---\n".join(formatted_games)
    except Exception as e:
        error_msg = f"Unexpected error in get_live_scores: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"

@mcp.tool()
async def get_player_career_information(player_name: str) -> str:
    """
    Get career statistics for an NBA player by their name.

    Args:
        player_name: The name of the player (e.g. "LeBron James")
    """
    print(f"DEBUG: Attempting to get career stats for: {player_name}", file=sys.stderr)
    try:
        client = NBAApiClient()
        
        # Load API documentation at the beginning
        await client.get_api_documentation()
        
        # First check if we can find the player
        player_id = get_player_id(player_name)
        if not player_id:
            return f"Error: No player found matching '{player_name}'"
            
        # Get the career stats using the client function
        player_stats_df = await client.get_player_career_stats(player_name, as_dataframe=True)
        
        if player_stats_df.empty:
            print(f"DEBUG: No career stats found for player: {player_name}", file=sys.stderr)
            return f"No career stats found for {player_name}."
        
        # Extract the most recent season stats
        recent_stats = player_stats_df.iloc[-1]
        
        # Format the response
        stats_text = f"""
Player: {player_name}
Seasons: {player_stats_df.iloc[0]['SEASON_ID']} to {recent_stats['SEASON_ID']}
Career Games: {recent_stats['GP']}
Career Stats:
- Points Per Game: {recent_stats.get('PTS', 'N/A')}
- Rebounds Per Game: {recent_stats.get('REB', 'N/A')}
- Assists Per Game: {recent_stats.get('AST', 'N/A')}
- Field Goal %: {recent_stats.get('FG_PCT', 'N/A')}
- 3-Point %: {recent_stats.get('FG3_PCT', 'N/A')}
- Free Throw %: {recent_stats.get('FT_PCT', 'N/A')}
"""
        return stats_text
        
    except ValueError as e:
        error_msg = str(e)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Unexpected error in get_player_career_information: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"



@mcp.tool()
async def get_team_game_log(team_name: str, season: str = "2023-24") -> str:
    """
    Get game log for a specific NBA team in the given season.

    Args:
        team_name: Name of the team (e.g. "Lakers" or "Los Angeles Lakers")
        season: Season in format 'YYYY-YY' (e.g., '2023-24')
    """
    print(f"DEBUG: Attempting to get game log for team: {team_name} in season {season}", file=sys.stderr)
    try:
        client = NBAApiClient()
        
        # Load API documentation at the beginning
        await client.get_api_documentation()
        
        # First check if we can find the team
        team_id = get_team_id(team_name)
        if not team_id:
            return f"Error: No team found matching '{team_name}'"
            
        # Get the game log using the client function
        game_log_df = await client.get_league_game_log(season=season, team_name_or_id=str(team_id), as_dataframe=True)
        
        if game_log_df.empty:
            print(f"DEBUG: No game log found for team: {team_name}", file=sys.stderr)
            return f"No game log found for {team_name} in the {season} season."
        
        # Format the last 5 games
        formatted_games = []
        for i, (_, game) in enumerate(game_log_df.head(5).iterrows()):
            game_date = game.get('GAME_DATE', 'Unknown Date')
            matchup = game.get('MATCHUP', 'Unknown Matchup')
            result = game.get('WL', '')
            pts = game.get('PTS', 0)
            
            # Check if PTS_OPP exists in the dataframe columns
            if 'PTS_OPP' in game_log_df.columns:
                opp_pts = game.get('PTS_OPP', 0)
            else:
                # If we don't have opponent points directly, try to infer from other data
                # (In some versions of the NBA API, this isn't returned directly)
                opp_pts = "N/A"
            
            formatted_games.append(f"{game_date}: {matchup} - Result: {result} ({pts}-{opp_pts})")
        
        return f"Recent Games for {team_name} in {season} Season:\n" + "\n".join(formatted_games)
    except ValueError as e:
        error_msg = str(e)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Unexpected error in get_team_game_log: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"

@mcp.tool()
async def get_nba_games(date: Optional[str] = None, 
                        lookback_days: Optional[int] = None) -> str:
    """
    Get NBA games for a specific date or over a range of past days.
    
    Args:
        date: Date in format 'YYYY-MM-DD', defaults to today if not provided
        lookback_days: Number of days to look back (including the specified date)
    """
    print(
        f"DEBUG: Attempting to get NBA games for date:{date}, "
        f"lookback:{lookback_days}", 
        file=sys.stderr
    )
    try:
        client = NBAApiClient()
        
        # Load API documentation at the beginning
        await client.get_api_documentation()
        
        result = await client.get_games_by_date(
            date=date, 
            lookback_days=lookback_days
        )
        
        if "error" in result:
            print(
                f"ERROR: Failed to get NBA games: {result['error']}", 
                file=sys.stderr
            )
            return f"Error: {result['error']}"
        
        if not result["games"]:
            date_str = result["date"] if "date" in result else date or "today"
            return f"No games found for {date_str}."
        
        # Format the output as a string
        output_lines = []
        
        if "date_range" in result:
            output_lines.append(f"NBA Games ({result['date_range']}):")
        else:
            output_lines.append(f"NBA Games for {result['date']}:")
        
        for game in result["games"]:
            # Get team IDs from names if needed
            home_team = game["home_team"]
            away_team = game["away_team"]
            
            status = game["status"]
            
            if status == "Final":
                home_score = game["home_score"]
                away_score = game["away_score"]
                
                # Format winner and add markers
                if home_score > away_score:
                    home_team = f"{home_team} ✓"
                elif away_score > home_score:
                    away_team = f"{away_team} ✓"
                
                game_str = (
                    f"{away_team} {away_score} @ "
                    f"{home_team} {home_score} (Final)"
                )
            elif (
                status.startswith("Q") 
                or "Half" in status 
                or "Start" in status
            ):
                home_score = game["home_score"]
                away_score = game["away_score"]
                game_str = (
                    f"{away_team} {away_score} @ "
                    f"{home_team} {home_score} ({status})"
                )
            else:
                # For scheduled games
                game_time = game.get("game_time", "")
                game_str = (
                    f"{away_team} @ {home_team} "
                    f"({game_time})"
                )
                
            output_lines.append(game_str)
        
        return "\n".join(output_lines)
    except Exception as e:
        error_msg = f"Error retrieving NBA games: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return error_msg

@mcp.tool()
async def get_player_multi_season_stats(player: str, seasons: Optional[List[int]] = None) -> str:
    """
    Get player stats for multiple seasons with a tabular format.

    Args:
        player: The name of the player (e.g. "LeBron James")
        seasons: Optional list of season years (e.g. [2023, 2022, 2021])
    """
    print(f"DEBUG: Attempting to get multi-season stats for: {player}", file=sys.stderr)
    client = NBAApiClient()
    
    # Load API documentation at the beginning
    await client.get_api_documentation()
    
    try:
        result = await client.get_player_stats_bulk(player, seasons)

        if "error" in result:
            print(f"ERROR: Failed to get player stats: {result['error']}", file=sys.stderr)
            return f"Error: {result['error']}"

        player_name = result["player"]
        
        if not result.get("season_stats"):
            print(f"DEBUG: No stats found for player: {player_name}", file=sys.stderr)
            return f"No stats found for {player_name}."
        
        # Define the stats we want to show in the table
        stats_to_show = {
            "pts": "PPG",
            "reb": "RPG", 
            "ast": "APG",
            "stl": "SPG",
            "blk": "BPG",
            "fg_pct": "FG%",
            "fg3_pct": "3P%",
            "ft_pct": "FT%"
        }
        
        # Create a header for the table
        seasons_found = result.get("seasons_found", [])
        
        print(f"DEBUG: Successfully retrieved stats for {player_name}, {len(seasons_found)} seasons", file=sys.stderr)
        
        # Start building the response
        response = f"Stats for {player_name} (Last {len(seasons_found)} Seasons):\n\n"
        
        # Build the table
        # Header row with season years
        header_row = "Stat      "  # Padding for stat name column
        for season in seasons_found:
            season_str = f"{season}-{str(season+1)[-2:]}"
            header_row += f" | {season_str:>7}"
        response += header_row + "\n"
        
        # Add a separator row
        separator = "-" * len(header_row)
        response += separator + "\n"
        
        # Add each stat row
        for stat_key, stat_name in stats_to_show.items():
            stat_row = f"{stat_name:<10}"
            
            for season_data in result["season_stats"]:
                # Get the stat value, format as string with appropriate precision
                stat_value = season_data["stats"].get(stat_key.upper())
                if stat_key.endswith('_pct'):  # It's a percentage
                    if stat_value is not None:
                        # Format as percentage with 1 decimal
                        formatted_value = f"{float(stat_value) * 100:.1f}%"
                    else:
                        formatted_value = "N/A"
                else:  # It's a regular number
                    if stat_value is not None:
                        # Format as number with 1 decimal
                        formatted_value = f"{float(stat_value):.1f}"
                    else:
                        formatted_value = "N/A"
                
                stat_row += f" | {formatted_value:>7}"
            
            response += stat_row + "\n"
        
        return response
    except Exception as e:
        error_msg = f"Unexpected error in get_player_multi_season_stats: {str(e)}"
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
