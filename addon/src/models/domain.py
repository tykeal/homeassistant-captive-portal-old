# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Domain models for the captive portal addon."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class GrantStatus(str, Enum):
    """Grant lifecycle status."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class GrantSource(str, Enum):
    """Source of grant creation."""

    RENTAL_CONTROL = "rental_control"
    VOUCHER = "voucher"
    MANUAL = "manual"


class VoucherStatus(str, Enum):
    """Voucher status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class EventType(str, Enum):
    """Audit event types."""

    GRANT_CREATED = "grant_created"
    GRANT_ACTIVATED = "grant_activated"
    GRANT_EXTENDED = "grant_extended"
    GRANT_SHORTENED = "grant_shortened"
    GRANT_REVOKED = "grant_revoked"
    GRANT_EXPIRED = "grant_expired"
    VOUCHER_CREATED = "voucher_created"
    VOUCHER_USED = "voucher_used"
    VOUCHER_DEACTIVATED = "voucher_deactivated"
    PORTAL_ACCESS = "portal_access"
    PORTAL_RATE_LIMIT = "portal_rate_limit"
    THEME_UPDATED = "theme_updated"
    CONFIG_CHANGED = "config_changed"
    CONTROLLER_ERROR = "controller_error"


class AccessGrant(BaseModel):
    """Access grant domain model."""

    grant_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str | None = Field(None, description="Rental Control booking ID")
    status: GrantStatus = GrantStatus.PENDING
    source: GrantSource = GrantSource.RENTAL_CONTROL

    # Time information
    start_time: datetime = Field(..., description="Grant start time")
    end_time: datetime = Field(..., description="Grant end time")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    revoked_at: datetime | None = None
    modified_at: datetime | None = None

    # Guest information
    guest_name: str = Field(..., description="Guest name")
    device_mac: str | None = Field(None, description="Device MAC address")

    # Controller integration
    controller_voucher_id: str | None = Field(None, description="Controller voucher ID")

    # Error tracking
    last_error: str | None = None
    retry_count: int = 0

    # Termination info
    revocation_reason: str | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware."""
        if v.tzinfo is None:
            # Assume UTC if no timezone provided
            return v.replace(tzinfo=UTC)
        return v

    @field_validator("end_time")
    @classmethod
    def validate_end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        """Validate end_time is after start_time."""
        if hasattr(info.data, "start_time") and info.data.get("start_time"):
            start_time = info.data["start_time"]
            if v <= start_time:
                raise ValueError("end_time must be after start_time")
        return v

    def is_currently_active(self) -> bool:
        """Check if grant should be active right now."""
        now = datetime.now(UTC)
        return (
            self.status == GrantStatus.ACTIVE
            and self.start_time <= now <= self.end_time
        )

    def should_be_activated(self) -> bool:
        """Check if grant should be activated (past start time)."""
        now = datetime.now(UTC)
        return self.status == GrantStatus.PENDING and now >= self.start_time

    def should_be_expired(self) -> bool:
        """Check if grant should be expired (past end time)."""
        now = datetime.now(UTC)
        return (
            self.status in [GrantStatus.PENDING, GrantStatus.ACTIVE]
            and now > self.end_time
        )

    def extend_grant(self, new_end_time: datetime, reason: str) -> None:
        """Extend the grant to a new end time."""
        if new_end_time <= self.end_time:
            raise ValueError("New end time must be after current end time")

        self.end_time = new_end_time
        self.modified_at = datetime.now(UTC)

    def shorten_grant(
        self, new_end_time: datetime | None, reason: str, immediate: bool = False
    ) -> None:
        """Shorten the grant or terminate immediately."""
        if immediate:
            self.status = GrantStatus.REVOKED
            self.revoked_at = datetime.now(UTC)
        elif new_end_time:
            if new_end_time >= self.end_time:
                raise ValueError("New end time must be before current end time")
            self.end_time = new_end_time

        self.revocation_reason = reason
        self.modified_at = datetime.now(UTC)


class Voucher(BaseModel):
    """Voucher domain model."""

    voucher_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str = Field(..., description="Voucher code for guest use")
    status: VoucherStatus = VoucherStatus.ACTIVE

    # Usage information
    duration_hours: int = Field(..., gt=0, description="Grant duration in hours")
    max_uses: int = Field(1, description="Maximum number of uses (-1 for unlimited)")
    uses_count: int = 0

    # Metadata
    description: str = Field(..., description="Voucher description")
    created_by: str = Field(..., description="Creator identifier")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        """Validate voucher code format."""
        if len(v) < 6:
            raise ValueError("Voucher code must be at least 6 characters")
        if not v.isalnum():
            raise ValueError("Voucher code must be alphanumeric")
        return v.upper()

    def is_valid(self) -> bool:
        """Check if voucher is valid for use."""
        now = datetime.now(UTC)

        # Check status
        if self.status != VoucherStatus.ACTIVE:
            return False

        # Check expiry
        if self.expires_at and now > self.expires_at:
            return False

        # Check usage limits
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False

        return True

    def use_voucher(self) -> None:
        """Mark voucher as used (increment use count)."""
        if not self.is_valid():
            raise ValueError("Voucher is not valid for use")

        self.uses_count += 1

        # Check if this was the last use
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            self.status = VoucherStatus.INACTIVE

    def deactivate(self) -> None:
        """Deactivate the voucher."""
        self.status = VoucherStatus.INACTIVE


class EventLogEntry(BaseModel):
    """Audit log entry domain model."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = Field(..., description="Type of event")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Context information
    entity_type: str | None = Field(
        None, description="Type of entity (grant, voucher, etc.)"
    )
    entity_id: str | None = Field(None, description="ID of related entity")

    # Event details
    details: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific details"
    )

    # User context
    user_id: str | None = Field(None, description="User or system identifier")
    session_id: str | None = Field(None, description="Session identifier")

    # Request context
    ip_address: str | None = Field(None, description="Source IP address")
    user_agent: str | None = Field(None, description="User agent string")

    def add_detail(self, key: str, value: Any) -> None:
        """Add a detail to the event."""
        self.details[key] = value

    @classmethod
    def create_grant_event(
        cls,
        event_type: EventType,
        grant: AccessGrant,
        details: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> "EventLogEntry":
        """Create an event log entry for a grant."""
        event_details = {
            "grant_id": grant.grant_id,
            "booking_id": grant.booking_id,
            "status": grant.status.value,
            "source": grant.source.value,
            "guest_name": grant.guest_name,
        }

        if details:
            event_details.update(details)

        return cls(
            event_type=event_type,
            entity_type="grant",
            entity_id=grant.grant_id,
            details=event_details,
            user_id=user_id,
        )

    @classmethod
    def create_voucher_event(
        cls,
        event_type: EventType,
        voucher: Voucher,
        details: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> "EventLogEntry":
        """Create an event log entry for a voucher."""
        event_details = {
            "voucher_id": voucher.voucher_id,
            "code": voucher.code,
            "status": voucher.status.value,
            "uses_count": voucher.uses_count,
            "max_uses": voucher.max_uses,
        }

        if details:
            event_details.update(details)

        return cls(
            event_type=event_type,
            entity_type="voucher",
            entity_id=voucher.voucher_id,
            details=event_details,
            user_id=user_id,
        )


class ThemeConfig(BaseModel):
    """Theme configuration domain model."""

    portal_title: str = Field("Guest Network Access", description="Portal page title")
    background_color: str = Field("#f5f5f5", description="Background color (hex)")
    primary_color: str = Field("#007bff", description="Primary color (hex)")
    logo_url: str | None = Field(None, description="Logo URL")
    custom_css: str | None = Field(None, description="Custom CSS styles")

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by: str | None = Field(None, description="Who updated the theme")

    @field_validator("background_color", "primary_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Validate hex color format."""
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be in hex format (#rrggbb)")
        try:
            int(v[1:], 16)
        except ValueError as e:
            raise ValueError("Invalid hex color") from e
        return v

    @field_validator("logo_url")
    @classmethod
    def validate_logo_url(cls, v: str | None) -> str | None:
        """Validate logo URL."""
        if v is None:
            return v

        # Basic URL validation and security check
        if not v.startswith(("http://", "https://")):
            raise ValueError("Logo URL must use http or https protocol")

        # Prevent JavaScript injection
        if "javascript:" in v.lower():
            raise ValueError("JavaScript URLs are not allowed")

        return v

    @field_validator("custom_css")
    @classmethod
    def validate_custom_css(cls, v: str | None) -> str | None:
        """Validate custom CSS for security."""
        if v is None:
            return v

        # Basic security checks
        dangerous_patterns = [
            "javascript:",
            "@import",
            "expression(",
            "behavior:",
            "binding:",
        ]

        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if pattern in v_lower:
                raise ValueError(f"CSS contains dangerous pattern: {pattern}")

        return v

    def to_css_variables(self) -> str:
        """Convert theme to CSS custom properties."""
        return f"""
        :root {{
            --portal-bg-color: {self.background_color};
            --portal-primary-color: {self.primary_color};
            --portal-title: "{self.portal_title}";
        }}
        """
