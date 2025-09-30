# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration for the captive portal addon."""

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON format for logs
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure timestamper
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    # Configure processors
    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        # JSON formatter for production
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Console formatter for development
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    # Configure structlog
    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Set uvicorn access logs to WARNING to reduce noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structured logger
    """
    return structlog.get_logger(name)


def redact_sensitive_data(record: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive information from log records.

    Args:
        record: Log record dictionary

    Returns:
        Log record with sensitive data redacted
    """
    sensitive_fields = {
        "password",
        "passwd",
        "secret",
        "token",
        "key",
        "credential",
        "auth",
        "authorization",
        "certificate",
        "cert",
        "private",
    }

    def _redact_dict(data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: "[REDACTED]"
                if any(field in k.lower() for field in sensitive_fields)
                else _redact_dict(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [_redact_dict(item) for item in data]
        else:
            return data

    return _redact_dict(record)


# Add redaction processor for production use
def add_redaction_processor() -> None:
    """Add sensitive data redaction to the logging pipeline."""
    current_processors = structlog.get_config()["processors"]
    # Insert redaction before the final renderer
    current_processors.insert(-1, redact_sensitive_data)
    structlog.configure(processors=current_processors)
