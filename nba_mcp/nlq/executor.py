# nba_mcp/nlq/executor.py
"""
Tool Executor for NBA MCP NLQ.

Executes tool calls with intelligent parallelization, error handling,
and result aggregation.
"""

from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field
import asyncio
import logging
import time

from .planner import ToolCall, ExecutionPlan
from ..api.models import ResponseEnvelope, success_response, error_response
from ..api.errors import NBAMCPError

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION RESULT
# ============================================================================

@dataclass
class ToolResult:
    """Result from executing a single tool."""

    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms
        }


@dataclass
class ExecutionResult:
    """Aggregated results from executing an execution plan."""

    plan: ExecutionPlan
    tool_results: Dict[str, ToolResult] = field(default_factory=dict)
    total_time_ms: float = 0.0
    all_success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "tool_results": {k: v.to_dict() for k, v in self.tool_results.items()},
            "total_time_ms": self.total_time_ms,
            "all_success": self.all_success
        }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

# Global tool registry - will be populated by NBA MCP server
_TOOL_REGISTRY: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable):
    """Register a tool for execution."""
    _TOOL_REGISTRY[name] = func
    logger.debug(f"Registered tool: {name}")


def get_tool(name: str) -> Optional[Callable]:
    """Get a tool by name."""
    return _TOOL_REGISTRY.get(name)


def list_tools() -> List[str]:
    """List all registered tools."""
    return list(_TOOL_REGISTRY.keys())


# ============================================================================
# TOOL EXECUTION
# ============================================================================

async def execute_tool(tool_call: ToolCall) -> ToolResult:
    """
    Execute a single tool call.

    Args:
        tool_call: Tool call specification

    Returns:
        ToolResult with data or error
    """
    start_time = time.time()
    tool_name = tool_call.tool_name

    logger.info(f"Executing tool: {tool_name} with params {tool_call.params}")

    try:
        # Get tool function
        tool_func = get_tool(tool_name)

        if not tool_func:
            error_msg = f"Tool '{tool_name}' not found in registry"
            logger.error(error_msg)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=error_msg,
                execution_time_ms=0.0
            )

        # Execute tool
        result = await tool_func(**tool_call.params)

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Tool {tool_name} completed in {execution_time_ms:.1f}ms")

        return ToolResult(
            tool_name=tool_name,
            success=True,
            data=result,
            execution_time_ms=execution_time_ms
        )

    except NBAMCPError as e:
        # Known NBA MCP error
        execution_time_ms = (time.time() - start_time) * 1000
        error_msg = f"{e.code}: {e.message}"
        logger.error(f"Tool {tool_name} failed: {error_msg}")

        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=error_msg,
            execution_time_ms=execution_time_ms
        )

    except Exception as e:
        # Unexpected error
        execution_time_ms = (time.time() - start_time) * 1000
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        logger.exception(f"Tool {tool_name} failed with unexpected error")

        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=error_msg,
            execution_time_ms=execution_time_ms
        )


# ============================================================================
# PARALLEL EXECUTION
# ============================================================================

async def execute_parallel_group(tool_calls: List[ToolCall]) -> List[ToolResult]:
    """
    Execute a group of tool calls in parallel.

    Args:
        tool_calls: List of tool calls to execute in parallel

    Returns:
        List of tool results
    """
    logger.info(f"Executing {len(tool_calls)} tools in parallel")

    # Execute all tools concurrently
    tasks = [execute_tool(tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that occurred
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Tool {tool_calls[i].tool_name} raised exception: {result}")
            processed_results.append(ToolResult(
                tool_name=tool_calls[i].tool_name,
                success=False,
                error=f"Execution exception: {str(result)}",
                execution_time_ms=0.0
            ))
        else:
            processed_results.append(result)

    return processed_results


# ============================================================================
# EXECUTION ORCHESTRATION
# ============================================================================

async def execute_plan(plan: ExecutionPlan) -> ExecutionResult:
    """
    Execute an execution plan with optimal parallelization.

    Strategy:
    1. Group tool calls by parallel_group
    2. Execute groups in order (group 0, then group 1, etc.)
    3. Within each group, execute tools in parallel
    4. Aggregate results

    Args:
        plan: Execution plan

    Returns:
        ExecutionResult with all tool results
    """
    start_time = time.time()
    logger.info(f"Executing plan with {len(plan.tool_calls)} tool calls (parallelizable: {plan.can_parallelize})")

    # Group tool calls by parallel_group
    groups: Dict[int, List[ToolCall]] = {}
    for tc in plan.tool_calls:
        group_id = tc.parallel_group
        if group_id not in groups:
            groups[group_id] = []
        groups[group_id].append(tc)

    # Execute groups in order
    all_results = {}
    tool_call_index = 0
    for group_id in sorted(groups.keys()):
        group_tools = groups[group_id]
        logger.info(f"Executing parallel group {group_id} with {len(group_tools)} tools")

        # Execute group in parallel
        group_results = await execute_parallel_group(group_tools)

        # Store results with unique keys (tool_name + index for duplicates)
        for result in group_results:
            # Create unique key for duplicate tool names
            key = result.tool_name
            if key in all_results:
                # Add suffix for duplicate
                suffix = 2
                while f"{key}_{suffix}" in all_results:
                    suffix += 1
                key = f"{key}_{suffix}"
            all_results[key] = result
            tool_call_index += 1

    # Calculate total time
    total_time_ms = (time.time() - start_time) * 1000

    # Check if all succeeded
    all_success = all(r.success for r in all_results.values())

    logger.info(f"Plan execution complete: {len(all_results)} results, all_success={all_success}, time={total_time_ms:.1f}ms")

    return ExecutionResult(
        plan=plan,
        tool_results=all_results,
        total_time_ms=total_time_ms,
        all_success=all_success
    )


# ============================================================================
# ERROR HANDLING & PARTIAL RESULTS
# ============================================================================

def extract_successful_results(execution_result: ExecutionResult) -> Dict[str, Any]:
    """
    Extract only successful tool results.

    Args:
        execution_result: Execution result

    Returns:
        Dictionary of successful results
    """
    return {
        name: result.data
        for name, result in execution_result.tool_results.items()
        if result.success
    }


def get_failure_summary(execution_result: ExecutionResult) -> List[str]:
    """
    Get summary of failed tools.

    Args:
        execution_result: Execution result

    Returns:
        List of error messages
    """
    failures = []
    for name, result in execution_result.tool_results.items():
        if not result.success:
            failures.append(f"{name}: {result.error}")
    return failures


# ============================================================================
# MOCK TOOLS FOR TESTING
# ============================================================================

async def mock_get_league_leaders_info(
    stat_category: str,
    season: Optional[str] = None,
    per_mode: str = "PerGame",
    season_type_all_star: str = "Regular Season"
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)  # Simulate API call
    return {
        "stat_category": stat_category,
        "season": season,
        "leaders": [
            {"player": "Player 1", "value": 10.5},
            {"player": "Player 2", "value": 9.8}
        ]
    }


async def mock_compare_players(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
    normalization: str = "per_75"
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {
        "player1": {"name": player1_name, "ppg": 25.5},
        "player2": {"name": player2_name, "ppg": 27.3}
    }


async def mock_get_team_standings(
    season: Optional[str] = None,
    conference: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return [
        {"team": "Team 1", "wins": 40, "losses": 20},
        {"team": "Team 2", "wins": 35, "losses": 25}
    ]


async def mock_get_team_advanced_stats(
    team_name: str,
    season: Optional[str] = None
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {
        "team_name": team_name,
        "offensive_rating": 115.5,
        "defensive_rating": 108.2
    }


async def mock_get_player_advanced_stats(
    player_name: str,
    season: Optional[str] = None
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {
        "player_name": player_name,
        "true_shooting_pct": 0.625,
        "usage_pct": 28.5
    }


# Register mock tools for testing
def register_mock_tools():
    """Register all mock tools."""
    register_tool("get_league_leaders_info", mock_get_league_leaders_info)
    register_tool("compare_players", mock_compare_players)
    register_tool("get_team_standings", mock_get_team_standings)
    register_tool("get_team_advanced_stats", mock_get_team_advanced_stats)
    register_tool("get_player_advanced_stats", mock_get_player_advanced_stats)
    logger.info("Registered mock tools for testing")
