# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Theme API router."""

from datetime import UTC, datetime

from fastapi import APIRouter

from ..core.logging_config import get_logger
from ..models.domain import ThemeConfig
from ..storage.database import get_db_session
from ..storage.repository import ThemeRepository
from .models import ThemeUpdateRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/theme", tags=["theme"])


@router.get("")
async def get_current_theme() -> dict:
    """Get the current theme configuration."""
    async with get_db_session() as session:
        theme_repo = ThemeRepository(session)
        theme = await theme_repo.get_current_theme()

    return theme.model_dump(mode="json")


@router.post("")
async def update_theme(request: ThemeUpdateRequest) -> dict:
    """Update theme configuration.

    Supports partial updates - only provided fields will be updated.
    """
    async with get_db_session() as session:
        theme_repo = ThemeRepository(session)

        # Get current theme
        current_theme = await theme_repo.get_current_theme()

        # Apply updates (partial update support)
        update_data = request.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if value is not None and hasattr(current_theme, field):
                setattr(current_theme, field, value)

        # Update timestamp
        current_theme.updated_at = datetime.now(UTC)

        # Save updated theme
        updated_theme = await theme_repo.update_theme(current_theme)

        logger.info(
            "Theme updated",
            updated_fields=list(update_data.keys()),
        )

        return updated_theme.model_dump(mode="json")


@router.post("/reset")
async def reset_theme() -> dict:
    """Reset theme to default configuration."""
    async with get_db_session() as session:
        theme_repo = ThemeRepository(session)

        # Create default theme
        default_theme = ThemeConfig(
            portal_title="Guest Network Portal",
            background_color="#ffffff",
            primary_color="#0066cc",
            logo_url=None,
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        # Save default theme
        reset_theme = await theme_repo.update_theme(default_theme)

        logger.info("Theme reset to defaults")

        return reset_theme.model_dump(mode="json")


@router.get("/preview")
async def preview_theme(
    portal_title: str | None = None,
    background_color: str | None = None,
    primary_color: str | None = None,
) -> dict:
    """Preview theme with specified parameters without saving."""
    async with get_db_session() as session:
        theme_repo = ThemeRepository(session)
        current_theme = await theme_repo.get_current_theme()

    # Create preview theme by overlaying parameters
    preview_data = current_theme.model_dump()

    if portal_title:
        preview_data["portal_title"] = portal_title
    if background_color:
        preview_data["background_color"] = background_color
    if primary_color:
        preview_data["primary_color"] = primary_color

    return preview_data
