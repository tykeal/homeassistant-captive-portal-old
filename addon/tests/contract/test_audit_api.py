# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for audit API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestAuditAPI:
    """Contract tests for audit logging API."""

    @pytest.mark.asyncio
    async def test_get_audit_events(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit for retrieving audit events."""
        response = test_client.get("/api/audit", headers=auth_headers)

        assert response.status_code == 200
        audit_data = response.json()

        # Verify response structure
        assert "events" in audit_data
        assert "total" in audit_data
        assert "page" in audit_data
        assert "page_size" in audit_data

        assert isinstance(audit_data["events"], list)
        assert isinstance(audit_data["total"], int)
        assert isinstance(audit_data["page"], int)
        assert isinstance(audit_data["page_size"], int)

    @pytest.mark.asyncio
    async def test_get_audit_events_with_filters(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit with filter parameters."""
        # Test event type filter
        response = test_client.get(
            "/api/audit?event_type=grant_created", headers=auth_headers
        )

        assert response.status_code == 200
        audit_data = response.json()

        # All events should be grant_created type
        for event in audit_data["events"]:
            assert event["event_type"] == "grant_created"

    @pytest.mark.asyncio
    async def test_get_audit_events_date_range(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit with date range filters."""
        params = {
            "start_date": "2025-01-01T00:00:00Z",
            "end_date": "2025-01-31T23:59:59Z",
        }

        response = test_client.get("/api/audit", params=params, headers=auth_headers)

        assert response.status_code == 200
        audit_data = response.json()

        # Verify events are within date range
        for event in audit_data["events"]:
            assert "timestamp" in event
            # Event timestamps should be within range (basic check)
            assert event["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_get_audit_events_pagination(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit pagination."""
        # First page
        response = test_client.get(
            "/api/audit?page=1&page_size=10", headers=auth_headers
        )

        assert response.status_code == 200
        audit_data = response.json()

        assert audit_data["page"] == 1
        assert audit_data["page_size"] == 10
        assert len(audit_data["events"]) <= 10

    @pytest.mark.asyncio
    async def test_get_audit_event_structure(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test audit event structure and required fields."""
        response = test_client.get("/api/audit?page_size=1", headers=auth_headers)

        assert response.status_code == 200
        audit_data = response.json()

        if audit_data["events"]:
            event = audit_data["events"][0]

            # Required fields for audit events
            required_fields = ["event_id", "event_type", "timestamp", "details"]

            for field in required_fields:
                assert field in event, f"Missing required field: {field}"

            # Event type should be from known types
            valid_event_types = [
                "grant_created",
                "grant_activated",
                "grant_extended",
                "grant_shortened",
                "grant_revoked",
                "grant_expired",
                "voucher_created",
                "voucher_used",
                "voucher_deactivated",
                "portal_access",
                "theme_updated",
                "config_changed",
            ]

            assert event["event_type"] in valid_event_types

    @pytest.mark.asyncio
    async def test_get_audit_events_by_entity(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit filtered by entity ID."""
        # Filter by grant ID
        response = test_client.get(
            "/api/audit?entity_type=grant&entity_id=test123", headers=auth_headers
        )

        assert response.status_code == 200
        audit_data = response.json()

        # All events should relate to the specified entity
        for event in audit_data["events"]:
            if "entity_id" in event["details"]:
                assert event["details"]["entity_id"] == "test123"

    @pytest.mark.asyncio
    async def test_get_audit_invalid_filters(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit with invalid filter parameters."""
        # Invalid date format
        response = test_client.get(
            "/api/audit?start_date=invalid-date", headers=auth_headers
        )

        assert response.status_code == 422  # Validation error

        # Invalid page number
        response = test_client.get("/api/audit?page=-1", headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_audit_export(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test GET /api/audit/export for audit log export."""
        response = test_client.get("/api/audit/export?format=csv", headers=auth_headers)

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        # Test JSON export
        response = test_client.get(
            "/api/audit/export?format=json", headers=auth_headers
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
