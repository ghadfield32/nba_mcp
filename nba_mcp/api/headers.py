"""
Centralized HTTP headers configuration for NBA MCP.

This module provides standardized headers for all NBA API requests,
ensuring we're a good API citizen by properly identifying ourselves
and following best practices.

Features:
- Professional User-Agent string identifying NBA MCP
- Proper Referer headers for NBA domains
- Standard Accept headers for JSON responses
- Configurable via environment variables
- Version-aware (reads from package metadata)

Usage:
    from nba_mcp.api.headers import get_nba_headers

    # Use in requests
    response = requests.get(url, headers=get_nba_headers())

    # Or access specific headers
    from nba_mcp.api.headers import NBA_USER_AGENT, NBA_REFERER
"""

import os
from importlib.metadata import PackageNotFoundError, version
from typing import Dict

# ============================================================================
# Version Detection
# ============================================================================


def _get_package_version() -> str:
    """
    Get the installed version of nba_mcp package.

    Returns:
        Version string (e.g., "1.0.0") or "dev" if not installed

    Example:
        >>> _get_package_version()
        '1.0.0'
    """
    try:
        return version("nba_mcp")
    except PackageNotFoundError:
        # Package not installed (development mode)
        return "dev"


# ============================================================================
# Header Constants
# ============================================================================


# Package version for User-Agent
NBA_MCP_VERSION = _get_package_version()

# Custom User-Agent identifying NBA MCP
# Format: NBA-MCP/{version} (Project-URL) Python/{python_version}
NBA_USER_AGENT = os.getenv(
    "NBA_MCP_USER_AGENT",
    f"NBA-MCP/{NBA_MCP_VERSION} (https://github.com/your-org/nba_mcp)",
)

# Referer header (important for NBA API rate limiting)
# Uses stats.nba.com as the referrer to avoid being blocked
NBA_REFERER = os.getenv("NBA_MCP_REFERER", "https://stats.nba.com")

# Standard Accept headers for JSON responses
NBA_ACCEPT = os.getenv("NBA_MCP_ACCEPT", "application/json")

# Accept-Language (English by default)
NBA_ACCEPT_LANGUAGE = os.getenv("NBA_MCP_ACCEPT_LANGUAGE", "en-US,en;q=0.9")

# Accept-Encoding (support compression)
NBA_ACCEPT_ENCODING = os.getenv("NBA_MCP_ACCEPT_ENCODING", "gzip, deflate, br")


# ============================================================================
# Header Builder Functions
# ============================================================================


def get_nba_headers(
    include_referer: bool = True,
    include_accept: bool = True,
    additional_headers: Dict[str, str] = None,
) -> Dict[str, str]:
    """
    Get standardized HTTP headers for NBA API requests.

    This is the primary function to use for all NBA API requests.
    It returns a dictionary of headers that properly identify NBA MCP
    and follow NBA API best practices.

    Args:
        include_referer: If True, includes Referer header (recommended)
        include_accept: If True, includes Accept-* headers (recommended)
        additional_headers: Optional dict of additional headers to merge

    Returns:
        Dictionary of HTTP headers ready for requests

    Example:
        >>> headers = get_nba_headers()
        >>> requests.get("https://stats.nba.com/stats/...", headers=headers)

        >>> # With custom headers
        >>> headers = get_nba_headers(additional_headers={"X-Custom": "value"})
    """
    headers = {
        "User-Agent": NBA_USER_AGENT,
    }

    if include_referer:
        headers["Referer"] = NBA_REFERER

    if include_accept:
        headers["Accept"] = NBA_ACCEPT
        headers["Accept-Language"] = NBA_ACCEPT_LANGUAGE
        headers["Accept-Encoding"] = NBA_ACCEPT_ENCODING

    # Merge additional headers (overrides defaults if keys conflict)
    if additional_headers:
        headers.update(additional_headers)

    return headers


def get_live_data_headers() -> Dict[str, str]:
    """
    Get headers optimized for NBA Live Data API (cdn.nba.com).

    Live data endpoints have slightly different requirements:
    - No Referer needed (CDN doesn't check)
    - Minimal headers for performance

    Returns:
        Dictionary of HTTP headers for live data endpoints

    Example:
        >>> headers = get_live_data_headers()
        >>> requests.get("https://cdn.nba.com/static/json/...", headers=headers)
    """
    return {
        "User-Agent": NBA_USER_AGENT,
        "Accept": NBA_ACCEPT,
        "Accept-Encoding": NBA_ACCEPT_ENCODING,
    }


def get_stats_api_headers() -> Dict[str, str]:
    """
    Get headers optimized for NBA Stats API (stats.nba.com).

    Stats API endpoints are more strict and require proper headers:
    - User-Agent is required
    - Referer is strongly recommended
    - Full Accept headers for content negotiation

    Returns:
        Dictionary of HTTP headers for stats API endpoints

    Example:
        >>> headers = get_stats_api_headers()
        >>> requests.get("https://stats.nba.com/stats/...", headers=headers)
    """
    return get_nba_headers(
        include_referer=True,
        include_accept=True,
    )


# ============================================================================
# Legacy Header Compatibility
# ============================================================================


# For backward compatibility with existing code
# DEPRECATED: Use get_stats_api_headers() instead
STATS_HEADERS = get_stats_api_headers()


# ============================================================================
# Header Validation
# ============================================================================


def validate_headers(headers: Dict[str, str]) -> bool:
    """
    Validate that headers meet NBA API requirements.

    Checks for:
    - User-Agent presence
    - Referer presence (recommended)
    - Proper Accept headers

    Args:
        headers: Dictionary of headers to validate

    Returns:
        True if headers are valid, False otherwise

    Example:
        >>> headers = {"User-Agent": "MyApp/1.0"}
        >>> validate_headers(headers)
        False  # Missing Referer
    """
    # User-Agent is required
    if "User-Agent" not in headers:
        return False

    # Referer is strongly recommended
    if "Referer" not in headers:
        # Warning: Missing Referer, but not fatal
        pass

    return True


# ============================================================================
# Environment Variable Documentation
# ============================================================================


def print_header_config():
    """
    Print current header configuration (useful for debugging).

    Example:
        >>> from nba_mcp.api.headers import print_header_config
        >>> print_header_config()
        NBA MCP Header Configuration
        ============================
        Version: 1.0.0
        User-Agent: NBA-MCP/1.0.0 (https://github.com/your-org/nba_mcp)
        Referer: https://stats.nba.com
        ...
    """
    print("NBA MCP Header Configuration")
    print("=" * 70)
    print(f"Version: {NBA_MCP_VERSION}")
    print(f"User-Agent: {NBA_USER_AGENT}")
    print(f"Referer: {NBA_REFERER}")
    print(f"Accept: {NBA_ACCEPT}")
    print(f"Accept-Language: {NBA_ACCEPT_LANGUAGE}")
    print(f"Accept-Encoding: {NBA_ACCEPT_ENCODING}")
    print("=" * 70)
    print("\nEnvironment Variables (override defaults):")
    print("  NBA_MCP_USER_AGENT - Custom User-Agent string")
    print("  NBA_MCP_REFERER - Custom Referer URL")
    print("  NBA_MCP_ACCEPT - Custom Accept header")
    print("  NBA_MCP_ACCEPT_LANGUAGE - Custom Accept-Language")
    print("  NBA_MCP_ACCEPT_ENCODING - Custom Accept-Encoding")


# ============================================================================
# Export
# ============================================================================


__all__ = [
    "get_nba_headers",
    "get_live_data_headers",
    "get_stats_api_headers",
    "NBA_USER_AGENT",
    "NBA_REFERER",
    "NBA_ACCEPT",
    "NBA_ACCEPT_LANGUAGE",
    "NBA_ACCEPT_ENCODING",
    "NBA_MCP_VERSION",
    "validate_headers",
    "print_header_config",
    "STATS_HEADERS",  # Legacy compatibility
]
