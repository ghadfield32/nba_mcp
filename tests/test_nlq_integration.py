"""
Integration tests for NLQ pipeline.

Tests the complete pipeline from natural language query to formatted answer.
"""

import pytest
import asyncio
import sys
sys.path.insert(0, '/home/user/nba_mcp')

from nba_mcp.nlq.parser import parse_query
from nba_mcp.nlq.planner import plan_query_execution
from nba_mcp.nlq.executor import execute_plan
from nba_mcp.nlq.synthesizer import synthesize_response
from nba_mcp.nlq.pipeline import answer_nba_question
from nba_mcp.nlq.mock_tools import register_mock_tools


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module", autouse=True)
def setup_mock_tools():
    """Register mock tools for testing."""
    register_mock_tools()
    yield


# ============================================================================
# PARSER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_parser_leaders_query():
    """Test parsing a leaders query."""
    parsed = await parse_query("Who leads the NBA in assists?")
    assert parsed.intent == "leaders"
    assert "AST" in parsed.stat_types
    assert parsed.confidence > 0.8


@pytest.mark.asyncio
async def test_parser_comparison_query():
    """Test parsing a comparison query."""
    parsed = await parse_query("Compare LeBron James and Kevin Durant")
    assert parsed.intent == "comparison"
    assert len(parsed.entities) == 2
    assert parsed.confidence > 0.8


@pytest.mark.asyncio
async def test_parser_player_stats_query():
    """Test parsing a player stats query."""
    parsed = await parse_query("Show me Giannis stats from 2023-24")
    assert parsed.intent == "player_stats"
    assert len(parsed.entities) == 1
    assert parsed.time_range.season == "2023-24"


# ============================================================================
# PLANNER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_planner_leaders():
    """Test planning a leaders query."""
    parsed = await parse_query("Who leads the NBA in assists?")
    plan = await plan_query_execution(parsed)
    assert plan.template_used == "leaders"
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].tool_name == "get_league_leaders_info"


@pytest.mark.asyncio
async def test_planner_comparison():
    """Test planning a comparison query."""
    parsed = await parse_query("Compare LeBron James and Kevin Durant")
    plan = await plan_query_execution(parsed)
    assert plan.template_used == "comparison_players"
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].tool_name == "compare_players"


# ============================================================================
# EXECUTOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_executor_single_tool():
    """Test executing a single tool."""
    parsed = await parse_query("Who leads the NBA in assists?")
    plan = await plan_query_execution(parsed)
    result = await execute_plan(plan)

    assert result.all_success
    assert len(result.tool_results) == 1
    assert result.total_time_ms > 0


@pytest.mark.asyncio
async def test_executor_parallel_tools():
    """Test executing parallel tools."""
    parsed = await parse_query("Lakers vs Celtics")
    plan = await plan_query_execution(parsed)
    result = await execute_plan(plan)

    assert result.all_success
    assert len(result.tool_results) >= 2  # At least standings + stats
    assert result.total_time_ms > 0


# ============================================================================
# SYNTHESIZER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_synthesizer_leaders():
    """Test synthesizing a leaders response."""
    parsed = await parse_query("Who leads the NBA in assists?")
    plan = await plan_query_execution(parsed)
    result = await execute_plan(plan)
    response = await synthesize_response(parsed, result)

    assert response.intent == "leaders"
    assert len(response.answer) > 0
    assert "AST" in response.answer or "Assists" in response.answer
    assert response.confidence > 0.5


# ============================================================================
# END-TO-END PIPELINE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pipeline_leaders_query():
    """Test complete pipeline for leaders query."""
    answer = await answer_nba_question("Who leads the NBA in assists?")

    assert isinstance(answer, str)
    assert len(answer) > 0
    assert "Player" in answer or "AST" in answer


@pytest.mark.asyncio
async def test_pipeline_comparison_query():
    """Test complete pipeline for comparison query."""
    answer = await answer_nba_question("Compare LeBron James and Kevin Durant")

    assert isinstance(answer, str)
    assert len(answer) > 0
    # Should contain player names
    assert "LeBron" in answer or "Durant" in answer


@pytest.mark.asyncio
async def test_pipeline_player_stats_query():
    """Test complete pipeline for player stats query."""
    answer = await answer_nba_question("Show me Giannis stats from 2023-24")

    assert isinstance(answer, str)
    assert len(answer) > 0
    assert "Giannis" in answer


@pytest.mark.asyncio
async def test_pipeline_standings_query():
    """Test complete pipeline for standings query."""
    answer = await answer_nba_question("Eastern Conference standings")

    assert isinstance(answer, str)
    assert len(answer) > 0
    assert "Team" in answer or "Standing" in answer


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pipeline_handles_invalid_query():
    """Test pipeline handles invalid queries gracefully."""
    answer = await answer_nba_question("asdfghjkl qwertyuiop")

    assert isinstance(answer, str)
    # Should return an error message, not crash
    assert len(answer) > 0


@pytest.mark.asyncio
async def test_pipeline_handles_ambiguous_query():
    """Test pipeline handles ambiguous queries."""
    answer = await answer_nba_question("James")

    # Should either resolve to a player or ask for clarification
    assert isinstance(answer, str)
    assert len(answer) > 0


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pipeline_performance():
    """Test pipeline completes within reasonable time."""
    import time

    start = time.time()
    answer = await answer_nba_question("Who leads the NBA in assists?")
    duration = time.time() - start

    assert duration < 5.0  # Should complete in < 5 seconds with mocks
    assert len(answer) > 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
