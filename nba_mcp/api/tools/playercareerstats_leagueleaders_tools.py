"""
Example Script for Pulling NBA Data Using nba_api

This script demonstrates how to use two different kinds of endpoints:

1. NBA Live Data:
   - Live Scoreboard: Retrieves game data from NBA.com in real time.
2. NBA Official Stats:
   - Player Career Stats: Example for Nikola Jokić (player_id '203999').
   - League Leaders: Retrieve season leader statistics.
   - League Game Log: Retrieves game log data for a given season.

The script prints some of the first few rows of each returned DataFrame,
and for the player career stats it also shows how to fetch a JSON snippet.

Ensure you have Python 3.7+ installed.
"""


import pandas as pd
from typing import Union, List
from nba_api.stats.endpoints import playercareerstats, LeagueLeaders
from nba_mcp.api.tools.nba_api_utils import (
    get_player_id, normalize_stat_category, normalize_per_mode, normalize_season
)


def get_player_career_stats(player_name: str, season: Union[str, List[str]]) -> pd.DataFrame:
    """Retrieve career stats for a specific player by name."""
    # 1) Normalize & inspect what normalize_season returns
    season_norm = normalize_season(season)
    print(f"DEBUG ▶ normalize_season({season!r}) → {season_norm!r} (type={type(season_norm)})")
    
    # 2) Look up the player ID
    player_id = get_player_id(player_name)
    if player_id is None:
        raise ValueError(f"Player not found: {player_name!r}")

    # 3) Fetch the raw career DataFrame
    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    career_df = career.get_data_frames()[0]
    
    # 4) Log available seasons in the data
    available = career_df['SEASON_ID'].unique().tolist()
    print(f"DEBUG ▶ Available SEASON_IDs: {available}")

    # 5) Apply filtering, choosing the right comparison
    if isinstance(season_norm, (list, tuple, set)):
        filtered = career_df[career_df['SEASON_ID'].isin(season_norm)]
        print(f"DEBUG ▶ Filtering with .isin({season_norm!r}), result shape: {filtered.shape}")
    else:
        filtered = career_df[career_df['SEASON_ID'] == season_norm]
        print(f"DEBUG ▶ Filtering with == {season_norm!r}, result shape: {filtered.shape}")

    # 6) Return the filtered DataFrame
    return filtered


def get_league_leaders(season: str, stat_category: str, per_mode: str = "Totals") -> pd.DataFrame:
    """
    Retrieve league leaders for a specified season and statistical category.
    (Unchanged from before—kept here just for your reference.)
    """
    season_norm = normalize_season(season)
    normalized_stat = normalize_stat_category(stat_category)
    normalized_mode = normalize_per_mode(per_mode)
    
    params = {
        "league_id": "00",
        "per_mode48": normalized_mode,
        "scope": "S",
        "season": season_norm,
        "season_type_all_star": "Regular Season",
        "stat_category_abbreviation": normalized_stat,
        "active_flag_nullable": ""
    }
    
    leaders = LeagueLeaders(**params)
    return leaders.get_data_frames()[0]



def main() -> None:
    """Run example queries for player career stats and league leaders."""
    # ------------------------------
    # Example : NBA Official Stats – Player Career Stats
    # ------------------------------
    # Update examples to use names instead of IDs
    print("\nFetching player career stats for Nikola Jokić:")
    try:
        season = "2024"
        career_df = get_player_career_stats('Nikola Jokić', season)

        print("Player Career Stats DataFrame (first 5 rows):")
        print(career_df.head())
    except Exception as e:
        print("Error retrieving player career stats:", e)
    
    # ------------------------------
    # Example : NBA Official Stats – League Leaders
    # ------------------------------
    per_mode = "PerGame"
    season = "1990-91"
    stat_category = "rebounds"

    print(f"\nFetching league leaders for season {season}, stat {stat_category}:")
    try:
        leaders = get_league_leaders(season, stat_category, per_mode)
        
        # Display without duplicates
        print("League Leaders DataFrame (first 5 rows):")
        print(leaders.head())
    except Exception as e:
        print("Error retrieving league leaders:", e)


if __name__ == '__main__':
    main()

    
