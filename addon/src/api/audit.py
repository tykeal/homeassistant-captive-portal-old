# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Audit API router."""

from datetime import datetime

from fastapi import APIRouter, Query

from ..core.logging_config import get_logger
from ..models.domain import EventType
from ..services.audit_logger import get_audit_logger
from .models import PaginatedResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def get_audit_events(
    event_type: str | None = None,
    entity_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse:
    """Retrieve audit log events with optional filtering and pagination."""
    audit_logger = get_audit_logger()

    # Convert event_type string to EventType if provided
    event_type_filter = None
    if event_type:
        try:
            event_type_filter = EventType(event_type)
        except ValueError:
            # Invalid event type, ignore filter
            pass

    # Get all events (in a real implementation, this would be paginated at DB level)
    all_events = await audit_logger.get_events(
        event_type=event_type_filter,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination
    total = len(all_events)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_events = all_events[start_idx:end_idx]

    # Convert events to dict format
    events_dict = [event.model_dump(mode="json") for event in paginated_events]

    return PaginatedResponse(
        events=events_dict,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export_audit_events(
    event_type: str | None = None,
    entity_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    format: str = "json",
) -> dict:
    """Export audit events for reporting or compliance.

    Supports JSON and CSV formats (CSV implementation TODO).
    """
    audit_logger = get_audit_logger()

    # Convert event_type string to EventType if provided
    event_type_filter = None
    if event_type:
        try:
            event_type_filter = EventType(event_type)
        except ValueError:
            # Invalid event type, ignore filter
            pass

    events = await audit_logger.get_events(
        event_type=event_type_filter,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    if format == "json":
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "total": len(events),
            "exported_at": datetime.utcnow().isoformat(),
        }
    else:
        # CSV export TODO
        return {
            "error": "CSV export not yet implemented",
            "supported_formats": ["json"],
        }
