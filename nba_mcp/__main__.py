#!/usr/bin/env python3
"""
NBA MCP Server main entry point.
This allows the server to be run with 'python -m nba_mcp'
"""

import sys
import traceback

def main():
    try:
        # Import here to avoid circular imports
        from nba_mcp.nba_server import main as server_main
        
        # Log startup to stderr for diagnostics
        print("Starting NBA MCP server...", file=sys.stderr)
        
        # Run the server
        server_main()
    except Exception as e:
        # Log any unhandled exceptions to stderr
        print(f"ERROR: Unhandled exception during startup: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 