# Week 3 Implementation Plan: NLQ Query Planner with LangGraph

**Date**: 2025-10-28
**Status**: Planning Phase
**Goal**: Build an intelligent query planner that understands natural language NBA questions and orchestrates API calls

---

## Architecture Overview

### LangGraph Pipeline (4 Nodes)

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌────────────┐
│  PARSE  │────▶│  PLAN   │────▶│ EXECUTE │────▶│ SYNTHESIZE │
└─────────┘     └─────────┘     └─────────┘     └────────────┘
     │               │                │                 │
     ▼               ▼                ▼                 ▼
  Extract         Map to          Call MCP         Format
  entities,       tool calls      tools in         final
  stats,          sequence        parallel         answer
  time ranges                     when possible
```

### State Schema

```python
class QueryState(TypedDict):
    # Input
    raw_query: str

    # Parse phase
    entities: List[EntityReference]  # Resolved players/teams
    stat_types: List[str]  # ["PPG", "AST", "TS%"]
    time_range: Optional[TimeRange]  # Season, date range, "tonight"
    query_intent: str  # "comparison", "leaders", "game_context", etc.

    # Plan phase
    tool_calls: List[ToolCall]  # Ordered or parallel tool invocations

    # Execute phase
    tool_results: Dict[str, Any]  # Results from each tool

    # Synthesize phase
    final_answer: str
    confidence: float
    sources: List[str]
```

---

## Component 1: Query Parser

**File**: `nba_mcp/nlq/parser.py`

### Responsibilities
1. Extract entities (players, teams) using existing `entity_resolver`
2. Identify stat categories (points, rebounds, assists, advanced stats)
3. Parse time expressions ("tonight", "this season", "2023-24", "last 10 games")
4. Classify query intent using pattern matching + LLM fallback

### Key Functions

```python
async def parse_query(query: str, llm: Optional[LLM] = None) -> ParsedQuery:
    """
    Parse natural language query into structured components.

    Examples:
        "Who leads the NBA in assists?"
        → intent=leaders, stat=AST, time=current_season

        "Compare LeBron and Curry this season"
        → intent=comparison, entities=[LeBron, Curry], time=2024-25

        "Lakers vs Celtics tonight - who will win?"
        → intent=game_context, entities=[LAL, BOS], time=tonight
    """
```

### Pattern Matching Rules
- **Leaders**: "who leads", "top 5", "best", "leader in"
- **Comparison**: "vs", "compare", "versus", "X or Y"
- **Game context**: "tonight", "today", "game", "matchup"
- **Season stats**: "this season", "2023-24", "career"

---

## Component 2: Execution Planner

**File**: `nba_mcp/nlq/planner.py`

### Responsibilities
1. Map parsed query to sequence of MCP tool calls
2. Identify parallelizable operations (e.g., fetch both players' stats)
3. Handle dependencies (e.g., resolve entity → fetch stats)
4. Apply answer pack templates

### Answer Pack Templates

#### Template 1: Leaders Query
```python
{
    "intent": "leaders",
    "tools": [
        {"name": "get_league_leaders_info", "params": {"stat_category": "{stat}", "season": "{season}"}}
    ],
    "synthesis": "The top {N} {stat} leaders are: {formatted_list}"
}
```

#### Template 2: Head-to-Head Comparison
```python
{
    "intent": "comparison",
    "tools": [
        {"name": "compare_players", "params": {"player1": "{entity1}", "player2": "{entity2}", "season": "{season}"}}
    ],
    "synthesis": "{player1} vs {player2} comparison:\n{formatted_table}"
}
```

#### Template 3: Tonight's Game Context
```python
{
    "intent": "game_context",
    "tools": [
        {"name": "get_live_scores", "params": {"target_date": "{today}"}},
        {"name": "get_team_standings", "params": {}},
        {"name": "get_team_advanced_stats", "params": {"team_name": "{team1}"}},
        {"name": "get_team_advanced_stats", "params": {"team_name": "{team2}"}}
    ],
    "synthesis": "{team1} ({record1}) vs {team2} ({record2})\nKey matchup: {analysis}"
}
```

#### Template 4: Season Comparison
```python
{
    "intent": "season_comparison",
    "tools": [
        {"name": "get_player_advanced_stats", "params": {"player_name": "{player}", "season": "{season1}"}},
        {"name": "get_player_advanced_stats", "params": {"player_name": "{player}", "season": "{season2}"}}
    ],
    "synthesis": "{player}'s {season1} vs {season2}:\n{comparison_table}"
}
```

---

## Component 3: Tool Executor

**File**: `nba_mcp/nlq/executor.py`

### Responsibilities
1. Execute tool calls in optimal order (parallel when possible)
2. Handle errors gracefully (partial results, retries)
3. Aggregate results with metadata (execution time, cache status)

### Key Functions

```python
async def execute_tools(
    tool_calls: List[ToolCall],
    mcp_tools: Dict[str, Callable]
) -> Dict[str, Any]:
    """
    Execute tools with intelligent parallelization.

    Rules:
    - Independent calls → asyncio.gather()
    - Dependent calls → sequential execution
    - Failed calls → log error, continue with partial data
    """
```

---

## Component 4: Response Synthesizer

**File**: `nba_mcp/nlq/synthesizer.py`

### Responsibilities
1. Format tool results into natural language
2. Generate tables for comparisons
3. Add context and analysis
4. Include data sources and confidence scores

### Output Formats

#### Table Format (Comparisons)
```
Player Comparison (2023-24 season, per-75 possessions):

│ Metric       │ LeBron James │ Stephen Curry │ Advantage │
├──────────────┼──────────────┼───────────────┼───────────┤
│ PPG          │ 25.7         │ 26.4          │ Curry     │
│ AST          │ 8.3          │ 5.1           │ LeBron    │
│ True Shot %  │ 0.587        │ 0.670         │ Curry     │
│ Usage %      │ 29.7         │ 31.2          │ Curry     │

Source: NBA API (nba_mcp v1)
```

#### Narrative Format (Game Context)
```
Boston Celtics (37-11, 1st East) vs Los Angeles Lakers (30-18, 6th West)

Recent Form:
- Celtics: 8-2 in last 10, W3 streak
- Lakers: 6-4 in last 10, L1 streak

Key Matchups:
- Jayson Tatum (27.0 PPG, 61.2 TS%) vs LeBron James (25.4 PPG, 58.7 TS%)
- Celtics' #1 defense (110.5 DRtg) vs Lakers' #10 offense (116.2 ORtg)

Prediction: Celtics favored due to home court + better form

Source: NBA API (nba_mcp v1), data as of 2025-10-28 12:45 UTC
```

---

## Component 5: LangGraph Integration

**File**: `nba_mcp/nlq/graph.py`

### Graph Definition

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(QueryState)

# Add nodes
workflow.add_node("parse", parse_node)
workflow.add_node("plan", plan_node)
workflow.add_node("execute", execute_node)
workflow.add_node("synthesize", synthesize_node)

# Define edges
workflow.add_edge("parse", "plan")
workflow.add_edge("plan", "execute")
workflow.add_edge("execute", "synthesize")
workflow.add_edge("synthesize", END)

# Set entry point
workflow.set_entry_point("parse")

# Compile
app = workflow.compile()
```

### Error Handling

```python
# Conditional edges for error recovery
def should_retry(state: QueryState) -> str:
    if state.get("error") and state.get("retry_count", 0) < 3:
        return "retry"
    return "end"

workflow.add_conditional_edges(
    "execute",
    should_retry,
    {"retry": "plan", "end": "synthesize"}
)
```

---

## Component 6: Game Context Composer

**File**: `nba_mcp/nlq/game_context.py`

### Responsibilities
Compose comprehensive game context from multiple sources:
1. Standings (conference rank, games behind)
2. Recent form (last 10, streak)
3. Head-to-head history (if available)
4. Injuries (future: integrate injury API)
5. Betting odds (future: integrate odds API)

### Function Signature

```python
async def get_game_context(
    team1: str,
    team2: str,
    game_date: Optional[str] = None
) -> GameContext:
    """
    Compose comprehensive game context.

    Returns:
        GameContext with standings, form, matchups, prediction
    """
```

---

## Implementation Steps

### Phase 1: Parser (Days 1-2)
- [ ] Create `nba_mcp/nlq/` directory
- [ ] Implement `parser.py` with pattern matching
- [ ] Add time range parsing (season, date, "tonight")
- [ ] Test with 20 sample queries

### Phase 2: Planner (Days 2-3)
- [ ] Implement `planner.py` with answer pack templates
- [ ] Create 4 base templates (leaders, H2H, game context, season comp)
- [ ] Add template matching logic
- [ ] Test tool call generation

### Phase 3: Executor (Days 3-4)
- [ ] Implement `executor.py` with parallel execution
- [ ] Add error handling and partial results
- [ ] Integrate with existing MCP tools
- [ ] Test with mock responses

### Phase 4: Synthesizer (Days 4-5)
- [ ] Implement `synthesizer.py` with table formatting
- [ ] Add narrative generation for context queries
- [ ] Create output templates
- [ ] Test readability

### Phase 5: LangGraph Integration (Days 5-6)
- [ ] Implement `graph.py` with StateGraph
- [ ] Wire up all nodes
- [ ] Add conditional edges for errors
- [ ] End-to-end testing

### Phase 6: Game Context Composer (Days 6-7)
- [ ] Implement `game_context.py`
- [ ] Integrate standings, form, matchups
- [ ] Add analysis/prediction logic
- [ ] Test with live data

---

## Dependencies to Add

```toml
[project]
dependencies = [
    # Existing...
    "langgraph>=0.2.0",  # State machine orchestration
    "langchain-core>=0.3.0",  # LangChain primitives
    "tabulate>=0.9.0",  # Table formatting
    "python-dateutil>=2.8.0",  # Date parsing (already present)
]
```

---

## Testing Strategy

### Unit Tests
- `test_parser.py`: 20 query parsing tests
- `test_planner.py`: Template matching tests
- `test_executor.py`: Parallel execution tests
- `test_synthesizer.py`: Output formatting tests

### Integration Tests
- `test_nlq_pipeline.py`: End-to-end query → answer
- Golden tests with recorded NBA API responses

### Sample Test Queries
1. "Who leads the NBA in assists this season?"
2. "Compare LeBron James and Kevin Durant"
3. "Lakers vs Celtics tonight - who will win?"
4. "Show me Giannis's stats from the 2021 playoffs"
5. "Which team has the best offense this season?"
6. "How did LeBron's 2023 season compare to his 2020 season?"
7. "What happened in the Warriors game last night?"
8. "Top 10 scorers in NBA history"
9. "Bulls record in last 10 games"
10. "Luka Doncic's usage rate vs James Harden"

---

## Success Criteria

- [ ] Parser correctly extracts entities, stats, time ranges for 90% of test queries
- [ ] Planner generates valid tool sequences for all answer pack templates
- [ ] Executor completes parallel calls 2x faster than sequential
- [ ] Synthesizer produces readable, accurate natural language
- [ ] End-to-end latency < 3 seconds for most queries
- [ ] Graceful degradation on API failures (partial answers)

---

## Future Enhancements (Post-Week 3)

1. **LLM Fallback**: Use GPT/Claude for ambiguous queries
2. **Multi-turn Conversations**: Remember context across queries
3. **Query Suggestions**: "Did you mean...?" for typos
4. **Visualization**: Auto-generate charts for comparisons
5. **Streaming Responses**: Show progress as tools execute
6. **Query History**: Learn from common patterns
7. **Caching**: Cache parsed queries and tool plans

---

## Notes

- **Keep it minimal**: Start with pattern matching before adding LLM complexity
- **Fail fast**: Return partial results rather than hanging on errors
- **Measure everything**: Log parsing accuracy, execution time, cache hits
- **User feedback**: Collect queries that fail to parse → improve patterns
