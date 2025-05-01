from invoke import task
import os

# Virtual-env directory
ENV_DIR = ".venv"

@task
def env(c):
    """
    Create a virtual environment if it doesn't exist and install deps.
    """
    if not os.path.exists(ENV_DIR):
        c.run(f"uv venv {ENV_DIR}")
    activate = (
        os.path.join(ENV_DIR, "Scripts", "activate")
        if os.name == "nt"
        else os.path.join(ENV_DIR, "bin", "activate")
    )
    c.run(f"source {activate} && uv pip install -r requirements.txt")

@task(pre=[env], help={"mode": "‘local’ for port 8001 or ‘claude’ for port 8000"})
def run(c, mode="local"):
    """
    Launch the NBA MCP server in the given mode.
    """
    activate = (
        os.path.join(ENV_DIR, "Scripts", "activate")
        if os.name == "nt"
        else os.path.join(ENV_DIR, "bin", "activate")
    )
    c.run(f"source {activate} && python -m nba_mcp --mode {mode}", pty=True)
