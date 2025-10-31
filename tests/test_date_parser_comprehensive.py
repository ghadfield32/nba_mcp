"""
Comprehensive test suite for date_parser module.

Tests all date parsing scenarios including natural language dates,
relative offsets, parameter aliasing, and edge cases.

Created: 2025-10-31
Purpose: Short-term improvement - expanded test coverage
"""

import pytest
from datetime import date, timedelta
from nba_mcp.api.tools.date_parser import (
    parse_relative_date,
    normalize_parameter_name,
    parse_and_normalize_date_params,
)


class TestParseRelativeDate:
    """Test suite for parse_relative_date function."""

    def test_natural_language_yesterday(self):
        """Test 'yesterday' parses to correct date."""
        expected = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        result, msg = parse_relative_date("yesterday")
        assert result == expected
        assert "Parsed 'yesterday'" in msg

    def test_natural_language_today(self):
        """Test 'today' parses to correct date."""
        expected = date.today().strftime("%Y-%m-%d")
        result, msg = parse_relative_date("today")
        assert result == expected
        assert "Parsed 'today'" in msg

    def test_natural_language_tomorrow(self):
        """Test 'tomorrow' parses to correct date."""
        expected = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        result, msg = parse_relative_date("tomorrow")
        assert result == expected
        assert "Parsed 'tomorrow'" in msg

    def test_relative_offset_minus_one_day(self):
        """Test '-1 day' parses correctly."""
        expected = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        result, msg = parse_relative_date("-1 day")
        assert result == expected
        assert "relative offset" in msg.lower()

    def test_relative_offset_plus_two_days(self):
        """Test '+2 days' parses correctly."""
        expected = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")
        result, msg = parse_relative_date("+2 days")
        assert result == expected

    def test_relative_offset_weeks(self):
        """Test 'last week' and week offsets."""
        expected_last_week = (date.today() - timedelta(weeks=1)).strftime("%Y-%m-%d")
        result, _ = parse_relative_date("last week")
        assert result == expected_last_week

        expected_minus_2_weeks = (date.today() - timedelta(weeks=2)).strftime("%Y-%m-%d")
        result, _ = parse_relative_date("-2 weeks")
        assert result == expected_minus_2_weeks

    def test_already_correct_format(self):
        """Test date already in YYYY-MM-DD format."""
        result, msg = parse_relative_date("2024-12-25")
        assert result == "2024-12-25"
        assert "already in correct format" in msg.lower()

    def test_mmddyyyy_format_conversion(self):
        """Test MM/DD/YYYY format conversion."""
        result, msg = parse_relative_date("12/25/2024")
        assert result == "2024-12-25"
        assert "Converted MM/DD/YYYY" in msg

    def test_yyyymmdd_format_conversion(self):
        """Test YYYYMMDD (no separators) format conversion."""
        result, msg = parse_relative_date("20241225")
        assert result == "2024-12-25"
        assert "Converted YYYYMMDD" in msg

    def test_none_input(self):
        """Test None input returns None."""
        result, msg = parse_relative_date(None)
        assert result is None
        assert "No date provided" in msg

    def test_empty_string(self):
        """Test empty string returns None."""
        result, msg = parse_relative_date("")
        assert result is None
        assert "No date provided" in msg

    def test_invalid_date_format(self):
        """Test invalid date format returns None with error."""
        result, msg = parse_relative_date("invalid-date-123")
        assert result is None
        assert "Unrecognized date format" in msg

    def test_invalid_calendar_date(self):
        """Test invalid calendar date (e.g., Feb 30) returns None."""
        result, msg = parse_relative_date("2024-02-30")
        assert result is None
        assert "Invalid date format" in msg

    def test_case_insensitive(self):
        """Test natural language parsing is case-insensitive."""
        result1, _ = parse_relative_date("YESTERDAY")
        result2, _ = parse_relative_date("yesterday")
        result3, _ = parse_relative_date("YeStErDaY")
        assert result1 == result2 == result3


class TestNormalizeParameterName:
    """Test suite for parameter name normalization."""

    def test_alias_applied(self):
        """Test parameter aliasing works."""
        params = {"date": "2024-12-25"}
        result, msg = normalize_parameter_name(params, "date", "target_date")
        assert "target_date" in result
        assert "date" not in result
        assert result["target_date"] == "2024-12-25"
        assert msg is not None

    def test_no_alias_needed(self):
        """Test no aliasing when parameter already correct."""
        params = {"target_date": "2024-12-25"}
        result, msg = normalize_parameter_name(params, "date", "target_date")
        assert result == params
        assert msg is None

    def test_alias_preserves_other_params(self):
        """Test aliasing doesn't affect other parameters."""
        params = {"date": "2024-12-25", "other_param": "value"}
        result, _ = normalize_parameter_name(params, "date", "target_date")
        assert result["target_date"] == "2024-12-25"
        assert result["other_param"] == "value"


class TestParseAndNormalizeDateParams:
    """Test suite for complete parameter normalization pipeline."""

    def test_full_pipeline_with_alias_and_parsing(self):
        """Test complete pipeline with parameter alias and date parsing."""
        params = {"date": "yesterday"}
        result, messages = parse_and_normalize_date_params(params)

        assert "target_date" in result
        assert result["target_date"] == (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert len(messages) == 2  # Alias message + parse message
        assert any("Aliased" in msg for msg in messages)
        assert any("Parsed" in msg for msg in messages)

    def test_pipeline_with_correct_param_name(self):
        """Test pipeline when parameter name is already correct."""
        params = {"target_date": "yesterday"}
        result, messages = parse_and_normalize_date_params(params)

        assert "target_date" in result
        assert result["target_date"] == (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        # Should have parse message but not alias message
        assert len(messages) >= 1
        assert any("Parsed" in msg for msg in messages)

    def test_pipeline_with_no_date_param(self):
        """Test pipeline when no date parameter provided."""
        params = {"other_param": "value"}
        result, messages = parse_and_normalize_date_params(params)

        assert "target_date" not in result
        assert result["other_param"] == "value"

    def test_pipeline_with_multiple_aliases(self):
        """Test pipeline tries multiple aliases."""
        # Test with "game_date" alias
        params1 = {"game_date": "today"}
        result1, _ = parse_and_normalize_date_params(params1)
        assert "target_date" in result1

        # Test with "day" alias
        params2 = {"day": "tomorrow"}
        result2, _ = parse_and_normalize_date_params(params2)
        assert "target_date" in result2

    def test_pipeline_preserves_other_params(self):
        """Test pipeline doesn't affect unrelated parameters."""
        params = {"date": "yesterday", "team": "Lakers", "season": "2024-25"}
        result, _ = parse_and_normalize_date_params(params)

        assert result["team"] == "Lakers"
        assert result["season"] == "2024-25"
        assert "target_date" in result


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_non_string_input(self):
        """Test non-string input to parse_relative_date."""
        result, _ = parse_relative_date(12345)
        assert result is None

    def test_whitespace_handling(self):
        """Test whitespace is properly stripped."""
        result1, _ = parse_relative_date("  yesterday  ")
        result2, _ = parse_relative_date("yesterday")
        assert result1 == result2

    def test_future_dates(self):
        """Test parsing future dates."""
        result, _ = parse_relative_date("tomorrow")
        assert result is not None

        result, _ = parse_relative_date("+7 days")
        assert result is not None

    def test_past_dates(self):
        """Test parsing past dates."""
        result, _ = parse_relative_date("last week")
        assert result is not None

        result, _ = parse_relative_date("-30 days")
        assert result is not None


# ==================================================================
# INTEGRATION TESTS (require full module context)
# ==================================================================

@pytest.mark.integration
class TestIntegrationWithGetLiveScores:
    """Integration tests simulating actual get_live_scores usage."""

    def test_model_sends_date_yesterday(self):
        """Simulate open-source model sending {"date": "yesterday"}."""
        params = {"date": "yesterday"}
        result, _ = parse_and_normalize_date_params(params)

        # Should now work - parameter normalized
        assert "target_date" in result
        assert result["target_date"] == (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    def test_model_sends_game_date_today(self):
        """Simulate model sending {"game_date": "today"}."""
        params = {"game_date": "today"}
        result, _ = parse_and_normalize_date_params(params)

        assert "target_date" in result
        assert result["target_date"] == date.today().strftime("%Y-%m-%d")

    def test_model_sends_correct_format(self):
        """Simulate model sending correct parameter and format."""
        params = {"target_date": "2024-12-25"}
        result, _ = parse_and_normalize_date_params(params)

        assert result["target_date"] == "2024-12-25"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
