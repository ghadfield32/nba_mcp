#!/usr/bin/env python3
"""
Systematic validation script for Weeks 1-4.

Runs through all validation tests and produces a comprehensive report.
"""

import asyncio
import sys
import time
from typing import Dict, Any, List
sys.path.insert(0, '/home/user/nba_mcp')


class ValidationReport:
    """Tracks validation results."""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def add_result(self, test_name: str, status: str, message: str = ""):
        """Add a test result."""
        self.results.append({
            "test": test_name,
            "status": status,
            "message": message
        })
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        else:
            self.skipped += 1

    def print_report(self):
        """Print validation report."""
        print("\n" + "="*70)
        print("VALIDATION REPORT")
        print("="*70)
        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Skipped: {self.skipped}")
        print(f"Success Rate: {self.passed / len(self.results) * 100:.1f}%")
        print("="*70)

        for result in self.results:
            status_emoji = {"PASS": "✓", "FAIL": "✗", "SKIP": "○"}[result["status"]]
            print(f"{status_emoji} {result['test']}")
            if result["message"]:
                print(f"  {result['message']}")


async def validate_week1(report: ValidationReport):
    """Validate Week 1: Foundations."""
    print("\n" + "="*70)
    print("WEEK 1: FOUNDATIONS")
    print("="*70)

    # 1.1 Entity Resolution
    print("\n1.1 Entity Resolution & Caching")
    try:
        from nba_mcp.api.entity_resolver import resolve_entity
        from nba_mcp.api.errors import EntityNotFoundError

        # Test 1: Exact player match
        entity = resolve_entity("LeBron James", entity_type="player")
        assert entity.confidence >= 0.9, f"Confidence too low: {entity.confidence}"
        assert entity.entity_type == "player"
        report.add_result("Entity: Exact player match", "PASS", f"Confidence: {entity.confidence:.2f}")

        # Test 2: Partial player match
        entity = resolve_entity("LeBron", entity_type="player")
        assert entity.confidence >= 0.7, f"Confidence too low: {entity.confidence}"
        assert "LeBron" in entity.name
        report.add_result("Entity: Partial player match", "PASS", f"Found: {entity.name}")

        # Test 3: Team abbreviation
        entity = resolve_entity("LAL", entity_type="team")
        assert entity.confidence == 1.0, f"Confidence should be 1.0, got {entity.confidence}"
        assert entity.abbreviation == "LAL"
        report.add_result("Entity: Team abbreviation", "PASS", f"Team: {entity.name}")

        # Test 4: Invalid entity raises error
        try:
            resolve_entity("XYZNOTEREAL999", entity_type="player")
            report.add_result("Entity: Invalid entity error", "FAIL", "Should have raised EntityNotFoundError")
        except EntityNotFoundError as e:
            assert e.code == "ENTITY_NOT_FOUND"
            assert len(e.details.get("suggestions", [])) > 0
            report.add_result("Entity: Invalid entity error", "PASS", f"Suggestions: {len(e.details['suggestions'])}")

    except Exception as e:
        report.add_result("Entity Resolution", "FAIL", str(e))

    # 1.2 Response Envelope
    print("\n1.2 Standard Response Envelope")
    try:
        from nba_mcp.api.models import success_response, error_response, ResponseEnvelope

        # Test 1: Success response structure
        resp = success_response(data={"key": "value"}, source="historical")
        assert resp.status == "success"
        assert resp.data == {"key": "value"}
        assert resp.metadata.version == "v1"
        report.add_result("Envelope: Success response", "PASS")

        # Test 2: Error response structure
        err = error_response("TEST_ERROR", "Test message", severity="error")
        assert err.status == "error"
        assert len(err.errors) == 1
        assert err.errors[0].code == "TEST_ERROR"
        report.add_result("Envelope: Error response", "PASS")

        # Test 3: Deterministic JSON
        json1 = resp.to_json_string()
        json2 = resp.to_json_string()
        assert json1 == json2, "JSON not deterministic"
        report.add_result("Envelope: Deterministic JSON", "PASS")

    except Exception as e:
        report.add_result("Response Envelope", "FAIL", str(e))

    # 1.3 Error Taxonomy
    print("\n1.3 Error Taxonomy & Resilience")
    try:
        from nba_mcp.api.errors import (
            NBAMCPError, EntityNotFoundError, InvalidParameterError, RateLimitError
        )

        # Test 1: Error hierarchy
        try:
            raise EntityNotFoundError(entity_type="player", query="invalid")
        except NBAMCPError as e:
            assert e.code == "ENTITY_NOT_FOUND"
            report.add_result("Errors: Exception hierarchy", "PASS")

        # Test 2: Error codes
        try:
            raise InvalidParameterError(param_name="test", param_value="bad")
        except NBAMCPError as e:
            assert e.code == "INVALID_PARAMETER"
            assert e.retryable == False
            report.add_result("Errors: Error codes", "PASS")

    except Exception as e:
        report.add_result("Error Taxonomy", "FAIL", str(e))


async def validate_week2(report: ValidationReport):
    """Validate Week 2: Core Data Coverage."""
    print("\n" + "="*70)
    print("WEEK 2: CORE DATA COVERAGE")
    print("="*70)

    print("\n2.1 Team Statistics (Mock Test - avoiding API calls)")
    try:
        from nba_mcp.api.advanced_stats import get_team_standings, get_team_advanced_stats

        # Note: We're not making real API calls to avoid rate limits
        # Instead, we verify the functions exist and have correct signatures
        import inspect

        # Verify get_team_standings signature
        sig = inspect.signature(get_team_standings)
        assert "season" in sig.parameters
        assert "conference" in sig.parameters
        report.add_result("Team: get_team_standings signature", "PASS")

        # Verify get_team_advanced_stats signature
        sig = inspect.signature(get_team_advanced_stats)
        assert "team_abbr" in sig.parameters
        assert "season" in sig.parameters
        report.add_result("Team: get_team_advanced_stats signature", "PASS")

    except Exception as e:
        report.add_result("Team Statistics", "FAIL", str(e))

    print("\n2.2 Player Statistics")
    try:
        from nba_mcp.api.advanced_stats import get_player_advanced_stats, compare_players
        import inspect

        # Verify signatures
        sig = inspect.signature(get_player_advanced_stats)
        assert "player_name" in sig.parameters
        report.add_result("Player: get_player_advanced_stats signature", "PASS")

        sig = inspect.signature(compare_players)
        assert "player1_name" in sig.parameters
        assert "player2_name" in sig.parameters
        report.add_result("Player: compare_players signature", "PASS")

    except Exception as e:
        report.add_result("Player Statistics", "FAIL", str(e))


async def validate_week3(report: ValidationReport):
    """Validate Week 3: NLQ Pipeline."""
    print("\n" + "="*70)
    print("WEEK 3: NATURAL LANGUAGE QUERY")
    print("="*70)

    print("\n3.1 Query Parser")
    try:
        from nba_mcp.nlq.parser import parse_query

        # Test 1: Leaders query
        parsed = await parse_query("Who leads the NBA in assists?")
        assert parsed.intent == "leaders"
        report.add_result("Parser: Leaders intent", "PASS", f"Intent: {parsed.intent}")

        # Test 2: Comparison query
        parsed = await parse_query("Compare LeBron James and Kevin Durant")
        assert parsed.intent == "comparison_players"
        assert len(parsed.entities) >= 2
        report.add_result("Parser: Comparison intent", "PASS", f"Entities: {len(parsed.entities)}")

    except Exception as e:
        report.add_result("Query Parser", "FAIL", str(e))

    print("\n3.2 Execution Planner")
    try:
        from nba_mcp.nlq.planner import plan_query_execution
        from nba_mcp.nlq.parser import ParsedQuery

        # Test with mock parsed query
        parsed = ParsedQuery(
            query="test query",
            intent="leaders",
            entities=[],
            stat_types=["AST"],
            time_range={},
            modifiers={}
        )
        plan = await plan_query_execution(parsed)
        assert plan.template_name == "leaders"
        assert len(plan.tool_calls) > 0
        report.add_result("Planner: Leaders template", "PASS", f"Tools: {len(plan.tool_calls)}")

    except Exception as e:
        report.add_result("Execution Planner", "FAIL", str(e))

    print("\n3.3 NLQ Pipeline Integration")
    try:
        from nba_mcp.nlq.pipeline import answer_nba_question
        from nba_mcp.nlq.mock_tools import register_mock_tools

        # Register mock tools to avoid API calls
        register_mock_tools()

        # Test end-to-end
        answer = await answer_nba_question("Who are the top scorers?", return_metadata=False)
        assert len(answer) > 50, "Answer too short"
        report.add_result("NLQ: End-to-end pipeline", "PASS", f"Answer length: {len(answer)}")

    except Exception as e:
        report.add_result("NLQ Pipeline", "FAIL", str(e))


async def validate_week4(report: ValidationReport):
    """Validate Week 4: Scale & Observability."""
    print("\n" + "="*70)
    print("WEEK 4: SCALE & OBSERVABILITY")
    print("="*70)

    print("\n4.1 Redis Caching")
    try:
        from nba_mcp.cache.redis_cache import CacheTier, get_cache_key

        # Test TTL tiers
        assert CacheTier.LIVE.value == 30
        assert CacheTier.DAILY.value == 3600
        assert CacheTier.HISTORICAL.value == 86400
        assert CacheTier.STATIC.value == 604800
        report.add_result("Cache: TTL tiers defined", "PASS")

        # Test cache key generation
        key1 = get_cache_key("test_func", {"param": "value"})
        key2 = get_cache_key("test_func", {"param": "value"})
        assert key1 == key2, "Cache keys not deterministic"
        report.add_result("Cache: Deterministic keys", "PASS")

    except Exception as e:
        report.add_result("Redis Caching", "FAIL", str(e))

    print("\n4.2 Rate Limiting")
    try:
        from nba_mcp.rate_limit.token_bucket import TokenBucket, RateLimiter

        # Test token bucket
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) == True
        assert bucket.tokens == 5.0
        assert bucket.consume(10) == False  # Not enough
        report.add_result("Rate Limit: Token bucket", "PASS")

        # Test rate limiter
        limiter = RateLimiter()
        limiter.add_limit("test_api", capacity=10, refill_rate=1.0)
        allowed, retry_after = limiter.check_limit("test_api", tokens=5)
        assert allowed == True
        report.add_result("Rate Limit: Multi-bucket manager", "PASS")

    except Exception as e:
        report.add_result("Rate Limiting", "FAIL", str(e))

    print("\n4.3 Observability")
    try:
        from nba_mcp.observability import initialize_metrics, get_metrics_snapshot

        # Initialize metrics
        initialize_metrics()
        snapshot = get_metrics_snapshot()
        assert "server_uptime_seconds" in snapshot
        report.add_result("Metrics: Initialization", "PASS")

        # Test tracing
        from nba_mcp.observability import initialize_tracing, get_tracing_manager
        initialize_tracing(service_name="test")
        tracer = get_tracing_manager()
        assert tracer is not None
        report.add_result("Tracing: Initialization", "PASS")

    except Exception as e:
        report.add_result("Observability", "FAIL", str(e))

    print("\n4.4 Golden Tests")
    try:
        from tests.golden import GOLDEN_QUERIES, get_query_statistics

        # Verify query count
        assert len(GOLDEN_QUERIES) == 20, f"Expected 20 queries, got {len(GOLDEN_QUERIES)}"
        report.add_result("Golden: Query count", "PASS", "20 queries defined")

        # Verify statistics
        stats = get_query_statistics()
        assert stats["total_queries"] == 20
        assert len(stats["categories"]) >= 5
        report.add_result("Golden: Statistics", "PASS", f"{len(stats['categories'])} categories")

    except Exception as e:
        report.add_result("Golden Tests", "FAIL", str(e))


async def main():
    """Run all validations."""
    print("\n" + "="*70)
    print("NBA MCP WEEKS 1-4 VALIDATION")
    print("="*70)
    print("\nThis script validates all implementations from Weeks 1-4.")
    print("Some tests use mock data to avoid NBA API rate limits.")
    print("="*70)

    report = ValidationReport()

    try:
        await validate_week1(report)
        await validate_week2(report)
        await validate_week3(report)
        await validate_week4(report)
    except Exception as e:
        print(f"\n❌ Fatal error during validation: {e}")
        import traceback
        traceback.print_exc()

    # Print final report
    report.print_report()

    # Exit code based on failures
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
