# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Automatic expiry scheduler for grant lifecycle management.

This service runs periodically to:
1. Expire grants past their end_time + grace period
2. Revoke network access for expired grants
3. Process pending activations

FR-003: Revoke network access within grace period after stay end
"""

import asyncio
from datetime import UTC, datetime, timedelta

from ..core.logging_config import get_logger
from ..models.domain import GrantStatus
from ..services.audit_logger import get_audit_logger
from ..services.grant_manager import get_grant_manager

logger = get_logger(__name__)


class ExpiryScheduler:
    """Scheduler for automatic grant expiry and revocation.

    Runs background task to:
    - Check for grants past end_time
    - Apply grace period before revocation
    - Mark grants as expired
    - Revoke controller access
    - Log all lifecycle transitions

    FR-003: Revoke network access within grace period after stay end
    """

    def __init__(
        self, grace_period_minutes: int = 30, check_interval_seconds: int = 300
    ):
        """Initialize the expiry scheduler.

        Args:
            grace_period_minutes: Minutes after end_time before revocation (default 30)
            check_interval_seconds: Seconds between expiry checks (default 300 = 5 min)
        """
        self.grace_period_minutes = grace_period_minutes
        self.check_interval_seconds = check_interval_seconds
        self._running = False
        self._scheduler_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the expiry scheduler background task."""
        if self._running:
            logger.warning("Expiry scheduler already running")
            return

        self._running = True
        logger.info(
            "Starting expiry scheduler",
            grace_period_minutes=self.grace_period_minutes,
            check_interval_seconds=self.check_interval_seconds,
        )

        # Start background task
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the expiry scheduler background task."""
        if not self._running:
            return

        logger.info("Stopping expiry scheduler")
        self._running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        logger.info("Expiry scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Background task that periodically processes expiries."""
        logger.info("Expiry scheduler loop started")

        while self._running:
            try:
                await self.process_expiries()
            except Exception as e:
                logger.error(
                    "Error in expiry scheduler loop",
                    error=str(e),
                )

            # Wait before next check
            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("Expiry scheduler loop stopped")

    async def process_expiries(self) -> dict[str, int]:
        """Process all grants that should be expired.

        Checks for grants that have passed their end_time + grace period
        and marks them as expired, then revokes network access.

        Returns:
            Dictionary with counts of processed grants:
            - expired: Number of grants marked as expired
            - revoked: Number of grants with access revoked
            - failed: Number of grants that failed processing
        """
        grant_manager = get_grant_manager()
        audit_logger = get_audit_logger()
        now = datetime.now(UTC)

        # Calculate expiry threshold (now - grace period)
        grace_delta = timedelta(minutes=self.grace_period_minutes)
        expiry_threshold = now - grace_delta

        logger.debug(
            "Processing grant expiries",
            current_time=now.isoformat(),
            expiry_threshold=expiry_threshold.isoformat(),
            grace_period_minutes=self.grace_period_minutes,
        )

        # Get all non-expired grants
        all_grants = await grant_manager.list_grants(limit=10000)
        active_grants = [
            g
            for g in all_grants
            if g.status in [GrantStatus.ACTIVE, GrantStatus.PENDING]
        ]

        expired_count = 0
        revoked_count = 0
        failed_count = 0

        for grant in active_grants:
            # Check if grant has passed end_time + grace period
            if grant.end_time <= expiry_threshold:
                try:
                    # Mark as expired and revoke
                    grant.status = GrantStatus.EXPIRED
                    grant.modified_at = now

                    # Update grant
                    from ..storage.database import get_db_session
                    from ..storage.repository import GrantRepository

                    async with get_db_session() as session:
                        grant_repo = GrantRepository(session)
                        await grant_repo.update(grant)

                    expired_count += 1

                    # Log expiry event
                    await audit_logger.log_grant_expired(
                        grant=grant,
                        reason="Automatic expiry after grace period",
                    )

                    logger.info(
                        "Grant expired after grace period",
                        grant_id=grant.grant_id,
                        booking_id=grant.booking_id,
                        end_time=grant.end_time.isoformat(),
                        grace_period_minutes=self.grace_period_minutes,
                    )

                    # Revoke controller access if provisioned (T031)
                    if grant.controller_voucher_id:
                        try:
                            from ..controllers.factory import get_controller

                            controller = get_controller()

                            logger.info(
                                "Revoking controller access for expired grant",
                                grant_id=grant.grant_id,
                                controller_voucher_id=grant.controller_voucher_id,
                            )

                            result = await controller.revoke_grant(
                                controller_voucher_id=grant.controller_voucher_id,
                                reason="Automatic expiry after grace period",
                            )

                            if result.success:
                                revoked_count += 1
                                logger.info(
                                    "Controller access revoked successfully",
                                    grant_id=grant.grant_id,
                                )
                            else:
                                logger.warning(
                                    "Controller revocation completed with non-success",
                                    grant_id=grant.grant_id,
                                    result=result.model_dump(),
                                )

                        except Exception as e:
                            logger.error(
                                "Failed to revoke controller access",
                                grant_id=grant.grant_id,
                                controller_voucher_id=grant.controller_voucher_id,
                                error=str(e),
                            )
                            # Continue - grant is marked expired in database

                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Failed to expire grant",
                        grant_id=grant.grant_id,
                        error=str(e),
                    )

        if expired_count > 0 or failed_count > 0:
            logger.info(
                "Expiry processing complete",
                expired_count=expired_count,
                revoked_count=revoked_count,
                failed_count=failed_count,
            )

        return {
            "expired": expired_count,
            "revoked": revoked_count,
            "failed": failed_count,
        }

    async def get_grace_period_minutes(self) -> int:
        """Get current grace period in minutes."""
        return self.grace_period_minutes

    async def set_grace_period_minutes(self, minutes: int) -> None:
        """Update grace period (for testing or configuration changes).

        Args:
            minutes: New grace period in minutes (must be >= 0)

        Raises:
            ValueError: If minutes is negative
        """
        if minutes < 0:
            raise ValueError("Grace period must be non-negative")

        old_period = self.grace_period_minutes
        self.grace_period_minutes = minutes

        logger.info(
            "Grace period updated",
            old_grace_period_minutes=old_period,
            new_grace_period_minutes=minutes,
        )


# Global scheduler instance
_expiry_scheduler: ExpiryScheduler | None = None


def get_expiry_scheduler() -> ExpiryScheduler:
    """Get the global expiry scheduler instance."""
    global _expiry_scheduler
    if _expiry_scheduler is None:
        _expiry_scheduler = ExpiryScheduler()
    return _expiry_scheduler
