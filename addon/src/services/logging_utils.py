# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Structured logging utilities for grant lifecycle and operational decisions.

Provides consistent structured logging with context and decision tracking.
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import GrantStatus

logger = get_logger(__name__)


@contextmanager
def log_operation(
    operation: str, grant_id: str | None = None, **context: Any
) -> Generator[dict[str, Any]]:
    """Context manager for logging operations with timing and outcome.

    Args:
        operation: Operation name
        grant_id: Grant ID if applicable
        **context: Additional context fields

    Yields:
        Context dictionary for adding additional fields

    Example:
        with log_operation("provision_grant", grant_id="123") as ctx:
            # Perform operation
            ctx["controller_id"] = "abc"
            # Exceptions are automatically logged
    """
    start_time = datetime.now(UTC)
    op_context: dict[str, Any] = {"grant_id": grant_id, **context}

    logger.info(f"{operation}_started", operation=operation, **op_context)

    try:
        yield op_context
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        logger.info(
            f"{operation}_completed",
            operation=operation,
            duration_ms=round(duration_ms, 2),
            success=True,
            **op_context,
        )

    except Exception as e:
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        logger.error(
            f"{operation}_failed",
            operation=operation,
            duration_ms=round(duration_ms, 2),
            success=False,
            error=str(e),
            error_type=type(e).__name__,
            **op_context,
        )
        raise


def log_lifecycle_transition(
    grant_id: str,
    from_status: GrantStatus | None,
    to_status: GrantStatus,
    reason: str | None = None,
    **context: Any,
) -> None:
    """Log grant lifecycle state transition.

    Args:
        grant_id: Grant ID
        from_status: Previous status (None if newly created)
        to_status: New status
        reason: Reason for transition
        **context: Additional context
    """
    logger.info(
        "grant_lifecycle_transition",
        grant_id=grant_id,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        reason=reason,
        **context,
    )


def log_decision(
    decision_type: str, decision: str, rationale: str, **context: Any
) -> None:
    """Log operational decision with rationale.

    Args:
        decision_type: Type of decision (e.g., "queue_scaling", "retry_policy")
        decision: Decision made (e.g., "scale_up", "abort_retry")
        rationale: Explanation of why decision was made
        **context: Additional context

    Example:
        log_decision(
            "queue_scaling",
            "scale_up",
            "Queue depth exceeded threshold",
            current_depth=150,
            threshold=100
        )
    """
    logger.info(
        "operational_decision",
        decision_type=decision_type,
        decision=decision,
        rationale=rationale,
        **context,
    )


def log_performance_metric(
    metric_name: str,
    value: float,
    unit: str,
    threshold: float | None = None,
    **context: Any,
) -> None:
    """Log performance metric with threshold comparison.

    Args:
        metric_name: Name of metric
        value: Metric value
        unit: Unit of measurement
        threshold: Optional threshold for comparison
        **context: Additional context

    Example:
        log_performance_metric(
            "provision_latency",
            value=125.5,
            unit="ms",
            threshold=200.0,
            grant_id="123"
        )
    """
    exceeds_threshold = threshold is not None and value > threshold

    logger.info(
        "performance_metric",
        metric_name=metric_name,
        value=round(value, 2),
        unit=unit,
        threshold=threshold,
        exceeds_threshold=exceeds_threshold,
        **context,
    )


def log_controller_operation(
    operation: str,
    controller_type: str,
    success: bool,
    duration_ms: float | None = None,
    error: str | None = None,
    **context: Any,
) -> None:
    """Log controller operation with timing and outcome.

    Args:
        operation: Operation name (e.g., "provision", "revoke", "extend")
        controller_type: Type of controller (e.g., "tp-omada", "unifi")
        success: Whether operation succeeded
        duration_ms: Operation duration in milliseconds
        error: Error message if failed
        **context: Additional context (grant_id, controller_voucher_id, etc.)
    """
    log_data = {
        "operation": operation,
        "controller_type": controller_type,
        "success": success,
        **context,
    }

    if duration_ms is not None:
        log_data["duration_ms"] = round(duration_ms, 2)

    if error:
        log_data["error"] = error

    level = "info" if success else "error"
    getattr(logger, level)("controller_operation", **log_data)


def log_audit_event(
    event_type: str,
    grant_id: str,
    user_id: str | None = None,
    **context: Any,
) -> None:
    """Log audit event for compliance tracking.

    Args:
        event_type: Type of audit event
        grant_id: Grant ID
        user_id: User who performed the action
        **context: Additional audit context
    """
    logger.info(
        "audit_event",
        event_type=event_type,
        grant_id=grant_id,
        user_id=user_id,
        timestamp=datetime.now(UTC).isoformat(),
        **context,
    )


def log_resource_state(
    resource_type: str, resource_id: str, state: dict[str, Any]
) -> None:
    """Log resource state snapshot for debugging.

    Args:
        resource_type: Type of resource (e.g., "grant", "queue", "controller")
        resource_id: Resource identifier
        state: Current state dictionary
    """
    logger.debug(
        "resource_state_snapshot",
        resource_type=resource_type,
        resource_id=resource_id,
        state=state,
    )
