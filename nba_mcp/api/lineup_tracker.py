"""
Lineup Tracking for Play-by-Play Data

Tracks player substitutions and maintains lineup state throughout NBA games.
Adds CURRENT_LINEUP_HOME and CURRENT_LINEUP_AWAY columns to each play-by-play event.

Key Features:
- Parses substitution events (EVENT_TYPE = 8)
- Maintains 5-player lineup state for home/away teams
- Handles edge cases (starting lineups, overtime, missing data)
- Links lineups to LeagueDashLineups for advanced stats correlation
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Lineup:
    """Represents a 5-player lineup"""
    player_ids: List[int] = field(default_factory=list)
    player_names: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Ensure lineup is sorted for consistent comparison"""
        if self.player_ids:
            # Sort by player_id to ensure consistent ordering
            paired = list(zip(self.player_ids, self.player_names))
            paired_sorted = sorted(paired, key=lambda x: x[0])
            self.player_ids, self.player_names = zip(*paired_sorted) if paired_sorted else ([], [])
            self.player_ids = list(self.player_ids)
            self.player_names = list(self.player_names)

    @property
    def lineup_id(self) -> str:
        """
        Generate lineup ID in NBA API format

        Format: "-PLAYERID1-PLAYERID2-PLAYERID3-PLAYERID4-PLAYERID5-"
        Example: "-1626157-1628384-1628404-1628969-1628973-"
        """
        if not self.player_ids:
            return ""
        return "-" + "-".join(str(pid) for pid in sorted(self.player_ids)) + "-"

    @property
    def lineup_display(self) -> str:
        """
        Generate human-readable lineup string

        Format: "Player1 - Player2 - Player3 - Player4 - Player5"
        """
        if not self.player_names:
            return ""
        # Use last names only for compactness
        last_names = [name.split()[-1] if " " in name else name for name in self.player_names]
        return " - ".join(last_names)

    def add_player(self, player_id: int, player_name: str):
        """Add a player to the lineup"""
        if player_id not in self.player_ids:
            self.player_ids.append(player_id)
            self.player_names.append(player_name)
            self.__post_init__()  # Re-sort

    def remove_player(self, player_id: int):
        """Remove a player from the lineup"""
        if player_id in self.player_ids:
            idx = self.player_ids.index(player_id)
            self.player_ids.pop(idx)
            self.player_names.pop(idx)

    def substitute(self, out_player_id: int, in_player_id: int, in_player_name: str):
        """Replace one player with another"""
        self.remove_player(out_player_id)
        self.add_player(in_player_id, in_player_name)

    def is_valid(self) -> bool:
        """Check if lineup has exactly 5 players"""
        return len(self.player_ids) == 5

    def copy(self) -> Lineup:
        """Create a copy of this lineup"""
        return Lineup(
            player_ids=self.player_ids.copy(),
            player_names=self.player_names.copy()
        )


@dataclass
class LineupState:
    """Tracks current lineups for both teams"""
    home_lineup: Lineup = field(default_factory=Lineup)
    away_lineup: Lineup = field(default_factory=Lineup)
    period: int = 0
    event_num: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DataFrame attachment"""
        return {
            "CURRENT_LINEUP_HOME": self.home_lineup.player_names,
            "CURRENT_LINEUP_AWAY": self.away_lineup.player_names,
            "CURRENT_LINEUP_HOME_IDS": self.home_lineup.player_ids,
            "CURRENT_LINEUP_AWAY_IDS": self.away_lineup.player_ids,
            "LINEUP_ID_HOME": self.home_lineup.lineup_id,
            "LINEUP_ID_AWAY": self.away_lineup.lineup_id,
            "LINEUP_DISPLAY_HOME": self.home_lineup.lineup_display,
            "LINEUP_DISPLAY_AWAY": self.away_lineup.lineup_display,
        }


# ============================================================================
# LINEUP TRACKER
# ============================================================================

class LineupTracker:
    """
    Tracks lineups throughout a game's play-by-play

    Maintains lineup state by:
    1. Initializing from starting lineups (period 1, first events)
    2. Processing substitution events (EVENT_TYPE = 8)
    3. Attaching current lineup to each event
    """

    def __init__(self, game_id: str):
        self.game_id = game_id
        self.state = LineupState()
        self.home_team_id: Optional[int] = None
        self.away_team_id: Optional[int] = None

        # Track substitution history for debugging
        self.substitution_log: List[Dict[str, Any]] = []

    def process_play_by_play(self, pbp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Process play-by-play DataFrame and add lineup columns

        Args:
            pbp_df: Play-by-play DataFrame from PlayByPlayV3

        Returns:
            Enhanced DataFrame with lineup columns added
        """
        if pbp_df.empty:
            logger.warning(f"Empty play-by-play DataFrame for game {self.game_id}")
            return pbp_df

        # Normalize column names to lowercase for consistent access
        # NBA API V3 returns mixed case columns
        pbp_df = pbp_df.copy()
        pbp_df.columns = [col.lower() if isinstance(col, str) else col for col in pbp_df.columns]

        # Ensure required columns exist
        required_cols = ["period", "actiontype", "teamid"]
        missing = [col for col in required_cols if col not in pbp_df.columns]
        if missing:
            logger.error(f"Missing required columns in play-by-play: {missing}")
            logger.debug(f"Available columns: {list(pbp_df.columns)}")
            # Add empty lineup columns
            return self._add_empty_lineup_columns(pbp_df)

        # Initialize team IDs from first events
        self._initialize_team_ids(pbp_df)

        # Initialize starting lineups (first 5 players in period 1)
        self._initialize_starting_lineups(pbp_df)

        # Process each event and track lineups
        lineup_data = []
        for idx, row in pbp_df.iterrows():
            # Update state for current event
            self.state.period = row.get("period", 0)
            self.state.event_num = row.get("actionnumber", 0)

            # Check if this is a substitution event
            if self._is_substitution(row):
                self._process_substitution(row)

            # Attach current lineup state to this event
            lineup_data.append(self.state.to_dict())

        # Convert lineup data to DataFrame and merge
        lineup_df = pd.DataFrame(lineup_data)
        result_df = pd.concat([pbp_df.reset_index(drop=True), lineup_df], axis=1)

        logger.info(
            f"Processed {len(pbp_df)} events for game {self.game_id}, "
            f"tracked {len(self.substitution_log)} substitutions"
        )

        return result_df

    def _initialize_team_ids(self, pbp_df: pd.DataFrame):
        """Extract home and away team IDs from play-by-play data"""
        # Look for team IDs in first few events (columns are lowercase now)
        for _, row in pbp_df.head(20).iterrows():
            team_id = row.get("teamid")
            if pd.notna(team_id):
                team_id = int(team_id)
                # Determine if home or away (heuristic: home team ID usually appears first in opening tip)
                # This is a simplification - ideally we'd use box score metadata
                if self.home_team_id is None:
                    self.home_team_id = team_id
                elif team_id != self.home_team_id and self.away_team_id is None:
                    self.away_team_id = team_id

        logger.debug(f"Identified teams: home={self.home_team_id}, away={self.away_team_id}")

    def _initialize_starting_lineups(self, pbp_df: pd.DataFrame):
        """
        Extract starting lineups from first period events

        Starting lineup is typically the first 5 unique players per team
        who appear in period 1 events (excluding bench players)
        """
        period_1 = pbp_df[pbp_df["period"] == 1]

        home_starters = set()
        away_starters = set()

        for _, row in period_1.iterrows():
            team_id = row.get("teamid")
            player_id = row.get("personid")
            player_name = row.get("playername") or row.get("playernamei", "")

            if pd.isna(team_id) or pd.isna(player_id):
                continue

            team_id = int(team_id)
            player_id = int(player_id)

            # Collect starters (first 5 players per team)
            if team_id == self.home_team_id and len(home_starters) < 5:
                home_starters.add((player_id, player_name))
            elif team_id == self.away_team_id and len(away_starters) < 5:
                away_starters.add((player_id, player_name))

            # Stop once we have 5 starters for both teams
            if len(home_starters) >= 5 and len(away_starters) >= 5:
                break

        # Initialize lineups
        for player_id, player_name in home_starters:
            self.state.home_lineup.add_player(player_id, player_name)

        for player_id, player_name in away_starters:
            self.state.away_lineup.add_player(player_id, player_name)

        logger.info(
            f"Initialized starting lineups: "
            f"home={self.state.home_lineup.lineup_display}, "
            f"away={self.state.away_lineup.lineup_display}"
        )

    def _is_substitution(self, row: pd.Series) -> bool:
        """Check if event is a substitution"""
        # EVENT_TYPE = 8 is substitution in NBA API
        # actiontype might also be "substitution" (columns are lowercase now)
        action_type = row.get("actiontype", "")
        if isinstance(action_type, str) and "substitut" in action_type.lower():
            return True

        # Check numeric event type
        event_type = row.get("eventtype")
        if pd.notna(event_type) and int(event_type) == 8:
            return True

        # Check description for "SUB:"
        description = row.get("description", "")
        if isinstance(description, str) and "SUB:" in description.upper():
            return True

        return False

    def _process_substitution(self, row: pd.Series):
        """
        Process a substitution event

        NBA API substitution format:
        - description: "SUB: Player IN for Player OUT"
        - OR separate fields for subType, personId (in), etc.
        """
        description = row.get("description", "")
        team_id = int(row.get("teamid", 0)) if pd.notna(row.get("teamid")) else 0

        # Determine which team this substitution affects
        is_home = team_id == self.home_team_id
        current_lineup = self.state.home_lineup if is_home else self.state.away_lineup

        # Parse substitution from description
        # Format examples:
        #   "SUB: Smith IN for Jones"
        #   "Smith enters for Jones"
        in_player_id = int(row.get("personid", 0)) if pd.notna(row.get("personid")) else 0
        in_player_name = row.get("playername") or row.get("playernamei", "")

        # Try to extract OUT player from description
        out_player_id = None
        out_pattern = re.search(r"for\s+(.+?)(?:\s|$)", description, re.IGNORECASE)
        if out_pattern:
            out_player_name = out_pattern.group(1).strip()
            # Find this player in current lineup
            for pid, pname in zip(current_lineup.player_ids, current_lineup.player_names):
                if out_player_name.lower() in pname.lower() or pname.lower() in out_player_name.lower():
                    out_player_id = pid
                    break

        # Perform substitution if we have both players
        if in_player_id and out_player_id:
            current_lineup.substitute(out_player_id, in_player_id, in_player_name)

            self.substitution_log.append({
                "period": self.state.period,
                "event_num": self.state.event_num,
                "team_id": team_id,
                "in_player": in_player_name,
                "out_player": out_player_name if out_pattern else "Unknown",
                "description": description
            })

            logger.debug(
                f"Substitution: {in_player_name} IN for {out_player_name} "
                f"(team={team_id}, period={self.state.period})"
            )
        else:
            logger.warning(
                f"Could not parse substitution: {description} "
                f"(in={in_player_id}, out={out_player_id})"
            )

    def _add_empty_lineup_columns(self, pbp_df: pd.DataFrame) -> pd.DataFrame:
        """Add empty lineup columns when tracking fails"""
        pbp_df["CURRENT_LINEUP_HOME"] = None
        pbp_df["CURRENT_LINEUP_AWAY"] = None
        pbp_df["CURRENT_LINEUP_HOME_IDS"] = None
        pbp_df["CURRENT_LINEUP_AWAY_IDS"] = None
        pbp_df["LINEUP_ID_HOME"] = ""
        pbp_df["LINEUP_ID_AWAY"] = ""
        pbp_df["LINEUP_DISPLAY_HOME"] = ""
        pbp_df["LINEUP_DISPLAY_AWAY"] = ""
        return pbp_df

    def get_substitution_summary(self) -> pd.DataFrame:
        """Get summary of all substitutions tracked"""
        if not self.substitution_log:
            return pd.DataFrame()
        return pd.DataFrame(self.substitution_log)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def add_lineups_to_play_by_play(
    pbp_df: pd.DataFrame,
    game_id: str
) -> pd.DataFrame:
    """
    Add lineup tracking columns to play-by-play DataFrame

    Args:
        pbp_df: Play-by-play DataFrame (from PlayByPlayV3)
        game_id: NBA game ID

    Returns:
        Enhanced DataFrame with lineup columns:
        - CURRENT_LINEUP_HOME: List of player names
        - CURRENT_LINEUP_AWAY: List of player names
        - CURRENT_LINEUP_HOME_IDS: List of player IDs
        - CURRENT_LINEUP_AWAY_IDS: List of player IDs
        - LINEUP_ID_HOME: Lineup ID string (NBA API format)
        - LINEUP_ID_AWAY: Lineup ID string
        - LINEUP_DISPLAY_HOME: Human-readable lineup
        - LINEUP_DISPLAY_AWAY: Human-readable lineup

    Example:
        from nba_api.stats.endpoints import PlayByPlayV3
        result = PlayByPlayV3(game_id="0022300001")
        pbp_df = result.get_data_frames()[0]

        # Add lineup tracking
        pbp_with_lineups = add_lineups_to_play_by_play(pbp_df, "0022300001")

        # Access lineup data
        first_lineup_home = pbp_with_lineups.iloc[0]["CURRENT_LINEUP_HOME"]
        print(f"Home lineup: {first_lineup_home}")
    """
    tracker = LineupTracker(game_id)
    return tracker.process_play_by_play(pbp_df)


async def get_play_by_play_with_lineups(
    game_id: str,
    start_period: int = 1,
    end_period: int = 10
) -> pd.DataFrame:
    """
    Fetch play-by-play data with lineup tracking

    Args:
        game_id: NBA game ID
        start_period: Starting period (default: 1)
        end_period: Ending period (default: 10 for OT)

    Returns:
        DataFrame with play-by-play events and lineup data

    Example:
        df = await get_play_by_play_with_lineups("0022300001")
        print(df[["period", "clock", "description", "LINEUP_DISPLAY_HOME", "LINEUP_DISPLAY_AWAY"]].head())
    """
    from nba_api.stats.endpoints import PlayByPlayV3

    logger.info(f"Fetching play-by-play with lineups for game {game_id}")

    # Fetch play-by-play
    result = PlayByPlayV3(
        game_id=game_id,
        start_period=start_period,
        end_period=end_period
    )
    pbp_df = result.get_data_frames()[0]  # [0] is PlayByPlay, [1] is AvailableVideo

    # Add lineup tracking
    pbp_with_lineups = add_lineups_to_play_by_play(pbp_df, game_id)

    return pbp_with_lineups
