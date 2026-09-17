"""Logging setup for Reddit Research Data-Retrieval System.

Configures the root logger with console and file handlers.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = "logs/run.log") -> logging.Logger:
    """Configure root logger with console and file handlers.

    - Console handler: INFO level (always shows INFO+ to terminal)
    - File handler: configurable level, append mode
    - Format: "%(asctime)s %(levelname)-5s %(message)s"

    Creates log directory if it doesn't exist.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, etc.)
        log_file: Path to the log file.

    Returns:
        The configured root logger.
    """
    # Resolve numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create log directory if needed
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # Formatter
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(message)s")

    # Console handler — always INFO+ for clean terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    # File handler — configurable level, append mode, UTF-8
    file_handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    return root_logger
