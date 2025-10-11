# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for theme manager fallback logic."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.domain import ThemeConfig
from src.services.theme_manager import ThemeManager


@pytest.fixture
def theme_manager() -> ThemeManager:
    """Create a theme manager instance for testing."""
    return ThemeManager()


@pytest.fixture
def valid_theme() -> ThemeConfig:
    """Create a valid theme configuration."""
    return ThemeConfig(
        portal_title="Test Portal",
        background_color="#ffffff",
        primary_color="#0000ff",
        logo_url="https://example.com/logo.png",
        custom_css=".portal { margin: 10px; }",
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def default_theme() -> ThemeConfig:
    """Get the default theme configuration."""
    return ThemeManager.DEFAULT_THEME


class TestThemeFallbackLogic:
    """Test theme manager fallback behavior."""

    async def test_fallback_on_database_error(self, theme_manager) -> None:
        """Test that default theme is returned when database fails."""
        with patch("src.services.theme_manager.get_db_session") as mock_session:
            mock_session.side_effect = Exception("Database connection failed")

            theme = await theme_manager.get_current_theme(use_fallback=True)

            # Should return default theme
            assert theme.portal_title == ThemeManager.DEFAULT_THEME.portal_title
            assert theme.background_color == ThemeManager.DEFAULT_THEME.background_color
            assert theme.primary_color == ThemeManager.DEFAULT_THEME.primary_color

    async def test_fallback_disabled_raises_error(self, theme_manager) -> None:
        """Test that exception is raised when fallback is disabled."""
        with patch("src.services.theme_manager.get_db_session") as mock_session:
            mock_session.side_effect = Exception("Database error")

            with pytest.raises(ValueError, match="Failed to load theme"):
                await theme_manager.get_current_theme(use_fallback=False)

    async def test_fallback_on_missing_theme(self, theme_manager) -> None:
        """Test fallback when no theme exists in database."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = None

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                theme = await theme_manager.get_current_theme(use_fallback=True)

                # Should return default theme
                assert theme == ThemeManager.DEFAULT_THEME

    async def test_fallback_on_invalid_theme_title(self, theme_manager) -> None:
        """Test fallback when theme has invalid title."""
        invalid_theme = ThemeConfig(
            portal_title="",  # Invalid: empty title
            background_color="#ffffff",
            primary_color="#0000ff",
            logo_url=None,
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = invalid_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                theme = await theme_manager.get_current_theme(use_fallback=True)

                # Should return default theme due to validation failure
                assert theme.portal_title == ThemeManager.DEFAULT_THEME.portal_title

    async def test_fallback_on_invalid_color(self, theme_manager) -> None:
        """Test fallback when theme update has invalid color."""
        # Create a valid initial theme
        valid_theme = ThemeConfig(
            portal_title="Test",
            background_color="#ffffff",
            primary_color="#0000ff",
            logo_url=None,
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = valid_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # Try to update with invalid color - should raise ValueError
                with pytest.raises(ValueError, match="Invalid color format"):
                    # This validates the color before updating
                    theme_manager._validate_color("not-a-color")

    async def test_fallback_on_dangerous_css(self, theme_manager) -> None:
        """Test fallback when theme contains dangerous CSS."""
        dangerous_theme = ThemeConfig(
            portal_title="Test",
            background_color="#ffffff",
            primary_color="#0000ff",
            logo_url=None,
            custom_css="<script>alert('xss')</script>",  # Dangerous CSS
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = dangerous_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                theme = await theme_manager.get_current_theme(use_fallback=True)

                # Should return default theme
                assert (
                    theme.custom_css is None
                    or theme.custom_css == ThemeManager.DEFAULT_THEME.custom_css
                )

    async def test_fallback_on_invalid_logo_url(self, theme_manager) -> None:
        """Test fallback when theme update has invalid logo URL."""
        # Try to validate an invalid logo URL - should raise ValueError
        with pytest.raises(ValueError, match="Invalid URL format"):
            theme_manager._validate_url("javascript:alert('xss')")

    async def test_cache_used_on_subsequent_calls(
        self, theme_manager, valid_theme
    ) -> None:
        """Test that cached theme is used on subsequent calls."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = valid_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # First call loads from database
                theme1 = await theme_manager.get_current_theme(use_fallback=True)
                assert theme1.portal_title == valid_theme.portal_title

                # Second call should use cache
                theme2 = await theme_manager.get_current_theme(use_fallback=True)
                assert theme2 == theme1

                # Repository should only be called once
                assert mock_repo.get_current_theme.call_count == 1

    async def test_cache_invalidated_on_update(
        self, theme_manager, valid_theme
    ) -> None:
        """Test that cache is invalidated after update."""
        # Set up initial cached theme
        theme_manager._cache = valid_theme
        theme_manager._cache_timestamp = datetime.now(UTC)

        assert theme_manager._is_cache_valid()

        # Invalidate cache
        theme_manager._invalidate_cache()

        assert not theme_manager._is_cache_valid()
        assert theme_manager._cache is None
        assert theme_manager._cache_timestamp is None

    async def test_cache_expires_after_ttl(self, theme_manager, valid_theme) -> None:
        """Test that cache expires after TTL."""
        from datetime import timedelta

        # Set cache with old timestamp
        theme_manager._cache = valid_theme
        theme_manager._cache_timestamp = datetime.now(UTC) - timedelta(seconds=400)

        # Cache should be expired (TTL is 300 seconds)
        assert not theme_manager._is_cache_valid()

    async def test_default_theme_properties(self, default_theme) -> None:
        """Test that default theme has required properties."""
        assert default_theme.portal_title is not None
        assert len(default_theme.portal_title) > 0
        assert default_theme.background_color is not None
        assert default_theme.background_color.startswith("#")
        assert default_theme.primary_color is not None
        assert default_theme.primary_color.startswith("#")
        assert default_theme.logo_url is None  # Default has no logo
        assert default_theme.custom_css is None  # Default has no custom CSS

    async def test_reset_to_default(self, theme_manager) -> None:
        """Test resetting theme to default configuration."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.update_theme.return_value = ThemeManager.DEFAULT_THEME

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # Set a custom cache
                theme_manager._cache = ThemeConfig(
                    portal_title="Custom",
                    background_color="#000000",
                    primary_color="#ff0000",
                    logo_url="https://example.com/logo.png",
                    custom_css=".custom {}",
                    updated_at=datetime.now(UTC),
                )
                theme_manager._cache_timestamp = datetime.now(UTC)

                # Reset to default
                reset_theme = await theme_manager.reset_to_default()

                # Should match default theme
                assert (
                    reset_theme.portal_title == ThemeManager.DEFAULT_THEME.portal_title
                )
                assert (
                    reset_theme.background_color
                    == ThemeManager.DEFAULT_THEME.background_color
                )

                # Cache should be invalidated
                assert theme_manager._cache is None

    async def test_partial_theme_update_with_fallback(
        self, theme_manager, valid_theme
    ) -> None:
        """Test partial theme update doesn't break fallback."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = valid_theme
        mock_repo.update_theme.return_value = valid_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # Update only some fields
                updates = {
                    "portal_title": "New Title",
                    "background_color": "#ff0000",
                }

                updated_theme = await theme_manager.update_theme(updates)

                # Theme should still be valid after partial update
                assert updated_theme.portal_title == "New Title"

    async def test_missing_asset_fallback(self, theme_manager) -> None:
        """Test fallback when logo asset is missing (URL validation)."""
        # Theme with logo URL that might not exist
        theme_with_missing_logo = ThemeConfig(
            portal_title="Test",
            background_color="#ffffff",
            primary_color="#0000ff",
            logo_url="https://example.com/missing.png",  # Valid URL but might not exist
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = theme_with_missing_logo

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # Should still load theme (URL is valid, even if resource doesn't exist)
                theme = await theme_manager.get_current_theme(use_fallback=True)

                # Theme should be loaded (validation doesn't check resource existence)
                assert theme.logo_url == "https://example.com/missing.png"

    async def test_concurrent_fallback_requests(self, theme_manager) -> None:
        """Test that concurrent requests with fallback don't cause issues."""
        import asyncio

        with patch("src.services.theme_manager.get_db_session") as mock_session:
            mock_session.side_effect = Exception("Database error")

            # Request themes concurrently
            tasks = [
                theme_manager.get_current_theme(use_fallback=True) for _ in range(10)
            ]

            themes = await asyncio.gather(*tasks)

            # All should return default theme
            for theme in themes:
                assert theme.portal_title == ThemeManager.DEFAULT_THEME.portal_title

    async def test_validation_failure_triggers_fallback(self, theme_manager) -> None:
        """Test that validation failures trigger fallback appropriately."""
        # Create theme that will fail validation
        invalid_theme = ThemeConfig(
            portal_title="  ",  # Whitespace only - invalid
            background_color="#ffffff",
            primary_color="#0000ff",
            logo_url=None,
            custom_css=None,
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_current_theme.return_value = invalid_theme

        with patch(
            "src.services.theme_manager.get_db_session",
            return_value=mock_session,
        ):
            with patch(
                "src.services.theme_manager.ThemeRepository",
                return_value=mock_repo,
            ):
                # With fallback enabled
                theme = await theme_manager.get_current_theme(use_fallback=True)
                assert theme == ThemeManager.DEFAULT_THEME

                # Without fallback should raise
                theme_manager._invalidate_cache()
                with pytest.raises(ValueError):
                    await theme_manager.get_current_theme(use_fallback=False)
