# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for vouchers API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestVouchersAPI:
    """Contract tests for voucher management API."""

    @pytest.mark.asyncio
    async def test_post_vouchers_create(self, test_client: TestClient) -> None:
        """Test POST /api/vouchers for manual voucher creation."""
        voucher_request = {
            "duration_hours": 24,
            "description": "Manual guest access",
            "created_by": "admin",
            "max_uses": 1,
        }

        response = test_client.post("/api/vouchers", json=voucher_request)

        assert response.status_code == 201
        voucher_data = response.json()

        # Verify response structure
        required_fields = [
            "voucher_id",
            "code",
            "duration_hours",
            "description",
            "created_by",
            "max_uses",
            "uses_count",
            "status",
            "created_at",
            "expires_at",
        ]
        for field in required_fields:
            assert field in voucher_data

        assert voucher_data["duration_hours"] == 24
        assert voucher_data["description"] == "Manual guest access"
        assert voucher_data["created_by"] == "admin"
        assert voucher_data["max_uses"] == 1
        assert voucher_data["uses_count"] == 0
        assert voucher_data["status"] == "active"

        # Voucher code should be generated
        assert len(voucher_data["code"]) >= 8
        assert voucher_data["code"].isalnum()

    @pytest.mark.asyncio
    async def test_post_vouchers_validation(self, test_client: TestClient) -> None:
        """Test POST /api/vouchers validation."""
        # Invalid duration (negative)
        invalid_request = {
            "duration_hours": -1,
            "description": "Invalid voucher",
            "created_by": "admin",
        }

        response = test_client.post("/api/vouchers", json=invalid_request)
        assert response.status_code == 422

        # Missing required fields
        incomplete_request = {
            "duration_hours": 24
            # Missing description and created_by
        }

        response = test_client.post("/api/vouchers", json=incomplete_request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_vouchers_unlimited_uses(self, test_client: TestClient) -> None:
        """Test POST /api/vouchers with unlimited uses."""
        voucher_request = {
            "duration_hours": 4,
            "description": "Multi-use voucher",
            "created_by": "admin",
            "max_uses": -1,  # Unlimited
        }

        response = test_client.post("/api/vouchers", json=voucher_request)

        assert response.status_code == 201
        voucher_data = response.json()
        assert voucher_data["max_uses"] == -1

    @pytest.mark.asyncio
    async def test_get_vouchers_list(self, test_client: TestClient) -> None:
        """Test GET /api/vouchers for listing vouchers."""
        response = test_client.get("/api/vouchers")

        assert response.status_code == 200
        vouchers_data = response.json()

        assert "vouchers" in vouchers_data
        assert "total" in vouchers_data
        assert isinstance(vouchers_data["vouchers"], list)
        assert isinstance(vouchers_data["total"], int)

    @pytest.mark.asyncio
    async def test_get_voucher_by_id(self, test_client: TestClient) -> None:
        """Test GET /api/vouchers/{id} for specific voucher."""
        # Create voucher first
        voucher_request = {
            "duration_hours": 12,
            "description": "Test voucher",
            "created_by": "admin",
        }

        create_response = test_client.post("/api/vouchers", json=voucher_request)
        voucher_id = create_response.json()["voucher_id"]

        # Get voucher by ID
        response = test_client.get(f"/api/vouchers/{voucher_id}")

        assert response.status_code == 200
        voucher_data = response.json()
        assert voucher_data["voucher_id"] == voucher_id
        assert voucher_data["description"] == "Test voucher"

    @pytest.mark.asyncio
    async def test_delete_voucher(self, test_client: TestClient) -> None:
        """Test DELETE /api/vouchers/{id} for voucher deactivation."""
        # Create voucher first
        voucher_request = {
            "duration_hours": 6,
            "description": "Voucher to delete",
            "created_by": "admin",
        }

        create_response = test_client.post("/api/vouchers", json=voucher_request)
        voucher_id = create_response.json()["voucher_id"]

        # Delete voucher
        response = test_client.delete(f"/api/vouchers/{voucher_id}")

        assert response.status_code == 200

        # Verify voucher is deactivated
        get_response = test_client.get(f"/api/vouchers/{voucher_id}")
        assert get_response.status_code == 200
        voucher_data = get_response.json()
        assert voucher_data["status"] == "inactive"
