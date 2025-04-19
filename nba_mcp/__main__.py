# __main__.py
import sys
import logging

# Configure logging right away – only keyword args allowed
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Entry point for NBA MCP application."""
    try:
        from nba_mcp.nba_server import main as server_main
        logger.info("Starting NBA MCP server…")
        server_main()
    except ModuleNotFoundError as e:
        logger.error("ModuleNotFoundError in __main__: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unhandled exception in __main__")
        sys.exit(1)

if __name__ == "__main__":
    main()
