# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""API request and response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class GrantCreateRequest(BaseModel):
    """Request model for creating a grant."""

    booking_id: str | None = None
    start_time: datetime
    end_time: datetime
    guest_name: str
    source: str = "rental_control"
    device_mac: str | None = None


class GrantExtendRequest(BaseModel):
    """Request model for extending a grant."""

    new_end_time: datetime
    reason: str | None = None


class GrantShortenRequest(BaseModel):
    """Request model for shortening/terminating a grant."""

    new_end_time: datetime | None = None
    reason: str
    immediate: bool = True


class VoucherCreateRequest(BaseModel):
    """Request model for creating a voucher."""

    duration_hours: int = Field(gt=0, description="Voucher duration in hours")
    description: str
    created_by: str
    max_uses: int = Field(default=1, ge=-1, description="-1 for unlimited uses")


class ThemeUpdateRequest(BaseModel):
    """Request model for updating theme configuration."""

    portal_title: str | None = None
    background_color: str | None = None
    primary_color: str | None = None
    logo_url: str | None = None
    custom_css: str | None = None


class AuditQueryParams(BaseModel):
    """Query parameters for audit log filtering."""

    event_type: str | None = None
    entity_id: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    events: list[dict]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "1.0.0"
    queue_depth: int | None = None
    controller_status: str | None = None
    details: dict | None = None
