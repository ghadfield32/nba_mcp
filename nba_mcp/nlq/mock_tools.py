# nba_mcp/nlq/mock_tools.py
"""
Mock tools for testing the NLQ pipeline without real NBA API calls.
"""

from typing import Dict, Any, List, Optional
import asyncio


async def mock_get_league_leaders_info(
    stat_category: str,
    season: Optional[str] = None,
    per_mode: str = "PerGame",
    season_type_all_star: str = "Regular Season",
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)  # Simulate API call
    return {
        "stat_category": stat_category,
        "season": season,
        "leaders": [
            {"player": "Player 1", "value": 10.5},
            {"player": "Player 2", "value": 9.8},
        ],
    }


async def mock_compare_players(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
    normalization: str = "per_75",
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {
        "player1": {"name": player1_name, "ppg": 25.5},
        "player2": {"name": player2_name, "ppg": 27.3},
    }


async def mock_get_team_standings(
    season: Optional[str] = None, conference: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return [
        {"team": "Team 1", "wins": 40, "losses": 20},
        {"team": "Team 2", "wins": 35, "losses": 25},
    ]


async def mock_get_team_advanced_stats(
    team_name: str, season: Optional[str] = None
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {
        "team_name": team_name,
        "offensive_rating": 115.5,
        "defensive_rating": 108.2,
    }


async def mock_get_player_advanced_stats(
    player_name: str, season: Optional[str] = None
) -> Dict[str, Any]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return {"player_name": player_name, "true_shooting_pct": 0.625, "usage_pct": 28.5}


async def mock_get_live_scores(
    target_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Mock implementation for testing."""
    await asyncio.sleep(0.1)
    return [
        {
            "home_team": "Lakers",
            "away_team": "Celtics",
            "home_score": 105,
            "away_score": 98,
        }
    ]


def register_mock_tools():
    """Register all mock tools for testing."""
    from .tool_registry import register_tool

    register_tool("get_league_leaders_info", mock_get_league_leaders_info)
    register_tool("compare_players", mock_compare_players)
    register_tool("get_team_standings", mock_get_team_standings)
    register_tool("get_team_advanced_stats", mock_get_team_advanced_stats)
    register_tool("get_player_advanced_stats", mock_get_player_advanced_stats)
    register_tool("get_live_scores", mock_get_live_scores)
