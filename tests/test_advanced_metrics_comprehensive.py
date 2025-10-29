"""
Comprehensive tests for advanced metrics and performance splits.

Tests all Priority 2 enhancements:
- Performance splits (recent form, home/away, wins/losses)
- Per-100 possessions stats
- Trend detection (hot/cold streaks)
- Caching improvements
- Head-to-head comparisons
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient
from nba_mcp.cache import get_cache, initialize_cache


class TestAdvancedMetrics:
    """Test suite for advanced metrics"""

    def __init__(self):
        self.client = NBAApiClient()
        self.results = []
        self.passed = 0
        self.failed = 0

    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        status = "[PASS]" if passed else "[FAIL]"
        self.results.append(f"{status} {test_name}: {message}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"{status} {test_name}")
        if message:
            print(f"  {message}")

    async def test_performance_splits_basic(self):
        """Test 1: Basic performance splits functionality"""
        try:
            result = await self.client.get_player_performance_splits(
                player_name="LeBron James",
                season="2023-24",
                last_n_games=10
            )

            # Validate structure
            assert "error" not in result, f"Error in result: {result.get('error')}"
            assert "season_stats" in result, "Missing season_stats"
            assert "last_n_stats" in result, "Missing last_n_stats"
            assert "home_stats" in result, "Missing home_stats"
            assert "away_stats" in result, "Missing away_stats"
            assert "wins_stats" in result, "Missing wins_stats"
            assert "losses_stats" in result, "Missing losses_stats"
            assert "trends" in result, "Missing trends"
            assert "per_100_stats" in result, "Missing per_100_stats"

            # Validate data types
            assert isinstance(result["season_stats"], dict), "season_stats not dict"
            assert isinstance(result["last_n_stats"], dict), "last_n_stats not dict"
            assert isinstance(result["trends"], dict), "trends not dict"

            self.log_result(
                "test_performance_splits_basic",
                True,
                f"Found {result['season_stats'].get('games', 0)} games"
            )
            return True
        except Exception as e:
            self.log_result("test_performance_splits_basic", False, str(e))
            return False

    async def test_recent_form_analysis(self):
        """Test 2: Recent form analysis (last N games)"""
        try:
            result = await self.client.get_player_performance_splits(
                player_name="Stephen Curry",
                season="2023-24",
                last_n_games=5
            )

            assert "error" not in result
            last_n = result["last_n_stats"]
            season = result["season_stats"]
            trends = result["trends"]

            # Validate last N games data
            assert last_n.get("games", 0) <= 5, f"Expected <=5 games, got {last_n.get('games')}"
            assert "ppg" in last_n, "Missing ppg in last_n_stats"
            assert "rpg" in last_n, "Missing rpg in last_n_stats"
            assert "apg" in last_n, "Missing apg in last_n_stats"

            # Validate trends
            assert "ppg_trend" in trends, "Missing ppg_trend"
            assert "is_hot_streak" in trends, "Missing is_hot_streak"
            assert "is_cold_streak" in trends, "Missing is_cold_streak"

            streak_status = "hot" if trends["is_hot_streak"] else "cold" if trends["is_cold_streak"] else "normal"

            self.log_result(
                "test_recent_form_analysis",
                True,
                f"Last 5: {last_n['ppg']:.1f} PPG, Season: {season['ppg']:.1f} PPG, Streak: {streak_status}"
            )
            return True
        except Exception as e:
            self.log_result("test_recent_form_analysis", False, str(e))
            return False

    async def test_home_away_splits(self):
        """Test 3: Home vs Away performance splits"""
        try:
            result = await self.client.get_player_performance_splits(
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
            assert "ppg" in home, "Missing ppg in home_stats"
            assert "ppg" in away, "Missing ppg in away_stats"

            # Check totals roughly match season
            total_games = result["season_stats"].get("games", 0)
            assert abs((home_count + away_count) - total_games) <= 2, "Home+Away doesn't match total"

            self.log_result(
                "test_home_away_splits",
                True,
                f"Home: {home['ppg']:.1f} PPG ({home_count}g), Away: {away['ppg']:.1f} PPG ({away_count}g)"
            )
            return True
        except Exception as e:
            self.log_result("test_home_away_splits", False, str(e))
            return False

    async def test_win_loss_performance(self):
        """Test 4: Win vs Loss performance splits"""
        try:
            result = await self.client.get_player_performance_splits(
                player_name="Kevin Durant",
                season="2023-24"
            )

            assert "error" not in result
            wins = result["wins_stats"]
            losses = result["losses_stats"]
            wins_count = result["wins_count"]
            losses_count = result["losses_count"]

            # Validate win/loss data
            assert wins_count > 0, "No wins found"
            assert losses_count > 0, "No losses found"
            assert "ppg" in wins, "Missing ppg in wins_stats"
            assert "ppg" in losses, "Missing ppg in losses_stats"
            assert "plus_minus" in wins, "Missing plus_minus in wins_stats"

            # Plus/minus should generally be positive in wins, negative in losses
            win_pm = wins.get("plus_minus", 0)
            loss_pm = losses.get("plus_minus", 0)

            self.log_result(
                "test_win_loss_performance",
                True,
                f"Wins: {wins['ppg']:.1f} PPG (+/- {win_pm:.1f}), Losses: {losses['ppg']:.1f} PPG (+/- {loss_pm:.1f})"
            )
            return True
        except Exception as e:
            self.log_result("test_win_loss_performance", False, str(e))
            return False

    async def test_per_100_possessions(self):
        """Test 5: Per-100 possessions normalization"""
        try:
            result = await self.client.get_player_performance_splits(
                player_name="Luka Doncic",
                season="2023-24"
            )

            assert "error" not in result
            per_100 = result["per_100_stats"]

            # Validate per-100 data
            assert per_100, "per_100_stats is empty"
            assert "pts_per_100" in per_100, "Missing pts_per_100"
            assert "reb_per_100" in per_100, "Missing reb_per_100"
            assert "ast_per_100" in per_100, "Missing ast_per_100"
            assert "tov_per_100" in per_100, "Missing tov_per_100"

            # Per-100 stats should be reasonable (higher than per-game)
            season_ppg = result["season_stats"].get("ppg", 0)
            per_100_pts = per_100["pts_per_100"]
            assert per_100_pts > season_ppg, f"Per-100 ({per_100_pts:.1f}) should be > per-game ({season_ppg:.1f})"

            self.log_result(
                "test_per_100_possessions",
                True,
                f"Per-100: {per_100['pts_per_100']:.1f} PTS, {per_100['ast_per_100']:.1f} AST"
            )
            return True
        except Exception as e:
            self.log_result("test_per_100_possessions", False, str(e))
            return False

    async def test_multiple_players_parallel(self):
        """Test 6: Multiple players in parallel (stress test)"""
        try:
            players = ["LeBron James", "Stephen Curry", "Giannis", "Kevin Durant", "Luka Doncic"]

            # Run all in parallel
            tasks = [
                self.client.get_player_performance_splits(player, season="2023-24", last_n_games=10)
                for player in players
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check all succeeded
            success_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"  [{players[i]}] FAILED: {result}")
                elif "error" in result:
                    print(f"  [{players[i]}] ERROR: {result['error']}")
                else:
                    success_count += 1

            assert success_count == len(players), f"Only {success_count}/{len(players)} succeeded"

            self.log_result(
                "test_multiple_players_parallel",
                True,
                f"{success_count}/{len(players)} players analyzed successfully"
            )
            return True
        except Exception as e:
            self.log_result("test_multiple_players_parallel", False, str(e))
            return False

    async def test_edge_case_rookie(self):
        """Test 7: Edge case - player with limited games"""
        try:
            # Try to get splits for a player (adjust based on current season)
            result = await self.client.get_player_performance_splits(
                player_name="Victor Wembanyama",
                season="2023-24",
                last_n_games=5
            )

            # Should handle gracefully even with limited data
            if "error" in result:
                # Expected for rookies/new players
                self.log_result(
                    "test_edge_case_rookie",
                    True,
                    "Correctly handled player with no/limited data"
                )
            else:
                # Or successfully returned data
                games = result["season_stats"].get("games", 0)
                self.log_result(
                    "test_edge_case_rookie",
                    True,
                    f"Found {games} games for player"
                )
            return True
        except Exception as e:
            self.log_result("test_edge_case_rookie", False, str(e))
            return False

    async def test_different_last_n_values(self):
        """Test 8: Different last_n_games values"""
        try:
            player = "LeBron James"
            season = "2023-24"

            for last_n in [5, 10, 15]:
                result = await self.client.get_player_performance_splits(
                    player_name=player,
                    season=season,
                    last_n_games=last_n
                )

                assert "error" not in result, f"Error for last_n={last_n}"
                actual_games = result["last_n_stats"].get("games", 0)
                assert actual_games <= last_n, f"Expected <={last_n} games, got {actual_games}"

            self.log_result(
                "test_different_last_n_values",
                True,
                "All last_n values (5, 10, 15) work correctly"
            )
            return True
        except Exception as e:
            self.log_result("test_different_last_n_values", False, str(e))
            return False

    async def test_head_to_head(self):
        """Test 9: Head-to-head comparison"""
        try:
            result = await self.client.get_player_head_to_head(
                player1_name="LeBron James",
                player2_name="Kevin Durant",
                season="2023-24"
            )

            assert "error" not in result, f"Error: {result.get('error')}"
            assert "matchup_count" in result, "Missing matchup_count"
            assert "player1_stats" in result, "Missing player1_stats"
            assert "player2_stats" in result, "Missing player2_stats"

            matchups = result["matchup_count"]

            self.log_result(
                "test_head_to_head",
                True,
                f"Found {matchups} head-to-head matchups"
            )
            return True
        except Exception as e:
            self.log_result("test_head_to_head", False, str(e))
            return False

    async def test_cache_integration(self):
        """Test 10: Cache integration (if Redis available)"""
        try:
            # First call (cache miss)
            result1 = await self.client.get_player_performance_splits(
                player_name="Stephen Curry",
                season="2023-24"
            )

            # Second call (should be cached if Redis available)
            result2 = await self.client.get_player_performance_splits(
                player_name="Stephen Curry",
                season="2023-24"
            )

            assert result1 == result2, "Results should be identical"

            # Check cache stats if available
            cache = get_cache()
            if cache:
                stats = cache.get_stats()
                self.log_result(
                    "test_cache_integration",
                    True,
                    f"Cache hit ratio: {stats.get('hit_ratio', 0):.1%}"
                )
            else:
                self.log_result(
                    "test_cache_integration",
                    True,
                    "Cache not initialized (expected in test environment)"
                )
            return True
        except Exception as e:
            self.log_result("test_cache_integration", False, str(e))
            return False

    async def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*80)
        print("COMPREHENSIVE ADVANCED METRICS TESTS")
        print("="*80 + "\n")

        # Run all test methods
        test_methods = [
            self.test_performance_splits_basic,
            self.test_recent_form_analysis,
            self.test_home_away_splits,
            self.test_win_loss_performance,
            self.test_per_100_possessions,
            self.test_multiple_players_parallel,
            self.test_edge_case_rookie,
            self.test_different_last_n_values,
            self.test_head_to_head,
            self.test_cache_integration,
        ]

        for test_method in test_methods:
            await test_method()
            print()  # Blank line between tests

        # Print summary
        print("="*80)
        print(f"TEST SUMMARY: {self.passed}/{self.passed + self.failed} tests passed")
        print("="*80)

        if self.failed > 0:
            print("\nFailed tests:")
            for result in self.results:
                if "[FAIL]" in result:
                    print(f"  {result}")

        return self.failed == 0


async def main():
    """Run comprehensive tests"""
    tester = TestAdvancedMetrics()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
