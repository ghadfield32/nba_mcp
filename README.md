# NBA MCP Server

An NBA statistics API server using MCP (Message Control Protocol) for enhanced interaction with basketball data. This server provides access to NBA game scores, player statistics, and other basketball-related data.

## Requirements

- Python 3.10 or higher
- Dependencies as listed in `pyproject.toml` and `setup.py`

## Installation

### Setup with uv (recommended)

Run the provided setup script to create a virtual environment:

```powershell
.\setup_uvenv.ps1
```

### Manual Installation

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install the package:
```bash
pip install -e .
```

## API Key

Some endpoints require an API key from the balldontlie API:

1. Sign up at https://app.balldontlie.io to get your API key
2. Set it as an environment variable:
   ```bash
   # On Linux/macOS
   export NBA_API_KEY=your_key_here
   
   # On Windows PowerShell
   $env:NBA_API_KEY = "your_key_here"
   ```

## Usage

### Running the Server

Run the MCP server:

```bash
nba-mcp
```

### MCP Tools

The server exposes the following MCP tools:

- `get_game_scores`: Get NBA game scores for a specific date (YYYY-MM-DD format)
- `get_player_stats`: Get season averages for a player by name

### Testing

Run the API client tests:

```bash
python test_api_client.py
```

For improved error handling examples:

```bash
python tests/test_nba_api_with_error_handling.py
```

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