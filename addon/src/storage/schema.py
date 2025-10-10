# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Database schema and tables definition."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base: Any = declarative_base()


class GrantTable(Base):  # type: ignore[no-any-unimported]
    """Access grants table."""

    __tablename__ = "grants"

    grant_id = Column(String(36), primary_key=True)
    booking_id = Column(String(255), nullable=True, index=True)
    status = Column(String(20), nullable=False, index=True)
    source = Column(String(20), nullable=False, index=True)

    # Time columns
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    activated_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    modified_at = Column(DateTime(timezone=True), nullable=True)

    # Guest information
    guest_name = Column(String(255), nullable=False)
    device_mac = Column(String(17), nullable=True, index=True)  # MAC address format

    # Controller integration
    controller_voucher_id = Column(String(255), nullable=True)

    # Error tracking
    last_error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    # Termination info
    revocation_reason = Column(Text, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="valid_time_range"),
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'revoked')", name="valid_status"
        ),
        CheckConstraint(
            "source IN ('rental_control', 'voucher', 'manual')", name="valid_source"
        ),
        Index("idx_grants_status_time", "status", "start_time", "end_time"),
        Index("idx_grants_booking", "booking_id"),
    )


class VoucherTable(Base):  # type: ignore[no-any-unimported]
    """Vouchers table."""

    __tablename__ = "vouchers"

    voucher_id = Column(String(36), primary_key=True)
    code = Column(String(20), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, index=True)

    # Usage information
    duration_hours = Column(Integer, nullable=False)
    max_uses = Column(Integer, nullable=False, default=1)
    uses_count = Column(Integer, nullable=False, default=0)

    # Metadata
    description = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("duration_hours > 0", name="valid_duration"),
        CheckConstraint("max_uses >= -1", name="valid_max_uses"),
        CheckConstraint("uses_count >= 0", name="valid_uses_count"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'expired')", name="valid_voucher_status"
        ),
        Index("idx_vouchers_code", "code"),
        Index("idx_vouchers_status", "status"),
    )


class EventLogTable(Base):  # type: ignore[no-any-unimported]
    """Audit event log table."""

    __tablename__ = "event_log"

    event_id = Column(String(36), primary_key=True)
    event_type = Column(String(50), nullable=False, index=True)
    timestamp = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Context information
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(36), nullable=True, index=True)

    # Event details (JSON stored as text)
    details = Column(Text, nullable=False, default="{}")

    # User context
    user_id = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=True)

    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_events_type_time", "event_type", "timestamp"),
        Index("idx_events_entity", "entity_type", "entity_id"),
        Index("idx_events_timestamp", "timestamp"),
    )


class ThemeConfigTable(Base):  # type: ignore[no-any-unimported]
    """Theme configuration table."""

    __tablename__ = "theme_config"

    id = Column(Integer, primary_key=True)  # Single row table
    portal_title = Column(String(255), nullable=False, default="Guest Network Access")
    background_color = Column(String(7), nullable=False, default="#f5f5f5")
    primary_color = Column(String(7), nullable=False, default="#007bff")
    logo_url = Column(Text, nullable=True)
    custom_css = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_by = Column(String(255), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "LENGTH(background_color) = 7 AND background_color LIKE '#%'",
            name="valid_bg_color",
        ),
        CheckConstraint(
            "LENGTH(primary_color) = 7 AND primary_color LIKE '#%'",
            name="valid_primary_color",
        ),
    )
