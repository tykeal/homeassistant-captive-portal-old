# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Metrics exporter for grant lifecycle and queue operations.

Provides Prometheus-style metrics for monitoring:
- Active grants count
- Queue depth (pending provisions)
- Provision latency (p50, p95, p99)
- Failed provisions count
- Grant lifecycle events
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import GrantStatus

logger = get_logger(__name__)


@dataclass
class ControllerMetrics:
    """Controller operation metrics for tracking controller interactions."""

    # Counters
    requests_total: int = 0
    failures_total: int = 0
    retry_attempts_total: int = 0
    successes_total: int = 0

    # Per-operation counters
    provision_requests: int = 0
    provision_failures: int = 0
    revoke_requests: int = 0
    revoke_failures: int = 0
    extend_requests: int = 0
    extend_failures: int = 0

    def record_request(
        self, operation: str, success: bool, retry_count: int = 0
    ) -> None:
        """Record a controller operation request.

        Args:
            operation: Operation type (provision, revoke, extend)
            success: Whether the operation succeeded
            retry_count: Number of retries attempted
        """
        self.requests_total += 1
        self.retry_attempts_total += retry_count

        if success:
            self.successes_total += 1
        else:
            self.failures_total += 1

        # Track per-operation metrics
        if operation == "provision_grant":
            self.provision_requests += 1
            if not success:
                self.provision_failures += 1
        elif operation == "revoke_grant":
            self.revoke_requests += 1
            if not success:
                self.revoke_failures += 1
        elif operation == "extend_grant":
            self.extend_requests += 1
            if not success:
                self.extend_failures += 1


@dataclass
class GrantMetrics:
    """Grant lifecycle metrics."""

    # Counters
    total_grants_created: int = 0
    total_grants_activated: int = 0
    total_grants_expired: int = 0
    total_grants_revoked: int = 0
    total_provisions_attempted: int = 0
    total_provisions_succeeded: int = 0
    total_provisions_failed: int = 0

    # Gauges
    active_grants: int = 0
    pending_grants: int = 0
    expired_grants: int = 0
    revoked_grants: int = 0
    queue_depth: int = 0  # Grants awaiting provisioning

    # Latency tracking (milliseconds)
    provision_latencies: list[float] = field(default_factory=list)
    max_latency_samples: int = 1000  # Keep last 1000 samples

    # Grant status distribution
    status_counts: dict[GrantStatus, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    # Error tracking
    last_provision_error: str | None = None
    last_provision_error_time: datetime | None = None

    def record_grant_created(self) -> None:
        """Record a grant creation."""
        self.total_grants_created += 1
        self.pending_grants += 1
        self.queue_depth += 1

    def record_grant_activated(self, provision_latency_ms: float | None = None) -> None:
        """Record a grant activation.

        Args:
            provision_latency_ms: Time taken to provision (milliseconds)
        """
        self.total_grants_activated += 1
        self.pending_grants = max(0, self.pending_grants - 1)
        self.active_grants += 1
        self.queue_depth = max(0, self.queue_depth - 1)

        if provision_latency_ms is not None:
            self._record_latency(provision_latency_ms)

    def record_grant_expired(self) -> None:
        """Record a grant expiration."""
        self.total_grants_expired += 1
        self.active_grants = max(0, self.active_grants - 1)
        self.expired_grants += 1

    def record_grant_revoked(self) -> None:
        """Record a grant revocation."""
        self.total_grants_revoked += 1
        self.active_grants = max(0, self.active_grants - 1)
        self.revoked_grants += 1

    def record_provision_attempt(self, success: bool, error: str | None = None) -> None:
        """Record a provision attempt.

        Args:
            success: Whether provision succeeded
            error: Error message if failed
        """
        self.total_provisions_attempted += 1

        if success:
            self.total_provisions_succeeded += 1
        else:
            self.total_provisions_failed += 1
            self.last_provision_error = error
            self.last_provision_error_time = datetime.now(UTC)

    def _record_latency(self, latency_ms: float) -> None:
        """Record a provision latency sample.

        Args:
            latency_ms: Latency in milliseconds
        """
        self.provision_latencies.append(latency_ms)

        # Keep only the most recent samples
        if len(self.provision_latencies) > self.max_latency_samples:
            self.provision_latencies = self.provision_latencies[
                -self.max_latency_samples :
            ]

    def update_status_counts(self, status_counts: dict[GrantStatus, int]) -> None:
        """Update grant status distribution.

        Args:
            status_counts: Dictionary of status -> count
        """
        self.status_counts = dict(status_counts)

        # Update gauges from status counts
        self.active_grants = status_counts.get(GrantStatus.ACTIVE, 0)
        self.pending_grants = status_counts.get(GrantStatus.PENDING, 0)
        self.expired_grants = status_counts.get(GrantStatus.EXPIRED, 0)
        self.revoked_grants = status_counts.get(GrantStatus.REVOKED, 0)

        # Queue depth is pending grants without controller_voucher_id
        # For now, approximate as pending grants
        self.queue_depth = self.pending_grants

    def get_latency_percentile(self, percentile: float) -> float | None:
        """Get latency percentile.

        Args:
            percentile: Percentile to calculate (0-100)

        Returns:
            Latency at percentile in milliseconds, or None if no samples
        """
        if not self.provision_latencies:
            return None

        sorted_latencies = sorted(self.provision_latencies)
        index = int(len(sorted_latencies) * percentile / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]

    def get_metrics_dict(self) -> dict[str, Any]:
        """Get metrics as dictionary.

        Returns:
            Dictionary of all metrics
        """
        return {
            # Counters
            "total_grants_created": self.total_grants_created,
            "total_grants_activated": self.total_grants_activated,
            "total_grants_expired": self.total_grants_expired,
            "total_grants_revoked": self.total_grants_revoked,
            "total_provisions_attempted": self.total_provisions_attempted,
            "total_provisions_succeeded": self.total_provisions_succeeded,
            "total_provisions_failed": self.total_provisions_failed,
            # Gauges
            "active_grants": self.active_grants,
            "pending_grants": self.pending_grants,
            "expired_grants": self.expired_grants,
            "revoked_grants": self.revoked_grants,
            "queue_depth": self.queue_depth,
            # Latency percentiles
            "provision_latency_p50_ms": self.get_latency_percentile(50),
            "provision_latency_p95_ms": self.get_latency_percentile(95),
            "provision_latency_p99_ms": self.get_latency_percentile(99),
            # Status distribution
            "status_counts": {
                status.value: count for status, count in self.status_counts.items()
            },
            # Error info
            "last_provision_error": self.last_provision_error,
            "last_provision_error_time": self.last_provision_error_time.isoformat()
            if self.last_provision_error_time
            else None,
        }

    def get_prometheus_format(self) -> str:
        """Get metrics in Prometheus exposition format.

        Returns:
            Metrics formatted for Prometheus scraping
        """
        lines = [
            "# HELP captive_portal_grants_total Total grants created",
            "# TYPE captive_portal_grants_total counter",
            f"captive_portal_grants_total {self.total_grants_created}",
            "",
            "# HELP captive_portal_grants_activated_total Total grants activated",
            "# TYPE captive_portal_grants_activated_total counter",
            f"captive_portal_grants_activated_total {self.total_grants_activated}",
            "",
            "# HELP captive_portal_grants_expired_total Total grants expired",
            "# TYPE captive_portal_grants_expired_total counter",
            f"captive_portal_grants_expired_total {self.total_grants_expired}",
            "",
            "# HELP captive_portal_grants_revoked_total Total grants revoked",
            "# TYPE captive_portal_grants_revoked_total counter",
            f"captive_portal_grants_revoked_total {self.total_grants_revoked}",
            "",
            "# HELP captive_portal_provisions_attempted_total Total provision attempts",
            "# TYPE captive_portal_provisions_attempted_total counter",
            f"captive_portal_provisions_attempted_total {self.total_provisions_attempted}",
            "",
            "# HELP captive_portal_provisions_succeeded_total Total successful provisions",
            "# TYPE captive_portal_provisions_succeeded_total counter",
            f"captive_portal_provisions_succeeded_total {self.total_provisions_succeeded}",
            "",
            "# HELP captive_portal_provisions_failed_total Total failed provisions",
            "# TYPE captive_portal_provisions_failed_total counter",
            f"captive_portal_provisions_failed_total {self.total_provisions_failed}",
            "",
            "# HELP captive_portal_active_grants Current active grants",
            "# TYPE captive_portal_active_grants gauge",
            f"captive_portal_active_grants {self.active_grants}",
            "",
            "# HELP captive_portal_pending_grants Current pending grants",
            "# TYPE captive_portal_pending_grants gauge",
            f"captive_portal_pending_grants {self.pending_grants}",
            "",
            "# HELP captive_portal_queue_depth Grants awaiting provisioning",
            "# TYPE captive_portal_queue_depth gauge",
            f"captive_portal_queue_depth {self.queue_depth}",
            "",
        ]

        # Add latency percentiles
        for percentile in [50, 95, 99]:
            value = self.get_latency_percentile(percentile)
            if value is not None:
                lines.extend(
                    [
                        f"# HELP captive_portal_provision_latency_p{percentile}_ms "
                        f"Provision latency p{percentile} (milliseconds)",
                        f"# TYPE captive_portal_provision_latency_p{percentile}_ms gauge",
                        f"captive_portal_provision_latency_p{percentile}_ms {value:.2f}",
                        "",
                    ]
                )

        return "\n".join(lines)

    def reset_counters(self) -> None:
        """Reset all counters (for testing)."""
        self.total_grants_created = 0
        self.total_grants_activated = 0
        self.total_grants_expired = 0
        self.total_grants_revoked = 0
        self.total_provisions_attempted = 0
        self.total_provisions_succeeded = 0
        self.total_provisions_failed = 0
        self.provision_latencies.clear()


class MetricsExporter:
    """Metrics exporter for grant lifecycle operations."""

    def __init__(self) -> None:
        """Initialize metrics exporter."""
        self.metrics = GrantMetrics()
        self.controller_metrics = ControllerMetrics()
        self._start_time = time.time()

    def record_provision_start(self) -> float:
        """Record start of provision operation.

        Returns:
            Start timestamp for latency tracking
        """
        return time.time()

    def record_provision_end(
        self, start_time: float, success: bool, error: str | None = None
    ) -> float:
        """Record end of provision operation.

        Args:
            start_time: Start timestamp from record_provision_start()
            success: Whether provision succeeded
            error: Error message if failed

        Returns:
            Latency in milliseconds
        """
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000

        self.metrics.record_provision_attempt(success, error)

        if success:
            self.metrics._record_latency(latency_ms)

        logger.debug(
            "Provision operation completed",
            success=success,
            latency_ms=round(latency_ms, 2),
            error=error,
        )

        return latency_ms

    def record_controller_operation(
        self, operation: str, success: bool, retry_count: int = 0
    ) -> None:
        """Record a controller operation.

        Args:
            operation: Operation type (provision_grant, revoke_grant, extend_grant)
            success: Whether the operation succeeded
            retry_count: Number of retries attempted
        """
        self.controller_metrics.record_request(operation, success, retry_count)

        logger.debug(
            "Controller operation recorded",
            operation=operation,
            success=success,
            retry_count=retry_count,
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics as dictionary.

        Returns:
            Dictionary of all metrics
        """
        metrics = self.metrics.get_metrics_dict()

        # Add exporter metadata
        metrics["uptime_seconds"] = int(time.time() - self._start_time)

        return metrics

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format.

        Returns:
            Prometheus exposition format metrics
        """
        return self.metrics.get_prometheus_format()


# Global metrics exporter instance
_metrics_exporter: MetricsExporter | None = None


def get_metrics_exporter() -> MetricsExporter:
    """Get the global metrics exporter instance.

    Returns:
        Global MetricsExporter instance
    """
    global _metrics_exporter
    if _metrics_exporter is None:
        _metrics_exporter = MetricsExporter()
    return _metrics_exporter


def set_metrics_exporter(exporter: MetricsExporter) -> None:
    """Set a custom metrics exporter (for testing).

    Args:
        exporter: Custom MetricsExporter instance
    """
    global _metrics_exporter
    _metrics_exporter = exporter
