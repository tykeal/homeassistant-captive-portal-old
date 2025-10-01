# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration helpers for queue scheduler with grant and voucher operations."""

import asyncio
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import AccessGrant
from .audit_logger import get_audit_logger
from .grant_manager import get_grant_manager
from .queue_scheduler import TaskPriority, get_queue_scheduler
from .voucher_service import get_voucher_service

logger = get_logger(__name__)


class QueuedOperations:
    """Helper class for queuing grant and voucher operations."""

    def __init__(self):
        """Initialize queued operations."""
        self.scheduler = get_queue_scheduler()
        self.grant_manager = get_grant_manager()
        self.voucher_service = get_voucher_service()
        self.audit_logger = get_audit_logger()

    async def queue_grant_activation(
        self,
        grant: AccessGrant,
        controller_voucher_id: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        **audit_context,
    ) -> None:
        """Queue grant activation with controller provisioning.

        Args:
            grant: Grant to activate
            controller_voucher_id: Controller voucher ID if already provisioned
            priority: Task priority
            **audit_context: Additional audit context
        """

        async def _activate_grant() -> dict[str, Any]:
            """Internal activation task."""
            try:
                # Activate the grant
                activated_grant = await self.grant_manager.activate_grant(
                    grant=grant,
                    controller_voucher_id=controller_voucher_id,
                    **audit_context,
                )

                return {
                    "status": "success",
                    "grant_id": activated_grant.grant_id,
                    "activated_at": activated_grant.activated_at.isoformat()
                    if activated_grant.activated_at
                    else None,
                }

            except Exception as e:
                # Update grant with error
                await self.grant_manager.update_grant_error(grant, str(e))

                # Log controller error
                await self.audit_logger.log_controller_error(
                    operation="activate_grant",
                    error=str(e),
                    grant_id=grant.grant_id,
                    **audit_context,
                )

                raise

        task_id = f"activate_grant_{grant.grant_id}"

        await self.scheduler.submit_task(
            task_id=task_id,
            coro=_activate_grant,
            priority=priority,
            context={
                "operation": "activate_grant",
                "grant_id": grant.grant_id,
                "booking_id": grant.booking_id,
                "guest_name": grant.guest_name,
            },
        )

        logger.debug(
            "Grant activation queued",
            task_id=task_id,
            grant_id=grant.grant_id,
            priority=priority.name,
        )

    async def queue_grant_revocation(
        self,
        grant: AccessGrant,
        reason: str,
        user_id: str | None = None,
        priority: TaskPriority = TaskPriority.HIGH,
        **audit_context,
    ) -> None:
        """Queue grant revocation with controller cleanup.

        Args:
            grant: Grant to revoke
            reason: Revocation reason
            user_id: User revoking the grant
            priority: Task priority (default HIGH for revocations)
            **audit_context: Additional audit context
        """

        async def _revoke_grant() -> dict[str, Any]:
            """Internal revocation task."""
            try:
                # Revoke the grant
                revoked_grant = await self.grant_manager.revoke_grant(
                    grant=grant, reason=reason, user_id=user_id, **audit_context
                )

                # TODO: Add controller cleanup call here when controller adapter is implemented

                return {
                    "status": "success",
                    "grant_id": revoked_grant.grant_id,
                    "revoked_at": revoked_grant.revoked_at.isoformat()
                    if revoked_grant.revoked_at
                    else None,
                    "reason": reason,
                }

            except Exception as e:
                # Log controller error
                await self.audit_logger.log_controller_error(
                    operation="revoke_grant",
                    error=str(e),
                    grant_id=grant.grant_id,
                    **audit_context,
                )

                raise

        task_id = f"revoke_grant_{grant.grant_id}"

        await self.scheduler.submit_task(
            task_id=task_id,
            coro=_revoke_grant,
            priority=priority,
            context={
                "operation": "revoke_grant",
                "grant_id": grant.grant_id,
                "reason": reason,
                "user_id": user_id,
            },
        )

        logger.debug(
            "Grant revocation queued",
            task_id=task_id,
            grant_id=grant.grant_id,
            reason=reason,
            priority=priority.name,
        )

    async def queue_voucher_cleanup(
        self, priority: TaskPriority = TaskPriority.LOW
    ) -> None:
        """Queue voucher expiry cleanup task.

        Args:
            priority: Task priority (default LOW for maintenance)
        """

        async def _cleanup_vouchers() -> dict[str, Any]:
            """Internal voucher cleanup task."""
            expired_count = await self.voucher_service.expire_vouchers()

            return {"status": "success", "expired_count": expired_count}

        task_id = f"voucher_cleanup_{int(asyncio.get_event_loop().time())}"

        await self.scheduler.submit_task(
            task_id=task_id,
            coro=_cleanup_vouchers,
            priority=priority,
            context={"operation": "voucher_cleanup"},
        )

        logger.debug("Voucher cleanup queued", task_id=task_id, priority=priority.name)

    async def queue_grant_lifecycle_processing(
        self, priority: TaskPriority = TaskPriority.NORMAL
    ) -> None:
        """Queue grant lifecycle processing (activation + expiry).

        Args:
            priority: Task priority
        """

        async def _process_lifecycle() -> dict[str, Any]:
            """Internal lifecycle processing task."""
            stats = await self.grant_manager.process_grant_lifecycle()

            return {"status": "success", **stats}

        task_id = f"grant_lifecycle_{int(asyncio.get_event_loop().time())}"

        await self.scheduler.submit_task(
            task_id=task_id,
            coro=_process_lifecycle,
            priority=priority,
            context={"operation": "grant_lifecycle_processing"},
        )

        logger.debug(
            "Grant lifecycle processing queued", task_id=task_id, priority=priority.name
        )

    async def get_queue_health(self) -> dict[str, Any]:
        """Get queue health status.

        Returns:
            Dictionary with queue health information
        """
        metrics = self.scheduler.get_metrics()
        status = self.scheduler.get_queue_status()

        # Determine health status
        health_status = "healthy"
        issues = []

        # Check for high queue depth
        if metrics["queue_depth"] > metrics["active_workers"] * 5:
            health_status = "degraded"
            issues.append("High queue depth")

        # Check for high failure rate
        total_tasks = metrics["tasks_processed"] + metrics["tasks_failed"]
        if total_tasks > 0:
            failure_rate = metrics["tasks_failed"] / total_tasks
            if failure_rate > 0.1:  # 10% failure rate
                health_status = "unhealthy"
                issues.append(f"High failure rate: {failure_rate:.1%}")

        # Check for high latency
        if metrics["p95_processing_time_ms"] > metrics["latency_threshold_ms"] * 2:
            health_status = "degraded"
            issues.append("High processing latency")

        return {
            "status": health_status,
            "issues": issues,
            "metrics": metrics,
            "queue_status": status,
        }


# Global queued operations instance
_queued_operations: QueuedOperations | None = None


def get_queued_operations() -> QueuedOperations:
    """Get the global queued operations instance."""
    global _queued_operations
    if _queued_operations is None:
        _queued_operations = QueuedOperations()
    return _queued_operations
