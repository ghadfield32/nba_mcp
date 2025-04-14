# NBA MCP Fixed Issues

This document outlines the issues that were fixed in the NBA MCP project to make it work correctly with Claude Desktop.

## Issues Fixed

1. **Configuration Issues**
   - The project now has a proper `[project]` table in pyproject.toml
   - All Python version dependencies now consistently require Python >=3.10

2. **Entry Point Issues**
   - Added a direct run script (`run_nba_mcp.py`) that can be used instead of relying on entry points
   - Fixed imports in `__init__.py` to properly expose the main function

3. **API Usage Issues**
   - Removed all references to balldontlie API 
   - Updated all endpoints to use the official NBA API
   - Fixed test dates to use known, valid date ranges instead of future dates

4. **API Key Removal**
   - Removed all references to API keys since the official NBA API doesn't require them

## Running the MCP

For easiest operation with Claude Desktop:

1. Run `python run_nba_mcp.py` to start the MCP server
2. In Claude Desktop, connect to the NBA MCP
3. Ask questions about NBA games, players, and statistics

## Troubleshooting

If you encounter errors:

1. Verify Python 3.10 or higher is installed
2. Ensure all dependencies are installed: `pip install -r requirements.txt`
3. Check that the MCP server is running when you connect from Claude Desktop
4. If using test dates, ensure you're using dates from past NBA seasons (e.g., 2022-12-25) 