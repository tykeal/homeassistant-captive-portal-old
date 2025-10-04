# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for metrics assertion (FR-020 observability)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.health import router


@pytest.fixture
def mock_grant_manager():
    """Create a mock grant manager."""
    manager = AsyncMock()
    manager.get_stats = AsyncMock(
        return_value={
            "total": 100,
            "current_active": 45,
            "pending": 5,
            "expired": 30,
            "revoked": 20,
        }
    )
    return manager


@pytest.fixture
def mock_queued_operations():
    """Create a mock queued operations service."""
    ops = AsyncMock()
    ops.get_queue_health = AsyncMock(
        return_value={
            "queue_depth": 12,
            "active_workers": 3,
            "max_workers": 5,
            "processing_rate": 8.5,
        }
    )
    return ops


@pytest.fixture
def test_app(mock_grant_manager, mock_queued_operations):
    """Create a test FastAPI app with health/metrics router."""
    from fastapi import FastAPI

    app = FastAPI()

    # Patch the global getters to return our mocks
    with patch(
        "src.services.grant_manager.get_grant_manager", return_value=mock_grant_manager
    ):
        with patch(
            "src.services.queue_integration.get_queued_operations",
            return_value=mock_queued_operations,
        ):
            app.include_router(router)

    return app


def test_metrics_endpoint_exists(test_app):
    """Test that /api/metrics endpoint exists."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 0,
                    "current_active": 0,
                    "pending": 0,
                    "expired": 0,
                    "revoked": 0,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 0,
                    "active_workers": 0,
                    "max_workers": 5,
                    "processing_rate": 0,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200


def test_metrics_exports_active_grants(test_app):
    """Test that active_grants metric is exported."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()

            assert "metrics" in data
            metrics_text = data["metrics"]

            # Check for active grants metric
            assert "captive_portal_grants_active 45" in metrics_text


def test_metrics_exports_queue_depth(test_app):
    """Test that queue_depth metric is exported."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()

            metrics_text = data["metrics"]

            # Check for queue depth metric
            assert "captive_portal_queue_depth 12" in metrics_text


def test_metrics_exports_provision_latency_placeholder(test_app):
    """Test that provision latency metric structure is present.

    Note: This tests the metric export structure. Actual latency tracking
    would be implemented in the grant manager or queue scheduler.
    """
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 0,
                    "current_active": 0,
                    "pending": 0,
                    "expired": 0,
                    "revoked": 0,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 0,
                    "active_workers": 0,
                    "max_workers": 5,
                    "processing_rate": 0,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()

            # Verify we have a metrics response
            assert "metrics" in data
            # For now, just verify the endpoint works
            # TODO: Add provision_latency metric to grant_manager


def test_metrics_exports_all_grant_states(test_app):
    """Test that all grant state metrics are exported."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()
            metrics_text = data["metrics"]

            # Check all grant state metrics
            assert "captive_portal_grants_total 100" in metrics_text
            assert "captive_portal_grants_active 45" in metrics_text
            assert "captive_portal_grants_pending 5" in metrics_text
            assert "captive_portal_grants_expired 30" in metrics_text
            assert "captive_portal_grants_revoked 20" in metrics_text


def test_metrics_exports_queue_workers(test_app):
    """Test that queue worker count is exported."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()
            metrics_text = data["metrics"]

            # Check queue workers metric
            assert "captive_portal_queue_workers 3" in metrics_text


def test_metrics_format_prometheus_compatible(test_app):
    """Test that metrics format is Prometheus-compatible."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            assert response.status_code == 200
            data = response.json()
            metrics_text = data["metrics"]

            # Verify basic Prometheus format: metric_name value
            lines = metrics_text.strip().split("\n")
            assert len(lines) > 0

            for line in lines:
                parts = line.split()
                assert len(parts) == 2, f"Invalid metric format: {line}"

                metric_name, metric_value = parts

                # Metric name should start with captive_portal_
                assert metric_name.startswith("captive_portal_")

                # Value should be numeric
                assert metric_value.replace(".", "").replace("-", "").isdigit()


def test_metrics_handles_errors_gracefully(test_app):
    """Test that metrics endpoint handles errors gracefully."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            # Make grant_manager.get_stats raise an error
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 0,
                    "active_workers": 0,
                    "max_workers": 5,
                    "processing_rate": 0,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/metrics")

            # Should still return 200 with error info
            assert response.status_code == 200
            data = response.json()

            assert "error" in data or "metrics" in data


def test_health_endpoint_includes_metrics(test_app):
    """Test that health endpoint includes key metrics."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 100,
                    "current_active": 45,
                    "pending": 5,
                    "expired": 30,
                    "revoked": 20,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 12,
                    "active_workers": 3,
                    "max_workers": 5,
                    "processing_rate": 8.5,
                }
            )

            client = TestClient(test_app)
            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()

            # Verify metrics are included in health response
            assert data["queue_depth"] == 12
            assert data["details"]["active_grants"] == 45
            assert data["details"]["pending_grants"] == 5
            assert data["details"]["queue_metrics"]["queue_depth"] == 12


@pytest.mark.asyncio
async def test_metrics_real_time_updates():
    """Test that metrics reflect real-time changes."""
    from fastapi import FastAPI

    app = FastAPI()

    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        with patch("src.services.queue_integration.get_queued_operations") as mock_qo:
            # Initial state
            mock_gm.return_value = AsyncMock()
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 10,
                    "current_active": 5,
                    "pending": 2,
                    "expired": 3,
                    "revoked": 0,
                }
            )
            mock_qo.return_value = AsyncMock()
            mock_qo.return_value.get_queue_health = AsyncMock(
                return_value={
                    "queue_depth": 5,
                    "active_workers": 2,
                    "max_workers": 5,
                    "processing_rate": 1.5,
                }
            )

            app.include_router(router)
            client = TestClient(app)

            response1 = client.get("/api/metrics")
            assert "captive_portal_grants_active 5" in response1.json()["metrics"]

            # Simulate state change
            mock_gm.return_value.get_stats = AsyncMock(
                return_value={
                    "total": 12,
                    "current_active": 7,
                    "pending": 1,
                    "expired": 4,
                    "revoked": 0,
                }
            )

            response2 = client.get("/api/metrics")
            assert "captive_portal_grants_active 7" in response2.json()["metrics"]
