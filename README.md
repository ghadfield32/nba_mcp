
https://github.com/user-attachments/assets/c73aacf1-018a-427a-9e1c-8290b1a99963
# NBA MCP Server

## Overview
NBA MCP (Message Control Protocol) server provides NBA data services via a network-accessible API. Built on top of the official [NBA API](https://github.com/swar/nba_api) and [FastMCP](https://github.com/fastmcp/fastmcp) framework, this server offers real-time and historical NBA data through a simple interface.

# Example Real Time Data Pull:
   It pulls in:
      - live scores ahead of the broadcast
      - live play by play ahead of nba.com
      - assist leaders back to 1996 to compare to todays 

https://github.com/user-attachments/assets/297eca7e-398b-4061-9fbb-7611a02b453c


## Getting Started

### Installation

1. Create and activate a virtual environment using UV:
```bash
# Install UV if you haven't already
pip install uv

# Create virtual environment
uv venv nbavenv

# Activate the environment
# On Windows:
.\nbavenv\Scripts\activate
# On Unix/MacOS:
source nbavenv/bin/activate
```

2. Install the project:
```bash
# Clone the repository
git clone <repository-url>
cd nba_mcp

# Install dependencies using UV
uv pip install -r requirements.txt

# For development installation (includes testing tools)
uv pip install -e ".[dev]"
```

### Running the Server

The simplest way to run the server:
```bash
python -m nba_mcp
```

Using the launcher script with custom configuration:
```bash
python run_nba_mcp.py --port 8080 --max-tries 5
```

## Features

- Real-time NBA game scores and statistics
- Historical game data and player statistics
- League leaders and team performance metrics
- Live scoreboard data for current games
- Comprehensive play-by-play data
- Team game logs and historical analysis

## Usage

### Running the Server

You can run the NBA MCP server in two ways:

1. Directly through the terminal:
   ```bash
   python -m nba_mcp
   ```

2. Configure it in your MCP client's configuration file:
   
   Configuration file locations:
   - VSCode: `%APPDATA%\Code\User\mcp.json` or `~/.config/Code/User/mcp.json`
   - Cursor: `%APPDATA%\Cursor\User\mcp.json` or `~/.config/Cursor/User/mcp.json`
   
   ```json
   {
     "mcpServers": {
       "nba-mcp": {
         "command": ["python", "-m", "nba_mcp"],
         "cwd": "${workspaceFolder}",
         "env": {
           "NBA_API_KEY": "your-api-key"
         }
       }
     }
   }
   ```

## Available MCP Tools

### Game Information

#### Live Scores
```python
# Get current live scores
await get_live_scores()

# Get scores for a specific date
await get_live_scores(target_date="2024-03-15")
```

#### Game Scores by Date
```python
# Get scores for a specific date
await get_game_scores(date="2024-03-15")
```

#### Game History
```python
# Get games with lookback
await get_nba_games(date="2024-03-15", lookback_days=7)
```

### Player Statistics

#### Current Season Stats
```python
# Get player's current season stats
await get_player_stats(player="LeBron James")
```

#### Career Statistics
```python
# Get comprehensive career information
await get_player_career_information(player_name="Stephen Curry")
```

#### Multi-Season Analysis
```python
# Get stats across multiple seasons
await get_player_multi_season_stats(
    player="Luka Doncic",
    seasons=[2024, 2023, 2022]
)
```

### Team and League Data

#### Team Game Logs
```python
# Get team's game history
await get_team_game_log(
    team_name="Lakers",
    season="2023-24"
)
```

#### League Leaders
```python
# Get scoring leaders
await get_league_leaders(stat_category="PTS")

# Get assist leaders
await get_league_leaders(stat_category="AST")
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest tests/

# Run specific test categories
pytest tests/test_api_client.py
pytest tests/test_nba_api_with_error_handling.py
pytest tests/api/test_live_scores.py
pytest tests/api/test_player_stats.py
```

Run integration tests with NBA API:
```bash
pytest tests/integration/test_nba_api_integration.py
```

## Dependencies

- Python ≥ 3.10
- nba_api ≥ 1.9.0
- fastmcp ≥ 2.2.0
- pandas ≥ 2.2.3
- pydantic ≥ 2.11.3

## Error Handling

The API includes comprehensive error handling for:
- Invalid dates or date formats
- Player name mismatches
- Network connectivity issues
- API rate limiting
- Missing or incomplete data

### Common Error Solutions

1. Rate Limiting:
   ```python
   # Add delay between requests
   await get_player_stats(player="LeBron James", delay=1.5)
   ```

2. Network Issues:
   ```python
   # Increase timeout and retries
   await get_live_scores(timeout=30, max_retries=3)
   ```

## Troubleshooting

1. Verify your environment:
   ```bash
   # Check Python version
   python --version
   
   # Verify dependencies
   uv pip list
   ```

2. Test API connectivity:
   ```bash
   python tests/utils/test_api_connection.py
   ```

3. Check logs:
   ```bash
   # Enable debug logging
   export NBA_MCP_LOG_LEVEL=DEBUG
   python -m nba_mcp
   ```

## License

MIT
