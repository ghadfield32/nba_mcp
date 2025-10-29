# NBA MCP Server - Development Log

## Format
**Feature/Component** → Status → Key Details (1-2 lines)

---

## Recent Updates (October 2025)

### NBA API Bug Fix - WinProbability KeyError - Complete ✅
- **Status**: ✅ Fixed (2025-10-29)
- **Issue**: Play-by-play API calls failing with `KeyError: 'WinProbability'` for games on 2025-10-28
- **Root Cause**: `nba_api` library assumes NBA API always returns `WinProbability` dataset, but recent games don't include it
- **Solution**: Monkey patch to make `WinProbability` optional in `ScoreboardV2` endpoint
- **Files**:
  - NEW: [`nba_mcp/api/nba_api_patches.py`](nba_mcp/api/nba_api_patches.py) - Centralized nba_api bug fixes
  - MODIFIED: [`playbyplayv3_or_realtime.py`](nba_mcp/api/tools/playbyplayv3_or_realtime.py) - Apply patches at module load
- **Testing**: All 5 previously failing games now return play-by-play data successfully
- **Impact**: Fixes play-by-play MCP tool and all downstream features
- **Documentation**: See [WINPROBABILITY_FIX_SUMMARY.md](WINPROBABILITY_FIX_SUMMARY.md)

### Dataset Management & Joins Feature - Complete ✅
- **Status**: ✅ Fully Implemented and Tested (2025-10-29)
- **Modules**: `nba_mcp/data/` (4 modules, 1,400+ lines)
- **Features**:
  - **Data Catalog** (`catalog.py`): 9 endpoint definitions with schemas, PKs, join relationships, 6 join patterns
  - **Dataset Manager** (`dataset_manager.py`): In-memory storage with TTL (1h), automatic cleanup, multi-format export
  - **Joins Engine** (`joins.py`): DuckDB-powered SQL joins (inner/left/right/outer/cross), column validation, filter/aggregate ops
  - **Fetch Module** (`fetch.py`): Real NBA API data fetching for 8 endpoints with provenance tracking
- **MCP Tools** (6 new):
  1. `list_endpoints()` - Enumerate all endpoints with schemas and params
  2. `catalog()` - Complete data dictionary with join relationships and examples
  3. `fetch()` - Fetch raw data as Arrow tables with dataset handles (REAL DATA)
  4. `join()` - DuckDB joins on datasets with stats tracking
  5. `build_dataset()` - Multi-step pipeline (fetch + join + filter + select)
  6. `save_dataset()` - Export to Parquet/CSV/Feather/JSON
- **Endpoints with Real Data**:
  1. `player_career_stats` - Full career stats via get_player_career_stats()
  2. `player_advanced_stats` - Advanced metrics (TS%, Usage%, PIE) via get_player_advanced_stats()
  3. `team_standings` - Conference/division standings via get_team_standings()
  4. `team_advanced_stats` - Team efficiency metrics via get_team_advanced_stats()
  5. `team_game_log` - Historical game logs via fetch_league_game_log()
  6. `league_leaders` - Top performers in any category via get_league_leaders()
  7. `shot_chart` - Shot location data via fetch_shot_chart_data()
  8. `live_scores` - Placeholder (use get_live_scores() tool directly)
- **Dependencies**: Added DuckDB ≥0.9.0 (v1.4.1), PyArrow ≥14.0.0 (v19.0.1)
- **Integration**: Dataset manager initialization in server startup, background cleanup tasks
- **Performance**: In-memory datasets with 500MB limit, automatic TTL expiry, DuckDB query optimization
- **Formats**: Parquet (snappy), CSV, Feather (lz4), JSON (records)
- **Testing**: Complete integration tests (`test_dataset_fetch.py`) - all passing with real API:
  - Basic fetch from 3 endpoints (player stats, league leaders, standings)
  - Dataset manager storage/retrieval
  - Multi-table joins with DuckDB
  - Export to 4 formats (parquet, csv, feather, json)
- **Documentation**: Implementation plan (DATASET_IMPLEMENTATION_PLAN.md), test script, inline examples

### Endpoint Enhancement & Pagination - Complete ✅
- **Status**: ✅ Fully Implemented and Tested (2025-10-29)
- **Modules**: `nba_mcp/data/` (2 new modules, 1,000+ lines)
- **Features**:
  - **Introspection Module** (`introspection.py`): Auto-discover endpoint capabilities
    - Column names and data types
    - Estimated row counts for any parameter combination
    - Available date ranges (1996-present for historical, current season for live)
    - Available seasons (1996-97 through current)
    - Recommended chunking strategies (date/season/game/none)
    - Memory and time estimates before fetching
  - **Pagination Module** (`pagination.py`): Handle datasets of any size
    - Date-based chunking (monthly intervals)
    - Season-based chunking (one season at a time)
    - Game-based chunking (one game at a time)
    - Auto-select optimal strategy based on dataset size
    - Progress tracking with callbacks
    - Graceful handling of API timeouts
  - **Enhanced Catalog** (`catalog.py`): Added 9 metadata fields
    - supports_date_range, supports_season_filter, supports_pagination
    - typical_row_count, max_row_count, available_seasons
    - chunk_strategy, min_date, max_date
- **MCP Tools** (3 new):
  1. `inspect_endpoint(endpoint, params)` - Discover all metadata before fetching
  2. `fetch_chunked(endpoint, params, strategy, progress)` - Fetch large datasets in chunks
  3. `discover_nba_endpoints()` - Browse all available endpoints with capabilities
- **Chunking Strategies**:
  - **No chunking**: Small datasets (<1,000 rows) like team_standings
  - **Season chunking**: Moderate datasets (1,000-5,000 rows) like player_career_stats
  - **Date chunking**: Large datasets (>5,000 rows) like shot_chart
  - **Game chunking**: Detailed data like play_by_play
- **Capabilities Discovered**:
  - player_career_stats: 28 columns, ~20 rows/player, 30 seasons available
  - shot_chart: 24 columns, ~1,500 rows/season, date range 1996-present, season chunking recommended
  - team_standings: 15 columns, 30 rows/season, no chunking needed
  - league_leaders: 25 columns, 10-50 rows, no chunking needed
- **Performance**:
  - Row count estimation (based on endpoint type and parameters)
  - Memory usage prediction (~1KB per row in Arrow format)
  - Time estimation (2s per API call × number of chunks)
  - Automatic chunk size optimization
- **Testing**: Complete test suite (`test_endpoint_enhancement.py`) - all 4 suites passing:
  - Endpoint Introspection (3 tests): Discover columns, row counts, date ranges
  - Pagination & Chunking (5 tests): No chunking, season chunking, date chunking, progress callbacks, estimates
  - Catalog Integration (2 tests): List endpoints, get metadata with new fields
  - Dataset Tool Integration (3 tests): Store chunks, union chunks, save to file
- **Error Handling**: Graceful degradation for API timeouts, empty result handling, schema mismatches
- **Documentation**: Implementation plan (ENDPOINT_ENHANCEMENT_PLAN.md), comprehensive test suite

### Dataset Size Limits - Complete ✅
- **Status**: ✅ Fully Implemented and Tested (2025-10-29)
- **Modules**: `nba_mcp/data/limits.py` (1 new module, 250+ lines)
- **Features**:
  - **Limit Configuration** (`limits.py`): Configurable fetch size limits
    - Default: 1024 MB (1 GB) - reasonable for most use cases
    - Environment variable: NBA_MCP_MAX_FETCH_SIZE_MB
    - Runtime configuration via configure_limits() tool
    - Unlimited mode (-1) with warnings
    - Singleton pattern for global configuration
  - **Size Checking**: Pre-fetch estimation and warnings
    - Estimates dataset size before fetching (1KB per row)
    - Checks against configured limit
    - Provides detailed warnings with options when exceeded
    - Suggests chunking or limit increase
  - **Integration**: Seamless with existing tools
    - introspection.py: New check_size_limit() method
    - pagination.py: Added check_size_limit and force parameters
    - fetch() tool: Shows warning if size exceeds limit (allows fetch)
    - fetch_chunked() tool: Shows info message (bypasses limit)
- **MCP Tools** (1 new):
  - `configure_limits(max_fetch_mb, show_current)` - Configure or view fetch size limits at runtime
- **Configuration Options**:
  - **Default**: 1024 MB (1 GB)
  - **Environment**: Set NBA_MCP_MAX_FETCH_SIZE_MB=2048 at startup
  - **Runtime**: configure_limits(max_fetch_mb=2048)
  - **Unlimited**: configure_limits(max_fetch_mb=-1) with warnings
- **Warning System**:
  - Pre-fetch size estimation (before API calls)
  - Detailed warning messages when limit exceeded:
    - Estimated size vs. current limit
    - Overage percentage
    - Option 1: Use fetch_chunked() (recommended)
    - Option 2: Increase limit with configure_limits()
    - Option 3: Filter query to reduce size
  - fetch() shows full warning but allows fetch
  - fetch_chunked() shows info only (doesn't block)
- **Size Estimates**:
  - team_standings: ~0.03 MB (30 rows)
  - player_career_stats: ~0.02 MB (20 rows)
  - shot_chart: ~1.46 MB (1,500 rows/season)
  - league_leaders: ~0.025 MB (10-50 rows)
  - Estimation: 1KB per row in Arrow format
- **Benefits**:
  - Prevents unexpected large downloads
  - Protects against excessive memory usage
  - User awareness before fetching large datasets
  - Configurable for different use cases
  - Clear guidance on alternatives (chunking)
- **Testing**: Complete test suite (`test_size_limits.py`) - all 5 suites passing:
  - Limit Configuration (5 tests): get, set, reset, unlimited
  - Size Checking (4 tests): within limit, at limit, exceeds limit, unlimited mode
  - Introspector Integration (3 tests): small/medium/large dataset checks
  - Pagination Integration (3 tests): size blocking, force override, chunked fetch
  - Environment Variable (2 tests): env config, limit initialization
- **Documentation**: Comprehensive docstrings, test suite with examples

---

## Recent Updates (January 2025)

### Date Handling Overhaul - Complete ✅
- **Status**: ✅ Fixed, Audited, and Tested (2025-01-28)
- **Issue**: Multiple functions used system clock (`datetime.now()`) which could be incorrect
- **Root Cause**: Relied on system clock instead of authoritative NBA API date
- **Impact**: When system clock wrong → incorrect dates/seasons → wrong data or no results
- **Scope**: Affected 4 functions across 2 files
- **Fixes**:
  1. **get_live_scores** (nba_server.py:738-744)
     - Now uses NBA API's `ScoreBoard.score_board_date` for current date
     - Removed fallback to system clock (fail fast if NBA API unavailable)
     - Added import: `from nba_api.live.nba.endpoints.scoreboard import ScoreBoard`
  2. **get_team_standings** (advanced_stats.py:147)
     - Now uses `get_current_season_from_nba_api()` helper
  3. **get_team_advanced_stats** (advanced_stats.py:243)
     - Now uses `get_current_season_from_nba_api()` helper
  4. **get_player_advanced_stats** (advanced_stats.py:333)
     - Now uses `get_current_season_from_nba_api()` helper
- **New Helper Function**: `get_current_season_from_nba_api()` (advanced_stats.py:48-81)
  - Fetches current date from NBA API
  - Calculates NBA season based on date (October = season start)
  - Replaces 3 instances of duplicate datetime.now() logic
  - Includes debug logging for troubleshooting
- **Audit**: Comprehensive datetime.now() audit documented in DATETIME_AUDIT.md
  - 13 total usages found in production code
  - 3 critical issues fixed (season determination)
  - 7 acceptable uses (rate limiting, circuit breakers)
  - 3 metadata uses (documentation timestamps)
- **Testing**: Complete unit test suite created (tests/test_date_handling.py)
  - 15 test cases covering all scenarios
  - Tests for NBA API success, failure, edge cases
  - Tests for season calculation logic (all months)
  - Integration tests for advanced stats functions
- **Documentation**:
  - DEBUG_LOG.md: Complete debugging analysis
  - DATETIME_AUDIT.md: Comprehensive audit report
  - CHANGELOG.md: This entry
- **Benefits**: Production-ready, timezone-aware, authoritative date source, consistent across codebase

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
