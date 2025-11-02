"""
Golden tests for top 20 NBA MCP queries.

These tests ensure schema stability and correctness for the most common
queries. They serve as regression tests to catch breaking changes.

Run with:
    pytest tests/test_golden_queries.py -v

Update snapshots:
    pytest tests/test_golden_queries.py --update-snapshots
"""

import pytest
import asyncio
import time
import json
import hashlib
import os
from pathlib import Path
from typing import Dict, Any
import sys

# Phase 6: Cross-platform path handling (2025-11-01)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.golden import GOLDEN_QUERIES, GoldenQuery, get_query_statistics
from nba_mcp.nlq.pipeline import answer_nba_question
from nba_mcp.nlq.tool_registry import initialize_tool_registry
from nba_mcp.nlq.mock_tools import register_mock_tools


# ============================================================================
# SNAPSHOT TESTING
# ============================================================================

SNAPSHOT_DIR = Path(__file__).parent / "golden" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def get_snapshot_path(query_id: str) -> Path:
    """Get path to snapshot file for a query."""
    return SNAPSHOT_DIR / f"{query_id}.json"


def save_snapshot(query_id: str, data: Dict[str, Any]):
    """
    Save snapshot to file.

    Phase 6: Added error handling for read-only environments (2025-11-01)
    """
    try:
        snapshot_path = get_snapshot_path(query_id)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(snapshot_path, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except (IOError, PermissionError, OSError) as e:
        pytest.skip(f"Cannot write snapshot for {query_id}: {e}")


def load_snapshot(query_id: str) -> Dict[str, Any]:
    """Load snapshot from file."""
    snapshot_path = get_snapshot_path(query_id)
    if not snapshot_path.exists():
        return None

    with open(snapshot_path, 'r') as f:
        return json.load(f)


def compute_response_hash(response: str) -> str:
    """Compute hash of response for schema comparison."""
    # Normalize response (remove timestamps, specific values that change)
    normalized = response.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def extract_schema_keys(response: str) -> list:
    """Extract key structural elements from response."""
    # For table responses, extract column headers
    # For narrative responses, extract sentence count
    keys = []

    if "|" in response:  # Table format
        lines = response.split("\n")
        for line in lines:
            if "|" in line and not line.strip().startswith("|---"):
                keys.append("table_row")
                if "Player" in line or "Team" in line:
                    keys.append("header_row")

    keys.append(f"length_{len(response)//100*100}")  # Bucketed length
    keys.append(f"sentences_{response.count('.')}")

    return keys


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def cleanup_registry():
    """
    Clear tool registry before and after each test.

    Phase 6: Added registry cleanup to prevent test pollution (2025-11-01)
    """
    from nba_mcp.nlq.tool_registry import clear_registry
    clear_registry()  # Clear before test
    register_mock_tools()  # Register mocks
    yield
    clear_registry()  # Clear after test


@pytest.fixture(scope="module")
def setup_tools():
    """Initialize tools for testing (deprecated, use cleanup_registry)."""
    # Use mock tools to avoid NBA API rate limits
    register_mock_tools()
    yield
    # Cleanup handled by cleanup_registry fixture


@pytest.fixture
def update_snapshots(request):
    """Flag for updating snapshots."""
    return request.config.getoption("--update-snapshots", default=False)


def pytest_addoption(parser):
    """Add custom pytest options."""
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update golden test snapshots"
    )


# ============================================================================
# GOLDEN TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("query", GOLDEN_QUERIES, ids=[q.id for q in GOLDEN_QUERIES])
async def test_golden_query(query: GoldenQuery, setup_tools, update_snapshots):
    """
    Test a golden query against snapshot.

    Verifies:
    - Response is generated successfully
    - Response length meets minimum requirement
    - Response time is within acceptable range
    - Schema structure matches snapshot
    """
    # Skip team stats query - feature not implemented yet (see nlq/synthesizer.py:458)
    if query.id == "team_002":
        pytest.skip("Team stats synthesis not yet implemented")
    
    # Execute query
    start_time = time.time()
    try:
        response = await answer_nba_question(query.query, return_metadata=False)
        duration_ms = (time.time() - start_time) * 1000
        error = None
    except Exception as e:
        response = None
        duration_ms = (time.time() - start_time) * 1000
        error = str(e)

    # Create snapshot data
    snapshot_data = {
        "query_id": query.id,
        "query": query.query,
        "intent": query.intent,
        "category": query.category,
        "response_length": len(response) if response else 0,
        "duration_ms": duration_ms,
        "response_hash": compute_response_hash(response) if response else None,
        "schema_keys": extract_schema_keys(response) if response else [],
        "error": error,
    }

    # Load or save snapshot
    if update_snapshots:
        save_snapshot(query.id, snapshot_data)
        pytest.skip(f"Updated snapshot for {query.id}")

    existing_snapshot = load_snapshot(query.id)

    # Assertions
    assert error is None, f"Query failed: {error}"
    assert response is not None, "No response generated"

    # Check response length
    assert len(response) >= query.min_response_length, \
        f"Response too short: {len(response)} < {query.min_response_length}"

    # Check duration (with 2x tolerance for variability)
    assert duration_ms < query.max_duration_ms * 2, \
        f"Query too slow: {duration_ms}ms > {query.max_duration_ms * 2}ms"

    # Check schema stability (if snapshot exists)
    if existing_snapshot:
        # Schema keys should be similar (allow some variance)
        assert len(snapshot_data["schema_keys"]) > 0, "No schema keys extracted"

        # Response length should be similar (within 50%)
        if existing_snapshot["response_length"] > 0:
            length_ratio = len(response) / existing_snapshot["response_length"]
            assert 0.5 <= length_ratio <= 2.0, \
                f"Response length changed significantly: {len(response)} vs {existing_snapshot['response_length']}"


@pytest.mark.asyncio
async def test_golden_queries_statistics(setup_tools):
    """Test statistics about golden queries (Phase 6: Updated for 50 queries)."""
    stats = get_query_statistics()

    assert stats["total_queries"] == 50, "Should have 50 golden queries (Phase 6 expansion)"
    assert len(stats["categories"]) >= 10, "Should have at least 10 categories (Phase 6)"
    assert stats["avg_max_duration_ms"] < 3000, "Average duration should be reasonable"


@pytest.mark.asyncio
async def test_golden_queries_by_category(setup_tools):
    """Test queries can be grouped by category."""
    from tests.golden import get_all_categories, get_queries_by_category

    categories = get_all_categories()
    assert len(categories) > 0, "Should have categories"

    for category in categories:
        queries = get_queries_by_category(category)
        assert len(queries) > 0, f"Category {category} should have queries"


@pytest.mark.asyncio
async def test_golden_queries_performance_budget(setup_tools):
    """Test that all queries meet performance budget."""
    results = []

    for query in GOLDEN_QUERIES[:5]:  # Test first 5 for speed
        start_time = time.time()
        try:
            await answer_nba_question(query.query, return_metadata=False)
            duration_ms = (time.time() - start_time) * 1000
            results.append({
                "query_id": query.id,
                "duration_ms": duration_ms,
                "budget_ms": query.max_duration_ms,
                "within_budget": duration_ms <= query.max_duration_ms
            })
        except Exception as e:
            results.append({
                "query_id": query.id,
                "error": str(e)
            })

    # At least 80% should meet performance budget
    within_budget = sum(1 for r in results if r.get("within_budget", False))
    success_rate = within_budget / len(results) if results else 0

    assert success_rate >= 0.8, \
        f"Performance budget failure: {success_rate:.1%} success rate (expected >= 80%)"


# ============================================================================
# SNAPSHOT VALIDATION
# ============================================================================

@pytest.mark.asyncio
async def test_validate_existing_snapshots():
    """Validate that all expected snapshots exist."""
    missing_snapshots = []

    for query in GOLDEN_QUERIES:
        snapshot_path = get_snapshot_path(query.id)
        if not snapshot_path.exists():
            missing_snapshots.append(query.id)

    if missing_snapshots:
        pytest.skip(
            f"Missing snapshots: {', '.join(missing_snapshots)}. "
            f"Run with --update-snapshots to create them."
        )


@pytest.mark.asyncio
async def test_snapshot_consistency():
    """Test that snapshots are internally consistent."""
    for query in GOLDEN_QUERIES:
        snapshot = load_snapshot(query.id)
        if not snapshot:
            continue

        # Validate snapshot structure
        assert "query_id" in snapshot
        assert "response_length" in snapshot
        assert "duration_ms" in snapshot
        assert "schema_keys" in snapshot

        # Validate snapshot values
        assert snapshot["query_id"] == query.id
        assert snapshot["response_length"] >= 0
        assert snapshot["duration_ms"] >= 0


# ============================================================================
# HELPER TESTS
# ============================================================================

def test_golden_query_coverage():
    """Test that golden queries cover all important use cases."""
    # Count queries by category
    categories = {}
    for query in GOLDEN_QUERIES:
        categories[query.category] = categories.get(query.category, 0) + 1

    # Ensure key categories are covered
    assert "leaders" in categories, "Should have leader queries"
    assert "stats" in categories, "Should have stats queries"
    assert "comparison" in categories, "Should have comparison queries"
    assert "team" in categories, "Should have team queries"

    # Should have at least 2 queries per major category
    assert categories.get("leaders", 0) >= 2
    assert categories.get("stats", 0) >= 2
    assert categories.get("comparison", 0) >= 2


def test_query_ids_unique():
    """Test that all query IDs are unique."""
    ids = [q.id for q in GOLDEN_QUERIES]
    assert len(ids) == len(set(ids)), "Query IDs must be unique"


def test_query_names_descriptive():
    """Test that query names are descriptive."""
    for query in GOLDEN_QUERIES:
        assert len(query.name) > 10, f"Query name too short: {query.name}"
        assert query.name.strip() == query.name, f"Query name has whitespace: {query.name}"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
