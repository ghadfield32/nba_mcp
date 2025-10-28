# NBA MCP Setup Guide

Complete guide to integrating the NBA MCP server with Claude Desktop and VS Code.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Claude Desktop Setup](#claude-desktop-setup)
4. [VS Code Setup](#vs-code-setup)
5. [Testing Connection](#testing-connection)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before setting up NBA MCP, ensure you have:

- **Python 3.11+** installed
- **uv** package manager (recommended) or **pip**
- **Claude Desktop** (for Claude Desktop setup) - Download from [claude.ai](https://claude.ai/download)
- **VS Code** (for VS Code setup) with Continue extension

---

## Installation

### 1. Clone and Install NBA MCP

```bash
# Clone the repository
cd /path/to/your/projects
git clone https://github.com/your-org/nba_mcp.git
cd nba_mcp

# Install with uv (recommended)
uv pip install -e .

# OR install with pip
pip install -e .

# Verify installation
python -c "import nba_mcp; print('✅ NBA MCP installed successfully')"
```

### 2. Verify Dependencies

```bash
# Test NBA API connectivity
python -c "from nba_api.stats.static import players; print('✅ NBA API accessible')"

# Check MCP SDK
python -c "import mcp; print('✅ MCP SDK installed')"
```

---

## Claude Desktop Setup

Claude Desktop uses a configuration file to connect to MCP servers.

### Step 1: Locate Configuration File

The configuration file location depends on your operating system:

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### Step 2: Edit Configuration

Open the configuration file and add the NBA MCP server to the `mcpServers` section:

```json
{
  "mcpServers": {
    "nba-mcp": {
      "command": "python",
      "args": ["-m", "nba_mcp.nba_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/nba_mcp"
      }
    }
  }
}
```

**Important**: Replace `/absolute/path/to/nba_mcp` with your actual path.

#### Example (macOS/Linux):
```json
{
  "mcpServers": {
    "nba-mcp": {
      "command": "python",
      "args": ["-m", "nba_mcp.nba_server"],
      "env": {
        "PYTHONPATH": "/Users/yourname/projects/nba_mcp"
      }
    }
  }
}
```

#### Example (Windows):
```json
{
  "mcpServers": {
    "nba-mcp": {
      "command": "python",
      "args": ["-m", "nba_mcp.nba_server"],
      "env": {
        "PYTHONPATH": "C:\\Users\\YourName\\projects\\nba_mcp"
      }
    }
  }
}
```

### Step 3: Restart Claude Desktop

1. Quit Claude Desktop completely
2. Reopen Claude Desktop
3. Look for the 🔌 icon in the bottom-right corner
4. Click it to see available MCP servers
5. You should see **"nba-mcp"** listed

### Step 4: Test Connection

In Claude Desktop, try asking:

```
"Get Stephen Curry's stats for the 2023-24 season"
```

You should see Claude use the `get_player_stats` tool and return real NBA data.

---

## VS Code Setup

VS Code can connect to MCP servers via the **Continue** extension.

### Step 1: Install Continue Extension

1. Open VS Code
2. Go to Extensions (Cmd+Shift+X / Ctrl+Shift+X)
3. Search for "Continue"
4. Click **Install**

### Step 2: Configure Continue

1. Open Continue settings (click Continue icon in sidebar, then ⚙️)
2. This opens `~/.continue/config.json`

3. Add NBA MCP to the `mcpServers` section:

```json
{
  "models": [
    {
      "title": "Claude 3.5 Sonnet",
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "apiKey": "your-anthropic-api-key"
    }
  ],
  "mcpServers": [
    {
      "name": "nba-mcp",
      "command": "python",
      "args": ["-m", "nba_mcp.nba_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/nba_mcp"
      }
    }
  ]
}
```

**Important**:
- Replace `/absolute/path/to/nba_mcp` with your actual path
- Add your Anthropic API key to the `apiKey` field

### Step 3: Restart VS Code

1. Reload VS Code window (Cmd+Shift+P → "Reload Window")
2. Open Continue chat panel
3. Start a new conversation

### Step 4: Test Connection

In Continue chat, ask:

```
"Show me the top 10 scorers in the NBA this season"
```

You should see Continue use the NBA MCP tools to fetch real data.

---

## Testing Connection

### Method 1: Using MCP Inspector (Recommended)

The MCP Inspector provides a web UI to test your server:

```bash
# Install MCP Inspector globally
npm install -g @modelcontextprotocol/inspector

# Run NBA MCP with inspector
npx @modelcontextprotocol/inspector python -m nba_mcp.nba_server
```

This opens a web interface at `http://localhost:5173` where you can:
- See all available tools
- Test individual tools with parameters
- View responses in real-time

### Method 2: Direct Python Test

```python
# test_connection.py
import asyncio
import json
from nba_mcp.nba_server import (
    get_player_career_information,
    get_shot_chart,
    get_game_context
)

async def test_connection():
    print("🏀 Testing NBA MCP Connection...\n")

    # Test 1: Player Stats
    print("Test 1: Get Player Career Information")
    try:
        result = await get_player_career_information("Stephen Curry")
        data = json.loads(result)
        print(f"✅ Success: Found {data['data']['player']['name']}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Test 2: Shot Chart
    print("\nTest 2: Get Shot Chart")
    try:
        result = await get_shot_chart(
            entity_name="Stephen Curry",
            season="2023-24",
            granularity="summary"
        )
        data = json.loads(result)
        print(f"✅ Success: {data['data']['metadata']['total_shots']} shots")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Test 3: Game Context
    print("\nTest 3: Get Game Context")
    try:
        result = await get_game_context("Lakers", "Warriors")
        data = json.loads(result)
        print(f"✅ Success: {len(data['data']['metadata']['components_loaded'])} components loaded")
    except Exception as e:
        print(f"❌ Failed: {e}")

    print("\n🎉 All tests complete!")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run with:
```bash
python test_connection.py
```

### Method 3: Golden Questions

Run the golden questions test suite:

```bash
# See docs/GOLDEN_QUESTIONS.md for full test suite
python -c "
import asyncio
from nba_mcp.nba_server import get_player_career_information

async def test():
    result = await get_player_career_information('LeBron James')
    print('✅ Golden Question 1.1 passed:', 'LeBron James' in result)

asyncio.run(test())
"
```

---

## Troubleshooting

### Issue: "Module not found: nba_mcp"

**Solution:**
```bash
# Ensure NBA MCP is installed
pip install -e /path/to/nba_mcp

# Or add to PYTHONPATH
export PYTHONPATH="/path/to/nba_mcp:$PYTHONPATH"
```

### Issue: "MCP server not appearing in Claude Desktop"

**Solutions:**
1. Check config file syntax (use JSON validator)
2. Verify path is absolute, not relative
3. Restart Claude Desktop completely
4. Check Claude Desktop logs:
   - macOS: `~/Library/Logs/Claude/`
   - Windows: `%APPDATA%\Claude\logs\`

### Issue: "Permission denied" when running server

**Solution:**
```bash
# Make sure Python is in your PATH
which python  # Should show Python 3.11+

# If using virtual environment, activate it first
source venv/bin/activate  # Unix
venv\Scripts\activate  # Windows
```

### Issue: "NBA API returns empty data"

**Solutions:**
1. Check internet connection
2. NBA API may be experiencing issues (retry later)
3. Verify season parameter is valid (e.g., "2023-24")
4. Some endpoints don't have data for current season until games start

### Issue: "Rate limit exceeded"

**Solution:**
```bash
# Wait 60 seconds between requests
# NBA MCP has built-in rate limiting:
# - Simple tools: 60/min
# - Complex tools: 20-30/min
# - Daily quota: 10,000 requests
```

### Issue: "JSON Schema validation failed"

**Solution:**
```bash
# Regenerate schemas
python -m nba_mcp.schemas.publisher

# Verify schemas directory exists
ls schemas/
```

---

## Advanced Configuration

### Environment Variables

You can customize NBA MCP behavior with environment variables:

```bash
# Custom headers
export NBA_MCP_USER_AGENT="MyApp/1.0"
export NBA_MCP_REFERER="https://my-app.com"

# Redis cache (optional)
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# Logging
export LOG_LEVEL="DEBUG"  # DEBUG, INFO, WARNING, ERROR
```

### Custom Rate Limits

Edit `nba_mcp/rate_limit/token_bucket.py` to customize rate limits:

```python
# Increase limit for your use case
_rate_limiter.add_limit(
    "get_shot_chart",
    capacity=100,  # 100 requests
    refill_rate=100 / 60  # per minute
)
```

### Using with Docker (Optional)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -e .

CMD ["python", "-m", "nba_mcp.nba_server"]
```

```bash
# Build and run
docker build -t nba-mcp .
docker run -p 8080:8080 nba-mcp
```

---

## Example Usage in Claude Desktop

Once connected, you can ask Claude:

**Simple queries:**
- "Who are the top scorers this season?"
- "Show me LeBron's stats"
- "What are today's NBA scores?"

**Complex queries:**
- "Compare LeBron James and Michael Jordan with era adjustments"
- "Get Stephen Curry's shot chart for 2023-24 season"
- "Give me game context for Lakers vs Warriors"

**Natural language:**
- "Who is the best three-point shooter?"
- "How did the Celtics do last night?"
- "Show me highlights from Game 7 of the Finals"

Claude will automatically:
1. Parse your question
2. Select appropriate MCP tool(s)
3. Fetch real NBA data
4. Format response in readable markdown

---

## Next Steps

After successful setup:

1. **Test golden questions** - See `docs/GOLDEN_QUESTIONS.md`
2. **Explore all tools** - See `docs/TOOL_REFERENCE.md` (if available)
3. **Review schema** - See `schemas/openapi.yaml` for full API spec
4. **Check performance** - Monitor cache hit rates, latency
5. **Report issues** - Create GitHub issue if you find bugs

---

## Support

If you encounter issues:

1. Check this troubleshooting section
2. Review `docs/GOLDEN_QUESTIONS.md` for test cases
3. Inspect logs in Claude Desktop / VS Code
4. Open GitHub issue with error details

---

## References

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Claude Desktop Download](https://claude.ai/download)
- [Continue Extension](https://continue.dev/)
- [NBA API Documentation](https://github.com/swar/nba_api)

---

Last Updated: 2025-10-28
