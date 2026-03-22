"""
Logging configuration for ProcessIQ.

Log Levels:
    DEBUG:   Development details (LLM calls, state transitions, data transforms)
    INFO:    Key operations ("Analyzing process...", "Found 3 bottlenecks")
    WARNING: Recoverable issues (missing optional data, fallback used)
    ERROR:   Failures (LLM API error, validation failure)

Usage:
    from processiq.logging_config import setup_logging
    setup_logging()

    # In any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Starting analysis")
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the entire application.

    Safe to call multiple times. Checks for existing handlers rather than using
    a module-level flag to prevent handler accumulation on repeated calls.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    app_logger = logging.getLogger("processiq")

    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        app_logger.addHandler(handler)
        # Prevent propagation to root logger (avoids duplicates from
        # root handler or basicConfig leftovers)
        app_logger.propagate = False

        # Quiet noisy third-party loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("chromadb").setLevel(logging.WARNING)
        logging.getLogger("langchain").setLevel(logging.WARNING)

    # Always update level (allows runtime level changes)
    app_logger.setLevel(log_level)
