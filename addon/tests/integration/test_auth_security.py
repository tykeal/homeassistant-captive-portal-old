# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Security tests for authentication and authorization (T049).

Tests that admin API endpoints properly reject unauthorized requests
and return appropriate HTTP status codes (401/403) when authentication
is enabled.
"""

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.core import auth


class TestAuthenticationRequired:
    """Test that admin endpoints require authentication when auth is enabled."""

    @pytest.fixture(autouse=True)
    def setup_auth_mode(self, monkeypatch):
        """Set up API key auth mode for these tests."""
        # Save original auth service
        original_auth_service = auth._auth_service

        # Set API key for testing
        monkeypatch.setenv("CAPTIVE_PORTAL_API_KEY", "test-secret-key-12345")
        # Clear supervisor token to avoid conflicts
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        # Reset auth service singleton to pick up new environment
        auth._auth_service = None

        yield

        # Restore original auth service
        auth._auth_service = original_auth_service

    @pytest.fixture
    def auth_client(self):
        """Create test client with auth enabled."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_grants_endpoint_rejects_unauthenticated(self, auth_client):
        """Test GET /api/grants returns 401 without credentials."""
        response = auth_client.get("/api/grants")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_grants_endpoint_rejects_invalid_token(self, auth_client):
        """Test GET /api/grants returns 401 with invalid token."""
        response = auth_client.get(
            "/api/grants",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_vouchers_endpoint_rejects_unauthenticated(self, auth_client):
        """Test POST /api/vouchers returns 401 without credentials."""
        response = auth_client.post(
            "/api/vouchers",
            json={"duration_hours": 4, "description": "Test"},
        )
        assert response.status_code == 401

    def test_theme_endpoint_rejects_unauthenticated(self, auth_client):
        """Test GET /api/theme returns 401 without credentials."""
        response = auth_client.get("/api/theme")
        assert response.status_code == 401

    def test_audit_endpoint_rejects_unauthenticated(self, auth_client):
        """Test GET /api/audit returns 401 without credentials."""
        response = auth_client.get("/api/audit")
        assert response.status_code == 401

    def test_system_endpoint_rejects_unauthenticated(self, auth_client):
        """Test POST /api/system/process-expiry returns 401 without credentials."""
        response = auth_client.post("/api/system/process-expiry")
        assert response.status_code == 401

    def test_health_endpoint_public(self, auth_client):
        """Test /api/health is accessible without authentication."""
        response = auth_client.get("/api/health")
        # Should NOT be 401/403 (may be 500 if DB fails, but not auth failure)
        assert response.status_code not in (401, 403)

    def test_metrics_endpoint_public(self, auth_client):
        """Test /api/metrics is accessible without authentication."""
        response = auth_client.get("/api/metrics")
        # Should NOT be 401/403
        assert response.status_code not in (401, 403)

    def test_valid_api_key_grants_access(self, auth_client):
        """Test that valid API key allows access to protected endpoints."""
        response = auth_client.get(
            "/api/grants",
            headers={"Authorization": "Bearer test-secret-key-12345"},
        )
        # Should NOT be 401/403 (may be 500 if DB/service fails, but auth should pass)
        assert response.status_code not in (401, 403)


class TestAuthDisabledMode:
    """Test behavior when authentication is disabled (no credentials configured)."""

    @pytest.fixture(autouse=True)
    def setup_no_auth(self, monkeypatch):
        """Clear all auth credentials."""
        # Save original auth service
        original_auth_service = auth._auth_service

        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.delenv("CAPTIVE_PORTAL_API_KEY", raising=False)
        # Reset auth service
        auth._auth_service = None

        yield

        # Restore original auth service
        auth._auth_service = original_auth_service

    @pytest.fixture
    def noauth_client(self):
        """Create test client with auth disabled."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_grants_accessible_without_auth(self, noauth_client):
        """Test endpoints are accessible when auth is disabled."""
        response = noauth_client.get("/api/grants")
        # Should NOT be 401/403 when auth is disabled
        assert response.status_code not in (401, 403)


class TestAuthModes:
    """Test authentication mode detection."""

    @pytest.fixture(autouse=True)
    def cleanup_auth_service(self):
        """Clean up auth service after each test."""
        original_auth_service = auth._auth_service
        yield
        auth._auth_service = original_auth_service

    def test_supervisor_mode_when_token_present(self, monkeypatch):
        """Test supervisor mode is selected when SUPERVISOR_TOKEN is set."""
        monkeypatch.setenv("SUPERVISOR_TOKEN", "test-supervisor-token")
        monkeypatch.delenv("CAPTIVE_PORTAL_API_KEY", raising=False)
        auth._auth_service = None

        service = auth.get_auth_service()
        assert service.auth_mode == "supervisor"

    def test_api_key_mode_when_key_present(self, monkeypatch):
        """Test API key mode is selected when CAPTIVE_PORTAL_API_KEY is set."""
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.setenv("CAPTIVE_PORTAL_API_KEY", "test-api-key")
        auth._auth_service = None

        service = auth.get_auth_service()
        assert service.auth_mode == "api_key"

    def test_disabled_mode_when_no_credentials(self, monkeypatch):
        """Test auth is disabled when no credentials are configured."""
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.delenv("CAPTIVE_PORTAL_API_KEY", raising=False)
        auth._auth_service = None

        service = auth.get_auth_service()
        assert service.auth_mode == "disabled"


class TestAuthorizationHeaders:
    """Test various Authorization header formats."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, monkeypatch):
        """Enable API key auth."""
        # Save original auth service
        original_auth_service = auth._auth_service

        monkeypatch.setenv("CAPTIVE_PORTAL_API_KEY", "valid-key")
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        auth._auth_service = None

        yield

        # Restore original auth service
        auth._auth_service = original_auth_service

    @pytest.fixture
    def auth_client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_bearer_prefix_rejected(self, auth_client):
        """Test that Authorization header without 'Bearer' prefix is rejected."""
        response = auth_client.get(
            "/api/grants",
            headers={"Authorization": "valid-key"},
        )
        assert response.status_code == 401

    def test_empty_token_rejected(self, auth_client):
        """Test that empty token is rejected."""
        response = auth_client.get(
            "/api/grants",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_malformed_header_rejected(self, auth_client):
        """Test that malformed Authorization header is rejected."""
        response = auth_client.get(
            "/api/grants",
            headers={"Authorization": "NotBearer valid-key"},
        )
        assert response.status_code == 401
