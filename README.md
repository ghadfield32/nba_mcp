# NBA MCP Server

A Media Control Protocol (MCP) server for retrieving NBA data.

## Features

- Retrieve NBA game scores by date
- Get player season and career statistics
- View top league leaders in various statistical categories
- Access live scoreboard data for current games
- View team game logs and historical data

## Setup

1. Create a virtual environment using UV:
   ```
   .\setup_uvenv.ps1
   ```

2. Install the package in development mode:
   ```
   pip install -e .
   ```

## Usage

### Running the Server

You can run the NBA MCP server in two ways:

1. Directly through the terminal:
   ```
   python -m nba_mcp
   ```

2. Configure it in your MCP client's configuration file (e.g., for Claude/Cursor):
   ```json
   {
     "servers": {
       "nba-mcp": {
         "command": ["python", "-m", "nba_mcp"]
       }
     }
   }
   ```

## Available MCP Tools

The server provides the following tools through the Model Context Protocol:

### Game Information

- `get_game_scores(date: str)`
  - Get NBA game scores for a specific date
  - Format: YYYY-MM-DD (e.g., "2022-12-25")

- `get_live_scores()`
  - Get live NBA game scores for today

- `get_nba_games(date: Optional[str], lookback_days: Optional[int])`
  - Get games for a specific date or range
  - Optional date format: YYYY-MM-DD
  - Optional lookback_days for historical data

### Player Statistics

- `get_player_stats(player: str)`
  - Get current season averages for a player
  - Example: "LeBron James"

- `get_player_career_information(player_name: str)`
  - Get career statistics for a player
  - Example: "LeBron James"

- `get_player_multi_season_stats(player: str, seasons: Optional[List[int]])`
  - Get stats across multiple seasons in tabular format
  - Optional seasons list (e.g., [2023, 2022, 2021])

### Team and League Data

- `get_team_game_log(team_name: str, season: str)`
  - Get game log for a specific team
  - Team name: "Lakers" or "Los Angeles Lakers"
  - Season format: "2023-24"

- `get_league_leaders(stat_category: str)`
  - View top league leaders by statistical category
  - Categories: PTS, AST, REB, STL, BLK, etc.

## Testing

Run the test scripts to verify the API functionality:

```
python tests/test_api_client.py
python tests/test_nba_api_with_error_handling.py
```

## Dependencies

- Python ≥ 3.10
- nba_api ≥ 1.2.1
- fastmcp

## Error Handling

The API includes comprehensive error handling for:
- Invalid dates or date formats
- Player name mismatches
- Network connectivity issues
- API rate limiting
- Missing or incomplete data

## Troubleshooting

If you encounter issues:

1. Verify your API key is correctly set
2. Ensure you're using Python 3.10 or higher
3. Check that all dependencies are installed
4. For specific endpoint errors, see the error messages for detailed information

## License

MIT
