# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Grant manager for lifecycle management (pending→active, extend, shorten, revoke)."""

from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import AccessGrant, GrantSource, GrantStatus
from ..services.audit_logger import get_audit_logger
from ..services.logging_utils import (
    log_controller_operation,
    log_lifecycle_transition,
    log_performance_metric,
)
from ..services.metrics_exporter import get_metrics_exporter
from ..services.retry_policy import get_retry_policy
from ..storage.database import get_db_session
from ..storage.repository import GrantRepository

logger = get_logger(__name__)


class GrantManager:
    """Service for access grant lifecycle management."""

    def __init__(self):
        """Initialize grant manager."""
        self.audit_logger = get_audit_logger()
        self.metrics = get_metrics_exporter()

    async def create_grant(
        self,
        booking_id: str | None,
        start_time: datetime,
        end_time: datetime,
        guest_name: str,
        source: GrantSource,
        device_mac: str | None = None,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Create a new access grant.

        Args:
            booking_id: Rental Control booking ID (if applicable)
            start_time: Grant start time
            end_time: Grant end time
            guest_name: Guest name
            source: Source of grant creation
            device_mac: Device MAC address (if known)
            user_id: User creating the grant
            **audit_context: Additional audit context

        Returns:
            Created grant

        Raises:
            ValueError: If parameters are invalid
        """
        # Validate time range
        if end_time <= start_time:
            raise ValueError("End time must be after start time")

        # Check for duplicate booking ID
        if booking_id:
            existing = await self.get_grant_by_booking_id(booking_id)
            if existing:
                raise ValueError(f"Grant already exists for booking ID: {booking_id}")

        # Create grant
        grant = AccessGrant(
            booking_id=booking_id,
            start_time=start_time,
            end_time=end_time,
            guest_name=guest_name,
            source=source,
            device_mac=device_mac,
        )

        # Always start in PENDING status - activation happens via activate_grant()
        # which handles controller provisioning and proper error handling
        grant.status = GrantStatus.PENDING

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.create(grant)

        # Record metrics (T033)
        self.metrics.metrics.record_grant_created()

        # Log creation
        await self.audit_logger.log_grant_created(
            grant=grant, user_id=user_id, **audit_context
        )

        # Log initial PENDING status
        # Structured lifecycle transition logging (T034)
        log_lifecycle_transition(
            grant_id=grant.grant_id,
            from_status=None,
            to_status=GrantStatus.PENDING,
            reason="Grant created - awaiting activation",
            booking_id=booking_id,
            source=source.value,
        )

        logger.info(
            "Grant created",
            grant_id=grant.grant_id,
            booking_id=booking_id,
            status=grant.status.value,
            source=source.value,
            guest_name=guest_name,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        return grant

    async def get_grant_by_id(self, grant_id: str) -> AccessGrant | None:
        """Get grant by ID.

        Args:
            grant_id: Grant ID

        Returns:
            Grant if found, None otherwise
        """
        async with get_db_session() as session:
            repository = GrantRepository(session)
            return await repository.get_by_id(grant_id)

    async def get_grant_by_booking_id(self, booking_id: str) -> AccessGrant | None:
        """Get grant by booking ID.

        Args:
            booking_id: Booking ID

        Returns:
            Grant if found, None otherwise
        """
        async with get_db_session() as session:
            repository = GrantRepository(session)
            return await repository.get_by_booking_id(booking_id)

    async def activate_grant(
        self,
        grant: AccessGrant,
        controller_voucher_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Activate a pending grant and provision network access (T031).

        Provisions network access via controller adapter if not already provisioned.
        Updates grant status to ACTIVE and records activation timestamp.

        Args:
            grant: Grant to activate
            controller_voucher_id: Controller voucher ID if already provisioned
            **audit_context: Additional audit context

        Returns:
            Updated grant with ACTIVE status

        Raises:
            ValueError: If grant cannot be activated
        """
        if grant.status != GrantStatus.PENDING:
            raise ValueError(f"Cannot activate grant with status: {grant.status}")

        now = datetime.now(UTC)

        # Check if grant should be activated
        if now < grant.start_time:
            raise ValueError("Grant start time has not been reached")

        if now > grant.end_time:
            raise ValueError("Grant has already expired")

        logger.info(
            "Activating grant",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            start_time=grant.start_time.isoformat(),
            end_time=grant.end_time.isoformat(),
        )

        # Provision network access via controller if not already provisioned (T031)
        provisioned_voucher_id = controller_voucher_id
        provision_success = False
        provision_latency = 0.0  # Track provision latency (T033)

        if not provisioned_voucher_id:
            try:
                from ..controllers.factory import get_controller

                controller = get_controller()

                logger.info(
                    "Provisioning network access",
                    grant_id=grant.grant_id,
                    booking_id=grant.booking_id,
                )

                # Track provision latency (T033)
                provision_start = self.metrics.record_provision_start()

                # Call controller with retry policy (T032)
                retry_policy = get_retry_policy()

                async def provision_operation() -> dict[str, Any]:
                    """Provision grant on controller."""
                    return await controller.provision_grant(
                        grant_id=grant.grant_id,
                        guest_name=grant.guest_name,
                        start_time=grant.start_time,
                        end_time=grant.end_time,
                        device_mac=None,
                    )

                result = await retry_policy.execute_with_retry(
                    operation=provision_operation,
                    operation_name="provision_grant",
                    grant_id=grant.grant_id,
                )

                # Record provision metrics (T033)
                provision_latency = self.metrics.record_provision_end(
                    provision_start, success=True
                )

                # Log performance metric (T034)
                log_performance_metric(
                    "provision_latency",
                    value=provision_latency,
                    unit="ms",
                    threshold=1000.0,  # Alert if > 1 second
                    grant_id=grant.grant_id,
                    operation="provision",
                )

                if result.success:
                    provisioned_voucher_id = result.controller_voucher_id
                    provision_success = True

                    # Structured controller operation logging (T034)
                    log_controller_operation(
                        operation="provision",
                        controller_type="tp-omada",  # TODO: Get from controller
                        success=True,
                        duration_ms=provision_latency,
                        grant_id=grant.grant_id,
                        controller_voucher_id=provisioned_voucher_id,
                    )
                    logger.info(
                        "Network access provisioned successfully",
                        grant_id=grant.grant_id,
                        controller_voucher_id=provisioned_voucher_id,
                    )
                else:
                    logger.warning(
                        "Controller provisioning completed with non-success status",
                        grant_id=grant.grant_id,
                        result=result,
                    )
                    # Continue with activation - will retry later

            except Exception as e:
                # Record failed provision (T033)
                provision_latency = self.metrics.record_provision_end(
                    provision_start, success=False, error=str(e)
                )

                # Structured controller operation logging (T034)
                log_controller_operation(
                    operation="provision",
                    controller_type="tp-omada",
                    success=False,
                    duration_ms=provision_latency,
                    error=str(e),
                    grant_id=grant.grant_id,
                )

                logger.error(
                    "Failed to provision network access",
                    grant_id=grant.grant_id,
                    error=str(e),
                )
                # Store error for debugging and retry tracking
                grant.last_error = str(e)
                grant.retry_count += 1
                grant.modified_at = now

                # Save grant with error info but keep status as PENDING
                async with get_db_session() as session:
                    repository = GrantRepository(session)
                    await repository.update(grant)

                # Propagate the exception so API knows activation failed
                raise ValueError(f"Failed to provision grant: {e}") from e

        # Only reach here if provisioning succeeded
        # Update grant to ACTIVE status
        grant.status = GrantStatus.ACTIVE
        grant.activated_at = now
        grant.controller_voucher_id = provisioned_voucher_id
        grant.modified_at = now

        # Clear any previous errors if provisioning succeeded
        if provision_success:
            grant.last_error = None
            grant.retry_count = 0

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            updated_grant = await repository.update(grant)

        # Record activation metrics (T033)
        self.metrics.metrics.record_grant_activated(
            provision_latency_ms=provision_latency if provision_success else None
        )

        # Structured lifecycle transition logging (T034)
        log_lifecycle_transition(
            grant_id=updated_grant.grant_id,
            from_status=GrantStatus.PENDING,
            to_status=GrantStatus.ACTIVE,
            reason="Manual activation" if controller_voucher_id else "Auto activation",
            provision_success=provision_success,
            controller_voucher_id=provisioned_voucher_id,
        )

        # Log activation
        await self.audit_logger.log_grant_activated(
            grant=updated_grant,
            controller_voucher_id=provisioned_voucher_id,
            provision_success=provision_success,
            **audit_context,
        )

        logger.info(
            "Grant activated successfully",
            grant_id=updated_grant.grant_id,
            booking_id=updated_grant.booking_id,
            controller_voucher_id=provisioned_voucher_id,
            provision_success=provision_success,
            activated_at=updated_grant.activated_at.isoformat()
            if updated_grant.activated_at
            else None,
        )

        return updated_grant

    async def extend_grant(
        self,
        grant: AccessGrant,
        new_end_time: datetime,
        reason: str,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Extend a grant to a new end time (FR-004, FR-012).

        Extends grant duration with validation and audit logging.
        Can extend controller voucher if already provisioned.

        Args:
            grant: Grant to extend
            new_end_time: New end time (must be after current end_time)
            reason: Reason for extension
            user_id: User extending the grant
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be extended or invalid parameters
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot extend grant with status: {grant.status}")

        # Validate new_end_time is after current end_time
        if new_end_time <= grant.end_time:
            raise ValueError(
                f"New end time ({new_end_time.isoformat()}) must be after "
                f"current end time ({grant.end_time.isoformat()})"
            )

        # Store old end time for audit
        old_end_time = grant.end_time

        logger.info(
            "Extending grant",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat(),
            reason=reason,
            user_id=user_id,
        )

        # Update grant
        grant.extend_grant(new_end_time, reason)

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            updated_grant = await repository.update(grant)

        # Extend controller voucher if already provisioned
        controller_extended = False
        if updated_grant.controller_voucher_id:
            try:
                from ..controllers.factory import get_controller

                controller = get_controller()

                logger.info(
                    "Extending controller voucher",
                    grant_id=updated_grant.grant_id,
                    controller_voucher_id=updated_grant.controller_voucher_id,
                    new_end_time=new_end_time.isoformat(),
                )

                result = await controller.extend_grant(
                    controller_voucher_id=updated_grant.controller_voucher_id,
                    new_end_time=new_end_time,
                )

                if result.success:
                    controller_extended = True
                    logger.info(
                        "Controller voucher extended successfully",
                        grant_id=updated_grant.grant_id,
                    )
                else:
                    logger.warning(
                        "Controller extension completed with non-success status",
                        grant_id=updated_grant.grant_id,
                        result=result,
                    )

            except Exception as e:
                logger.error(
                    "Failed to extend controller voucher",
                    grant_id=updated_grant.grant_id,
                    controller_voucher_id=updated_grant.controller_voucher_id,
                    error=str(e),
                )
                # Continue - grant is extended in database

        # Log extension (FR-008)
        await self.audit_logger.log_grant_extended(
            grant=updated_grant,
            old_end_time=old_end_time,
            new_end_time=new_end_time,
            reason=reason,
            user_id=user_id,
            controller_extended=controller_extended,
            **audit_context,
        )

        logger.info(
            "Grant extended successfully",
            grant_id=updated_grant.grant_id,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat(),
            reason=reason,
            extended_by=user_id,
            controller_extended=controller_extended,
        )

        return updated_grant

    async def shorten_grant(
        self,
        grant: AccessGrant,
        new_end_time: datetime | None,
        reason: str,
        immediate: bool = False,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Shorten a grant or terminate immediately (FR-004, FR-012, FR-013).

        Supports both scheduled shortening and immediate termination.
        Validates new_end_time and clamps to now if in the past.

        Args:
            grant: Grant to shorten
            new_end_time: New end time (if not immediate)
            reason: Reason for shortening
            immediate: Whether to terminate immediately
            user_id: User shortening the grant
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be shortened or invalid parameters
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot shorten grant with status: {grant.status}")

        if not immediate and not new_end_time:
            raise ValueError("Must provide new_end_time or set immediate=True")

        # Clamp future end times that are not shortening (FR-013)
        now = datetime.now(UTC)
        if new_end_time and new_end_time >= grant.end_time:
            raise ValueError(
                f"New end time ({new_end_time.isoformat()}) must be before "
                f"current end time ({grant.end_time.isoformat()})"
            )

        # Clamp past times to now with warning (FR-013)
        if new_end_time and new_end_time < now:
            logger.warning(
                "Shortening new_end_time is in past, clamping to now",
                grant_id=grant.grant_id,
                requested_end_time=new_end_time.isoformat(),
                clamped_to=now.isoformat(),
            )
            new_end_time = now

        # Store old end time for audit
        old_end_time = grant.end_time

        logger.info(
            "Shortening grant",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat() if new_end_time else None,
            immediate=immediate,
            reason=reason,
            user_id=user_id,
        )

        # Update grant
        grant.shorten_grant(new_end_time, reason, immediate)

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            updated_grant = await repository.update(grant)

        # Log shortening (FR-008)
        await self.audit_logger.log_grant_shortened(
            grant=updated_grant,
            old_end_time=old_end_time,
            new_end_time=new_end_time,
            reason=reason,
            immediate=immediate,
            user_id=user_id,
            **audit_context,
        )

        # If immediate, also log revocation
        if immediate:
            await self.audit_logger.log_grant_revoked(
                grant=updated_grant, reason=reason, user_id=user_id, **audit_context
            )

        logger.info(
            "Grant shortened successfully",
            grant_id=updated_grant.grant_id,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat() if new_end_time else None,
            immediate=immediate,
            reason=reason,
            shortened_by=user_id,
        )

        return updated_grant

    async def revoke_grant(
        self,
        grant: AccessGrant,
        reason: str,
        user_id: str | None = None,
        immediate: bool = True,
        **audit_context,
    ) -> AccessGrant:
        """Revoke a grant immediately (FR-013, FR-019).

        This implements forced termination with controller integration.
        When immediate=True, this revokes network access immediately.
        Otherwise, it schedules revocation (clamps to now with warning).

        Args:
            grant: Grant to revoke
            reason: Reason for revocation
            user_id: User revoking the grant
            immediate: Whether to revoke immediately (default True)
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be revoked
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot revoke grant with status: {grant.status}")

        logger.info(
            "Revoking grant",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            status=grant.status.value,
            reason=reason,
            immediate=immediate,
            user_id=user_id,
        )

        # Update grant status
        grant.status = GrantStatus.REVOKED
        grant.revoked_at = datetime.now(UTC)
        grant.revocation_reason = reason
        grant.modified_at = grant.revoked_at

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            updated_grant = await repository.update(grant)

        # Record revocation metrics (T033)
        self.metrics.metrics.record_grant_revoked()

        # Revoke controller access if provisioned (FR-013, FR-019)
        controller_revoked = False
        if updated_grant.controller_voucher_id:
            try:
                from ..controllers.factory import get_controller

                controller = get_controller()

                # Call controller to revoke access
                logger.info(
                    "Revoking controller access",
                    grant_id=updated_grant.grant_id,
                    controller_voucher_id=updated_grant.controller_voucher_id,
                )

                result = await controller.revoke_grant(
                    controller_voucher_id=updated_grant.controller_voucher_id,
                    reason=reason,
                )

                if result.success:
                    controller_revoked = True
                    logger.info(
                        "Controller access revoked successfully",
                        grant_id=updated_grant.grant_id,
                        controller_voucher_id=updated_grant.controller_voucher_id,
                    )
                else:
                    logger.warning(
                        "Controller revocation completed with non-success status",
                        grant_id=updated_grant.grant_id,
                        result=result,
                    )

            except Exception as e:
                logger.error(
                    "Failed to revoke controller access",
                    grant_id=updated_grant.grant_id,
                    controller_voucher_id=updated_grant.controller_voucher_id,
                    error=str(e),
                )
                # Continue - grant is revoked in database even if controller call fails
                # This will be retried by the expiry scheduler

        # Audit log the revocation (FR-008, FR-013, FR-019)
        await self.audit_logger.log_grant_revoked(
            grant=updated_grant,
            reason=reason,
            user_id=user_id,
            immediate=immediate,
            controller_revoked=controller_revoked,
            **audit_context,
        )

        logger.info(
            "Grant revoked successfully",
            grant_id=updated_grant.grant_id,
            controller_revoked=controller_revoked,
        )

        return updated_grant
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.update(grant)

        # Log revocation
        await self.audit_logger.log_grant_revoked(
            grant=grant, reason=reason, user_id=user_id, **audit_context
        )

        logger.info(
            "Grant revoked",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            guest_name=grant.guest_name,
            reason=reason,
            revoked_by=user_id,
            revoked_at=grant.revoked_at.isoformat(),
        )

        return grant

    async def expire_grant(self, grant: AccessGrant, **audit_context) -> AccessGrant:
        """Expire a grant that has passed its end time.

        Args:
            grant: Grant to expire
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be expired
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot expire grant with status: {grant.status}")

        now = datetime.now(UTC)
        if now <= grant.end_time:
            raise ValueError("Grant has not yet reached its end time")

        # Update grant
        grant.status = GrantStatus.EXPIRED
        grant.modified_at = now

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            updated_grant = await repository.update(grant)

        # Record expiry metrics (T033)
        self.metrics.metrics.record_grant_expired()

        # Log expiration
        await self.audit_logger.log_grant_expired(grant=updated_grant, **audit_context)

        logger.info(
            "Grant expired",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            guest_name=grant.guest_name,
            end_time=grant.end_time.isoformat(),
            expired_at=now.isoformat(),
        )

        return grant

    async def update_grant_error(
        self, grant: AccessGrant, error: str, increment_retry: bool = True
    ) -> AccessGrant:
        """Update grant with error information.

        Args:
            grant: Grant to update
            error: Error message
            increment_retry: Whether to increment retry count

        Returns:
            Updated grant
        """
        grant.last_error = error
        if increment_retry:
            grant.retry_count += 1
        grant.modified_at = datetime.now(UTC)

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.update(grant)

        logger.warning(
            "Grant error updated",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            error=error,
            retry_count=grant.retry_count,
        )

        return grant

    async def list_grants(
        self,
        status: GrantStatus | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AccessGrant]:
        """List grants with optional filtering.

        Args:
            status: Filter by status
            source: Filter by source
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of grants
        """
        async with get_db_session() as session:
            repository = GrantRepository(session)
            return await repository.list_grants(
                status=status, source=source, limit=limit, offset=offset
            )

    async def get_grants_needing_activation(self) -> list[AccessGrant]:
        """Get grants that should be activated (past start time, still pending).

        Returns:
            List of grants needing activation
        """
        async with get_db_session() as session:
            repository = GrantRepository(session)
            return await repository.get_grants_needing_activation()

    async def get_grants_needing_expiry(self) -> list[AccessGrant]:
        """Get grants that should be expired (past end time).

        Returns:
            List of grants needing expiry
        """
        async with get_db_session() as session:
            repository = GrantRepository(session)
            return await repository.get_grants_needing_expiry()

    async def process_grant_lifecycle(self) -> dict[str, int]:
        """Process grant lifecycle (activate pending, expire old grants).

        Returns:
            Dictionary with counts of processed grants
        """
        stats = {"activated": 0, "expired": 0, "errors": 0}

        try:
            # Activate pending grants
            pending_grants = await self.get_grants_needing_activation()
            for grant in pending_grants:
                try:
                    await self.activate_grant(grant)
                    stats["activated"] += 1
                except Exception as e:
                    await self.update_grant_error(grant, str(e))
                    stats["errors"] += 1
                    logger.error(
                        "Failed to activate grant",
                        grant_id=grant.grant_id,
                        error=str(e),
                    )

            # Expire old grants
            expired_grants = await self.get_grants_needing_expiry()
            for grant in expired_grants:
                try:
                    await self.expire_grant(grant)
                    stats["expired"] += 1
                except Exception as e:
                    await self.update_grant_error(grant, str(e))
                    stats["errors"] += 1
                    logger.error(
                        "Failed to expire grant", grant_id=grant.grant_id, error=str(e)
                    )

            if stats["activated"] > 0 or stats["expired"] > 0:
                logger.info("Grant lifecycle processing completed", **stats)

        except Exception as e:
            logger.error("Grant lifecycle processing failed", error=str(e))
            stats["errors"] += 1

        return stats

    async def get_grant_stats(self) -> dict[str, Any]:
        """Get grant statistics.

        Returns:
            Dictionary with grant statistics
        """
        all_grants = await self.list_grants(limit=10000)  # Get all grants

        stats: dict[str, Any] = {
            "total": len(all_grants),
            "pending": 0,
            "active": 0,
            "expired": 0,
            "revoked": 0,
            "by_source": {},
            "current_active": 0,
        }

        for grant in all_grants:
            stats[grant.status.value] = stats.get(grant.status.value, 0) + 1

            # Count by source
            source = grant.source.value
            if source not in stats["by_source"]:
                stats["by_source"][source] = 0
            stats["by_source"][source] = stats["by_source"][source] + 1

            # Count currently active (active status and within time window)
            if grant.is_currently_active():
                stats["current_active"] = stats["current_active"] + 1

        return stats

    async def get_stats(self) -> dict:
        """Get grant statistics (alias for get_grant_stats for API compatibility).

        Returns:
            Dictionary with grant statistics
        """
        return await self.get_grant_stats()


# Global grant manager instance
_grant_manager: GrantManager | None = None


def get_grant_manager() -> GrantManager:
    """Get the global grant manager instance."""
    global _grant_manager
    if _grant_manager is None:
        _grant_manager = GrantManager()
    return _grant_manager
