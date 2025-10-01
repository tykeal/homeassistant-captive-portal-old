# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Grant manager for lifecycle management (pending→active, extend, shorten, revoke)."""

from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import AccessGrant, GrantSource, GrantStatus
from ..services.audit_logger import get_audit_logger
from ..storage.database import get_db_session
from ..storage.repository import GrantRepository

logger = get_logger(__name__)


class GrantManager:
    """Service for access grant lifecycle management."""

    def __init__(self):
        """Initialize grant manager."""
        self.audit_logger = get_audit_logger()

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

        # Determine initial status
        now = datetime.now(UTC)
        if now >= start_time:
            # Should be active immediately
            grant.status = GrantStatus.ACTIVE
            grant.activated_at = now
        else:
            # Pending until start time
            grant.status = GrantStatus.PENDING

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.create(grant)

        # Log creation
        await self.audit_logger.log_grant_created(
            grant=grant, user_id=user_id, **audit_context
        )

        # Log activation if immediate
        if grant.status == GrantStatus.ACTIVE:
            await self.audit_logger.log_grant_activated(grant=grant, **audit_context)

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
        """Activate a pending grant.

        Args:
            grant: Grant to activate
            controller_voucher_id: Controller voucher ID if provisioned
            **audit_context: Additional audit context

        Returns:
            Updated grant

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

        # Update grant
        grant.status = GrantStatus.ACTIVE
        grant.activated_at = now
        grant.controller_voucher_id = controller_voucher_id
        grant.modified_at = now

        # Clear any previous errors
        grant.last_error = None
        grant.retry_count = 0

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.update(grant)

        # Log activation
        await self.audit_logger.log_grant_activated(
            grant=grant, controller_voucher_id=controller_voucher_id, **audit_context
        )

        logger.info(
            "Grant activated",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            guest_name=grant.guest_name,
            controller_voucher_id=controller_voucher_id,
            activated_at=grant.activated_at.isoformat(),
        )

        return grant

    async def extend_grant(
        self,
        grant: AccessGrant,
        new_end_time: datetime,
        reason: str,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Extend a grant to a new end time.

        Args:
            grant: Grant to extend
            new_end_time: New end time
            reason: Reason for extension
            user_id: User extending the grant
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be extended
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot extend grant with status: {grant.status}")

        if new_end_time <= grant.end_time:
            raise ValueError("New end time must be after current end time")

        # Store old end time for audit
        old_end_time = grant.end_time

        # Update grant
        grant.extend_grant(new_end_time, reason)

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.update(grant)

        # Log extension
        await self.audit_logger.log_grant_extended(
            grant=grant,
            old_end_time=old_end_time,
            reason=reason,
            user_id=user_id,
            **audit_context,
        )

        logger.info(
            "Grant extended",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            guest_name=grant.guest_name,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat(),
            reason=reason,
            extended_by=user_id,
        )

        return grant

    async def shorten_grant(
        self,
        grant: AccessGrant,
        new_end_time: datetime | None,
        reason: str,
        immediate: bool = False,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Shorten a grant or terminate immediately.

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
            ValueError: If grant cannot be shortened
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot shorten grant with status: {grant.status}")

        if not immediate and not new_end_time:
            raise ValueError("Must provide new_end_time or set immediate=True")

        if new_end_time and new_end_time >= grant.end_time:
            raise ValueError("New end time must be before current end time")

        # Store old end time for audit
        old_end_time = grant.end_time

        # Update grant
        grant.shorten_grant(new_end_time, reason, immediate)

        # Save to database
        async with get_db_session() as session:
            repository = GrantRepository(session)
            await repository.update(grant)

        # Log shortening
        await self.audit_logger.log_grant_shortened(
            grant=grant,
            old_end_time=old_end_time,
            reason=reason,
            immediate=immediate,
            user_id=user_id,
            **audit_context,
        )

        # If immediate, also log revocation
        if immediate:
            await self.audit_logger.log_grant_revoked(
                grant=grant, reason=reason, user_id=user_id, **audit_context
            )

        logger.info(
            "Grant shortened",
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            guest_name=grant.guest_name,
            old_end_time=old_end_time.isoformat(),
            new_end_time=new_end_time.isoformat() if new_end_time else None,
            immediate=immediate,
            reason=reason,
            shortened_by=user_id,
        )

        return grant

    async def revoke_grant(
        self,
        grant: AccessGrant,
        reason: str,
        user_id: str | None = None,
        **audit_context,
    ) -> AccessGrant:
        """Revoke a grant immediately.

        Args:
            grant: Grant to revoke
            reason: Reason for revocation
            user_id: User revoking the grant
            **audit_context: Additional audit context

        Returns:
            Updated grant

        Raises:
            ValueError: If grant cannot be revoked
        """
        if grant.status not in [GrantStatus.PENDING, GrantStatus.ACTIVE]:
            raise ValueError(f"Cannot revoke grant with status: {grant.status}")

        # Update grant
        grant.status = GrantStatus.REVOKED
        grant.revoked_at = datetime.now(UTC)
        grant.revocation_reason = reason
        grant.modified_at = grant.revoked_at

        # Save to database
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
            await repository.update(grant)

        # Log expiration
        await self.audit_logger.log_grant_expired(grant=grant, **audit_context)

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


# Global grant manager instance
_grant_manager: GrantManager | None = None


def get_grant_manager() -> GrantManager:
    """Get the global grant manager instance."""
    global _grant_manager
    if _grant_manager is None:
        _grant_manager = GrantManager()
    return _grant_manager
