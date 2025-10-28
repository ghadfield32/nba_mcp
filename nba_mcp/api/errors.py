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
        # Build helpful error message with suggestions
        base_message = f"{entity_type.capitalize()} '{query}' not found"

        # Add suggestions if available
        if suggestions and len(suggestions) > 0:
            suggestion_text = "\n\nDid you mean?"
            for i, suggestion in enumerate(suggestions[:3], 1):
                name = suggestion.get("name", "Unknown")
                confidence = suggestion.get("confidence", 0.0)
                suggestion_text += f"\n  {i}. {name} (match: {confidence:.0%})"

            # Add usage example
            example_name = suggestions[0].get("name", "")
            suggestion_text += f"\n\nTry: resolve_nba_entity('{example_name}', entity_type='{entity_type}')"

            message = base_message + suggestion_text
        else:
            # No suggestions - provide general help
            if entity_type == "player":
                message = (
                    f"{base_message}\n\n"
                    "Tips:\n"
                    "  - Use full name: 'LeBron James' instead of 'Lebron'\n"
                    "  - Check spelling: 'Stephen Curry' not 'Steven Curry'\n"
                    "  - Try last name only: 'Curry' or 'James'\n"
                    "  - Use partial match: 'Giannis' instead of full Greek name"
                )
            elif entity_type == "team":
                message = (
                    f"{base_message}\n\n"
                    "Tips:\n"
                    "  - Use full name: 'Los Angeles Lakers' or 'Lakers'\n"
                    "  - Use abbreviation: 'LAL', 'GSW', 'BOS'\n"
                    "  - Use city: 'Los Angeles' or 'Golden State'\n"
                    "  - Use nickname: 'Lakers', 'Warriors', 'Celtics'"
                )
            else:
                message = base_message

        super().__init__(
            message=message,
            code=ErrorCode.ENTITY_NOT_FOUND,
            details={
                "entity_type": entity_type,
                "query": query,
                "suggestions": suggestions or [],
                "how_to_fix": (
                    f"Use resolve_nba_entity() to fuzzy-match names, or "
                    f"check spelling and try again with a different query"
                ),
            },
        )


class InvalidParameterError(NBAMCPError):
    """Raised when tool parameters are invalid."""

    def __init__(
        self,
        param_name: str,
        param_value: Any,
        expected: str,
        examples: Optional[list] = None,
    ):
        # Build helpful error message
        base_message = f"Invalid parameter '{param_name}': got '{param_value}', expected {expected}"

        # Add examples if provided
        if examples:
            example_text = "\n\nValid examples:"
            for ex in examples[:3]:
                example_text += f"\n  - {ex}"
            message = base_message + example_text
        else:
            # Provide context-specific help based on parameter name
            if "season" in param_name.lower():
                message = (
                    f"{base_message}\n\n"
                    "Season format: 'YYYY-YY' (e.g., '2023-24', '2024-25')\n"
                    "Tip: Use current_season() helper or omit for current season"
                )
            elif "date" in param_name.lower():
                message = (
                    f"{base_message}\n\n"
                    "Date format: 'YYYY-MM-DD' (e.g., '2024-01-15')\n"
                    "Tip: Use date.today().isoformat() for today's date"
                )
            elif "stat" in param_name.lower() or "category" in param_name.lower():
                message = (
                    f"{base_message}\n\n"
                    "Valid stat categories: PTS, REB, AST, STL, BLK, FG_PCT, FG3_PCT, FT_PCT\n"
                    "Tip: Use uppercase abbreviations"
                )
            else:
                message = base_message

        super().__init__(
            message=message,
            code=ErrorCode.INVALID_PARAMETER,
            details={
                "param_name": param_name,
                "param_value": str(param_value),
                "expected": expected,
                "examples": examples or [],
                "how_to_fix": "Check parameter format and try again with a valid value",
            },
        )


class RateLimitError(NBAMCPError):
    """Raised when NBA API rate limit is exceeded."""

    def __init__(self, retry_after: int = 60, daily_quota: Optional[int] = None):
        # Build helpful error message with guidance
        if retry_after < 60:
            wait_time = f"{retry_after} seconds"
        elif retry_after < 3600:
            wait_time = f"{retry_after // 60} minutes"
        else:
            wait_time = f"{retry_after // 3600} hours"

        message = (
            f"NBA API rate limit exceeded. Please wait {wait_time} before retrying.\n\n"
            "What happened:\n"
            "  - Too many requests sent to NBA API in a short time\n"
            "  - NBA API has temporarily blocked further requests\n\n"
            "How to fix:\n"
            "  1. Wait {wait_time} and try again\n"
            "  2. Reduce request frequency (use caching)\n"
            "  3. Batch multiple queries together\n"
            "  4. Consider using cached data where possible\n\n"
            "Tip: Enable caching with REDIS_URL environment variable to reduce API calls"
        )

        if daily_quota:
            message += f"\n\nDaily quota: {daily_quota} requests/day"

        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            retry_after=retry_after,
            details={
                "quota_exceeded": True,
                "retry_after_seconds": retry_after,
                "retry_after_human": wait_time,
                "daily_quota": daily_quota,
                "how_to_fix": f"Wait {wait_time}, then retry. Enable caching to reduce API calls.",
            },
        )


class UpstreamSchemaError(NBAMCPError):
    """Raised when NBA API response schema changes unexpectedly."""

    def __init__(self, endpoint: str, missing_fields: list, unexpected_fields: list):
        # Build detailed error message
        message = f"NBA API schema changed for endpoint: {endpoint}\n\n"

        if missing_fields:
            message += "Missing fields (previously available):\n"
            for field in missing_fields[:5]:
                message += f"  - {field}\n"
            if len(missing_fields) > 5:
                message += f"  ... and {len(missing_fields) - 5} more\n"
            message += "\n"

        if unexpected_fields:
            message += "New fields (not in schema):\n"
            for field in unexpected_fields[:5]:
                message += f"  + {field}\n"
            if len(unexpected_fields) > 5:
                message += f"  ... and {len(unexpected_fields) - 5} more\n"
            message += "\n"

        message += (
            "What this means:\n"
            "  - NBA has updated their API structure\n"
            "  - Some data may be unavailable or in different format\n"
            "  - This tool needs to be updated to handle new schema\n\n"
            "What to do:\n"
            "  1. Report this issue to NBA MCP maintainers\n"
            "  2. Check for updates: pip install --upgrade nba_mcp\n"
            "  3. Try alternative tools that may still work\n"
            "  4. Enable graceful degradation mode if available\n\n"
            "This is not your fault - NBA changed their API without notice."
        )

        super().__init__(
            message=message,
            code=ErrorCode.UPSTREAM_SCHEMA_CHANGED,
            details={
                "endpoint": endpoint,
                "missing_fields": missing_fields,
                "unexpected_fields": unexpected_fields,
                "how_to_fix": "Update NBA MCP to latest version or report the issue",
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

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
    ):
        # Enhance message with status code context
        enhanced_message = message

        if status_code:
            status_explanations = {
                400: "Bad Request - Invalid parameters sent to NBA API",
                401: "Unauthorized - API key or authentication failed",
                403: "Forbidden - Access denied by NBA API (possible rate limit)",
                404: "Not Found - Endpoint or resource doesn't exist",
                429: "Too Many Requests - Rate limit exceeded",
                500: "Internal Server Error - NBA API is experiencing issues",
                502: "Bad Gateway - NBA API is temporarily unavailable",
                503: "Service Unavailable - NBA API is down for maintenance",
                504: "Gateway Timeout - NBA API took too long to respond",
            }

            explanation = status_explanations.get(status_code, "Unknown error")
            enhanced_message = f"{message}\n\nHTTP {status_code}: {explanation}\n\n"

            # Add specific guidance based on status code
            if status_code in [429, 403]:
                enhanced_message += (
                    "This is likely a rate limiting issue.\n"
                    "Try:\n"
                    "  1. Wait a few minutes before retrying\n"
                    "  2. Enable caching to reduce API calls\n"
                    "  3. Reduce request frequency\n"
                )
            elif status_code in [500, 502, 503, 504]:
                enhanced_message += (
                    "NBA API is experiencing issues (not your fault).\n"
                    "Try:\n"
                    "  1. Wait a few minutes and retry\n"
                    "  2. Check NBA.com/stats to see if site is down\n"
                    "  3. Use cached data if available\n"
                )
            elif status_code == 404:
                enhanced_message += (
                    "The requested resource doesn't exist.\n"
                    "Try:\n"
                    "  1. Check player/team names for typos\n"
                    "  2. Verify the season exists (e.g., '2023-24')\n"
                    "  3. Use resolve_nba_entity() to verify names\n"
                )
            else:
                enhanced_message += (
                    "Try:\n"
                    "  1. Check your parameters are correct\n"
                    "  2. Wait a moment and retry\n"
                    "  3. Report this if it persists\n"
                )

        if endpoint:
            enhanced_message += f"\n\nEndpoint: {endpoint}"

        super().__init__(
            message=enhanced_message,
            code=ErrorCode.NBA_API_ERROR,
            details={
                "status_code": status_code,
                "endpoint": endpoint,
                "how_to_fix": "Check error details above for specific guidance",
            },
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
