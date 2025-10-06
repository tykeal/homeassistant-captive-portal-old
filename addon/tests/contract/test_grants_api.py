# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for grants API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestGrantsAPI:
    """Contract tests for grants management API."""

    @pytest.mark.asyncio
    async def test_post_grants_provision_from_rental_control(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test POST /api/grants provision grant from Rental Control event.

        Expected flow: pending → active transition.
        """
        # Rental Control event data
        grant_request = {
            "booking_id": "booking_123",
            "start_time": "2025-01-01T15:00:00Z",
            "end_time": "2025-01-01T18:00:00Z",
            "guest_name": "John Doe",
            "source": "rental_control",
        }

        # POST to create grant
        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )

        # Should return 201 Created with grant details
        assert response.status_code == 201

        grant_data = response.json()
        assert grant_data["booking_id"] == "booking_123"
        assert grant_data["status"] == "pending"  # Initial state
        assert grant_data["guest_name"] == "John Doe"
        assert grant_data["source"] == "rental_control"
        assert "grant_id" in grant_data

        # Verify response schema
        required_fields = [
            "grant_id",
            "booking_id",
            "status",
            "start_time",
            "end_time",
            "guest_name",
            "source",
            "created_at",
        ]
        for field in required_fields:
            assert field in grant_data

    @pytest.mark.asyncio
    async def test_post_grants_immediate_activation(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test POST /api/grants for immediate activation scenario.

        When start_time is now or past, should transition to active.
        """
        grant_request = {
            "booking_id": "booking_124",
            "start_time": "2024-12-01T15:00:00Z",  # Past time
            "end_time": "2025-12-31T18:00:00Z",
            "guest_name": "Jane Smith",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )

        assert response.status_code == 201
        grant_data = response.json()
        assert grant_data["status"] == "active"  # Should activate immediately

    @pytest.mark.asyncio
    async def test_post_grants_validation_errors(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test POST /api/grants validation error handling."""
        # Missing required fields
        invalid_request = {"booking_id": "test"}

        response = test_client.post(
            "/api/grants", json=invalid_request, headers=auth_headers
        )

        assert response.status_code == 422  # Validation error
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_post_grants_duplicate_booking(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test POST /api/grants with duplicate booking ID."""
        grant_request = {
            "booking_id": "booking_duplicate",
            "start_time": "2025-01-01T15:00:00Z",
            "end_time": "2025-01-01T18:00:00Z",
            "guest_name": "Test User",
            "source": "rental_control",
        }

        # First request should succeed
        response1 = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response1.status_code == 201

        # Second request with same booking_id should fail
        response2 = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response2.status_code == 409  # Conflict

    @pytest.mark.asyncio
    async def test_patch_grants_extend(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test PATCH /api/grants/{id}/extend for grant extension."""
        # First create a grant
        grant_request = {
            "booking_id": "booking_extend",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-01-01T18:00:00Z",
            "guest_name": "Extend User",
            "source": "rental_control",
        }

        create_response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert create_response.status_code == 201
        grant_id = create_response.json()["grant_id"]

        # Extend the grant
        extend_request = {
            "new_end_time": "2025-01-02T18:00:00Z",  # Extend by 1 day
            "reason": "Guest requested extension",
        }

        response = test_client.patch(
            f"/api/grants/{grant_id}/extend", json=extend_request, headers=auth_headers
        )

        assert response.status_code == 200
        updated_grant = response.json()
        assert updated_grant["grant_id"] == grant_id
        assert updated_grant["end_time"] == "2025-01-02T18:00:00Z"
        assert "modified_at" in updated_grant

    @pytest.mark.asyncio
    async def test_patch_grants_extend_validation(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test PATCH /api/grants/{id}/extend validation."""
        # Create grant first
        grant_request = {
            "booking_id": "booking_extend_val",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-01-01T18:00:00Z",
            "guest_name": "Test User",
            "source": "rental_control",
        }

        create_response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        grant_id = create_response.json()["grant_id"]

        # Try to extend to past time (should fail)
        invalid_extend = {
            "new_end_time": "2024-11-01T18:00:00Z",  # Past time
            "reason": "Invalid extension",
        }

        response = test_client.patch(
            f"/api/grants/{grant_id}/extend", json=invalid_extend, headers=auth_headers
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_patch_grants_extend_nonexistent(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test PATCH /api/grants/{id}/extend for non-existent grant."""
        extend_request = {
            "new_end_time": "2025-01-02T18:00:00Z",
            "reason": "Test extension",
        }

        response = test_client.patch(
            "/api/grants/nonexistent/extend", json=extend_request, headers=auth_headers
        )
        assert response.status_code == 404  # Not found

    @pytest.mark.asyncio
    async def test_patch_grants_shorten(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test PATCH /api/grants/{id}/shorten for immediate force termination."""
        # Create active grant first
        grant_request = {
            "booking_id": "booking_shorten",
            "start_time": "2024-12-01T15:00:00Z",  # Past time = active
            "end_time": "2025-12-31T18:00:00Z",
            "guest_name": "Shorten User",
            "source": "rental_control",
        }

        create_response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert create_response.status_code == 201
        grant_id = create_response.json()["grant_id"]

        # Force terminate immediately
        shorten_request = {"reason": "Guest violated terms", "immediate": True}

        response = test_client.patch(
            f"/api/grants/{grant_id}/shorten",
            json=shorten_request,
            headers=auth_headers,
        )

        assert response.status_code == 200
        terminated_grant = response.json()
        assert terminated_grant["grant_id"] == grant_id
        assert terminated_grant["status"] == "revoked"
        assert "revoked_at" in terminated_grant
        assert terminated_grant["revocation_reason"] == "Guest violated terms"

    @pytest.mark.asyncio
    async def test_patch_grants_shorten_scheduled(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test PATCH /api/grants/{id}/shorten for scheduled termination."""
        # Create grant
        grant_request = {
            "booking_id": "booking_scheduled",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-12-31T18:00:00Z",
            "guest_name": "Scheduled User",
            "source": "rental_control",
        }

        create_response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        grant_id = create_response.json()["grant_id"]

        # Schedule termination for specific time
        shorten_request = {
            "new_end_time": "2025-01-15T12:00:00Z",
            "reason": "Early checkout",
            "immediate": False,
        }

        response = test_client.patch(
            f"/api/grants/{grant_id}/shorten",
            json=shorten_request,
            headers=auth_headers,
        )

        assert response.status_code == 200
        updated_grant = response.json()
        assert updated_grant["end_time"] == "2025-01-15T12:00:00Z"
        assert updated_grant["status"] == "active"  # Still active until end time
