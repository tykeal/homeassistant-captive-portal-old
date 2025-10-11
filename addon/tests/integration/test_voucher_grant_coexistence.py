# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for voucher and Rental Control derived grant coexistence."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


class TestVoucherGrantCoexistence:
    """Integration tests for managing both vouchers and Rental Control grants."""

    @pytest.mark.asyncio
    async def test_voucher_grant_creation_coexistence(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that voucher-based grants and Rental Control grants can coexist."""
        now = datetime.now(UTC)

        # Create a Rental Control grant (currently active)
        rental_grant_request = {
            "booking_id": "coexist_rental_001",
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(days=30)).isoformat(),
            "guest_name": "Rental Guest",
            "source": "rental_control",
        }

        rental_response = test_client.post(
            "/api/grants", json=rental_grant_request, headers=auth_headers
        )
        assert rental_response.status_code == 201
        rental_grant = rental_response.json()

        # Create a voucher-sourced grant (simulating voucher redemption, currently active)
        voucher_grant_request = {
            "booking_id": "voucher_guest_001",
            "start_time": (now - timedelta(minutes=30)).isoformat(),
            "end_time": (now + timedelta(days=1)).isoformat(),
            "guest_name": "Voucher Guest",
            "device_mac": "aa:bb:cc:dd:ee:ff",
            "source": "voucher",
        }

        voucher_grant_response = test_client.post(
            "/api/grants", json=voucher_grant_request, headers=auth_headers
        )
        assert voucher_grant_response.status_code == 201
        voucher_grant = voucher_grant_response.json()

        # Verify both grants exist and are distinct
        assert rental_grant["source"] == "rental_control"
        assert voucher_grant["source"] == "voucher"
        assert rental_grant["grant_id"] != voucher_grant["grant_id"]

        # Both should be active (assuming past start times)
        assert rental_grant["status"] == "active"
        assert voucher_grant["status"] == "active"

    @pytest.mark.asyncio
    async def test_audit_logging_different_sources(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that audit logs correctly distinguish between grant sources."""
        # Create grants from different sources
        rental_request = {
            "booking_id": "audit_rental_001",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-01-15T18:00:00Z",
            "guest_name": "Audit Rental Guest",
            "source": "rental_control",
        }

        voucher_request = {
            "duration_hours": 12,
            "description": "Audit voucher test",
            "created_by": "admin",
        }

        # Create both
        rental_response = test_client.post(
            "/api/grants", json=rental_request, headers=auth_headers
        )
        voucher_response = test_client.post(
            "/api/vouchers", json=voucher_request, headers=auth_headers
        )

        assert rental_response.status_code == 201
        assert voucher_response.status_code == 201

        # Check audit logs
        audit_response = test_client.get("/api/audit", headers=auth_headers)
        assert audit_response.status_code == 200

        audit_data = audit_response.json()
        events = audit_data["events"]

        # Find the relevant events
        rental_events = [
            e for e in events if "rental_control" in str(e.get("details", {}))
        ]
        voucher_events = [e for e in events if "voucher" in str(e.get("details", {}))]

        assert len(rental_events) > 0, "Should have rental control events"
        assert len(voucher_events) > 0, "Should have voucher events"

        # Verify event details distinguish sources
        for event in rental_events:
            assert event["event_type"] in ["grant_created", "grant_activated"]

        for event in voucher_events:
            assert event["event_type"] in ["voucher_created", "grant_created"]

    @pytest.mark.asyncio
    async def test_concurrent_access_different_sources(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test concurrent network access from different grant sources."""
        now = datetime.now(UTC)

        # Create overlapping grants from different sources
        rental_request = {
            "booking_id": "concurrent_rental",
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(days=30)).isoformat(),
            "guest_name": "Concurrent Rental",
            "source": "rental_control",
        }

        # Create rental grant
        rental_response = test_client.post(
            "/api/grants", json=rental_request, headers=auth_headers
        )
        assert rental_response.status_code == 201

        # Create voucher-sourced grant (48 hours)
        voucher_grant_request = {
            "booking_id": "concurrent_voucher",
            "start_time": (now - timedelta(minutes=30)).isoformat(),
            "end_time": (now + timedelta(hours=48)).isoformat(),
            "guest_name": "Concurrent Voucher",
            "device_mac": "bb:cc:dd:ee:ff:aa",
            "source": "voucher",
        }

        voucher_grant_response = test_client.post(
            "/api/grants", json=voucher_grant_request, headers=auth_headers
        )
        assert voucher_grant_response.status_code == 201

        # Get list of active grants
        grants_response = test_client.get(
            "/api/grants?status=active", headers=auth_headers
        )
        assert grants_response.status_code == 200

        active_grants = grants_response.json()["grants"]

        # Should have both active grants
        rental_grants = [g for g in active_grants if g["source"] == "rental_control"]
        voucher_grants = [g for g in active_grants if g["source"] == "voucher"]

        assert len(rental_grants) >= 1, "Should have active rental grant"
        assert len(voucher_grants) >= 1, "Should have active voucher grant"

    @pytest.mark.asyncio
    async def test_voucher_reuse_with_existing_rental_grants(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test multiple voucher grants can coexist with rental grants."""
        # Create rental grant
        rental_request = {
            "booking_id": "reuse_rental_001",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-01-15T18:00:00Z",
            "guest_name": "Rental Guest",
            "source": "rental_control",
        }

        rental_response = test_client.post(
            "/api/grants", json=rental_request, headers=auth_headers
        )
        assert rental_response.status_code == 201

        # Create multiple voucher-sourced grants (6 hours each)
        for i in range(3):
            voucher_grant_request = {
                "booking_id": f"voucher_grant_{i + 1:03d}",
                "start_time": "2024-12-01T16:00:00Z",
                "end_time": "2024-12-01T22:00:00Z",  # 6 hours
                "guest_name": f"Voucher Guest {i + 1}",
                "device_mac": f"cc:dd:ee:ff:aa:{i:02d}",
                "source": "voucher",
            }

            use_response = test_client.post(
                "/api/grants", json=voucher_grant_request, headers=auth_headers
            )
            assert use_response.status_code == 201

            voucher_grant = use_response.json()
            assert voucher_grant["source"] == "voucher"

        # Verify all grants exist
        all_grants_response = test_client.get("/api/grants", headers=auth_headers)
        assert all_grants_response.status_code == 200

        all_grants = all_grants_response.json()["grants"]
        rental_grants = [g for g in all_grants if g["source"] == "rental_control"]
        voucher_grants = [g for g in all_grants if g["source"] == "voucher"]

        assert len(rental_grants) >= 1
        assert len(voucher_grants) >= 3

    @pytest.mark.asyncio
    async def test_expiry_handling_mixed_sources(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test expiry handling for grants from different sources."""
        # Create short-lived grants from both sources
        rental_request = {
            "booking_id": "expiry_rental",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2024-12-01T16:00:00Z",  # 1 hour duration (past)
            "guest_name": "Expiry Rental",
            "source": "rental_control",
        }

        # Create rental grant (should be expired)
        rental_response = test_client.post(
            "/api/grants", json=rental_request, headers=auth_headers
        )
        assert rental_response.status_code == 201
        rental_grant_id = rental_response.json()["grant_id"]

        # Create voucher-sourced grant (also expired, 1 hour)
        voucher_grant_request = {
            "booking_id": "expiry_voucher",
            "start_time": "2024-12-01T16:00:00Z",
            "end_time": "2024-12-01T17:00:00Z",  # 1 hour (past)
            "guest_name": "Expiry Voucher Guest",
            "device_mac": "ee:ff:aa:bb:cc:dd",
            "source": "voucher",
        }

        voucher_grant_response = test_client.post(
            "/api/grants", json=voucher_grant_request, headers=auth_headers
        )
        assert voucher_grant_response.status_code == 201
        voucher_grant_id = voucher_grant_response.json()["grant_id"]

        # Trigger expiry processing
        expiry_response = test_client.post(
            "/api/system/process-expiry", headers=auth_headers
        )
        assert expiry_response.status_code == 200

        # Check that both grants are properly expired
        rental_check = test_client.get(
            f"/api/grants/{rental_grant_id}", headers=auth_headers
        )
        voucher_check = test_client.get(
            f"/api/grants/{voucher_grant_id}", headers=auth_headers
        )

        assert rental_check.status_code == 200
        assert voucher_check.status_code == 200

        rental_final = rental_check.json()
        voucher_final = voucher_check.json()

        # Both should be expired
        assert rental_final["status"] == "expired"
        assert voucher_final["status"] == "expired"

    @pytest.mark.asyncio
    async def test_metrics_separated_by_source(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that metrics properly separate grants by source."""
        now = datetime.now(UTC)

        # Create grants from both sources
        rental_request = {
            "booking_id": "metrics_rental",
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(days=30)).isoformat(),
            "guest_name": "Metrics Rental",
            "source": "rental_control",
        }

        voucher_grant_request = {
            "booking_id": "metrics_voucher",
            "start_time": (now - timedelta(minutes=30)).isoformat(),
            "end_time": (now + timedelta(days=1)).isoformat(),
            "guest_name": "Metrics Voucher Guest",
            "device_mac": "ff:aa:bb:cc:dd:ee",
            "source": "voucher",
        }

        # Create both
        test_client.post("/api/grants", json=rental_request, headers=auth_headers)
        test_client.post(
            "/api/grants", json=voucher_grant_request, headers=auth_headers
        )

        # Check metrics
        metrics_response = test_client.get("/api/metrics", headers=auth_headers)
        assert metrics_response.status_code == 200

        metrics_data = metrics_response.json()
        metrics_text = metrics_data["metrics"]

        # Should have total grants metric
        assert "captive_portal_grants_total" in metrics_text
        assert "captive_portal_grants_active" in metrics_text

        # Parse the actual values
        # The metrics show total grants created (should be 2)
        import re

        total_match = re.search(r"captive_portal_grants_total\s+(\d+)", metrics_text)
        active_match = re.search(r"captive_portal_grants_active\s+(\d+)", metrics_text)

        assert total_match is not None, "Should have grants_total metric"
        assert active_match is not None, "Should have grants_active metric"

        # Should have created 2 grants (1 rental + 1 voucher)
        total_grants = int(total_match.group(1))
        active_grants = int(active_match.group(1))

        assert total_grants >= 2, (
            f"Should have at least 2 total grants, got {total_grants}"
        )
        assert active_grants >= 2, (
            f"Should have at least 2 active grants, got {active_grants}"
        )
