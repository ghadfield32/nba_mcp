"""
Unit tests for date handling across the NBA MCP server.

Tests verify that:
1. Live scores uses NBA API for date (not system clock)
2. Advanced stats uses NBA API for season determination
3. Date handling is consistent across all tools
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import functions to test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from nba_mcp.api.advanced_stats import get_current_season_from_nba_api


class TestGetLiveScoresDateHandling:
    """Test get_live_scores uses NBA API for date instead of system clock."""

    @patch('nba_mcp.nba_server.ScoreBoard')
    @patch('nba_mcp.nba_server.NBAApiClient')
    async def test_get_live_scores_fetches_date_from_nba_api(self, mock_client_class, mock_scoreboard_class):
        """
        Test that get_live_scores fetches date from NBA API when no target_date provided.
        """
        from nba_mcp.nba_server import get_live_scores

        # Mock ScoreBoard to return a specific date
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "2025-01-28"
        mock_scoreboard_class.return_value = mock_sb_instance

        # Mock NBAApiClient
        mock_client_instance = Mock()
        mock_client_instance.get_live_scoreboard = Mock(return_value=[])
        mock_client_class.return_value = mock_client_instance

        # Call get_live_scores without target_date
        result = await get_live_scores(target_date=None)

        # Verify ScoreBoard was called
        mock_scoreboard_class.assert_called_once_with(get_request=True)

        # Verify client.get_live_scoreboard was called with NBA API date
        mock_client_instance.get_live_scoreboard.assert_called_once()
        call_args = mock_client_instance.get_live_scoreboard.call_args
        assert call_args[1]['target_date'] == "2025-01-28"

    @patch('nba_mcp.nba_server.ScoreBoard')
    @patch('nba_mcp.nba_server.NBAApiClient')
    async def test_get_live_scores_uses_provided_date(self, mock_client_class, mock_scoreboard_class):
        """
        Test that get_live_scores uses provided target_date without calling NBA API.
        """
        from nba_mcp.nba_server import get_live_scores

        # Mock NBAApiClient
        mock_client_instance = Mock()
        mock_client_instance.get_live_scoreboard = Mock(return_value=[])
        mock_client_class.return_value = mock_client_instance

        # Call get_live_scores WITH explicit target_date
        result = await get_live_scores(target_date="2024-12-25")

        # Verify ScoreBoard was NOT called (no need to fetch date)
        mock_scoreboard_class.assert_not_called()

        # Verify client.get_live_scoreboard was called with provided date
        mock_client_instance.get_live_scoreboard.assert_called_once()
        call_args = mock_client_instance.get_live_scoreboard.call_args
        assert call_args[1]['target_date'] == "2024-12-25"

    @patch('nba_mcp.nba_server.ScoreBoard')
    async def test_get_live_scores_raises_on_nba_api_failure(self, mock_scoreboard_class):
        """
        Test that get_live_scores raises exception when NBA API fails.
        (No fallback to system clock)
        """
        from nba_mcp.nba_server import get_live_scores

        # Mock ScoreBoard to raise an exception
        mock_scoreboard_class.side_effect = Exception("NBA API unavailable")

        # Call should raise the exception (no fallback)
        with pytest.raises(Exception) as exc_info:
            await get_live_scores(target_date=None)

        assert "NBA API unavailable" in str(exc_info.value)


class TestGetCurrentSeasonFromNBAAPI:
    """Test get_current_season_from_nba_api helper function."""

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_season_calculation_october_or_later(self, mock_scoreboard_class):
        """
        Test season calculation when date is October or later.
        Expected: Current year is start of season.
        """
        # Mock NBA API to return date in October
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "2024-10-28"  # October 2024
        mock_scoreboard_class.return_value = mock_sb_instance

        result = get_current_season_from_nba_api()

        # October 2024 → 2024-25 season
        assert result == "2024-25"

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_season_calculation_before_october(self, mock_scoreboard_class):
        """
        Test season calculation when date is before October.
        Expected: Previous year is start of season.
        """
        # Mock NBA API to return date in January
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "2025-01-28"  # January 2025
        mock_scoreboard_class.return_value = mock_sb_instance

        result = get_current_season_from_nba_api()

        # January 2025 → 2024-25 season (season started in October 2024)
        assert result == "2024-25"

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_season_calculation_december(self, mock_scoreboard_class):
        """
        Test season calculation for December (edge case).
        Expected: Current year is start of season.
        """
        # Mock NBA API to return date in December
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "2024-12-25"  # December 2024
        mock_scoreboard_class.return_value = mock_sb_instance

        result = get_current_season_from_nba_api()

        # December 2024 → 2024-25 season
        assert result == "2024-25"

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_season_calculation_september(self, mock_scoreboard_class):
        """
        Test season calculation for September (edge case before season starts).
        Expected: Previous year is start of season.
        """
        # Mock NBA API to return date in September
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "2024-09-15"  # September 2024
        mock_scoreboard_class.return_value = mock_sb_instance

        result = get_current_season_from_nba_api()

        # September 2024 → 2023-24 season (previous season)
        assert result == "2023-24"

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_raises_on_nba_api_failure(self, mock_scoreboard_class):
        """
        Test that function raises exception when NBA API fails.
        """
        # Mock ScoreBoard to raise an exception
        mock_scoreboard_class.side_effect = Exception("NBA API connection failed")

        with pytest.raises(Exception) as exc_info:
            get_current_season_from_nba_api()

        assert "NBA API connection failed" in str(exc_info.value)

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_raises_on_invalid_date_format(self, mock_scoreboard_class):
        """
        Test that function raises exception on invalid date format from NBA API.
        """
        # Mock NBA API to return invalid date format
        mock_sb_instance = Mock()
        mock_sb_instance.score_board_date = "invalid-date"
        mock_scoreboard_class.return_value = mock_sb_instance

        with pytest.raises(ValueError):
            get_current_season_from_nba_api()


class TestAdvancedStatsSeasonDetection:
    """Test that advanced stats functions use NBA API for season detection."""

    @patch('nba_mcp.api.advanced_stats.get_current_season_from_nba_api')
    @patch('nba_mcp.api.advanced_stats.asyncio.to_thread')
    @patch('nba_mcp.api.advanced_stats.resolve_entity')
    async def test_get_team_standings_uses_nba_api_season(
        self, mock_resolve, mock_to_thread, mock_get_season
    ):
        """
        Test that get_team_standings uses NBA API for season when not provided.
        """
        from nba_mcp.api.advanced_stats import get_team_standings

        # Mock the helper function
        mock_get_season.return_value = "2024-25"

        # Mock entity resolution (not needed for this test, but function calls it)
        mock_to_thread.return_value = MagicMock()

        # Call without season parameter
        try:
            result = await get_team_standings(season=None)
        except:
            pass  # We're just testing that get_current_season_from_nba_api was called

        # Verify that get_current_season_from_nba_api was called
        mock_get_season.assert_called_once()

    @patch('nba_mcp.api.advanced_stats.get_current_season_from_nba_api')
    @patch('nba_mcp.api.advanced_stats.asyncio.to_thread')
    @patch('nba_mcp.api.advanced_stats.resolve_entity')
    async def test_get_team_advanced_stats_uses_nba_api_season(
        self, mock_resolve, mock_to_thread, mock_get_season
    ):
        """
        Test that get_team_advanced_stats uses NBA API for season when not provided.
        """
        from nba_mcp.api.advanced_stats import get_team_advanced_stats

        # Mock the helper function
        mock_get_season.return_value = "2024-25"

        # Mock entity resolution
        mock_entity = Mock()
        mock_entity.entity_id = 1610612747  # Lakers
        mock_entity.name = "Los Angeles Lakers"
        mock_resolve.return_value = mock_entity

        # Mock NBA API response
        mock_to_thread.return_value = MagicMock()

        # Call without season parameter
        try:
            result = await get_team_advanced_stats(team_name="Lakers", season=None)
        except:
            pass  # We're just testing that get_current_season_from_nba_api was called

        # Verify that get_current_season_from_nba_api was called
        mock_get_season.assert_called_once()

    @patch('nba_mcp.api.advanced_stats.get_current_season_from_nba_api')
    @patch('nba_mcp.api.advanced_stats.asyncio.to_thread')
    @patch('nba_mcp.api.advanced_stats.resolve_entity')
    async def test_get_player_advanced_stats_uses_nba_api_season(
        self, mock_resolve, mock_to_thread, mock_get_season
    ):
        """
        Test that get_player_advanced_stats uses NBA API for season when not provided.
        """
        from nba_mcp.api.advanced_stats import get_player_advanced_stats

        # Mock the helper function
        mock_get_season.return_value = "2024-25"

        # Mock entity resolution
        mock_entity = Mock()
        mock_entity.entity_id = 2544  # LeBron James
        mock_entity.name = "LeBron James"
        mock_resolve.return_value = mock_entity

        # Mock NBA API response
        mock_to_thread.return_value = MagicMock()

        # Call without season parameter
        try:
            result = await get_player_advanced_stats(player_name="LeBron James", season=None)
        except:
            pass  # We're just testing that get_current_season_from_nba_api was called

        # Verify that get_current_season_from_nba_api was called
        mock_get_season.assert_called_once()


class TestDateHandlingConsistency:
    """Integration tests to verify consistent date handling across the codebase."""

    @patch('nba_mcp.api.advanced_stats.ScoreBoard')
    def test_consistent_season_calculation_logic(self, mock_scoreboard_class):
        """
        Test that season calculation logic is consistent regardless of environment.
        """
        # Test cases: (nba_date, expected_season)
        test_cases = [
            ("2024-10-01", "2024-25"),  # Season start (October 1)
            ("2024-10-31", "2024-25"),  # End of October
            ("2024-11-15", "2024-25"),  # November
            ("2024-12-31", "2024-25"),  # End of calendar year
            ("2025-01-01", "2024-25"),  # New year, same season
            ("2025-06-30", "2024-25"),  # End of season
            ("2025-09-30", "2024-25"),  # Right before new season
            ("2025-10-01", "2025-26"),  # New season starts
        ]

        for nba_date, expected_season in test_cases:
            # Mock NBA API
            mock_sb_instance = Mock()
            mock_sb_instance.score_board_date = nba_date
            mock_scoreboard_class.return_value = mock_sb_instance

            # Call function
            result = get_current_season_from_nba_api()

            # Verify
            assert result == expected_season, f"Date {nba_date} should return season {expected_season}, got {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
