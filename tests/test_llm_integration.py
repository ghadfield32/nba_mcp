"""
LLM Integration Tests for NBA MCP NLQ Pipeline.

Tests LLM fallback functionality including:
- Config loading from environment
- Ollama client initialization and health checks
- Parse refinement (low confidence → LLM boost)
- Plan generation (unknown intent → tool calls)
- JSON validation for small model compatibility
- Graceful degradation when Ollama unavailable

Phase 6: Testing & Validation (2025-11-02)

Run with:
    pytest tests/test_llm_integration.py -v

Skip if Ollama unavailable:
    pytest tests/test_llm_integration.py -v -k "not requires_ollama"
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import asdict

from nba_mcp.nlq.llm_fallback import (
    LLMConfig,
    OllamaClient,
    get_llm_config,
    get_ollama_client,
    validate_and_correct_json,
    refine_parse,
    generate_plan,
    get_llm_metrics,
    reset_llm_metrics,
    PARSE_REFINEMENT_PROMPT,
    PLAN_GENERATION_PROMPT,
)
from nba_mcp.nlq.parser import ParsedQuery
from nba_mcp.nlq.planner import ToolCall


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset LLM metrics before each test."""
    reset_llm_metrics()
    yield
    reset_llm_metrics()


@pytest.fixture
def mock_env_enabled():
    """Mock environment with LLM enabled."""
    with patch.dict(os.environ, {
        "NBA_MCP_ENABLE_LLM_FALLBACK": "true",
        "NBA_MCP_LLM_MODEL": "llama3.2:3b",
        "NBA_MCP_LLM_URL": "http://localhost:11434",
        "NBA_MCP_LLM_TIMEOUT": "5"
    }):
        yield


@pytest.fixture
def mock_env_disabled():
    """Mock environment with LLM disabled."""
    with patch.dict(os.environ, {
        "NBA_MCP_ENABLE_LLM_FALLBACK": "false"
    }):
        yield


@pytest.fixture
def sample_parsed_query():
    """Sample ParsedQuery for testing."""
    return ParsedQuery(
        raw_query="Who leads the NBA in scoring?",
        intent="leaders",
        entities=[],
        stat_types=["PTS"],
        time_range={},
        modifiers={},
        confidence=0.4  # Low confidence to trigger refinement
    )


@pytest.fixture
def sample_unknown_intent_query():
    """Sample ParsedQuery with unknown intent."""
    return ParsedQuery(
        raw_query="Show me hot players right now",
        intent="unknown",
        entities=[],
        stat_types=[],
        time_range={},
        modifiers={},
        confidence=0.3
    )


# ============================================================================
# CONFIG TESTS
# ============================================================================

def test_llm_config_from_env_defaults():
    """Test LLMConfig loads defaults when env vars not set."""
    with patch.dict(os.environ, {}, clear=True):
        config = LLMConfig.from_env()

        assert config.model == "llama3.2:3b"
        assert config.url == "http://localhost:11434"
        assert config.enabled is True  # Default is enabled
        assert config.timeout == 5


def test_llm_config_from_env_custom(mock_env_enabled):
    """Test LLMConfig loads from environment variables."""
    config = LLMConfig.from_env()

    assert config.model == "llama3.2:3b"
    assert config.url == "http://localhost:11434"
    assert config.enabled is True
    assert config.timeout == 5


def test_llm_config_disabled(mock_env_disabled):
    """Test LLMConfig respects disabled flag."""
    config = LLMConfig.from_env()

    assert config.enabled is False


# ============================================================================
# OLLAMA CLIENT TESTS
# ============================================================================

def test_ollama_client_lazy_initialization():
    """Test Ollama client lazy initialization."""
    config = LLMConfig(
        model="llama3.2:3b",
        url="http://localhost:11434",
        enabled=True,
        timeout=5
    )
    client = OllamaClient(config)

    # Client should not be initialized yet
    assert client._client is None
    assert client._healthy is None


def test_ollama_client_disabled():
    """Test Ollama client respects disabled config."""
    config = LLMConfig(
        model="llama3.2:3b",
        url="http://localhost:11434",
        enabled=False,  # Disabled
        timeout=5
    )
    client = OllamaClient(config)

    # Initialization should fail gracefully
    assert not client._initialize()
    assert not client.is_healthy()


@pytest.mark.asyncio
async def test_ollama_client_invoke_when_disabled():
    """Test invoke returns None when LLM disabled."""
    config = LLMConfig(
        model="llama3.2:3b",
        url="http://localhost:11434",
        enabled=False,
        timeout=5
    )
    client = OllamaClient(config)

    result = await client.invoke("test prompt")
    assert result is None


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_ollama_client_invoke_success(mock_chat_ollama):
    """Test successful Ollama invocation."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.content = '{"intent": "leaders"}'

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    config = LLMConfig(
        model="llama3.2:3b",
        url="http://localhost:11434",
        enabled=True,
        timeout=5
    )
    client = OllamaClient(config)

    result = await client.invoke("test prompt")

    assert result == '{"intent": "leaders"}'
    assert mock_instance.invoke.called


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_ollama_client_invoke_failure(mock_chat_ollama):
    """Test Ollama invocation failure handling."""
    # Mock invocation failure
    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(side_effect=Exception("Connection failed"))
    mock_chat_ollama.return_value = mock_instance

    config = LLMConfig(
        model="llama3.2:3b",
        url="http://localhost:11434",
        enabled=True,
        timeout=5
    )
    client = OllamaClient(config)

    result = await client.invoke("test prompt")

    assert result is None
    # Metrics should track failure
    metrics = get_llm_metrics()
    assert metrics.failures == 1


# ============================================================================
# JSON VALIDATION TESTS
# ============================================================================

def test_json_validation_valid():
    """Test validation passes for valid JSON."""
    valid_json = '{"intent": "leaders", "confidence": 0.9}'
    result = validate_and_correct_json(valid_json)

    assert result is not None
    assert result["intent"] == "leaders"
    assert result["confidence"] == 0.9


def test_json_validation_markdown_code_block():
    """Test validation removes markdown code blocks."""
    markdown_json = '''```json
{
  "intent": "leaders",
  "confidence": 0.9
}
```'''
    result = validate_and_correct_json(markdown_json)

    assert result is not None
    assert result["intent"] == "leaders"


def test_json_validation_single_quotes():
    """Test validation fixes single quotes."""
    single_quote_json = "{'intent': 'leaders', 'confidence': 0.9}"
    result = validate_and_correct_json(single_quote_json)

    assert result is not None
    assert result["intent"] == "leaders"


def test_json_validation_trailing_comma():
    """Test validation removes trailing commas."""
    trailing_comma_json = '{"intent": "leaders", "confidence": 0.9,}'
    result = validate_and_correct_json(trailing_comma_json)

    assert result is not None
    assert result["intent"] == "leaders"


def test_json_validation_unquoted_keys():
    """Test validation quotes unquoted keys."""
    unquoted_json = '{intent: "leaders", confidence: 0.9}'
    result = validate_and_correct_json(unquoted_json)

    assert result is not None
    assert result["intent"] == "leaders"


def test_json_validation_combined_fixes():
    """Test validation handles multiple issues."""
    messy_json = """```json
{
  intent: 'leaders',
  confidence: 0.9,
}
```"""
    result = validate_and_correct_json(messy_json)

    assert result is not None
    assert result["intent"] == "leaders"


def test_json_validation_uncorrectable():
    """Test validation returns None for uncorrectable JSON."""
    invalid_json = "this is not JSON at all"
    result = validate_and_correct_json(invalid_json)

    assert result is None


# ============================================================================
# PARSE REFINEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_refine_parse_disabled(mock_env_disabled, sample_parsed_query):
    """Test parse refinement returns original when disabled."""
    with patch("nba_mcp.nlq.llm_fallback._config", None):  # Reset config
        result = await refine_parse(sample_parsed_query)

        assert result == sample_parsed_query
        assert result.confidence == 0.4  # Unchanged


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_refine_parse_success(mock_chat_ollama, sample_parsed_query):
    """Test successful parse refinement."""
    # Mock successful LLM response
    mock_response = MagicMock()
    mock_response.content = '''{"intent": "leaders", "entities": [], "stat_types": ["PTS"], "confidence": 0.7}'''

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    # Reset config to force re-initialization
    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await refine_parse(sample_parsed_query)

                assert result.intent == "leaders"
                assert result.confidence > 0.4  # Boosted confidence

                # Metrics should track success
                metrics = get_llm_metrics()
                assert metrics.parse_refinement_calls == 1
                assert metrics.successes == 1


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_refine_parse_llm_returns_none(mock_chat_ollama, sample_parsed_query):
    """Test parse refinement handles LLM returning None."""
    mock_instance = MagicMock()
    mock_instance.invoke = AsyncMock(return_value=None)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await refine_parse(sample_parsed_query)

                assert result == sample_parsed_query  # Returns original


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_refine_parse_invalid_json(mock_chat_ollama, sample_parsed_query):
    """Test parse refinement handles invalid JSON response."""
    mock_response = MagicMock()
    mock_response.content = "this is not valid JSON"

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await refine_parse(sample_parsed_query)

                assert result == sample_parsed_query  # Returns original

                # Metrics should track failure
                metrics = get_llm_metrics()
                assert metrics.failures == 1


# ============================================================================
# PLAN GENERATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_plan_disabled(mock_env_disabled, sample_unknown_intent_query):
    """Test plan generation returns empty when disabled."""
    with patch("nba_mcp.nlq.llm_fallback._config", None):
        result = await generate_plan(sample_unknown_intent_query)

        assert result == []


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_generate_plan_success(mock_chat_ollama, sample_unknown_intent_query):
    """Test successful plan generation."""
    # Mock successful LLM response
    mock_response = MagicMock()
    mock_response.content = '''{
        "tools": [
            {"tool_name": "get_league_leaders_info", "params": {"stat_category": "PTS", "limit": 10}}
        ]
    }'''

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await generate_plan(sample_unknown_intent_query)

                assert len(result) == 1
                assert isinstance(result[0], ToolCall)
                assert result[0].tool_name == "get_league_leaders_info"
                assert result[0].params["stat_category"] == "PTS"

                # Metrics should track success
                metrics = get_llm_metrics()
                assert metrics.plan_generation_calls == 1
                assert metrics.successes == 1


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_generate_plan_multiple_tools(mock_chat_ollama, sample_unknown_intent_query):
    """Test plan generation with multiple tools."""
    mock_response = MagicMock()
    mock_response.content = '''{
        "tools": [
            {"tool_name": "get_league_leaders_info", "params": {"stat_category": "PTS"}},
            {"tool_name": "get_team_standings", "params": {"conference": "East"}}
        ]
    }'''

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await generate_plan(sample_unknown_intent_query)

                assert len(result) == 2
                assert result[0].tool_name == "get_league_leaders_info"
                assert result[1].tool_name == "get_team_standings"


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_generate_plan_llm_returns_none(mock_chat_ollama, sample_unknown_intent_query):
    """Test plan generation handles LLM returning None."""
    mock_instance = MagicMock()
    mock_instance.invoke = AsyncMock(return_value=None)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await generate_plan(sample_unknown_intent_query)

                assert result == []


@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_generate_plan_invalid_json(mock_chat_ollama, sample_unknown_intent_query):
    """Test plan generation handles invalid JSON."""
    mock_response = MagicMock()
    mock_response.content = "not valid JSON"

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                result = await generate_plan(sample_unknown_intent_query)

                assert result == []

                # Metrics should track failure
                metrics = get_llm_metrics()
                assert metrics.failures == 1


# ============================================================================
# METRICS TESTS
# ============================================================================

def test_metrics_initialization():
    """Test LLM metrics start at zero."""
    metrics = get_llm_metrics()

    assert metrics.parse_refinement_calls == 0
    assert metrics.plan_generation_calls == 0
    assert metrics.successes == 0
    assert metrics.failures == 0
    assert metrics.total_latency_ms == 0.0


def test_metrics_reset():
    """Test metrics can be reset."""
    metrics = get_llm_metrics()

    # Simulate some activity
    metrics.parse_refinement_calls = 5
    metrics.successes = 3
    metrics.failures = 2

    # Reset
    reset_llm_metrics()

    metrics = get_llm_metrics()
    assert metrics.parse_refinement_calls == 0
    assert metrics.successes == 0
    assert metrics.failures == 0


def test_metrics_to_dict():
    """Test metrics conversion to dictionary."""
    metrics = get_llm_metrics()
    metrics.parse_refinement_calls = 5
    metrics.successes = 3

    result = metrics.to_dict()

    assert result["parse_refinement_calls"] == 5
    assert result["successes"] == 3
    assert "failures" in result


# ============================================================================
# PROMPT TEMPLATE TESTS
# ============================================================================

def test_parse_refinement_prompt_format():
    """Test parse refinement prompt formatting."""
    query = "Who leads the NBA in scoring?"
    prompt = PARSE_REFINEMENT_PROMPT.format(query=query)

    assert "Who leads the NBA in scoring?" in prompt
    assert "leaders" in prompt
    assert "PTS" in prompt
    assert "JSON" in prompt


def test_plan_generation_prompt_format():
    """Test plan generation prompt formatting."""
    query = "Show me hot players"
    prompt = PLAN_GENERATION_PROMPT.format(
        query=query,
        intent="unknown",
        entities="[]"
    )

    assert "Show me hot players" in prompt
    assert "unknown" in prompt
    assert "get_league_leaders_info" in prompt
    assert "JSON" in prompt


# ============================================================================
# END-TO-END INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
@patch("nba_mcp.nlq.llm_fallback.ChatOllama")
async def test_full_pipeline_with_llm_fallback(mock_chat_ollama):
    """Test full NLQ pipeline with LLM fallback."""
    # Mock successful parse refinement
    mock_response = MagicMock()
    mock_response.content = '''{
        "intent": "leaders",
        "entities": [],
        "stat_types": ["PTS"],
        "confidence": 0.8
    }'''

    mock_instance = MagicMock()
    mock_instance.invoke = MagicMock(return_value=mock_response)
    mock_chat_ollama.return_value = mock_instance

    # Create low-confidence query
    query = ParsedQuery(
        raw_query="Who's scoring a lot?",
        intent="unknown",
        entities=[],
        stat_types=[],
        time_range={},
        modifiers={},
        confidence=0.3
    )

    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch("nba_mcp.nlq.llm_fallback._ollama_client", None):
            with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "true"}):
                # Refine parse
                refined = await refine_parse(query)

                assert refined.intent == "leaders"
                assert refined.confidence > 0.3
                assert "PTS" in refined.stat_types


@pytest.mark.asyncio
async def test_graceful_degradation_when_ollama_unavailable():
    """Test pipeline gracefully degrades when Ollama unavailable."""
    query = ParsedQuery(
        raw_query="Who leads the NBA?",
        intent="leaders",
        entities=[],
        stat_types=["PTS"],
        time_range={},
        modifiers={},
        confidence=0.3  # Low confidence
    )

    # Disable LLM fallback
    with patch("nba_mcp.nlq.llm_fallback._config", None):
        with patch.dict(os.environ, {"NBA_MCP_ENABLE_LLM_FALLBACK": "false"}):
            result = await refine_parse(query)

            # Should return original query unchanged
            assert result == query
            assert result.confidence == 0.3


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
