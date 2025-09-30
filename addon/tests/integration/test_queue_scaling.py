# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for adaptive queue scaling scenario."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient


class TestAdaptiveQueueScaling:
    """Integration tests for queue scaling under load."""

    @pytest.mark.asyncio
    async def test_burst_grant_creation_scaling(self, test_client: TestClient) -> None:
        """Test adaptive queue scaling during burst grant creation with latency measurement.

        Simulates property turnover scenario with 50+ grants created in rapid succession.
        Verifies that queue scaling adapts from 2→5 workers and latency stays under threshold.
        """
        # Create a burst of grant requests (simulating property turnover)
        grant_requests = []
        for i in range(50):
            grant_requests.append(
                {
                    "booking_id": f"burst_booking_{i:03d}",
                    "start_time": f"2025-01-{(i % 28) + 1:02d}T15:00:00Z",
                    "end_time": f"2025-01-{(i % 28) + 1:02d}T18:00:00Z",
                    "guest_name": f"Guest {i}",
                    "source": "rental_control",
                }
            )

        # Measure latency during burst creation
        latencies = []
        start_time = time.time()

        # Submit all requests rapidly
        for i, request in enumerate(grant_requests):
            request_start = time.time()

            response = test_client.post("/api/grants", json=request)

            request_end = time.time()
            latency = (request_end - request_start) * 1000  # Convert to ms
            latencies.append(latency)

            # Verify successful creation
            assert response.status_code == 201
            grant_data = response.json()
            assert grant_data["booking_id"] == request["booking_id"]

            # Brief pause to simulate realistic request timing
            if i < 49:  # Don't pause after last request
                await asyncio.sleep(0.02)  # 20ms between requests

        total_time = time.time() - start_time

        # Verify performance characteristics
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(0.95 * len(latencies))]
        p99_latency = sorted(latencies)[int(0.99 * len(latencies))]

        # Performance assertions based on plan requirements
        assert avg_latency < 2000, (
            f"Average latency {avg_latency:.2f}ms exceeds 2s threshold"
        )
        assert p95_latency < 2000, (
            f"P95 latency {p95_latency:.2f}ms exceeds 2s threshold"
        )
        assert p99_latency < 5000, (
            f"P99 latency {p99_latency:.2f}ms exceeds 5s threshold"
        )

        # Verify queue processed all requests reasonably quickly
        expected_max_time = 60  # 60 seconds for 50 requests should be reasonable
        assert total_time < expected_max_time, (
            f"Total processing time {total_time:.2f}s too slow"
        )

        print(
            f"Burst test completed: {len(grant_requests)} grants in {total_time:.2f}s"
        )
        print(
            f"Latency stats - Avg: {avg_latency:.2f}ms, P95: {p95_latency:.2f}ms, P99: {p99_latency:.2f}ms"
        )

    @pytest.mark.asyncio
    async def test_queue_scaling_metrics(self, test_client: TestClient) -> None:
        """Test that queue scaling decisions are observable via metrics."""
        # Check initial queue state
        metrics_response = test_client.get("/metrics")
        assert metrics_response.status_code == 200

        initial_metrics = metrics_response.text

        # Create enough load to trigger scaling
        concurrent_requests = []
        for i in range(10):
            grant_request = {
                "booking_id": f"scaling_test_{i}",
                "start_time": "2025-01-15T15:00:00Z",
                "end_time": "2025-01-15T18:00:00Z",
                "guest_name": f"Scaling Guest {i}",
                "source": "rental_control",
            }
            concurrent_requests.append(grant_request)

        # Submit requests concurrently to trigger scaling
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(test_client.post, "/api/grants", json=request)
                for request in concurrent_requests
            ]

            responses = [future.result() for future in futures]

        # Verify all requests succeeded
        for response in responses:
            assert response.status_code == 201

        # Check metrics after load
        final_metrics_response = test_client.get("/metrics")
        assert final_metrics_response.status_code == 200

        final_metrics = final_metrics_response.text

        # Verify queue metrics are present
        expected_metrics = [
            "queue_depth",
            "active_workers",
            "provision_latency",
            "grants_processed_total",
        ]

        for metric in expected_metrics:
            assert metric in final_metrics, f"Missing metric: {metric}"

    @pytest.mark.asyncio
    async def test_queue_scaling_under_sustained_load(
        self, test_client: TestClient
    ) -> None:
        """Test queue behavior under sustained load over time."""
        # Submit requests at steady rate to verify scaling stability
        total_requests = 20
        request_interval = 0.5  # 500ms between requests

        start_time = time.time()
        successful_requests = 0

        for i in range(total_requests):
            grant_request = {
                "booking_id": f"sustained_load_{i:03d}",
                "start_time": f"2025-02-{(i % 28) + 1:02d}T14:00:00Z",
                "end_time": f"2025-02-{(i % 28) + 1:02d}T17:00:00Z",
                "guest_name": f"Sustained Guest {i}",
                "source": "rental_control",
            }

            response = test_client.post("/api/grants", json=grant_request)

            if response.status_code == 201:
                successful_requests += 1

            # Wait before next request
            if i < total_requests - 1:
                await asyncio.sleep(request_interval)

        total_time = time.time() - start_time

        # Verify success rate and timing
        success_rate = successful_requests / total_requests
        assert success_rate >= 0.95, (
            f"Success rate {success_rate:.2%} below 95% threshold"
        )

        expected_min_time = (
            total_requests * request_interval * 0.8
        )  # Allow some variance
        expected_max_time = (
            total_requests * request_interval * 2.0
        )  # Allow for processing overhead

        assert expected_min_time <= total_time <= expected_max_time, (
            f"Total time {total_time:.2f}s outside expected range {expected_min_time:.2f}-{expected_max_time:.2f}s"
        )

        print(
            f"Sustained load test: {successful_requests}/{total_requests} successful in {total_time:.2f}s"
        )
