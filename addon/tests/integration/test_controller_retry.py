# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for controller unreachable scenarios and retry logic."""

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.controllers.base import ProvisionResult


class TestControllerUnreachable:
    """Integration tests for controller connectivity and retry scenarios."""

    @pytest.mark.asyncio
    async def test_controller_unreachable_grant_remains_pending(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test grant creation when controller is unreachable - should remain in pending state."""
        # Reset and configure mock controller to simulate network failure
        mock_controller.provision_grant.reset_mock()
        mock_controller.provision_grant.side_effect = httpx.ConnectTimeout(
            "Connection timeout"
        )

        grant_request = {
            "booking_id": "unreachable_test_001",
            "start_time": "2025-01-01T00:00:00Z",  # Past time - would normally activate
            "end_time": "2026-12-31T23:59:59Z",  # Future time - grant is valid
            "guest_name": "Unreachable Test User",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )

        # Grant should be created but remain pending due to controller failure
        assert response.status_code == 201
        grant_data = response.json()
        assert grant_data["status"] == "pending"
        assert grant_data["booking_id"] == "unreachable_test_001"

        # Verify retry attempts were made
        assert mock_controller.provision_grant.call_count >= 1

    @pytest.mark.asyncio
    async def test_controller_retry_with_backoff(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test retry mechanism with exponential backoff when controller fails."""
        call_times = []

        async def track_call_time(*args, **kwargs) -> None:
            """Mock function that tracks call times to verify backoff behavior."""
            import time

            call_times.append(time.time())
            raise httpx.ConnectTimeout("Simulated failure")

        # Reset and configure mock controller to track call times
        mock_controller.provision_grant.reset_mock()
        mock_controller.provision_grant.side_effect = track_call_time

        grant_request = {
            "booking_id": "retry_test_001",
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2026-12-31T23:59:59Z",
            "guest_name": "Retry Test User",
            "source": "rental_control",
        }

        # Submit grant request
        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response.status_code == 201

        # Wait for retry attempts
        import asyncio

        await asyncio.sleep(5)  # Allow time for retries

        # Verify multiple retry attempts were made
        assert len(call_times) >= 2, "Should have made multiple retry attempts"

        # Verify backoff timing (each retry should be delayed)
        if len(call_times) >= 2:
            time_between_attempts = call_times[1] - call_times[0]
            assert time_between_attempts >= 0.5, (
                "Should have backoff delay between retries"
            )

    @pytest.mark.asyncio
    async def test_controller_recovery_pending_to_active(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test grant activation when controller becomes available after being unreachable."""
        # Track call attempts
        call_count = 0

        async def mock_provision_with_recovery(*args, **kwargs) -> None:
            """Mock function that fails twice then succeeds to simulate recovery."""
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # First 2 attempts fail
                raise httpx.ConnectTimeout("Controller unreachable")
            else:
                # Third attempt succeeds
                return ProvisionResult(
                    success=True,
                    controller_voucher_id="recovered_voucher_123",
                    message="Grant provisioned successfully",
                )

        # Reset and configure mock controller for recovery scenario
        mock_controller.provision_grant.reset_mock()
        mock_controller.provision_grant.side_effect = mock_provision_with_recovery

        grant_request = {
            "booking_id": "recovery_test_001",
            "start_time": "2025-01-01T00:00:00Z",  # Past time
            "end_time": "2026-12-31T23:59:59Z",
            "guest_name": "Recovery Test User",
            "source": "rental_control",
        }

        # Create grant (should start pending)
        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response.status_code == 201
        grant_id = response.json()["grant_id"]

        # Wait for retry logic to complete
        import asyncio

        await asyncio.sleep(8)  # Allow time for retries and recovery

        # Check grant status - should eventually become active
        get_response = test_client.get(f"/api/grants/{grant_id}", headers=auth_headers)
        assert get_response.status_code == 200

        final_grant = get_response.json()
        assert final_grant["status"] == "active", (
            "Grant should activate after controller recovery"
        )
        assert "controller_voucher_id" in final_grant

    @pytest.mark.asyncio
    async def test_controller_permanent_failure_handling(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test handling of grants when controller remains permanently unreachable."""
        # Reset and configure mock controller for permanent failure
        mock_controller.provision_grant.reset_mock()
        mock_controller.provision_grant.side_effect = httpx.ConnectTimeout(
            "Permanent failure"
        )

        grant_request = {
            "booking_id": "permanent_failure_001",
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2026-12-31T23:59:59Z",
            "guest_name": "Permanent Failure User",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response.status_code == 201
        grant_id = response.json()["grant_id"]

        # Wait for maximum retry period
        import asyncio

        await asyncio.sleep(10)

        # Grant should remain pending with error details
        get_response = test_client.get(f"/api/grants/{grant_id}", headers=auth_headers)
        assert get_response.status_code == 200

        grant_data = get_response.json()
        assert grant_data["status"] == "pending"
        assert "last_error" in grant_data
        assert "retry_count" in grant_data

    @pytest.mark.asyncio
    async def test_health_endpoint_controller_status(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test health endpoint reflects controller connectivity status."""
        # Test with healthy controller
        mock_controller.health_check.reset_mock()
        mock_controller.health_check.return_value = True

        response = test_client.get("/api/health", headers=auth_headers)
        assert response.status_code == 200

        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert "details" in health_data
        assert health_data["details"]["controller_healthy"] is True

        # Test with unhealthy controller
        mock_controller.health_check.reset_mock()
        mock_controller.health_check.side_effect = httpx.ConnectTimeout(
            "Controller unreachable"
        )

        response = test_client.get("/api/health", headers=auth_headers)
        assert response.status_code == 200  # Returns 200 but with degraded status

        health_data = response.json()
        assert health_data["status"] == "degraded"
        assert health_data["details"]["controller_healthy"] is False

    @pytest.mark.asyncio
    async def test_metrics_include_controller_failures(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_controller: MagicMock,
    ) -> None:
        """Test that controller failure metrics are tracked and exposed."""
        # Reset and configure mock controller for failure
        mock_controller.provision_grant.reset_mock()
        mock_controller.provision_grant.side_effect = httpx.ConnectTimeout(
            "Metrics test failure"
        )

        # Create a grant that will fail
        grant_request = {
            "booking_id": "metrics_failure_001",
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2026-12-31T23:59:59Z",
            "guest_name": "Metrics Test User",
            "source": "rental_control",
        }

        response = test_client.post(
            "/api/grants", json=grant_request, headers=auth_headers
        )
        assert response.status_code == 201

        # Wait for retry attempts
        import asyncio

        await asyncio.sleep(3)

        # Check metrics
        metrics_response = test_client.get("/api/metrics", headers=auth_headers)
        assert metrics_response.status_code == 200

        metrics_text = metrics_response.text

        # Verify failure metrics are present
        expected_metrics = [
            "controller_requests_total",
            "controller_failures_total",
            "controller_retry_attempts_total",
        ]

        for metric in expected_metrics:
            assert metric in metrics_text, f"Missing controller metric: {metric}"
