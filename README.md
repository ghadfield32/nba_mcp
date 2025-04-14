# NBA MCP Server

A Media Control Protocol (MCP) server for retrieving NBA data.

## Features

- Retrieve NBA game scores by date
- Get player season statistics by player name
- View top league leaders in various statistical categories
- Access live scoreboard data for current games

## Setup

1. Create a virtual environment:
   ```
   .\setup_uvenv.ps1
   ```

2. Install the package in development mode:
   ```
   pip install -e .
   ```

## Usage

The server runs as an MCP server with the following available tools:

- `get_game_scores(date: str)`: Retrieve NBA game scores for a specific date in YYYY-MM-DD format
- `get_player_stats(player: str)`: Get season statistics for a specific NBA player by name
- `get_league_leaders(stat_category: str)`: View top 5 league leaders for a specific statistical category (PTS, AST, REB, etc.)

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

The API includes comprehensive error handling:

- HTTP 404 responses are properly handled with meaningful error messages
- Validation of response data structures
- Informative error messages for API key requirements
- Graceful handling of empty result sets

## Troubleshooting

If you encounter issues:

1. Verify your API key is correctly set
2. Ensure you're using Python 3.10 or higher
3. Check that all dependencies are installed
4. For specific endpoint errors, see the error messages for detailed information

## License

MIT