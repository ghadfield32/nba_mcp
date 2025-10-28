"""
Prometheus metrics for NBA MCP server.
This module provides comprehensive metrics tracking for:
- Request counts and durations per tool
"""

import functools
import logging
import time
from typing import Any, Callable, Dict, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

logger = logging.getLogger(__name__)

# METRIC DEFINITIONS

# Request metrics
REQUEST_COUNT = Counter(
    "nba_mcp_requests_total",
    "Total number of requests by tool",
    ["tool_name", "status"],  # status: success, error, rate_limited
)

REQUEST_DURATION = Histogram(
    "nba_mcp_request_duration_seconds",
    "Request duration in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Error metrics
ERROR_COUNT = Counter(
    "nba_mcp_errors_total",
    "Total number of errors by type",
    ["tool_name", "error_type"],
)

# Cache metrics
CACHE_OPERATIONS = Counter(
    "nba_mcp_cache_operations_total",
    "Total cache operations",
    ["operation", "result"],  # operation: get, set; result: hit, miss, error
)

CACHE_HIT_RATE = Gauge("nba_mcp_cache_hit_rate", "Current cache hit rate (0-1)")

CACHE_SIZE = Gauge("nba_mcp_cache_size_items", "Number of items in cache")

# Rate limiting metrics
RATE_LIMIT_EVENTS = Counter(
    "nba_mcp_rate_limit_events_total",
    "Rate limit events",
    ["tool_name", "event_type"],  # event_type: allowed, blocked
)

QUOTA_USAGE = Gauge(
    "nba_mcp_quota_usage",
    "Current quota usage (0-1)",
    ["quota_type"],  # quota_type: daily, hourly
)

QUOTA_REMAINING = Gauge("nba_mcp_quota_remaining", "Remaining quota", ["quota_type"])

# Token bucket metrics
TOKEN_BUCKET_TOKENS = Gauge(
    "nba_mcp_token_bucket_tokens", "Available tokens in bucket", ["tool_name"]
)

# NLQ Pipeline metrics
NLQ_PIPELINE_STAGE_DURATION = Histogram(
    "nba_mcp_nlq_stage_duration_seconds",
    "NLQ pipeline stage duration",
    ["stage"],  # stage: parse, plan, execute, synthesize
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

NLQ_PIPELINE_TOOL_CALLS = Counter(
    "nba_mcp_nlq_tool_calls_total",
    "Number of tool calls per NLQ query",
    ["query_intent"],  # intent: leaders, comparison, stats, etc.
)

# System info
SERVER_INFO = Info("nba_mcp_server", "NBA MCP server information")

# Uptime
SERVER_START_TIME = Gauge(
    "nba_mcp_server_start_time_seconds", "Server start time in unix timestamp"
)

# METRICS MANAGER

class MetricsManager:
    """
    Centralized metrics management.

    Provides convenience methods for recording metrics and aggregating
    statistics from cache and rate limiter.
    """

    def __init__(self):
        """Initialize metrics manager."""
        self.start_time = time.time()
        SERVER_START_TIME.set(self.start_time)
        logger.info("Metrics manager initialized")

    # ────────────────────────────────────────────────────────────────────
    # Request Metrics
    # ────────────────────────────────────────────────────────────────────

    def record_request(
        self,
        tool_name: str,
        duration: float,
        status: str = "success",
        error_type: Optional[str] = None,
    ):
        """
        Record a request with duration and status.

        Args:
            tool_name: Name of the tool called
            duration: Request duration in seconds
            status: Request status (success, error, rate_limited)
            error_type: Type of error if status is error
        """
        REQUEST_COUNT.labels(tool_name=tool_name, status=status).inc()
        REQUEST_DURATION.labels(tool_name=tool_name).observe(duration)

        if error_type:
            ERROR_COUNT.labels(tool_name=tool_name, error_type=error_type).inc()

    # ────────────────────────────────────────────────────────────────────
    # Cache Metrics
    # ────────────────────────────────────────────────────────────────────

    def record_cache_hit(self):
        """Record a cache hit."""
        CACHE_OPERATIONS.labels(operation="get", result="hit").inc()

    def record_cache_miss(self):
        """Record a cache miss."""
        CACHE_OPERATIONS.labels(operation="get", result="miss").inc()

    def record_cache_set(self, success: bool = True):
        """Record a cache set operation."""
        result = "success" if success else "error"
        CACHE_OPERATIONS.labels(operation="set", result=result).inc()

    def update_cache_stats(self, stats: Dict[str, Any]):
        """
        Update cache metrics from cache statistics.

        Args:
            stats: Cache statistics dict with hits, misses, hit_rate, stored_items
        """
        if "hit_rate" in stats:
            CACHE_HIT_RATE.set(stats["hit_rate"])
        if "stored_items" in stats:
            CACHE_SIZE.set(stats["stored_items"])

    # ────────────────────────────────────────────────────────────────────
    # Rate Limit Metrics
    # ────────────────────────────────────────────────────────────────────

    def record_rate_limit_allowed(self, tool_name: str):
        """Record a rate limit check that was allowed."""
        RATE_LIMIT_EVENTS.labels(tool_name=tool_name, event_type="allowed").inc()

    def record_rate_limit_blocked(self, tool_name: str):
        """Record a rate limit check that was blocked."""
        RATE_LIMIT_EVENTS.labels(tool_name=tool_name, event_type="blocked").inc()

    def update_quota_usage(self, used: int, limit: int, quota_type: str = "daily"):
        """
        Update quota usage metrics.

        Args:
            used: Number of requests used
            limit: Total quota limit
            quota_type: Type of quota (daily, hourly)
        """
        usage_ratio = used / limit if limit > 0 else 0
        QUOTA_USAGE.labels(quota_type=quota_type).set(usage_ratio)
        QUOTA_REMAINING.labels(quota_type=quota_type).set(limit - used)

    def update_token_bucket(self, tool_name: str, tokens: float):
        """
        Update token bucket metrics.

        Args:
            tool_name: Name of the tool
            tokens: Available tokens in bucket
        """
        TOKEN_BUCKET_TOKENS.labels(tool_name=tool_name).set(tokens)

    # ────────────────────────────────────────────────────────────────────
    # NLQ Pipeline Metrics
    # ────────────────────────────────────────────────────────────────────

    def record_nlq_stage(self, stage: str, duration: float):
        """
        Record NLQ pipeline stage duration.

        Args:
            stage: Pipeline stage (parse, plan, execute, synthesize)
            duration: Stage duration in seconds
        """
        NLQ_PIPELINE_STAGE_DURATION.labels(stage=stage).observe(duration)

    def record_nlq_tool_calls(self, query_intent: str, num_calls: int):
        """
        Record number of tool calls for an NLQ query.

        Args:
            query_intent: Intent of the query (leaders, comparison, etc.)
            num_calls: Number of tool calls made
        """
        NLQ_PIPELINE_TOOL_CALLS.labels(query_intent=query_intent).inc(num_calls)

    # ────────────────────────────────────────────────────────────────────
    # Server Info
    # ────────────────────────────────────────────────────────────────────

    def set_server_info(self, version: str, environment: str = "production"):
        """
        Set server information.

        Args:
            version: Server version
            environment: Deployment environment
        """
        SERVER_INFO.info({"version": version, "environment": environment})

    # ────────────────────────────────────────────────────────────────────
    # Export
    # ────────────────────────────────────────────────────────────────────

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus format.

        Returns:
            Metrics in Prometheus text format
        """
        return generate_latest(REGISTRY)

    def get_content_type(self) -> str:
        """
        Get content type for metrics response.

        Returns:
            Content type string
        """
        return CONTENT_TYPE_LATEST

# GLOBAL METRICS MANAGER

_metrics_manager: Optional[MetricsManager] = None

def initialize_metrics() -> MetricsManager:
    """
    Initialize global metrics manager.

    Returns:
        Initialized metrics manager
    """
    global _metrics_manager
    _metrics_manager = MetricsManager()
    return _metrics_manager

def get_metrics_manager() -> MetricsManager:
    """
    Get global metrics manager.

    Returns:
        Global metrics manager instance

    Raises:
        RuntimeError: If metrics not initialized
    """
    if _metrics_manager is None:
        raise RuntimeError("Metrics not initialized. Call initialize_metrics() first.")
    return _metrics_manager

# DECORATORS

def track_metrics(tool_name: Optional[str] = None):
    """
    Decorator to automatically track metrics for a function.

    Tracks request count, duration, and errors.

    Args:
        tool_name: Name of the tool (defaults to function name)

    def decorator(func: Callable) -> Callable:
        actual_tool_name = tool_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            error_type = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                raise
            finally:
                duration = time.time() - start_time
                try:
                    metrics = get_metrics_manager()
                    metrics.record_request(
                        tool_name=actual_tool_name,
                        duration=duration,
                        status=status,
                        error_type=error_type,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record metrics: {e}")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            error_type = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                raise
            finally:
                duration = time.time() - start_time
                try:
                    metrics = get_metrics_manager()
                    metrics.record_request(
                        tool_name=actual_tool_name,
                        duration=duration,
                        status=status,
                        error_type=error_type,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record metrics: {e}")

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# PERIODIC METRICS UPDATE

def update_infrastructure_metrics():
    """
    Update metrics from cache and rate limiter.

    Should be called periodically (e.g., every 10 seconds) to keep
    metrics up to date.
    """
    try:
        metrics = get_metrics_manager()

        # Update cache metrics
        try:
            from nba_mcp.cache.redis_cache import get_cache

            cache = get_cache()
            cache_stats = cache.get_stats()
            metrics.update_cache_stats(cache_stats)
        except Exception as e:
            logger.debug(f"Could not update cache metrics: {e}")

        # Update rate limiter metrics
        try:
            from nba_mcp.rate_limit.token_bucket import get_rate_limiter

            limiter = get_rate_limiter()

            # Update quota
            quota_status = limiter.get_quota_status()
            metrics.update_quota_usage(
                used=quota_status["used"],
                limit=quota_status["limit"],
                quota_type="daily",
            )

            # Update token buckets
            for tool_name in limiter.buckets.keys():
                status = limiter.get_status(tool_name)
                metrics.update_token_bucket(
                    tool_name=tool_name, tokens=status["tokens_available"]
                )
        except Exception as e:
            logger.debug(f"Could not update rate limiter metrics: {e}")

    except Exception as e:
        logger.warning(f"Failed to update infrastructure metrics: {e}")

# HELPER FUNCTIONS

def get_metrics_snapshot() -> Dict[str, Any]:
    """
    Get a snapshot of current metrics for debugging.

    Returns:
        Dictionary with current metric values
    """
    snapshot = {
        "server_uptime_seconds": (
            time.time() - _metrics_manager.start_time if _metrics_manager else 0
        ),
    }

    try:
        from nba_mcp.cache.redis_cache import get_cache

        cache = get_cache()
        snapshot["cache"] = cache.get_stats()
    except:
        pass

    try:
        from nba_mcp.rate_limit.token_bucket import get_rate_limiter

        limiter = get_rate_limiter()
        snapshot["quota"] = limiter.get_quota_status()
    except:
        pass

    return snapshot
