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
        query="Who are the top scorers and what are the standings in 2023-24?",  # Use historical season
        intent="multi",
        category="complex",
        tools_expected=["get_league_leaders_info", "get_team_standings"],
        min_response_length=300,
        max_duration_ms=3000
    ),
    GoldenQuery(
        id="complex_002",
        name="LeBron vs Curry with team context",
        query="Compare LeBron and Curry in 2023-24 and show their team standings",  # Use historical season
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

    # ════════════════════════════════════════════════════════════════════
    # PHASE 6: NEW QUERIES (2025-11-01) - Expanding to 50 total
    # ════════════════════════════════════════════════════════════════════

    # ────────────────────────────────────────────────────────────────────
    # RANKINGS QUERIES (Phase 1.1 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="rankings_001",
        name="Where does LeBron rank in scoring",
        query="Where does LeBron James rank in points?",
        intent="rankings",
        category="rankings",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="rankings_002",
        name="Team ranking by offensive rating",
        query="Rank teams by offensive rating",
        intent="rankings",
        category="rankings",
        tools_expected=["get_team_standings"],
        min_response_length=150,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="rankings_003",
        name="Defensive rankings",
        query="Who are the top defenders this season?",
        intent="rankings",
        category="rankings",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="rankings_004",
        name="Three-point leaders ranking",
        query="Rank players by three-pointers made",
        intent="rankings",
        category="rankings",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # STREAKS QUERIES (Phase 2.2 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="streaks_001",
        name="Lakers winning streak",
        query="What is the Lakers current winning streak?",
        intent="streaks",
        category="streaks",
        tools_expected=["get_date_range_game_log_or_team_game_log"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="streaks_002",
        name="LeBron scoring streak",
        query="How many consecutive 30-point games does LeBron have?",
        intent="streaks",
        category="streaks",
        tools_expected=["fetch_player_games"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="streaks_003",
        name="Team losing streak",
        query="Show me the Warriors losing streak",
        intent="streaks",
        category="streaks",
        tools_expected=["get_date_range_game_log_or_team_game_log"],
        min_response_length=80,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # MILESTONES QUERIES (Phase 2.2 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="milestones_001",
        name="Career 30000 points",
        query="Has LeBron scored 30,000 career points?",
        intent="milestones",
        category="milestones",
        tools_expected=["get_player_career_information"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="milestones_002",
        name="Triple double milestone",
        query="How many triple doubles does Westbrook have?",
        intent="milestones",
        category="milestones",
        tools_expected=["fetch_player_games"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="milestones_003",
        name="Career assists record",
        query="Is Chris Paul close to 10,000 assists?",
        intent="milestones",
        category="milestones",
        tools_expected=["get_player_career_information"],
        min_response_length=80,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # AWARDS QUERIES (Phase 2.2 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="awards_001",
        name="MVP this season",
        query="Who won MVP this season?",
        intent="awards",
        category="awards",
        tools_expected=["get_nba_awards"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="awards_002",
        name="LeBron awards",
        query="Show me all of LeBron James awards",
        intent="awards",
        category="awards",
        tools_expected=["get_nba_awards"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="awards_003",
        name="Defensive Player of Year",
        query="Who is the Defensive Player of the Year?",
        intent="awards",
        category="awards",
        tools_expected=["get_nba_awards"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="awards_004",
        name="Rookie of the Year",
        query="Who won Rookie of the Year in 2023-24?",
        intent="awards",
        category="awards",
        tools_expected=["get_nba_awards"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="awards_005",
        name="All-NBA selections",
        query="Show me the All-NBA first team",
        intent="awards",
        category="awards",
        tools_expected=["get_nba_awards"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # FILTERED GAMES QUERIES (Phase 5.1 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="filtered_001",
        name="LeBron 30-point games",
        query="Show me LeBron games with 30+ points",
        intent="filtered_games",
        category="filtered",
        tools_expected=["fetch_player_games"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="filtered_002",
        name="Curry triple double games",
        query="Find games where Stephen Curry had a triple double",
        intent="filtered_games",
        category="filtered",
        tools_expected=["fetch_player_games"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="filtered_003",
        name="Giannis 40-point games",
        query="Giannis games where he scored over 40",
        intent="filtered_games",
        category="filtered",
        tools_expected=["fetch_player_games"],
        min_response_length=80,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="filtered_004",
        name="Jokic 15-assist games",
        query="Show me Nikola Jokic games with 15+ assists",
        intent="filtered_games",
        category="filtered",
        tools_expected=["fetch_player_games"],
        min_response_length=80,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # ALL-TIME LEADERS QUERIES (Phase 5.2 P4 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="alltime_001",
        name="All-time scoring leaders",
        query="Who are the all-time leading scorers?",
        intent="all_time_leaders",
        category="all_time",
        tools_expected=["get_all_time_leaders"],
        min_response_length=100,
        max_duration_ms=2000
    ),
    GoldenQuery(
        id="alltime_002",
        name="Career assists leaders",
        query="All-time assist leaders in NBA history",
        intent="all_time_leaders",
        category="all_time",
        tools_expected=["get_all_time_leaders"],
        min_response_length=100,
        max_duration_ms=2000
    ),
    GoldenQuery(
        id="alltime_003",
        name="Career rebounds leaders",
        query="Who has the most career rebounds?",
        intent="all_time_leaders",
        category="all_time",
        tools_expected=["get_all_time_leaders"],
        min_response_length=100,
        max_duration_ms=2000
    ),

    # ────────────────────────────────────────────────────────────────────
    # LINEUP ANALYSIS QUERIES (Phase 5.2 P6 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="lineup_001",
        name="Lakers best lineup",
        query="What is the Lakers best 5-man lineup?",
        intent="lineup_analysis",
        category="lineup",
        tools_expected=["get_lineup_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="lineup_002",
        name="Warriors starting lineup stats",
        query="Show me the Warriors starting lineup statistics",
        intent="lineup_analysis",
        category="lineup",
        tools_expected=["get_lineup_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="lineup_003",
        name="Celtics lineup with Tatum",
        query="Celtics lineups with Jayson Tatum",
        intent="lineup_analysis",
        category="lineup",
        tools_expected=["get_lineup_stats"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # HIGHLIGHT QUERIES (Phase 2.1 enhancement)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="highlight_001",
        name="Players with 30+ points",
        query="Show me players with 30+ points per game",
        intent="highlight",
        category="highlight",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="highlight_002",
        name="Teams with 10+ wins",
        query="Highlight teams with 10 or more wins",
        intent="highlight",
        category="highlight",
        tools_expected=["get_team_standings"],
        min_response_length=100,
        max_duration_ms=1500
    ),
    GoldenQuery(
        id="highlight_003",
        name="Players shooting over 50%",
        query="Find players shooting over 50% from the field",
        intent="highlight",
        category="highlight",
        tools_expected=["get_league_leaders_info"],
        min_response_length=100,
        max_duration_ms=1500
    ),

    # ────────────────────────────────────────────────────────────────────
    # LLM FALLBACK EDGE CASES (Phase 3 LLM integration)
    # ────────────────────────────────────────────────────────────────────
    GoldenQuery(
        id="llm_001",
        name="Ambiguous query needing LLM",
        query="Who's hot right now?",  # Requires LLM to interpret "hot"
        intent="unknown",  # Will trigger LLM fallback
        category="llm_fallback",
        tools_expected=["get_league_leaders_info"],  # After LLM refinement
        min_response_length=50,
        max_duration_ms=3000  # Longer for LLM call
    ),
    GoldenQuery(
        id="llm_002",
        name="Complex multi-intent query",
        query="Tell me about the best players and their teams",
        intent="unknown",  # Will trigger LLM fallback
        category="llm_fallback",
        tools_expected=["get_league_leaders_info", "get_team_standings"],
        min_response_length=100,
        max_duration_ms=3000
    ),
    GoldenQuery(
        id="llm_003",
        name="Colloquial phrasing",
        query="Who's ballin out lately?",  # Slang requiring LLM
        intent="unknown",  # Will trigger LLM fallback
        category="llm_fallback",
        tools_expected=["get_league_leaders_info"],
        min_response_length=50,
        max_duration_ms=3000
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
