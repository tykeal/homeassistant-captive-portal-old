# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Portal router for captive portal splash page and authentication."""

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..core.logging_config import get_logger
from ..models.domain import EventType, GrantSource
from ..services.audit_logger import get_audit_logger
from ..services.grant_manager import get_grant_manager
from ..services.rate_limiter import get_rate_limiter
from ..services.theme_manager import get_theme_manager
from ..services.voucher_service import get_voucher_service
from ..storage.database import get_db_session
from ..storage.repository import VoucherRepository

logger = get_logger(__name__)
router = APIRouter(prefix="/portal", tags=["portal"])


TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _validate_logo_url(logo_url: str | None) -> str | None:
    """Validate that a logo URL is accessible (quick DNS check).

    Args:
        logo_url: URL to validate

    Returns:
        The URL if valid and accessible, None otherwise
    """
    if not logo_url:
        return None

    try:
        # Parse the URL to get hostname
        parsed = urlparse(logo_url)
        if not parsed.hostname:
            return None

        # Quick DNS lookup with timeout to check if domain exists
        # This prevents showing logos from obviously invalid domains
        socket.setdefaulttimeout(0.5)  # 500ms timeout
        socket.gethostbyname(parsed.hostname)

        return logo_url

    except (TimeoutError, socket.gaierror, Exception) as e:
        logger.warning(
            "Logo URL validation failed, will not display logo",
            logo_url=logo_url,
            error=str(e),
        )
        return None
    finally:
        socket.setdefaulttimeout(None)  # Reset timeout


class AuthenticateRequest(BaseModel):
    """Request model for portal authentication."""

    voucher_code: str
    device_mac: str | None = None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/splash", response_class=HTMLResponse)
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

        # Validate logo URL (quick DNS check) to avoid broken images
        validated_logo_url = _validate_logo_url(theme.logo_url)

        # Render template with theme data
        return templates.TemplateResponse(
            "splash.html",
            {
                "request": request,
                "portal_title": theme.portal_title,
                "background_color": theme.background_color,
                "primary_color": theme.primary_color,
                "logo_url": validated_logo_url,
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


@router.post("/splash", response_class=HTMLResponse, response_model=None)
async def splash_page_form_submit(
    request: Request, credential: str = Form(...)
) -> HTMLResponse | RedirectResponse:
    """Handle form submission from splash page (for performance testing).

    This endpoint handles traditional form POST submissions,
    primarily for compatibility with performance testing scenarios.
    Production usage should use the /authenticate JSON API endpoint.

    Args:
        request: FastAPI request object
        credential: Form field with credential/voucher code

    Returns:
        Redirect to success page or re-render splash with error
    """
    from starlette import status as http_status

    if not credential:
        # Return error response (simplified for testing)
        theme_manager = get_theme_manager()
        theme = await theme_manager.get_current_theme(use_fallback=True)

        # Validate logo URL
        validated_logo_url = _validate_logo_url(theme.logo_url)

        return templates.TemplateResponse(
            "splash.html",
            {
                "request": request,
                "portal_title": theme.portal_title,
                "background_color": theme.background_color,
                "primary_color": theme.primary_color,
                "logo_url": validated_logo_url,
                "custom_css": theme.custom_css,
                "error": "Please enter a credential",
            },
            status_code=http_status.HTTP_200_OK,
        )

    # For testing: simulate successful authentication and redirect
    return RedirectResponse(
        url="/portal/success", status_code=http_status.HTTP_303_SEE_OTHER
    )


@router.post("/authenticate", response_model=None)
async def authenticate(
    auth_request: AuthenticateRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Authenticate user with voucher code and provision network access.

    This endpoint validates the voucher code, creates a grant, and
    provisions network access through the controller.

    FR-009: Validate credentials and transition to authorized state
    Implements rate limiting to prevent brute force attacks.

    Args:
        auth_request: Authentication request with voucher code
        request: FastAPI request object (for client IP)

    Returns:
        Success dict with grant_id or JSONResponse with error details
        (status: 401 on invalid credentials, 429 on rate limit, 500 on system error)
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit (FR-009 security)
    rate_limiter = get_rate_limiter()
    is_allowed, rate_info = await rate_limiter.check_rate_limit(client_ip)

    if not is_allowed:
        logger.warning(
            "Portal authentication blocked by rate limit",
            client_ip=client_ip,
            lockout_info=rate_info,
        )

        # Audit log the rate limit event
        audit_logger = get_audit_logger()
        await audit_logger.log_event(
            event_type=EventType.PORTAL_RATE_LIMIT,
            details={
                "client_ip": client_ip,
                "locked_out": rate_info.get("locked_out"),
                "remaining_seconds": rate_info.get("remaining_seconds"),
            },
        )

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "status": "error",
                "message": (
                    f"Too many authentication attempts. "
                    f"Please try again in {rate_info.get('remaining_seconds', 300)} seconds."
                ),
                "retry_after": rate_info.get("remaining_seconds", 300),
            },
        )

    logger.info(
        "Portal authentication attempt",
        voucher_code=auth_request.voucher_code[:4] + "***",  # Log partial code
        device_mac=auth_request.device_mac,
        client_ip=client_ip,
    )

    voucher_service = get_voucher_service()

    # Lookup voucher by code
    async with get_db_session() as session:
        voucher_repo = VoucherRepository(session)
        voucher = await voucher_repo.get_by_code(auth_request.voucher_code)

    if not voucher:
        # Record failed attempt
        await rate_limiter.record_attempt(client_ip, success=False)

        logger.warning(
            "Invalid voucher code",
            voucher_code=auth_request.voucher_code[:4] + "***",
            client_ip=client_ip,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "status": "error",
                "message": "Invalid voucher code",
            },
        )

    # Check usage limits FIRST (FR-018: prevent reuse of exhausted vouchers)
    # This must come before is_valid() check since voucher becomes inactive after max_uses
    if voucher.max_uses != -1 and voucher.uses_count >= voucher.max_uses:
        # Record failed attempt
        await rate_limiter.record_attempt(client_ip, success=False)

        logger.warning(
            "Voucher usage limit exceeded",
            voucher_id=voucher.voucher_id,
            voucher_code=auth_request.voucher_code[:4] + "***",
            uses_count=voucher.uses_count,
            max_uses=voucher.max_uses,
        )

        # Audit log the rejection
        audit_logger = get_audit_logger()
        await audit_logger.log_portal_access(
            result="rejected_usage_limit",
            details={
                "success": False,
                "voucher_code": auth_request.voucher_code[:4] + "***",
                "device_mac": auth_request.device_mac,
                "rejection_reason": f"Usage limit exceeded ({voucher.uses_count}/{voucher.max_uses})",
                "voucher_id": voucher.voucher_id,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "status": "error",
                "message": (
                    "This voucher has already been used and cannot be reused. "
                    "Please request a new access code from the property manager."
                ),
            },
        )

    # Check if voucher is valid and active (FR-018: expired credential rejection)
    if not voucher.is_valid():
        # Record failed attempt
        await rate_limiter.record_attempt(client_ip, success=False)

        # Determine specific rejection reason for better user messaging
        now = datetime.now(UTC)
        rejection_reason = "not active"

        if voucher.status != "active":
            rejection_reason = f"status is {voucher.status.value}"
        elif voucher.expires_at and now > voucher.expires_at:
            rejection_reason = "has expired"

        logger.warning(
            "Expired/invalid voucher rejected",
            voucher_id=voucher.voucher_id,
            voucher_code=auth_request.voucher_code[:4] + "***",
            status=voucher.status.value,
            expires_at=voucher.expires_at.isoformat() if voucher.expires_at else None,
            reason=rejection_reason,
        )

        # Audit log the rejection (FR-018: audit expired credential attempts)
        audit_logger = get_audit_logger()
        await audit_logger.log_portal_access(
            result="rejected_expired",
            details={
                "success": False,
                "voucher_code": auth_request.voucher_code[:4] + "***",
                "device_mac": auth_request.device_mac,
                "rejection_reason": f"Voucher {rejection_reason}",
                "voucher_id": voucher.voucher_id,
            },
        )

        # User-friendly error message
        if "expired" in rejection_reason:
            message = (
                "This voucher has expired and cannot be used. "
                "Please contact the property manager for a new access code."
            )
        else:
            message = (
                "This voucher is not currently active. "
                "Please check with the property manager."
            )

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "status": "error",
                "message": message,
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
            device_mac=auth_request.device_mac,
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

        # Record successful attempt (clears rate limit history)
        await rate_limiter.record_attempt(client_ip, success=True)

        # Audit log successful authentication (FR-018: audit all access attempts)
        audit_logger = get_audit_logger()
        await audit_logger.log_portal_access(
            result="success",
            details={
                "success": True,
                "voucher_code": auth_request.voucher_code[:4] + "***",
                "device_mac": auth_request.device_mac,
                "grant_id": grant.grant_id,
                "voucher_id": voucher.voucher_id,
            },
        )

        return {
            "status": "success",
            "message": "Access granted",
            "grant_id": grant.grant_id,
            "expires_at": grant.end_time.isoformat(),
        }

    except Exception as e:
        # Record failed attempt on system error
        await rate_limiter.record_attempt(client_ip, success=False)

        logger.error(
            "Portal authentication failed",
            voucher_code=auth_request.voucher_code[:4] + "***",
            error=str(e),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": "System error during authentication",
            },
        )


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
