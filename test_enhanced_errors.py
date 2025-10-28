"""
Test script for enhanced error messages.

Demonstrates the improved error messages with actionable suggestions.
"""

import sys

sys.path.insert(0, "/home/user/nba_mcp")

from nba_mcp.api.errors import (
    EntityNotFoundError,
    InvalidParameterError,
    RateLimitError,
    UpstreamSchemaError,
    NBAApiError,
)


def test_entity_not_found_with_suggestions():
    """Test EntityNotFoundError with suggestions."""
    print("=" * 70)
    print("TEST 1: Entity Not Found (WITH Suggestions)")
    print("=" * 70)

    suggestions = [
        {"name": "LeBron James", "confidence": 0.95},
        {"name": "LeBron Raymone James Sr.", "confidence": 0.90},
        {"name": "LeBron James Jr.", "confidence": 0.75},
    ]

    try:
        raise EntityNotFoundError("player", "Lebron James", suggestions=suggestions)
    except EntityNotFoundError as e:
        print(f"\n{e.message}\n")
        print(f"Error Code: {e.code}")
        print(f"How to fix: {e.details.get('how_to_fix')}")


def test_entity_not_found_without_suggestions():
    """Test EntityNotFoundError without suggestions."""
    print("\n" + "=" * 70)
    print("TEST 2: Entity Not Found (WITHOUT Suggestions)")
    print("=" * 70)

    try:
        raise EntityNotFoundError("player", "XYZINVALID123")
    except EntityNotFoundError as e:
        print(f"\n{e.message}\n")


def test_invalid_parameter_season():
    """Test InvalidParameterError for season."""
    print("\n" + "=" * 70)
    print("TEST 3: Invalid Parameter (Season)")
    print("=" * 70)

    try:
        raise InvalidParameterError("season", "2024", "season in YYYY-YY format")
    except InvalidParameterError as e:
        print(f"\n{e.message}\n")


def test_invalid_parameter_with_examples():
    """Test InvalidParameterError with examples."""
    print("\n" + "=" * 70)
    print("TEST 4: Invalid Parameter (With Examples)")
    print("=" * 70)

    try:
        raise InvalidParameterError(
            "stat_category",
            "points",
            "uppercase stat abbreviation",
            examples=["PTS", "REB", "AST", "STL", "BLK"],
        )
    except InvalidParameterError as e:
        print(f"\n{e.message}\n")


def test_rate_limit_error():
    """Test RateLimitError."""
    print("\n" + "=" * 70)
    print("TEST 5: Rate Limit Exceeded")
    print("=" * 70)

    try:
        raise RateLimitError(retry_after=180, daily_quota=10000)
    except RateLimitError as e:
        print(f"\n{e.message}\n")
        print(f"Retry after: {e.retry_after} seconds")


def test_upstream_schema_error():
    """Test UpstreamSchemaError."""
    print("\n" + "=" * 70)
    print("TEST 6: Upstream Schema Changed")
    print("=" * 70)

    try:
        raise UpstreamSchemaError(
            endpoint="playercareerstats",
            missing_fields=["PTS", "REB", "AST", "FG_PCT"],
            unexpected_fields=["NEW_METRIC_1", "NEW_METRIC_2", "NEW_STAT_XYZ"],
        )
    except UpstreamSchemaError as e:
        print(f"\n{e.message}\n")


def test_nba_api_error_rate_limit():
    """Test NBAApiError with rate limit status code."""
    print("\n" + "=" * 70)
    print("TEST 7: NBA API Error (429 Rate Limit)")
    print("=" * 70)

    try:
        raise NBAApiError(
            "Request failed",
            status_code=429,
            endpoint="https://stats.nba.com/stats/playercareerstats",
        )
    except NBAApiError as e:
        print(f"\n{e.message}\n")


def test_nba_api_error_server_down():
    """Test NBAApiError with server error status code."""
    print("\n" + "=" * 70)
    print("TEST 8: NBA API Error (503 Service Unavailable)")
    print("=" * 70)

    try:
        raise NBAApiError(
            "NBA API is down",
            status_code=503,
            endpoint="https://stats.nba.com/stats/leagueleaders",
        )
    except NBAApiError as e:
        print(f"\n{e.message}\n")


def main():
    """Run all error message tests."""
    print("\n" + "=" * 70)
    print("ENHANCED ERROR MESSAGES DEMONSTRATION")
    print("=" * 70)
    print()

    test_entity_not_found_with_suggestions()
    test_entity_not_found_without_suggestions()
    test_invalid_parameter_season()
    test_invalid_parameter_with_examples()
    test_rate_limit_error()
    test_upstream_schema_error()
    test_nba_api_error_rate_limit()
    test_nba_api_error_server_down()

    print("\n" + "=" * 70)
    print("All enhanced error messages demonstrated successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
