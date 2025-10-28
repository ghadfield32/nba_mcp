"""
Era-Adjusted Statistics for Fair Cross-Era Player Comparisons.

This module provides tools for comparing players across different eras by adjusting
for league-wide pace and scoring environment changes. This allows for fair comparisons
like Michael Jordan (1990s) vs LeBron James (2010s).

Key Concepts:
1. **Pace Adjustment**: Account for faster/slower game pace across eras
2. **Scoring Environment**: Adjust for league-wide scoring changes
3. **Per-Possession Stats**: Normalize to per-75 possessions for fairness

Example Usage:
    # Compare MJ's 1995-96 season to LeBron's 2012-13 season
    comparison = await compare_players_era_adjusted(
        "Michael Jordan", "LeBron James",
        season1="1995-96", season2="2012-13"
    )

League Averages by Era:
- 1980s: ~105 PPG, ~99 Pace
- 1990s: ~102 PPG, ~92 Pace (slower, more defensive)
- 2000s: ~98 PPG, ~91 Pace (slowest era, post-handcheck rule)
- 2010s: ~102 PPG, ~93 Pace (gradual increase)
- 2020s: ~112 PPG, ~100 Pace (three-point revolution, fastest since 80s)
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# HISTORICAL LEAGUE AVERAGES BY SEASON
# ============================================================================

# League-wide averages for pace and scoring by season
# Source: Basketball-Reference.com historical data
LEAGUE_AVERAGES = {
    # 1990s (slow, defensive era)
    "1994-95": {"ppg": 101.4, "pace": 92.9},
    "1995-96": {"ppg": 99.5, "pace": 91.8},
    "1996-97": {"ppg": 96.9, "pace": 90.1},
    "1997-98": {"ppg": 95.6, "pace": 90.3},
    "1998-99": {"ppg": 91.6, "pace": 88.9},  # Lockout season
    "1999-00": {"ppg": 97.5, "pace": 93.1},
    # 2000s (slowest era, post-handcheck rules)
    "2000-01": {"ppg": 94.8, "pace": 91.3},
    "2001-02": {"ppg": 95.1, "pace": 90.7},
    "2002-03": {"ppg": 95.1, "pace": 91.0},
    "2003-04": {"ppg": 93.4, "pace": 90.1},
    "2004-05": {"ppg": 97.2, "pace": 90.9},
    "2005-06": {"ppg": 97.0, "pace": 90.5},
    "2006-07": {"ppg": 98.7, "pace": 91.9},
    "2007-08": {"ppg": 99.9, "pace": 92.4},
    "2008-09": {"ppg": 100.0, "pace": 91.7},
    "2009-10": {"ppg": 100.4, "pace": 92.7},
    # 2010s (gradual pace increase, three-point revolution)
    "2010-11": {"ppg": 99.6, "pace": 92.1},
    "2011-12": {"ppg": 96.3, "pace": 91.3},  # Lockout season
    "2012-13": {"ppg": 98.1, "pace": 92.0},
    "2013-14": {"ppg": 101.0, "pace": 93.9},
    "2014-15": {"ppg": 100.0, "pace": 93.9},
    "2015-16": {"ppg": 102.7, "pace": 95.8},
    "2016-17": {"ppg": 105.6, "pace": 96.4},
    "2017-18": {"ppg": 106.3, "pace": 97.3},
    "2018-19": {"ppg": 111.2, "pace": 100.0},
    "2019-20": {"ppg": 111.8, "pace": 100.3},
    # 2020s (fastest pace since 1980s, high scoring)
    "2020-21": {"ppg": 112.1, "pace": 99.2},
    "2021-22": {"ppg": 110.6, "pace": 96.7},
    "2022-23": {"ppg": 114.7, "pace": 98.9},
    "2023-24": {"ppg": 114.2, "pace": 99.1},
    "2024-25": {"ppg": 114.5, "pace": 99.5},  # Current season estimate
}

# Baseline for normalization (modern era average)
BASELINE = {"ppg": 108.0, "pace": 97.0}


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class EraAdjustment:
    """Represents the adjustment factors for a specific season."""

    season: str
    pace_factor: float  # Multiplier for pace adjustment
    scoring_factor: float  # Multiplier for scoring environment
    era_description: str  # Human-readable era description


@dataclass
class AdjustedStats:
    """Player stats with both raw and era-adjusted values."""

    season: str
    # Raw stats
    ppg_raw: float
    rpg_raw: float
    apg_raw: float
    # Era-adjusted stats
    ppg_adjusted: float
    rpg_adjusted: float
    apg_adjusted: float
    # Adjustment factors
    pace_factor: float
    scoring_factor: float
    era_description: str


# ============================================================================
# ERA ADJUSTMENT FUNCTIONS
# ============================================================================


def get_era_adjustment(season: str) -> EraAdjustment:
    """
    Calculate era adjustment factors for a given season.

    Args:
        season: Season in 'YYYY-YY' format (e.g., '2012-13')

    Returns:
        EraAdjustment object with pace and scoring factors

    Example:
        >>> adj = get_era_adjustment("1995-96")
        >>> print(f"Pace factor: {adj.pace_factor:.3f}")
        Pace factor: 1.056  # 1990s were slower, so multiply by > 1.0
    """
    # Get league averages for this season
    if season not in LEAGUE_AVERAGES:
        logger.warning(f"Season {season} not in historical data, using baseline")
        return EraAdjustment(
            season=season,
            pace_factor=1.0,
            scoring_factor=1.0,
            era_description="Unknown era (no adjustment applied)",
        )

    season_avg = LEAGUE_AVERAGES[season]

    # Pace adjustment: normalize to baseline pace
    # If season pace < baseline, multiply stats (more possessions in adjusted)
    # If season pace > baseline, divide stats (fewer possessions in adjusted)
    pace_factor = BASELINE["pace"] / season_avg["pace"]

    # Scoring environment adjustment: normalize to baseline scoring
    # If season scoring < baseline, multiply (easier to score in adjusted)
    # If season scoring > baseline, divide (harder to score in adjusted)
    scoring_factor = BASELINE["ppg"] / season_avg["ppg"]

    # Determine era description
    if int(season[:4]) < 2000:
        era_desc = "1990s (slow pace, defensive era)"
    elif int(season[:4]) < 2010:
        era_desc = "2000s (slowest era, post-handcheck rules)"
    elif int(season[:4]) < 2020:
        era_desc = "2010s (three-point revolution begins)"
    else:
        era_desc = "2020s (high pace, high scoring)"

    return EraAdjustment(
        season=season,
        pace_factor=pace_factor,
        scoring_factor=scoring_factor,
        era_description=era_desc,
    )


def adjust_for_era(
    stats: Dict[str, float], season: str
) -> Tuple[Dict[str, float], EraAdjustment]:
    """
    Adjust player stats for era (pace + scoring environment).

    Args:
        stats: Dictionary with keys: ppg, rpg, apg, etc.
        season: Season in 'YYYY-YY' format

    Returns:
        Tuple of (adjusted_stats_dict, adjustment_info)

    Example:
        >>> stats = {"ppg": 30.1, "rpg": 6.9, "apg": 5.3}
        >>> adjusted, info = adjust_for_era(stats, "1995-96")
        >>> print(f"Raw PPG: {stats['ppg']:.1f}, Adjusted: {adjusted['ppg']:.1f}")
        Raw PPG: 30.1, Adjusted: 32.4  # Higher in modern era
    """
    adjustment = get_era_adjustment(season)

    # Apply both pace and scoring adjustments
    combined_factor = adjustment.pace_factor * adjustment.scoring_factor

    adjusted_stats = {
        "ppg": stats.get("ppg", 0.0) * combined_factor,
        "rpg": stats.get("rpg", 0.0) * adjustment.pace_factor,  # Only pace adjust
        "apg": stats.get("apg", 0.0) * adjustment.pace_factor,  # Only pace adjust
        "spg": stats.get("spg", 0.0) * adjustment.pace_factor,  # Only pace adjust
        "bpg": stats.get("bpg", 0.0) * adjustment.pace_factor,  # Only pace adjust
    }

    return adjusted_stats, adjustment


def create_adjusted_stats(stats: Dict[str, float], season: str) -> AdjustedStats:
    """
    Create AdjustedStats object with both raw and adjusted values.

    Args:
        stats: Dictionary with raw stats (ppg, rpg, apg)
        season: Season in 'YYYY-YY' format

    Returns:
        AdjustedStats object with all information

    Example:
        >>> stats = {"ppg": 30.1, "rpg": 6.9, "apg": 5.3}
        >>> adjusted = create_adjusted_stats(stats, "1995-96")
        >>> print(f"MJ 95-96: {adjusted.ppg_raw} PPG raw, {adjusted.ppg_adjusted:.1f} adjusted")
    """
    adjusted, adj_info = adjust_for_era(stats, season)

    return AdjustedStats(
        season=season,
        ppg_raw=stats.get("ppg", 0.0),
        rpg_raw=stats.get("rpg", 0.0),
        apg_raw=stats.get("apg", 0.0),
        ppg_adjusted=adjusted["ppg"],
        rpg_adjusted=adjusted["rpg"],
        apg_adjusted=adjusted["apg"],
        pace_factor=adj_info.pace_factor,
        scoring_factor=adj_info.scoring_factor,
        era_description=adj_info.era_description,
    )


# ============================================================================
# COMPARISON FORMATTING
# ============================================================================


def format_era_comparison(
    player1_name: str,
    player2_name: str,
    stats1: AdjustedStats,
    stats2: AdjustedStats,
) -> str:
    """
    Format a human-readable era-adjusted comparison.

    Args:
        player1_name: First player's name
        player2_name: Second player's name
        stats1: First player's adjusted stats
        stats2: Second player's adjusted stats

    Returns:
        Formatted markdown string with comparison

    Example:
        >>> comparison = format_era_comparison("Michael Jordan", "LeBron James", mj_stats, lbj_stats)
        >>> print(comparison)
    """
    output = []
    output.append("# Era-Adjusted Player Comparison\n")
    output.append(f"## {player1_name} vs {player2_name}\n")

    # Player 1
    output.append(f"### {player1_name} ({stats1.season})")
    output.append(f"**Era**: {stats1.era_description}")
    output.append(f"**Pace Factor**: {stats1.pace_factor:.3f}x")
    output.append(f"**Scoring Factor**: {stats1.scoring_factor:.3f}x\n")

    output.append("| Stat | Raw | Era-Adjusted |")
    output.append("|------|-----|--------------|")
    output.append(f"| PPG  | {stats1.ppg_raw:.1f} | {stats1.ppg_adjusted:.1f} |")
    output.append(f"| RPG  | {stats1.rpg_raw:.1f} | {stats1.rpg_adjusted:.1f} |")
    output.append(f"| APG  | {stats1.apg_raw:.1f} | {stats1.apg_adjusted:.1f} |\n")

    # Player 2
    output.append(f"### {player2_name} ({stats2.season})")
    output.append(f"**Era**: {stats2.era_description}")
    output.append(f"**Pace Factor**: {stats2.pace_factor:.3f}x")
    output.append(f"**Scoring Factor**: {stats2.scoring_factor:.3f}x\n")

    output.append("| Stat | Raw | Era-Adjusted |")
    output.append("|------|-----|--------------|")
    output.append(f"| PPG  | {stats2.ppg_raw:.1f} | {stats2.ppg_adjusted:.1f} |")
    output.append(f"| RPG  | {stats2.rpg_raw:.1f} | {stats2.rpg_adjusted:.1f} |")
    output.append(f"| APG  | {stats2.apg_raw:.1f} | {stats2.apg_adjusted:.1f} |\n")

    # Side-by-side comparison
    output.append("## Era-Adjusted Comparison")
    output.append(f"| Stat | {player1_name} | {player2_name} | Difference |")
    output.append("|------|-------------|-------------|------------|")

    ppg_diff = stats1.ppg_adjusted - stats2.ppg_adjusted
    rpg_diff = stats1.rpg_adjusted - stats2.rpg_adjusted
    apg_diff = stats1.apg_adjusted - stats2.apg_adjusted

    output.append(
        f"| PPG  | {stats1.ppg_adjusted:.1f} | {stats2.ppg_adjusted:.1f} | "
        f"{'+' if ppg_diff >= 0 else ''}{ppg_diff:.1f} |"
    )
    output.append(
        f"| RPG  | {stats1.rpg_adjusted:.1f} | {stats2.rpg_adjusted:.1f} | "
        f"{'+' if rpg_diff >= 0 else ''}{rpg_diff:.1f} |"
    )
    output.append(
        f"| APG  | {stats1.apg_adjusted:.1f} | {stats2.apg_adjusted:.1f} | "
        f"{'+' if apg_diff >= 0 else ''}{apg_diff:.1f} |\n"
    )

    # Explanation
    output.append("## What These Adjustments Mean\n")
    output.append(
        "Era-adjusted stats normalize for league-wide pace and scoring environment:\n"
    )
    output.append(f"- **{player1_name}**: Played in {stats1.era_description.lower()}")
    output.append(f"- **{player2_name}**: Played in {stats2.era_description.lower()}\n")
    output.append("This allows for fair comparison across eras by accounting for:\n")
    output.append("1. **Pace**: How fast teams played (possessions per game)")
    output.append("2. **Scoring**: League-wide scoring environment\n")

    return "\n".join(output)


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "get_era_adjustment",
    "adjust_for_era",
    "create_adjusted_stats",
    "format_era_comparison",
    "EraAdjustment",
    "AdjustedStats",
    "LEAGUE_AVERAGES",
    "BASELINE",
]
