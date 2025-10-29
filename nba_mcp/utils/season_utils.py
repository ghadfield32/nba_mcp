"""
Season Range Utilities

Provides parsing and validation for NBA season ranges.
Supports flexible input formats for single and multi-season queries.
"""

import json
from typing import List, Union
import logging

logger = logging.getLogger(__name__)


def parse_season_input(season: str) -> List[str]:
    """
    Parse season input into list of season strings.

    Supports multiple formats:
    - Single season: "2023-24" → ["2023-24"]
    - JSON array: '["2021-22", "2022-23", "2023-24"]' → ["2021-22", "2022-23", "2023-24"]
    - Season range: "2021-22:2023-24" → ["2021-22", "2022-23", "2023-24"]
    - Season range (alt): "2021-22..2023-24" → ["2021-22", "2022-23", "2023-24"]

    Args:
        season: Season string in one of the supported formats

    Returns:
        List of season strings in "YYYY-YY" format

    Examples:
        >>> parse_season_input("2023-24")
        ['2023-24']

        >>> parse_season_input("2021-22:2023-24")
        ['2021-22', '2022-23', '2023-24']

        >>> parse_season_input('["2022-23", "2023-24"]')
        ['2022-23', '2023-24']
    """
    # Handle JSON array format
    if season.startswith("["):
        try:
            seasons = json.loads(season)
            if not isinstance(seasons, list):
                raise ValueError(f"JSON must be array of seasons, got: {type(seasons)}")
            logger.info(f"Parsed JSON array: {len(seasons)} seasons")
            return seasons
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON array format: {e}")

    # Handle season range format (colon or double-dot)
    if ":" in season or ".." in season:
        separator = ":" if ":" in season else ".."
        parts = season.split(separator)

        if len(parts) != 2:
            raise ValueError(f"Season range must have format 'START{separator}END', got: {season}")

        start_season, end_season = parts[0].strip(), parts[1].strip()
        seasons = expand_season_range(start_season, end_season)
        logger.info(f"Expanded season range {start_season} to {end_season}: {len(seasons)} seasons")
        return seasons

    # Single season
    validate_season_format(season)
    return [season]


def expand_season_range(start_season: str, end_season: str) -> List[str]:
    """
    Expand season range into list of all seasons.

    Args:
        start_season: Starting season (e.g., "2021-22")
        end_season: Ending season (e.g., "2023-24")

    Returns:
        List of all seasons in range (inclusive)

    Examples:
        >>> expand_season_range("2021-22", "2023-24")
        ['2021-22', '2022-23', '2023-24']
    """
    validate_season_format(start_season)
    validate_season_format(end_season)

    # Parse start year
    start_year = int(start_season.split("-")[0])
    end_year = int(end_season.split("-")[0])

    if start_year > end_year:
        raise ValueError(f"Start season {start_season} must be before end season {end_season}")

    # Generate all seasons in range
    seasons = []
    for year in range(start_year, end_year + 1):
        next_year = year + 1
        season_str = f"{year}-{str(next_year)[2:]}"  # "2021-22" format
        seasons.append(season_str)

    return seasons


def validate_season_format(season: str) -> None:
    """
    Validate season format is YYYY-YY.

    Args:
        season: Season string to validate

    Raises:
        ValueError: If season format is invalid

    Examples:
        >>> validate_season_format("2023-24")  # OK
        >>> validate_season_format("2023")  # Raises ValueError
    """
    if not season or "-" not in season:
        raise ValueError(f"Season must have format 'YYYY-YY', got: {season}")

    parts = season.split("-")
    if len(parts) != 2:
        raise ValueError(f"Season must have format 'YYYY-YY', got: {season}")

    try:
        year1 = int(parts[0])
        year2 = int(parts[1])

        # Validate year values
        if year1 < 1900 or year1 > 2100:
            raise ValueError(f"Invalid start year: {year1}")

        # Year2 should be 2-digit representation of year1 + 1
        expected_year2 = (year1 + 1) % 100
        if year2 != expected_year2:
            raise ValueError(f"Season format error: {year1}-{year2:02d} (expected {year1}-{expected_year2:02d})")

    except ValueError as e:
        raise ValueError(f"Invalid season format '{season}': {e}")


def season_to_year(season: str) -> int:
    """
    Convert season string to starting year.

    Args:
        season: Season string (e.g., "2023-24")

    Returns:
        Starting year as integer

    Examples:
        >>> season_to_year("2023-24")
        2023
    """
    validate_season_format(season)
    return int(season.split("-")[0])


def format_season_display(seasons: List[str]) -> str:
    """
    Format season list for display.

    Args:
        seasons: List of season strings

    Returns:
        Human-readable string

    Examples:
        >>> format_season_display(["2023-24"])
        '2023-24'

        >>> format_season_display(["2021-22", "2022-23", "2023-24"])
        '3 seasons (2021-22, 2022-23, 2023-24)'
    """
    if len(seasons) == 1:
        return seasons[0]

    return f"{len(seasons)} seasons ({', '.join(seasons)})"


# Convenience constants
CURRENT_SEASON = "2024-25"  # Update annually
AVAILABLE_SEASONS = expand_season_range("1996-97", CURRENT_SEASON)  # NBA API data starts 1996-97
