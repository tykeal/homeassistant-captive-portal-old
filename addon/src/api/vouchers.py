# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Vouchers API router."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import require_auth
from ..core.logging_config import get_logger
from ..services.voucher_service import get_voucher_service
from .models import VoucherCreateRequest

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/vouchers",
    tags=["vouchers"],
    dependencies=[
        Depends(require_auth)
    ],  # T048: Require auth for all voucher endpoints
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_voucher(request: VoucherCreateRequest) -> dict:
    """Create a new voucher for manual guest access."""
    voucher_service = get_voucher_service()

    try:
        voucher = await voucher_service.create_voucher(
            duration_hours=request.duration_hours,
            description=request.description,
            created_by=request.created_by,
            max_uses=request.max_uses,
        )

        logger.info(
            "Voucher created",
            voucher_id=voucher.voucher_id,
            code=voucher.code,
            created_by=request.created_by,
        )

        return voucher.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to create voucher",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.get("/{voucher_id}")
async def get_voucher(voucher_id: str) -> dict:
    """Get details of a specific voucher."""
    voucher_service = get_voucher_service()

    voucher = await voucher_service.get_voucher_by_id(voucher_id)
    if not voucher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voucher {voucher_id} not found",
        )

    return voucher.model_dump(mode="json")


@router.get("")
async def list_vouchers(
    status_filter: str | None = None,
    limit: int = 100,
) -> dict:
    """List all vouchers with optional filtering."""
    voucher_service = get_voucher_service()

    vouchers = await voucher_service.list_vouchers(limit=limit)

    # Apply status filter if provided
    if status_filter:
        from ..models.domain import VoucherStatus

        try:
            status_enum = VoucherStatus(status_filter)
            vouchers = [v for v in vouchers if v.status == status_enum]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status: {status_filter}",
            ) from e

    return {
        "vouchers": [voucher.model_dump(mode="json") for voucher in vouchers],
        "total": len(vouchers),
    }


@router.delete("/{voucher_id}")
async def deactivate_voucher(
    voucher_id: str, reason: str = "Manual deactivation"
) -> dict:
    """Deactivate a voucher to prevent further use."""
    voucher_service = get_voucher_service()

    try:
        voucher = await voucher_service.deactivate_voucher(
            voucher_id=voucher_id,
            reason=reason,
        )

        logger.info(
            "Voucher deactivated",
            voucher_id=voucher_id,
            reason=reason,
        )

        if not voucher:
            # Should not happen since ValueError would be raised
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Voucher deactivation returned None",
            )

        return voucher.model_dump(mode="json")

    except ValueError as e:
        logger.warning(
            "Failed to deactivate voucher",
            voucher_id=voucher_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
