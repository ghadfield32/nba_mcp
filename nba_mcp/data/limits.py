"""
Dataset size limit configuration for NBA MCP.

Provides configurable limits for fetch operations to prevent:
- Excessive memory usage
- Long-running API calls
- Unexpected large downloads

Default limit: 1 GB (1024 MB)
Can be configured via:
1. Environment variable: NBA_MCP_MAX_FETCH_SIZE_MB
2. Runtime: get_limits().set_max_fetch_size_mb(size)
3. MCP tool: configure_limits(max_fetch_mb=size)
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SizeCheckResult:
    """Result of a dataset size limit check."""

    allowed: bool
    estimated_mb: float
    limit_mb: float
    message: str
    warning_message: Optional[str] = None


class FetchLimits:
    """
    Configuration for dataset fetch size limits.

    Controls maximum size of datasets that can be fetched in a single operation.
    Helps prevent excessive memory usage and unexpected large downloads.

    Default: 1024 MB (1 GB)
    Set to -1 for unlimited (not recommended for production)
    """

    def __init__(self):
        """Initialize fetch limits from environment or defaults."""
        # Try to get from environment variable
        env_limit = os.getenv("NBA_MCP_MAX_FETCH_SIZE_MB")

        if env_limit:
            try:
                self._max_fetch_size_mb = float(env_limit)
                logger.info(
                    f"Fetch size limit set from env: {self._max_fetch_size_mb} MB"
                )
            except ValueError:
                logger.warning(
                    f"Invalid NBA_MCP_MAX_FETCH_SIZE_MB value: {env_limit}. "
                    f"Using default: 1024 MB"
                )
                self._max_fetch_size_mb = 1024.0
        else:
            # Default: 1 GB
            self._max_fetch_size_mb = 1024.0
            logger.info(f"Using default fetch size limit: {self._max_fetch_size_mb} MB")

    def get_max_fetch_size_mb(self) -> float:
        """
        Get current maximum fetch size in megabytes.

        Returns:
            Maximum fetch size in MB (-1 for unlimited)
        """
        return self._max_fetch_size_mb

    def set_max_fetch_size_mb(self, size_mb: float):
        """
        Set maximum fetch size in megabytes.

        Args:
            size_mb: Maximum size in MB (-1 for unlimited)

        Example:
            limits = get_limits()
            limits.set_max_fetch_size_mb(2048)  # Set to 2 GB
            limits.set_max_fetch_size_mb(-1)    # Set to unlimited
        """
        if size_mb < -1:
            raise ValueError("Size must be >= 0 or -1 for unlimited")

        old_limit = self._max_fetch_size_mb
        self._max_fetch_size_mb = size_mb

        if size_mb == -1:
            logger.warning("Fetch size limit set to UNLIMITED - use with caution")
        else:
            logger.info(f"Fetch size limit updated: {old_limit} MB → {size_mb} MB")

    def is_unlimited(self) -> bool:
        """
        Check if fetch size is unlimited.

        Returns:
            True if unlimited, False otherwise
        """
        return self._max_fetch_size_mb == -1

    def check_size(
        self, estimated_mb: float, operation: str = "fetch"
    ) -> SizeCheckResult:
        """
        Check if an estimated dataset size is within limits.

        Args:
            estimated_mb: Estimated size in megabytes
            operation: Operation name (for messaging)

        Returns:
            SizeCheckResult with check outcome and messages

        Example:
            result = limits.check_size(1500.0, "fetch")
            if not result.allowed:
                print(result.message)
                print(result.warning_message)
        """
        limit_mb = self._max_fetch_size_mb

        # Unlimited always allowed
        if self.is_unlimited():
            return SizeCheckResult(
                allowed=True,
                estimated_mb=estimated_mb,
                limit_mb=-1,
                message=f"✓ Dataset size {estimated_mb:.2f} MB - unlimited mode",
            )

        # Within limits
        if estimated_mb <= limit_mb:
            return SizeCheckResult(
                allowed=True,
                estimated_mb=estimated_mb,
                limit_mb=limit_mb,
                message=f"✓ Dataset size {estimated_mb:.2f} MB within limit ({limit_mb:.0f} MB)",
            )

        # Exceeds limits - build warning message
        warning_lines = [
            f"⚠ Dataset size exceeds fetch limit",
            f"",
            f"**Estimated Size**: {estimated_mb:.2f} MB",
            f"**Current Limit**: {limit_mb:.0f} MB",
            f"**Overage**: {estimated_mb - limit_mb:.2f} MB ({(estimated_mb / limit_mb - 1) * 100:.1f}% over)",
            f"",
            f"**Options**:",
            f"",
            f"1. **Use chunked fetching** (recommended):",
            f"   ```python",
            f"   fetch_chunked(endpoint, params, strategy='auto')",
            f"   ```",
            f"   This breaks the dataset into smaller chunks for better performance.",
            f"",
            f"2. **Increase the limit** (if you have sufficient memory):",
            f"   ```python",
            f"   configure_limits(max_fetch_mb={int(estimated_mb * 1.2)})",
            f"   ```",
            f"   Or set environment variable: NBA_MCP_MAX_FETCH_SIZE_MB={int(estimated_mb * 1.2)}",
            f"",
            f"3. **Filter the query** to reduce dataset size:",
            f"   - Use narrower date ranges",
            f"   - Filter by specific seasons",
            f"   - Limit to specific teams/players",
        ]

        warning_message = "\n".join(warning_lines)

        return SizeCheckResult(
            allowed=False,
            estimated_mb=estimated_mb,
            limit_mb=limit_mb,
            message=f"Dataset size {estimated_mb:.2f} MB exceeds limit ({limit_mb:.0f} MB)",
            warning_message=warning_message,
        )

    def get_stats(self) -> dict:
        """
        Get current limit configuration statistics.

        Returns:
            Dictionary with limit stats
        """
        limit_mb = self._max_fetch_size_mb

        if self.is_unlimited():
            return {
                "max_fetch_mb": -1,
                "max_fetch_gb": -1,
                "is_unlimited": True,
                "description": "Unlimited (⚠ use with caution)",
            }

        return {
            "max_fetch_mb": limit_mb,
            "max_fetch_gb": round(limit_mb / 1024, 2),
            "is_unlimited": False,
            "description": f"{limit_mb:.0f} MB ({limit_mb / 1024:.2f} GB)",
        }


# Global limits instance (singleton)
_limits = None


def get_limits() -> FetchLimits:
    """
    Get the global fetch limits instance (singleton pattern).

    Returns:
        FetchLimits instance

    Example:
        limits = get_limits()
        result = limits.check_size(1500.0)
        if not result.allowed:
            print(result.warning_message)
    """
    global _limits
    if _limits is None:
        _limits = FetchLimits()
    return _limits


def reset_limits():
    """
    Reset fetch limits to default (1 GB).

    Useful for testing or resetting after configuration changes.
    """
    limits = get_limits()
    limits.set_max_fetch_size_mb(1024.0)
    logger.info("Fetch limits reset to default (1024 MB)")
