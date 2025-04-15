"""NBA MCP Server Package."""

from nba_mcp.nba_server import main

__all__ = [
    "main",
    "get_live_scoreboard",
    "get_player_career_stats",
    "get_league_leaders",
    "get_league_game_log"
]

__version__ = "0.1.0"