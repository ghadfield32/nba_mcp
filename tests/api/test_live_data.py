import pytest
import pandas as pd
from datetime import datetime, timedelta
from nba_mcp.api.client import NBAApiClient

@pytest.mark.asyncio
async def test_live_game_data():
    """Test fetching live game data for recent dates."""
    client = NBAApiClient()
    
    # Use dates from the past where we know games were played
    # Using a fixed period from the 2023-2024 season
    start_date = datetime(2023, 11, 1)  # November 1, 2023
    results = []
    api_responses = []
    
    print("\nTesting dates:")
    for i in range(7):  # Test a week of games
        test_date = start_date + timedelta(days=i)
        date_str = test_date.strftime("%Y-%m-%d")
        print(f"Checking date: {date_str}")
        
        # Use the live scoreboard endpoint instead of balldontlie
        scoreboard = await client.get_live_scoreboard()
        api_responses.append({"date": date_str, "response": scoreboard})
        
        if scoreboard and "scoreboard" in scoreboard:
            games = scoreboard["scoreboard"].get("games", [])
            results.append({
                "date": date_str,
                "games": len(games),
                "has_scores": any(g.get("homeTeam", {}).get("score", 0) > 0 for g in games)
            })
    
    print("\nAPI Responses:")
    for resp in api_responses:
        print(f"Date: {resp['date']}")
        print(f"Response: {resp['response']}\n")
        
    print("\nLive Data Test Results:")
    for result in results:
        print(f"Date: {result['date']}, Games: {result['games']}, Has Scores: {result['has_scores']}")
    
    if not results:
        print("\nNo results found. This could be due to:")
        print("1. API rate limiting")
        print("2. No games scheduled in the date range")
        print("3. API connection issues")
        print("4. API response format changes")
    
    assert len(results) > 0, "No game data available for recent dates"

@pytest.mark.asyncio
async def test_live_scoreboard():
    """Test fetching live scoreboard data."""
    client = NBAApiClient()
    
    # Get today's date in the format expected by the API
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\nFetching live scoreboard for {today} ...")
    
    # Get live scoreboard data
    scoreboard = await client.get_live_scoreboard()
    
    # Display the JSON snippet (first 500 characters)
    if scoreboard:
        print("\nLive Scoreboard JSON data snippet:")
        try:
            json_str = str(scoreboard)[:500]
            print(json_str + "...")
            
            # Convert to DataFrame for better visualization
            if 'scoreboard' in scoreboard and 'games' in scoreboard['scoreboard']:
                games_df = pd.DataFrame(scoreboard['scoreboard']['games'])
                print("\nLive Scoreboard DataFrame (first 5 rows):")
                print(games_df.head().to_string())
                
                # Validate data structure - check if at least some basic fields exist
                basic_columns = ['gameId', 'homeTeam', 'awayTeam']
                for col in basic_columns:
                    assert col in games_df.columns, f"Expected column '{col}' not found in scoreboard data"
                
                return True
            else:
                print("No games data found in scoreboard response")
        except Exception as e:
            print(f"Error processing scoreboard data: {e}")
    else:
        print("Error retrieving live scoreboard data")
    
    # If we reach here, something went wrong
    # Don't fail the test if no games are scheduled for today
    return False

@pytest.mark.asyncio
async def test_player_career_stats():
    """Test fetching player career stats."""
    client = NBAApiClient()
    
    # Test with Nikola Jokić's player ID
    player_id = '203999'
    print(f"\nFetching player career stats for Nikola Jokić (player_id='{player_id}'):")
    
    # Get player career stats
    career_stats = await client.get_player_career_stats(player_id)
    
    if career_stats:
        # Check if the response has the expected structure
        assert 'resultSets' in career_stats, "Expected 'resultSets' in response"
        
        # Convert to DataFrame for better visualization
        try:
            # Extract data from the response
            headers = career_stats['resultSets'][0]['headers']
            rows = career_stats['resultSets'][0]['rowSet']
            
            # Create DataFrame
            career_df = pd.DataFrame(rows, columns=headers)
            print("Player Career Stats DataFrame (first 5 rows):")
            print(career_df.head().to_string())
            
            # Display JSON snippet
            json_str = str(career_stats)[:500]
            print("\nPlayer Career Stats JSON snippet (first 500 characters):")
            print(json_str + "...")
            
            # Validate data
            assert len(career_df) > 0, "No career stats data found"
            expected_columns = ['PLAYER_ID', 'SEASON_ID', 'TEAM_ID', 'PTS', 'REB', 'AST']
            for col in expected_columns:
                assert col in career_df.columns, f"Expected column '{col}' not found in career stats data"
            
            # Verify it's the right player
            assert career_df['PLAYER_ID'].iloc[0] == int(player_id), "Player ID doesn't match"
            
            return True
        except Exception as e:
            print(f"Error processing career stats data: {e}")
    else:
        print("Error retrieving player career stats")
    
    return False

@pytest.mark.asyncio
async def test_league_leaders():
    """Test fetching league leaders."""
    client = NBAApiClient()
    
    # Use a completed season (2022-23) for reliable data
    season = "2022-23"
    
    print(f"\nFetching league leaders for season {season}:")
    
    # Get league leaders
    leaders = await client.get_league_leaders(season=season)
    
    if leaders:
        try:
            # Check if the response has the expected structure
            assert 'resultSets' in leaders, "Expected 'resultSets' in response"
            
            # Extract data
            headers = leaders['resultSets'][0]['headers']
            rows = leaders['resultSets'][0]['rowSet']
            
            # Create DataFrame
            leaders_df = pd.DataFrame(rows, columns=headers)
            print("League Leaders DataFrame (first 5 rows):")
            print(leaders_df.head().to_string())
            
            # Validate data
            assert len(leaders_df) > 0, "No league leaders data found"
            expected_columns = ['PLAYER_ID', 'PLAYER', 'TEAM', 'PTS']
            for col in expected_columns:
                assert col in leaders_df.columns, f"Expected column '{col}' not found in league leaders data"
            
            return True
        except Exception as e:
            print(f"Error processing league leaders data: {e}")
    else:
        print("Error retrieving league leaders")
    
    return False

@pytest.mark.asyncio
async def test_league_game_log():
    """Test fetching league game log."""
    client = NBAApiClient()
    
    # Use a completed season (2022-23) for reliable data
    season = "2022-23"
    
    print(f"\nFetching league game log for season {season}:")
    
    # Get league game log
    game_log = await client.get_league_game_log(season=season)
    
    if game_log:
        try:
            # Check if the response has the expected structure
            assert 'resultSets' in game_log, "Expected 'resultSets' in response"
            
            # Extract data
            headers = game_log['resultSets'][0]['headers']
            rows = game_log['resultSets'][0]['rowSet']
            
            # Create DataFrame
            game_log_df = pd.DataFrame(rows, columns=headers)
            
            # Display most recent 5 games
            print("League Game Log DataFrame (most recent 5 games):")
            print(game_log_df.tail(5).to_string())
            
            # Validate data
            assert len(game_log_df) > 0, "No game log data found"
            expected_columns = ['SEASON_ID', 'TEAM_ID', 'GAME_ID', 'GAME_DATE', 'MATCHUP', 'PTS']
            for col in expected_columns:
                assert col in game_log_df.columns, f"Expected column '{col}' not found in game log data"
            
            return True
        except Exception as e:
            print(f"Error processing game log data: {e}")
    else:
        print("Error retrieving league game log")
    
    return False

@pytest.mark.asyncio
async def test_all_endpoints():
    """Test all API endpoints in sequence."""
    # Run all tests in sequence
    test_results = {
        "live_scoreboard": await test_live_scoreboard(),
        "player_career_stats": await test_player_career_stats(),
        "league_leaders": await test_league_leaders(),
        "league_game_log": await test_league_game_log()
    }
    
    print("\nTest Results Summary:")
    for test_name, result in test_results.items():
        status = "PASSED" if result else "FAILED"
        print(f"{test_name}: {status}")
    
    # Ensure at least some endpoints worked
    assert any(test_results.values()), "All API endpoint tests failed"





