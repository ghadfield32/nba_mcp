# nba_mcp/nlq/pipeline.py
"""
Complete NLQ Pipeline Interface.

Provides a simple async function to answer NBA questions in natural language.
"""

import logging
from typing import Optional

from .executor import execute_plan
from .parser import parse_query, validate_parsed_query
from .planner import plan_query_execution
from .synthesizer import SynthesizedResponse, synthesize_response

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN PIPELINE
# ============================================================================


async def answer_nba_question(query: str, return_metadata: bool = False) -> str:
    """
    Answer a natural language question about NBA data.

    This is the main entry point for the NLQ pipeline. It orchestrates:
    1. Parsing the query
    2. Planning tool execution
    3. Executing tools (with parallelization)
    4. Synthesizing a formatted response

    Args:
        query: Natural language question (e.g., "Who leads the NBA in assists?")
        return_metadata: If True, return full response with metadata. If False, return just the answer.

    Returns:
        Formatted answer string (markdown) or full response dict if return_metadata=True

    Examples:
        >>> await answer_nba_question("Who leads the NBA in assists?")
        "### NBA Leaders in AST\n\n| Rank | Player | AST |\n..."

        >>> await answer_nba_question("Compare LeBron James and Kevin Durant")
        "### Player Comparison\n\n| Metric | LeBron James | Kevin Durant | Advantage |\n..."

    Raises:
        ValueError: If query cannot be parsed or planned
    """
    logger.info(f"Processing NBA question: '{query}'")

    try:
        # Step 1: Parse
        parsed = await parse_query(query)
        logger.debug(
            f"Parsed: intent={parsed.intent}, confidence={parsed.confidence:.2f}"
        )

        # Validate parse quality (Phase 2.5: Enhanced validation with hints)
        validation = validate_parsed_query(parsed)
        if not validation.valid:
            error_msg = f"Unable to understand query: '{query}'.\n\n"
            error_msg += "**Errors:**\n"
            for error in validation.errors:
                error_msg += f"- {error}\n"
            if validation.hints:
                error_msg += "\n**Suggestions:**\n"
                for hint in validation.hints:
                    error_msg += f"- {hint}\n"
            logger.warning(f"Validation failed: {validation.errors}")
            return error_msg

        # Step 2: Plan
        plan = await plan_query_execution(parsed)
        logger.debug(
            f"Plan: {len(plan.tool_calls)} tools, template={plan.template_used}"
        )

        # Step 3: Execute
        result = await execute_plan(plan)
        logger.debug(
            f"Execution: {result.total_time_ms:.1f}ms, success={result.all_success}"
        )

        # Step 4: Synthesize
        response = await synthesize_response(parsed, result)
        logger.info(
            f"Completed: {len(response.answer)} chars, confidence={response.confidence:.2f}"
        )

        # Return answer or full response
        if return_metadata:
            return response.to_dict()
        else:
            return response.answer

    except ValueError as e:
        error_msg = f"Error processing query: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        logger.exception("Unexpected error in NLQ pipeline")
        return error_msg


# ============================================================================
# BATCH PROCESSING
# ============================================================================


async def answer_nba_questions(queries: list[str]) -> list[str]:
    """
    Answer multiple NBA questions in parallel.

    Args:
        queries: List of natural language questions

    Returns:
        List of formatted answers (same order as queries)
    """
    import asyncio

    tasks = [answer_nba_question(q) for q in queries]
    return await asyncio.gather(*tasks, return_exceptions=True)


# ============================================================================
# PIPELINE STATUS
# ============================================================================


def get_pipeline_status() -> dict:
    """
    Get current pipeline status and statistics.

    Returns:
        Dictionary with pipeline info
    """
    from .tool_registry import get_registry_info
    from .llm_fallback import get_llm_metrics, get_llm_config

    # Get LLM metrics (Phase 3.7: LLM metrics tracking)
    llm_metrics = get_llm_metrics()
    llm_config = get_llm_config()

    return {
        "status": "ready",
        "tools": get_registry_info(),
        "supported_intents": [
            "leaders",
            "comparison",
            "game_context",
            "season_stats",
            "team_stats",
            "player_stats",
            "standings",
            # Phase 2.2: New intent types
            "rankings",
            "streaks",
            "milestones",
            "awards",
        ],
        # Phase 3.7: LLM fallback metrics
        "llm_fallback": {
            "enabled": llm_config.enabled,
            "model": llm_config.model,
            "parse_refinement_calls": llm_metrics.parse_refinement_calls,
            "plan_generation_calls": llm_metrics.plan_generation_calls,
            "successes": llm_metrics.successes,
            "failures": llm_metrics.failures,
            "avg_latency_ms": (
                llm_metrics.total_latency_ms
                / (llm_metrics.parse_refinement_calls + llm_metrics.plan_generation_calls)
                if (llm_metrics.parse_refinement_calls + llm_metrics.plan_generation_calls) > 0
                else 0.0
            ),
        },
    }
