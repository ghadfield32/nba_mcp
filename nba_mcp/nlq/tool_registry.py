# nba_mcp/nlq/tool_registry.py
"""
Tool Registry for NBA MCP NLQ.

Maps tool names to actual MCP tool functions, allowing the executor
to call real tools instead of mocks.
"""

import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL REGISTRY
# ============================================================================

_TOOL_REGISTRY: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable):
    """
    Register a tool function.

    Args:
        name: Tool name (e.g., "get_league_leaders_info")
        func: Async callable tool function
    """
    _TOOL_REGISTRY[name] = func
    logger.debug(f"Registered tool: {name}")


def get_tool(name: str) -> Optional[Callable]:
    """
    Get a tool function by name.

    Args:
        name: Tool name

    Returns:
        Tool function or None if not found
    """
    return _TOOL_REGISTRY.get(name)


def list_tools() -> list:
    """List all registered tool names."""
    return list(_TOOL_REGISTRY.keys())


def clear_registry():
    """Clear all registered tools."""
    _TOOL_REGISTRY.clear()
    logger.info("Tool registry cleared")


def get_registry_info() -> Dict[str, int]:
    """Get registry statistics."""
    return {"total_tools": len(_TOOL_REGISTRY), "tools": list(_TOOL_REGISTRY.keys())}


# ============================================================================
# BATCH REGISTRATION
# ============================================================================


def register_all_tools(tools: Dict[str, Callable]):
    """
    Register multiple tools at once.

    Args:
        tools: Dictionary mapping tool names to functions
    """
    for name, func in tools.items():
        register_tool(name, func)
    logger.info(f"Registered {len(tools)} tools")


# ============================================================================
# INITIALIZATION
# ============================================================================


def initialize_tool_registry(mcp_tools: Dict[str, Callable]):
    """
    Initialize the tool registry with MCP tools.

    This should be called once when the server starts to wire up
    all the real MCP tool functions.

    Args:
        mcp_tools: Dictionary of {tool_name: tool_function}
    """
    clear_registry()
    register_all_tools(mcp_tools)
    logger.info(f"Tool registry initialized with {len(mcp_tools)} tools")
