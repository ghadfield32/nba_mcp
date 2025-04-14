# PowerShell script to run the NBA MCP server

# Display startup message
Write-Host "Starting NBA MCP Server..." -ForegroundColor Green

# Run the server using Python
try {
    python run_nba_mcp.py
}
catch {
    Write-Host "Error starting NBA MCP server: $_" -ForegroundColor Red
    Write-Host "Make sure Python is installed and the dependencies are installed with 'pip install -r requirements.txt'" -ForegroundColor Yellow
    
    # Keep the window open if there's an error
    Read-Host "Press Enter to exit"
} 