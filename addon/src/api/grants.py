# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Grants API router."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import require_auth
from ..core.logging_config import get_logger
from ..models.domain import GrantSource, GrantStatus
from ..services.event_ingestion import get_event_ingestion_service
from ..services.grant_manager import get_grant_manager
from .models import GrantCreateRequest, GrantExtendRequest, GrantShortenRequest

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/grants",
    tags=["grants"],
    dependencies=[Depends(require_auth)],  # T048: Require auth for all grant endpoints
)


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
    logger.debug(
        "Checking grant activation",
        grant_id=grant.grant_id,
        start_time=grant.start_time.isoformat(),
        end_time=grant.end_time.isoformat(),
        now=now.isoformat(),
        should_activate=grant.start_time <= now and grant.end_time > now,
    )
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
    """Shorten or immediately terminate an existing grant.

    FR-013: Force terminate (immediate revoke) an active grant
    FR-019: Allow revocation prior to natural expiry

    Args:
        grant_id: Grant identifier
        request: Shortening parameters

    Returns:
        Updated grant JSON
    """
    grant_manager = get_grant_manager()

    try:
        # First get the grant
        grant = await grant_manager.get_grant_by_id(grant_id)
        if not grant:
            raise ValueError(f"Grant {grant_id} not found")

        if request.immediate:
            # Immediate termination (revoke) - FR-013, FR-019
            logger.info(
                "Processing immediate grant revocation",
                grant_id=grant_id,
                reason=request.reason,
            )

            updated_grant = await grant_manager.revoke_grant(
                grant=grant,
                reason=request.reason,
                immediate=True,
                user_id=None,  # TODO: Extract from auth context when implemented
            )

            logger.info(
                "Grant terminated immediately (forced termination)",
                grant_id=grant_id,
                reason=request.reason,
                controller_revoked=bool(updated_grant.controller_voucher_id),
            )
        else:
            # Scheduled shortening
            if not request.new_end_time:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="new_end_time required for scheduled shortening",
                )

            # FR-013: Normal shortening clamps to now with warning
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            if request.new_end_time < now:
                logger.warning(
                    "Shortening new_end_time is in past, clamping to now",
                    grant_id=grant_id,
                    requested_end_time=request.new_end_time.isoformat(),
                    clamped_to=now.isoformat(),
                )
                request.new_end_time = now

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


@router.post("/{grant_id}/activate")
async def activate_grant(grant_id: str) -> dict:
    """Manually activate a pending grant.

    This endpoint allows manual activation of grants that are in pending state.
    Typically used for testing or manual intervention when automatic activation
    hasn't occurred.
    """
    grant_manager = get_grant_manager()

    try:
        # Get the grant
        grant = await grant_manager.get_grant_by_id(grant_id)
        if not grant:
            raise ValueError(f"Grant {grant_id} not found")

        # Activate it
        activated_grant = await grant_manager.activate_grant(grant)

        logger.info(
            "Grant manually activated",
            grant_id=grant_id,
        )

        return activated_grant.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to activate grant",
            grant_id=grant_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post("/ingest-event", status_code=status.HTTP_201_CREATED)
async def ingest_rental_control_event(event_data: dict) -> dict:
    """Ingest a Rental Control event and create a grant.

    This endpoint allows manual ingestion of Rental Control events.
    In production, this would typically be called automatically by
    the Home Assistant integration.

    Required fields in event_data:
    - booking_id: Unique booking identifier
    - start_time: ISO 8601 timestamp
    - end_time: ISO 8601 timestamp
    - guest_name: Guest name
    """
    event_service = get_event_ingestion_service()

    try:
        grant_id = await event_service.ingest_rental_control_event(event_data)

        logger.info(
            "Rental Control event ingested",
            grant_id=grant_id,
            booking_id=event_data.get("booking_id"),
        )

        # Return the created grant
        grant_manager = get_grant_manager()
        grant = await grant_manager.get_grant_by_id(grant_id)

        if not grant:
            # Should not happen, but handle gracefully
            return {"grant_id": grant_id, "message": "Grant created"}

        return grant.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to ingest Rental Control event",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.patch("/{grant_id}/expire")
async def expire_grant(grant_id: str) -> dict:
    """Manually expire a grant (for testing expired credential rejection).

    This endpoint immediately expires a grant by setting its end_time to now
    and updating its status to expired. Useful for testing T018B expired
    credential rejection logic.

    Args:
        grant_id: Grant identifier

    Returns:
        Updated grant with expired status

    Raises:
        HTTPException: 404 if grant not found
    """
    grant_manager = get_grant_manager()

    try:
        # Get the grant
        grant = await grant_manager.get_grant_by_id(grant_id)
        if not grant:
            raise ValueError(f"Grant {grant_id} not found")

        # Manually set to expired
        from datetime import UTC, datetime

        from ..storage.database import get_db_session
        from ..storage.repository import GrantRepository

        grant.end_time = datetime.now(UTC)
        grant.status = GrantStatus.EXPIRED
        grant.modified_at = datetime.now(UTC)

        # Save the expired grant
        async with get_db_session() as session:
            grant_repo = GrantRepository(session)
            expired_grant = await grant_repo.update(grant)

        logger.info(
            "Grant manually expired",
            grant_id=grant_id,
        )

        return expired_grant.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to expire grant",
            grant_id=grant_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
