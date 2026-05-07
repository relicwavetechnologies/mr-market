"""Structured logging setup for Mr. Market services."""

import logging
import sys
from typing import ClassVar


class StructuredFormatter(logging.Formatter):
    """Log formatter that produces structured, key-value style output."""

    LEVEL_COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[32m",      # green
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def __init__(self, *, use_colors: bool = True) -> None:
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        level = record.levelname.ljust(8)
        name = record.name
        msg = record.getMessage()

        if self.use_colors:
            color = self.LEVEL_COLORS.get(record.levelno, "")
            level = f"{color}{level}{self.RESET}"

        line = f"{ts} | {level} | {name} | {msg}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line += f"\n{record.exc_text}"

        return line


def get_logger(
    name: str,
    *,
    level: int | str = logging.INFO,
    use_colors: bool = True,
) -> logging.Logger:
    """Return a configured logger with structured output.

    Args:
        name: Logger name (typically __name__ of the calling module).
        level: Logging level.
        use_colors: Whether to use ANSI colour codes in output.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter(use_colors=use_colors))
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
