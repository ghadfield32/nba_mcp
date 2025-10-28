# nba_mcp/__main__.py
import logging
import os
import sys

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Add debug information about environment
def print_debug_info():
    logger.debug("Python executable: %s", sys.executable)
    logger.debug("Python version: %s", sys.version)
    logger.debug("Current working directory: %s", os.getcwd())
    logger.debug("sys.path: %s", sys.path)
    logger.debug("PYTHONPATH: %s", os.environ.get("PYTHONPATH", "Not set"))

def main():
    print_debug_info()
    try:
        from nba_mcp.nba_server import main as server_main

        logger.info("Launching NBA MCP…")
        server_main()
    except ModuleNotFoundError as e:
        logger.error("Missing module: %s", e)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error in __main__")
        sys.exit(1)

if __name__ == "__main__":
    main()
