"""
Date parsing and normalization utilities for NBA MCP tools.

Handles natural language dates like "yesterday", "today", "tomorrow" and
converts them to YYYY-MM-DD format for API compatibility.

Created: 2024-10-31
Purpose: Improve open-source model compatibility by supporting natural date inputs
"""

import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def parse_relative_date(date_string: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Convert natural language or relative dates to YYYY-MM-DD format.

    Supports:
    - Natural language: "yesterday", "today", "tomorrow"
    - Relative offsets: "-1 day", "+2 days", "last week"
    - Absolute dates: "2024-10-30", "10/30/2024"
    - None/empty: Returns None (uses today's date in API)

    Args:
        date_string: Input date string from user/model

    Returns:
        Tuple of (normalized_date: Optional[str], debug_message: str)
        - normalized_date: YYYY-MM-DD format or None
        - debug_message: Explanation of transformation

    Examples:
        >>> parse_relative_date("yesterday")
        ("2024-10-30", "Parsed 'yesterday' → 2024-10-30")

        >>> parse_relative_date("2024-12-25")
        ("2024-12-25", "Date already in correct format")

        >>> parse_relative_date(None)
        (None, "No date provided, will use today (API default)")
    """
    # Handle None/empty
    if not date_string or not isinstance(date_string, str):
        logger.debug("[date_parser] No date provided, returning None (API will use today)")
        return None, "No date provided, will use today (API default)"

    original_input = date_string
    date_string = date_string.strip().lower()
    today = date.today()

    # Natural language dates
    natural_language_map = {
        "today": today,
        "yesterday": today - timedelta(days=1),
        "tomorrow": today + timedelta(days=1),
        "last week": today - timedelta(weeks=1),
        "next week": today + timedelta(weeks=1),
        "last month": today - timedelta(days=30),
        "next month": today + timedelta(days=30),
    }

    if date_string in natural_language_map:
        result_date = natural_language_map[date_string]
        result_str = result_date.strftime("%Y-%m-%d")
        debug_msg = f"Parsed '{original_input}' → {result_str}"
        logger.info(f"[date_parser] {debug_msg}")
        return result_str, debug_msg

    # Relative offsets: "-1 day", "+2 days", "-3 weeks"
    offset_pattern = r'^([+-]?\d+)\s*(day|days|week|weeks|month|months)$'
    match = re.match(offset_pattern, date_string)
    if match:
        offset_num = int(match.group(1))
        unit = match.group(2)

        if 'day' in unit:
            result_date = today + timedelta(days=offset_num)
        elif 'week' in unit:
            result_date = today + timedelta(weeks=offset_num)
        elif 'month' in unit:
            result_date = today + timedelta(days=offset_num * 30)  # Approximation

        result_str = result_date.strftime("%Y-%m-%d")
        debug_msg = f"Parsed relative offset '{original_input}' → {result_str}"
        logger.info(f"[date_parser] {debug_msg}")
        return result_str, debug_msg

    # Already in YYYY-MM-DD format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_string):
        try:
            # Validate it's a real date
            datetime.strptime(date_string, "%Y-%m-%d")
            debug_msg = f"Date already in correct format: {date_string}"
            logger.debug(f"[date_parser] {debug_msg}")
            return date_string, debug_msg
        except ValueError:
            error_msg = f"Invalid date format: {original_input} (not a valid calendar date)"
            logger.warning(f"[date_parser] {error_msg}")
            return None, error_msg

    # Try parsing MM/DD/YYYY format
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_string):
        try:
            parsed = datetime.strptime(date_string, "%m/%d/%Y")
            result_str = parsed.strftime("%Y-%m-%d")
            debug_msg = f"Converted MM/DD/YYYY '{original_input}' → {result_str}"
            logger.info(f"[date_parser] {debug_msg}")
            return result_str, debug_msg
        except ValueError:
            error_msg = f"Invalid date: {original_input} (not a valid calendar date)"
            logger.warning(f"[date_parser] {error_msg}")
            return None, error_msg

    # Try parsing YYYYMMDD format (no separators)
    if re.match(r'^\d{8}$', date_string):
        try:
            parsed = datetime.strptime(date_string, "%Y%m%d")
            result_str = parsed.strftime("%Y-%m-%d")
            debug_msg = f"Converted YYYYMMDD '{original_input}' → {result_str}"
            logger.info(f"[date_parser] {debug_msg}")
            return result_str, debug_msg
        except ValueError:
            error_msg = f"Invalid date: {original_input} (not a valid calendar date)"
            logger.warning(f"[date_parser] {error_msg}")
            return None, error_msg

    # Unrecognized format
    error_msg = (
        f"Unrecognized date format: '{original_input}'. "
        f"Expected: YYYY-MM-DD, 'yesterday', 'today', 'tomorrow', or relative offsets like '-1 day'"
    )
    logger.warning(f"[date_parser] {error_msg}")
    return None, error_msg


def normalize_parameter_name(params: dict, old_name: str, new_name: str) -> Tuple[dict, Optional[str]]:
    """
    Normalize parameter names for backward compatibility.

    Supports aliasing (e.g., "date" → "target_date") so open-source models
    that use slightly different parameter names still work.

    Args:
        params: Original parameters dict from model
        old_name: Parameter name the model sent (e.g., "date")
        new_name: Parameter name the tool expects (e.g., "target_date")

    Returns:
        Tuple of (normalized_params: dict, debug_message: Optional[str])

    Examples:
        >>> normalize_parameter_name({"date": "yesterday"}, "date", "target_date")
        ({"target_date": "yesterday"}, "Aliased parameter 'date' → 'target_date'")

        >>> normalize_parameter_name({"target_date": "2024-12-25"}, "date", "target_date")
        ({"target_date": "2024-12-25"}, None)  # No change needed
    """
    if old_name in params and new_name not in params:
        params[new_name] = params.pop(old_name)
        debug_msg = f"Aliased parameter '{old_name}' → '{new_name}'"
        logger.info(f"[date_parser] {debug_msg}")
        return params, debug_msg

    return params, None


def parse_and_normalize_date_params(
    params: dict,
    date_param_name: str = "target_date",
    date_param_aliases: list = None
) -> Tuple[dict, list]:
    """
    Complete date parameter normalization pipeline.

    Combines parameter aliasing and date parsing into one function.

    Args:
        params: Raw parameters from model
        date_param_name: Expected parameter name (e.g., "target_date")
        date_param_aliases: List of alternative names (e.g., ["date", "game_date"])

    Returns:
        Tuple of (normalized_params: dict, debug_messages: list[str])

    Example:
        >>> parse_and_normalize_date_params(
        ...     {"date": "yesterday"},
        ...     date_param_name="target_date",
        ...     date_param_aliases=["date"]
        ... )
        (
            {"target_date": "2024-10-30"},
            [
                "Aliased parameter 'date' → 'target_date'",
                "Parsed 'yesterday' → 2024-10-30"
            ]
        )
    """
    if date_param_aliases is None:
        date_param_aliases = ["date", "game_date", "day"]

    debug_messages = []

    # Step 1: Normalize parameter name
    for alias in date_param_aliases:
        params, msg = normalize_parameter_name(params, alias, date_param_name)
        if msg:
            debug_messages.append(msg)
            break

    # Step 2: Parse date value
    if date_param_name in params:
        original_value = params[date_param_name]
        normalized_value, msg = parse_relative_date(original_value)
        params[date_param_name] = normalized_value
        debug_messages.append(msg)

    return params, debug_messages


# ============================================================================
# TESTING UTILITIES (for validation)
# ============================================================================

def validate_date_parser():
    """
    Self-test function to validate date parser behavior.

    Returns:
        bool: True if all tests pass, False otherwise
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    test_cases = [
        ("yesterday", yesterday.strftime("%Y-%m-%d")),
        ("today", today.strftime("%Y-%m-%d")),
        ("tomorrow", tomorrow.strftime("%Y-%m-%d")),
        ("2024-12-25", "2024-12-25"),
        ("-1 day", yesterday.strftime("%Y-%m-%d")),
        ("+1 day", tomorrow.strftime("%Y-%m-%d")),
        (None, None),
        ("", None),
    ]

    all_passed = True
    for input_val, expected in test_cases:
        result, _ = parse_relative_date(input_val)
        if result != expected:
            logger.error(
                f"[date_parser TEST FAILED] Input: {input_val} | "
                f"Expected: {expected} | Got: {result}"
            )
            all_passed = False
        else:
            logger.debug(
                f"[date_parser TEST PASSED] Input: {input_val} → {result}"
            )

    return all_passed


if __name__ == "__main__":
    # Run self-tests when module is executed directly
    logging.basicConfig(level=logging.DEBUG)
    print("Running date_parser validation tests...")
    success = validate_date_parser()
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed. Check logs above.")
