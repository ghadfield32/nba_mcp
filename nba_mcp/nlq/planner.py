# nba_mcp/nlq/planner.py
"""
Execution Planner for NBA MCP NLQ.

Maps parsed queries to sequences of MCP tool calls using answer pack templates.
Identifies parallelizable operations and handles dependencies.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import logging

from .parser import ParsedQuery, TimeRange

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL CALL SPECIFICATION
# ============================================================================


@dataclass
class ToolCall:
    """Specification for an MCP tool call."""

    tool_name: str
    params: Dict[str, Any]
    depends_on: Optional[List[str]] = None  # Tool names this depends on
    parallel_group: int = 0  # Tools with same group can run in parallel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "depends_on": self.depends_on or [],
            "parallel_group": self.parallel_group,
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan for a query."""

    parsed_query: ParsedQuery
    tool_calls: List[ToolCall]
    template_used: str
    can_parallelize: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parsed_query": self.parsed_query.to_dict(),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "template_used": self.template_used,
            "can_parallelize": self.can_parallelize,
        }


# ============================================================================
# ANSWER PACK TEMPLATES
# ============================================================================

ANSWER_PACK_TEMPLATES = {
    # Template 1: League Leaders
    "leaders": {
        "description": "Get top players in a stat category",
        "required": ["stat_types"],
        "optional": ["time_range", "modifiers.top_n"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_league_leaders_info",
                params={
                    "stat_category": (
                        parsed.stat_types[0] if parsed.stat_types else "PTS"
                    ),
                    "season": _extract_season(parsed.time_range),
                    "per_mode": _extract_per_mode(parsed.modifiers),
                    "season_type_all_star": _extract_season_type(parsed.modifiers),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 2: Player Comparison (2 players)
    "comparison_players": {
        "description": "Compare two players side-by-side",
        "required": ["entities"],  # 2 players
        "optional": ["time_range", "modifiers.normalization"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="compare_players",
                params={
                    "player1_name": parsed.entities[0]["name"],
                    "player2_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                    "normalization": parsed.modifiers.get("normalization", "per_75"),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 3: Team Comparison (Game Context)
    "comparison_teams": {
        "description": "Compare two teams with standings and advanced stats",
        "required": ["entities"],  # 2 teams
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_team_standings",
                params={
                    "season": _extract_season(parsed.time_range),
                    "conference": None,
                },
                parallel_group=0,
            ),
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=1,
            ),
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[1]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=1,
            ),
        ],
    },
    # Template 4: Tonight's Game
    "game_context": {
        "description": "Get live scores and game context",
        "required": [],
        "optional": ["entities", "time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_live_scores",
                params={"target_date": _extract_date(parsed.time_range)},
                parallel_group=0,
            )
        ],
    },
    # Template 5: Player Season Stats
    "player_stats": {
        "description": "Get a player's season statistics",
        "required": ["entities"],  # 1 player
        "optional": ["time_range", "stat_types"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={
                    "player_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 6: Team Season Stats
    "team_stats": {
        "description": "Get a team's season statistics",
        "required": ["entities"],  # 1 team
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_team_advanced_stats",
                params={
                    "team_name": parsed.entities[0]["name"],
                    "season": _extract_season(parsed.time_range),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 7: Conference Standings
    "standings": {
        "description": "Get team standings",
        "required": [],
        "optional": ["time_range"],
        "tools": lambda parsed: [
            ToolCall(
                tool_name="get_team_standings",
                params={
                    "season": _extract_season(parsed.time_range),
                    "conference": _extract_conference(parsed.raw_query),
                },
                parallel_group=0,
            )
        ],
    },
    # Template 8: Season Comparison (same player, different seasons)
    "season_comparison": {
        "description": "Compare a player across multiple seasons",
        "required": ["entities"],  # 1 player
        "optional": ["time_range"],
        "tools": lambda parsed: _build_season_comparison_tools(parsed),
    },
}


# ============================================================================
# HELPER FUNCTIONS FOR PARAMETER EXTRACTION
# ============================================================================


def _extract_season(time_range: Optional[TimeRange]) -> Optional[str]:
    """Extract season string from time range."""
    if not time_range:
        return None
    return time_range.season


def _extract_date(time_range: Optional[TimeRange]) -> Optional[str]:
    """Extract date string from time range."""
    if not time_range:
        return None
    if time_range.start_date:
        return time_range.start_date.isoformat()
    if time_range.relative == "tonight":
        from datetime import date

        return date.today().isoformat()
    return None


def _extract_per_mode(modifiers: Dict[str, Any]) -> str:
    """Extract per-mode from modifiers."""
    normalization = modifiers.get("normalization", "per_game")
    if normalization == "per_game":
        return "PerGame"
    elif normalization == "per_75":
        return "Per48"  # NBA API doesn't have Per75, use Per48 as closest
    elif normalization == "per_100":
        return "PerGame"  # Will normalize in post-processing
    return "PerGame"


def _extract_season_type(modifiers: Dict[str, Any]) -> str:
    """Extract season type from modifiers."""
    season_type = modifiers.get("season_type", "regular")
    if season_type == "playoffs":
        return "Playoffs"
    return "Regular Season"


def _extract_conference(query: str) -> Optional[str]:
    """Extract conference filter from query."""
    query_lower = query.lower()
    if "eastern" in query_lower or "east" in query_lower:
        return "East"
    elif "western" in query_lower or "west" in query_lower:
        return "West"
    return None


def _build_season_comparison_tools(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Build tool calls for season comparison.

    Extracts multiple seasons from query (e.g., "2023 vs 2020" or "this season vs last season").
    """
    # Parse multiple seasons from query
    import re

    seasons = re.findall(r"(\d{4})-?(\d{2})?", parsed.raw_query)

    if len(seasons) >= 2:
        # Found explicit season years
        season1 = f"{seasons[0][0]}-{seasons[0][1] or str(int(seasons[0][0]) + 1)[-2:]}"
        season2 = f"{seasons[1][0]}-{seasons[1][1] or str(int(seasons[1][0]) + 1)[-2:]}"

        return [
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={"player_name": parsed.entities[0]["name"], "season": season1},
                parallel_group=0,
            ),
            ToolCall(
                tool_name="get_player_advanced_stats",
                params={"player_name": parsed.entities[0]["name"], "season": season2},
                parallel_group=0,
            ),
        ]

    # Default: current season only
    return [
        ToolCall(
            tool_name="get_player_advanced_stats",
            params={
                "player_name": parsed.entities[0]["name"],
                "season": _extract_season(parsed.time_range),
            },
            parallel_group=0,
        )
    ]


# ============================================================================
# TEMPLATE MATCHING
# ============================================================================


def match_template(parsed: ParsedQuery) -> Optional[str]:
    """
    Match parsed query to best answer pack template.

    Args:
        parsed: Parsed query

    Returns:
        Template name or None if no match
    """
    intent = parsed.intent
    num_entities = len(parsed.entities)
    entity_types = (
        [e["entity_type"] for e in parsed.entities] if parsed.entities else []
    )

    logger.debug(
        f"Matching template: intent={intent}, entities={num_entities}, types={entity_types}"
    )

    # Leaders query
    if intent == "leaders":
        return "leaders"

    # Comparison queries
    if intent == "comparison":
        if num_entities == 2:
            # Determine if player or team comparison
            if all(t == "player" for t in entity_types):
                return "comparison_players"
            elif all(t == "team" for t in entity_types):
                return "comparison_teams"

        # Season comparison (same player, different seasons)
        elif num_entities == 1 and entity_types[0] == "player":
            # Check if query mentions multiple seasons
            import re

            if len(re.findall(r"\d{4}", parsed.raw_query)) >= 2:
                return "season_comparison"

    # Game context
    if intent == "game_context":
        return "game_context"

    # Player stats
    if intent == "player_stats" and num_entities == 1 and entity_types[0] == "player":
        return "player_stats"

    # Team stats
    if intent == "team_stats" and num_entities == 1 and entity_types[0] == "team":
        return "team_stats"

    # Standings
    if intent == "standings":
        return "standings"

    logger.warning(f"No template matched for intent={intent}, entities={num_entities}")
    return None


# ============================================================================
# PLAN GENERATION
# ============================================================================


def generate_execution_plan(parsed: ParsedQuery) -> Optional[ExecutionPlan]:
    """
    Generate execution plan from parsed query.

    Args:
        parsed: Parsed query

    Returns:
        ExecutionPlan or None if no template matches

    Examples:
        >>> parsed = ParsedQuery(intent="leaders", stat_types=["AST"])
        >>> plan = generate_execution_plan(parsed)
        >>> plan.tool_calls[0].tool_name
        'get_league_leaders_info'
    """
    logger.info(f"Generating execution plan for query: '{parsed.raw_query}'")

    # Match template
    template_name = match_template(parsed)

    if not template_name:
        logger.error("No template matched - cannot generate plan")
        return None

    logger.info(f"Matched template: {template_name}")

    # Get template
    template = ANSWER_PACK_TEMPLATES[template_name]

    # Generate tool calls using template function
    try:
        tool_calls = template["tools"](parsed)
        logger.info(f"Generated {len(tool_calls)} tool calls")

        # Determine if tools can be parallelized
        can_parallelize = len(set(tc.parallel_group for tc in tool_calls)) > 1

        plan = ExecutionPlan(
            parsed_query=parsed,
            tool_calls=tool_calls,
            template_used=template_name,
            can_parallelize=can_parallelize,
        )

        logger.debug(f"Execution plan: {plan.to_dict()}")
        return plan

    except Exception as e:
        logger.error(f"Failed to generate tool calls from template: {e}", exc_info=True)
        return None


# ============================================================================
# PLAN VALIDATION
# ============================================================================


def validate_execution_plan(plan: ExecutionPlan) -> bool:
    """
    Validate that execution plan is sound.

    Checks:
    - All tool calls have required parameters
    - Dependencies are resolvable
    - No circular dependencies

    Args:
        plan: Execution plan

    Returns:
        True if valid, False otherwise
    """
    if not plan.tool_calls:
        logger.error("Execution plan has no tool calls")
        return False

    # Check that all tool calls have tool_name and params
    for tc in plan.tool_calls:
        if not tc.tool_name:
            logger.error("Tool call missing tool_name")
            return False
        if tc.params is None:
            logger.error(f"Tool call {tc.tool_name} missing params")
            return False

    # TODO: Validate dependencies (no circular deps)

    return True


# ============================================================================
# MAIN PLANNER FUNCTION
# ============================================================================


async def plan_query_execution(parsed: ParsedQuery) -> ExecutionPlan:
    """
    Main planner function: generate and validate execution plan.

    Args:
        parsed: Parsed query

    Returns:
        Valid execution plan

    Raises:
        ValueError: If no plan can be generated or validation fails
    """
    plan = generate_execution_plan(parsed)

    if not plan:
        raise ValueError(
            f"No execution plan could be generated for query: '{parsed.raw_query}'"
        )

    if not validate_execution_plan(plan):
        raise ValueError(
            f"Generated plan failed validation for query: '{parsed.raw_query}'"
        )

    return plan
