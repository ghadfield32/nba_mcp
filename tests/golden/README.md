# Golden Tests

Golden tests are regression tests that ensure schema stability and correctness for the most common NBA queries.

## Overview

The golden test suite includes **20 carefully selected queries** that represent:
- Most common use cases (leaders, stats, comparisons)
- Critical functionality (live scores, standings)
- Complex multi-tool scenarios
- Edge cases (ambiguous names, historical data)

## Test Categories

### Leaders (4 queries)
- Current scoring leader
- Assists leader
- Rebounds leader
- Three-point percentage leader

### Stats (3 queries)
- Current season player stats
- Career stats
- Team stats

### Comparisons (5 queries)
- Player head-to-head comparisons
- Team comparisons
- Multi-season comparisons

### Team (3 queries)
- Conference standings
- Team advanced stats
- Team comparisons

### Live (2 queries)
- Today's games
- Live scores

### Complex (2 queries)
- Multi-tool queries
- Queries with context

### Historical (1 query)
- Past season data

## How It Works

### Snapshot Testing

Each query has a **snapshot** that captures:
- Query text and metadata
- Response length
- Execution duration
- Schema structure (table rows, key elements)
- Response hash

When tests run, current responses are compared to snapshots to detect:
- Schema changes
- Performance regressions
- Unexpected errors
- Response format changes

### Test Execution

```bash
# Run all golden tests
pytest tests/test_golden_queries.py -v

# Run specific category
pytest tests/test_golden_queries.py -k "leaders" -v

# Run with detailed output
pytest tests/test_golden_queries.py -v -s

# Update snapshots (after intentional changes)
pytest tests/test_golden_queries.py --update-snapshots
```

## What's Tested

For each query, we verify:

1. **Correctness**: Query executes without errors
2. **Response Quality**: Response length meets minimum requirement
3. **Performance**: Execution time within acceptable range (with 2x tolerance)
4. **Schema Stability**: Response structure matches snapshot
5. **Tool Selection**: Expected tools are called

## Performance Budgets

Each query has a **maximum duration** budget:

| Category | Budget | Rationale |
|----------|--------|-----------|
| Simple queries | 1500ms | Single tool, cached data |
| Comparisons | 2000ms | Two parallel tool calls |
| Complex queries | 3000ms | Multiple tools, sequential |
| Live data | 1500ms | Real-time requirements |

Budgets have 2x tolerance in tests to account for variability.

## Schema Validation

Schema validation detects:
- Changes in response format (table vs narrative)
- Missing or added columns
- Significant length changes (>50%)
- Structural changes in multi-tool responses

## Updating Snapshots

Snapshots should be updated when:
- Intentionally changing response format
- Adding new data fields
- Improving response quality
- Fixing bugs that affect output

**Process**:
1. Make your changes
2. Run tests to see failures
3. Review failures carefully
4. If changes are intentional: `pytest tests/test_golden_queries.py --update-snapshots`
5. Commit updated snapshots with your changes

**⚠️ Never update snapshots without review!** Changes may indicate bugs.

## Adding New Golden Queries

To add a new query:

1. Edit `tests/golden/queries.py`
2. Add to `GOLDEN_QUERIES` list:

```python
GoldenQuery(
    id="new_query_001",
    name="Descriptive name",
    query="Natural language query text",
    intent="expected_intent",
    category="category_name",
    tools_expected=["tool1", "tool2"],
    min_response_length=100,
    max_duration_ms=2000
)
```

3. Run with `--update-snapshots` to create baseline
4. Verify snapshot in `tests/golden/snapshots/`

## Query Selection Criteria

Queries included in golden tests should be:

1. **Common**: Represents frequent user requests
2. **Representative**: Covers a key feature or use case
3. **Stable**: Expected response format is well-defined
4. **Fast**: Executes reasonably quickly (< 3 seconds)
5. **Deterministic**: Gives consistent results (for given data)

## Continuous Integration

Golden tests run on every:
- Pull request
- Merge to main
- Nightly build

CI failures indicate potential breaking changes and block merges.

## Performance Tracking

Golden tests also track performance trends:
- Average query duration
- p95 latency per category
- Success rate
- Cache effectiveness

Metrics are reported in CI and tracked over time.

## Troubleshooting

### Test Failures

**Schema mismatch**:
- Review the diff between snapshot and current response
- Check if change was intentional
- Update snapshot if appropriate

**Performance regression**:
- Check if cache is working
- Review NBA API response times
- Look for new N+1 queries
- Consider optimization

**Unexpected errors**:
- Check NBA API availability
- Verify tool registration
- Review recent code changes
- Check logs for details

### Missing Snapshots

If snapshots are missing:
```bash
pytest tests/test_golden_queries.py --update-snapshots
```

This creates snapshots for all queries.

### Flaky Tests

If tests are inconsistent:
- Check NBA API stability
- Increase performance budget tolerance
- Review mock tool implementation
- Consider using fixed test data

## Statistics

View golden test statistics:
```python
from tests.golden import get_query_statistics
print(get_query_statistics())
```

Output:
```python
{
    "total_queries": 20,
    "categories": {
        "leaders": 4,
        "stats": 3,
        "comparison": 5,
        ...
    },
    "avg_min_response_length": 150,
    "avg_max_duration_ms": 1800
}
```

## Best Practices

1. **Keep snapshots in git**: Track changes over time
2. **Review snapshot changes**: Don't blindly update
3. **Add tests for bugs**: Prevent regressions
4. **Keep queries realistic**: Mirror actual user behavior
5. **Maintain performance budgets**: Prevent performance degradation
6. **Update documentation**: Keep query list current

## Future Enhancements

Planned improvements:
- [ ] Semantic similarity scoring (beyond schema)
- [ ] Automatic detection of new common queries
- [ ] Performance trend analysis
- [ ] Coverage reporting by tool
- [ ] Integration with load testing
