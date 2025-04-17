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
from nba_api.stats.endpoints import playercareerstats, LeagueLeaders
from nba_mcp.api.tools.nba_api_utils import (
    get_player_id, normalize_stat_category, normalize_per_mode, normalize_season
)


def get_player_career_stats(player_name: str, season: str) -> pd.DataFrame:
    """Retrieve career stats for a specific player by name."""
    season = normalize_season(season)
    player_id = get_player_id(player_name)
    if player_id is None:
        raise ValueError(f"Player not found: {player_name}")
    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    career_df = career.get_data_frames()[0]
    # filter for season_id 2024-25
    career_df = career_df[career_df['SEASON_ID'] == season]
    return career_df


def get_league_leaders(season: str, stat_category: str, per_mode: str = "Totals") -> pd.DataFrame:
    """
    Retrieve league leaders for a specified season and statistical category.
    
    Args:
        season: Season string (e.g. '2024-25').
        stat_category: Statistical category such as "PTS", "AST", etc.
        per_mode: Mode of statistic aggregation (e.g. "Totals", "PerGame", "Per48").
                  Accepts various case variations or synonyms.
    
    Returns:
        A LeagueLeaders instance (or its DataFrame via get_data_frames()[0]).
    """
    season = normalize_season(season)
    # Normalize the stat_category input to the expected abbreviation.
    normalized_stat = normalize_stat_category(stat_category)
    # Normalize the per_mode parameter
    normalized_mode = normalize_per_mode(per_mode)
    
    params = {
        "league_id": "00",
        "per_mode48": normalized_mode,
        "scope": "S",
        "season": season,
        "season_type_all_star": "Regular Season",
        "stat_category_abbreviation": normalized_stat,
        "active_flag_nullable": ""
    }
    
    leaders = LeagueLeaders(**params)
    leaders_df = leaders.get_data_frames()[0]
                
    return leaders_df


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

    
