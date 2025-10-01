# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Grants API router."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from ..core.logging_config import get_logger
from ..models.domain import GrantSource, GrantStatus
from ..services.grant_manager import get_grant_manager
from .models import GrantCreateRequest, GrantExtendRequest, GrantShortenRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/grants", tags=["grants"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_grant(request: GrantCreateRequest) -> dict:
    """Create a new access grant.

    Creates a grant that will provision network access for a guest.
    If start_time is now or in the past, the grant activates immediately.
    Otherwise, it remains in pending state until start_time.
    """
    grant_manager = get_grant_manager()

    # Check for duplicate booking_id
    if request.booking_id:
        existing_grants = await grant_manager.list_grants(limit=10000)
        for existing_grant in existing_grants:
            if existing_grant.booking_id == request.booking_id:
                logger.warning(
                    "Attempted to create duplicate grant",
                    booking_id=request.booking_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Grant with booking_id {request.booking_id} already exists",
                )

    # Create the grant
    grant = await grant_manager.create_grant(
        booking_id=request.booking_id,
        guest_name=request.guest_name,
        start_time=request.start_time,
        end_time=request.end_time,
        source=GrantSource(request.source),
        device_mac=request.device_mac,
    )

    # Check if grant should activate immediately
    now = datetime.now(UTC)
    if grant.start_time <= now and grant.end_time > now:
        try:
            # Activate immediately
            grant = await grant_manager.activate_grant(grant)
            logger.info(
                "Grant activated immediately",
                grant_id=grant.grant_id,
                booking_id=grant.booking_id,
            )
        except Exception as e:
            logger.error(
                "Failed to activate grant immediately",
                grant_id=grant.grant_id,
                error=str(e),
            )
            # Grant remains in pending state

    return grant.model_dump(mode="json")


@router.patch("/{grant_id}/extend")
async def extend_grant(grant_id: str, request: GrantExtendRequest) -> dict:
    """Extend the expiration time of an existing grant."""
    grant_manager = get_grant_manager()

    # Validate new_end_time is in the future
    now = datetime.now(UTC)
    if request.new_end_time <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="new_end_time must be in the future",
        )

    try:
        # First get the grant
        grant = await grant_manager.get_grant_by_id(grant_id)
        if not grant:
            raise ValueError(f"Grant {grant_id} not found")

        updated_grant = await grant_manager.extend_grant(
            grant=grant,
            new_end_time=request.new_end_time,
            reason=request.reason or "Extension requested",
        )

        logger.info(
            "Grant extended",
            grant_id=grant_id,
            new_end_time=request.new_end_time.isoformat(),
        )

        return updated_grant.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to extend grant",
            grant_id=grant_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.patch("/{grant_id}/shorten")
async def shorten_grant(grant_id: str, request: GrantShortenRequest) -> dict:
    """Shorten or immediately terminate an existing grant."""
    grant_manager = get_grant_manager()

    try:
        # First get the grant
        grant = await grant_manager.get_grant_by_id(grant_id)
        if not grant:
            raise ValueError(f"Grant {grant_id} not found")

        if request.immediate:
            # Immediate termination (revoke)
            updated_grant = await grant_manager.revoke_grant(
                grant=grant,
                reason=request.reason,
            )
            logger.info(
                "Grant terminated immediately",
                grant_id=grant_id,
                reason=request.reason,
            )
        else:
            # Scheduled shortening
            if not request.new_end_time:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="new_end_time required for scheduled shortening",
                )

            updated_grant = await grant_manager.shorten_grant(
                grant=grant,
                new_end_time=request.new_end_time,
                reason=request.reason,
            )
            logger.info(
                "Grant shortened",
                grant_id=grant_id,
                new_end_time=request.new_end_time.isoformat(),
            )

        return updated_grant.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to shorten/terminate grant",
            grant_id=grant_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/{grant_id}")
async def get_grant(grant_id: str) -> dict:
    """Get details of a specific grant."""
    grant_manager = get_grant_manager()

    grant = await grant_manager.get_grant_by_id(grant_id)
    if not grant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grant {grant_id} not found",
        )

    return grant.model_dump(mode="json")


@router.get("")
async def list_grants(
    status: GrantStatus | None = None,
    source: GrantSource | None = None,
    limit: int = 100,
) -> dict:
    """List all grants with optional filtering."""
    grant_manager = get_grant_manager()

    grants = await grant_manager.list_grants(limit=limit)

    # Apply filters
    if status:
        grants = [g for g in grants if g.status == status]
    if source:
        grants = [g for g in grants if g.source == source]

    return {
        "grants": [grant.model_dump(mode="json") for grant in grants],
        "total": len(grants),
    }
