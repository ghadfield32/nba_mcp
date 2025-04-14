#!/usr/bin/env python3
"""
NBA MCP Server starter script.
This script ensures that the NBA MCP server can be started directly,
without relying on the entry_points installation.
"""

import os
import sys

# Add the current directory to the path to ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Import and run the main function from nba_server
    from nba_mcp.nba_server import main
    main() 