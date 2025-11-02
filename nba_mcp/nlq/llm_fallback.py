# nba_mcp/nlq/llm_fallback.py
"""
LLM Fallback Module for NBA NLQ Pipeline.

Provides LLM-powered fallback for ambiguous queries using Ollama.
Two main use cases:
1. Parse refinement: Boost low-confidence parses (<0.5 confidence)
2. Plan generation: Handle unknown intents

Phase 3: LLM Fallback Integration (2025-11-01)
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama

from .parser import ParsedQuery
from .planner import ToolCall

logger = logging.getLogger(__name__)


# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================


@dataclass
class LLMConfig:
    """LLM configuration from environment variables."""

    model: str
    url: str
    enabled: bool
    timeout: int  # seconds

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load configuration from environment variables with defaults."""
        return cls(
            model=os.getenv("NBA_MCP_LLM_MODEL", "llama3.2:3b"),
            url=os.getenv("NBA_MCP_LLM_URL", "http://localhost:11434"),
            enabled=os.getenv("NBA_MCP_ENABLE_LLM_FALLBACK", "true").lower()
            == "true",
            timeout=int(os.getenv("NBA_MCP_LLM_TIMEOUT", "5")),
        )


# Global config singleton
_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    """Get global LLM configuration."""
    global _config
    if _config is None:
        _config = LLMConfig.from_env()
        logger.info(
            f"LLM Fallback Config: model={_config.model}, enabled={_config.enabled}"
        )
    return _config


# ============================================================================
# OLLAMA CLIENT WRAPPER
# ============================================================================


class OllamaClient:
    """
    Wrapper for ChatOllama with lazy initialization and health checking.

    Provides graceful degradation if Ollama is unavailable.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Optional[ChatOllama] = None
        self._healthy: Optional[bool] = None

    def _initialize(self) -> bool:
        """
        Lazy initialization of Ollama client.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._client is not None:
            return True

        if not self.config.enabled:
            logger.info("LLM fallback disabled via NBA_MCP_ENABLE_LLM_FALLBACK")
            return False

        try:
            self._client = ChatOllama(
                model=self.config.model,
                base_url=self.config.url,
                timeout=self.config.timeout,
            )
            logger.info(
                f"Ollama client initialized: {self.config.model} at {self.config.url}"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama client: {e}")
            self._healthy = False
            return False

    def is_healthy(self) -> bool:
        """
        Check if Ollama is available and healthy.

        Returns:
            True if Ollama is available, False otherwise
        """
        if self._healthy is not None:
            return self._healthy

        if not self._initialize():
            return False

        try:
            # Simple health check: invoke with minimal prompt
            response = self._client.invoke("test")
            self._healthy = True
            logger.info("Ollama health check passed")
            return True
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            self._healthy = False
            return False

    async def invoke(self, prompt: str) -> Optional[str]:
        """
        Invoke Ollama with prompt.

        Args:
            prompt: Prompt text

        Returns:
            Response text or None if invocation failed
        """
        if not self._initialize():
            return None

        try:
            response = self._client.invoke(prompt)
            # Extract content from response
            if hasattr(response, "content"):
                return response.content
            return str(response)
        except Exception as e:
            logger.warning(f"Ollama invocation failed: {e}")
            _metrics.failures += 1
            return None


# Global Ollama client singleton
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get global Ollama client."""
    global _ollama_client
    if _ollama_client is None:
        config = get_llm_config()
        _ollama_client = OllamaClient(config)
    return _ollama_client


# ============================================================================
# PROMPT TEMPLATES
# ============================================================================

PARSE_REFINEMENT_PROMPT = """You are an NBA query parser. Extract structured information from this query.

Query: "{query}"

Available intents: leaders, comparison, game_context, season_stats, team_stats, player_stats, standings, rankings, streaks, milestones, awards

Available stat types: PTS (points), AST (assists), REB (rebounds), STL (steals), BLK (blocks), FG_PCT (field goal %), FT_PCT (free throw %), FG3_PCT (3-point %), MIN (minutes)

Output JSON only (no explanation):
{{
  "intent": "<intent_type>",
  "entities": [{{"name": "<full_name>", "entity_type": "player|team"}}],
  "stat_types": ["<STAT_CODE>"],
  "time_range": {{"season": "<YYYY-YY>"}},
  "confidence": 0.0-1.0
}}

Examples:

Query: "Where does LeBron rank in scoring?"
Output: {{"intent": "rankings", "entities": [{{"name": "LeBron James", "entity_type": "player"}}], "stat_types": ["PTS"], "confidence": 0.9}}

Query: "Lakers winning streak"
Output: {{"intent": "streaks", "entities": [{{"name": "Los Angeles Lakers", "entity_type": "team"}}], "stat_types": [], "confidence": 0.95}}

Query: "Who won MVP in 2023?"
Output: {{"intent": "awards", "entities": [], "stat_types": [], "time_range": {{"season": "2022-23"}}, "confidence": 0.9}}

Now parse this query:
Query: "{query}"
Output:"""

PLAN_GENERATION_PROMPT = """You are an NBA API planner. Generate tool calls for this query.

Query: "{query}"
Intent: {intent}
Entities: {entities}

Available tools:
- get_league_leaders_info: Get top players by stat category (params: stat_category, season, per_mode, limit)
- compare_players: Compare two players (params: player1_name, player2_name, season)
- get_season_stats: Get player/team season stats (params: entity_type, entity_name, season)
- get_team_standings: Get team standings (params: season, conference)
- get_player_career_information: Get player career info (params: player_name, season)
- get_nba_awards: Get NBA awards (params: award_type, player_name, season)
- get_player_game_stats: Get player game stats (params: player_name, season, last_n_games)
- get_game_context: Get game context for matchup (params: team1_name, team2_name, season)

Output JSON only (no explanation):
{{
  "tools": [
    {{"tool_name": "<name>", "params": {{"param_name": "value"}}}}
  ]
}}

Examples:

Query: "Where does LeBron rank in scoring?" Intent: rankings
Output: {{"tools": [{{"tool_name": "get_league_leaders_info", "params": {{"stat_category": "PTS", "limit": 25}}}}]}}

Query: "LeBron James awards" Intent: awards
Output: {{"tools": [{{"tool_name": "get_nba_awards", "params": {{"player_name": "LeBron James"}}}}]}}

Now generate plan:
Query: "{query}"
Intent: {intent}
Output:"""


# ============================================================================
# JSON VALIDATION (Phase 5.2: P3 - Small Model Compatibility)
# ============================================================================


def validate_and_correct_json(json_str: str) -> Optional[Dict[str, Any]]:
    """
    Validate and attempt to correct malformed JSON from small/open-source LLMs.

    Phase 5.2 (P3): Small Model Compatibility (2025-11-01)

    Small models often generate JSON with formatting issues. This function
    applies progressive fixes to handle common malformations.

    Args:
        json_str: Raw JSON string from LLM response

    Returns:
        Parsed dict if successful, None if uncorrectable

    Common Fixes Applied:
        1. Remove markdown code blocks (```json ... ```)
        2. Fix single quotes → double quotes
        3. Remove trailing commas before } and ]
        4. Quote unquoted keys
        5. Combined fixes (all of the above)

    Examples:
        >>> # Markdown code block
        >>> validate_and_correct_json('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}

        >>> # Single quotes
        >>> validate_and_correct_json("{'key': 'value'}")
        {'key': 'value'}

        >>> # Trailing comma
        >>> validate_and_correct_json('{"key": "value",}')
        {'key': 'value'}

        >>> # Unquoted keys
        >>> validate_and_correct_json('{key: "value"}')
        {'key': 'value'}
    """
    import json
    import re

    if not json_str:
        return None

    # Strip whitespace
    json_str = json_str.strip()

    # Fix 0: Remove markdown code blocks first
    if "```json" in json_str or "```" in json_str:
        json_str = re.sub(r"```json\s*", "", json_str)
        json_str = re.sub(r"```\s*", "", json_str)
        json_str = json_str.strip()

    # Try parsing as-is (fastest path)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Fix 1: Replace single quotes with double quotes
    try:
        fixed = json_str.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Fix 2: Remove trailing commas
    try:
        fixed = re.sub(r",\s*}", "}", json_str)
        fixed = re.sub(r",\s*\]", "]", fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Fix 3: Quote unquoted keys (simple pattern)
    try:
        fixed = re.sub(r'(\w+):', r'"\1":', json_str)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Fix 4: Combined fixes (all at once)
    try:
        fixed = json_str.replace("'", '"')
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*\]", "]", fixed)
        fixed = re.sub(r'(\w+):', r'"\1":', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        logger.warning(f"Could not correct JSON after all fixes: {json_str[:100]}...")
        return None


# ============================================================================
# METRICS TRACKING
# ============================================================================


@dataclass
class LLMMetrics:
    """Track LLM usage statistics."""

    parse_refinement_calls: int = 0
    plan_generation_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


# Global metrics singleton
_metrics = LLMMetrics()


def get_llm_metrics() -> LLMMetrics:
    """Get global LLM metrics."""
    return _metrics


def reset_llm_metrics() -> None:
    """Reset LLM metrics (for testing)."""
    global _metrics
    _metrics = LLMMetrics()


# ============================================================================
# PARSE REFINEMENT
# ============================================================================


async def refine_parse(parsed: ParsedQuery) -> ParsedQuery:
    """
    Refine a low-confidence parse using LLM.

    Args:
        parsed: ParsedQuery with confidence < 0.5

    Returns:
        Refined ParsedQuery with improved confidence (or original if LLM unavailable)

    Phase 3.3: Parse refinement logic
    """
    import time

    _metrics.parse_refinement_calls += 1
    start_time = time.time()

    # Check if LLM fallback enabled
    config = get_llm_config()
    if not config.enabled:
        logger.debug("LLM fallback disabled, returning original parse")
        return parsed

    # Get Ollama client
    client = get_ollama_client()
    if not client.is_healthy():
        logger.warning("Ollama unavailable, returning original parse")
        return parsed

    try:
        # Build prompt
        prompt = PARSE_REFINEMENT_PROMPT.format(query=parsed.raw_query)

        # Invoke Ollama
        logger.info(
            f"Refining parse with LLM (confidence={parsed.confidence:.2f}): '{parsed.raw_query}'"
        )
        response = await client.invoke(prompt)

        if response is None:
            logger.warning("LLM returned None, returning original parse")
            return parsed

        # Parse JSON response (Phase 5.2: P3 - Use robust JSON validation)
        try:
            llm_result = validate_and_correct_json(response)

            if llm_result is None:
                logger.warning("JSON validation failed, returning original parse")
                _metrics.failures += 1
                return parsed

            # Build refined ParsedQuery
            refined = ParsedQuery(
                raw_query=parsed.raw_query,
                intent=llm_result.get("intent", parsed.intent),
                entities=llm_result.get("entities", parsed.entities),
                stat_types=llm_result.get("stat_types", parsed.stat_types),
                time_range=llm_result.get("time_range", parsed.time_range),
                modifiers=parsed.modifiers,  # Keep original modifiers
                confidence=min(
                    llm_result.get("confidence", 0.0) + 0.3, 1.0
                ),  # Boost confidence
            )

            # Track success
            _metrics.successes += 1
            elapsed_ms = (time.time() - start_time) * 1000
            _metrics.total_latency_ms += elapsed_ms

            logger.info(
                f"Parse refined via LLM: {parsed.intent}→{refined.intent}, "
                f"confidence={parsed.confidence:.2f}→{refined.confidence:.2f} ({elapsed_ms:.1f}ms)"
            )

            return refined

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}\nResponse: {response}")
            _metrics.failures += 1
            return parsed

    except Exception as e:
        logger.warning(f"Parse refinement failed: {e}")
        _metrics.failures += 1
        return parsed


# ============================================================================
# PLAN GENERATION
# ============================================================================


async def generate_plan(parsed: ParsedQuery) -> List[ToolCall]:
    """
    Generate execution plan for unknown intent using LLM.

    Args:
        parsed: ParsedQuery with unknown intent

    Returns:
        List of ToolCall objects (or empty list if LLM unavailable)

    Phase 3.4: Plan generation logic
    """
    import time

    _metrics.plan_generation_calls += 1
    start_time = time.time()

    # Check if LLM fallback enabled
    config = get_llm_config()
    if not config.enabled:
        logger.debug("LLM fallback disabled, returning empty plan")
        return []

    # Get Ollama client
    client = get_ollama_client()
    if not client.is_healthy():
        logger.warning("Ollama unavailable, returning empty plan")
        return []

    try:
        # Build prompt
        prompt = PLAN_GENERATION_PROMPT.format(
            query=parsed.raw_query,
            intent=parsed.intent,
            entities=json.dumps(parsed.entities) if parsed.entities else "[]",
        )

        # Invoke Ollama
        logger.info(f"Generating plan with LLM for intent '{parsed.intent}': '{parsed.raw_query}'")
        response = await client.invoke(prompt)

        if response is None:
            logger.warning("LLM returned None, returning empty plan")
            return []

        # Parse JSON response (Phase 5.2: P3 - Use robust JSON validation)
        try:
            llm_result = validate_and_correct_json(response)

            if llm_result is None:
                logger.warning("JSON validation failed, returning empty plan")
                _metrics.failures += 1
                return []

            # Convert to ToolCall objects (Phase 5.2: P3 - Normalize parameters)
            from .planner import normalize_parameters

            tools = llm_result.get("tools", [])
            tool_calls = [
                ToolCall(
                    tool_name=tool["tool_name"],
                    params=normalize_parameters(tool.get("params", {})),  # Apply parameter normalization
                    parallel_group=idx,  # Sequential execution
                )
                for idx, tool in enumerate(tools)
            ]

            # Track success
            _metrics.successes += 1
            elapsed_ms = (time.time() - start_time) * 1000
            _metrics.total_latency_ms += elapsed_ms

            logger.info(
                f"Plan generated via LLM: {len(tool_calls)} tools ({elapsed_ms:.1f}ms)"
            )

            return tool_calls

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}\nResponse: {response}")
            _metrics.failures += 1
            return []

    except Exception as e:
        logger.warning(f"Plan generation failed: {e}")
        _metrics.failures += 1
        return []
