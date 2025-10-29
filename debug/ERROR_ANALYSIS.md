# NBA MCP Query Errors - Root Cause Analysis

## Executive Summary

Debug script revealed **4 distinct root causes** across 5 failed tests:
- **1 test passed** (LeBron home games) ✅
- **4 tests failed** due to systematic issues ❌

## Test Results Summary

| Test | Status | Root Cause |
|------|--------|-----------|
| LeBron last 5 home | ✅ PASS | N/A |
| Curry shot chart | ❌ FAIL | Wrong import path |
| Durant monthly | ❌ FAIL | Wrong column name |
| Warriors home | ❌ FAIL | Wrong method name |
| All players | ❌ FAIL | Wrong import path |
| NLQ queries | ⚠️ PARTIAL | Tool registry missing |

---

## Issue 1: NLQ Tool Registry Missing Tools

### Error Message:
```
ERROR - Tool 'get_player_advanced_stats' not found in registry
```

### What Happened:
1. User query: "Show me LeBron James last 5 game averages at home"
2. NLQ parser correctly identified intent: `player_stats` ✅
3. NLQ planner generated tool call: `get_player_advanced_stats` ✅
4. NLQ executor tried to find tool in registry: ❌ **TOOL NOT FOUND**
5. Tool execution failed silently
6. Response returned with `confidence=0.70` and incomplete data

### Root Cause:
The NLQ tool registry (`nba_mcp/nlq/tool_registry.py`) does not have all the tools registered that the planner is trying to use.

**Expected**: Tool registry should contain all tools that the planner can generate
**Actual**: Tool registry is missing `get_player_advanced_stats` and possibly others

### Code Location:
- **Planner**: `nba_mcp/nlq/planner.py` (generates tool calls)
- **Executor**: `nba_mcp/nlq/executor.py` (tries to execute tools)
- **Registry**: `nba_mcp/nlq/tool_registry.py` (maps tool names to functions)

### Why This Causes the Original Error:
The NLQ pipeline returns a `SynthesizedResponse` object (dataclass) with `.to_dict()` method.
However, when tools fail, the synthesizer might return a string error message instead.
When the calling code tries to call `.get()` on this string, we get:
```
AttributeError: 'str' object has no attribute 'get'
```

### Step-by-Step Trace:
1. `answer_nba_question("query")` called (pipeline.py:24)
2. Parse → Plan → Execute (lines 54-73)
3. Execute fails because tool not in registry
4. Synthesize creates response with `all_success=False`
5. Returns SynthesizedResponse object
6. But somewhere downstream, code expects dict and calls `.get()`

### Debug Evidence:
```
2025-10-29 17:00:12,220 - ERROR - Tool 'get_player_advanced_stats' not found in registry
2025-10-29 17:00:12,220 - INFO - Plan execution complete: 1 results, all_success=False, time=0.2ms
2025-10-29 17:00:12,220 - INFO - Synthesis complete: 115 chars, confidence=0.70
```

---

## Issue 2: Wrong Import Path for NBA Stats API

### Error Message:
```
ModuleNotFoundError: No module named 'nba_stats_api'
```

### What Happened:
Code attempted to import:
```python
from nba_stats_api.stats_api import get_player_shotchart
from nba_stats_api.stats_api import get_league_leaders
```

### Root Cause:
The module is actually part of the `nba_mcp` package, not a separate `nba_stats_api` package.

**Expected**: Import from `nba_mcp.api.client` or direct NBA API wrapper
**Actual**: Trying to import from non-existent package

### Correct Approach:
```python
# WRONG:
from nba_stats_api.stats_api import get_player_shotchart

# CORRECT:
from nba_mcp.api.client import NBAApiClient
client = NBAApiClient()
shot_data = await client.get_player_shot_chart(...)
```

### Affected Tests:
- Test 2: Curry shot chart
- Test 5: All players data

---

## Issue 3: Wrong DataFrame Column Name

### Error Message:
```
KeyError: "Column(s) ['GAME_ID'] do not exist"
```

### What Happened:
Code tried to count games using:
```python
game_log.groupby('MONTH').agg({
    'PTS': 'mean',
    'REB': 'mean',
    'AST': 'mean',
    'FG_PCT': 'mean',
    'GAME_ID': 'count'  # ❌ Column doesn't exist
})
```

### Root Cause:
The game log DataFrame doesn't have a column named 'GAME_ID'.

### Debug Steps Needed:
1. Check actual column names in game log DataFrame
2. Find correct column to use for counting games
3. Alternatives: Use any column with `.size()` or `'PTS': 'count'`

### Correct Approach:
```python
# Option 1: Use .size()
monthly_stats = game_log.groupby('MONTH').agg({
    'PTS': ['mean', 'count'],  # count PTS instead
    'REB': 'mean',
    'AST': 'mean',
    'FG_PCT': 'mean'
})

# Option 2: Use index
monthly_stats = game_log.groupby('MONTH').agg({
    'PTS': 'mean',
    'REB': 'mean',
    'AST': 'mean',
    'FG_PCT': 'mean'
})
monthly_stats['GAMES'] = game_log.groupby('MONTH').size()
```

### Affected Tests:
- Test 3: Durant monthly progression

---

## Issue 4: Wrong Method Name for Team Game Log

### Error Message:
```
AttributeError: 'NBAApiClient' object has no attribute 'get_team_game_log'
Did you mean: 'get_league_game_log'?
```

### What Happened:
Code tried to call:
```python
game_log = await client.get_team_game_log(team_name="Warriors", season="2023-24")
```

### Root Cause:
The method name doesn't exist in NBAApiClient.

### Debug Steps Needed:
1. Check NBAApiClient for correct method name
2. Options mentioned by Python: `get_league_game_log`
3. Check if there's a team-specific method or if we need to filter league log

### Correct Approach (Need to verify):
```python
# Option 1: Use get_date_range_game_log_or_team_game_log with team filter
game_log = await client.get_date_range_game_log_or_team_game_log(
    season="2023-24",
    team="Warriors"
)

# Option 2: Use league log and filter
from nba_stats_api import get_team_game_log  # If it exists
```

### Affected Tests:
- Test 4: Warriors home performance

---

## What Worked Successfully ✅

### Test 1: LeBron's Last 5 Home Games
**Status**: ✅ PASSED

**Results**:
- Total games: 70
- Home games found: 34 (using `vs\.` regex - our earlier fix!)
- Last 5 home games:
  - PPG: 21.4
  - RPG: 4.6
  - APG: 6.6
  - FG%: 51.9%
  - 3P%: 43.2%

**Why It Worked**:
- Used NBAApiClient directly (not through NLQ pipeline)
- Used correct method names
- Used correct regex for home game detection (`vs\.`)
- DataFrame operations worked correctly

**Key Takeaway**: The core client functionality works perfectly. Issues are in:
1. NLQ tool registry
2. Import paths in utility scripts
3. Method/column name inconsistencies

---

## Detailed Error Trace Timeline

### NLQ Query Processing Flow:

```
User Query
    ↓
[1] parse_query() ✅ SUCCESS
    ├─ Intent: player_stats
    ├─ Entity: LeBron James
    └─ Confidence: 1.00
    ↓
[2] plan_query_execution() ✅ SUCCESS
    ├─ Template: player_stats
    ├─ Tool: get_player_advanced_stats
    └─ Params: {player_name, season}
    ↓
[3] execute_plan() ❌ FAILURE
    ├─ Tool lookup in registry
    ├─ ERROR: Tool not found
    └─ Returns: all_success=False
    ↓
[4] synthesize_response() ⚠️ PARTIAL
    ├─ Returns SynthesizedResponse object
    ├─ confidence=0.70 (reduced due to failure)
    └─ Answer: "Unable to synthesize..." (115 chars)
    ↓
[5] Return to caller
    └─ Type: dict (from .to_dict())
```

### Where the `.get()` Error Happens:

Somewhere in the calling code (likely in nba_server.py or a formatter), the code expects a dict and calls:
```python
result = await answer_nba_question(query, return_metadata=False)
# result should be a string, but error handling might return dict
# Calling code might do: result.get('answer')
# But if result is actually a string due to error, we get:
# AttributeError: 'str' object has no attribute 'get'
```

---

## Recommended Fixes (Priority Order)

### Priority 1: Fix NLQ Tool Registry
**File**: `nba_mcp/nlq/tool_registry.py`
**Action**:
1. Read the file to see what tools are registered
2. Add missing tools that planner generates:
   - `get_player_advanced_stats`
   - `get_player_performance_splits` (if used)
   - Others identified in planner templates
3. Ensure registry matches planner templates 1:1

### Priority 2: Fix Column Names
**File**: `debug/debug_mcp_queries.py` (or wherever used)
**Action**:
1. Print actual column names from game log
2. Replace 'GAME_ID' with correct column or use `.size()`
3. Update all groupby aggregations

### Priority 3: Fix Import Paths
**Files**: Various scripts/tests
**Action**:
1. Replace `from nba_stats_api` with `from nba_mcp.api.client`
2. Update function calls to match NBAApiClient methods
3. Ensure consistent import pattern across codebase

### Priority 4: Fix Method Names
**Files**: Various scripts using team game logs
**Action**:
1. Check NBAApiClient for correct method
2. Replace `get_team_game_log` with correct method
3. Document correct method names in API reference

---

## Next Steps for Complete Fix

1. **Investigate Tool Registry**
   ```python
   # Read nba_mcp/nlq/tool_registry.py
   # Check what tools are registered
   # Add missing tools
   ```

2. **Check DataFrame Columns**
   ```python
   game_log = await client.get_player_game_log(...)
   print(game_log.columns.tolist())
   # Identify correct column names
   ```

3. **Check NBAApiClient Methods**
   ```python
   # List all methods in NBAApiClient
   print([m for m in dir(NBAApiClient) if not m.startswith('_')])
   # Find correct method for team game logs
   ```

4. **Create Corrected Implementation**
   - Fix each issue systematically
   - Test each fix independently
   - Run full debug suite again
   - Verify all 6 tests pass

---

## Impact Assessment

### Current State:
- ❌ NLQ queries fail silently (bad UX)
- ❌ Users get cryptic "AttributeError: 'str' object has no attribute 'get'"
- ✅ Direct client usage works perfectly
- ⚠️ Documentation doesn't match implementation

### After Fixes:
- ✅ NLQ queries will work end-to-end
- ✅ All user requests can be fulfilled
- ✅ Error messages will be clear and actionable
- ✅ Documentation will match implementation

### Estimated Fix Complexity:
- Tool Registry: **EASY** (add missing mappings)
- Column Names: **TRIVIAL** (change string literal)
- Import Paths: **EASY** (find/replace)
- Method Names: **EASY** (lookup and replace)

**Total Estimated Time**: 30-60 minutes for all fixes + testing

---

## Lessons Learned

1. **Root Cause vs Symptom**: The "AttributeError: 'str' object has no attribute 'get'" was a symptom, not the root cause
2. **Debug Script Value**: Creating systematic debug script revealed all issues in one run
3. **Tool Registry Importance**: NLQ pipeline requires strict registry-planner synchronization
4. **Direct Client Works**: Core API client is solid; issues are in abstraction layers
5. **Test Coverage**: Need integration tests that exercise NLQ pipeline end-to-end

---

## Files to Modify (Summary)

1. `nba_mcp/nlq/tool_registry.py` - Add missing tools
2. `debug/debug_mcp_queries.py` - Fix imports, columns, methods
3. Any scripts using team game logs - Fix method name
4. Any scripts importing nba_stats_api - Fix import path

---

**Generated**: 2025-10-29 17:00:12 UTC
**Debug Log**: `debug/debug_mcp_queries.log`
