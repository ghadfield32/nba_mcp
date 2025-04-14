import asyncio
import os
from nba_mcp.api.client import NBAApiClient

async def test_teams():
    """Test getting teams list (should be available in free tier)"""
    client = NBAApiClient()
    print("Testing teams endpoint...")
    try:
        # Try to get teams (should be available in free tier)
        result = await client.make_request("teams")
        print("Teams result:", result)
    except Exception as e:
        print(f"Error: {str(e)}")

async def test_games():
    client = NBAApiClient()
    # Test with a date that should have games
    print("\nTesting games by date...")
    try:
        result = await client.get_games_by_date("2022-12-25")
        print("Games result:", result)

        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Found {len(result.get('data', []))} games")
    except Exception as e:
        print(f"Error: {str(e)}")

async def test_player():
    client = NBAApiClient()
    # Test with a player name
    print("\nTesting player stats...")
    try:
        result = await client.get_player_stats("LeBron")
        print("Player result:", result)
    except Exception as e:
        print(f"Error: {str(e)}")

async def main():
    print("Testing NBA API Client...")
    await test_teams()
    await test_games()
    await test_player()

    print("\nNote: The balldontlie API now requires an API key.")
    print("To get an API key, sign up at https://app.balldontlie.io")
    print("Then set it as an environment variable: NBA_API_KEY=your_key_here")

if __name__ == "__main__":
    asyncio.run(main())
