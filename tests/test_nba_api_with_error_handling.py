"""
Improved NBA API Testing Script with Enhanced Error Handling

This script tests the NBA MCP API client with proper error handling
for edge cases and input validation.
"""

import asyncio
from datetime import datetime
import pytest
from nba_mcp.api.client import NBAApiClient

# Mark all tests in this module as asyncio tests
pytestmark = pytest.mark.asyncio


async def test_games_with_error_handling():
    """Test getting games with proper error handling."""
    client = NBAApiClient()
    
    # Use a date that should have NBA games - Christmas is usually guaranteed
    test_date = "2022-12-25"
    print(f"\n===== Testing Games for {test_date} =====")
    
    try:
        result = await client.get_games_by_date(test_date)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
            
        games = result.get("data", [])
        games_count = len(games)
        
        if games_count == 0:
            print(f"No games found for {test_date}")
            return
            
        print(f"Success! Found {games_count} games on {test_date}")
        
        # Display some game information
        print("\nGames:")
        for i, game in enumerate(games, 1):
            home_team = game["home_team"]["full_name"]
            visitor_team = game["visitor_team"]["full_name"]
            home_score = game["home_team_score"]
            visitor_score = game["visitor_team_score"]
            
            print(f"  {i}. {visitor_team} ({visitor_score}) @ {home_team} ({home_score})")
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")


async def test_player_with_error_handling():
    """Test getting player stats with proper error handling."""
    client = NBAApiClient()
    
    # Test with a well-known player name
    player_name = "LeBron James"
    print(f"\n===== Testing Player Stats for '{player_name}' =====")
    
    try:
        result = await client.get_player_stats(player_name)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
            
        player = result["player"]
        season = result["season"]
        stats = result["stats"]
        
        if not stats:
            print(f"No stats found for {player} in season {season}")
            return
            
        print(f"Success! Found stats for {player} in season {season}")
        print("\nKey Statistics:")
        
        # Print the available stats
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
                print(f"  {field_name}: {stats.get(field_key_lower, 'N/A')}")
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")


async def test_invalid_date():
    """Test handling of an invalid date."""
    client = NBAApiClient()
    print("\n===== Testing Invalid Date Format =====")
    
    try:
        # Intentionally use an invalid date format
        result = await client.get_games_by_date("12/25/2022")  # Not YYYY-MM-DD
        
        if "error" in result:
            print(f"Successfully caught error: {result['error']}")
        else:
            print("Unexpected success response for invalid date format!")
            print(result)
    
    except Exception as e:
        print(f"Exception not properly caught: {str(e)}")


async def test_league_leaders():
    """Test getting league leaders."""
    client = NBAApiClient()
    stat_category = "PTS"
    print(f"\n===== Testing League Leaders for {stat_category} =====")
    
    try:
        result = await client.get_league_leaders(stat_category=stat_category)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
            
        if "resultSet" not in result or "rowSet" not in result["resultSet"]:
            print(f"No league leaders data found for {stat_category}")
            return
            
        leaders = result["resultSet"]["rowSet"]
        headers = result["resultSet"]["headers"]
        
        # Find indices for player name, team, and stat
        player_idx = headers.index("PLAYER") if "PLAYER" in headers else -1
        team_idx = headers.index("TEAM") if "TEAM" in headers else -1
        stat_idx = headers.index(stat_category) if stat_category in headers else -1
        
        if player_idx < 0 or stat_idx < 0:
            print(f"Could not find {stat_category} data in the response")
            return
            
        print(f"Success! Found league leaders for {stat_category}")
        print("\nTop 5 Leaders:")
        for i, leader in enumerate(leaders[:5], 1):
            player_name = leader[player_idx]
            team = leader[team_idx] if team_idx >= 0 else ""
            stat_value = leader[stat_idx]
            print(f"  {i}. {player_name} ({team}): {stat_value}")
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")


async def main():
    """Main entry point for the test script."""
    print("\n" + "="*50)
    print("NBA API CLIENT TEST WITH IMPROVED ERROR HANDLING")
    print("="*50)
    
    # Get current time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nTest started at: {current_time}")
    
    # Run tests
    await test_games_with_error_handling()
    await test_player_with_error_handling()
    await test_invalid_date()
    await test_league_leaders()
    
    print("\n" + "="*50)
    print("TEST COMPLETE")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main()) 