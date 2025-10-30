"""
Advanced Basketball Metrics Calculator

Implements sophisticated basketball metrics beyond basic box score stats:
- GS per 36 (Game Score per 36 minutes)
- EWA (Estimated Wins Added)
- WS (Win Shares) - Offensive and Defensive
- RAPM (Regularized Adjusted Plus-Minus) - when sufficient data available

References:
- Basketball Reference methodology for WS
- Hollinger's Game Score formula
- APBRmetrics for EWA calculations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS & FORMULAS
# ============================================================================

# League average pace (possessions per 48 minutes) by season
# Used for pace-adjusted calculations
LEAGUE_AVG_PACE = {
    "2023-24": 99.4,
    "2022-23": 99.0,
    "2021-22": 98.2,
    "2020-21": 99.2,
    "2019-20": 100.3,
    # Add more seasons as needed
}

# League average offensive rating (points per 100 possessions)
LEAGUE_AVG_ORTG = {
    "2023-24": 115.0,
    "2022-23": 114.6,
    "2021-22": 111.8,
    "2020-21": 112.4,
    "2019-20": 110.4,
}

# Default values when season not in lookup
DEFAULT_PACE = 99.0
DEFAULT_ORTG = 113.0


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class AdvancedMetrics:
    """Container for all advanced metrics"""
    player_name: str
    season: str

    # Game Score metrics
    game_score_total: float = 0.0
    game_score_per_game: float = 0.0
    game_score_per_36: float = 0.0

    # Efficiency metrics
    true_shooting_pct: float = 0.0
    effective_fg_pct: float = 0.0
    usage_rate: float = 0.0

    # Win Shares
    offensive_win_shares: float = 0.0
    defensive_win_shares: float = 0.0
    win_shares: float = 0.0
    win_shares_per_48: float = 0.0

    # Estimated Wins Added
    ewa: float = 0.0

    # Plus-Minus metrics (if available)
    rapm: Optional[float] = None
    rapm_offense: Optional[float] = None
    rapm_defense: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "PLAYER_NAME": self.player_name,
            "SEASON": self.season,
            "GAME_SCORE_TOTAL": round(self.game_score_total, 2),
            "GAME_SCORE_PER_GAME": round(self.game_score_per_game, 2),
            "GAME_SCORE_PER_36": round(self.game_score_per_36, 2),
            "TRUE_SHOOTING_PCT": round(self.true_shooting_pct, 3),
            "EFFECTIVE_FG_PCT": round(self.effective_fg_pct, 3),
            "USAGE_RATE": round(self.usage_rate, 3),
            "OFFENSIVE_WIN_SHARES": round(self.offensive_win_shares, 2),
            "DEFENSIVE_WIN_SHARES": round(self.defensive_win_shares, 2),
            "WIN_SHARES": round(self.win_shares, 2),
            "WIN_SHARES_PER_48": round(self.win_shares_per_48, 3),
            "EWA": round(self.ewa, 2),
            "RAPM": round(self.rapm, 2) if self.rapm is not None else None,
            "RAPM_OFFENSE": round(self.rapm_offense, 2) if self.rapm_offense else None,
            "RAPM_DEFENSE": round(self.rapm_defense, 2) if self.rapm_defense else None,
        }


# ============================================================================
# GAME SCORE CALCULATOR
# ============================================================================

def calculate_game_score(stats: Dict[str, float]) -> float:
    """
    Calculate John Hollinger's Game Score

    Formula:
    GS = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*OREB + 0.3*DREB
         + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV

    Args:
        stats: Dictionary with box score stats (PTS, FGM, FGA, etc.)

    Returns:
        Game Score value
    """
    pts = stats.get("PTS", 0)
    fgm = stats.get("FGM", 0)
    fga = stats.get("FGA", 0)
    ftm = stats.get("FTM", 0)
    fta = stats.get("FTA", 0)
    oreb = stats.get("OREB", 0)
    dreb = stats.get("DREB", 0)
    stl = stats.get("STL", 0)
    ast = stats.get("AST", 0)
    blk = stats.get("BLK", 0)
    pf = stats.get("PF", 0)
    tov = stats.get("TOV", 0)

    game_score = (
        pts
        + 0.4 * fgm
        - 0.7 * fga
        - 0.4 * (fta - ftm)
        + 0.7 * oreb
        + 0.3 * dreb
        + stl
        + 0.7 * ast
        + 0.7 * blk
        - 0.4 * pf
        - tov
    )

    return game_score


def calculate_game_score_per_36(stats: Dict[str, float]) -> float:
    """
    Calculate Game Score per 36 minutes

    Args:
        stats: Dictionary with totals and MIN

    Returns:
        Game Score per 36 minutes
    """
    total_gs = calculate_game_score(stats)
    minutes = stats.get("MIN", 0)

    if minutes == 0:
        return 0.0

    return (total_gs / minutes) * 36


# ============================================================================
# EFFICIENCY METRICS
# ============================================================================

def calculate_true_shooting_pct(pts: float, fga: float, fta: float) -> float:
    """
    Calculate True Shooting Percentage

    Formula: TS% = PTS / (2 * (FGA + 0.44 * FTA))

    Accounts for the value of 3-pointers and free throws
    """
    tsa = 2 * (fga + 0.44 * fta)
    if tsa == 0:
        return 0.0
    return pts / tsa


def calculate_effective_fg_pct(fgm: float, fg3m: float, fga: float) -> float:
    """
    Calculate Effective Field Goal Percentage

    Formula: eFG% = (FGM + 0.5 * FG3M) / FGA

    Adjusts for the fact that 3-pointers are worth more
    """
    if fga == 0:
        return 0.0
    return (fgm + 0.5 * fg3m) / fga


# ============================================================================
# WIN SHARES CALCULATOR
# ============================================================================

class WinSharesCalculator:
    """
    Calculate Win Shares following Basketball Reference methodology

    Win Shares = Offensive Win Shares + Defensive Win Shares

    Note: Full calculation requires team-level context
    """

    @staticmethod
    def calculate_offensive_win_shares(
        player_stats: Dict[str, float],
        team_stats: Dict[str, float],
        league_avg_ortg: float,
        season: str
    ) -> float:
        """
        Calculate Offensive Win Shares

        Simplified formula:
        OWS = (Player Points Produced - League Average) * Minutes / 48 / 30

        Args:
            player_stats: Player season totals
            team_stats: Team season totals
            league_avg_ortg: League average offensive rating
            season: Season string

        Returns:
            Offensive Win Shares
        """
        # Get player stats
        pts = player_stats.get("PTS", 0)
        fgm = player_stats.get("FGM", 0)
        fga = player_stats.get("FGA", 0)
        fg3m = player_stats.get("FG3M", 0)
        ftm = player_stats.get("FTM", 0)
        fta = player_stats.get("FTA", 0)
        orb = player_stats.get("OREB", 0)
        ast = player_stats.get("AST", 0)
        tov = player_stats.get("TOV", 0)
        minutes = player_stats.get("MIN", 0)

        if minutes == 0:
            return 0.0

        # Estimate points produced (simplified)
        # Full formula uses possession-based calculations
        points_produced = pts + 0.7 * ast - 0.5 * tov

        # Marginal offense (difference from league average)
        league_avg_per_min = league_avg_ortg / 100 / 48  # Points per minute at league avg
        marginal_offense = (points_produced - league_avg_per_min * minutes)

        # Convert to win shares (approximate)
        # Each win is worth about 30 marginal points
        ows = marginal_offense / 30

        return max(0.0, ows)  # Win shares can't be negative

    @staticmethod
    def calculate_defensive_win_shares(
        player_stats: Dict[str, float],
        team_stats: Dict[str, float],
        season: str
    ) -> float:
        """
        Calculate Defensive Win Shares

        This is highly simplified - actual DWS requires:
        - Team defensive rating
        - Player defensive rating
        - Stop percentage calculations

        Simplified approach uses defensive stats as proxy
        """
        stl = player_stats.get("STL", 0)
        blk = player_stats.get("BLK", 0)
        dreb = player_stats.get("DREB", 0)
        minutes = player_stats.get("MIN", 0)

        if minutes == 0:
            return 0.0

        # Rough estimate based on defensive contributions
        # Each steal worth ~2 points saved, block ~1.5, dreb ~0.5
        defensive_value = (2 * stl + 1.5 * blk + 0.5 * dreb)

        # Convert to win shares
        dws = defensive_value / 30

        return max(0.0, dws)

    @staticmethod
    def calculate_win_shares(
        player_stats: Dict[str, float],
        team_stats: Optional[Dict[str, float]],
        season: str
    ) -> Tuple[float, float, float]:
        """
        Calculate total Win Shares

        Returns:
            Tuple of (OWS, DWS, WS)
        """
        league_avg_ortg = LEAGUE_AVG_ORTG.get(season, DEFAULT_ORTG)

        # Calculate components
        ows = WinSharesCalculator.calculate_offensive_win_shares(
            player_stats,
            team_stats or {},
            league_avg_ortg,
            season
        )

        dws = WinSharesCalculator.calculate_defensive_win_shares(
            player_stats,
            team_stats or {},
            season
        )

        ws = ows + dws

        return ows, dws, ws


# ============================================================================
# ESTIMATED WINS ADDED (EWA)
# ============================================================================

def calculate_ewa(player_stats: Dict[str, float], season: str) -> float:
    """
    Calculate Estimated Wins Added (EWA)

    Simplified formula based on PER and minutes played
    EWA ≈ (PER - 15) * (MIN / 48) / 30

    Where:
    - PER = Player Efficiency Rating (need to calculate or have available)
    - 15 = League average PER
    - 30 = Marginal points per win

    Args:
        player_stats: Player season totals
        season: Season string

    Returns:
        Estimated Wins Added
    """
    # For now, use a simplified approach without full PER calculation
    # Use Game Score as a proxy for player value
    gs_total = calculate_game_score(player_stats)
    minutes = player_stats.get("MIN", 0)

    if minutes == 0:
        return 0.0

    # Estimate value above replacement
    # Average player contributes about 10 GS per game (15 per 36 min)
    avg_gs_per_min = 15 / 36
    replacement_value = avg_gs_per_min * minutes

    value_above_replacement = gs_total - replacement_value

    # Convert to wins (rough estimate: 30 marginal GS points per win)
    ewa = value_above_replacement / 30

    return ewa


# ============================================================================
# MAIN CALCULATOR CLASS
# ============================================================================

class AdvancedMetricsCalculator:
    """
    Main calculator for all advanced metrics

    Usage:
        calculator = AdvancedMetricsCalculator()
        metrics = await calculator.calculate_all_metrics(player_name, season)
    """

    async def calculate_all_metrics(
        self,
        player_name: str,
        season: str,
        player_stats: Optional[Dict[str, float]] = None,
        team_stats: Optional[Dict[str, float]] = None
    ) -> AdvancedMetrics:
        """
        Calculate all advanced metrics for a player

        Args:
            player_name: Player name
            season: Season in YYYY-YY format
            player_stats: Player season totals (if not provided, will fetch)
            team_stats: Team season totals (optional, improves WS accuracy)

        Returns:
            AdvancedMetrics object with all calculated metrics
        """
        # Fetch player stats if not provided
        if player_stats is None:
            player_stats = await self._fetch_player_season_stats(player_name, season)

        # Initialize metrics container
        metrics = AdvancedMetrics(
            player_name=player_name,
            season=season
        )

        # Calculate Game Score metrics
        metrics.game_score_total = calculate_game_score(player_stats)

        games_played = player_stats.get("GP", 1)
        minutes = player_stats.get("MIN", 0)

        if games_played > 0:
            metrics.game_score_per_game = metrics.game_score_total / games_played

        if minutes > 0:
            metrics.game_score_per_36 = (metrics.game_score_total / minutes) * 36

        # Calculate efficiency metrics
        metrics.true_shooting_pct = calculate_true_shooting_pct(
            player_stats.get("PTS", 0),
            player_stats.get("FGA", 0),
            player_stats.get("FTA", 0)
        )

        metrics.effective_fg_pct = calculate_effective_fg_pct(
            player_stats.get("FGM", 0),
            player_stats.get("FG3M", 0),
            player_stats.get("FGA", 0)
        )

        # Calculate Win Shares
        ws_calc = WinSharesCalculator()
        ows, dws, ws = ws_calc.calculate_win_shares(player_stats, team_stats, season)

        metrics.offensive_win_shares = ows
        metrics.defensive_win_shares = dws
        metrics.win_shares = ws

        if minutes > 0:
            metrics.win_shares_per_48 = (ws / minutes) * 48

        # Calculate EWA
        metrics.ewa = calculate_ewa(player_stats, season)

        # RAPM requires multi-year play-by-play data - mark as unavailable for now
        metrics.rapm = None
        metrics.rapm_offense = None
        metrics.rapm_defense = None

        logger.info(
            f"Calculated advanced metrics for {player_name} ({season}): "
            f"GS/36={metrics.game_score_per_36:.1f}, WS={metrics.win_shares:.1f}, EWA={metrics.ewa:.1f}"
        )

        return metrics

    async def _fetch_player_season_stats(
        self,
        player_name: str,
        season: str
    ) -> Dict[str, float]:
        """
        Fetch player season totals from season aggregator

        Args:
            player_name: Player name
            season: Season in YYYY-YY format

        Returns:
            Dictionary with season totals
        """
        from nba_mcp.api.entity_resolver import resolve_entity
        from nba_mcp.api.season_aggregator import get_player_season_stats

        # Resolve player to ID
        player_entity = resolve_entity(player_name, entity_type="player")

        # Fetch season stats
        stats_dict = await get_player_season_stats(
            season=season,
            player_id=player_entity.entity_id
        )

        return stats_dict


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def get_advanced_metrics(
    player_name: str,
    season: str,
    metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get advanced metrics for a player

    Args:
        player_name: Player name
        season: Season in YYYY-YY format
        metrics: Optional list of specific metrics to calculate
                 (default: all metrics)

    Returns:
        Dictionary with calculated metrics

    Example:
        metrics = await get_advanced_metrics("LeBron James", "2023-24")
        print(f"Win Shares: {metrics['WIN_SHARES']}")
    """
    calculator = AdvancedMetricsCalculator()
    result = await calculator.calculate_all_metrics(player_name, season)

    # If specific metrics requested, filter
    if metrics:
        full_dict = result.to_dict()
        return {k: v for k, v in full_dict.items() if k in metrics}

    return result.to_dict()
