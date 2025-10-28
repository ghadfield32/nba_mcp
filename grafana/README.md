# NBA MCP Grafana Dashboard

This directory contains Grafana dashboard configuration for monitoring NBA MCP server performance and health.

## Dashboard Overview

The **NBA MCP - Performance & Health Dashboard** provides comprehensive observability with:

### Request Metrics
- **Request Rate by Tool**: Real-time request rate per tool and status
- **Request Latency Percentiles**: p50, p95, p99 latency tracking
- **Error Rate by Tool**: Error rates by tool and error type

### Cache Performance
- **Cache Hit Rate**: Gauge showing current hit rate (target: >90%)
- **Cache Operations**: Hit/miss rates over time
- **Cache Size**: Number of items in cache

### Rate Limiting
- **Daily Quota Usage**: Gauge showing quota consumption (alert at >90%)
- **Quota Remaining**: Remaining requests in daily quota
- **Rate Limit Events**: Allowed vs blocked requests per tool
- **Token Bucket Availability**: Available tokens per tool

### NLQ Pipeline
- **Pipeline Stage Duration**: p95 latency for parse, plan, execute, synthesize stages
- **Tool Calls per Query**: Number of tool calls by query intent

### Summary Stats
- **Total Requests**: 1-hour request count
- **Success Rate**: Overall success rate (target: >99%)
- **Avg Response Time**: Average response time (5m window)
- **Server Uptime**: Time since server start

### Error Analysis
- **Error Types Breakdown**: Top 10 errors by tool and type

## Setup Instructions

### Prerequisites

1. **Prometheus** running and scraping the NBA MCP `/metrics` endpoint
2. **Grafana** instance (v8.0+)

### Configuration

1. **Configure Prometheus** to scrape NBA MCP metrics:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'nba-mcp'
    scrape_interval: 10s
    static_configs:
      - targets: ['localhost:8000']  # Adjust to your NBA MCP server address
    metrics_path: '/metrics'
```

2. **Add Prometheus as Grafana Data Source**:
   - Navigate to Grafana → Configuration → Data Sources
   - Click "Add data source"
   - Select "Prometheus"
   - Set URL to your Prometheus instance (e.g., `http://localhost:9090`)
   - Click "Save & Test"

3. **Import Dashboard**:
   - Navigate to Grafana → Dashboards → Import
   - Click "Upload JSON file"
   - Select `nba_mcp_dashboard.json`
   - Select your Prometheus data source
   - Click "Import"

## Alerts

The dashboard includes pre-configured alerts:

### High p95 Latency
- **Condition**: p95 latency > 2 seconds
- **Action**: Investigate slow queries, check NBA API health, review cache effectiveness

### High Error Rate
- **Condition**: Error rate > 5%
- **Action**: Check error logs, verify NBA API availability, review recent deployments

### High Quota Usage
- **Condition**: Daily quota usage > 90%
- **Action**: Review query patterns, optimize cache TTLs, consider rate limit adjustments

## Customization

### Adjusting Time Ranges

Default dashboard shows last 1 hour. To change:
1. Edit dashboard
2. Update `time.from` in JSON (e.g., `"now-6h"` for 6 hours)
3. Save dashboard

### Modifying Alert Thresholds

To adjust alert thresholds:
1. Edit dashboard
2. Find panel with alert (IDs: 2, 3, 7)
3. Update `alert.conditions.evaluator.params` values
4. Save dashboard

### Adding Custom Panels

Common additions:
- **Tool-specific dashboards**: Filter metrics by `tool_name` label
- **Hourly trends**: Use `[1h]` range instead of `[5m]`
- **SLA tracking**: Calculate uptime percentage
- **Cost tracking**: Multiply quota usage by API cost

## Metric Reference

All metrics are prefixed with `nba_mcp_`:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `requests_total` | Counter | `tool_name`, `status` | Total requests |
| `request_duration_seconds` | Histogram | `tool_name` | Request duration |
| `errors_total` | Counter | `tool_name`, `error_type` | Total errors |
| `cache_operations_total` | Counter | `operation`, `result` | Cache ops |
| `cache_hit_rate` | Gauge | - | Hit rate (0-1) |
| `cache_size_items` | Gauge | - | Cached items |
| `rate_limit_events_total` | Counter | `tool_name`, `event_type` | Rate limit events |
| `quota_usage` | Gauge | `quota_type` | Quota usage (0-1) |
| `quota_remaining` | Gauge | `quota_type` | Remaining quota |
| `token_bucket_tokens` | Gauge | `tool_name` | Available tokens |
| `nlq_stage_duration_seconds` | Histogram | `stage` | NLQ stage duration |
| `nlq_tool_calls_total` | Counter | `query_intent` | Tool calls |
| `server_start_time_seconds` | Gauge | - | Server start time |

## Example Queries

### Request Rate by Tool
```promql
rate(nba_mcp_requests_total[5m])
```

### 95th Percentile Latency
```promql
histogram_quantile(0.95, rate(nba_mcp_request_duration_seconds_bucket[5m]))
```

### Success Rate
```promql
sum(rate(nba_mcp_requests_total{status="success"}[5m]))
/
sum(rate(nba_mcp_requests_total[5m]))
```

### Cache Hit Rate Trend
```promql
nba_mcp_cache_hit_rate
```

### Quota Consumption Rate
```promql
rate(nba_mcp_quota_usage{quota_type="daily"}[1h])
```

## Troubleshooting

### No Data Showing

1. **Check Prometheus is scraping**:
   ```bash
   curl http://localhost:9090/api/v1/targets
   ```

2. **Verify metrics endpoint**:
   ```bash
   curl http://localhost:8000/metrics
   ```

3. **Check data source connection** in Grafana

### High Latency

Common causes:
- Cache not working (check Redis connection)
- NBA API slowness (check upstream latency)
- Rate limiting active (check quota usage)
- Database queries (if using persistence)

### High Error Rate

Common causes:
- NBA API downtime (check external monitoring)
- Invalid parameters (review error types breakdown)
- Rate limit exceeded (check quota)
- Schema changes (check for UpstreamSchemaError)

## Best Practices

1. **Monitor Regularly**: Check dashboard daily during active development
2. **Set Up Alerts**: Configure Slack/PagerDuty for critical alerts
3. **Review Trends**: Look for performance degradation over time
4. **Optimize Based on Data**: Use metrics to guide optimization efforts
5. **Capacity Planning**: Track quota usage trends for scaling decisions

## Support

For issues or questions:
- Check logs: `docker logs nba-mcp` or server logs
- Review metrics: Look for anomalies in dashboard
- Check NBA API status: [NBA API Health](https://stats.nba.com)
