# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for theme API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestThemeAPI:
    """Contract tests for theme management API."""

    @pytest.mark.asyncio
    async def test_post_theme_update(self, test_client: TestClient) -> None:
        """Test POST /api/theme for theme configuration update."""
        theme_request = {
            "portal_title": "Updated Guest Portal",
            "background_color": "#f8f9fa",
            "primary_color": "#28a745",
            "logo_url": "https://example.com/logo.png",
        }

        response = test_client.post("/api/theme", json=theme_request)

        assert response.status_code == 200
        theme_data = response.json()

        # Verify updated theme data
        assert theme_data["portal_title"] == "Updated Guest Portal"
        assert theme_data["background_color"] == "#f8f9fa"
        assert theme_data["primary_color"] == "#28a745"
        assert theme_data["logo_url"] == "https://example.com/logo.png"
        assert "updated_at" in theme_data

    @pytest.mark.asyncio
    async def test_get_theme_current(self, test_client: TestClient) -> None:
        """Test GET /api/theme for current theme configuration."""
        response = test_client.get("/api/theme")

        assert response.status_code == 200
        theme_data = response.json()

        # Required theme fields
        required_fields = ["portal_title", "background_color", "primary_color"]

        for field in required_fields:
            assert field in theme_data

        # Optional fields
        optional_fields = ["logo_url", "updated_at"]
        for field in optional_fields:
            # Field may or may not be present, but if present should not be null
            if field in theme_data:
                assert theme_data[field] is not None

    @pytest.mark.asyncio
    async def test_post_theme_validation(self, test_client: TestClient) -> None:
        """Test POST /api/theme validation for invalid theme data."""
        # Invalid color format
        invalid_theme = {
            "portal_title": "Test Portal",
            "background_color": "invalid-color",
            "primary_color": "#28a745",
        }

        response = test_client.post("/api/theme", json=invalid_theme)
        assert response.status_code == 422

        # Invalid URL format
        invalid_theme = {
            "portal_title": "Test Portal",
            "background_color": "#ffffff",
            "primary_color": "#000000",
            "logo_url": "not-a-url",
        }

        response = test_client.post("/api/theme", json=invalid_theme)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_theme_partial_update(self, test_client: TestClient) -> None:
        """Test POST /api/theme with partial theme update."""
        # Get current theme first
        get_response = test_client.get("/api/theme")
        current_theme = get_response.json()

        # Update only the title
        partial_update = {"portal_title": "Partially Updated Portal"}

        response = test_client.post("/api/theme", json=partial_update)

        assert response.status_code == 200
        updated_theme = response.json()

        # Title should be updated
        assert updated_theme["portal_title"] == "Partially Updated Portal"

        # Other fields should remain unchanged
        assert updated_theme["background_color"] == current_theme["background_color"]
        assert updated_theme["primary_color"] == current_theme["primary_color"]

    @pytest.mark.asyncio
    async def test_post_theme_reset_to_default(self, test_client: TestClient) -> None:
        """Test POST /api/theme/reset for resetting to default theme."""
        response = test_client.post("/api/theme/reset")

        assert response.status_code == 200
        reset_theme = response.json()

        # Should contain default values
        assert reset_theme["portal_title"] == "Guest Network Access"
        assert reset_theme["background_color"] == "#f5f5f5"
        assert reset_theme["primary_color"] == "#007bff"
        assert reset_theme.get("logo_url") is None

    @pytest.mark.asyncio
    async def test_get_theme_preview(self, test_client: TestClient) -> None:
        """Test GET /api/theme/preview for theme preview generation."""
        # Create theme preview with custom settings
        preview_params = {
            "portal_title": "Preview Portal",
            "background_color": "#e3f2fd",
            "primary_color": "#1976d2",
        }

        response = test_client.get("/api/theme/preview", params=preview_params)

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html"

        # HTML content should contain the preview elements
        html_content = response.text
        assert "Preview Portal" in html_content
        assert "#e3f2fd" in html_content
        assert "#1976d2" in html_content

    @pytest.mark.asyncio
    async def test_post_theme_with_custom_css(self, test_client: TestClient) -> None:
        """Test POST /api/theme with custom CSS snippets."""
        theme_with_css = {
            "portal_title": "Custom Styled Portal",
            "background_color": "#ffffff",
            "primary_color": "#ff5722",
            "custom_css": """
                .portal-container {
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }
                .login-form {
                    padding: 2rem;
                }
            """,
        }

        response = test_client.post("/api/theme", json=theme_with_css)

        assert response.status_code == 200
        theme_data = response.json()

        assert "custom_css" in theme_data
        assert ".portal-container" in theme_data["custom_css"]

    @pytest.mark.asyncio
    async def test_delete_theme_asset(self, test_client: TestClient) -> None:
        """Test DELETE /api/theme/assets/{filename} for removing theme assets."""
        # This would typically be used to remove uploaded logos, etc.
        response = test_client.delete("/api/theme/assets/old-logo.png")

        assert response.status_code in [200, 404]  # 200 if existed, 404 if not found
