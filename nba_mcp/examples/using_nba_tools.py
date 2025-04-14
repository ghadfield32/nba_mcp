"""
Example usage of NBA API tools.

This file demonstrates how to use the NBA API tools to fetch data from the NBA API
and manipulate it with pandas or extract raw JSON/dict data.
"""

import pandas as pd
from datetime import date

# Import the NBA API tools
from nba_mcp import (
    get_live_scoreboard,
    get_player_career_stats,
    get_league_leaders,
    get_league_game_log
)

def main():
    """Run examples of using the NBA API tools."""
    print("NBA API Tools Examples\n")
    
    # Example 1: Get live scoreboard for today
    print("Example 1: Live Scoreboard for Today")
    scoreboard_df = get_live_scoreboard()
    if not scoreboard_df.empty:
        print(f"Found {len(scoreboard_df)} games today")
        print(scoreboard_df[['gameId', 'gameStatusText']].head())
    else:
        print("No games found for today")
        
    # You can also get the raw dict data
    scoreboard_data = get_live_scoreboard(as_dataframe=False)
    print(f"Raw scoreboard data keys: {scoreboard_data.keys() if isinstance(scoreboard_data, dict) else 'N/A'}\n")
    
    # Example 2: Get Nikola Jokić's career stats
    print("Example 2: Player Career Stats (Nikola Jokić)")
    jokic_id = "203999"  # Nikola Jokić's player ID
    jokic_career_df = get_player_career_stats(jokic_id)
    if not jokic_career_df.empty:
        print(f"Career seasons: {len(jokic_career_df)}")
        print(jokic_career_df[['SEASON_ID', 'TEAM_ABBREVIATION', 'PTS', 'AST', 'REB']].head())
    else:
        print("No career stats found")
    print()
    
    # Example 3: Get current season's league leaders
    print("Example 3: League Leaders (Current Season)")
    current_season = f"{date.today().year-1}-{str(date.today().year)[-2:]}"
    leaders_df = get_league_leaders(current_season)
    if not leaders_df.empty:
        print(f"Found {len(leaders_df)} league leaders")
        print(leaders_df[['PLAYER_ID', 'PLAYER', 'TEAM', 'PTS']].head())
    else:
        print("No league leaders found")
    print()
    
    # Example 4: Get game log for Denver Nuggets
    print("Example 4: Game Log for Denver Nuggets (Current Season)")
    nuggets_id = "1610612743"  # Denver Nuggets team ID
    nuggets_games_df = get_league_game_log(current_season, team_id=nuggets_id)
    if not nuggets_games_df.empty:
        print(f"Found {len(nuggets_games_df)} games for the Nuggets")
        print(nuggets_games_df[['GAME_DATE', 'MATCHUP', 'WL', 'PTS']].head())
    else:
        print("No game log found")

if __name__ == "__main__":
    main() 