# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Theme manager for portal customization with fallback support."""

import re
from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import ThemeConfig
from ..storage.database import get_db_session
from ..storage.repository import ThemeRepository

logger = get_logger(__name__)


class ThemeManager:
    """Manages portal theme configuration with validation and fallback."""

    # Default theme configuration
    DEFAULT_THEME = ThemeConfig(
        portal_title="Guest Network Access",
        background_color="#f5f5f5",
        primary_color="#007bff",
        logo_url=None,
        custom_css=None,
        updated_at=datetime.now(UTC),
    )

    # URL validation pattern
    URL_PATTERN = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    # Color validation pattern (hex colors)
    COLOR_PATTERN = re.compile(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")

    # Dangerous CSS patterns to sanitize
    DANGEROUS_CSS_PATTERNS = [
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"<script", re.IGNORECASE),
        re.compile(r"</script>", re.IGNORECASE),
        re.compile(r"on\w+\s*=", re.IGNORECASE),  # onclick, onload, etc.
        re.compile(r"expression\s*\(", re.IGNORECASE),  # IE expression()
        re.compile(r"@import", re.IGNORECASE),  # Prevent external CSS imports
        re.compile(r"url\s*\([^)]*javascript:", re.IGNORECASE),
    ]

    def __init__(self):
        """Initialize the theme manager."""
        self._cache: ThemeConfig | None = None
        self._cache_timestamp: datetime | None = None
        self._cache_ttl_seconds = 300  # 5 minutes

    async def get_current_theme(self, use_fallback: bool = True) -> ThemeConfig:
        """Get the current theme configuration with optional fallback.

        Args:
            use_fallback: Whether to return default theme on error

        Returns:
            Current theme configuration

        Raises:
            ValueError: If theme cannot be loaded and use_fallback is False
        """
        # Check cache
        if self._is_cache_valid():
            logger.debug("Returning cached theme")
            return self._cache  # type: ignore

        try:
            async with get_db_session() as session:
                theme_repo = ThemeRepository(session)
                theme = await theme_repo.get_current_theme()

            # Validate theme
            self._validate_theme(theme)

            # Update cache
            self._cache = theme
            self._cache_timestamp = datetime.now(UTC)

            logger.debug("Theme loaded from database")
            return theme

        except Exception as e:
            logger.warning(
                "Failed to load theme from database",
                error=str(e),
                use_fallback=use_fallback,
            )

            if use_fallback:
                logger.info("Using default theme as fallback")
                return self.DEFAULT_THEME
            else:
                raise ValueError(f"Failed to load theme: {e}") from e

    async def update_theme(self, theme_updates: dict[str, Any]) -> ThemeConfig:
        """Update theme configuration with validation.

        Args:
            theme_updates: Dictionary of theme fields to update

        Returns:
            Updated theme configuration

        Raises:
            ValueError: If validation fails
        """
        # Get current theme
        current_theme = await self.get_current_theme(use_fallback=False)

        # Apply updates
        update_data = {}
        for field, value in theme_updates.items():
            if value is not None and hasattr(current_theme, field):
                # Validate specific fields
                if field == "logo_url" and value:
                    self._validate_url(value)
                elif field in ("background_color", "primary_color") and value:
                    self._validate_color(value)
                elif field == "custom_css" and value:
                    value = self._sanitize_css(value)

                update_data[field] = value

        # Update theme object
        for field, value in update_data.items():
            setattr(current_theme, field, value)

        current_theme.updated_at = datetime.now(UTC)

        # Save to database
        async with get_db_session() as session:
            theme_repo = ThemeRepository(session)
            updated_theme = await theme_repo.update_theme(current_theme)

        # Invalidate cache
        self._invalidate_cache()

        logger.info(
            "Theme updated",
            updated_fields=list(update_data.keys()),
        )

        return updated_theme

    async def reset_to_default(self) -> ThemeConfig:
        """Reset theme to default configuration.

        Returns:
            Default theme configuration
        """
        default_theme = ThemeConfig(
            portal_title=self.DEFAULT_THEME.portal_title,
            background_color=self.DEFAULT_THEME.background_color,
            primary_color=self.DEFAULT_THEME.primary_color,
            logo_url=None,
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        async with get_db_session() as session:
            theme_repo = ThemeRepository(session)
            reset_theme = await theme_repo.update_theme(default_theme)

        # Invalidate cache
        self._invalidate_cache()

        logger.info("Theme reset to default")

        return reset_theme

    def _validate_theme(self, theme: ThemeConfig) -> None:
        """Validate theme configuration.

        Args:
            theme: Theme to validate

        Raises:
            ValueError: If validation fails
        """
        # Validate required fields
        if not theme.portal_title or len(theme.portal_title.strip()) == 0:
            raise ValueError("portal_title cannot be empty")

        # Validate colors
        if theme.background_color:
            self._validate_color(theme.background_color)
        if theme.primary_color:
            self._validate_color(theme.primary_color)

        # Validate logo URL if present
        if theme.logo_url:
            self._validate_url(theme.logo_url)

        # Validate custom CSS if present
        if theme.custom_css:
            if self._contains_dangerous_css(theme.custom_css):
                raise ValueError("Custom CSS contains potentially dangerous content")

    def _validate_url(self, url: str) -> None:
        """Validate URL format.

        Args:
            url: URL to validate

        Raises:
            ValueError: If URL is invalid
        """
        if not url or len(url.strip()) == 0:
            return  # Empty URL is allowed (will use fallback)

        if not self.URL_PATTERN.match(url):
            raise ValueError(f"Invalid URL format: {url}")

        # Additional security checks
        if "javascript:" in url.lower():
            raise ValueError("JavaScript URLs are not allowed")

        if len(url) > 2048:
            raise ValueError("URL too long (max 2048 characters)")

    def _validate_color(self, color: str) -> None:
        """Validate hex color format.

        Args:
            color: Color to validate (hex format)

        Raises:
            ValueError: If color is invalid
        """
        if not color or len(color.strip()) == 0:
            raise ValueError("Color cannot be empty")

        if not self.COLOR_PATTERN.match(color):
            raise ValueError(
                f"Invalid color format: {color}. Expected hex color (e.g., #FF0000)"
            )

    def _sanitize_css(self, css: str) -> str:
        """Sanitize custom CSS to remove dangerous content.

        Args:
            css: CSS to sanitize

        Returns:
            Sanitized CSS

        Raises:
            ValueError: If CSS contains dangerous content that can't be sanitized
        """
        # Check for dangerous patterns
        if self._contains_dangerous_css(css):
            logger.warning(
                "Custom CSS contains dangerous patterns, attempting sanitization"
            )

            # Try to remove dangerous patterns
            sanitized = css
            for pattern in self.DANGEROUS_CSS_PATTERNS:
                sanitized = pattern.sub("/* REMOVED */", sanitized)

            # Verify no dangerous content remains
            if self._contains_dangerous_css(sanitized):
                raise ValueError(
                    "Custom CSS contains dangerous content that cannot be sanitized"
                )

            return sanitized

        return css

    def _contains_dangerous_css(self, css: str) -> bool:
        """Check if CSS contains dangerous patterns.

        Args:
            css: CSS to check

        Returns:
            True if dangerous content detected
        """
        for pattern in self.DANGEROUS_CSS_PATTERNS:
            if pattern.search(css):
                return True
        return False

    def _is_cache_valid(self) -> bool:
        """Check if cached theme is still valid.

        Returns:
            True if cache is valid
        """
        if not self._cache or not self._cache_timestamp:
            return False

        age = (datetime.now(UTC) - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds

    def _invalidate_cache(self) -> None:
        """Invalidate the theme cache."""
        self._cache = None
        self._cache_timestamp = None
        logger.debug("Theme cache invalidated")

    async def validate_logo_accessible(self, logo_url: str) -> bool:
        """Check if logo URL is accessible (optional validation).

        This is a placeholder for future implementation that could verify
        logo accessibility before saving theme configuration.

        Args:
            logo_url: Logo URL to check

        Returns:
            True if accessible, False otherwise
        """
        # TODO: Implement actual HTTP check with timeout
        # For now, just validate format
        try:
            self._validate_url(logo_url)
            return True
        except ValueError:
            return False


# Global theme manager instance
_theme_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager
