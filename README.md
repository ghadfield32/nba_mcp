# NBA MCP Server

A production-ready MCP (Model Context Protocol) server that provides comprehensive NBA data access through a standardized API interface. Built on top of the official NBA API with advanced features including caching, rate limiting, metrics collection, and natural language query support.

## Features

- **Real-time & Historical Data**: Live scores, game stats, player/team information, and historical records
- **Advanced Analytics**: Team and player advanced statistics, era-adjusted comparisons, shot charts
- **Natural Language Queries**: Ask questions in plain English (e.g., "Who leads the NBA in assists?")
- **Game Context**: Rich pre-game analysis with standings, form, head-to-head, and narrative synthesis
- **Production Infrastructure**: Redis caching, rate limiting, Prometheus metrics, OpenTelemetry tracing
- **Entity Resolution**: Fuzzy matching for player and team names with confidence scoring
- **Robust Error Handling**: Retry logic, circuit breakers, graceful degradation

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Git
- (Optional) Redis for caching
- (Optional) Ollama for local LLM usage

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/ghadfield32/nba_mcp.git
cd nba_mcp
```

2. **Create and activate a virtual environment**
```bash
# Using UV (recommended)
pip install uv
uv venv nbavenv

# Activate on Windows
.\nbavenv\Scripts\activate

# Activate on Unix/MacOS
source nbavenv/bin/activate
```

3. **Install dependencies**
```bash
# Basic installation
uv pip install -r requirements.txt

# Or install from setup.py
pip install -e .

# For development (includes testing tools)
pip install -e ".[dev]"
```

### Running the Server

The server can run in two modes:

**Claude Desktop Mode** (Port 8000)
```bash
python -m nba_mcp.nba_server --mode claude
```

**Local LLM Mode** (Port 8001 - for Ollama, etc.)
```bash
python -m nba_mcp.nba_server --mode local
```

The server will start and display available tools and configuration.

## Configuration

### MCP Client Setup

#### For Claude Desktop

Add to your Claude Desktop configuration file:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nba": {
      "command": "python",
      "args": ["-m", "nba_mcp.nba_server", "--mode", "claude"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\nba_mcp"
      }
    }
  }
}
```

#### For VS Code / Cursor

Add to your MCP configuration file:

**VS Code**: `%APPDATA%\Code\User\mcp.json` or `~/.config/Code/User/mcp.json`
**Cursor**: `%APPDATA%\Cursor\User\mcp.json` or `~/.config/Cursor/User/mcp.json`

```json
{
  "mcpServers": {
    "nba": {
      "url": "http://localhost:8000"
    }
  }
}
```

### Environment Variables

Configure optional features through environment variables:

```bash
# Server configuration
export NBA_MCP_PORT=8000
export NBA_MCP_LOG_LEVEL=INFO

# Redis caching (optional)
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export ENABLE_REDIS_CACHE=true

# Rate limiting
export NBA_MCP_DAILY_QUOTA=10000
export NBA_MCP_SIMPLE_RATE_LIMIT=60
export NBA_MCP_COMPLEX_RATE_LIMIT=30

# Observability (optional)
export ENABLE_METRICS=true
export ENABLE_TRACING=false
export OTLP_ENDPOINT=http://localhost:4317
```

## Usage Guide

### Available Tools

#### Game Information
- `get_live_scores(target_date)` - Get current or historical game scores
- `play_by_play(game_id)` - Detailed play-by-play data for a specific game
- `get_game_context(team1_name, team2_name, season)` - Rich pre-game context and analysis

#### Player Statistics
- `get_player_career_information(player_name, seasons)` - Comprehensive player career stats
- `get_player_advanced_stats(player_name, season)` - Advanced metrics (TS%, Usage%, eFG%, etc.)
- `compare_players(player1_name, player2_name, stat_categories)` - Head-to-head comparison
- `compare_players_era_adjusted(player1_name, player2_name)` - Cross-era comparisons

#### Team Statistics
- `get_team_standings(season, conference)` - Conference and division standings
- `get_team_advanced_stats(team_name, season)` - Team efficiency metrics
- `get_date_range_game_log_or_team_game_log(team_name, season, date_from, date_to)` - Team game history

#### League Data
- `get_league_leaders_info(stat_category, per_mode, season)` - League leaders in any category

#### Shot Charts
- `get_shot_chart(player_or_team_name, season, granularity)` - Shot location data with hexagonal binning

#### Natural Language Queries
- `answer_nba_question(question)` - Ask questions in plain English

#### Entity Resolution
- `resolve_nba_entity(entity_name, entity_type)` - Fuzzy matching for players/teams

### Example Queries

#### Basic Queries

```python
# Get today's live scores
get_live_scores()

# Get scores for a specific date
get_live_scores(target_date="2024-03-15")

# Get player career stats
get_player_career_information(player_name="LeBron James", seasons=[2023])

# Get league leaders in points
get_league_leaders_info(stat_category="PTS", per_mode="PerGame", season="2023-24")
```

#### Advanced Queries

```python
# Compare two players
compare_players(
    player1_name="Stephen Curry",
    player2_name="Damian Lillard",
    stat_categories=["PTS", "AST", "FG3M"]
)

# Cross-era comparison with adjustments
compare_players_era_adjusted(
    player1_name="Michael Jordan",
    player2_name="LeBron James"
)

# Get shot chart with hexagonal aggregation
get_shot_chart(
    player_or_team_name="Kevin Durant",
    season="2023-24",
    granularity="hexbin"
)

# Rich game context
get_game_context(
    team1_name="Lakers",
    team2_name="Warriors",
    season="2023-24"
)
```

#### Natural Language Queries

```python
# These all work with answer_nba_question()
"Who leads the NBA in assists this season?"
"Compare LeBron James and Michael Jordan career stats"
"What are the Lakers standings?"
"Show me Stephen Curry's shooting stats"
"Who scored the most points last night?"
```

### Working with Local LLMs (Ollama)

1. **Pull an Ollama model**
```bash
ollama pull llama3.2:3b
```

2. **Start the NBA MCP server in local mode**
```bash
python -m nba_mcp.nba_server --mode local
```

3. **Run the example agent**
```bash
python examples/langgraph_ollama_agent_w_tools.py --mode local
```

4. **Interact with the agent**
```
Enter a question:
> who leads the nba in assists this season?

AIMessage: Let me check the league leaders for assists this season.
ToolMessage: [League leaders data for assists...]
AIMessage: Based on the data, Tyrese Haliburton leads the NBA in assists...
```

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test categories
pytest tests/test_api_client.py
pytest tests/api/test_live_scores.py
pytest tests/api/test_player_stats.py

# Run integration tests
pytest tests/integration/

# Run with coverage
pytest --cov=nba_mcp --cov-report=html tests/
```

### Validation Script

Run the comprehensive validation suite:

```bash
python run_validation.py
```

This runs 23 core tests covering:
- Entity resolution
- Live data fetching
- Player and team statistics
- Advanced analytics
- Comparisons
- Shot charts
- Natural language queries

### Code Quality

```bash
# Format code
black nba_mcp/
isort nba_mcp/

# Type checking
mypy nba_mcp/

# Linting
flake8 nba_mcp/
```

## Monitoring & Observability

### Metrics Endpoint

When metrics are enabled, access Prometheus metrics at:

```
http://localhost:8000/metrics
```

Includes 14 metric types:
- Request counts and durations
- Error rates by type
- Cache hit/miss rates
- Rate limit usage
- Tool execution times

### Grafana Dashboard

A pre-built Grafana dashboard is available in `grafana/`:

```bash
# Start Grafana (with Docker)
cd grafana
docker-compose up -d

# Access at http://localhost:3000
# Default credentials: admin/admin
```

## Performance

- **Cache Performance**: 410x speedup with Redis (820ms → 2ms for cached responses)
- **Parallel Execution**: Game context composition uses 4x parallel API calls
- **Rate Limits**:
  - Simple tools: 60 requests/minute
  - Complex tools: 30 requests/minute
  - Multi-API tools: 20 requests/minute
  - Global quota: 10,000 requests/day

## Troubleshooting

### Common Issues

**1. Module Not Found Errors**
```bash
# Ensure PYTHONPATH is set correctly
export PYTHONPATH=/path/to/nba_mcp

# Or reinstall in development mode
pip install -e .
```

**2. API Rate Limiting**
```bash
# Check rate limit status in logs
# Reduce request frequency
# Wait for quota reset (daily)
```

**3. Redis Connection Issues**
```bash
# Verify Redis is running
redis-cli ping

# Or disable Redis caching
export ENABLE_REDIS_CACHE=false
```

**4. NBA API Errors**
```python
# The NBA API can be flaky
# The server includes automatic retries with exponential backoff
# Check logs for specific error details
```

### Debug Mode

Enable detailed logging:

```bash
export NBA_MCP_LOG_LEVEL=DEBUG
python -m nba_mcp.nba_server --mode claude
```

### Verify Installation

```bash
# Check Python version
python --version  # Should be 3.10+

# Verify dependencies
pip list | grep nba_api
pip list | grep fastmcp

# Test API connectivity
python -c "from nba_api.stats.static import players; print(len(players.get_players()))"
```

## Architecture

```
NBA MCP Server
├── nba_server.py           # Main FastMCP server
├── api/                    # Core API layer
│   ├── client.py           # NBA API client
│   ├── advanced_stats.py   # Advanced statistics
│   ├── entity_resolver.py  # Fuzzy entity matching
│   ├── shot_charts.py      # Shot chart data
│   ├── game_context.py     # Multi-source composition
│   ├── era_adjusted.py     # Cross-era adjustments
│   └── tools/              # API utilities
├── nlq/                    # Natural language processing
│   ├── parser.py           # Query parsing
│   ├── planner.py          # Query planning
│   ├── executor.py         # Parallel execution
│   └── synthesizer.py      # Response formatting
├── cache/                  # Redis caching layer
├── rate_limit/             # Token bucket rate limiting
├── observability/          # Metrics and tracing
└── schemas/                # Pydantic models and schemas
```

## API Response Format

All tools return a standardized response envelope:

```json
{
  "status": "success",
  "data": { ... },
  "metadata": {
    "version": "v1",
    "schema_version": "2025-01",
    "timestamp": "2024-03-15T10:30:00Z",
    "source": "nba_api",
    "cached": true,
    "cache_ttl": 3600
  },
  "errors": []
}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests (`pytest tests/`)
5. Format code (`black nba_mcp/ && isort nba_mcp/`)
6. Commit your changes (`git commit -m "Add your feature"`)
7. Push to the branch (`git push origin feature/your-feature`)
8. Open a Pull Request

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built on [nba_api](https://github.com/swar/nba_api) by Swar Patel
- Powered by [FastMCP](https://github.com/fastmcp/fastmcp) framework
- NBA data provided by [NBA.com](https://www.nba.com/)

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check existing documentation in the repository
- Review the troubleshooting section above
