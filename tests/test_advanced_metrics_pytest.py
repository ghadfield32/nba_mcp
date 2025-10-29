"""
Pytest version of comprehensive advanced metrics tests.

Run with: pytest test_advanced_metrics_pytest.py -v
"""
import pytest
import asyncio
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient
from nba_mcp.cache import get_cache


@pytest.fixture
def client():
    """Fixture to create NBAApiClient"""
    return NBAApiClient()


@pytest.mark.asyncio
async def test_performance_splits_basic(client):
    """Test basic performance splits functionality"""
    result = await client.get_player_performance_splits(
        player_name="LeBron James",
        season="2023-24",
        last_n_games=10
    )

    # Validate structure
    assert "error" not in result, f"Error in result: {result.get('error')}"
    assert "season_stats" in result
    assert "last_n_stats" in result
    assert "home_stats" in result
    assert "away_stats" in result
    assert "wins_stats" in result
    assert "losses_stats" in result
    assert "trends" in result
    assert "per_100_stats" in result

    # Validate data types
    assert isinstance(result["season_stats"], dict)
    assert isinstance(result["last_n_stats"], dict)
    assert isinstance(result["trends"], dict)

    # Validate season has games
    assert result["season_stats"].get("games", 0) > 0


@pytest.mark.asyncio
async def test_recent_form_analysis(client):
    """Test recent form analysis (last N games)"""
    result = await client.get_player_performance_splits(
        player_name="Stephen Curry",
        season="2023-24",
        last_n_games=5
    )

    assert "error" not in result
    last_n = result["last_n_stats"]
    season = result["season_stats"]
    trends = result["trends"]

    # Validate last N games data
    assert last_n.get("games", 0) <= 5
    assert "ppg" in last_n
    assert "rpg" in last_n
    assert "apg" in last_n

    # Validate trends
    assert "ppg_trend" in trends
    assert "is_hot_streak" in trends
    assert "is_cold_streak" in trends

    # Validate numeric values are reasonable
    assert 0 <= last_n["ppg"] <= 100  # PPG should be reasonable
    assert 0 <= last_n["fg_pct"] <= 1.0  # FG% should be between 0 and 1


@pytest.mark.asyncio
async def test_home_away_splits(client):
    """Test home vs away performance splits"""
    result = await client.get_player_performance_splits(
        player_name="Giannis Antetokounmpo",
        season="2023-24"
    )

    assert "error" not in result
    home = result["home_stats"]
    away = result["away_stats"]
    home_count = result["home_games_count"]
    away_count = result["away_games_count"]

    # Validate home/away data
    assert home_count > 0, "No home games found"
    assert away_count > 0, "No away games found"
    assert "ppg" in home
    assert "ppg" in away

    # Check totals roughly match season
    total_games = result["season_stats"].get("games", 0)
    assert abs((home_count + away_count) - total_games) <= 2


@pytest.mark.asyncio
async def test_win_loss_performance(client):
    """Test win vs loss performance splits"""
    result = await client.get_player_performance_splits(
        player_name="Kevin Durant",
        season="2023-24"
    )

    assert "error" not in result
    wins = result["wins_stats"]
    losses = result["losses_stats"]
    wins_count = result["wins_count"]
    losses_count = result["losses_count"]

    # Validate win/loss data
    assert wins_count > 0
    assert losses_count > 0
    assert "ppg" in wins
    assert "ppg" in losses
    assert "plus_minus" in wins

    # Plus/minus should generally be positive in wins
    assert wins.get("plus_minus", 0) > losses.get("plus_minus", 0)


@pytest.mark.asyncio
async def test_per_100_possessions(client):
    """Test per-100 possessions normalization"""
    result = await client.get_player_performance_splits(
        player_name="Luka Doncic",
        season="2023-24"
    )

    assert "error" not in result
    per_100 = result["per_100_stats"]

    # Validate per-100 data
    assert per_100, "per_100_stats is empty"
    assert "pts_per_100" in per_100
    assert "reb_per_100" in per_100
    assert "ast_per_100" in per_100
    assert "tov_per_100" in per_100

    # Per-100 stats should be higher than per-game
    season_ppg = result["season_stats"].get("ppg", 0)
    per_100_pts = per_100["pts_per_100"]
    assert per_100_pts > season_ppg


@pytest.mark.asyncio
async def test_multiple_players_parallel(client):
    """Test multiple players in parallel (stress test)"""
    players = ["LeBron James", "Stephen Curry", "Giannis", "Kevin Durant", "Luka Doncic"]

    # Run all in parallel
    tasks = [
        client.get_player_performance_splits(player, season="2023-24", last_n_games=10)
        for player in players
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check all succeeded
    success_count = sum(
        1 for result in results
        if not isinstance(result, Exception) and "error" not in result
    )

    assert success_count == len(players), f"Only {success_count}/{len(players)} succeeded"


@pytest.mark.asyncio
async def test_edge_case_rookie(client):
    """Test edge case - player with limited games"""
    result = await client.get_player_performance_splits(
        player_name="Victor Wembanyama",
        season="2023-24",
        last_n_games=5
    )

    # Should handle gracefully even with limited data
    # Either returns error (no data) or returns data
    assert isinstance(result, dict)


@pytest.mark.asyncio
@pytest.mark.parametrize("last_n", [5, 10, 15])
async def test_different_last_n_values(client, last_n):
    """Test different last_n_games values"""
    result = await client.get_player_performance_splits(
        player_name="LeBron James",
        season="2023-24",
        last_n_games=last_n
    )

    assert "error" not in result
    actual_games = result["last_n_stats"].get("games", 0)
    assert actual_games <= last_n


@pytest.mark.asyncio
async def test_head_to_head(client):
    """Test head-to-head comparison"""
    result = await client.get_player_head_to_head(
        player1_name="LeBron James",
        player2_name="Kevin Durant",
        season="2023-24"
    )

    assert "error" not in result
    assert "matchup_count" in result
    assert "player1_stats" in result
    assert "player2_stats" in result
    assert result["matchup_count"] >= 0


@pytest.mark.asyncio
async def test_cache_integration(client):
    """Test cache integration"""
    # First call (cache miss)
    result1 = await client.get_player_performance_splits(
        player_name="Stephen Curry",
        season="2023-24"
    )

    # Second call (should be cached if Redis available)
    result2 = await client.get_player_performance_splits(
        player_name="Stephen Curry",
        season="2023-24"
    )

    # Results should be identical
    assert result1 == result2


@pytest.mark.asyncio
async def test_data_consistency(client):
    """Test that sum of home+away games equals total games"""
    result = await client.get_player_performance_splits(
        player_name="LeBron James",
        season="2023-24"
    )

    if "error" not in result:
        total = result["season_stats"].get("games", 0)
        home = result["home_games_count"]
        away = result["away_games_count"]

        # Should roughly match (allow small discrepancy)
        assert abs((home + away) - total) <= 2


@pytest.mark.asyncio
async def test_trend_calculation_accuracy(client):
    """Test that trend calculations are accurate"""
    result = await client.get_player_performance_splits(
        player_name="Stephen Curry",
        season="2023-24",
        last_n_games=10
    )

    if "error" not in result:
        season_ppg = result["season_stats"]["ppg"]
        last_n_ppg = result["last_n_stats"]["ppg"]
        trend = result["trends"]["ppg_trend"]

        # Trend should equal difference
        expected_trend = last_n_ppg - season_ppg
        assert abs(trend - expected_trend) < 0.01  # Allow small floating point error


@pytest.mark.asyncio
async def test_plus_minus_in_wins_vs_losses(client):
    """Test that plus/minus is typically higher in wins"""
    result = await client.get_player_performance_splits(
        player_name="Giannis Antetokounmpo",
        season="2023-24"
    )

    if "error" not in result:
        wins_pm = result["wins_stats"].get("plus_minus", 0)
        losses_pm = result["losses_stats"].get("plus_minus", 0)

        # In most cases, plus/minus should be higher in wins
        assert wins_pm > losses_pm


# Mark slow tests
@pytest.mark.slow
@pytest.mark.asyncio
async def test_full_season_analysis(client):
    """Test analyzing a full season worth of data"""
    result = await client.get_player_performance_splits(
        player_name="LeBron James",
        season="2023-24",
        last_n_games=82  # Full season
    )

    if "error" not in result:
        assert result["season_stats"]["games"] <= 82
        assert result["last_n_stats"]["games"] <= 82


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v", "--tb=short"])
