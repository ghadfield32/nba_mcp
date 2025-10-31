from invoke import task


@task
def env(c):
    """
    Create/update the project virtual environment and install dependencies.
    """
    c.run("uv sync --extra dev")


@task(pre=[env], help={"mode": "\"local\" for port 8001 or \"claude\" for port 8000"})
def run(c, mode="local"):
    """
    Launch the NBA MCP server in the given mode.
    """
    c.run(f"uv run python -m nba_mcp --mode {mode}", pty=True)
