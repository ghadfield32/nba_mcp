# nba_mcp/api/errors.py
"""
Error taxonomy and resilience patterns for NBA MCP.

Provides:
1. Custom exception hierarchy for different failure modes
2. Retry logic with exponential backoff
3. Circuit breaker pattern for failing endpoints
4. Error code constants for consistent error handling
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# ERROR CODES
# ============================================================================


class ErrorCode:
    """Standard error codes for NBA MCP."""

    # Client errors (4xx equivalent)
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
    INVALID_SEASON = "INVALID_SEASON"

    # Server/API errors (5xx equivalent)
    NBA_API_ERROR = "NBA_API_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_SCHEMA_CHANGED = "UPSTREAM_SCHEMA_CHANGED"

    # Infrastructure errors
    CACHE_ERROR = "CACHE_ERROR"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================================
# EXCEPTION HIERARCHY
# ============================================================================


class NBAMCPError(Exception):
    """Base exception for all NBA MCP errors."""

    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retry_after = retry_after
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for ResponseEnvelope."""
        return {
            "code": self.code,
            "message": self.message,
            "retry_after": self.retry_after,
            "details": self.details,
        }


class EntityNotFoundError(NBAMCPError):
    """Raised when player/team/referee/arena cannot be resolved."""

    def __init__(
        self, entity_type: str, query: str, suggestions: Optional[list] = None
    ):
        super().__init__(
            message=f"{entity_type.capitalize()} '{query}' not found",
            code=ErrorCode.ENTITY_NOT_FOUND,
            details={
                "entity_type": entity_type,
                "query": query,
                "suggestions": suggestions or [],
            },
        )


class InvalidParameterError(NBAMCPError):
    """Raised when tool parameters are invalid."""

    def __init__(self, param_name: str, param_value: Any, expected: str):
        super().__init__(
            message=f"Invalid parameter '{param_name}': got {param_value}, expected {expected}",
            code=ErrorCode.INVALID_PARAMETER,
            details={
                "param_name": param_name,
                "param_value": str(param_value),
                "expected": expected,
            },
        )


class RateLimitError(NBAMCPError):
    """Raised when NBA API rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"NBA API rate limit exceeded. Retry after {retry_after} seconds.",
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            retry_after=retry_after,
            details={"quota_exceeded": True},
        )


class UpstreamSchemaError(NBAMCPError):
    """Raised when NBA API response schema changes unexpectedly."""

    def __init__(self, endpoint: str, missing_fields: list, unexpected_fields: list):
        super().__init__(
            message=f"NBA API schema changed for {endpoint}",
            code=ErrorCode.UPSTREAM_SCHEMA_CHANGED,
            details={
                "endpoint": endpoint,
                "missing_fields": missing_fields,
                "unexpected_fields": unexpected_fields,
            },
        )


class CircuitBreakerOpenError(NBAMCPError):
    """Raised when circuit breaker is open (endpoint temporarily disabled)."""

    def __init__(self, endpoint: str, retry_after: int):
        super().__init__(
            message=f"Circuit breaker open for {endpoint}. Endpoint temporarily disabled.",
            code=ErrorCode.CIRCUIT_BREAKER_OPEN,
            retry_after=retry_after,
            details={"endpoint": endpoint},
        )


class NBAApiError(NBAMCPError):
    """Generic NBA API error (network, timeout, unexpected response)."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            code=ErrorCode.NBA_API_ERROR,
            details={"status_code": status_code},
        )


# ============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# ============================================================================


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retry_on: tuple = (NBAApiError, asyncio.TimeoutError),
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff (typically 2.0)
        retry_on: Tuple of exceptions to retry on

    Example:
        @retry_with_backoff(max_retries=3, base_delay=2.0)
        async def fetch_data():
            # Will retry up to 3 times with delays: 2s, 4s, 8s
            pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except retry_on as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries: {e}",
                            exc_info=True,
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base**attempt), max_delay)

                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Retrying in {delay:.1f}s: {e}"
                    )

                    await asyncio.sleep(delay)

                except Exception as e:
                    # Don't retry on non-retryable exceptions
                    logger.error(
                        f"{func.__name__} failed with non-retryable error: {e}",
                        exc_info=True,
                    )
                    raise

            # Should never reach here, but just in case
            raise last_exception

        return wrapper

    return decorator


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================


class CircuitBreaker:
    """
    Circuit breaker pattern for failing endpoints.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Endpoint failing, reject requests immediately
    - HALF_OPEN: Testing if endpoint recovered

    Transitions:
    - CLOSED → OPEN: After failure_threshold consecutive failures
    - OPEN → HALF_OPEN: After timeout_seconds
    - HALF_OPEN → CLOSED: On successful request
    - HALF_OPEN → OPEN: On failed request
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_max_calls: int = 1,
    ):
        """
        Args:
            failure_threshold: Consecutive failures before opening circuit
            timeout_seconds: Seconds to wait before half-open attempt
            half_open_max_calls: Max calls allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0

    def call(self, func: Callable):
        """
        Execute function with circuit breaker protection.

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check circuit state
            if self.state == "OPEN":
                # Check if timeout elapsed
                if (
                    self.last_failure_time
                    and datetime.now() - self.last_failure_time
                    > timedelta(seconds=self.timeout_seconds)
                ):
                    self.state = "HALF_OPEN"
                    self.half_open_calls = 0
                    logger.info(
                        f"Circuit breaker for {func.__name__} entering HALF_OPEN state"
                    )
                else:
                    retry_after = self.timeout_seconds
                    if self.last_failure_time:
                        elapsed = (datetime.now() - self.last_failure_time).seconds
                        retry_after = max(1, self.timeout_seconds - elapsed)

                    raise CircuitBreakerOpenError(
                        endpoint=func.__name__, retry_after=retry_after
                    )

            # HALF_OPEN: Allow limited calls
            if self.state == "HALF_OPEN":
                if self.half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        endpoint=func.__name__, retry_after=self.timeout_seconds
                    )
                self.half_open_calls += 1

            # Execute function
            try:
                result = await func(*args, **kwargs)

                # Success: reset failure count or close circuit
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info(
                        f"Circuit breaker for {func.__name__} closed (recovered)"
                    )
                elif self.state == "CLOSED":
                    self.failure_count = 0

                return result

            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = datetime.now()

                logger.warning(
                    f"Circuit breaker for {func.__name__}: failure {self.failure_count}/{self.failure_threshold}"
                )

                # Open circuit if threshold exceeded
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(
                        f"Circuit breaker for {func.__name__} opened after {self.failure_count} failures"
                    )

                # If in HALF_OPEN, immediately return to OPEN
                elif self.state == "HALF_OPEN":
                    self.state = "OPEN"
                    logger.error(
                        f"Circuit breaker for {func.__name__} reopened (half-open test failed)"
                    )

                raise

        return wrapper


# ============================================================================
# GLOBAL CIRCUIT BREAKERS
# ============================================================================

# Circuit breakers for critical endpoints
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(endpoint_name: str) -> CircuitBreaker:
    """Get or create circuit breaker for endpoint."""
    if endpoint_name not in _circuit_breakers:
        _circuit_breakers[endpoint_name] = CircuitBreaker(
            failure_threshold=5, timeout_seconds=60, half_open_max_calls=1
        )
    return _circuit_breakers[endpoint_name]


# ============================================================================
# UPSTREAM SCHEMA VALIDATION
# ============================================================================


def validate_upstream_schema(
    endpoint: str,
    response_data: Dict[str, Any],
    expected_fields: set,
    allow_extra_fields: bool = True,
) -> None:
    """
    Validate that upstream NBA API response matches expected schema.

    Raises:
        UpstreamSchemaError: If schema has changed unexpectedly

    Args:
        endpoint: Endpoint name for error reporting
        response_data: Response data to validate
        expected_fields: Set of required field names
        allow_extra_fields: If False, raise error on unexpected fields
    """
    actual_fields = set(response_data.keys())
    missing_fields = expected_fields - actual_fields
    unexpected_fields = actual_fields - expected_fields

    if missing_fields or (not allow_extra_fields and unexpected_fields):
        logger.error(
            f"Schema validation failed for {endpoint}: "
            f"missing={missing_fields}, unexpected={unexpected_fields}"
        )
        raise UpstreamSchemaError(
            endpoint=endpoint,
            missing_fields=list(missing_fields),
            unexpected_fields=list(unexpected_fields),
        )
