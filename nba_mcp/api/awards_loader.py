"""
Awards Data Loader for NBA MCP

Provides fast, cached access to historical NBA awards data.
Uses LRU caching for instant lookups (<1ms).

Award Types Supported:
- MVP (Most Valuable Player)
- Finals MVP
- DPOY (Defensive Player of the Year)
- ROY (Rookie of the Year)
- SMOY (Sixth Man of the Year)
- MIP (Most Improved Player)
- COY (Coach of the Year)

Data Source: api_documentation/awards_data.json (2004-2024)
"""

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


# Human-readable award names
AWARD_DISPLAY_NAMES = {
    "mvp": "MVP",
    "finals_mvp": "Finals MVP",
    "dpoy": "Defensive Player of the Year",
    "roy": "Rookie of the Year",
    "smoy": "Sixth Man of the Year",
    "mip": "Most Improved Player",
    "coy": "Coach of the Year",
}


@lru_cache(maxsize=1)
def load_awards_data() -> Dict[str, List[Dict]]:
    """
    Load historical awards data from JSON file.

    Cached in memory for instant subsequent access (<1ms).

    Returns:
        Dict mapping award_type -> list of winners
        Example: {"mvp": [{"season": "2023-24", "player_id": 203999, ...}], ...}

    Raises:
        FileNotFoundError: If awards_data.json doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    # awards_data.json is in the root api_documentation folder
    # Go up from nba_mcp/api/awards_loader.py to nba_mcp/ to root/ to api_documentation/
    awards_file = Path(__file__).parent.parent.parent / "api_documentation" / "awards_data.json"

    if not awards_file.exists():
        raise FileNotFoundError(
            f"Awards data file not found: {awards_file}\n"
            "Please ensure api_documentation/awards_data.json exists."
        )

    try:
        with open(awards_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded awards data: {len(data)} award types")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse awards JSON: {e}")
        raise


def get_player_awards_for_season(
    player_id: int,
    season: str
) -> Dict[str, bool]:
    """
    Get all awards won by a player in a specific season.

    Args:
        player_id: NBA player ID (e.g., 2544 for LeBron James)
        season: Season in YYYY-YY format (e.g., "2023-24")

    Returns:
        Dict of award_type -> bool (True if won, False otherwise)
        Example: {"mvp": True, "dpoy": False, "finals_mvp": False, ...}

    Example:
        >>> awards = get_player_awards_for_season(203999, "2023-24")  # Jokić
        >>> awards["mvp"]
        True
        >>> awards["dpoy"]
        False
    """
    awards_data = load_awards_data()

    # Check each award type (excluding metadata)
    awards_won = {}
    for award_type, winners in awards_data.items():
        if award_type == "metadata":
            continue

        # Check if this player won this award in this season
        won = any(
            w.get("season") == season and w.get("player_id") == player_id
            for w in winners
        )
        awards_won[award_type] = won

    return awards_won


def get_award_winners(
    award_type: str,
    start_season: Optional[str] = None,
    end_season: Optional[str] = None,
    last_n: Optional[int] = None
) -> List[Dict]:
    """
    Get winners of a specific award with optional filtering.

    Args:
        award_type: Award type (mvp, finals_mvp, dpoy, roy, smoy, mip, coy)
        start_season: Optional start season (inclusive, e.g., "2020-21")
        end_season: Optional end season (inclusive, e.g., "2023-24")
        last_n: Optional number of most recent winners to return

    Returns:
        List of winner dictionaries sorted by season (most recent first)
        Example: [
            {"season": "2023-24", "player_id": 203999, "player_name": "Nikola Jokić", ...},
            {"season": "2022-23", "player_id": 203954, "player_name": "Joel Embiid", ...},
            ...
        ]

    Raises:
        ValueError: If award_type is unknown

    Examples:
        >>> # Get last 10 MVPs
        >>> winners = get_award_winners("mvp", last_n=10)

        >>> # Get all DPOYs from 2020-21 to 2023-24
        >>> winners = get_award_winners("dpoy", start_season="2020-21", end_season="2023-24")
    """
    awards_data = load_awards_data()

    # Validate award type
    if award_type not in awards_data:
        available = [k for k in awards_data.keys() if k != "metadata"]
        raise ValueError(
            f"Unknown award type: {award_type}. "
            f"Available types: {', '.join(available)}"
        )

    # Get all winners for this award type
    winners = awards_data[award_type].copy()

    # Sort by season (most recent first)
    winners.sort(key=lambda x: x.get("season", ""), reverse=True)

    # Apply filters
    if start_season or end_season:
        filtered = []
        for winner in winners:
            season = winner.get("season", "")

            # Check if within range
            if start_season and season < start_season:
                continue
            if end_season and season > end_season:
                continue

            filtered.append(winner)
        winners = filtered

    # Apply last_n filter
    if last_n is not None and last_n > 0:
        winners = winners[:last_n]

    return winners


def format_awards_human_readable(awards_dict: Dict[str, bool]) -> List[str]:
    """
    Convert awards boolean dict to human-readable list.

    Args:
        awards_dict: Dict of award_type -> bool (e.g., {"mvp": True, "dpoy": False})

    Returns:
        List of human-readable award names for awards that were won
        Example: ["MVP", "All-NBA First Team"]

    Example:
        >>> awards = {"mvp": True, "dpoy": False, "finals_mvp": True}
        >>> format_awards_human_readable(awards)
        ["MVP", "Finals MVP"]
    """
    return [
        AWARD_DISPLAY_NAMES.get(award_type, award_type)
        for award_type, won in awards_dict.items()
        if won
    ]


def get_all_award_types() -> List[str]:
    """
    Get list of all available award types.

    Returns:
        List of award type strings (e.g., ["mvp", "finals_mvp", "dpoy", ...])
    """
    awards_data = load_awards_data()
    return [k for k in awards_data.keys() if k != "metadata"]


def get_awards_metadata() -> Dict:
    """
    Get metadata about awards data (coverage, sources, etc.).

    Returns:
        Metadata dictionary from awards_data.json
    """
    awards_data = load_awards_data()
    return awards_data.get("metadata", {})


def format_award_winners_text(
    award_type: str,
    winners: List[Dict],
    max_display: int = 10
) -> str:
    """
    Format award winners as human-readable text.

    Args:
        award_type: Award type (for title)
        winners: List of winner dictionaries
        max_display: Maximum number of winners to display

    Returns:
        Formatted text string

    Example:
        >>> winners = get_award_winners("mvp", last_n=5)
        >>> print(format_award_winners_text("mvp", winners))
        MVP Winners (Last 5 Seasons)
        ════════════════════════════
        2023-24: Nikola Jokić (DEN)
        2022-23: Joel Embiid (PHI)
        ...
    """
    # Get display name
    display_name = AWARD_DISPLAY_NAMES.get(award_type, award_type.upper())

    # Build header
    count_text = f"Last {len(winners)}" if len(winners) <= max_display else f"Top {max_display}"
    lines = [
        f"{display_name} Winners ({count_text} Seasons)",
        "=" * 50
    ]

    # Add winners (limit to max_display)
    for winner in winners[:max_display]:
        season = winner.get("season", "Unknown")
        player_name = winner.get("player_name", "Unknown")
        team = winner.get("team", "")

        if team:
            lines.append(f"{season}: {player_name} ({team})")
        else:
            lines.append(f"{season}: {player_name}")

    # Add truncation message if needed
    if len(winners) > max_display:
        lines.append(f"... and {len(winners) - max_display} more")

    return "\n".join(lines)
