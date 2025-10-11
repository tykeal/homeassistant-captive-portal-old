# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for forced termination logging and additional portal scenarios."""

import pytest
from fastapi.testclient import TestClient


class TestForcedTerminationLogging:
    """Integration tests for forced termination and audit logging."""

    @pytest.mark.asyncio
    async def test_forced_termination_audit_logging(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test forced termination logging (T018)."""
        # Create active grant
        grant_request = {
            "booking_id": "forced_term_001",
            "start_time": "2024-12-01T15:00:00Z",
            "end_time": "2025-01-15T18:00:00Z",
            "guest_name": "Force Term User",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response.status_code == 201
        grant_id = response.json()["grant_id"]

        # Force terminate
        terminate_request = {
            "reason": "Policy violation - unauthorized devices",
            "immediate": True,
        }

        term_response = test_client.patch(
            f"/api/grants/{grant_id}/shorten",
            json=terminate_request,
            headers=auth_headers,
        )
        assert term_response.status_code == 200

        # Check audit logs
        audit_response = test_client.get("/api/audit", headers=auth_headers)
        audit_events = audit_response.json()["events"]

        # Find termination event
        term_events = [e for e in audit_events if e["event_type"] == "grant_revoked"]
        assert len(term_events) > 0

        term_event = term_events[0]
        assert (
            term_event["details"]["reason"] == "Policy violation - unauthorized devices"
        )
        assert term_event["details"]["immediate"]


class TestSplashPageCredentialValidation:
    """Integration tests for splash page credential validation (T018A)."""

    @pytest.mark.asyncio
    async def test_splash_page_credential_success(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test splash page credential validation success (T018A)."""
        # Create active voucher
        voucher_request = {
            "duration_hours": 24,
            "description": "Splash test voucher",
            "created_by": "admin",
        }

        voucher_response = test_client.post(
            "/api/vouchers", json=voucher_request, headers=auth_headers
        )
        voucher = voucher_response.json()

        # Test successful credential submission
        credential_data = {
            "voucher_code": voucher["code"],
            "device_mac": "aa:bb:cc:dd:ee:ff",
        }

        response = test_client.post("/portal/authenticate", json=credential_data)
        assert response.status_code == 200

        result = response.json()
        assert result["status"] == "success"
        assert "grant_id" in result

    @pytest.mark.asyncio
    async def test_splash_page_credential_failure(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test splash page credential validation failure (T018A)."""
        # Test invalid voucher code
        invalid_credential = {
            "voucher_code": "INVALID123",
            "device_mac": "aa:bb:cc:dd:ee:ff",
        }

        response = test_client.post("/portal/authenticate", json=invalid_credential)
        assert response.status_code == 401

        result = response.json()
        assert result["status"] == "error"
        assert "invalid" in result["message"].lower()


class TestExpiredCredentialReuse:
    """Integration tests for expired credential reuse denial (T018B)."""

    @pytest.mark.asyncio
    async def test_expired_credential_reuse_denied(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test expired credential reuse denied (T018B)."""
        # Create expired voucher (short duration)
        voucher_request = {
            "duration_hours": 1,
            "description": "Expired test voucher",
            "created_by": "admin",
        }

        voucher_response = test_client.post(
            "/api/vouchers", json=voucher_request, headers=auth_headers
        )
        voucher = voucher_response.json()

        # Use the voucher initially
        initial_use = {
            "voucher_code": voucher["code"],
            "device_mac": "bb:cc:dd:ee:ff:aa",
        }

        initial_response = test_client.post("/portal/authenticate", json=initial_use)
        assert initial_response.status_code == 200
        grant_id = initial_response.json()["grant_id"]

        # Manually expire the grant
        expire_response = test_client.patch(
            f"/api/grants/{grant_id}/expire", headers=auth_headers
        )
        assert expire_response.status_code == 200

        # Try to reuse the same voucher code after expiry
        reuse_attempt = {
            "voucher_code": voucher["code"],
            "device_mac": "cc:dd:ee:ff:aa:bb",
        }

        reuse_response = test_client.post("/portal/authenticate", json=reuse_attempt)

        # Should be denied if voucher is single-use and already consumed
        assert reuse_response.status_code in [401, 403]
        result = reuse_response.json()
        assert (
            "expired" in result["message"].lower()
            or "used" in result["message"].lower()
        )


class TestAutomaticExpiryScheduler:
    """Integration tests for automatic expiry scheduler (T018C)."""

    @pytest.mark.asyncio
    async def test_automatic_expiry_scheduler_grace_period(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test automatic expiry scheduler revokes grants after grace period (T018C)."""
        # Create grant that should be expired
        expired_grant_request = {
            "booking_id": "auto_expire_001",
            "start_time": "2024-11-01T15:00:00Z",  # Past
            "end_time": "2024-11-01T18:00:00Z",  # Past (expired)
            "guest_name": "Auto Expire User",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=expired_grant_request, headers=auth_headers
        )
        assert response.status_code == 201
        grant_id = response.json()["grant_id"]

        # Trigger expiry processing
        expiry_response = test_client.post(
            "/api/system/process-expiry", headers=auth_headers
        )
        assert expiry_response.status_code == 200

        # Check grant status
        status_response = test_client.get(
            f"/api/grants/{grant_id}", headers=auth_headers
        )
        grant_data = status_response.json()

        assert grant_data["status"] == "expired"

        # Check audit log for expiry event
        audit_response = test_client.get("/api/audit", headers=auth_headers)
        audit_events = audit_response.json()["events"]

        expiry_events = [e for e in audit_events if e["event_type"] == "grant_expired"]
        assert len(expiry_events) > 0


class TestRentalControlEventIngestion:
    """Integration tests for Rental Control event ingestion (T018D)."""

    @pytest.mark.asyncio
    async def test_rental_control_event_creates_pending_then_activates(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test Rental Control event ingestion creates pending grant then activates at start (T018D)."""
        # Simulate future Rental Control event
        from datetime import UTC, datetime, timedelta

        future_start = datetime.now(UTC) + timedelta(days=30)
        future_end = future_start + timedelta(hours=3)

        future_event = {
            "booking_id": "future_booking_001",
            "start_time": future_start.isoformat().replace("+00:00", "Z"),
            "end_time": future_end.isoformat().replace("+00:00", "Z"),
            "guest_name": "Future Guest",
            "source": "rental_control",
        }

        # Create grant from future event
        response = test_client.post(
            "/api/grants", json=future_event, headers=auth_headers
        )
        assert response.status_code == 201

        grant_data = response.json()
        assert grant_data["status"] == "pending"  # Should be pending until start time

        # Verify the grant will activate at start time (manual activation should fail for future grants)
        activation_response = test_client.post(
            f"/api/grants/{grant_data['grant_id']}/activate", headers=auth_headers
        )

        # Activation should fail because start time is in the future
        assert activation_response.status_code == 404
        error_data = activation_response.json()
        assert "start time" in error_data["detail"].lower()

        # Verify grant remains pending
        status_response = test_client.get(
            f"/api/grants/{grant_data['grant_id']}", headers=auth_headers
        )
        current_grant = status_response.json()
        assert current_grant["status"] == "pending"
        assert current_grant["start_time"] == future_event["start_time"]
