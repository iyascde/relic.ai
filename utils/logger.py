"""
Structured logger for Relic.ai.

Every log line includes timestamp, component name, event type, and relevant
entity IDs (PR number, issue number). Consumed by every module in the system.
"""

import logging
import os
import sys
from typing import Optional


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(component)-20s | %(event_type)-25s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class RelicFormatter(logging.Formatter):
    """Custom log formatter that enforces the structured Relic.ai log schema."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "component"):
            record.component = "unknown"
        if not hasattr(record, "event_type"):
            record.event_type = "general"
        return super().format(record)


def get_logger(component: str) -> logging.Logger:
    """
    Return a structured logger bound to the given component name.

    Args:
        component: Human-readable name of the calling module (e.g. "risk_scorer").

    Returns:
        A configured Logger instance with the Relic formatter attached.
    """
    logger = logging.getLogger(f"relic.{component}")

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RelicFormatter(fmt=_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False

    return logger


class EventLogger:
    """
    Context-aware wrapper around a standard logger that injects event_type and
    entity IDs into every log call automatically.

    Usage:
        log = EventLogger("risk_scorer")
        log.info("pr_opened", "Processing PR", pr_number=42)
    """

    def __init__(self, component: str) -> None:
        self._logger = get_logger(component)
        self._component = component

    def _emit(
        self,
        level: int,
        event_type: str,
        message: str,
        pr_number: Optional[int] = None,
        issue_number: Optional[int] = None,
        **kwargs,
    ) -> None:
        extra = {"component": self._component, "event_type": event_type}
        parts = [message]
        if pr_number is not None:
            parts.append(f"pr={pr_number}")
        if issue_number is not None:
            parts.append(f"issue={issue_number}")
        for k, v in kwargs.items():
            parts.append(f"{k}={v}")
        self._logger.log(level, " | ".join(parts), extra=extra)

    def info(self, event_type: str, message: str, **kwargs) -> None:
        """Log at INFO level."""
        self._emit(logging.INFO, event_type, message, **kwargs)

    def warning(self, event_type: str, message: str, **kwargs) -> None:
        """Log at WARNING level."""
        self._emit(logging.WARNING, event_type, message, **kwargs)

    def error(self, event_type: str, message: str, **kwargs) -> None:
        """Log at ERROR level."""
        self._emit(logging.ERROR, event_type, message, **kwargs)

    def debug(self, event_type: str, message: str, **kwargs) -> None:
        """Log at DEBUG level."""
        self._emit(logging.DEBUG, event_type, message, **kwargs)
