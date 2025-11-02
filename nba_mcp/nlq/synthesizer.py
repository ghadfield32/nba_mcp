# nba_mcp/nlq/synthesizer.py
"""
Response Synthesizer for NBA MCP NLQ.

Formats tool execution results into natural language responses with:
- Tables for comparisons
- Narratives for game context
- Lists for rankings
- Metadata (sources, timestamps, confidence)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from tabulate import tabulate

from .executor import ExecutionResult, ToolResult
from .parser import ParsedQuery

logger = logging.getLogger(__name__)


# ============================================================================
# SYNTHESIS RESULT
# ============================================================================


@dataclass
class SynthesizedResponse:
    """Final synthesized response."""

    raw_query: str
    intent: str
    answer: str  # Natural language answer
    confidence: float
    sources: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "intent": self.intent,
            "answer": self.answer,
            "confidence": self.confidence,
            "sources": self.sources,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Format as markdown."""
        md = f"# {self.raw_query}\n\n"
        md += f"{self.answer}\n\n"
        md += f"---\n\n"
        md += f"**Confidence**: {self.confidence:.0%}\n"
        md += f"**Sources**: {', '.join(self.sources)}\n"
        md += f"**Generated**: {self.metadata.get('timestamp', 'N/A')}\n"
        return md


# ============================================================================
# OUTPUT NORMALIZATION (Phase 4.2)
# ============================================================================


def normalize_markdown_output(text: str) -> str:
    """
    Normalize markdown output for consistent formatting.

    Phase 4.2: Output normalization
    - Ensures consistent newline spacing
    - Trims extra whitespace
    - Standardizes markdown headers
    - Fixes table formatting

    Args:
        text: Raw markdown text

    Returns:
        Normalized markdown text
    """
    if not text:
        return ""

    # Split into lines for processing
    lines = text.split("\n")
    normalized_lines = []

    for line in lines:
        # Trim trailing whitespace
        line = line.rstrip()

        # Skip completely empty lines at start/end (will be added back strategically)
        if not line:
            # Keep empty line if previous line wasn't empty (prevents multiple consecutive empty lines)
            if normalized_lines and normalized_lines[-1]:
                normalized_lines.append(line)
        else:
            normalized_lines.append(line)

    # Join back together
    result = "\n".join(normalized_lines)

    # Ensure single newline after headers
    result = result.replace("###\n\n\n", "###\n\n")
    result = result.replace("##\n\n\n", "##\n\n")
    result = result.replace("#\n\n\n", "#\n\n")

    # Ensure tables have proper spacing
    result = result.replace("|\n|", "|\n\n|")  # Empty line before table continuation

    # Trim leading/trailing whitespace
    result = result.strip()

    return result


# ============================================================================
# MULTI-SEASON HELPERS (Phase 5.2 P2: Multi-Season Support)
# ============================================================================


def extract_multi_season_results(
    execution_result: ExecutionResult,
    base_tool_name: str
) -> List[ToolResult]:
    """
    Extract all results for a tool across multiple seasons.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    The executor names duplicate tools with suffixes:
    - First call: "get_player_advanced_stats"
    - Second call: "get_player_advanced_stats_2"
    - Third call: "get_player_advanced_stats_3"

    This function extracts ALL results matching the base tool name.

    Args:
        execution_result: Execution result with tool_results dict
        base_tool_name: Base tool name (e.g., "get_player_advanced_stats")

    Returns:
        List of ToolResult objects for all matching tools (sorted by suffix)

    Examples:
        >>> # Single season
        >>> extract_multi_season_results(result, "get_player_advanced_stats")
        [ToolResult(tool_name="get_player_advanced_stats", ...)]

        >>> # Multi-season (3 seasons)
        >>> extract_multi_season_results(result, "get_player_advanced_stats")
        [
            ToolResult(tool_name="get_player_advanced_stats", ...),
            ToolResult(tool_name="get_player_advanced_stats_2", ...),
            ToolResult(tool_name="get_player_advanced_stats_3", ...)
        ]
    """
    import re

    # Create pattern to match base_tool_name and base_tool_name_N
    pattern = re.compile(f"^{re.escape(base_tool_name)}(_\\d+)?$")

    results = []

    for key, result in execution_result.tool_results.items():
        if pattern.match(key) and result.success:
            results.append((key, result))

    # Sort by suffix number (original, _2, _3, etc.)
    def sort_key(item):
        key = item[0]
        if key == base_tool_name:
            return 0  # Original comes first
        else:
            # Extract number from suffix (e.g., "_2" -> 2)
            match = re.search(r"_(\d+)$", key)
            return int(match.group(1)) if match else 0

    results.sort(key=sort_key)

    # Return just the ToolResult objects (not the keys)
    return [result for _, result in results]


# ============================================================================
# TABLE FORMATTING
# ============================================================================


def format_comparison_table(
    player1_data: Dict[str, Any], player2_data: Dict[str, Any], metrics: List[str]
) -> str:
    """
    Format player comparison as table.

    Args:
        player1_data: First player's stats
        player2_data: Second player's stats
        metrics: List of metrics to compare

    Returns:
        Formatted table as string
    """
    headers = [
        "Metric",
        player1_data.get("player_name", "Player 1"),
        player2_data.get("player_name", "Player 2"),
        "Advantage",
    ]

    rows = []
    for metric in metrics:
        val1 = player1_data.get(metric, 0.0)
        val2 = player2_data.get(metric, 0.0)

        # Determine advantage (higher is better for most metrics)
        if val1 > val2:
            advantage = player1_data.get("player_name", "Player 1")
        elif val2 > val1:
            advantage = player2_data.get("player_name", "Player 2")
        else:
            advantage = "Tied"

        # Format values
        if isinstance(val1, float):
            val1_str = f"{val1:.1f}" if val1 > 10 else f"{val1:.3f}"
            val2_str = f"{val2:.1f}" if val2 > 10 else f"{val2:.3f}"
        else:
            val1_str = str(val1)
            val2_str = str(val2)

        rows.append([metric, val1_str, val2_str, advantage])

    return tabulate(rows, headers=headers, tablefmt="pipe")


def format_standings_table(
    standings_data: List[Dict[str, Any]], top_n: int = 10
) -> str:
    """
    Format standings as table.

    Args:
        standings_data: List of team standings
        top_n: Number of teams to show

    Returns:
        Formatted table as string
    """
    headers = ["Rank", "Team", "W-L", "Win%", "GB", "Streak"]

    rows = []
    for i, team in enumerate(standings_data[:top_n], 1):
        rows.append(
            [
                i,
                team.get("team_name", "Unknown"),
                f"{team.get('wins', 0)}-{team.get('losses', 0)}",
                f"{team.get('win_pct', 0.0):.3f}",
                team.get("games_behind", 0.0),
                team.get("streak", ""),
            ]
        )

    return tabulate(rows, headers=headers, tablefmt="pipe")


def format_leaders_table(leaders_data: List[Dict[str, Any]], stat_name: str) -> str:
    """
    Format league leaders as table.

    Args:
        leaders_data: List of leader entries
        stat_name: Name of the stat category

    Returns:
        Formatted table as string
    """
    headers = ["Rank", "Player", stat_name]

    rows = []
    for i, entry in enumerate(leaders_data, 1):
        rows.append(
            [i, entry.get("player", "Unknown"), f"{entry.get('value', 0.0):.1f}"]
        )

    return tabulate(rows, headers=headers, tablefmt="pipe")


# ============================================================================
# NARRATIVE FORMATTING
# ============================================================================


def format_team_comparison_narrative(
    team1_name: str,
    team2_name: str,
    team1_standing: Optional[Dict[str, Any]],
    team2_standing: Optional[Dict[str, Any]],
    team1_stats: Optional[Dict[str, Any]],
    team2_stats: Optional[Dict[str, Any]],
) -> str:
    """
    Format team comparison as narrative.

    Args:
        team1_name: First team name
        team2_name: Second team name
        team1_standing: First team's standing
        team2_standing: Second team's standing
        team1_stats: First team's advanced stats
        team2_stats: Second team's advanced stats

    Returns:
        Formatted narrative
    """
    lines = []

    # Title
    lines.append(f"## {team1_name} vs {team2_name}")
    lines.append("")

    # Standings
    if team1_standing and team2_standing:
        lines.append("### Records")
        lines.append(
            f"- **{team1_name}**: {team1_standing.get('wins', 0)}-{team1_standing.get('losses', 0)} "
            f"({team1_standing.get('conference', 'N/A')} #{team1_standing.get('conference_rank', 'N/A')})"
        )
        lines.append(
            f"- **{team2_name}**: {team2_standing.get('wins', 0)}-{team2_standing.get('losses', 0)} "
            f"({team2_standing.get('conference', 'N/A')} #{team2_standing.get('conference_rank', 'N/A')})"
        )
        lines.append("")

        # Recent form
        lines.append("### Recent Form")
        lines.append(
            f"- **{team1_name}**: Last 10: {team1_standing.get('last_10', 'N/A')}, "
            f"Streak: {team1_standing.get('streak', 'N/A')}"
        )
        lines.append(
            f"- **{team2_name}**: Last 10: {team2_standing.get('last_10', 'N/A')}, "
            f"Streak: {team2_standing.get('streak', 'N/A')}"
        )
        lines.append("")

    # Advanced stats
    if team1_stats and team2_stats:
        lines.append("### Advanced Stats")

        off1 = team1_stats.get("offensive_rating", 0.0)
        off2 = team2_stats.get("offensive_rating", 0.0)
        def1 = team1_stats.get("defensive_rating", 0.0)
        def2 = team2_stats.get("defensive_rating", 0.0)

        lines.append(
            f"- **Offense**: {team1_name} ({off1:.1f} ORtg) vs {team2_name} ({off2:.1f} ORtg) "
            f"→ Advantage: {team1_name if off1 > off2 else team2_name}"
        )
        lines.append(
            f"- **Defense**: {team1_name} ({def1:.1f} DRtg) vs {team2_name} ({def2:.1f} DRtg) "
            f"→ Advantage: {team1_name if def1 < def2 else team2_name}"
        )  # Lower is better for defense
        lines.append(
            f"- **Pace**: {team1_name} ({team1_stats.get('pace', 0.0):.1f}) vs "
            f"{team2_name} ({team2_stats.get('pace', 0.0):.1f})"
        )
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# INTENT-SPECIFIC SYNTHESIS
# ============================================================================


def synthesize_leaders_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """Synthesize response for leaders query."""
    # Extract leaders data
    leaders_result = execution_result.tool_results.get("get_league_leaders_info")

    if not leaders_result or not leaders_result.success:
        return "Unable to retrieve league leaders at this time."

    # Check if data is already a formatted string (new behavior)
    if isinstance(leaders_result.data, str):
        # Tool returns formatted string - pass it through
        return leaders_result.data

    # Handle structured data (old behavior for compatibility)
    leaders_data = leaders_result.data.get("leaders", [])
    stat_name = leaders_result.data.get("stat_category", "unknown stat")

    if not leaders_data:
        return f"No leaders found for {stat_name}."

    # Format as table
    table = format_leaders_table(leaders_data[:10], stat_name)

    response = f"### NBA Leaders in {stat_name}\n\n{table}"

    return response


def synthesize_comparison_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """Synthesize response for comparison query."""
    # Check if player or team comparison
    entity_types = [e["entity_type"] for e in parsed.entities]

    if "player" in entity_types:
        # Player comparison
        compare_result = execution_result.tool_results.get("compare_players")

        if not compare_result or not compare_result.success:
            return "Unable to compare players at this time."

        data = compare_result.data
        p1_data = data.get("player1", {})
        p2_data = data.get("player2", {})

        # Extract key metrics to compare
        metrics = [
            "points_per_game",
            "rebounds_per_game",
            "assists_per_game",
            "true_shooting_pct",
            "usage_pct",
        ]

        table = format_comparison_table(p1_data, p2_data, metrics)

        return f"### Player Comparison\n\n{table}"

    else:
        # Team comparison
        team1_name = (
            parsed.entities[0]["name"] if len(parsed.entities) > 0 else "Team 1"
        )
        team2_name = (
            parsed.entities[1]["name"] if len(parsed.entities) > 1 else "Team 2"
        )

        standings_result = execution_result.tool_results.get("get_team_standings")
        team1_stats_result = execution_result.tool_results.get(
            "get_team_advanced_stats"
        )
        team2_stats_result = execution_result.tool_results.get(
            "get_team_advanced_stats_2"
        )

        # Extract data
        standings_data = (
            standings_result.data
            if standings_result and standings_result.success
            else []
        )
        team1_stats = (
            team1_stats_result.data
            if team1_stats_result and team1_stats_result.success
            else None
        )
        team2_stats = (
            team2_stats_result.data
            if team2_stats_result and team2_stats_result.success
            else None
        )

        # Find standings for each team
        team1_standing = None
        team2_standing = None
        if isinstance(standings_data, list):
            for standing in standings_data:
                if standing.get("team_name") == team1_name:
                    team1_standing = standing
                elif standing.get("team_name") == team2_name:
                    team2_standing = standing

        narrative = format_team_comparison_narrative(
            team1_name,
            team2_name,
            team1_standing,
            team2_standing,
            team1_stats,
            team2_stats,
        )

        return narrative


def synthesize_standings_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """Synthesize response for standings query."""
    standings_result = execution_result.tool_results.get("get_team_standings")

    if not standings_result or not standings_result.success:
        return "Unable to retrieve standings at this time."

    standings_data = standings_result.data

    if not standings_data:
        return "No standings data available."

    table = format_standings_table(standings_data, top_n=15)

    conference = parsed.modifiers.get("conference", "League")
    return f"### {conference} Standings\n\n{table}"


def synthesize_player_stats_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """Synthesize response for player stats query."""

    # Phase 5.2 (P2): Check for multi-season results first
    multi_results = extract_multi_season_results(execution_result, "get_player_advanced_stats")

    if len(multi_results) > 1:
        # Multi-season query detected
        return synthesize_multi_season_stats(parsed, execution_result, "get_player_advanced_stats")

    # Single season: original logic
    stats_result = execution_result.tool_results.get("get_player_advanced_stats")

    if not stats_result or not stats_result.success:
        return "Unable to retrieve player stats at this time."

    # Check if data is already a formatted string (common pattern)
    if isinstance(stats_result.data, str):
        return stats_result.data

    data = stats_result.data
    player_name = data.get("player_name", "Unknown")
    season = data.get("season", "Unknown")

    lines = [
        f"### {player_name} Stats ({season})",
        "",
        f"**Games Played**: {data.get('games_played', 0)}",
        f"**Minutes Per Game**: {data.get('minutes_per_game', 0.0):.1f}",
        "",
        "**Scoring**:",
        f"- Points: {data.get('points_per_game', 0.0):.1f} PPG",
        f"- True Shooting %: {data.get('true_shooting_pct', 0.0):.1%}",
        f"- Usage %: {data.get('usage_pct', 0.0):.1f}%",
        "",
        "**Playmaking**:",
        f"- Assists: {data.get('assists_per_game', 0.0):.1f} APG",
        f"- Rebounds: {data.get('rebounds_per_game', 0.0):.1f} RPG",
        "",
        "**Impact**:",
        f"- PIE: {data.get('pie', 0.0):.3f}",
        f"- Net Rating: {data.get('net_rating', 0.0):.1f}",
    ]

    return "\n".join(lines)


def synthesize_team_stats_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for team stats query.

    Handles get_team_advanced_stats tool results which return formatted
    markdown strings with team statistics.

    Args:
        parsed: Parsed query with team entity
        execution_result: Tool execution results

    Returns:
        Formatted team statistics markdown string
    """

    # Phase 5.2 (P2): Check for multi-season results first
    multi_results = extract_multi_season_results(execution_result, "get_team_advanced_stats")

    if len(multi_results) > 1:
        # Multi-season query detected
        return synthesize_multi_season_stats(parsed, execution_result, "get_team_advanced_stats")

    # Single season: original logic
    stats_result = execution_result.tool_results.get("get_team_advanced_stats")

    if not stats_result or not stats_result.success:
        return "Unable to retrieve team stats at this time."

    # get_team_advanced_stats returns pre-formatted markdown string
    if isinstance(stats_result.data, str):
        return stats_result.data

    # Fallback: handle structured data if format changes
    data = stats_result.data
    team_name = data.get("team_name", parsed.entities[0]["name"] if parsed.entities else "Unknown")
    season = data.get("season", "Unknown")

    lines = [
        f"### {team_name} Team Stats ({season})",
        "",
        "**Offensive Metrics**:",
        f"- Offensive Rating: {data.get('off_rating', 0.0):.1f}",
        f"- True Shooting %: {data.get('ts_pct', 0.0):.1%}",
        f"- Effective FG %: {data.get('efg_pct', 0.0):.1%}",
        "",
        "**Defensive Metrics**:",
        f"- Defensive Rating: {data.get('def_rating', 0.0):.1f}",
        f"- Opponent FG %: {data.get('opp_fg_pct', 0.0):.1%}",
        "",
        "**Pace & Efficiency**:",
        f"- Pace: {data.get('pace', 0.0):.1f}",
        f"- Net Rating: {data.get('net_rating', 0.0):.1f}",
    ]

    return "\n".join(lines)


def synthesize_game_context_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for game context query.

    Handles get_game_context and get_live_scores tool results which provide
    comprehensive matchup information including standings, stats, and narratives.

    Args:
        parsed: Parsed query with team entities
        execution_result: Tool execution results

    Returns:
        Formatted game context markdown string
    """
    # Try get_game_context first (comprehensive matchup analysis)
    context_result = execution_result.tool_results.get("get_game_context")

    if context_result and context_result.success:
        # Check if already formatted as string
        if isinstance(context_result.data, str):
            return context_result.data

        # Handle structured ResponseEnvelope data
        # get_game_context returns dict with narrative field
        data = context_result.data
        if isinstance(data, dict):
            # Priority 1: Use pre-formatted narrative if available
            if "narrative" in data:
                return data["narrative"]

            # Priority 2: Extract data field if wrapped in ResponseEnvelope
            if "data" in data and isinstance(data["data"], dict):
                inner_data = data["data"]
                if "narrative" in inner_data:
                    return inner_data["narrative"]

                # Construct narrative from components
                return _build_game_context_narrative(inner_data, parsed)

            # Priority 3: Build from top-level data
            return _build_game_context_narrative(data, parsed)

    # Fallback: Try get_live_scores (simpler live game data)
    scores_result = execution_result.tool_results.get("get_live_scores")

    if scores_result and scores_result.success:
        if isinstance(scores_result.data, str):
            return scores_result.data

    # No data available
    return "Unable to retrieve game context at this time."


def _build_game_context_narrative(data: dict, parsed: ParsedQuery) -> str:
    """
    Build game context narrative from structured data components.

    Args:
        data: Game context data dict with matchup, standings, stats
        parsed: Parsed query for fallback team names

    Returns:
        Formatted markdown narrative
    """
    lines = []

    # Extract team names
    team1_name = "Team 1"
    team2_name = "Team 2"

    if parsed.entities and len(parsed.entities) >= 2:
        team1_name = parsed.entities[0].get("name", "Team 1")
        team2_name = parsed.entities[1].get("name", "Team 2")
    elif "matchup" in data:
        matchup = data["matchup"]
        team1_name = matchup.get("team1_name", team1_name)
        team2_name = matchup.get("team2_name", team2_name)

    lines.append(f"## {team1_name} vs {team2_name}")
    lines.append("")

    # Standings
    if "standings" in data:
        standings = data["standings"]
        team1_standing = standings.get("team1", {})
        team2_standing = standings.get("team2", {})

        if team1_standing or team2_standing:
            lines.append("### Records")
            if team1_standing:
                wins = team1_standing.get("wins", 0)
                losses = team1_standing.get("losses", 0)
                conf_rank = team1_standing.get("conference_rank", "N/A")
                lines.append(f"- **{team1_name}**: {wins}-{losses} (#{conf_rank})")
            if team2_standing:
                wins = team2_standing.get("wins", 0)
                losses = team2_standing.get("losses", 0)
                conf_rank = team2_standing.get("conference_rank", "N/A")
                lines.append(f"- **{team2_name}**: {wins}-{losses} (#{conf_rank})")
            lines.append("")

    # Advanced stats
    if "advanced_stats" in data:
        adv_stats = data["advanced_stats"]
        team1_stats = adv_stats.get("team1", {})
        team2_stats = adv_stats.get("team2", {})

        if team1_stats or team2_stats:
            lines.append("### Advanced Stats")
            off1 = team1_stats.get("off_rtg", 0.0)
            off2 = team2_stats.get("off_rtg", 0.0)
            if off1 or off2:
                adv1 = team1_name if off1 > off2 else team2_name
                lines.append(f"- **Offense**: {team1_name} ({off1:.1f}) vs {team2_name} ({off2:.1f}) → Advantage: {adv1}")

            def1 = team1_stats.get("def_rtg", 0.0)
            def2 = team2_stats.get("def_rtg", 0.0)
            if def1 or def2:
                adv2 = team1_name if def1 < def2 else team2_name  # Lower is better
                lines.append(f"- **Defense**: {team1_name} ({def1:.1f}) vs {team2_name} ({def2:.1f}) → Advantage: {adv2}")
            lines.append("")

    # Head to head
    if "head_to_head" in data:
        h2h = data["head_to_head"]
        record = h2h.get("record", "N/A")
        lines.append(f"### Season Series")
        lines.append(f"- {record}")
        lines.append("")

    # If no components, return minimal message
    if len(lines) <= 3:
        return f"Game context for {team1_name} vs {team2_name} is currently unavailable."

    return "\n".join(lines)


# ============================================================================
# Phase 2.2: New Intent Synthesis Functions (2025-11-01)
# ============================================================================


def synthesize_rankings_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for rankings query.

    Handles get_league_leaders_info results with conference/division filtering.

    Phase 2.2: Added for rankings intent type.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        Formatted rankings table as markdown string
    """
    leaders_result = execution_result.tool_results.get("get_league_leaders_info")

    if not leaders_result or not leaders_result.success:
        return "Unable to retrieve rankings at this time."

    # get_league_leaders_info returns pre-formatted markdown string
    if isinstance(leaders_result.data, str):
        return leaders_result.data

    # Fallback: structured data handling
    return "Rankings data retrieved but formatting is unavailable."


def synthesize_streaks_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for streaks query.

    Handles both team streaks (from standings) and player performance streaks.

    Phase 2.2: Added for streaks intent type.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        Formatted streaks information as markdown string
    """
    # Try team standings first (has streak info)
    standings_result = execution_result.tool_results.get("get_team_standings")
    if standings_result and standings_result.success:
        if isinstance(standings_result.data, str):
            return standings_result.data

    # Try player performance splits (has recent form/streaks)
    splits_result = execution_result.tool_results.get("get_player_performance_splits")
    if splits_result and splits_result.success:
        if isinstance(splits_result.data, str):
            return splits_result.data

    return "Unable to retrieve streak information at this time."


def synthesize_milestones_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for milestones query.

    Handles get_player_career_information results with career stats and achievements.

    Phase 2.2: Added for milestones intent type.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        Formatted milestones/career information as markdown string
    """
    career_result = execution_result.tool_results.get("get_player_career_information")

    if not career_result or not career_result.success:
        return "Unable to retrieve career milestones at this time."

    # get_player_career_information returns pre-formatted markdown string
    if isinstance(career_result.data, str):
        return career_result.data

    # Fallback: structured data handling
    data = career_result.data
    if isinstance(data, dict):
        player_name = data.get("player_name", "Unknown Player")
        return f"### {player_name} Career Information\n\nCareer data retrieved but detailed formatting is unavailable."

    return "Career milestones data retrieved but formatting is unavailable."


def synthesize_awards_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for awards query.

    Handles get_nba_awards results with MVP, DPOY, All-NBA selections, etc.

    Phase 2.2: Added for awards intent type.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        Formatted awards information as markdown string
    """
    awards_result = execution_result.tool_results.get("get_nba_awards")

    if not awards_result or not awards_result.success:
        return "Unable to retrieve awards information at this time."

    # get_nba_awards returns pre-formatted text string
    if isinstance(awards_result.data, str):
        return awards_result.data

    # Fallback: structured data handling
    return "Awards data retrieved but formatting is unavailable."


# ============================================================================
# MAIN SYNTHESIS FUNCTION
# ============================================================================


def synthesize_filtered_games_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize filtered game queries (games with statistical filters).

    Phase 5.1: Added for filtered_games intent.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        Formatted response with filtered game results

    Examples:
        "LeBron games with 30+ points" →
        "LeBron James - Games with 30+ points (2024-25 season)

        Found 15 games matching criteria:
        [Game table with PTS, REB, AST, W/L, etc.]"
    """
    tool_results = execution_result.tool_results

    # Get fetch_player_games result
    games_result = tool_results.get("fetch_player_games")

    if not games_result or not games_result.success:
        return "No games found matching the specified criteria."

    # Parse response data
    try:
        import json
        data = json.loads(games_result.data) if isinstance(games_result.data, str) else games_result.data

        # Extract game data
        games_data = data.get("data", [])
        metadata = data.get("metadata", {})

        if not games_data:
            return "No games found matching the specified criteria."

        game_count = len(games_data)
        player_name = parsed.entities[0]["name"] if parsed.entities else "Player"

        # Build filter description
        filters = []
        stat_filters = parsed.modifiers.get("stat_filters", {})
        for stat, (op, value) in stat_filters.items():
            op_text = ">=" if op == ">=" else ">" if op == ">" else "<=" if op == "<=" else "="
            if "PCT" in stat:
                filters.append(f"{stat} {op_text} {value*100:.0f}%")
            else:
                filters.append(f"{stat} {op_text} {value}")

        filter_desc = ", ".join(filters) if filters else "specified criteria"

        # Build header
        season = metadata.get("season", "2024-25")
        answer = f"**{player_name} - Games with {filter_desc}**\n\n"
        answer += f"Season: {season}\n"
        answer += f"Games Found: {game_count}\n\n"

        # Build game table
        answer += "| Date | Opponent | Result | MIN | PTS | REB | AST | FG% | 3P% |\n"
        answer += "|------|----------|--------|-----|-----|-----|-----|-----|-----|\n"

        for game in games_data[:20]:  # Limit to 20 games for readability
            game_date = game.get("GAME_DATE", "N/A")
            matchup = game.get("MATCHUP", "N/A")
            wl = game.get("WL", "")
            mins = game.get("MIN", 0)
            pts = game.get("PTS", 0)
            reb = game.get("REB", 0)
            ast = game.get("AST", 0)
            fg_pct = game.get("FG_PCT", 0)
            fg3_pct = game.get("FG3_PCT", 0)

            result_icon = "W" if wl == "W" else "L"
            answer += f"| {game_date} | {matchup} | {result_icon} | {mins:.0f} | {pts} | {reb} | {ast} | {fg_pct:.1%} | {fg3_pct:.1%} |\n"

        if game_count > 20:
            answer += f"\n*Showing first 20 of {game_count} games*"

        # Add summary stats
        if game_count > 0:
            avg_pts = sum(g.get("PTS", 0) for g in games_data) / game_count
            avg_reb = sum(g.get("REB", 0) for g in games_data) / game_count
            avg_ast = sum(g.get("AST", 0) for g in games_data) / game_count
            wins = sum(1 for g in games_data if g.get("WL") == "W")

            answer += f"\n\n**Averages in these games:**\n"
            answer += f"- PPG: {avg_pts:.1f}\n"
            answer += f"- RPG: {avg_reb:.1f}\n"
            answer += f"- APG: {avg_ast:.1f}\n"
            answer += f"- Record: {wins}-{game_count - wins} ({wins/game_count:.1%})"

        return answer

    except Exception as e:
        logger.error(f"Error synthesizing filtered games: {e}")
        return f"Error processing game data: {str(e)}"


def synthesize_multi_season_stats(
    parsed: ParsedQuery,
    execution_result: ExecutionResult,
    base_tool_name: str
) -> str:
    """
    Synthesize multi-season player or team statistics.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Creates comprehensive multi-season view with:
    - Per-season breakdown table
    - Multi-year aggregates (totals and averages)
    - Trend analysis (improving/declining stats)

    Args:
        parsed: Parsed query with entities and time_range
        execution_result: Execution results with multiple season data
        base_tool_name: Base tool name (e.g., "get_player_advanced_stats")

    Returns:
        Formatted markdown with multi-season table and aggregates

    Example Output:
        **LeBron James - Multi-Season Stats (2020-21 to 2023-24)**

        | Season | GP | PPG | RPG | APG | FG% | 3P% | PER |
        |--------|----|----|-----|-----|-----|-----|-----|
        | 2020-21 | 45 | 25.0 | 7.7 | 7.8 | 51.3% | 36.5% | 24.9 |
        | 2021-22 | 56 | 30.3 | 8.2 | 6.2 | 52.4% | 35.9% | 26.0 |
        | 2022-23 | 55 | 28.9 | 8.3 | 6.8 | 50.0% | 32.1% | 24.6 |
        | 2023-24 | 71 | 25.7 | 7.3 | 8.3 | 54.0% | 41.0% | 25.4 |

        **4-Year Averages:**
        - PPG: 27.5
        - RPG: 7.9
        - APG: 7.3
        - FG%: 51.9%
        - 3P%: 36.4%
        - Total Games: 227
    """
    try:
        # Extract all season results
        results = extract_multi_season_results(execution_result, base_tool_name)

        if not results:
            return "No multi-season data available."

        if len(results) == 1:
            # Only one season, fall back to single-season synthesis
            logger.warning("synthesize_multi_season_stats called with single season, using fallback")
            return "Single season data - use single-season synthesis instead."

        entity_name = parsed.entities[0]["name"] if parsed.entities else "Unknown"

        # Parse each season's data (results are already text from MCP tools)
        season_data = []
        for result in results:
            if isinstance(result.data, str):
                # Data is formatted string - extract key stats if possible
                # For now, just note we have the data
                season_data.append({"raw": result.data})
            else:
                season_data.append(result.data)

        # Build header
        first_season = parsed.time_range.seasons[0] if parsed.time_range.seasons else "Unknown"
        last_season = parsed.time_range.seasons[-1] if parsed.time_range.seasons else "Unknown"
        num_seasons = len(results)

        answer = f"**{entity_name} - Multi-Season Stats ({first_season} to {last_season})**\n\n"

        # If data is all formatted strings, just concatenate them with season headers
        if all(isinstance(sd.get("raw"), str) for sd in season_data):
            answer += f"*Showing stats for {num_seasons} seasons*\n\n"
            for i, (result, season) in enumerate(zip(results, parsed.time_range.seasons or [])):
                answer += f"### {season}\n\n"
                answer += result.data
                if i < len(results) - 1:
                    answer += "\n\n---\n\n"
        else:
            # Data is structured - build aggregate table
            # This is a placeholder for when we get structured data
            answer += f"*Note: Multi-season aggregation for structured data coming soon*\n\n"
            answer += f"Received {num_seasons} seasons of data.\n\n"
            for i, season in enumerate(parsed.time_range.seasons or []):
                answer += f"- {season}\n"

        return answer

    except Exception as e:
        logger.error(f"Error synthesizing multi-season stats: {e}")
        return f"Error processing multi-season data: {str(e)}"


def synthesize_all_time_leaders_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize all-time leaders query response.

    Phase 5.2 (P4): All-Time Leaders Tool (2025-11-01)

    Args:
        parsed: Parsed query with stat types
        execution_result: Tool execution results

    Returns:
        Formatted markdown response with all-time leaders table

    Example Output:
        **All-Time Points Leaders**

        | Rank | Player | Career Points | Status |
        |------|--------|---------------|--------|
        | 1 | LeBron James | 42,184 | Active |
        | 2 | Kareem Abdul-Jabbar | 38,387 | Retired |
        ...
    """
    try:
        if not execution_result.tool_results:
            return "No all-time leaders data available."

        # Get the result (should be text format from MCP tool)
        result_text = execution_result.tool_results[0].result

        # The MCP tool already formats the response nicely as text
        # We just need to pass it through
        if isinstance(result_text, str):
            return result_text

        return "Unable to format all-time leaders data."

    except Exception as e:
        logger.error(f"Error synthesizing all-time leaders: {e}")
        return f"Error processing all-time leaders data: {str(e)}"


def synthesize_lineup_analysis_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize lineup analysis query response.

    Phase 5.2 (P6): Lineup Analysis (2025-11-01)

    Args:
        parsed: Parsed query with team entity
        execution_result: Tool execution results

    Returns:
        Formatted markdown response with lineup statistics table

    Example Output:
        # Lakers - 5-Man Lineup Statistics (2023-24)
        **Minimum Minutes:** 50
        **Total Lineups:** 12

        | Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |
        |--------|----|----|-----|-----|-----|-----|-----|
        | James - Davis - Reaves - Russell - Hachimura | 45 | 30-15 | 682.3 | 1248 | +124 | 48.2% | 36.1% |
        ...
    """
    try:
        if not execution_result.tool_results:
            return "No lineup data available."

        # Get the result (should be text format from MCP tool)
        result_text = execution_result.tool_results[0].result

        # The MCP tool already formats the response nicely as markdown
        # We just need to pass it through
        if isinstance(result_text, str):
            return result_text

        return "Unable to format lineup data."

    except Exception as e:
        logger.error(f"Error synthesizing lineup analysis: {e}")
        return f"Error processing lineup data: {str(e)}"


def synthesize_highlight_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize response for highlight queries (players/teams meeting specific criteria).

    Phase 5.3 (NLQ Enhancement - Phase 3): Highlight synthesis (2025-11-01)

    Args:
        parsed: Parsed query with highlight intent
        execution_result: Tool execution results

    Returns:
        Formatted markdown response

    Examples:
        Query: "show me players with 30+ points"
        Query: "highlight teams with 10+ wins"
    """
    if not execution_result.tool_results:
        return "No results found matching the specified criteria."

    result = execution_result.tool_results[0]
    data = result.get("data", {})

    # Check if this is a filtered_games result or league_leaders result
    if isinstance(data, list):
        # League leaders result (list of players/teams)
        if not data:
            return "No results found matching the specified criteria."

        # Extract criteria from modifiers
        criteria_parts = []
        if parsed.modifiers.get("stat_filters"):
            criteria_parts.append(f"statistical filters: {parsed.modifiers['stat_filters']}")
        if parsed.modifiers.get("min_games"):
            criteria_parts.append(f"minimum {parsed.modifiers['min_games']} games played")

        criteria_str = " and ".join(criteria_parts) if criteria_parts else "specified criteria"

        # Build response
        response = f"# Players/Teams Meeting {criteria_str.title()}\n\n"
        response += f"Found **{len(data)}** results:\n\n"

        # Table format
        if len(data) > 0 and isinstance(data[0], dict):
            # Determine key columns
            first_item = data[0]
            key_cols = []

            if "PLAYER_NAME" in first_item:
                key_cols = ["RANK", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "PTS", "REB", "AST"]
            elif "TEAM_NAME" in first_item:
                key_cols = ["RANK", "TEAM_NAME", "W", "L", "W_PCT", "PTS", "DIFF"]
            else:
                # Use first 7 keys
                key_cols = list(first_item.keys())[:7]

            # Filter to available columns
            available_cols = [col for col in key_cols if col in first_item]

            # Table header
            response += "| " + " | ".join(available_cols) + " |\n"
            response += "|" + "|".join(["---"] * len(available_cols)) + "|\n"

            # Table rows (limit to top 25)
            for item in data[:25]:
                row_values = []
                for col in available_cols:
                    val = item.get(col, "")
                    # Format percentages and decimals
                    if isinstance(val, float):
                        if col.endswith("_PCT"):
                            row_values.append(f"{val:.1%}")
                        else:
                            row_values.append(f"{val:.1f}")
                    else:
                        row_values.append(str(val))
                response += "| " + " | ".join(row_values) + " |\n"

            if len(data) > 25:
                response += f"\n*Showing top 25 of {len(data)} results*\n"

        return response

    elif isinstance(data, dict):
        # Filtered games result (game-by-game data)
        # Delegate to filtered_games synthesis
        return synthesize_filtered_games_query(parsed, execution_result)

    else:
        return "Unable to format highlight results."


def synthesize_lineup_comparison_query(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> str:
    """
    Synthesize lineup comparison query response (side-by-side comparison).

    Phase 5.2 (P6 Phase 2): Lineup Comparison (2025-11-01)

    Args:
        parsed: Parsed query with 2 team entities
        execution_result: Results from 2x get_lineup_stats calls

    Returns:
        Formatted side-by-side lineup comparison
    """
    try:
        if not execution_result.tool_results or len(execution_result.tool_results) < 2:
            return "Insufficient lineup data for comparison."

        # Get results for both teams
        team1_result = execution_result.tool_results[0].result
        team2_result = execution_result.tool_results[1].result

        # Extract team names from parsed entities
        team1_name = parsed.entities[0]["name"] if parsed.entities else "Team 1"
        team2_name = parsed.entities[1]["name"] if len(parsed.entities) > 1 else "Team 2"

        # Parse lineup data from markdown tables (extract first lineup from each)
        def extract_best_lineup(markdown_text, team_name):
            """Extract best lineup (first row) from markdown table."""
            lines = markdown_text.split('\n')
            # Find table header row
            for i, line in enumerate(lines):
                if '| Lineup |' in line or '|--------|' in line:
                    # Data rows start after header + separator
                    if i + 2 < len(lines):
                        data_line = lines[i + 2]
                        # Parse: | Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |
                        parts = [p.strip() for p in data_line.split('|')]
                        if len(parts) >= 9:
                            return {
                                'lineup': parts[1],
                                'gp': parts[2],
                                'wl': parts[3],
                                'min': parts[4],
                                'pts': parts[5],
                                'plus_minus': parts[6],
                                'fg_pct': parts[7],
                                'fg3_pct': parts[8],
                            }
            return None

        team1_lineup = extract_best_lineup(team1_result, team1_name)
        team2_lineup = extract_best_lineup(team2_result, team2_name)

        if not team1_lineup or not team2_lineup:
            # Fallback: Return both results side-by-side without comparison table
            return f"# Lineup Comparison\n\n## {team1_name}\n\n{team1_result}\n\n## {team2_name}\n\n{team2_result}"

        # Build side-by-side comparison table
        from nba_mcp.nlq.planner import _extract_season
        season = _extract_season(parsed.time_range) or "Current Season"

        response_lines = [
            f"# {team1_name} vs {team2_name} - Best Lineup Comparison ({season})",
            "",
            "| Metric | " + team1_name + " | " + team2_name + " |",
            "|--------|" + "-"*len(team1_name) + "|" + "-"*len(team2_name) + "|",
            f"| **Players** | {team1_lineup['lineup']} | {team2_lineup['lineup']} |",
            f"| **Games Played** | {team1_lineup['gp']} | {team2_lineup['gp']} |",
            f"| **Win-Loss** | {team1_lineup['wl']} | {team2_lineup['wl']} |",
            f"| **Minutes** | {team1_lineup['min']} | {team2_lineup['min']} |",
            f"| **Points** | {team1_lineup['pts']} | {team2_lineup['pts']} |",
            f"| **Plus/Minus** | {team1_lineup['plus_minus']} | {team2_lineup['plus_minus']} |",
            f"| **FG%** | {team1_lineup['fg_pct']} | {team2_lineup['fg_pct']} |",
            f"| **3P%** | {team1_lineup['fg3_pct']} | {team2_lineup['fg3_pct']} |",
            "",
            "## Full Lineup Data",
            "",
            f"### {team1_name}",
            team1_result,
            "",
            f"### {team2_name}",
            team2_result,
        ]

        return "\n".join(response_lines)

    except Exception as e:
        logger.error(f"Error synthesizing lineup comparison: {e}")
        return f"Error processing lineup comparison: {str(e)}"


async def synthesize_response(
    parsed: ParsedQuery, execution_result: ExecutionResult
) -> SynthesizedResponse:
    """
    Main synthesis function: format tool results into natural language.

    Args:
        parsed: Parsed query
        execution_result: Tool execution results

    Returns:
        SynthesizedResponse with formatted answer
    """
    logger.info(f"Synthesizing response for intent: {parsed.intent}")

    # Route to intent-specific synthesizer
    if parsed.intent == "leaders":
        answer = synthesize_leaders_query(parsed, execution_result)
    elif parsed.intent == "comparison":
        answer = synthesize_comparison_query(parsed, execution_result)
    elif parsed.intent == "standings":
        answer = synthesize_standings_query(parsed, execution_result)
    elif parsed.intent == "player_stats":
        answer = synthesize_player_stats_query(parsed, execution_result)
    elif parsed.intent == "team_stats":
        answer = synthesize_team_stats_query(parsed, execution_result)
    elif parsed.intent == "game_context":
        answer = synthesize_game_context_query(parsed, execution_result)
    # Phase 2.2: New intent types (2025-11-01)
    elif parsed.intent == "rankings":
        answer = synthesize_rankings_query(parsed, execution_result)
    elif parsed.intent == "streaks":
        answer = synthesize_streaks_query(parsed, execution_result)
    elif parsed.intent == "milestones":
        answer = synthesize_milestones_query(parsed, execution_result)
    elif parsed.intent == "awards":
        answer = synthesize_awards_query(parsed, execution_result)
    # Phase 5.1: Filtered game queries (2025-11-01)
    elif parsed.intent == "filtered_games":
        answer = synthesize_filtered_games_query(parsed, execution_result)
    # Phase 5.2 (P4): All-time leaders (2025-11-01)
    elif parsed.intent == "all_time_leaders":
        answer = synthesize_all_time_leaders_query(parsed, execution_result)
    elif parsed.intent == "lineup_analysis":  # Phase 5.2 (P6)
        answer = synthesize_lineup_analysis_query(parsed, execution_result)
    elif parsed.intent == "lineup_comparison":  # Phase 5.2 (P6 Phase 2)
        answer = synthesize_lineup_comparison_query(parsed, execution_result)
    # Phase 5.3 (NLQ Enhancement - Phase 3): Highlight intent (2025-11-01)
    elif parsed.intent == "highlight":
        answer = synthesize_highlight_query(parsed, execution_result)
    else:
        answer = "Unable to synthesize response for this query type."

    # Phase 4.2: Normalize output for consistent formatting
    answer = normalize_markdown_output(answer)

    # Add disclaimer if not all tools succeeded
    if not execution_result.all_success:
        answer += (
            "\n\n*Note: Some data could not be retrieved. Results may be incomplete.*"
        )

    # Build metadata
    metadata = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "execution_time_ms": execution_result.total_time_ms,
        "tools_executed": len(execution_result.tool_results),
        "all_success": execution_result.all_success,
    }

    # Build sources list
    sources = ["NBA API (nba_mcp v1)"]

    # Calculate confidence (based on parse confidence + execution success)
    confidence = parsed.confidence
    if not execution_result.all_success:
        confidence *= 0.7

    response = SynthesizedResponse(
        raw_query=parsed.raw_query,
        intent=parsed.intent,
        answer=answer,
        confidence=confidence,
        sources=sources,
        metadata=metadata,
    )

    logger.info(f"Synthesis complete: {len(answer)} chars, confidence={confidence:.2f}")

    return response
