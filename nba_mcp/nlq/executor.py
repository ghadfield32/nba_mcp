# nba_mcp/nlq/executor.py
"""
Tool Executor for NBA MCP NLQ.

Executes tool calls with intelligent parallelization, error handling,
and result aggregation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..api.errors import NBAMCPError
from ..api.models import ResponseEnvelope, error_response, success_response
from .planner import ExecutionPlan, ToolCall

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
            "execution_time_ms": self.execution_time_ms,
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
            "all_success": self.all_success,
        }


# ============================================================================
# TOOL REGISTRY IMPORTS
# ============================================================================

from .tool_registry import get_tool, list_tools

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
                execution_time_ms=0.0,
            )

        # Execute tool
        result = await tool_func(**tool_call.params)

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Tool {tool_name} completed in {execution_time_ms:.1f}ms")

        return ToolResult(
            tool_name=tool_name,
            success=True,
            data=result,
            execution_time_ms=execution_time_ms,
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
            execution_time_ms=execution_time_ms,
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
            execution_time_ms=execution_time_ms,
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
            processed_results.append(
                ToolResult(
                    tool_name=tool_calls[i].tool_name,
                    success=False,
                    error=f"Execution exception: {str(result)}",
                    execution_time_ms=0.0,
                )
            )
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
    logger.info(
        f"Executing plan with {len(plan.tool_calls)} tool calls (parallelizable: {plan.can_parallelize})"
    )

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
        logger.info(
            f"Executing parallel group {group_id} with {len(group_tools)} tools"
        )

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

    logger.info(
        f"Plan execution complete: {len(all_results)} results, all_success={all_success}, time={total_time_ms:.1f}ms"
    )

    return ExecutionResult(
        plan=plan,
        tool_results=all_results,
        total_time_ms=total_time_ms,
        all_success=all_success,
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
# MOCK TOOLS (moved to mock_tools.py)
# ============================================================================

# For testing, import from mock_tools:
# from .mock_tools import register_mock_tools
