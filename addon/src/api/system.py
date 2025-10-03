# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""System API router for administrative operations."""

from fastapi import APIRouter

from ..core.logging_config import get_logger
from ..services.expiry_scheduler import get_expiry_scheduler

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])


@router.post("/process-expiry")
async def process_expiry() -> dict:
    """Manually trigger expiry processing.

    This endpoint processes all grants that have passed their
    end_time + grace period and marks them as expired.

    Useful for testing (T018C) and manual administrative operations.

    Returns:
        Dictionary with processing results:
        - expired: Number of grants marked as expired
        - revoked: Number of grants with access revoked
        - failed: Number of grants that failed processing
    """
    expiry_scheduler = get_expiry_scheduler()

    logger.info("Manual expiry processing triggered")

    results = await expiry_scheduler.process_expiries()

    logger.info(
        "Manual expiry processing complete",
        expired=results["expired"],
        revoked=results["revoked"],
        failed=results["failed"],
    )

    return {
        "status": "success",
        "results": results,
    }


@router.get("/grace-period")
async def get_grace_period() -> dict:
    """Get the current grace period setting.

    Returns:
        Dictionary with grace_period_minutes
    """
    expiry_scheduler = get_expiry_scheduler()
    minutes = await expiry_scheduler.get_grace_period_minutes()

    return {
        "grace_period_minutes": minutes,
    }


@router.post("/grace-period")
async def set_grace_period(minutes: int) -> dict:
    """Update the grace period setting.

    Args:
        minutes: New grace period in minutes (must be >= 0)

    Returns:
        Dictionary with updated grace_period_minutes
    """
    expiry_scheduler = get_expiry_scheduler()
    await expiry_scheduler.set_grace_period_minutes(minutes)

    return {
        "status": "success",
        "grace_period_minutes": minutes,
    }
