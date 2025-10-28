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

import logging
from typing import List, Union

import pandas as pd
from nba_api.stats.endpoints import LeagueLeaders, playercareerstats

from nba_mcp.api.tools.nba_api_utils import (
    get_player_id,
    normalize_per_mode,
    normalize_season,
    normalize_stat_category,
)

logger = logging.getLogger(__name__)


def get_player_career_stats(
    player_name: str, season: Union[str, List[str]]
) -> pd.DataFrame:
    """Retrieve career stats for a specific player by name."""
    # 1) Normalize the season parameter
    season_norm = normalize_season(season)
    logger.debug(
        "normalize_season(%r) → %r (type=%s)", season, season_norm, type(season_norm)
    )

    # 2) Look up the player ID
    player_id = get_player_id(player_name)
    if player_id is None:
        logger.error("Player not found: %r", player_name)
        raise ValueError(f"Player not found: {player_name!r}")

    logger.debug("Found player_id=%s for '%s'", player_id, player_name)

    # 3) Fetch the raw career DataFrame
    try:
        career = playercareerstats.PlayerCareerStats(player_id=player_id)
        # The API returns multiple dataframes - we want the regular season stats
        all_dfs = career.get_data_frames()
        if not all_dfs or len(all_dfs) < 1:
            logger.error(
                "No dataframes returned from PlayerCareerStats for %s", player_name
            )
            return pd.DataFrame()  # Return empty DataFrame if no data

        career_df = all_dfs[0]  # Regular season stats

        # 4) Log available seasons in the data
        available = career_df["SEASON_ID"].unique().tolist()
        logger.debug("Available SEASON_IDs for %s: %s", player_name, available)

        # 5) Apply filtering based on season parameter
        if isinstance(season_norm, (list, tuple, set)):
            filtered = career_df[career_df["SEASON_ID"].isin(season_norm)]
            logger.debug(
                "Filtering with .isin(%r), result shape: %s",
                season_norm,
                filtered.shape,
            )

            # If no exact match found, try to find closest season
            if filtered.empty and available:
                logger.info(
                    "No exact match for %r, trying closest available season",
                    season_norm,
                )
                # Use most recent season if available
                filtered = career_df[career_df["SEASON_ID"] == available[-1]]
                logger.debug(
                    "Using closest season %s, result shape: %s",
                    available[-1] if available else "N/A",
                    filtered.shape,
                )
        else:
            filtered = career_df[
                career_df["SEASON_ID"] == season_norm[0] if season_norm else ""
            ]
            logger.debug(
                "Filtering with == %r, result shape: %s",
                season_norm[0] if season_norm else "",
                filtered.shape,
            )

            # If no exact match found, try to find closest season
            if filtered.empty and available:
                logger.info(
                    "No exact match for %r, trying closest available season",
                    season_norm,
                )
                # Use most recent season if available
                filtered = career_df[career_df["SEASON_ID"] == available[-1]]
                logger.debug(
                    "Using closest season %s, result shape: %s",
                    available[-1] if available else "N/A",
                    filtered.shape,
                )

        # Log the columns to help debug
        logger.debug(
            "Columns in filtered DataFrame: %s",
            filtered.columns.tolist() if not filtered.empty else "N/A",
        )

        # 6) Return the filtered DataFrame
        return filtered

    except Exception as e:
        logger.exception("Error fetching career stats for %s: %s", player_name, e)
        # Return empty DataFrame on error
        return pd.DataFrame()


def get_league_leaders(
    season: str,
    stat_category: str,
    per_mode: str = "Totals",
    season_type_all_star: str = "Regular Season"
) -> pd.DataFrame:
    """
    Retrieve league leaders for a specified season and statistical category.

    Args:
        season: NBA season (e.g., '2023-24')
        stat_category: Statistical category (e.g., 'PTS', 'AST')
        per_mode: Aggregation mode ('Totals', 'PerGame', 'Per48')
        season_type_all_star: Season type ('Regular Season', 'Playoffs', 'All Star')
    """
    season_norm = normalize_season(season)
    normalized_stat = normalize_stat_category(stat_category)
    normalized_mode = normalize_per_mode(per_mode)

    params = {
        "league_id": "00",
        "per_mode48": normalized_mode,
        "scope": "S",
        "season": season_norm,
        "season_type_all_star": season_type_all_star,
        "stat_category_abbreviation": normalized_stat,
        "active_flag_nullable": "",
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
        career_df = get_player_career_stats("Nikola Jokić", season)

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


if __name__ == "__main__":
    main()
