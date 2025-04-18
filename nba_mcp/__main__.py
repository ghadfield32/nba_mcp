# __main__.py
import sys
import traceback
import logging

def main():
    # Configure logging right away
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.debug("sys.path at startup: %s", sys.path)

    try:
        from nba_mcp.nba_server import main as server_main
        logger.info("Starting NBA MCP server...")
        server_main()

    except ModuleNotFoundError as e:
        logger.error("ModuleNotFoundError in __main__: %s", e)
        logger.error("Ensure nba_mcp/__main__.py exists and nba_mcp is on PYTHONPATH")
        sys.exit(1)

    except BaseException as e:
        logger.error("Unhandled exception during startup: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
