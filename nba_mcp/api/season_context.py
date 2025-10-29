"""
Season Context Utility

Provides current season information for LLM context.
This helps the LLM understand what season it is and make better queries.
"""

from datetime import datetime
from typing import Dict, Any


def get_current_season() -> str:
    """
    Get the current NBA season string in 'YYYY-YY' format.

    The NBA season typically runs from October to June:
    - Games from October-December are in the first year
    - Games from January-June are still part of the season that started previous October
    - Games from July-September are offseason (returns next season)

    Returns:
        Season string like '2024-25'

    Examples:
        - October 2024 → '2024-25'
        - March 2025 → '2024-25' (still part of 2024-25 season)
        - July 2025 → '2025-26' (offseason, preparing for next season)
    """
    today = datetime.now()
    year = today.year
    month = today.month

    # NBA season logic:
    # Oct-Dec: Current year is start of season (e.g., Oct 2024 = 2024-25)
    # Jan-Jun: Previous year was start of season (e.g., Mar 2025 = 2024-25)
    # Jul-Sep: Offseason, return next season (e.g., Jul 2025 = 2025-26)

    if month >= 10:  # October, November, December
        # Season starts this year
        season_start_year = year
    elif month <= 6:  # January through June
        # Season started previous year
        season_start_year = year - 1
    else:  # July, August, September (offseason)
        # Offseason - return next season
        season_start_year = year

    season_end_year = season_start_year + 1
    season_end_year_short = str(season_end_year)[-2:]

    return f"{season_start_year}-{season_end_year_short}"


def get_season_context(include_date: bool = True) -> str:
    """
    Get formatted season context for LLM prompts.

    This provides the LLM with important temporal context so it can:
    - Know what the current season is
    - Make appropriate season-based queries
    - Understand what data is available

    Args:
        include_date: If True, includes today's date in the context

    Returns:
        Formatted context string for LLM consumption

    Example output:
        "Current NBA Season: 2024-25 (as of 2025-10-29)"
    """
    current_season = get_current_season()
    today = datetime.now().strftime("%Y-%m-%d")

    if include_date:
        return f"Current NBA Season: {current_season} (as of {today})"
    else:
        return f"Current NBA Season: {current_season}"


def get_season_metadata() -> Dict[str, Any]:
    """
    Get comprehensive season metadata for tool responses.

    Returns:
        Dictionary with season information including:
        - current_season: The current season string
        - season_start_year: The starting year of current season
        - season_end_year: The ending year of current season
        - current_date: Today's date
        - is_regular_season: Whether we're in regular season (Oct-Apr)
        - is_playoffs: Whether we're in playoffs (Apr-Jun)
        - is_offseason: Whether we're in offseason (Jul-Sep)

    Example:
        {
            "current_season": "2024-25",
            "season_start_year": 2024,
            "season_end_year": 2025,
            "current_date": "2025-10-29",
            "is_regular_season": True,
            "is_playoffs": False,
            "is_offseason": False
        }
    """
    current_season = get_current_season()
    today = datetime.now()
    month = today.month

    season_start_year = int(current_season.split('-')[0])
    season_end_year = season_start_year + 1

    # Determine season phase (approximate)
    # Regular season: October - April
    # Playoffs: April - June
    # Offseason: July - September

    is_regular_season = (month >= 10) or (month <= 4)
    is_playoffs = 4 <= month <= 6
    is_offseason = 7 <= month <= 9

    return {
        "current_season": current_season,
        "season_start_year": season_start_year,
        "season_end_year": season_end_year,
        "current_date": today.strftime("%Y-%m-%d"),
        "is_regular_season": is_regular_season,
        "is_playoffs": is_playoffs,
        "is_offseason": is_offseason,
        "month": month,
        "year": today.year
    }


def format_season_context_for_tool(tool_name: str) -> str:
    """
    Format season context specifically for a tool's output.

    This prepends season context to tool outputs so the LLM always
    knows what season the data relates to.

    Args:
        tool_name: Name of the tool calling this function

    Returns:
        Formatted context string to prepend to tool output

    Example:
        "📅 Current NBA Season: 2024-25 (as of 2025-10-29)\n"
        "Tool: get_player_career_information\n\n"
    """
    context = get_season_context(include_date=True)
    return f"📅 {context}\nTool: {tool_name}\n\n"


# For testing
if __name__ == "__main__":
    print("Current Season:", get_current_season())
    print("\nSeason Context:", get_season_context())
    print("\nSeason Metadata:")
    import json
    print(json.dumps(get_season_metadata(), indent=2))
    print("\nFormatted for Tool:")
    print(format_season_context_for_tool("get_player_career_information"))
