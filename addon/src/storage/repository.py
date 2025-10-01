# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Repository layer for data access."""

import json
from datetime import UTC, datetime

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import (
    AccessGrant,
    EventLogEntry,
    EventType,
    GrantStatus,
    ThemeConfig,
    Voucher,
    VoucherStatus,
)
from .schema import EventLogTable, GrantTable, ThemeConfigTable, VoucherTable


class GrantRepository:
    """Repository for access grants."""

    def __init__(self, session: AsyncSession):
        """Initialize the grant repository with a database session."""
        self.session = session

    async def create(self, grant: AccessGrant) -> AccessGrant:
        """Create a new grant."""
        grant_row = GrantTable(
            grant_id=grant.grant_id,
            booking_id=grant.booking_id,
            status=grant.status.value,
            source=grant.source.value,
            start_time=grant.start_time,
            end_time=grant.end_time,
            created_at=grant.created_at,
            activated_at=grant.activated_at,
            revoked_at=grant.revoked_at,
            modified_at=grant.modified_at,
            guest_name=grant.guest_name,
            device_mac=grant.device_mac,
            controller_voucher_id=grant.controller_voucher_id,
            last_error=grant.last_error,
            retry_count=grant.retry_count,
            revocation_reason=grant.revocation_reason,
        )

        self.session.add(grant_row)
        await self.session.flush()
        return grant

    async def get_by_id(self, grant_id: str) -> AccessGrant | None:
        """Get grant by ID."""
        result = await self.session.execute(
            select(GrantTable).where(GrantTable.grant_id == grant_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_domain(row) if row else None

    async def get_by_booking_id(self, booking_id: str) -> AccessGrant | None:
        """Get grant by booking ID."""
        result = await self.session.execute(
            select(GrantTable).where(GrantTable.booking_id == booking_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_domain(row) if row else None

    async def update(self, grant: AccessGrant) -> AccessGrant:
        """Update an existing grant."""
        await self.session.execute(
            update(GrantTable)
            .where(GrantTable.grant_id == grant.grant_id)
            .values(
                status=grant.status.value,
                start_time=grant.start_time,
                end_time=grant.end_time,
                activated_at=grant.activated_at,
                revoked_at=grant.revoked_at,
                modified_at=grant.modified_at,
                device_mac=grant.device_mac,
                controller_voucher_id=grant.controller_voucher_id,
                last_error=grant.last_error,
                retry_count=grant.retry_count,
                revocation_reason=grant.revocation_reason,
            )
        )
        return grant

    async def list_grants(
        self,
        status: GrantStatus | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AccessGrant]:
        """List grants with optional filtering."""
        query = select(GrantTable)

        if status:
            query = query.where(GrantTable.status == status.value)

        if source:
            query = query.where(GrantTable.source == source)

        query = query.order_by(desc(GrantTable.created_at)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        rows = result.scalars().all()
        return [self._row_to_domain(row) for row in rows]

    async def get_grants_needing_activation(self) -> list[AccessGrant]:
        """Get grants that should be activated (past start time, still pending)."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(GrantTable).where(
                and_(
                    GrantTable.status == GrantStatus.PENDING.value,
                    GrantTable.start_time <= now,
                )
            )
        )
        rows = result.scalars().all()
        return [self._row_to_domain(row) for row in rows]

    async def get_grants_needing_expiry(self) -> list[AccessGrant]:
        """Get grants that should be expired (past end time)."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(GrantTable).where(
                and_(
                    GrantTable.status.in_(
                        [GrantStatus.PENDING.value, GrantStatus.ACTIVE.value]
                    ),
                    GrantTable.end_time < now,
                )
            )
        )
        rows = result.scalars().all()
        return [self._row_to_domain(row) for row in rows]

    def _row_to_domain(self, row: GrantTable) -> AccessGrant:
        """Convert database row to domain model."""
        return AccessGrant(
            grant_id=row.grant_id,
            booking_id=row.booking_id,
            status=GrantStatus(row.status),
            source=row.source,
            start_time=row.start_time,
            end_time=row.end_time,
            created_at=row.created_at,
            activated_at=row.activated_at,
            revoked_at=row.revoked_at,
            modified_at=row.modified_at,
            guest_name=row.guest_name,
            device_mac=row.device_mac,
            controller_voucher_id=row.controller_voucher_id,
            last_error=row.last_error,
            retry_count=row.retry_count,
            revocation_reason=row.revocation_reason,
        )


class VoucherRepository:
    """Repository for vouchers."""

    def __init__(self, session: AsyncSession):
        """Initialize the voucher repository with a database session."""
        self.session = session

    async def create(self, voucher: Voucher) -> Voucher:
        """Create a new voucher."""
        voucher_row = VoucherTable(
            voucher_id=voucher.voucher_id,
            code=voucher.code,
            status=voucher.status.value,
            duration_hours=voucher.duration_hours,
            max_uses=voucher.max_uses,
            uses_count=voucher.uses_count,
            description=voucher.description,
            created_by=voucher.created_by,
            created_at=voucher.created_at,
            expires_at=voucher.expires_at,
        )

        self.session.add(voucher_row)
        await self.session.flush()
        return voucher

    async def get_by_id(self, voucher_id: str) -> Voucher | None:
        """Get voucher by ID."""
        result = await self.session.execute(
            select(VoucherTable).where(VoucherTable.voucher_id == voucher_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_domain(row) if row else None

    async def get_by_code(self, code: str) -> Voucher | None:
        """Get voucher by code."""
        result = await self.session.execute(
            select(VoucherTable).where(VoucherTable.code == code.upper())
        )
        row = result.scalar_one_or_none()
        return self._row_to_domain(row) if row else None

    async def update(self, voucher: Voucher) -> Voucher:
        """Update an existing voucher."""
        await self.session.execute(
            update(VoucherTable)
            .where(VoucherTable.voucher_id == voucher.voucher_id)
            .values(
                status=voucher.status.value,
                uses_count=voucher.uses_count,
                expires_at=voucher.expires_at,
            )
        )
        return voucher

    async def list_vouchers(
        self, status: VoucherStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[Voucher]:
        """List vouchers with optional filtering."""
        query = select(VoucherTable)

        if status:
            query = query.where(VoucherTable.status == status.value)

        query = (
            query.order_by(desc(VoucherTable.created_at)).limit(limit).offset(offset)
        )

        result = await self.session.execute(query)
        rows = result.scalars().all()
        return [self._row_to_domain(row) for row in rows]

    def _row_to_domain(self, row: VoucherTable) -> Voucher:
        """Convert database row to domain model."""
        return Voucher(
            voucher_id=row.voucher_id,
            code=row.code,
            status=VoucherStatus(row.status),
            duration_hours=row.duration_hours,
            max_uses=row.max_uses,
            uses_count=row.uses_count,
            description=row.description,
            created_by=row.created_by,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )


class EventRepository:
    """Repository for audit events."""

    def __init__(self, session: AsyncSession):
        """Initialize the event repository with a database session."""
        self.session = session

    async def create(self, event: EventLogEntry) -> EventLogEntry:
        """Create a new event log entry."""
        event_row = EventLogTable(
            event_id=event.event_id,
            event_type=event.event_type.value,
            timestamp=event.timestamp,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            details=json.dumps(event.details),
            user_id=event.user_id,
            session_id=event.session_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
        )

        self.session.add(event_row)
        await self.session.flush()
        return event

    async def list_events(
        self,
        event_type: EventType | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventLogEntry]:
        """List events with filtering."""
        query = select(EventLogTable)

        if event_type:
            query = query.where(EventLogTable.event_type == event_type.value)

        if entity_type:
            query = query.where(EventLogTable.entity_type == entity_type)

        if entity_id:
            query = query.where(EventLogTable.entity_id == entity_id)

        if start_date:
            query = query.where(EventLogTable.timestamp >= start_date)

        if end_date:
            query = query.where(EventLogTable.timestamp <= end_date)

        query = (
            query.order_by(desc(EventLogTable.timestamp)).limit(limit).offset(offset)
        )

        result = await self.session.execute(query)
        rows = result.scalars().all()
        return [self._row_to_domain(row) for row in rows]

    async def count_events(
        self,
        event_type: EventType | None = None,
        entity_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        """Count events with filtering."""
        from sqlalchemy import func

        query = select(func.count(EventLogTable.event_id))

        if event_type:
            query = query.where(EventLogTable.event_type == event_type.value)

        if entity_type:
            query = query.where(EventLogTable.entity_type == entity_type)

        if start_date:
            query = query.where(EventLogTable.timestamp >= start_date)

        if end_date:
            query = query.where(EventLogTable.timestamp <= end_date)

        result = await self.session.execute(query)
        return result.scalar() or 0

    def _row_to_domain(self, row: EventLogTable) -> EventLogEntry:
        """Convert database row to domain model."""
        details = json.loads(row.details) if row.details else {}

        return EventLogEntry(
            event_id=row.event_id,
            event_type=EventType(row.event_type),
            timestamp=row.timestamp,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            details=details,
            user_id=row.user_id,
            session_id=row.session_id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
        )


class ThemeRepository:
    """Repository for theme configuration."""

    def __init__(self, session: AsyncSession):
        """Initialize the theme repository with a database session."""
        self.session = session

    async def get_current_theme(self) -> ThemeConfig:
        """Get current theme configuration."""
        result = await self.session.execute(
            select(ThemeConfigTable).where(ThemeConfigTable.id == 1)
        )
        row = result.scalar_one_or_none()

        if row:
            return self._row_to_domain(row)
        else:
            # Return default theme if none exists
            return ThemeConfig()

    async def update_theme(self, theme: ThemeConfig) -> ThemeConfig:
        """Update theme configuration."""
        # Check if theme exists
        result = await self.session.execute(
            select(ThemeConfigTable).where(ThemeConfigTable.id == 1)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            await self.session.execute(
                update(ThemeConfigTable)
                .where(ThemeConfigTable.id == 1)
                .values(
                    portal_title=theme.portal_title,
                    background_color=theme.background_color,
                    primary_color=theme.primary_color,
                    logo_url=theme.logo_url,
                    custom_css=theme.custom_css,
                    updated_at=theme.updated_at,
                    updated_by=theme.updated_by,
                )
            )
        else:
            # Create new
            theme_row = ThemeConfigTable(
                id=1,
                portal_title=theme.portal_title,
                background_color=theme.background_color,
                primary_color=theme.primary_color,
                logo_url=theme.logo_url,
                custom_css=theme.custom_css,
                updated_at=theme.updated_at,
                updated_by=theme.updated_by,
            )
            self.session.add(theme_row)

        await self.session.flush()
        return theme

    def _row_to_domain(self, row: ThemeConfigTable) -> ThemeConfig:
        """Convert database row to domain model."""
        return ThemeConfig(
            portal_title=row.portal_title,
            background_color=row.background_color,
            primary_color=row.primary_color,
            logo_url=row.logo_url,
            custom_css=row.custom_css,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
