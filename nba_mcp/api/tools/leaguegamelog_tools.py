# leaguegamelog_tools.py
"""
Example Script for Pulling NBA Data Using nba_api

This script demonstrates how to use endpoints for retrieving game log data.
"""

from datetime import date, datetime
from typing import Optional, Union

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, leaguegamefinder

from nba_mcp.api.tools.nba_api_utils import (
    get_team_id,
    normalize_date,
    normalize_season,
    normalize_season_type,
)


def fetch_league_game_log(
    season: str,
    team_name: Optional[str] = None,
    season_type: str = "Regular Season",
    date_from: Optional[Union[str, date, datetime]] = None,
    date_to: Optional[Union[str, date, datetime]] = None,
    outcome: Optional[str] = None,
    direction: str = "DESC",
    sorter: str = "DATE",
) -> pd.DataFrame:
    """
    Fetch full-season or filtered game-log via LeagueGameFinder.

    This function now uses LeagueGameFinder instead of LeagueGameLog to support
    advanced filtering including outcome (W/L) filtering at the API level.

    Args:
      season:      "YYYY-YY" season string.
      team_name:   optional full or partial team name to filter by.
      season_type: user-friendly season type ("regular", "playoff", "preseason", "allstar", etc.)
      date_from:   optional start date.
      date_to:     optional end date.
      outcome:     optional win/loss filter ("W" for wins, "L" for losses).
      direction:   "ASC" or "DESC" sorting by the sorter field (not used with LeagueGameFinder).
      sorter:      one of the API sorter options (not used with LeagueGameFinder).

    Returns:
      DataFrame of all games (filtered by parameters).
    """
    # 1) normalize the season itself (ensures "YYYY-YY"),
    # 2) normalize the season_type into exactly what the API expects
    season = normalize_season(season)
    season_type = normalize_season_type(season_type)

    df_from = normalize_date(date_from) if date_from else None
    df_to = normalize_date(date_to) if date_to else None

    # Get team_id if team_name provided
    team_id = None
    if team_name:
        team_id = get_team_id(team_name)

    # Use LeagueGameFinder (supports outcome filtering)
    finder = leaguegamefinder.LeagueGameFinder(
        player_or_team_abbreviation="T",  # Team games
        season_nullable=season,
        season_type_nullable=season_type,
        date_from_nullable=(df_from.strftime("%Y-%m-%d") if df_from else ""),
        date_to_nullable=(df_to.strftime("%Y-%m-%d") if df_to else ""),
        outcome_nullable=(outcome if outcome else ""),  # W/L filtering
        team_id_nullable=(str(team_id) if team_id else ""),  # Team filter
        league_id_nullable="00",
    )
    df = finder.get_data_frames()[0]

    # If no team_id was found but team_name was provided, fallback to name matching
    if team_name and team_id is None and not df.empty:
        mask = df["TEAM_NAME"].str.contains(team_name, case=False, na=False) | df[
            "MATCHUP"
        ].str.contains(team_name, case=False, na=False)
        df = df[mask]

    # Sort by date (descending by default)
    if not df.empty and "GAME_DATE" in df.columns:
        df = df.sort_values(by="GAME_DATE", ascending=(direction == "ASC"))

    return df.reset_index(drop=True)


if __name__ == "__main__":
    # ------------------------------
    # Example : NBA Official Stats – League Game Log
    # Usage: Historical log for a specific date range
    # ------------------------------

    # 4) Full 2024‑25 season log
    full_log = fetch_league_game_log("2024-25")
    print(f"\n📊 2024‑25 season: total rows = {full_log.shape[0]}")
    print(full_log.head())

    # 5) Celtics only (partial match)
    celtics_log = fetch_league_game_log("2024-25", team_name="Celtics")
    if celtics_log.empty:
        print("\n❗ No Celtics games found in 2024‑25 log.")
    else:
        print(f"\n🐐 Celtics games this season: {celtics_log.shape[0]} rows")
        print(celtics_log.head())

    # 6) Date‑range: April 1–15, 2025
    april_df = fetch_league_game_log(
        "2024-25", date_from="2025-04-01", date_to="2025-04-15"
    )
    # sort by GAME_DATE
    april_df = april_df.sort_values(by="GAME_DATE", ascending=False)
    print(f"\n📆 Games from 2025-04-01 to 2025-04-15: {april_df.shape[0]} rows")
    print(april_df.head())

    from pprint import pprint

    test_season_types = [
        "Regular Season",  # canonical
        "regular",  # alias
        "Playoffs",  # canonical
        "playoff",  # alias
        "Postseason",  # alias→Playoffs
        "Pre Season",  # canonical
        "preseason",  # alias
        "pre",  # alias
        "All Star",  # canonical
        "allstar",  # alias
        "All-Star",  # variant
    ]

    season = "2024-25"
    for raw_type in test_season_types:
        print(f"\n🔄 Testing season_type = {raw_type!r}")
        try:
            df = fetch_league_game_log(
                season=season,
                season_type=raw_type,
                # keep the rest default; or you could add a date window here
            )
            print(f"  → normalized to: {normalize_season_type(raw_type)!r}")
            print(f"  → rows returned: {df.shape[0]}")
            # show up to 3 rows so you can eyeball it
            pprint(df.head(3).to_dict(orient="records"))
        except Exception as e:
            print(f"  ❗ error: {e}")
