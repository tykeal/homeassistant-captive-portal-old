# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for controller unreachable scenarios and retry logic."""

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient


class TestControllerUnreachable:
    """Integration tests for controller connectivity and retry scenarios."""

    @pytest.mark.asyncio
    async def test_controller_unreachable_grant_remains_pending(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test grant creation when controller is unreachable - should remain in pending state."""
        # Mock controller to simulate network failure
        with patch(
            "src.controllers.omada.OmadaController.provision_grant"
        ) as mock_provision:
            # Simulate connection timeout
            mock_provision.side_effect = httpx.ConnectTimeout("Connection timeout")

            grant_request = {
                "booking_id": "unreachable_test_001",
                "start_time": "2024-12-01T15:00:00Z",  # Past time - would normally activate
                "end_time": "2025-01-15T18:00:00Z",
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
            assert mock_provision.call_count >= 1

    @pytest.mark.asyncio
    async def test_controller_retry_with_backoff(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test retry mechanism with exponential backoff when controller fails."""
        call_times = []

        def track_call_time(*args, **kwargs):
            """Mock function that tracks call times to verify backoff behavior."""
            import time

            call_times.append(time.time())
            raise httpx.ConnectTimeout("Simulated failure")

        with patch(
            "src.controllers.omada.OmadaController.provision_grant"
        ) as mock_provision:
            mock_provision.side_effect = track_call_time

            grant_request = {
                "booking_id": "retry_test_001",
                "start_time": "2024-12-01T15:00:00Z",
                "end_time": "2025-01-15T18:00:00Z",
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
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test grant activation when controller becomes available after being unreachable."""
        # Track call attempts
        call_count = 0

        def mock_provision_with_recovery(*args, **kwargs):
            """Mock function that fails twice then succeeds to simulate recovery."""
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # First 2 attempts fail
                raise httpx.ConnectTimeout("Controller unreachable")
            else:
                # Third attempt succeeds
                return {
                    "status": "success",
                    "voucher_id": "recovered_voucher_123",
                    "message": "Grant provisioned successfully",
                }

        with patch(
            "src.controllers.omada.OmadaController.provision_grant"
        ) as mock_provision:
            mock_provision.side_effect = mock_provision_with_recovery

            grant_request = {
                "booking_id": "recovery_test_001",
                "start_time": "2024-12-01T15:00:00Z",  # Past time
                "end_time": "2025-01-15T18:00:00Z",
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
            get_response = test_client.get(
                f"/api/grants/{grant_id}", headers=auth_headers
            )
            assert get_response.status_code == 200

            final_grant = get_response.json()
            assert final_grant["status"] == "active", (
                "Grant should activate after controller recovery"
            )
            assert "controller_voucher_id" in final_grant

    @pytest.mark.asyncio
    async def test_controller_permanent_failure_handling(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test handling of grants when controller remains permanently unreachable."""
        with patch(
            "src.controllers.omada.OmadaController.provision_grant"
        ) as mock_provision:
            # Simulate permanent failure
            mock_provision.side_effect = httpx.ConnectTimeout("Permanent failure")

            grant_request = {
                "booking_id": "permanent_failure_001",
                "start_time": "2024-12-01T15:00:00Z",
                "end_time": "2025-01-15T18:00:00Z",
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
            get_response = test_client.get(
                f"/api/grants/{grant_id}", headers=auth_headers
            )
            assert get_response.status_code == 200

            grant_data = get_response.json()
            assert grant_data["status"] == "pending"
            assert "last_error" in grant_data
            assert "retry_count" in grant_data

    @pytest.mark.asyncio
    async def test_health_endpoint_controller_status(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test health endpoint reflects controller connectivity status."""
        # Test with healthy controller
        with patch("src.controllers.omada.OmadaController.health_check") as mock_health:
            mock_health.return_value = {"status": "healthy", "response_time": 50}

            response = test_client.get("/health", headers=auth_headers)
            assert response.status_code == 200

            health_data = response.json()
            assert health_data["status"] == "healthy"
            assert "controller" in health_data
            assert health_data["controller"]["status"] == "healthy"

        # Test with unhealthy controller
        with patch("src.controllers.omada.OmadaController.health_check") as mock_health:
            mock_health.side_effect = httpx.ConnectTimeout("Controller unreachable")

            response = test_client.get("/health", headers=auth_headers)
            assert response.status_code == 503  # Service Unavailable

            health_data = response.json()
            assert health_data["status"] == "degraded"
            assert health_data["controller"]["status"] == "unreachable"

    @pytest.mark.asyncio
    async def test_metrics_include_controller_failures(
        self, test_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that controller failure metrics are tracked and exposed."""
        with patch(
            "src.controllers.omada.OmadaController.provision_grant"
        ) as mock_provision:
            mock_provision.side_effect = httpx.ConnectTimeout("Metrics test failure")

            # Create a grant that will fail
            grant_request = {
                "booking_id": "metrics_failure_001",
                "start_time": "2024-12-01T15:00:00Z",
                "end_time": "2025-01-15T18:00:00Z",
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
            metrics_response = test_client.get("/metrics", headers=auth_headers)
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
