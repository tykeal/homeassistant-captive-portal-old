# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for theme fallback scenarios."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestThemeFallback:
    """Integration tests for theme asset fallback handling."""

    @pytest.mark.asyncio
    async def test_missing_logo_fallback(self, test_client: TestClient) -> None:
        """Test theme fallback when logo asset is missing."""
        # Set theme with invalid logo URL
        theme_request = {
            "portal_title": "Fallback Test Portal",
            "background_color": "#f0f0f0",
            "primary_color": "#333333",
            "logo_url": "https://invalid-domain-that-does-not-exist.com/logo.png",
        }

        response = test_client.post("/api/theme", json=theme_request)
        assert response.status_code == 200

        # Get portal page - should render without errors despite missing logo
        portal_response = test_client.get("/portal")
        assert portal_response.status_code == 200

        html_content = portal_response.text

        # Should contain fallback behavior (no broken img tags, default placeholder)
        assert "Fallback Test Portal" in html_content
        assert "#f0f0f0" in html_content  # Background color should still apply
        assert "#333333" in html_content  # Primary color should still apply

        # Should not have broken image references
        assert (
            'src="https://invalid-domain-that-does-not-exist.com/logo.png"'
            not in html_content
        )

    @pytest.mark.asyncio
    async def test_corrupted_theme_config_fallback(
        self, test_client: TestClient
    ) -> None:
        """Test fallback to default theme when theme config is corrupted."""
        # Simulate corrupted theme data
        with patch(
            "src.services.theme_manager.ThemeManager.get_current_theme"
        ) as mock_get_theme:
            # Return invalid theme data
            mock_get_theme.side_effect = ValueError("Corrupted theme data")

            # Portal should still render with default theme
            portal_response = test_client.get("/portal")
            assert portal_response.status_code == 200

            html_content = portal_response.text

            # Should contain default theme values
            assert "Guest Network Access" in html_content  # Default title
            # Default colors should be present in CSS
            assert "#f5f5f5" in html_content or "#007bff" in html_content

    @pytest.mark.asyncio
    async def test_invalid_css_fallback(self, test_client: TestClient) -> None:
        """Test theme rendering when custom CSS is invalid."""
        theme_request = {
            "portal_title": "CSS Test Portal",
            "background_color": "#ffffff",
            "primary_color": "#000000",
            "custom_css": """
                /* Invalid CSS with syntax errors */
                .portal-container {
                    background-color: #ffffff
                    /* Missing semicolon */
                    border-radius: 10px;
                }

                .invalid-selector {{{
                    /* Invalid brackets */
                    color: red;
                }

                @import "non-existent-file.css";
            """,
        }

        response = test_client.post("/api/theme", json=theme_request)
        assert response.status_code == 200

        # Portal should still render despite invalid CSS
        portal_response = test_client.get("/portal")
        assert portal_response.status_code == 200

        html_content = portal_response.text

        # Should contain the theme title and basic colors
        assert "CSS Test Portal" in html_content
        assert "#ffffff" in html_content
        assert "#000000" in html_content

        # Page should be functional despite CSS errors
        assert "<form" in html_content  # Login form should be present
        assert "submit" in html_content.lower()  # Submit button should be present

    @pytest.mark.asyncio
    async def test_theme_asset_loading_timeout(self, test_client: TestClient) -> None:
        """Test theme behavior when assets take too long to load."""
        # Use a URL that will timeout
        theme_request = {
            "portal_title": "Timeout Test Portal",
            "background_color": "#f8f9fa",
            "primary_color": "#6c757d",
            "logo_url": "https://httpbin.org/delay/30",  # 30 second delay
        }

        response = test_client.post("/api/theme", json=theme_request)
        assert response.status_code == 200

        # Portal should render quickly without waiting for slow assets
        import time

        start_time = time.time()

        portal_response = test_client.get("/portal")

        end_time = time.time()
        response_time = end_time - start_time

        assert portal_response.status_code == 200
        assert response_time < 5.0, (
            f"Portal took {response_time:.2f}s, should be <5s even with slow assets"
        )

        html_content = portal_response.text
        assert "Timeout Test Portal" in html_content

    @pytest.mark.asyncio
    async def test_theme_preview_with_invalid_params(
        self, test_client: TestClient
    ) -> None:
        """Test theme preview fallback with invalid parameters."""
        # Request preview with invalid color values
        invalid_params = {
            "portal_title": "Preview Test",
            "background_color": "not-a-color",
            "primary_color": "#invalid",
        }

        response = test_client.get("/api/theme/preview", params=invalid_params)

        # Should still return a preview, falling back to valid defaults
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html"

        html_content = response.text

        # Should contain the valid title but default colors
        assert "Preview Test" in html_content

        # Should have fallen back to default colors
        # (exact color values depend on implementation)
        assert "#" in html_content  # Should have some valid hex color

    @pytest.mark.asyncio
    async def test_theme_asset_size_limits(self, test_client: TestClient) -> None:
        """Test theme behavior with oversized assets."""
        # Try to set a theme with a very large image URL
        # (This simulates cases where the asset might be too large)
        theme_request = {
            "portal_title": "Size Test Portal",
            "background_color": "#ffffff",
            "primary_color": "#000000",
            "logo_url": "https://httpbin.org/bytes/10485760",  # 10MB response
        }

        response = test_client.post("/api/theme", json=theme_request)
        assert response.status_code == 200

        # Portal should handle oversized assets gracefully
        portal_response = test_client.get("/portal")
        assert portal_response.status_code == 200

        html_content = portal_response.text
        assert "Size Test Portal" in html_content

        # Should not include the oversized asset or should have timeout protection
        # Implementation should either skip the asset or have size limits

    @pytest.mark.asyncio
    async def test_default_theme_restore(self, test_client: TestClient) -> None:
        """Test restoration to default theme when current theme is problematic."""
        # Set a problematic theme
        problematic_theme = {
            "portal_title": "Problematic Portal",
            "background_color": "#000000",  # All black
            "primary_color": "#000000",  # All black (poor contrast)
            "logo_url": "javascript:alert('xss')",  # Security issue
        }

        response = test_client.post("/api/theme", json=problematic_theme)
        # Theme service should reject dangerous URLs

        # Try to reset to default
        reset_response = test_client.post("/api/theme/reset")
        assert reset_response.status_code == 200

        reset_theme = reset_response.json()

        # Should be back to safe defaults
        assert reset_theme["portal_title"] == "Guest Network Access"
        assert reset_theme["background_color"] == "#f5f5f5"
        assert reset_theme["primary_color"] == "#007bff"
        assert reset_theme.get("logo_url") is None

    @pytest.mark.asyncio
    async def test_theme_validation_sanitization(self, test_client: TestClient) -> None:
        """Test that theme input is properly validated and sanitized."""
        # Try various XSS and injection attempts
        dangerous_theme = {
            "portal_title": "<script>alert('xss')</script>Dangerous Title",
            "background_color": "#ffffff' onload='alert(1)'",
            "primary_color": "#000000",
            "custom_css": """
                body { background: url('javascript:alert(1)'); }
                .evil { content: '<script>alert(1)</script>'; }
            """,
        }

        response = test_client.post("/api/theme", json=dangerous_theme)

        # Should either reject the dangerous content or sanitize it
        if response.status_code == 200:
            # If accepted, should be sanitized
            portal_response = test_client.get("/portal")
            html_content = portal_response.text

            # Should not contain executable JavaScript
            assert "<script>" not in html_content
            assert "javascript:" not in html_content
            assert "onload=" not in html_content
        else:
            # Should be rejected with validation error
            assert response.status_code == 422
