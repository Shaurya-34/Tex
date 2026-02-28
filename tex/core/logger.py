"""Loguru-powered structured logger for Tex."""

import sys
from pathlib import Path
from loguru import logger
from tex.config import config


def setup_logger() -> None:
    """Configure loguru: human-readable file log + clean stderr for errors."""
    log_path = Path(config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # File: full structured log (rotation daily, kept 30 days)
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        encoding="utf-8",
    )

    # Stderr: only WARNING+ shown in terminal (Rich handles the rest)
    logger.add(
        sys.stderr,
        format="<yellow>{level}</yellow>: {message}",
        level="WARNING",
        colorize=True,
    )


def log_action(tool: str, arguments: dict, status: str, output: str = "") -> None:
    """Log a completed tool invocation."""
    logger.info(
        f"ACTION | tool={tool} | args={arguments} | status={status} | output={output[:200]}"
    )


def log_rejection(reason: str) -> None:
    logger.warning(f"REJECTED | {reason}")


def log_error(msg: str) -> None:
    logger.error(f"ERROR | {msg}")
