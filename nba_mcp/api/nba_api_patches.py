"""
Monkey patches for nba_api library bugs.

This module patches known issues in the nba_api library to make it more robust.
Import this module before using nba_api endpoints.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def patch_scoreboardv2():
    """
    Patch ScoreboardV2 to handle missing WinProbability dataset.

    Issue: NBA API sometimes doesn't return WinProbability in the response,
    but nba_api expects it to always be present (line 190 of scoreboardv2.py).

    This causes KeyError: 'WinProbability' for certain games/dates.

    Fix: Make win_probability field optional - set to None if missing.
    """
    try:
        from nba_api.stats.endpoints import scoreboardv2
        from nba_api.stats.library.http import NBAStatsHTTP

        # Save the original load_response method
        original_load_response = scoreboardv2.ScoreboardV2.load_response

        def patched_load_response(self):
            """Patched version that handles missing WinProbability."""
            # Get the data sets from the response
            data_sets = self.nba_response.get_data_sets()

            # IMPORTANT: Create the data_sets list (required by base class)
            self.data_sets = [
                scoreboardv2.Endpoint.DataSet(data=data_set)
                for data_set_name, data_set in data_sets.items()
            ]

            # Load all the standard datasets
            self.available = scoreboardv2.Endpoint.DataSet(data=data_sets["Available"])
            self.east_conf_standings_by_day = scoreboardv2.Endpoint.DataSet(
                data=data_sets["EastConfStandingsByDay"]
            )
            self.game_header = scoreboardv2.Endpoint.DataSet(data=data_sets["GameHeader"])
            self.last_meeting = scoreboardv2.Endpoint.DataSet(data=data_sets["LastMeeting"])
            self.line_score = scoreboardv2.Endpoint.DataSet(data=data_sets["LineScore"])
            self.series_standings = scoreboardv2.Endpoint.DataSet(
                data=data_sets["SeriesStandings"]
            )
            self.team_leaders = scoreboardv2.Endpoint.DataSet(data=data_sets["TeamLeaders"])
            self.ticket_links = scoreboardv2.Endpoint.DataSet(data=data_sets["TicketLinks"])
            self.west_conf_standings_by_day = scoreboardv2.Endpoint.DataSet(
                data=data_sets["WestConfStandingsByDay"]
            )

            # PATCHED: Make WinProbability optional
            if "WinProbability" in data_sets:
                self.win_probability = scoreboardv2.Endpoint.DataSet(
                    data=data_sets["WinProbability"]
                )
            else:
                # WinProbability not in response - set to None
                logger.debug(
                    "[PATCH] WinProbability dataset missing from ScoreboardV2 response - "
                    "setting to None"
                )
                self.win_probability = None

        # Apply the patch
        scoreboardv2.ScoreboardV2.load_response = patched_load_response

        logger.info("✓ Applied patch: ScoreboardV2.load_response (WinProbability optional)")
        return True

    except Exception as e:
        logger.error(f"Failed to patch ScoreboardV2: {e}")
        return False


def apply_all_patches():
    """
    Apply all nba_api patches.

    Call this once at module initialization to apply all known fixes.
    """
    patches_applied = []
    patches_failed = []

    # Patch 1: ScoreboardV2 WinProbability
    if patch_scoreboardv2():
        patches_applied.append("ScoreboardV2.WinProbability")
    else:
        patches_failed.append("ScoreboardV2.WinProbability")

    # Log summary
    if patches_applied:
        logger.info(f"NBA API patches applied: {', '.join(patches_applied)}")
    if patches_failed:
        logger.warning(f"NBA API patches failed: {', '.join(patches_failed)}")

    return len(patches_failed) == 0
