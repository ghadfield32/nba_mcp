# NBA MCP Development Changelog

**Format**: Topic → Status → Details (one-two liner)

---

## WEEK 1: FOUNDATIONS (Error Handling, Standards, CI/CD)

### 1.1 Entity Resolution & Caching ✅ COMPLETED
- [x] **resolve_entity tool**: Universal resolver for players/teams with fuzzy matching (SequenceMatcher)
- [x] **Entity cache**: In-memory LRU cache (1000 entries) via @lru_cache decorator
- [x] **Validation**: Pydantic EntityReference model with confidence scores (0.0-1.0)
- [x] **Suggestions**: Ranked suggestions for ambiguous queries with top-N results

### 1.2 Standard Response Envelope ✅ COMPLETED
- [x] **ResponseEnvelope model**: Unified `{status, data, metadata, errors}` structure
- [x] **Version tagging**: `version="v1"` in ResponseMetadata for all responses
- [x] **Pydantic validation**: ErrorDetail, ResponseMetadata, EntityReference models
- [x] **Helper functions**: success_response(), error_response(), partial_response()
- [x] **Deterministic JSON**: Sorted keys via to_json_string() for stable caching

### 1.3 Error Taxonomy & Resilience ✅ COMPLETED
- [x] **Error classes**: NBAMCPError, EntityNotFoundError, InvalidParameterError, RateLimitError, UpstreamSchemaError, CircuitBreakerOpenError
- [x] **Error codes**: Standardized ErrorCode constants (ENTITY_NOT_FOUND, RATE_LIMIT_EXCEEDED, etc.)
- [x] **Retry decorator**: @retry_with_backoff with exponential backoff (2^n, max 3 retries)
- [x] **Circuit breaker**: CircuitBreaker class (5 failures → 60s timeout → half-open → closed/open)
- [x] **Schema validation**: validate_upstream_schema() for detecting NBA API changes

### 1.4 CI/CD Pipeline ⏳ IN PROGRESS
- [ ] **GitHub Actions**: Lint (black, isort), type-check (mypy), pytest on push/PR
- [ ] **Contract tests**: Validate response schemas against published JSON Schemas
- [ ] **Coverage target**: 70% minimum code coverage with pytest-cov
- [ ] **Pre-commit hooks**: Auto-format and type-check before commits

---

## WEEK 2: CORE DATA COVERAGE

### 2.1 Team Statistics
- [ ] **get_team_standings**: Conference/division standings with W-L, GB, streak, home/away splits
- [ ] **get_team_advanced_stats**: OffRtg, DefRtg, Pace, NetRtg, Four Factors, per-possession stats
- [ ] **Team context**: Last 10 games, strength of schedule, injury impact

### 2.2 Player Advanced Statistics
- [ ] **get_player_advanced_stats**: Usage%, TS%, eFG%, PER, WS, BPM, VORP
- [ ] **Tracking data**: Speed, distance, touches, contested shots (if available)
- [ ] **Shooting splits**: By zone, distance, defender distance

### 2.3 Player Comparisons
- [ ] **compare_players**: Shared metric registry ensuring identical schema per call
- [ ] **Per-possession normalization**: Default per-75 possessions for fair comparison
- [ ] **Era adjustments**: Optional toggle for pace/era-adjusted stats
- [ ] **Deterministic responses**: Stable key ordering, consistent numeric dtypes (float64)

### 2.4 Response Determinism
- [ ] **Key ordering**: Sort all dict keys alphabetically in JSON responses
- [ ] **Stable pagination**: Consistent ordering by primary key (player_id, game_id)
- [ ] **Numeric types**: Force float64 for all percentages, int64 for counts

---

## WEEK 3: NATURAL LANGUAGE QUERY (NLQ) PLANNER

### 3.1 Query Planner Architecture
- [ ] **LangGraph pipeline**: Parse → Plan → Execute → Synthesize workflow
- [ ] **Query parser**: Extract entities (players/teams), time ranges, stat types from natural language
- [ ] **Execution planner**: Map parsed query to sequence of MCP tool calls
- [ ] **Response synthesizer**: Aggregate multi-tool results into coherent answer

### 3.2 Answer Pack Templates
- [ ] **Leaders template**: "Who leads in [stat]?" → `get_league_leaders_info`
- [ ] **H2H template**: "Player A vs Player B" → `compare_players`
- [ ] **Tonight's game**: "What's happening tonight?" → `get_live_scores` + `get_game_context`
- [ ] **Season comparison**: "Compare [player]'s [season1] to [season2]" → multi-season fetch

### 3.3 Context Composition
- [ ] **get_game_context**: Compose standings + recent form + injuries + odds + storylines
- [ ] **Resolver integration**: Auto-resolve ambiguous entities in queries
- [ ] **Fallback handling**: Graceful degradation if data unavailable

---

## WEEK 4: SCALE & OBSERVABILITY

### 4.1 Redis Caching Strategy
- [ ] **Redis integration**: Install `redis>=5.0.0`, `redis-om>=0.2.0`
- [ ] **TTL tiers**: Live=30s, daily=1h, historical=24h, static=7d
- [ ] **Stale-while-revalidate**: Serve cached data while async refresh for high-traffic periods
- [ ] **Cache keys**: Hash of `{tool_name, params, version}` for deterministic invalidation

### 4.2 Rate Limiting
- [ ] **Token bucket**: Per-tool rate limits (e.g., 10/min for live data, 60/min for historical)
- [ ] **Global quota**: Track daily NBA API usage (goal: <10k calls/day)
- [ ] **Backpressure**: Return 429 with `retry_after` when limits exceeded

### 4.3 Monitoring & Telemetry
- [ ] **Prometheus metrics**: Request count, p50/p95/p99 latency, error rate per tool
- [ ] **OpenTelemetry traces**: End-to-end tracing for multi-tool queries
- [ ] **Dashboard**: Grafana dashboard with error drilldowns, cache hit ratio, quota usage
- [ ] **Alerting**: PagerDuty/Slack alerts for >5% error rate or >2s p95 latency

### 4.4 Golden Tests
- [ ] **Top 20 queries**: Capture real NBA API responses for most common queries
- [ ] **Regression suite**: Ensure schema stability across updates
- [ ] **Snapshot testing**: Detect unintended response format changes

---

## CONCRETE IMPROVEMENTS (From User Spec)

### Standardization
- [x] **Response envelope**: `{status, data, metadata, errors}` with Pydantic validation
- [ ] **Schema publishing**: Publish JSON Schemas for GPT/Claude function-calling
- [ ] **Versioning**: Stable tool names + `?v=1` in metadata; v2 alongside v1 for breaking changes

### Live Data Hardening
- [ ] **User-Agent header**: Set `UA="NBA-MCP/v1.0"` and `Referer` for API calls
- [ ] **Schema drift detection**: Validate field presence/shape, raise `UpstreamSchemaChanged` on mismatch
- [ ] **Graceful degradation**: Return partial data if non-critical fields missing

### Shot Charts
- [ ] **Unified get_shot_chart**: Single tool for player/team, season, granularity (basic/hex)
- [ ] **Dual format**: Return both raw coordinates and binned hex data
- [ ] **Visualization**: Optional matplotlib/plotly chart generation

### Advanced Comparisons
- [ ] **Per-possession default**: Normalize to per-75 possessions by default
- [ ] **Era toggle**: Optional era-adjusted stats (pace, scoring environment)
- [ ] **Metric registry**: Shared definition ensuring identical fields

### Game Context
- [ ] **get_game_context composition**: Standings + recent form + injuries + odds + storylines
- [ ] **Resolver integration**: Auto-resolve team names from abbreviations

---

## MAINTENANCE LOG

### 2025-01-28: Week 1 Foundations Implementation
- **Created** nba_mcp/api/models.py: Response envelope (ResponseEnvelope, ErrorDetail, ResponseMetadata) with Pydantic validation
- **Created** nba_mcp/api/errors.py: Error taxonomy (6 exception classes), retry decorator, circuit breaker pattern
- **Created** nba_mcp/api/entity_resolver.py: Fuzzy entity matching with LRU cache (resolve_entity, suggest_players, suggest_teams)
- **Added** resolve_nba_entity MCP tool to nba_server.py (universal player/team resolver with confidence scoring)
- **Updated** pyproject.toml: Added tenacity, redis, prometheus-client, opentelemetry-api, python-dateutil
- **Fixed** FastMCP initialization: Removed unsupported 'path' parameter
- **Tested** All imports and entity resolution working correctly (LeBron James resolved with 0.67 confidence)

### 2025-01-28: Initial Roadmap
- Created comprehensive 4-week improvement roadmap
- Identified 14 high-priority tasks across foundations, coverage, NLQ, scale
- Established CHANGELOG.md for tracking progress

---

## NOTES

**Efficiency Principles**:
1. Reuse existing functions (update in place, don't create "enhanced" versions)
2. Leverage nba_api_utils for all normalization (already has good coverage)
3. Cache aggressively (Redis TTL tiers prevent stale data)
4. Fail fast with clear error codes (better UX than timeouts)
5. Test incrementally (each change validated before moving on)

**Dependencies to Add**:
- `redis>=5.0.0`, `redis-om>=0.2.0` (caching)
- `prometheus-client>=0.19.0` (metrics)
- `opentelemetry-api>=1.22.0` (tracing)
- `tenacity>=8.2.0` (retry logic)
- `pytest-cov>=4.1.0` (coverage)
- `plotly>=5.18.0` (shot charts)
