"""
Observability module for NBA MCP server.

Provides metrics, tracing, and monitoring capabilities.
"""

from nba_mcp.observability.metrics import (
    MetricsManager,
    initialize_metrics,
    get_metrics_manager,
    track_metrics,
    update_infrastructure_metrics,
    get_metrics_snapshot,
    # Prometheus metrics
    REQUEST_COUNT,
    REQUEST_DURATION,
    ERROR_COUNT,
    CACHE_OPERATIONS,
    CACHE_HIT_RATE,
    CACHE_SIZE,
    RATE_LIMIT_EVENTS,
    QUOTA_USAGE,
    QUOTA_REMAINING,
    TOKEN_BUCKET_TOKENS,
    NLQ_PIPELINE_STAGE_DURATION,
    NLQ_PIPELINE_TOOL_CALLS,
    SERVER_INFO,
    SERVER_START_TIME,
)

from nba_mcp.observability.tracing import (
    TracingManager,
    initialize_tracing,
    get_tracing_manager,
    trace_function,
    trace_nlq_pipeline,
    trace_nlq_stage,
    trace_tool_call,
    trace_cache_operation,
    get_current_trace_id,
    get_current_span_id,
    add_trace_attributes,
)

__all__ = [
    # Metrics Manager
    "MetricsManager",
    "initialize_metrics",
    "get_metrics_manager",
    "track_metrics",
    "update_infrastructure_metrics",
    "get_metrics_snapshot",
    # Metrics
    "REQUEST_COUNT",
    "REQUEST_DURATION",
    "ERROR_COUNT",
    "CACHE_OPERATIONS",
    "CACHE_HIT_RATE",
    "CACHE_SIZE",
    "RATE_LIMIT_EVENTS",
    "QUOTA_USAGE",
    "QUOTA_REMAINING",
    "TOKEN_BUCKET_TOKENS",
    "NLQ_PIPELINE_STAGE_DURATION",
    "NLQ_PIPELINE_TOOL_CALLS",
    "SERVER_INFO",
    "SERVER_START_TIME",
    # Tracing Manager
    "TracingManager",
    "initialize_tracing",
    "get_tracing_manager",
    "trace_function",
    "trace_nlq_pipeline",
    "trace_nlq_stage",
    "trace_tool_call",
    "trace_cache_operation",
    "get_current_trace_id",
    "get_current_span_id",
    "add_trace_attributes",
]
