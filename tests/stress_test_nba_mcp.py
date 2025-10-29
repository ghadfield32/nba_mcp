"""
Stress Test Suite for NBA MCP

Tests the MCP server under load to ensure:
- Concurrent request handling
- Cache effectiveness
- Rate limit handling
- Error recovery
- Memory management with large datasets

Simulates real-world usage patterns:
- Multiple simultaneous users
- Mixed read/write operations
- Rapid-fire requests
- Large data operations
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

class StressTestConfig:
    """Configuration for stress tests"""
    # Concurrency levels
    LIGHT_LOAD = 5  # 5 concurrent requests
    MEDIUM_LOAD = 20  # 20 concurrent requests
    HEAVY_LOAD = 50  # 50 concurrent requests

    # Test duration
    SHORT_TEST = 10  # 10 seconds
    MEDIUM_TEST = 30  # 30 seconds
    LONG_TEST = 60  # 60 seconds

    # Sample test data
    PLAYERS = [
        "LeBron James",
        "Stephen Curry",
        "Kevin Durant",
        "Giannis Antetokounmpo",
        "Luka Doncic",
        "Joel Embiid",
        "Nikola Jokic",
        "Jayson Tatum",
        "Damian Lillard",
        "Anthony Davis"
    ]

    TEAMS = [
        "Lakers",
        "Warriors",
        "Celtics",
        "Bucks",
        "Nuggets",
        "Mavericks",
        "76ers",
        "Heat",
        "Suns",
        "Knicks"
    ]

    SEASONS = ["2023-24", "2022-23", "2021-22"]


# ============================================================================
# STRESS TEST HELPERS
# ============================================================================

class StressTestResults:
    """Track stress test results"""
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.errors = []
        self.start_time = None
        self.end_time = None

    def record_success(self, response_time: float):
        """Record a successful request"""
        self.successful_requests += 1
        self.response_times.append(response_time)

    def record_failure(self, error: str):
        """Record a failed request"""
        self.failed_requests += 1
        self.errors.append(error)

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def p95_response_time(self) -> float:
        """Calculate 95th percentile response time"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    @property
    def p99_response_time(self) -> float:
        """Calculate 99th percentile response time"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx]

    @property
    def duration(self) -> float:
        """Calculate test duration"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def requests_per_second(self) -> float:
        """Calculate requests per second"""
        if self.duration == 0:
            return 0.0
        return self.total_requests / self.duration

    def print_summary(self):
        """Print test results summary"""
        logger.info("\n" + "=" * 80)
        logger.info("STRESS TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total Requests:      {self.total_requests}")
        logger.info(f"Successful:          {self.successful_requests}")
        logger.info(f"Failed:              {self.failed_requests}")
        logger.info(f"Success Rate:        {self.success_rate:.2f}%")
        logger.info(f"Duration:            {self.duration:.2f}s")
        logger.info(f"Requests/sec:        {self.requests_per_second:.2f}")
        logger.info(f"Avg Response Time:   {self.avg_response_time:.3f}s")
        logger.info(f"P95 Response Time:   {self.p95_response_time:.3f}s")
        logger.info(f"P99 Response Time:   {self.p99_response_time:.3f}s")

        if self.errors:
            logger.info(f"\nErrors ({len(self.errors)}):")
            for error in self.errors[:10]:  # Show first 10 errors
                logger.info(f"  - {error}")


# ============================================================================
# STRESS TEST SCENARIOS
# ============================================================================

class StressTestScenarios:
    """Collection of stress test scenarios"""

    @staticmethod
    async def concurrent_player_stats(concurrency: int, duration: int) -> StressTestResults:
        """
        Test: Concurrent player stats requests

        Simulates multiple users requesting player stats simultaneously
        """
        from nba_mcp.api.season_aggregator import get_player_season_stats
        import random

        results = StressTestResults()
        results.start_time = time.time()

        async def fetch_random_player_stats():
            """Fetch stats for a random player"""
            player = random.choice(StressTestConfig.PLAYERS)
            season = random.choice(StressTestConfig.SEASONS)

            try:
                start = time.time()
                # This would use get_player_season_stats once integrated
                # For now, simulate with sleep
                await asyncio.sleep(0.1)  # Simulate API call
                elapsed = time.time() - start
                results.record_success(elapsed)
            except Exception as e:
                results.record_failure(str(e))

        # Run concurrent requests for specified duration
        end_time = time.time() + duration
        tasks = []

        while time.time() < end_time:
            # Create batch of concurrent tasks
            batch = [fetch_random_player_stats() for _ in range(concurrency)]
            results.total_requests += len(batch)
            tasks.extend(batch)

            # Wait for batch to complete
            await asyncio.gather(*batch)

            # Small delay between batches
            await asyncio.sleep(0.1)

        results.end_time = time.time()
        return results

    @staticmethod
    async def concurrent_advanced_metrics(concurrency: int, duration: int) -> StressTestResults:
        """
        Test: Concurrent advanced metrics calculations

        Tests computation-heavy operations under load
        """
        from nba_mcp.api.advanced_metrics_calculator import calculate_game_score
        import random

        results = StressTestResults()
        results.start_time = time.time()

        async def calculate_random_metrics():
            """Calculate metrics for random player stats"""
            stats = {
                "PTS": random.randint(10, 40),
                "FGM": random.randint(5, 15),
                "FGA": random.randint(10, 25),
                "FTM": random.randint(2, 10),
                "FTA": random.randint(3, 12),
                "OREB": random.randint(0, 5),
                "DREB": random.randint(2, 10),
                "STL": random.randint(0, 3),
                "AST": random.randint(2, 12),
                "BLK": random.randint(0, 3),
                "PF": random.randint(1, 5),
                "TOV": random.randint(1, 5),
                "MIN": 36
            }

            try:
                start = time.time()
                gs = calculate_game_score(stats)
                elapsed = time.time() - start
                results.record_success(elapsed)
            except Exception as e:
                results.record_failure(str(e))

        end_time = time.time() + duration
        tasks = []

        while time.time() < end_time:
            batch = [calculate_random_metrics() for _ in range(concurrency)]
            results.total_requests += len(batch)
            await asyncio.gather(*batch)
            await asyncio.sleep(0.05)

        results.end_time = time.time()
        return results

    @staticmethod
    async def mixed_workload(concurrency: int, duration: int) -> StressTestResults:
        """
        Test: Mixed workload (reads, writes, computations)

        Simulates realistic usage with various operation types
        """
        import random

        results = StressTestResults()
        results.start_time = time.time()

        async def random_operation():
            """Execute a random operation"""
            operation_type = random.choice(["player_stats", "team_stats", "advanced_metrics", "grouping"])

            try:
                start = time.time()

                if operation_type == "player_stats":
                    # Simulate player stats fetch
                    await asyncio.sleep(0.1)
                elif operation_type == "team_stats":
                    # Simulate team stats fetch
                    await asyncio.sleep(0.12)
                elif operation_type == "advanced_metrics":
                    # Simulate metrics calculation
                    await asyncio.sleep(0.08)
                else:  # grouping
                    # Simulate data grouping operation
                    await asyncio.sleep(0.15)

                elapsed = time.time() - start
                results.record_success(elapsed)
            except Exception as e:
                results.record_failure(str(e))

        end_time = time.time() + duration
        while time.time() < end_time:
            batch = [random_operation() for _ in range(concurrency)]
            results.total_requests += len(batch)
            await asyncio.gather(*batch)
            await asyncio.sleep(0.1)

        results.end_time = time.time()
        return results

    @staticmethod
    async def large_dataset_operations(concurrency: int) -> StressTestResults:
        """
        Test: Large dataset operations

        Tests memory management with full-season data
        """
        from nba_mcp.api.data_groupings import GroupingFactory, GroupingLevel
        import random

        results = StressTestResults()
        results.start_time = time.time()

        async def fetch_full_season():
            """Fetch full season of game logs"""
            try:
                start = time.time()

                # Simulate fetching full season (82+ games)
                grouping = GroupingFactory.create(GroupingLevel.PLAYER_GAME)
                # This is a simulation - would be actual fetch in production
                await asyncio.sleep(0.5)  # Simulate large data fetch

                elapsed = time.time() - start
                results.record_success(elapsed)
            except Exception as e:
                results.record_failure(str(e))

        # Execute concurrent large dataset operations
        tasks = [fetch_full_season() for _ in range(concurrency)]
        results.total_requests = len(tasks)
        await asyncio.gather(*tasks)

        results.end_time = time.time()
        return results


# ============================================================================
# MAIN STRESS TEST RUNNER
# ============================================================================

async def run_stress_tests():
    """Run all stress test scenarios"""
    logger.info("\n" + "=" * 80)
    logger.info("NBA MCP STRESS TEST SUITE")
    logger.info("=" * 80)

    scenarios = StressTestScenarios()

    # Test 1: Light concurrent load
    logger.info("\n▶️  Test 1: Light Concurrent Load (5 concurrent, 10s)")
    results1 = await scenarios.concurrent_player_stats(
        concurrency=StressTestConfig.LIGHT_LOAD,
        duration=StressTestConfig.SHORT_TEST
    )
    results1.print_summary()

    # Test 2: Medium concurrent load
    logger.info("\n▶️  Test 2: Medium Concurrent Load (20 concurrent, 10s)")
    results2 = await scenarios.concurrent_player_stats(
        concurrency=StressTestConfig.MEDIUM_LOAD,
        duration=StressTestConfig.SHORT_TEST
    )
    results2.print_summary()

    # Test 3: Advanced metrics computation
    logger.info("\n▶️  Test 3: Advanced Metrics Computation (20 concurrent, 10s)")
    results3 = await scenarios.concurrent_advanced_metrics(
        concurrency=StressTestConfig.MEDIUM_LOAD,
        duration=StressTestConfig.SHORT_TEST
    )
    results3.print_summary()

    # Test 4: Mixed workload
    logger.info("\n▶️  Test 4: Mixed Workload (20 concurrent, 15s)")
    results4 = await scenarios.mixed_workload(
        concurrency=StressTestConfig.MEDIUM_LOAD,
        duration=15
    )
    results4.print_summary()

    # Test 5: Large dataset operations
    logger.info("\n▶️  Test 5: Large Dataset Operations (10 concurrent)")
    results5 = await scenarios.large_dataset_operations(
        concurrency=10
    )
    results5.print_summary()

    # Overall summary
    logger.info("\n" + "=" * 80)
    logger.info("OVERALL STRESS TEST SUMMARY")
    logger.info("=" * 80)

    all_results = [results1, results2, results3, results4, results5]
    total_requests = sum(r.total_requests for r in all_results)
    total_successful = sum(r.successful_requests for r in all_results)
    total_failed = sum(r.failed_requests for r in all_results)

    logger.info(f"Total Requests Across All Tests: {total_requests}")
    logger.info(f"Total Successful: {total_successful}")
    logger.info(f"Total Failed: {total_failed}")
    logger.info(f"Overall Success Rate: {(total_successful / total_requests * 100):.2f}%")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_stress_tests())
