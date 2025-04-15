# PowerShell script to run the NBA MCP server

# Display startup message
Write-Host "Starting NBA MCP Server..." -ForegroundColor Green

# Run the server using Python
try {
    # Option 1: Run using the module approach
    python -m nba_mcp

    # Option 2: Run using the script directly
    # python nba_mcp\nba_server.py
}
catch {
    Write-Host "Error starting NBA MCP server: $_" -ForegroundColor Red
    Write-Host "Make sure Python is installed and the dependencies are installed with 'pip install -r requirements.txt'" -ForegroundColor Yellow
    Write-Host "Also ensure the package is installed in development mode with 'pip install -e .'" -ForegroundColor Yellow
    
    # Keep the window open if there's an error
    Read-Host "Press Enter to exit"
} 