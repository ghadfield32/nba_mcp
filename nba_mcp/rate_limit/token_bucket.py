# nba_mcp/rate_limit/token_bucket.py
"""
Token bucket rate limiter for NBA MCP.

Provides per-tool and global rate limiting to prevent NBA API quota exhaustion.

Algorithm:
- Each tool has a bucket with capacity N tokens
- Tokens refill at rate R per second
- Each request consumes 1 token
- If no tokens available, request is rate-limited

Example:
    limiter = TokenBucket(capacity=60, refill_rate=1.0)  # 60 req/min
    if limiter.consume():
        # Request allowed
        call_nba_api()
    else:
        # Rate limited
        return 429
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# TOKEN BUCKET
# ============================================================================


@dataclass
class TokenBucket:
    """
    Token bucket rate limiter implementation.

    Thread-safe rate limiter that allows burst traffic while maintaining
    long-term rate limits.
    """

    capacity: float  # Max tokens in bucket
    refill_rate: float  # Tokens added per second
    tokens: float = field(init=False)  # Current tokens
    last_refill: float = field(default_factory=time.time)  # Last refill timestamp
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        """Initialize tokens to full capacity."""
        self.tokens = self.capacity

    def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_refill

        # Calculate tokens to add
        tokens_to_add = elapsed * self.refill_rate

        # Add tokens (up to capacity)
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed (request allowed), False if rate limited
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                logger.debug(f"Consumed {tokens} tokens, {self.tokens:.1f} remaining")
                return True
            else:
                logger.warning(
                    f"Rate limit exceeded: {self.tokens:.1f} tokens, need {tokens}"
                )
                return False

    def get_remaining(self) -> float:
        """Get number of remaining tokens."""
        with self.lock:
            self._refill()
            return self.tokens

    def get_wait_time(self, tokens: int = 1) -> float:
        """
        Get time to wait until tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds to wait (0 if tokens available now)
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                return 0.0

            tokens_needed = tokens - self.tokens
            return tokens_needed / self.refill_rate

    def reset(self):
        """Reset bucket to full capacity."""
        with self.lock:
            self.tokens = self.capacity
            self.last_refill = time.time()
            logger.info("Token bucket reset")


# ============================================================================
# RATE LIMITER (manages multiple buckets)
# ============================================================================


class RateLimiter:
    """
    Rate limiter managing multiple token buckets for different tools.

    Each tool can have its own rate limit. Also supports a global
    daily quota.
    """

    def __init__(self):
        """Initialize rate limiter with no buckets."""
        self.buckets: Dict[str, TokenBucket] = {}
        self.global_quota: Optional[QuotaTracker] = None
        self.lock = threading.Lock()

    def add_limit(self, name: str, capacity: float, refill_rate: float):
        """
        Add rate limit for a tool.

        Args:
            name: Tool name
            capacity: Max tokens (burst capacity)
            refill_rate: Tokens per second

        Example:
            limiter.add_limit("get_player_stats", capacity=60, refill_rate=1.0)
            # 60 requests/minute
        """
        with self.lock:
            self.buckets[name] = TokenBucket(capacity, refill_rate)
            logger.info(
                f"Added rate limit: {name} ({capacity} tokens, {refill_rate}/s)"
            )

    def set_global_quota(self, daily_limit: int, warning_threshold: float = 0.8):
        """
        Set global daily quota.

        Args:
            daily_limit: Max requests per day
            warning_threshold: Emit warning at this percentage (0.0-1.0)
        """
        self.global_quota = QuotaTracker(daily_limit, warning_threshold)
        logger.info(f"Global daily quota set: {daily_limit} requests/day")

    def check_limit(
        self, tool_name: str, tokens: int = 1
    ) -> tuple[bool, Optional[float]]:
        """
        Check if request is allowed.

        Args:
            tool_name: Tool name
            tokens: Tokens to consume

        Returns:
            (allowed, retry_after) tuple
            - allowed: True if request allowed
            - retry_after: Seconds to wait if rate limited (None if allowed)
        """
        # Check global quota first
        if self.global_quota and not self.global_quota.check():
            logger.error("Global daily quota exceeded!")
            return False, 86400  # Retry after 24h

        # Check tool-specific limit
        if tool_name in self.buckets:
            bucket = self.buckets[tool_name]

            if bucket.consume(tokens):
                # Update global quota
                if self.global_quota:
                    self.global_quota.increment()
                return True, None
            else:
                # Rate limited
                wait_time = bucket.get_wait_time(tokens)
                return False, wait_time

        # No limit configured - allow
        if self.global_quota:
            self.global_quota.increment()
        return True, None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with bucket stats and quota info
        """
        stats = {}

        # Per-tool stats
        for name, bucket in self.buckets.items():
            stats[name] = {
                "capacity": bucket.capacity,
                "remaining": bucket.get_remaining(),
                "refill_rate": bucket.refill_rate,
            }

        # Global quota
        if self.global_quota:
            stats["global_quota"] = self.global_quota.get_stats()

        return stats

    def reset_all(self):
        """Reset all rate limits."""
        with self.lock:
            for bucket in self.buckets.values():
                bucket.reset()

            if self.global_quota:
                self.global_quota.reset()

            logger.info("All rate limits reset")


# ============================================================================
# QUOTA TRACKER (daily limits)
# ============================================================================


@dataclass
class QuotaTracker:
    """
    Daily quota tracker.

    Tracks total requests per day and emits warnings when approaching limit.
    """

    daily_limit: int
    warning_threshold: float = 0.8
    count: int = 0
    reset_time: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(days=1)
    )
    lock: threading.Lock = field(default_factory=threading.Lock)
    warning_emitted: bool = False

    def _check_reset(self):
        """Reset counter if day has passed."""
        if datetime.now() >= self.reset_time:
            self.count = 0
            self.reset_time = datetime.now() + timedelta(days=1)
            self.warning_emitted = False
            logger.info(f"Daily quota reset: {self.daily_limit} requests available")

    def check(self) -> bool:
        """
        Check if quota allows request.

        Returns:
            True if under quota, False if quota exceeded
        """
        with self.lock:
            self._check_reset()
            return self.count < self.daily_limit

    def increment(self):
        """Increment request count."""
        with self.lock:
            self._check_reset()
            self.count += 1

            # Emit warning at threshold
            usage = self.count / self.daily_limit
            if usage >= self.warning_threshold and not self.warning_emitted:
                logger.warning(
                    f"Daily quota warning: {self.count}/{self.daily_limit} "
                    f"({usage:.1%}) requests used"
                )
                self.warning_emitted = True

    def get_stats(self) -> Dict[str, Any]:
        """Get quota statistics."""
        with self.lock:
            self._check_reset()
            return {
                "daily_limit": self.daily_limit,
                "count": self.count,
                "remaining": self.daily_limit - self.count,
                "usage_pct": (self.count / self.daily_limit) * 100,
                "reset_time": self.reset_time.isoformat(),
            }

    def reset(self):
        """Manually reset quota."""
        with self.lock:
            self.count = 0
            self.reset_time = datetime.now() + timedelta(days=1)
            self.warning_emitted = False


# ============================================================================
# GLOBAL RATE LIMITER
# ============================================================================

_rate_limiter: Optional[RateLimiter] = None


def initialize_rate_limiter() -> RateLimiter:
    """
    Initialize global rate limiter with default tool limits.

    Returns:
        RateLimiter instance
    """
    global _rate_limiter
    _rate_limiter = RateLimiter()

    # Configure per-tool limits
    # Format: (capacity, refill_rate) = (burst tokens, tokens/second)

    # High-cost tools (live data)
    _rate_limiter.add_limit(
        "get_live_scores", capacity=10, refill_rate=10 / 60
    )  # 10/min

    # Moderate-cost tools
    _rate_limiter.add_limit(
        "get_player_stats", capacity=60, refill_rate=60 / 60
    )  # 60/min
    _rate_limiter.add_limit(
        "get_team_stats", capacity=60, refill_rate=60 / 60
    )  # 60/min
    _rate_limiter.add_limit(
        "get_league_leaders", capacity=60, refill_rate=60 / 60
    )  # 60/min

    # Complex tools (call multiple APIs)
    _rate_limiter.add_limit(
        "compare_players", capacity=30, refill_rate=30 / 60
    )  # 30/min
    _rate_limiter.add_limit(
        "answer_nba_question", capacity=20, refill_rate=20 / 60
    )  # 20/min

    # Phase 3 tools (shot charts, game context)
    _rate_limiter.add_limit(
        "get_shot_chart", capacity=30, refill_rate=30 / 60
    )  # 30/min (single API call)
    _rate_limiter.add_limit(
        "get_game_context", capacity=20, refill_rate=20 / 60
    )  # 20/min (4-6 API calls)

    # Global daily quota (conservative to stay well under NBA API limits)
    _rate_limiter.set_global_quota(daily_limit=10000, warning_threshold=0.8)

    logger.info("Rate limiter initialized with default limits")
    return _rate_limiter


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get global rate limiter instance."""
    return _rate_limiter


# ============================================================================
# RATE LIMIT DECORATOR
# ============================================================================

from functools import wraps
from typing import Callable


def rate_limited(tool_name: str):
    """
    Decorator to enforce rate limits on functions.

    Args:
        tool_name: Tool name for rate limit lookup

    Example:
        @rate_limited("get_player_stats")
        async def get_player_stats(player: str):
            # ... NBA API call
            pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()

            if limiter:
                allowed, retry_after = limiter.check_limit(tool_name)

                if not allowed:
                    logger.warning(
                        f"Rate limit exceeded for {tool_name}, retry after {retry_after}s"
                    )
                    # Raise rate limit error
                    from ..api.errors import RateLimitError

                    raise RateLimitError(
                        retry_after=int(retry_after) if retry_after else 60
                    )

            # Call function
            return await func(*args, **kwargs)

        return wrapper

    return decorator
