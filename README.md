# NBA MCP Server

## Overview
NBA MCP (Message Control Protocol) server provides NBA data services via a network-accessible API. Built on top of the official [NBA API](https://github.com/swar/nba_api) and [FastMCP](https://github.com/fastmcp/fastmcp) framework, this server offers real-time and historical NBA data through a simple interface.

# Example Real Time Data Pull
   ## It pulls in:
      * live scores ahead of the broadcast
      * live play by play ahead of nba.com
      * assist leaders back to 1996 to compare to todays 

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
# python nba_server.py --mode local       # runs on 8001
# python nba_server.py --mode claude      # runs on 8000

The simplest way to run the server on Claude Desktop:
```bash
python nba_server.py --mode claude      # runs on 8000
```

Using the local port is great for local llms through ollama and such:
```bash
python nba_server.py --mode local       # runs on 8001
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
      "nba_mcp Docs": {
        "url": "https://gitmcp.io/ghadfield32/nba_mcp"
      }
    }
  }
   ```

## Available MCP Tools

### Game Information

- `get_live_scores(target_date: Optional[str] = None)` - Get current or historical NBA scores
- `get_game_scores(date: str)` - Get scores for a specific date
- `get_nba_games(date: str, lookback_days: int)` - Get games with historical lookback

### Player Statistics

- `get_player_stats(player: str)` - Get player's current season stats
- `get_player_career_information(player_name: str)` - Get comprehensive career information
- `get_player_multi_season_stats(player: str, seasons: List[int])` - Get stats across multiple seasons

### Team and League Data

- `get_team_game_log(team_name: str, season: str)` - Get team's game history
- `get_league_leaders(stat_category: str)` - Get league leaders for specific stat categories

## Running LangGraph Bots

### Prerequisites
First, pull the required Ollama model:
```bash
# Pull the LLaMA 3.2 model
python -m ollama pull llama3.2:3b
```

### Basic Agent
```bash
# Run the basic LangGraph agent with Ollama
python examples/langgraph_ollama_agent.py
```

### Agent with Tools
```bash
# Run the agent with NBA MCP tools in local mode
# This will:
# 1. Start the NBA MCP server on port 8001
# 2. Connect the LangGraph agent to it
python examples/langgraph_ollama_agent_w_tools.py --mode local
```

Example interaction:
```
Starting NBA MCP server in 'local' mode (port 8001)…
Langgraph agent starting…
Loaded tools: ['get_league_leaders_info', 'get_player_career_information', 'get_live_scores', 'play_by_play_info_for_current_games']
Enter a question:
> who leads the nba in assists this season?
AIMessage: Let me check the league leaders for assists this season.
ToolMessage: [League leaders data for assists...]
AIMessage: Based on the data, [Player Name] leads the NBA in assists this season...
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
