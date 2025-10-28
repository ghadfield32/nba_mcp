# nba_mcp/nlq/synthesizer.py
"""
Response Synthesizer for NBA MCP NLQ.

Formats tool execution results into natural language responses with:
- Tables for comparisons
- Narratives for game context
- Lists for rankings
- Metadata (sources, timestamps, confidence)
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from .parser import ParsedQuery
from .executor import ExecutionResult, ToolResult
from tabulate import tabulate

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
    stats_result = execution_result.tool_results.get("get_player_advanced_stats")

    if not stats_result or not stats_result.success:
        return "Unable to retrieve player stats at this time."

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


# ============================================================================
# MAIN SYNTHESIS FUNCTION
# ============================================================================


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
        answer = "Team stats synthesis not yet implemented."
    else:
        answer = "Unable to synthesize response for this query type."

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
