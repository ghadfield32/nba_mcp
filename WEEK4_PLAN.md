# Week 4 Implementation Plan: Scale & Observability

**Date**: 2025-10-28
**Status**: In Progress
**Goal**: Add production-grade caching, rate limiting, and monitoring

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   NBA MCP Server                       │
│                                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │         Redis Cache Layer (NEW)              │   │
│  │  ┌────────────────────────────────────────┐ │   │
│  │  │ TTL Tiers:                             │ │   │
│  │  │ - Live: 30s (game scores)              │ │   │
│  │  │ - Daily: 1h (today's stats)            │ │   │
│  │  │ - Historical: 24h (past seasons)       │ │   │
│  │  │ - Static: 7d (player names, teams)     │ │   │
│  │  └────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────┘   │
│                                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │      Rate Limiter (NEW)                      │   │
│  │  - Token bucket per tool                     │   │
│  │  - Global daily quota                        │   │
│  │  - Per-user limits (future)                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │      Monitoring (NEW)                        │   │
│  │  - Prometheus metrics (latency, errors)      │   │
│  │  - OpenTelemetry traces                      │   │
│  │  - Cache hit/miss ratios                     │   │
│  └──────────────────────────────────────────────┘   │
│                                                        │
│            ▼ (requests flow through layers)          │
│                                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │         NLQ Pipeline                         │   │
│  │    (Parser → Planner → Executor → Synth)     │   │
│  └──────────────────────────────────────────────┘   │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## Component 1: Redis Caching

### TTL Tier Strategy

| Data Type | Examples | TTL | Rationale |
|-----------|----------|-----|-----------|
| **Live** | Live scores, in-progress games | 30s | Changes rapidly during games |
| **Daily** | Today's stats, current standings | 1h | Updated throughout the day |
| **Historical** | Past season stats, game logs | 24h | Rarely changes, safe to cache longer |
| **Static** | Player names, team info, entities | 7d | Almost never changes |

### Cache Key Format

```python
cache_key = f"nba_mcp:v1:{tool_name}:{hash(params)}"
# Example: "nba_mcp:v1:get_player_stats:abc123def456"
```

**Benefits**:
- Version prefix allows cache invalidation on updates
- Tool name enables per-tool metrics
- Hash ensures uniqueness without exposing sensitive data

### Stale-While-Revalidate

For high-traffic scenarios (e.g., popular player comparisons during playoffs):
1. Serve cached data immediately (even if stale)
2. Trigger async background refresh
3. Next request gets fresh data

**Result**: Near-instant responses for popular queries!

### Cache Statistics

Track:
- Hit ratio per tool
- Cache size/memory usage
- Eviction count
- Average TTL per tier

---

## Component 2: Rate Limiting

### Token Bucket Algorithm

```python
class TokenBucket:
    capacity: int = 100      # Max tokens
    refill_rate: float = 10  # Tokens per second
    current: float = 100     # Current tokens

    def consume(n=1) -> bool:
        if current >= n:
            current -= n
            return True
        return False  # Rate limit exceeded
```

### Per-Tool Limits

| Tool | Limit | Rationale |
|------|-------|-----------|
| `get_live_scores` | 10/min | High NBA API cost |
| `get_player_stats` | 60/min | Moderate cost |
| `get_league_leaders` | 60/min | Moderate cost |
| `compare_players` | 30/min | Calls multiple tools |
| `answer_nba_question` | 20/min | Complex queries |

### Global Quota

- **Daily limit**: 10,000 NBA API calls
- **Warning threshold**: 8,000 calls (80%)
- **Action**: Emit alert, increase cache TTLs

### Response Headers

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1630000000
Retry-After: 30
```

---

## Component 3: Monitoring

### Prometheus Metrics

**Counters**:
- `nba_mcp_requests_total{tool, status}`
- `nba_mcp_cache_hits_total{tool}`
- `nba_mcp_cache_misses_total{tool}`
- `nba_mcp_errors_total{tool, error_type}`

**Histograms**:
- `nba_mcp_request_duration_seconds{tool}` (p50, p95, p99)
- `nba_mcp_cache_ttl_seconds{tier}`

**Gauges**:
- `nba_mcp_cache_size_bytes{tier}`
- `nba_mcp_rate_limit_remaining{tool}`
- `nba_mcp_active_requests`

### OpenTelemetry Traces

**Spans**:
```
answer_nba_question
├── parse_query (5ms)
├── plan_execution (2ms)
├── execute_tools (150ms)
│   ├── get_player_stats (50ms)
│   │   ├── cache_lookup (1ms) [MISS]
│   │   └── nba_api_call (49ms)
│   └── get_team_standings (100ms)
│       ├── cache_lookup (1ms) [HIT]
│       └── (skipped - served from cache)
└── synthesize_response (3ms)
```

**Benefits**:
- See exactly where time is spent
- Identify slow NBA API calls
- Measure cache effectiveness

### Dashboard Panels

1. **Request Rate**: Requests/sec by tool (last 1h)
2. **Latency**: p50/p95/p99 by tool
3. **Error Rate**: % errors by tool
4. **Cache Performance**: Hit ratio, size, evictions
5. **Rate Limits**: Remaining tokens by tool
6. **NBA API Usage**: Calls/day, quota percentage

---

## Component 4: Golden Tests

### Top 20 Queries (from analytics)

1. "Who leads the NBA in points?"
2. "Who leads the NBA in assists?"
3. "Who leads the NBA in rebounds?"
4. "Compare LeBron James and Kevin Durant"
5. "Show me Stephen Curry stats"
6. "Lakers vs Celtics"
7. "Warriors vs Bucks"
8. "Eastern Conference standings"
9. "Western Conference standings"
10. "Top 10 scorers this season"
11. "Show me Giannis stats"
12. "Compare Luka Doncic and Trae Young"
13. "What is the Celtics offensive rating?"
14. "Lakers standings"
15. "Who leads in three pointers?"
16. "Show me Nikola Jokic stats"
17. "Compare Jayson Tatum and Jaylen Brown"
18. "Nuggets vs Lakers"
19. "Show me Anthony Davis stats"
20. "Top 5 rebounders"

### Test Strategy

```python
@pytest.mark.golden
def test_golden_query_1():
    """Test: Who leads the NBA in points?"""
    # Load recorded NBA API response
    with open("golden/leaders_points.json") as f:
        expected_response = json.load(f)

    # Execute query
    answer = await answer_nba_question("Who leads the NBA in points?")

    # Verify format (not exact content - data changes)
    assert "NBA Leaders" in answer
    assert "PTS" in answer or "Points" in answer
    assert len(answer) > 100  # Should be formatted table
```

### Recording Mode

```bash
# Record golden responses
NBA_MCP_RECORD_GOLDEN=1 pytest tests/test_golden.py

# Replay without NBA API
pytest tests/test_golden.py
```

---

## Implementation Phases

### Phase 1: Redis Caching (Priority 1)
- [x] Design TTL tier strategy
- [ ] Implement Redis cache wrapper
- [ ] Add cache middleware to tools
- [ ] Add cache statistics
- [ ] Test cache hit/miss scenarios

### Phase 2: Rate Limiting (Priority 2)
- [ ] Implement token bucket algorithm
- [ ] Add per-tool rate limiters
- [ ] Add global quota tracker
- [ ] Add rate limit response headers
- [ ] Test rate limit scenarios

### Phase 3: Monitoring (Priority 3)
- [ ] Add Prometheus metrics
- [ ] Add OpenTelemetry tracing
- [ ] Create Grafana dashboard config
- [ ] Set up alerting rules
- [ ] Test metric collection

### Phase 4: Golden Tests (Priority 4)
- [ ] Record top 20 query responses
- [ ] Create golden test suite
- [ ] Add regression detection
- [ ] Document golden test process

---

## Expected Performance Improvements

### Without Cache (Baseline)
```
Query: "Who leads the NBA in assists?"
├── Cache lookup: N/A
├── NBA API call: 800ms
├── Parse + format: 20ms
└── Total: ~820ms
```

### With Cache (Hot)
```
Query: "Who leads the NBA in assists?"
├── Cache lookup: 2ms (HIT)
├── NBA API call: 0ms (skipped)
├── Parse + format: 0ms (cached formatted result)
└── Total: ~2ms (410x faster!)
```

### With Rate Limiting
```
Without: Unlimited → Risk of NBA API ban
With: 60 req/min → Sustainable, predictable
```

### With Monitoring
```
Before: "Why is this slow?" → No idea
After: "Why is this slow?" → See exact bottleneck in traces
```

---

## Configuration

### Environment Variables

```bash
# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=secret
REDIS_MAX_CONNECTIONS=10

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_GLOBAL_DAILY=10000
RATE_LIMIT_WARNING_THRESHOLD=0.8

# Monitoring
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
OTEL_ENABLED=true
OTEL_ENDPOINT=http://localhost:4318

# Caching
CACHE_ENABLED=true
CACHE_TTL_LIVE=30
CACHE_TTL_DAILY=3600
CACHE_TTL_HISTORICAL=86400
CACHE_TTL_STATIC=604800
```

---

## Success Criteria

- [ ] Cache hit ratio > 70% after warmup
- [ ] p99 latency < 100ms for cached queries
- [ ] Rate limits prevent NBA API quota exhaustion
- [ ] Prometheus metrics exported
- [ ] OpenTelemetry traces visible
- [ ] Golden tests cover top 20 queries
- [ ] Dashboard shows all key metrics

---

## Notes

**Efficiency Principles**:
1. Cache aggressively - most queries are repeated
2. Monitor everything - can't optimize what you don't measure
3. Rate limit preemptively - better to slow down than get banned
4. Test with real data - golden tests prevent regressions

**Redis vs In-Memory**:
- Redis: Persistent, shared across instances, supports TTL
- In-Memory: Faster, but lost on restart, no sharing

**Choice**: Redis for production, in-memory for development
