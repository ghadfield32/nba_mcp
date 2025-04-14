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
    """Test getting games data for a specific date"""
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
    """Test getting player stats"""
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

async def test_league_leaders():
    """Test getting league leaders for points"""
    client = NBAApiClient()
    stat_category = "PTS"
    print(f"\nTesting league leaders for {stat_category}...")
    try:
        result = await client.get_league_leaders(stat_category=stat_category)
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            if "resultSet" in result and "rowSet" in result["resultSet"]:
                leaders = result["resultSet"]["rowSet"]
                headers = result["resultSet"]["headers"]
                
                # Find indices for player name, team, and stat
                player_idx = headers.index("PLAYER") if "PLAYER" in headers else -1
                team_idx = headers.index("TEAM") if "TEAM" in headers else -1
                stat_idx = headers.index(stat_category) if stat_category in headers else -1
                
                if leaders and player_idx >= 0 and stat_idx >= 0:
                    print(f"Top 5 {stat_category} Leaders:")
                    for i, leader in enumerate(leaders[:5], 1):
                        player_name = leader[player_idx]
                        team = leader[team_idx] if team_idx >= 0 else ""
                        stat_value = leader[stat_idx]
                        print(f"{i}. {player_name} ({team}): {stat_value}")
                else:
                    print("Could not parse leaders data")
            else:
                print("No leader data found in response")
    except Exception as e:
        print(f"Error: {str(e)}")

async def test_live_scoreboard():
    """Test getting live scoreboard data"""
    client = NBAApiClient()
    print("\nTesting live scoreboard...")
    try:
        result = await client.get_live_scoreboard()
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            if "scoreboard" in result and "games" in result["scoreboard"]:
                games = result["scoreboard"]["games"]
                print(f"Found {len(games)} games on scoreboard")
                
                # Display first few games
                for i, game in enumerate(games[:3], 1):
                    home_team = game.get("homeTeam", {}).get("teamName", "Unknown")
                    away_team = game.get("awayTeam", {}).get("teamName", "Unknown")
                    home_score = game.get("homeTeam", {}).get("score", 0)
                    away_score = game.get("awayTeam", {}).get("score", 0)
                    status = game.get("gameStatusText", "")
                    
                    print(f"Game {i}: {away_team} {away_score} @ {home_team} {home_score} ({status})")
            else:
                print("No games data found in live scoreboard")
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
    await test_league_leaders()
    await test_live_scoreboard()
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
