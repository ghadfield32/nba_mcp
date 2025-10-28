# leaguegamelog_tools.py
"""
Example Script for Pulling NBA Data Using nba_api

This script demonstrates how to use endpoints for retrieving game log data.
"""

from datetime import date, datetime
from typing import Optional, Union

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog

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
    direction: str = "DESC",
    sorter: str = "DATE",
) -> pd.DataFrame:
    """
    Fetch full-season or filtered game-log via LeagueGameLog.

    Args:
      season:      "YYYY-YY" season string.
      team_name:   optional full or partial team name to filter by.
      season_type: user-friendly season type ("regular", "playoff", "preseason", "allstar", etc.)
      date_from:   optional start date.
      date_to:     optional end date.
      direction:   "ASC" or "DESC" sorting by the sorter field.
      sorter:      one of the API sorter options (e.g. "PTS","DATE", etc.)

    Returns:
      DataFrame of all games (filtered to team_name if given).
    """
    # 1) normalize the season itself (ensures "YYYY-YY"),
    # 2) normalize the season_type into exactly what the API expects
    season = normalize_season(season)
    season_type = normalize_season_type(season_type)

    df_from = normalize_date(date_from) if date_from else None
    df_to = normalize_date(date_to) if date_to else None

    lg = leaguegamelog.LeagueGameLog(
        counter=0,
        direction=direction,
        league_id="00",
        player_or_team_abbreviation="T",
        season=season,
        season_type_all_star=season_type,
        sorter=sorter,
        date_from_nullable=(df_from.strftime("%Y-%m-%d") if df_from else ""),
        date_to_nullable=(df_to.strftime("%Y-%m-%d") if df_to else ""),
    )
    df = lg.get_data_frames()[0]

    if team_name:
        # use centralized get_team_id for lookup
        tid = get_team_id(team_name)
        if tid is not None:
            df = df[df["TEAM_ID"] == tid]
        else:
            # fallback to matching in the API‑returned NAMEs
            mask = df["TEAM_NAME"].str.contains(team_name, case=False, na=False) | df[
                "MATCHUP"
            ].str.contains(team_name, case=False, na=False)
            df = df[mask]

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
