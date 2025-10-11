# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Theme API router."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ..core.auth import require_auth
from ..core.logging_config import get_logger
from ..services.theme_manager import get_theme_manager
from .models import ThemeUpdateRequest

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/theme",
    tags=["theme"],
    dependencies=[Depends(require_auth)],  # T048: Require auth for theme management
)


@router.get("")
async def get_current_theme() -> dict[str, Any]:
    """Get the current theme configuration."""
    theme_manager = get_theme_manager()
    theme = await theme_manager.get_current_theme(use_fallback=True)
    return theme.model_dump(mode="json")


@router.post("")
async def update_theme(request: ThemeUpdateRequest) -> dict[str, Any]:
    """Update theme configuration.

    Supports partial updates - only provided fields will be updated.
    """
    theme_manager = get_theme_manager()

    try:
        # Apply updates (partial update support)
        update_data = request.model_dump(exclude_unset=True)

        updated_theme = await theme_manager.update_theme(update_data)

        logger.info(
            "Theme updated",
            updated_fields=list(update_data.keys()),
        )

        return updated_theme.model_dump(mode="json")

    except ValueError as e:
        logger.warning("Theme validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.post("/reset")
async def reset_theme() -> dict[str, Any]:
    """Reset theme to default configuration."""
    theme_manager = get_theme_manager()
    reset_theme_config = await theme_manager.reset_to_default()

    logger.info("Theme reset to defaults")

    return reset_theme_config.model_dump(mode="json")


@router.get("/preview")
async def preview_theme(
    portal_title: str | None = None,
    background_color: str | None = None,
    primary_color: str | None = None,
    logo_url: str | None = None,
    custom_css: str | None = None,
) -> HTMLResponse:
    """Preview theme with specified parameters without saving.

    Falls back to current/default values if invalid parameters are provided.
    Returns HTML preview of the portal with the theme applied.
    """

    theme_manager = get_theme_manager()
    current_theme = await theme_manager.get_current_theme(use_fallback=True)

    # Start with current theme values
    preview_data = {
        "portal_title": current_theme.portal_title,
        "background_color": current_theme.background_color,
        "primary_color": current_theme.primary_color,
        "logo_url": current_theme.logo_url,
        "custom_css": current_theme.custom_css,
    }

    # Override with provided parameters (with validation)
    if portal_title:
        preview_data["portal_title"] = portal_title

    if background_color:
        try:
            theme_manager._validate_color(background_color)
            preview_data["background_color"] = background_color
        except ValueError:
            # Fall back to current value on validation error
            logger.warning(
                "Invalid background_color in preview, using current value",
                invalid_color=background_color,
            )

    if primary_color:
        try:
            theme_manager._validate_color(primary_color)
            preview_data["primary_color"] = primary_color
        except ValueError:
            # Fall back to current value on validation error
            logger.warning(
                "Invalid primary_color in preview, using current value",
                invalid_color=primary_color,
            )

    if logo_url:
        try:
            theme_manager._validate_url(logo_url)
            preview_data["logo_url"] = logo_url
        except ValueError:
            # Fall back to current value on validation error
            logger.warning(
                "Invalid logo_url in preview, using current value",
                invalid_url=logo_url,
            )

    if custom_css is not None:
        preview_data["custom_css"] = custom_css

    # Render preview template
    # Create a mock request object for template rendering
    from starlette.datastructures import Headers
    from starlette.requests import Request as StarletteRequest

    from ..portal.router import templates as portal_templates

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/theme/preview",
        "headers": Headers().raw,
        "query_string": b"",
    }
    mock_request = StarletteRequest(scope)

    return portal_templates.TemplateResponse(
        "splash.html",
        {
            "request": mock_request,
            **preview_data,
        },
    )
