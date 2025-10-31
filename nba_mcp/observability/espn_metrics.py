"""
ESPN API reliability monitoring and metrics tracking.

Tracks success rates, response times, and schema drift for ESPN odds API.
Provides visibility into ESPN API reliability for production monitoring.

Created: 2025-10-31
Purpose: Short-term improvement - ESPN API reliability monitoring
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ESPNAPICall:
    """Record of a single ESPN API call."""
    timestamp: datetime
    success: bool
    response_time_ms: float
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    games_fetched: int = 0
    odds_found: int = 0


@dataclass
class ESPNMetrics:
    """Aggregated metrics for ESPN API calls."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    success_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    last_24h_calls: int = 0
    last_24h_success_rate: float = 0.0
    odds_coverage_rate: float = 0.0  # % of games with odds
    recent_errors: List[str] = field(default_factory=list)


class ESPNMetricsTracker:
    """
    Tracks ESPN API reliability metrics over time.

    Maintains a rolling window of recent API calls and computes
    aggregated statistics for monitoring purposes.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize metrics tracker.

        Args:
            max_history: Maximum number of API calls to keep in history
        """
        self.max_history = max_history
        self.call_history: deque = deque(maxlen=max_history)
        self._last_report_time: Optional[datetime] = None

    def record_call(
        self,
        success: bool,
        response_time_ms: float,
        games_fetched: int = 0,
        odds_found: int = 0,
        error_message: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        """
        Record an ESPN API call for metrics tracking.

        Args:
            success: Whether the call succeeded
            response_time_ms: Response time in milliseconds
            games_fetched: Number of games in response
            odds_found: Number of games with odds data
            error_message: Error message if call failed
            status_code: HTTP status code if available
        """
        call = ESPNAPICall(
            timestamp=datetime.now(),
            success=success,
            response_time_ms=response_time_ms,
            error_message=error_message,
            status_code=status_code,
            games_fetched=games_fetched,
            odds_found=odds_found,
        )
        self.call_history.append(call)

        # Log important events
        if not success:
            logger.warning(
                f"[ESPN Metrics] API call failed: {error_message} "
                f"(status: {status_code}, response_time: {response_time_ms}ms)"
            )
        elif response_time_ms > 2000:  # Slow response threshold
            logger.warning(
                f"[ESPN Metrics] Slow API response: {response_time_ms}ms "
                f"(threshold: 2000ms)"
            )

        # Log periodic summary
        if self._should_log_summary():
            self._log_summary()

    def get_metrics(self) -> ESPNMetrics:
        """
        Compute aggregated metrics from call history.

        Returns:
            ESPNMetrics object with all computed statistics
        """
        if not self.call_history:
            return ESPNMetrics()

        # Overall stats
        total = len(self.call_history)
        successful = sum(1 for call in self.call_history if call.success)
        failed = total - successful
        success_rate = (successful / total * 100) if total > 0 else 0.0

        # Response time stats
        response_times = [call.response_time_ms for call in self.call_history]
        avg_response = sum(response_times) / len(response_times)
        min_response = min(response_times)
        max_response = max(response_times)

        # Last 24 hours stats
        cutoff_time = datetime.now() - timedelta(hours=24)
        last_24h_calls = [
            call for call in self.call_history
            if call.timestamp >= cutoff_time
        ]
        last_24h_total = len(last_24h_calls)
        last_24h_successful = sum(1 for call in last_24h_calls if call.success)
        last_24h_success_rate = (
            (last_24h_successful / last_24h_total * 100)
            if last_24h_total > 0 else 0.0
        )

        # Odds coverage rate (% of games with odds)
        total_games = sum(call.games_fetched for call in self.call_history)
        total_odds = sum(call.odds_found for call in self.call_history)
        odds_coverage = (
            (total_odds / total_games * 100)
            if total_games > 0 else 0.0
        )

        # Recent errors (last 5 unique errors)
        recent_errors = []
        seen_errors = set()
        for call in reversed(self.call_history):
            if not call.success and call.error_message:
                if call.error_message not in seen_errors:
                    recent_errors.append(call.error_message)
                    seen_errors.add(call.error_message)
                if len(recent_errors) >= 5:
                    break

        return ESPNMetrics(
            total_calls=total,
            successful_calls=successful,
            failed_calls=failed,
            success_rate=success_rate,
            avg_response_time_ms=avg_response,
            min_response_time_ms=min_response,
            max_response_time_ms=max_response,
            last_24h_calls=last_24h_total,
            last_24h_success_rate=last_24h_success_rate,
            odds_coverage_rate=odds_coverage,
            recent_errors=recent_errors,
        )

    def get_formatted_report(self) -> str:
        """
        Generate a human-readable metrics report.

        Returns:
            Formatted string with all metrics
        """
        metrics = self.get_metrics()

        report = [
            "=" * 60,
            "ESPN API METRICS REPORT",
            "=" * 60,
            "",
            "Overall Statistics:",
            f"  Total API Calls:     {metrics.total_calls}",
            f"  Successful:          {metrics.successful_calls} ({metrics.success_rate:.1f}%)",
            f"  Failed:              {metrics.failed_calls}",
            "",
            "Response Times:",
            f"  Average:             {metrics.avg_response_time_ms:.1f}ms",
            f"  Minimum:             {metrics.min_response_time_ms:.1f}ms",
            f"  Maximum:             {metrics.max_response_time_ms:.1f}ms",
            "",
            "Last 24 Hours:",
            f"  Calls:               {metrics.last_24h_calls}",
            f"  Success Rate:        {metrics.last_24h_success_rate:.1f}%",
            "",
            "Odds Coverage:",
            f"  Games with Odds:     {metrics.odds_coverage_rate:.1f}%",
            "",
        ]

        if metrics.recent_errors:
            report.append("Recent Errors:")
            for i, error in enumerate(metrics.recent_errors, 1):
                report.append(f"  {i}. {error}")
        else:
            report.append("Recent Errors: None")

        report.append("=" * 60)

        return "\n".join(report)

    def _should_log_summary(self) -> bool:
        """
        Determine if summary should be logged (every 100 calls or 1 hour).

        Returns:
            True if summary should be logged
        """
        # Log every 100 calls
        if len(self.call_history) % 100 == 0:
            return True

        # Log every hour
        if self._last_report_time is None:
            self._last_report_time = datetime.now()
            return False

        time_since_last_report = datetime.now() - self._last_report_time
        if time_since_last_report >= timedelta(hours=1):
            self._last_report_time = datetime.now()
            return True

        return False

    def _log_summary(self):
        """Log a summary of metrics to the logger."""
        metrics = self.get_metrics()
        logger.info(
            f"[ESPN Metrics Summary] "
            f"Calls: {metrics.total_calls} | "
            f"Success Rate: {metrics.success_rate:.1f}% | "
            f"Avg Response: {metrics.avg_response_time_ms:.1f}ms | "
            f"Odds Coverage: {metrics.odds_coverage_rate:.1f}%"
        )

    def detect_schema_drift(self, expected_fields: List[str], actual_data: dict) -> List[str]:
        """
        Detect if ESPN API response schema has changed.

        Args:
            expected_fields: List of expected field names
            actual_data: Actual response data from ESPN

        Returns:
            List of drift warnings (empty if no drift detected)
        """
        warnings = []

        # Check for missing expected fields
        for field in expected_fields:
            if field not in actual_data:
                warning = f"Expected field '{field}' missing from ESPN response"
                warnings.append(warning)
                logger.warning(f"[ESPN Schema Drift] {warning}")

        # Check for unexpected new fields (could indicate API changes)
        unexpected_fields = set(actual_data.keys()) - set(expected_fields)
        if unexpected_fields:
            warning = f"Unexpected new fields in ESPN response: {', '.join(unexpected_fields)}"
            warnings.append(warning)
            logger.info(f"[ESPN Schema Drift] {warning}")

        return warnings


# ==================================================================
# GLOBAL TRACKER INSTANCE
# ==================================================================

_global_tracker: Optional[ESPNMetricsTracker] = None


def get_espn_metrics_tracker() -> ESPNMetricsTracker:
    """
    Get the global ESPN metrics tracker instance.

    Returns:
        Global ESPNMetricsTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ESPNMetricsTracker()
    return _global_tracker


# ==================================================================
# DECORATOR FOR AUTOMATIC TRACKING
# ==================================================================

def track_espn_call(func):
    """
    Decorator to automatically track ESPN API calls.

    Usage:
        @track_espn_call
        def _fetch_espn_scoreboard(date_label, timeout):
            ...
    """
    def wrapper(*args, **kwargs):
        tracker = get_espn_metrics_tracker()
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            response_time = (time.time() - start_time) * 1000  # Convert to ms

            # Determine success and extract metrics
            success = result is not None
            games_fetched = 0
            odds_found = 0

            if success and isinstance(result, dict):
                events = result.get("events", [])
                games_fetched = len(events)
                odds_found = sum(
                    1 for event in events
                    if event.get("competitions", [{}])[0].get("odds")
                )

            tracker.record_call(
                success=success,
                response_time_ms=response_time,
                games_fetched=games_fetched,
                odds_found=odds_found,
            )

            return result

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            tracker.record_call(
                success=False,
                response_time_ms=response_time,
                error_message=str(e),
            )
            raise

    return wrapper


if __name__ == "__main__":
    # Test the metrics tracker
    tracker = ESPNMetricsTracker()

    # Simulate some API calls
    tracker.record_call(success=True, response_time_ms=150, games_fetched=10, odds_found=8)
    tracker.record_call(success=True, response_time_ms=200, games_fetched=12, odds_found=12)
    tracker.record_call(success=False, response_time_ms=5000, error_message="Timeout")
    tracker.record_call(success=True, response_time_ms=180, games_fetched=8, odds_found=6)

    # Print report
    print(tracker.get_formatted_report())
