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
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Teams result: Found {len(result.get('data', []))} teams")
            # Print the first team as an example
            if result.get('data') and len(result['data']) > 0:
                print(f"Example team: {result['data'][0]['full_name']}")
    except Exception as e:
        print(f"Error: {str(e)}")

async def test_games():
    client = NBAApiClient()
    # Test with a date that should have games - NBA Christmas games are usually guaranteed
    date = "2022-12-25"
    print(f"\nTesting games by date: {date}...")
    try:
        result = await client.get_games_by_date(date)

        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            games = result.get("data", [])
            print(f"Found {len(games)} games")
            
            # Display each game result
            for i, game in enumerate(games, 1):
                home_team = game["home_team"]["full_name"]
                visitor_team = game["visitor_team"]["full_name"]
                home_score = game["home_team_score"]
                visitor_score = game["visitor_team_score"]
                print(f"Game {i}: {home_team} {home_score} vs {visitor_team} {visitor_score}")
    except Exception as e:
        print(f"Error: {str(e)}")

async def test_player():
    client = NBAApiClient()
    # Test with a well-known player name
    player_name = "LeBron James"
    print(f"\nTesting player stats for {player_name}...")
    try:
        result = await client.get_player_stats(player_name)
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            player = result["player"]
            season = result["season"]
            stats = result["stats"]
            
            if stats:
                print(f"Player: {player}")
                print(f"Season: {season}")
                print(f"Games Played: {stats.get('games_played', 'N/A')}")
                print(f"Points Per Game: {stats.get('pts', 'N/A')}")
                print(f"Rebounds Per Game: {stats.get('reb', 'N/A')}")
                print(f"Assists Per Game: {stats.get('ast', 'N/A')}")
            else:
                print(f"No stats found for {player} for season {season}")
    except Exception as e:
        print(f"Error: {str(e)}")

async def main():
    print("Testing NBA API Client...")
    print("=========================")
    
    # Try to get API key from environment
    api_key = os.environ.get("NBA_API_KEY", "")
    if api_key:
        print("API key found in environment variable.")
    else:
        print("No API key found. Some endpoints may return error responses.")
        print("To get an API key, sign up at https://app.balldontlie.io")
        print("Then set it as an environment variable: NBA_API_KEY=your_key_here\n")
    
    await test_teams()
    await test_games()
    await test_player()

if __name__ == "__main__":
    asyncio.run(main())
