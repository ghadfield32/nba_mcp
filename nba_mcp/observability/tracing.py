"""
OpenTelemetry tracing for NBA MCP server.

This module provides distributed tracing capabilities for:
- NLQ pipeline stages (parse, plan, execute, synthesize)
- Individual tool calls
- Cache operations
- Rate limit checks

Traces can be exported to any OpenTelemetry-compatible backend
(Jaeger, Zipkin, Honeycomb, etc.).
"""

import functools
import time
from typing import Optional, Callable, Any, Dict, List
from contextlib import contextmanager
import logging

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import Status, StatusCode, Span

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None

logger = logging.getLogger(__name__)


# ============================================================================
# TRACER MANAGER
# ============================================================================


class TracingManager:
    """
    Centralized tracing management.

    Provides convenience methods for creating spans and managing trace context.
    """

    def __init__(
        self,
        service_name: str = "nba-mcp",
        otlp_endpoint: Optional[str] = None,
        console_export: bool = False,
    ):
        """
        Initialize tracing manager.

        Args:
            service_name: Name of the service
            otlp_endpoint: OTLP endpoint for exporting traces (e.g., "localhost:4317")
            console_export: Whether to export traces to console (for debugging)
        """
        if not OTEL_AVAILABLE:
            logger.warning(
                "OpenTelemetry not available. Install opentelemetry-api and opentelemetry-sdk."
            )
            self.tracer = None
            return

        # Create resource
        resource = Resource(attributes={SERVICE_NAME: service_name})

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add span processors
        if otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OTLP trace exporter configured: {otlp_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to configure OTLP exporter: {e}")

        if console_export:
            console_exporter = ConsoleSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Console trace exporter configured")

        # Set as global default
        trace.set_tracer_provider(provider)

        # Get tracer
        self.tracer = trace.get_tracer(__name__)
        logger.info(f"Tracing initialized for service: {service_name}")

    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self.tracer is not None

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: Optional[Any] = None,
    ):
        """
        Create a span context manager.

        Args:
            name: Span name
            attributes: Span attributes
            kind: Span kind (INTERNAL, CLIENT, SERVER, PRODUCER, CONSUMER)

        Example:
            with tracer.span("parse_query", attributes={"query": query_text}):
                result = parse(query_text)
        """
        if not self.is_enabled():
            yield None
            return

        with self.tracer.start_as_current_span(name, kind=kind) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))
            yield span

    def record_exception(self, span: Optional[Any], exception: Exception):
        """
        Record an exception in a span.

        Args:
            span: Span to record exception in
            exception: Exception to record
        """
        if span and self.is_enabled():
            span.record_exception(exception)
            span.set_status(Status(StatusCode.ERROR, str(exception)))

    def add_event(
        self,
        span: Optional[Any],
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Add an event to a span.

        Args:
            span: Span to add event to
            name: Event name
            attributes: Event attributes
        """
        if span and self.is_enabled():
            span.add_event(name, attributes=attributes)


# ============================================================================
# GLOBAL TRACING MANAGER
# ============================================================================

_tracing_manager: Optional[TracingManager] = None


def initialize_tracing(
    service_name: str = "nba-mcp",
    otlp_endpoint: Optional[str] = None,
    console_export: bool = False,
) -> TracingManager:
    """
    Initialize global tracing manager.

    Args:
        service_name: Name of the service
        otlp_endpoint: OTLP endpoint (e.g., "localhost:4317")
        console_export: Export to console for debugging

    Returns:
        Initialized tracing manager
    """
    global _tracing_manager
    _tracing_manager = TracingManager(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        console_export=console_export,
    )
    return _tracing_manager


def get_tracing_manager() -> Optional[TracingManager]:
    """
    Get global tracing manager.

    Returns:
        Global tracing manager instance (None if not initialized)
    """
    return _tracing_manager


# ============================================================================
# DECORATORS
# ============================================================================


def trace_function(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    capture_args: bool = False,
):
    """
    Decorator to automatically trace a function.

    Args:
        span_name: Name of the span (defaults to function name)
        attributes: Static attributes to add to span
        capture_args: Whether to capture function arguments as attributes

    Example:
        @trace_function("parse_query", capture_args=True)
        async def parse_query(query: str):
            return parse(query)
    """

    def decorator(func: Callable) -> Callable:
        actual_span_name = span_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracing_manager()
            if not tracer or not tracer.is_enabled():
                return await func(*args, **kwargs)

            span_attributes = dict(attributes or {})
            if capture_args:
                # Capture function arguments
                import inspect

                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                for key, value in bound_args.arguments.items():
                    # Only capture primitive types
                    if isinstance(value, (str, int, float, bool)):
                        span_attributes[f"arg.{key}"] = value

            with tracer.span(actual_span_name, attributes=span_attributes) as span:
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    tracer.record_exception(span, e)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracing_manager()
            if not tracer or not tracer.is_enabled():
                return func(*args, **kwargs)

            span_attributes = dict(attributes or {})
            if capture_args:
                import inspect

                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                for key, value in bound_args.arguments.items():
                    if isinstance(value, (str, int, float, bool)):
                        span_attributes[f"arg.{key}"] = value

            with tracer.span(actual_span_name, attributes=span_attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    tracer.record_exception(span, e)
                    raise

        # Return appropriate wrapper
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# NLQ PIPELINE TRACING HELPERS
# ============================================================================


@contextmanager
def trace_nlq_pipeline(query: str):
    """
    Context manager for tracing an entire NLQ pipeline execution.

    Args:
        query: Natural language query

    Example:
        with trace_nlq_pipeline(query):
            result = await answer_question(query)
    """
    tracer = get_tracing_manager()
    if not tracer or not tracer.is_enabled():
        yield None
        return

    with tracer.span("nlq_pipeline", attributes={"query": query}) as span:
        yield span


@contextmanager
def trace_nlq_stage(stage: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context manager for tracing an NLQ pipeline stage.

    Args:
        stage: Stage name (parse, plan, execute, synthesize)
        attributes: Additional attributes

    Example:
        with trace_nlq_stage("parse"):
            parsed = await parse_query(query)
    """
    tracer = get_tracing_manager()
    if not tracer or not tracer.is_enabled():
        yield None
        return

    span_name = f"nlq.{stage}"
    with tracer.span(span_name, attributes=attributes) as span:
        # Also record metrics
        start_time = time.time()
        try:
            yield span
        finally:
            duration = time.time() - start_time
            try:
                from nba_mcp.observability.metrics import get_metrics_manager

                metrics = get_metrics_manager()
                metrics.record_nlq_stage(stage, duration)
            except:
                pass


@contextmanager
def trace_tool_call(tool_name: str, params: Optional[Dict[str, Any]] = None):
    """
    Context manager for tracing a tool call.

    Args:
        tool_name: Name of the tool being called
        params: Tool parameters

    Example:
        with trace_tool_call("get_player_stats", {"player": "LeBron"}):
            result = await get_player_stats("LeBron")
    """
    tracer = get_tracing_manager()
    if not tracer or not tracer.is_enabled():
        yield None
        return

    attributes = {"tool.name": tool_name}
    if params:
        # Add non-sensitive parameters
        for key, value in params.items():
            if isinstance(value, (str, int, float, bool)):
                attributes[f"tool.param.{key}"] = value

    span_name = f"tool.{tool_name}"
    with tracer.span(span_name, attributes=attributes) as span:
        yield span


@contextmanager
def trace_cache_operation(operation: str, key: Optional[str] = None):
    """
    Context manager for tracing cache operations.

    Args:
        operation: Operation type (get, set, delete)
        key: Cache key

    Example:
        with trace_cache_operation("get", key):
            value = cache.get(key)
    """
    tracer = get_tracing_manager()
    if not tracer or not tracer.is_enabled():
        yield None
        return

    attributes = {"cache.operation": operation}
    if key:
        attributes["cache.key"] = key[:50]  # Truncate long keys

    span_name = f"cache.{operation}"
    with tracer.span(span_name, attributes=attributes) as span:
        yield span


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID.

    Returns:
        Current trace ID or None if not in a trace context
    """
    if not OTEL_AVAILABLE:
        return None

    try:
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            trace_id = span.get_span_context().trace_id
            return format(trace_id, "032x")
    except:
        pass

    return None


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID.

    Returns:
        Current span ID or None if not in a span context
    """
    if not OTEL_AVAILABLE:
        return None

    try:
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_id = span.get_span_context().span_id
            return format(span_id, "016x")
    except:
        pass

    return None


def add_trace_attributes(**attributes):
    """
    Add attributes to the current span.

    Args:
        **attributes: Attributes to add
    """
    if not OTEL_AVAILABLE:
        return

    try:
        span = trace.get_current_span()
        if span:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
    except:
        pass
