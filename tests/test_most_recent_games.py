import asyncio
import pytest
from datetime import datetime, timedelta

# Import your client and tool
from nba_mcp.api.client import NBAApiClient
from nba_mcp.nba_server import get_most_recent_game_scores  # or wherever your tool lives

@pytest.mark.asyncio
async def test_get_most_recent_game_date_no_games(monkeypatch):
    """
    Simulate no games in the last N days: the client should return an error dict.
    """
    client = NBAApiClient()

    # Monkey-patch get_games_by_date to always return empty data
    async def fake_get_games_by_date(date_str: str):
        return {"data": []}
    monkeypatch.setattr(client, "get_games_by_date", fake_get_games_by_date)

    result = await client.get_most_recent_game_date(lookback_days=3)
    assert "error" in result
    assert "No games found" in result["error"]


@pytest.mark.asyncio
async def test_get_most_recent_game_date_found(monkeypatch):
    """
    Simulate a game on "yesterday" and verify the client picks it up.
    """
    client = NBAApiClient()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    ystr = yesterday.strftime("%Y-%m-%d")

    # Create a fake response with one game
    fake_game = {
        "gameId": "1234",
        "homeTeam": {"teamName": "Home", "teamId": 1, "score": 100},
        "awayTeam": {"teamName": "Away", "teamId": 2, "score": 90},
        "gameStatus": 3,
        "period": 4,
        "gameClock": ""
    }

    async def fake_get_games_by_date(date_str: str):
        # Return empty for today, return one game for yesterday
        if date_str == today.strftime("%Y-%m-%d"):
            return {"data": []}
        elif date_str == ystr:
            return {"data": [fake_game]}
        else:
            return {"data": []}

    monkeypatch.setattr(client, "get_games_by_date", fake_get_games_by_date)

    result = await client.get_most_recent_game_date(lookback_days=3)

    # Should have picked yesterday's date
    assert result["date"] == ystr
    assert result["formatted_date"] == yesterday.strftime("%B %d, %Y")
    assert isinstance(result["games"], list)
    assert result["games"][0]["gameId"] == "1234"


@pytest.mark.asyncio
async def test_most_recent_game_scores_tool(monkeypatch):
    """
    Test the MCP tool wrapper: it should format the date header and include the game.
    """
    # Monkey-patch the client inside the tool to return our fake data
    fake_response = {
        "date": "2025-04-13",
        "formatted_date": "April 13, 2025",
        "games": [
            {
                "gameId": "9999",
                "home_team": {"full_name": "Test Home"},
                "visitor_team": {"full_name": "Test Away"},
                "home_team_score": 110,
                "visitor_team_score": 105,
                "status": 3,
                "period": 4,
                "time": ""
            }
        ]
    }

    async def fake_get_most_recent_game_date(self, lookback_days=7):
        return fake_response

    # Patch the client method on the NBAApiClient class
    monkeypatch.setattr(NBAApiClient, "get_most_recent_game_date", fake_get_most_recent_game_date)

    # Now call the tool
    output = await get_most_recent_game_scores()
    
    # Print the output for verification
    print("\n----- TOOL OUTPUT -----")
    print(output)
    print("-----------------------")

    # It should include our formatted header and the game line
    assert "Most Recent NBA Games (April 13, 2025):" in output
    assert "Test Home vs Test Away - Score: 110 to 105 (Final)" in output
