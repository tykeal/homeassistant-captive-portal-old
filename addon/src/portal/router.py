# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Portal router for captive portal splash page and authentication."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..core.logging_config import get_logger
from ..models.domain import GrantSource
from ..services.grant_manager import get_grant_manager
from ..services.theme_manager import get_theme_manager
from ..services.voucher_service import get_voucher_service
from ..storage.database import get_db_session
from ..storage.repository import VoucherRepository

logger = get_logger(__name__)
router = APIRouter(prefix="/portal", tags=["portal"])


TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class AuthenticateRequest(BaseModel):
    """Request model for portal authentication."""

    voucher_code: str
    device_mac: str | None = None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def splash_page(request: Request) -> HTMLResponse:
    """Render the captive portal splash page with current theme.

    This is the main landing page for guests connecting to the network.
    It presents a form for entering voucher codes or booking credentials.

    FR-009: Present captive portal splash page
    """
    theme_manager = get_theme_manager()

    try:
        # Get current theme with fallback
        theme = await theme_manager.get_current_theme(use_fallback=True)

        # Render template with theme data
        return templates.TemplateResponse(
            "splash.html",
            {
                "request": request,
                "portal_title": theme.portal_title,
                "background_color": theme.background_color,
                "primary_color": theme.primary_color,
                "logo_url": theme.logo_url,
                "custom_css": theme.custom_css,
            },
        )

    except Exception as e:
        logger.error("Failed to render splash page", error=str(e))

        # Fallback to minimal splash page
        return templates.TemplateResponse(
            "splash.html",
            {
                "request": request,
                "portal_title": "Guest Network Access",
                "background_color": "#f5f5f5",
                "primary_color": "#007bff",
                "logo_url": None,
                "custom_css": None,
            },
        )


@router.post("/authenticate")
async def authenticate(request: AuthenticateRequest) -> dict[str, Any]:
    """Authenticate user with voucher code and provision network access.

    This endpoint validates the voucher code, creates a grant, and
    provisions network access through the controller.

    FR-009: Validate credentials and transition to authorized state

    Args:
        request: Authentication request with voucher code

    Returns:
        Success response with grant_id or error response

    Raises:
        HTTPException: 401 on invalid credentials, 500 on system error
    """
    logger.info(
        "Portal authentication attempt",
        voucher_code=request.voucher_code[:4] + "***",  # Log partial code
        device_mac=request.device_mac,
    )

    voucher_service = get_voucher_service()

    # Lookup voucher by code
    async with get_db_session() as session:
        voucher_repo = VoucherRepository(session)
        voucher = await voucher_repo.get_by_code(request.voucher_code)

    if not voucher:
        logger.warning(
            "Invalid voucher code",
            voucher_code=request.voucher_code[:4] + "***",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "message": "Invalid voucher code",
            },
        )

    # Check if voucher is valid and active
    if not voucher.is_valid():
        logger.warning(
            "Voucher not valid",
            voucher_id=voucher.voucher_id,
            status=voucher.status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "message": "Voucher has expired or is not active",
            },
        )

    # Check usage limits
    if voucher.max_uses != -1 and voucher.uses_count >= voucher.max_uses:
        logger.warning(
            "Voucher usage limit reached",
            voucher_id=voucher.voucher_id,
            uses_count=voucher.uses_count,
            max_uses=voucher.max_uses,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "message": "Voucher usage limit reached",
            },
        )

    try:
        # Use voucher (increment usage counter)
        await voucher_service.use_voucher(voucher)

        # Create a grant from the voucher
        grant_manager = get_grant_manager()

        # Calculate grant duration from voucher
        now = datetime.now(UTC)
        start_time = now

        # Use voucher expiration or default to duration_hours
        if voucher.expires_at:
            end_time = voucher.expires_at
        else:
            from datetime import timedelta

            end_time = now + timedelta(hours=voucher.duration_hours)

        # Create grant
        grant = await grant_manager.create_grant(
            booking_id=None,  # Voucher-based, no booking
            guest_name=f"Voucher {voucher.code[:4]}***",
            start_time=start_time,
            end_time=end_time,
            source=GrantSource.VOUCHER,
            device_mac=request.device_mac,
        )

        # Try to activate the grant immediately
        if grant.start_time <= now < grant.end_time:
            try:
                activated_grant = await grant_manager.activate_grant(grant)
                grant = activated_grant
                logger.info(
                    "Grant activated via portal authentication",
                    grant_id=grant.grant_id,
                    voucher_id=voucher.voucher_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to activate grant immediately",
                    grant_id=grant.grant_id,
                    error=str(e),
                )
                # Grant remains pending for retry

        logger.info(
            "Portal authentication successful",
            grant_id=grant.grant_id,
            voucher_id=voucher.voucher_id,
            status=grant.status.value,
        )

        return {
            "status": "success",
            "message": "Access granted",
            "grant_id": grant.grant_id,
            "expires_at": grant.end_time.isoformat(),
        }

    except Exception as e:
        logger.error(
            "Portal authentication failed",
            voucher_code=request.voucher_code[:4] + "***",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "System error during authentication",
            },
        ) from e


@router.get("/success", response_class=HTMLResponse)
async def success_page(request: Request) -> HTMLResponse:
    """Render success page after authentication.

    This page confirms successful network access and may show
    usage information or terms of service.
    """
    theme_manager = get_theme_manager()
    theme = await theme_manager.get_current_theme(use_fallback=True)

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "portal_title": theme.portal_title,
            "background_color": theme.background_color,
            "primary_color": theme.primary_color,
        },
    )
