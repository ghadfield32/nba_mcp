"""
Golden test queries for NBA MCP.

This module defines the top 20 most common NBA queries that should be
regularly tested for schema stability and correctness.

These queries represent the most critical use cases and serve as
regression tests to ensure updates don't break existing functionality.
"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class GoldenQuery:
    """
    A golden query with expected behavior.

    Attributes:
        id: Unique identifier for the query
        name: Human-readable name
        query: Natural language query text
        intent: Expected query intent
        category: Query category (leaders, stats, comparison, etc.)
        tools_expected: List of tools expected to be called
        min_response_length: Minimum expected response length (characters)
        max_duration_ms: Maximum acceptable duration in milliseconds
        schema_keys: Expected keys in structured response
    """
    id: str
    name: str
    query: str
    intent: str
    category: str
    tools_expected: List[str]
    min_response_length: int = 50
    max_duration_ms: int = 2000
    schema_keys: List[str] = None


# ============================================================================
# TOP 20 GOLDEN QUERIES
# ============================================================================

GOLDEN_QUERIES = [
    # ────────────────────────────────────────────────────────────────────
    # LEADERS QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="leaders_001",
        name="Current scoring leader",
        query="Who leads the NBA in points?",
        intent="leaders",
        category="leaders",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="leaders_002",
        name="Assists leader",
        query="Who has the most assists this season?",
        intent="leaders",
        category="leaders",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="leaders_003",
        name="Rebounds leader",
        query="Who is the top rebounder in the NBA?",
        intent="leaders",
        category="leaders",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="leaders_004",
        name="Three-point percentage leader",
        query="Who has the best three-point percentage?",
        intent="leaders",
        category="leaders",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # PLAYER STATS QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="player_stats_001",
        name="LeBron James stats",
        query="Show me LeBron James stats this season",
        intent="player_stats",
        category="stats",
        tools_expected=["get_player_advanced_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="player_stats_002",
        name="Stephen Curry stats",
        query="What are Stephen Curry's stats?",
        intent="player_stats",
        category="stats",
        tools_expected=["get_player_advanced_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="player_stats_003",
        name="Giannis career stats",
        query="Show me Giannis Antetokounmpo career stats",
        intent="player_career",
        category="stats",
        tools_expected=["get_player_career_information"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # PLAYER COMPARISON QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="comparison_001",
        name="LeBron vs Jordan",
        query="Compare LeBron James and Michael Jordan",
        intent="comparison_players",
        category="comparison",
        tools_expected=["compare_players"],
        min_response_length=200,
        max_duration_ms=2000
    ),
    GoldenQuery(
        id="comparison_002",
        name="Curry vs Lillard",
        query="Stephen Curry vs Damian Lillard",
        intent="comparison_players",
        category="comparison",
        tools_expected=["compare_players"],
        min_response_length=200,
        max_duration_ms=2000
    ),
    GoldenQuery(
        id="comparison_003",
        name="Jokic vs Embiid",
        query="Who is better: Nikola Jokic or Joel Embiid?",
        intent="comparison_players",
        category="comparison",
        tools_expected=["compare_players"],
        min_response_length=200,
        max_duration_ms=2000
    ),

    # ────────────────────────────────────────────────────────────────────
    # TEAM QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="team_001",
        name="Conference standings",
        query="Show me the Eastern Conference standings",
        intent="standings",
        category="team",
        tools_expected=["get_team_standings"],
        min_response_length=150,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="team_002",
        name="Lakers stats",
        query="What are the Lakers team stats?",
        intent="team_stats",
        category="team",
        tools_expected=["get_team_advanced_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="team_003",
        name="Warriors vs Celtics",
        query="Compare Warriors and Celtics",
        intent="comparison_teams",
        category="comparison",
        tools_expected=["get_team_advanced_stats"],
        min_response_length=200,
        max_duration_ms=2000
    ),

    # ────────────────────────────────────────────────────────────────────
    # LIVE DATA QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="live_001",
        name="Today's games",
        query="What games are on today?",
        intent="schedule",
        category="live",
        tools_expected=["get_live_scores"],
        min_response_length=50,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="live_002",
        name="Live scores",
        query="Show me live scores",
        intent="live_scores",
        category="live",
        tools_expected=["get_live_scores"],
        min_response_length=50,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # COMPLEX QUERIES (Multi-tool)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="complex_001",
        name="Best players and standings",
        query="Who are the top scorers and what are the standings?",
        intent="multi",
        category="complex",
        tools_expected=["get_league_leaders_info", "get_team_standings"],
        min_response_length=300,
        max_duration_ms=3000
    ),
    GoldenQuery(
        id="complex_002",
        name="LeBron vs Curry with team context",
        query="Compare LeBron and Curry and show their team standings",
        intent="multi",
        category="complex",
        tools_expected=["compare_players", "get_team_standings"],
        min_response_length=300,
        max_duration_ms=3000
    ),

    # ────────────────────────────────────────────────────────────────────
    # HISTORICAL QUERIES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="historical_001",
        name="2020 season leaders",
        query="Who led the NBA in scoring in 2019-20?",
        intent="leaders",
        category="historical",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=2000
    ),
    GoldenQuery(
        id="historical_002",
        name="LeBron 2016 stats",
        query="Show me LeBron's stats from the 2016 season",
        intent="player_stats",
        category="historical",
        tools_expected=["get_player_advanced_stats"],
        min_response_length=100,
        max_duration_ms=2000
    ),

    # ────────────────────────────────────────────────────────────────────
    # EDGE CASES
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="edge_001",
        name="Ambiguous player name",
        query="Show me stats for Jordan",  # Could be Michael or DeAndre
        intent="player_stats",
        category="edge_case",
        tools_expected=["get_player_advanced_stats"],
        min_response_length=50,
        max_duration_ms=1500
    ),
]


def get_query_by_id(query_id: str) -> GoldenQuery:
    """
    Get a golden query by ID.

    Args:
        query_id: Query ID

    Returns:
        GoldenQuery object

    Raises:
        ValueError: If query ID not found
    """
    for query in GOLDEN_QUERIES:
        if query.id == query_id:
            return query
    raise ValueError(f"Query ID not found: {query_id}")


def get_queries_by_category(category: str) -> List[GoldenQuery]:
    """
    Get all queries in a category.

    Args:
        category: Category name

    Returns:
        List of GoldenQuery objects
    """
    return [q for q in GOLDEN_QUERIES if q.category == category]


def get_queries_by_intent(intent: str) -> List[GoldenQuery]:
    """
    Get all queries with a specific intent.

    Args:
        intent: Intent name

    Returns:
        List of GoldenQuery objects
    """
    return [q for q in GOLDEN_QUERIES if q.intent == intent]


def get_all_categories() -> List[str]:
    """
    Get list of all categories.

    Returns:
        List of category names
    """
    return sorted(set(q.category for q in GOLDEN_QUERIES))


def get_all_intents() -> List[str]:
    """
    Get list of all intents.

    Returns:
        List of intent names
    """
    return sorted(set(q.intent for q in GOLDEN_QUERIES))


def get_query_statistics() -> Dict[str, Any]:
    """
    Get statistics about golden queries.

    Returns:
        Dictionary with statistics
    """
    return {
        "total_queries": len(GOLDEN_QUERIES),
        "categories": {cat: len(get_queries_by_category(cat)) for cat in get_all_categories()},
        "intents": {intent: len(get_queries_by_intent(intent)) for intent in get_all_intents()},
        "avg_min_response_length": sum(q.min_response_length for q in GOLDEN_QUERIES) / len(GOLDEN_QUERIES),
        "avg_max_duration_ms": sum(q.max_duration_ms for q in GOLDEN_QUERIES) / len(GOLDEN_QUERIES),
    }
