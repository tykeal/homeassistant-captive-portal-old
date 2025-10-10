# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Audit logging service for append-only event tracking."""

from datetime import datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import AccessGrant, EventLogEntry, EventType, Voucher
from ..storage.database import get_db_session
from ..storage.repository import EventRepository

logger = get_logger(__name__)


class AuditLogger:
    """Service for audit logging with append-only guarantees."""

    def __init__(self) -> None:
        """Initialize audit logger."""
        pass

    def _extract_log_params(
        self, context: dict[str, Any]
    ) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
        """Extract log_event parameters from context and return remaining details.

        Args:
            context: Context dictionary that may contain session_id, ip_address,
                    user_agent, and other fields

        Returns:
            Tuple of (session_id, ip_address, user_agent, extra_details)
        """
        session_id = context.get("session_id")
        ip_address = context.get("ip_address")
        user_agent = context.get("user_agent")

        # Build extra details from remaining context fields
        extra_details = {}
        for key, value in context.items():
            if key not in ("session_id", "ip_address", "user_agent"):
                # Serialize datetime objects
                if isinstance(value, datetime):
                    extra_details[key] = value.isoformat()
                else:
                    extra_details[key] = value

        return session_id, ip_address, user_agent, extra_details

    async def log_event(
        self,
        event_type: EventType,
        details: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EventLogEntry:
        """Log a general audit event.

        Args:
            event_type: Type of event
            details: Event-specific details
            entity_type: Type of entity (grant, voucher, etc.)
            entity_id: ID of related entity
            user_id: User or system identifier
            session_id: Session identifier
            ip_address: Source IP address
            user_agent: User agent string

        Returns:
            Created event log entry
        """
        event = EventLogEntry(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        async with get_db_session() as session:
            repository = EventRepository(session)
            await repository.create(event)

        # Also log to structured logger for real-time monitoring
        logger.info(
            "Audit event recorded",
            event_type=event_type.value,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            **details or {},
        )

        return event

    async def log_grant_created(
        self, grant: AccessGrant, user_id: str | None = None, **context: Any
    ) -> EventLogEntry:
        """Log grant creation event.

        Args:
            grant: Created grant
            user_id: User who created the grant
            **context: Additional context (session_id, ip_address, etc.)

        Returns:
            Created event log entry
        """
        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "source": grant.source.value,
            "guest_name": grant.guest_name,
            "start_time": grant.start_time.isoformat(),
            "end_time": grant.end_time.isoformat(),
            "status": grant.status.value,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.GRANT_CREATED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_grant_activated(
        self,
        grant: AccessGrant,
        controller_voucher_id: str | None = None,
        **context: Any,
    ) -> EventLogEntry:
        """Log grant activation event.

        Args:
            grant: Activated grant
            controller_voucher_id: Controller voucher ID if provisioned
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "guest_name": grant.guest_name,
            "activated_at": grant.activated_at.isoformat()
            if grant.activated_at
            else None,
            "controller_voucher_id": controller_voucher_id,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.GRANT_ACTIVATED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_grant_extended(
        self,
        grant: AccessGrant,
        old_end_time: datetime,
        new_end_time: datetime,
        reason: str,
        user_id: str | None = None,
        **context: Any,
    ) -> EventLogEntry:
        """Log grant extension event.

        Args:
            grant: Extended grant
            old_end_time: Previous end time
            new_end_time: New end time
            reason: Reason for extension
            user_id: User who extended the grant
            **context: Additional context

        Returns:
            Created event log entry
        """
        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "old_end_time": old_end_time.isoformat(),
            "new_end_time": grant.end_time.isoformat(),
            "reason": reason,
            "guest_name": grant.guest_name,
            **extra_details,
        }

        return await self.log_event(
            event_type=EventType.GRANT_EXTENDED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_grant_shortened(
        self,
        grant: AccessGrant,
        old_end_time: datetime,
        reason: str,
        immediate: bool = False,
        user_id: str | None = None,
        **context: Any,
    ) -> EventLogEntry:
        """Log grant shortening event.

        Args:
            grant: Shortened grant
            old_end_time: Previous end time
            reason: Reason for shortening
            immediate: Whether it was immediate termination
            user_id: User who shortened the grant
            **context: Additional context

        Returns:
            Created event log entry
        """
        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "old_end_time": old_end_time.isoformat(),
            "new_end_time": grant.end_time.isoformat() if not immediate else None,
            "reason": reason,
            "immediate": immediate,
            "guest_name": grant.guest_name,
            **extra_details,
        }

        return await self.log_event(
            event_type=EventType.GRANT_SHORTENED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_grant_revoked(
        self,
        grant: AccessGrant,
        reason: str,
        user_id: str | None = None,
        **context: Any,
    ) -> EventLogEntry:
        """Log grant revocation event.

        Args:
            grant: Revoked grant
            reason: Reason for revocation
            user_id: User who revoked the grant
            **context: Additional context (immediate, controller_revoked, etc.)

        Returns:
            Created event log entry
        """
        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "reason": reason,
            "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
            "guest_name": grant.guest_name,
            "was_active": grant.status.value,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        # Include immediate and controller_revoked flags if provided (T091)
        if "immediate" in extra_details:
            details["immediate"] = extra_details.pop("immediate")
        if "controller_revoked" in extra_details:
            details["controller_revoked"] = extra_details.pop("controller_revoked")

        return await self.log_event(
            event_type=EventType.GRANT_REVOKED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_grant_expired(
        self, grant: AccessGrant, **context: Any
    ) -> EventLogEntry:
        """Log grant expiration event.

        Args:
            grant: Expired grant
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "end_time": grant.end_time.isoformat(),
            "guest_name": grant.guest_name,
            "was_active": grant.status.value,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.GRANT_EXPIRED,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=details,
            user_id="system",
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_voucher_created(
        self, voucher: Voucher, user_id: str | None = None, **context: Any
    ) -> EventLogEntry:
        """Log voucher creation event.

        Args:
            voucher: Created voucher
            user_id: User who created the voucher
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {
            "voucher_id": voucher.voucher_id,
            "code": voucher.code,
            "duration_hours": voucher.duration_hours,
            "max_uses": voucher.max_uses,
            "description": voucher.description,
            "created_by": voucher.created_by,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.VOUCHER_CREATED,
            entity_type="voucher",
            entity_id=voucher.voucher_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_voucher_used(
        self, voucher: Voucher, grant: AccessGrant, **context: Any
    ) -> EventLogEntry:
        """Log voucher usage event.

        Args:
            voucher: Used voucher
            grant: Grant created from voucher
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {
            "voucher_id": voucher.voucher_id,
            "code": voucher.code,
            "grant_id": grant.grant_id,
            "guest_name": grant.guest_name,
            "device_mac": grant.device_mac,
            "uses_count": voucher.uses_count,
            "max_uses": voucher.max_uses,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.VOUCHER_USED,
            entity_type="voucher",
            entity_id=voucher.voucher_id,
            details=details,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_voucher_deactivated(
        self, voucher: Voucher, reason: str, user_id: str | None = None, **context: Any
    ) -> EventLogEntry:
        """Log voucher deactivation event.

        Args:
            voucher: Deactivated voucher
            reason: Reason for deactivation
            user_id: User who deactivated the voucher
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {
            "voucher_id": voucher.voucher_id,
            "code": voucher.code,
            "reason": reason,
            "uses_count": voucher.uses_count,
            "max_uses": voucher.max_uses,
        }

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.VOUCHER_DEACTIVATED,
            entity_type="voucher",
            entity_id=voucher.voucher_id,
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_portal_access(
        self, result: str, details: dict[str, Any] | None = None, **context: Any
    ) -> EventLogEntry:
        """Log portal access attempt.

        Args:
            result: Access result (success, failure, etc.)
            details: Access details
            **context: Additional context (should include ip_address, user_agent)

        Returns:
            Created event log entry
        """
        access_details = {"result": result, **(details or {})}

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.PORTAL_ACCESS,
            entity_type="portal",
            details=access_details,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_theme_updated(
        self,
        old_theme: dict[str, Any] | None = None,
        new_theme: dict[str, Any] | None = None,
        user_id: str | None = None,
        **context: Any,
    ) -> EventLogEntry:
        """Log theme update event.

        Args:
            old_theme: Previous theme configuration
            new_theme: New theme configuration
            user_id: User who updated the theme
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {"old_theme": old_theme, "new_theme": new_theme}

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.THEME_UPDATED,
            entity_type="theme",
            details=details,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_controller_error(
        self, operation: str, error: str, grant_id: str | None = None, **context: Any
    ) -> EventLogEntry:
        """Log controller communication error.

        Args:
            operation: Operation that failed (provision, revoke, etc.)
            error: Error message
            grant_id: Related grant ID if applicable
            **context: Additional context

        Returns:
            Created event log entry
        """
        details = {"operation": operation, "error": error, "grant_id": grant_id}

        session_id, ip_address, user_agent, extra_details = self._extract_log_params(
            context
        )

        return await self.log_event(
            event_type=EventType.CONTROLLER_ERROR,
            entity_type="controller",
            entity_id=grant_id,
            details=details,
            user_id="system",
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_events(
        self,
        event_type: EventType | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventLogEntry]:
        """Get audit events with filtering.

        Args:
            event_type: Filter by event type
            entity_type: Filter by entity type
            entity_id: Filter by entity ID
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of event log entries
        """
        async with get_db_session() as session:
            repository = EventRepository(session)
            return await repository.list_events(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )

    async def count_events(
        self,
        event_type: EventType | None = None,
        entity_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        """Count audit events with filtering.

        Args:
            event_type: Filter by event type
            entity_type: Filter by entity type
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Number of matching events
        """
        async with get_db_session() as session:
            repository = EventRepository(session)
            return await repository.count_events(
                event_type=event_type,
                entity_type=entity_type,
                start_date=start_date,
                end_date=end_date,
            )


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
