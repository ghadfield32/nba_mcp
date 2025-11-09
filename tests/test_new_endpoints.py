"""Tests for newly registered endpoints in unified_fetch system."""
import pytest
import pandas as pd
from nba_mcp.data.unified_fetch import unified_fetch
from nba_mcp.data.endpoint_registry import get_registry


class TestNewEndpointRegistration:
    """Test that all new endpoints are properly registered."""

    def test_all_endpoints_registered(self):
        """Verify all expected endpoints are registered."""
        # Import to trigger decorators
        import nba_mcp.data.fetch

        registry = get_registry()
        registered = set(registry.list_endpoints())

        new_endpoints = {
            "player_game_log",
            "box_score",
            "clutch_stats",
            "player_head_to_head",
            "player_performance_splits",
            "play_by_play",
        }

        assert new_endpoints.issubset(
            registered
        ), f"Missing endpoints: {new_endpoints - registered}"

    def test_endpoint_metadata(self):
        """Verify endpoint metadata is correct."""
        import nba_mcp.data.fetch

        registry = get_registry()

        # Check player_game_log
        reg = registry.get_registration("player_game_log")
        assert reg is not None
        assert "player_name" in reg.required_params
        assert "season" in reg.optional_params
        assert "player" in reg.tags
        assert "game" in reg.tags

        # Check box_score
        reg = registry.get_registration("box_score")
        assert reg is not None
        assert "game_id" in reg.required_params
        assert "game" in reg.tags
        assert "box_score" in reg.tags

        # Check clutch_stats
        reg = registry.get_registration("clutch_stats")
        assert reg is not None
        assert "entity_name" in reg.required_params
        assert "entity_type" in reg.optional_params
        assert "clutch" in reg.tags

        # Check player_head_to_head
        reg = registry.get_registration("player_head_to_head")
        assert reg is not None
        assert "player1_name" in reg.required_params
        assert "player2_name" in reg.required_params
        assert "matchup" in reg.tags

        # Check player_performance_splits
        reg = registry.get_registration("player_performance_splits")
        assert reg is not None
        assert "player_name" in reg.required_params
        assert "splits" in reg.tags

        # Check play_by_play
        reg = registry.get_registration("play_by_play")
        assert reg is not None
        assert len(reg.required_params) == 0  # No required params
        assert "game_date" in reg.optional_params
        assert "team" in reg.optional_params


@pytest.mark.asyncio
class TestNewEndpointBasicFunctionality:
    """Basic functionality tests for new endpoints (mock-friendly)."""

    async def test_player_game_log_validation(self):
        """Test player_game_log parameter validation."""
        # Test that missing required param raises error
        with pytest.raises(Exception) as exc_info:
            await unified_fetch("player_game_log", {})

        assert "player_name" in str(exc_info.value).lower()

    async def test_box_score_validation(self):
        """Test box_score parameter validation."""
        # Test that missing required param raises error
        with pytest.raises(Exception) as exc_info:
            await unified_fetch("box_score", {})

        assert "game_id" in str(exc_info.value).lower()

    async def test_clutch_stats_validation(self):
        """Test clutch_stats parameter validation."""
        # Test that missing required param raises error
        with pytest.raises(Exception) as exc_info:
            await unified_fetch("clutch_stats", {})

        assert "entity_name" in str(exc_info.value).lower()

    async def test_player_head_to_head_validation(self):
        """Test player_head_to_head parameter validation."""
        # Test that missing required params raises error
        with pytest.raises(Exception) as exc_info:
            await unified_fetch("player_head_to_head", {})

        assert (
            "player1_name" in str(exc_info.value).lower()
            or "player2_name" in str(exc_info.value).lower()
        )

    async def test_player_performance_splits_validation(self):
        """Test player_performance_splits parameter validation."""
        # Test that missing required param raises error
        with pytest.raises(Exception) as exc_info:
            await unified_fetch("player_performance_splits", {})

        assert "player_name" in str(exc_info.value).lower()

    async def test_play_by_play_no_params(self):
        """Test play_by_play with no params returns placeholder."""
        # play_by_play has no required params, should return placeholder
        result = await unified_fetch("play_by_play", {})

        # Should return a DataFrame (even if placeholder)
        assert result.data.num_rows >= 0

        # Check provenance
        assert "play_by_play" in result.provenance.source_endpoints


# Integration tests are commented out to avoid hitting real NBA API during CI
# Uncomment and run manually to test against real API


# @pytest.mark.asyncio
# class TestNewEndpointIntegration:
#     """Integration tests hitting real NBA API (run manually)."""
#
#     async def test_player_game_log_real_data(self):
#         """Test fetching real player game log."""
#         result = await unified_fetch(
#             "player_game_log",
#             {"player_name": "LeBron James", "season": "2023-24", "last_n_games": 5}
#         )
#
#         assert result.data.num_rows > 0
#         assert result.data.num_rows <= 5  # Should respect last_n_games
#
#     async def test_box_score_real_data(self):
#         """Test fetching real box score."""
#         # Use a known game ID from 2023-24 season
#         result = await unified_fetch(
#             "box_score",
#             {"game_id": "0022300001"}  # First game of 2023-24 season
#         )
#
#         assert result.data.num_rows > 0  # Should have player stats
#
#     async def test_clutch_stats_real_data(self):
#         """Test fetching real clutch stats."""
#         result = await unified_fetch(
#             "clutch_stats",
#             {"entity_name": "LeBron James", "entity_type": "player", "season": "2023-24"}
#         )
#
#         assert result.data.num_rows >= 0  # May be empty if no clutch situations
#
#     async def test_player_head_to_head_real_data(self):
#         """Test fetching real head-to-head stats."""
#         result = await unified_fetch(
#             "player_head_to_head",
#             {"player1_name": "LeBron James", "player2_name": "Kevin Durant", "season": "2023-24"}
#         )
#
#         assert result.data.num_rows >= 0  # May be empty if they didn't face each other
#
#     async def test_player_performance_splits_real_data(self):
#         """Test fetching real performance splits."""
#         result = await unified_fetch(
#             "player_performance_splits",
#             {"player_name": "LeBron James", "season": "2023-24", "last_n_games": 10}
#         )
#
#         assert result.data.num_rows > 0  # Should have splits data
#
#     async def test_play_by_play_real_data(self):
#         """Test fetching real play-by-play data."""
#         result = await unified_fetch(
#             "play_by_play",
#             {"game_date": "2024-01-15", "team": "Lakers"}
#         )
#
#         assert result.data.num_rows >= 0  # May be empty if no game on that date
