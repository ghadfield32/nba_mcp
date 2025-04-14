"""
Improved NBA API Testing Script with Enhanced Error Handling

This script tests the NBA MCP API client with proper error handling
for edge cases, API key requirements, and 404 responses.
"""

import asyncio
import os
from datetime import datetime
from nba_mcp.api.client import NBAApiClient


async def test_teams_with_error_handling():
    """Test getting teams list with proper error handling."""
    client = NBAApiClient()
    print("\n===== Testing Teams Endpoint =====")
    
    try:
        result = await client.make_request("teams")
        
        if "error" in result:
            print(f"Error: {result['error']}")
            if "status_code" in result and result["status_code"] == 404:
                print("This is likely because the endpoint doesn't exist or requires an API key.")
            elif "status_code" in result:
                print(f"Status code: {result['status_code']}")
            return
            
        teams_count = len(result.get("data", []))
        print(f"Success! Found {teams_count} teams")
        
        # Print a few teams as example
        if teams_count > 0:
            print("\nExample teams:")
            for i, team in enumerate(result.get("data", [])[:3], 1):
                print(f"  {i}. {team.get('full_name', 'Unknown')} ({team.get('abbreviation', '??')})")
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")


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
        print(f"  Games Played: {stats.get('games_played', 'N/A')}")
        print(f"  Points Per Game: {stats.get('pts', 'N/A')}")
        print(f"  Rebounds Per Game: {stats.get('reb', 'N/A')}")
        print(f"  Assists Per Game: {stats.get('ast', 'N/A')}")
        print(f"  Field Goal %: {stats.get('fg_pct', 'N/A')}")
        print(f"  3-Point %: {stats.get('fg3_pct', 'N/A')}")
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")


async def test_invalid_endpoint():
    """Test handling of an invalid endpoint."""
    client = NBAApiClient()
    print("\n===== Testing Invalid Endpoint =====")
    
    try:
        # Intentionally use a non-existent endpoint
        result = await client.make_request("non_existent_endpoint")
        
        if "error" in result:
            print(f"Successfully caught error: {result['error']}")
            if "status_code" in result:
                print(f"Status code: {result['status_code']}")
        else:
            print("Unexpected success response for invalid endpoint!")
            print(result)
    
    except Exception as e:
        print(f"Exception not properly caught: {str(e)}")


async def main():
    """Main entry point for the test script."""
    print("\n" + "="*50)
    print("NBA API CLIENT TEST WITH IMPROVED ERROR HANDLING")
    print("="*50)
    
    # Check for API key
    api_key = os.environ.get("NBA_API_KEY", "")
    if api_key:
        print("\nAPI Key: Found in environment variables")
    else:
        print("\nAPI Key: Not found in environment variables")
        print("Some endpoints may return error responses without an API key.")
        print("To get an API key, sign up at https://app.balldontlie.io")
        print("Then set it as an environment variable: NBA_API_KEY=your_key_here")
    
    # Get current time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nTest started at: {current_time}")
    
    # Run tests
    await test_teams_with_error_handling()
    await test_games_with_error_handling()
    await test_player_with_error_handling()
    await test_invalid_endpoint()
    
    print("\n" + "="*50)
    print("TEST COMPLETE")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main()) 