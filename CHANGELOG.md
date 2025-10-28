# NBA MCP Server - Development Log

## Format
**Feature/Component** → Status → Key Details (1-2 lines)

---

## Recent Updates (October 2025)

### Shot Charts Feature
- **Status**: ✅ Complete
- **Module**: `nba_mcp/api/shot_charts.py` (525 lines)
- **Features**: Raw shot data, hexagonal binning aggregation, zone summaries (paint, mid-range, 3PT)
- **Performance**: <2s cold cache, <100ms warm cache, 4 granularity modes
- **Integration**: Entity resolution, response envelope, caching (HISTORICAL tier), rate limiting (30/min)
- **Testing**: 26 unit tests, coordinate validation, hexbin aggregation, edge cases

### Game Context Composition
- **Status**: ✅ Complete
- **Module**: `nba_mcp/api/game_context.py` (700+ lines)
- **Features**: Multi-source data (standings, advanced stats, form, H2H), auto-generated markdown narratives
- **Performance**: Parallel API execution with asyncio (4x speedup), graceful degradation
- **Narrative**: 5 sections (matchup header, series, form, edge, storylines)
- **Integration**: Entity resolution, retry logic, rate limiting (20/min)

### Era-Adjusted Comparisons
- **Status**: ✅ Complete
- **Module**: `nba_mcp/api/era_adjusted.py` (350 lines)
- **Features**: Cross-era player comparisons with pace and scoring environment adjustments
- **Historical Data**: League averages from 1990s-2020s
- **Use Case**: Fair comparisons (e.g., Michael Jordan vs LeBron James)

---

## Core Features

### Infrastructure & Observability
- **Redis Caching**: 4-tier TTL system (LIVE 30s, DAILY 1h, HISTORICAL 24h, STATIC 7d), 410x speedup
- **Rate Limiting**: Token bucket algorithm, per-tool limits (60/30/20 req/min), global quota (10k/day)
- **Metrics**: Prometheus export, 14 metric types, /metrics endpoint
- **Tracing**: OpenTelemetry support, OTLP export, distributed tracing
- **Grafana**: Pre-built dashboard with 17 panels

### Natural Language Query (NLQ) Pipeline
- **Parser**: `nlq/parser.py` - Pattern-based query parsing, entity extraction, 8 intent types
- **Planner**: `nlq/planner.py` - Maps queries to tool sequences, dependency resolution
- **Executor**: `nlq/executor.py` - Parallel execution, error handling, 1.8x+ speedup
- **Synthesizer**: `nlq/synthesizer.py` - Response formatting as markdown with natural language
- **Pipeline**: End-to-end orchestration (Parse → Plan → Execute → Synthesize)

### API Layer
- **Entity Resolution**: Fuzzy matching (SequenceMatcher), LRU cache (1000 entries), confidence scoring (0.0-1.0)
- **Response Envelope**: Standardized `{status, data, metadata, errors}` structure across all tools
- **Error Handling**: 6 error classes, retry decorator with exponential backoff (max 3 retries), circuit breaker (5 failures → 60s timeout)
- **Schema Validation**: Drift detection for NBA API changes, 3 modes (strict, warn, log)

### Team Statistics
- **Standings**: `get_team_standings` - Conference/division rankings, W-L, GB, streaks, home/away splits
- **Advanced Stats**: `get_team_advanced_stats` - OffRtg, DefRtg, Pace, NetRtg, Four Factors
- **Game Logs**: `get_date_range_game_log_or_team_game_log` - Historical game data with date filtering

### Player Statistics
- **Career Stats**: `get_player_career_information` - Multi-season career data with entity resolution
- **Advanced Stats**: `get_player_advanced_stats` - Usage%, TS%, eFG%, PIE, OffRtg, DefRtg, NetRtg, AST%, REB%, TOV%
- **Comparisons**: `compare_players` - Head-to-head with 22 metric registry
- **Era-Adjusted**: `compare_players_era_adjusted` - Cross-era comparisons with pace/scoring adjustments

### Live Data
- **Live Scores**: `get_live_scores` - Real-time game scores with broadcast timing
- **Play-by-Play**: `play_by_play` - Detailed game action data
- **Scoreboards**: Multi-date scoreboard queries with lookback

### League Data
- **Leaders**: `get_league_leaders_info` - League leaders by stat category, per-mode filtering
- **Static Data**: Player/team lookups, ID resolution

### Schemas & Standards
- **Parameter Models**: 12 Pydantic models for all MCP tools (`schemas/tool_params.py`)
- **OpenAPI Spec**: Complete OpenAPI 3.1.0 specification at `schemas/openapi.yaml`
- **Version Tracking**: Response schema versioning (format: YYYY-MM)
- **Headers**: Professional User-Agent and Referer for NBA API requests (`api/headers.py`)

---

## Testing & Validation

### Test Coverage
- **Unit Tests**: Core functionality, entity resolution, response envelopes, error handling
- **Integration Tests**: NBA API connectivity, multi-endpoint workflows
- **Golden Tests**: 20 query patterns covering all major features
- **Validation Script**: `run_validation.py` - 23 automated tests

### CI/CD
- **GitHub Actions**: Lint (black, isort), type-check (mypy), pytest on push/PR
- **Coverage**: Target 70%+ with pytest-cov
- **Pre-commit**: Auto-format and type-check

---

## Configuration

### Environment Variables
- **Server**: `NBA_MCP_PORT`, `NBA_MCP_LOG_LEVEL`
- **Redis**: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `ENABLE_REDIS_CACHE`
- **Rate Limits**: `NBA_MCP_DAILY_QUOTA`, `NBA_MCP_SIMPLE_RATE_LIMIT`, `NBA_MCP_COMPLEX_RATE_LIMIT`
- **Observability**: `ENABLE_METRICS`, `ENABLE_TRACING`, `OTLP_ENDPOINT`
- **Headers**: `NBA_MCP_USER_AGENT`, `NBA_MCP_REFERER`
- **Validation**: `ENABLE_SCHEMA_VALIDATION`

### Dual Mode Support
- **Claude Mode**: Port 8000 - Optimized for Claude Desktop MCP integration
- **Local Mode**: Port 8001 - For Ollama and other local LLMs

---

## Performance Benchmarks

### Caching
- **Cold Cache**: 820ms average response time
- **Warm Cache**: 2ms average response time
- **Speedup**: 410x with Redis

### API Execution
- **Sequential**: ~2s for 4 API calls
- **Parallel**: ~500ms for 4 API calls
- **Speedup**: 4x with asyncio.gather

### Rate Limits
- **Simple Tools**: 60 requests/minute
- **Complex Tools**: 30 requests/minute
- **Multi-API Tools**: 20 requests/minute
- **Daily Quota**: 10,000 requests

---

## Dependencies

### Core
- Python ≥ 3.10
- nba_api ≥ 1.9.0
- fastmcp ≥ 2.2.0
- pandas ≥ 2.2.3
- pydantic ≥ 2.11.3

### Infrastructure
- redis (optional, for caching)
- prometheus-client (for metrics)
- opentelemetry-api (for tracing)

### Development
- pytest ≥ 7.0.0
- black (code formatting)
- isort (import sorting)
- mypy (type checking)
- flake8 (linting)

---

## Architecture Summary

```
NBA MCP Server
├── nba_server.py           # FastMCP server (dual-mode: Claude/Local)
├── api/                    # Core API layer
│   ├── client.py           # NBA API wrapper
│   ├── advanced_stats.py   # Team/player analytics
│   ├── entity_resolver.py  # Fuzzy matching
│   ├── shot_charts.py      # Shot visualization data
│   ├── game_context.py     # Multi-source composition
│   ├── era_adjusted.py     # Cross-era adjustments
│   ├── errors.py           # Error taxonomy & resilience
│   ├── models.py           # Pydantic models
│   └── tools/              # API utilities
├── nlq/                    # Natural language pipeline
│   ├── parser.py           # Query parsing
│   ├── planner.py          # Query planning
│   ├── executor.py         # Parallel execution
│   └── synthesizer.py      # Response formatting
├── cache/                  # Redis caching (4 TTL tiers)
├── rate_limit/             # Token bucket rate limiting
├── observability/          # Metrics & tracing
└── schemas/                # Pydantic models & OpenAPI
```

---

## Known Issues & Limitations

### NBA API
- **Flakiness**: Official NBA API can be unreliable, automatic retries implemented
- **Rate Limits**: Undocumented limits, conservative rate limiting applied
- **Schema Changes**: Occasional upstream changes, schema validation helps detect

### Caching
- **Redis Required**: Full performance benefits require Redis server
- **Memory**: Large responses can consume significant cache memory

### Testing
- **API Dependencies**: Some tests require live NBA API access, may be flaky
- **Seasonal Data**: Some queries only valid during NBA season

---

## Future Enhancements

### Planned Features
- [ ] Player injury reports and status
- [ ] Team roster and depth charts
- [ ] Advanced shooting metrics (catch-and-shoot, pull-up, etc.)
- [ ] Playoff bracket and series tracking
- [ ] Historical season comparisons
- [ ] Video highlight links (if available via API)

### Infrastructure
- [ ] GraphQL endpoint option
- [ ] WebSocket support for live updates
- [ ] Multi-region caching
- [ ] Enhanced circuit breaker patterns
- [ ] Automated performance regression testing

---

## Version History

### v0.5.0 (October 2025)
- Added shot charts with hexagonal binning
- Added game context composition with narrative synthesis
- Added era-adjusted player comparisons
- Implemented comprehensive observability (metrics, tracing, Grafana)
- Added Redis caching with 4-tier TTL system
- Implemented token bucket rate limiting
- Created golden test suite

### v0.4.0 (April 2025)
- Natural language query pipeline
- Entity resolution with fuzzy matching
- Response envelope standardization
- Error taxonomy and resilience patterns
- Schema validation and versioning

### v0.3.0 (March 2025)
- Team advanced statistics
- Player advanced statistics
- Player comparisons
- League leaders

### v0.2.0 (February 2025)
- Live scores and play-by-play
- Team and player game logs
- Date range queries

### v0.1.0 (January 2025)
- Initial MCP server implementation
- Basic player and team statistics
- FastMCP integration
