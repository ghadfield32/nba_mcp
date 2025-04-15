import asyncio
import pytest
from datetime import datetime, timedelta
from nba_mcp.nba_server import get_nba_games
from nba_mcp.api.client import NBAApiClient

@pytest.mark.asyncio
async def test_get_games_specific_date():
    """Test getting games for a specific date."""
    # Use a recent date that's likely to have games
    today = datetime.now()
    test_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    
    result = await get_nba_games(date=test_date)
    print(f"\nTest output for {test_date}:")
    print(result)
    
    # Basic validation
    assert isinstance(result, str)
    assert test_date in result or "No games found" in result

@pytest.mark.asyncio
async def test_get_recent_games():
    """Test getting most recent games with lookback."""
    result = await get_nba_games(lookback_days=3)
    print("\nTest output for recent games:")
    print(result)
    
    # Basic validation
    assert isinstance(result, str)
    assert "Most Recent NBA Games" in result or "No recent games found" in result

@pytest.mark.asyncio
async def test_get_games_error_handling():
    """Test error handling with invalid date."""
    invalid_date = "2025-13-45"  # Invalid date format
    result = await get_nba_games(date=invalid_date)
    
    assert "Error" in result

@pytest.mark.asyncio
async def test_game_formatting():
    """Test game score formatting with real data."""
    client = NBAApiClient()
    
    # Get a recent date with games
    recent_data = await client.get_most_recent_game_date(lookback_days=7)
    if "error" not in recent_data and recent_data.get("games"):
        date_str = recent_data["date"]
        result = await get_nba_games(date=date_str)
        
        # Verify formatting
        assert "NBA Games for" in result
        assert "Score:" in result
        assert "Final" in result or "Q" in result  # Either final or quarter indicator
        
        print("\nFormatted output example:")
        print(result)

if __name__ == "__main__":
    asyncio.run(test_scoreboard_format()) 
