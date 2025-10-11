# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Performance test for portal page rendering."""

import time
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.portal import router as portal_router
from src.services.theme_manager import ThemeManager


@pytest.fixture
def mock_storage() -> None:
    """Create a mock storage layer."""
    storage = AsyncMock()
    storage.validate_credential = AsyncMock(return_value=False)
    return storage


@pytest.fixture
def mock_audit() -> None:
    """Create a mock audit logger."""
    audit = AsyncMock()
    audit.log_event = AsyncMock()
    return audit


@pytest.fixture
def theme_manager(tmp_path) -> None:
    """Create a theme manager with test themes."""
    # Create a simple test theme
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    default_theme = theme_dir / "default"
    default_theme.mkdir()

    # Create minimal template
    template_content = """
    <!DOCTYPE html>
    <html>
    <head><title>{{ title }}</title></head>
    <body>
        <h1>{{ welcome_message }}</h1>
        <form method="post">
            <input type="text" name="credential" />
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """
    (default_theme / "login.html").write_text(template_content.strip())

    # ThemeManager now uses singleton pattern, no constructor parameters
    return ThemeManager()


@pytest.fixture
def test_app(theme_manager, mock_storage, mock_audit) -> None:
    """Create a test FastAPI app with portal router."""
    app = FastAPI()
    # The router is already configured, just include it
    app.include_router(portal_router.router)
    return app


def test_portal_page_render_performance(test_app) -> None:
    """Test that portal page renders within <300ms p95 (FR-007/FR-009)."""
    client = TestClient(test_app)
    latencies = []
    iterations = 100

    # Warm up template cache
    for _ in range(5):
        client.get("/portal/splash")

    # Measure rendering performance
    for _ in range(iterations):
        start = time.time()
        response = client.get("/portal/splash")
        latency = (time.time() - start) * 1000  # Convert to milliseconds
        latencies.append(latency)

        # Verify successful render
        assert response.status_code == 200
        assert b"Welcome to Guest Network" in response.content

    # Calculate p95 latency
    latencies.sort()
    p95_index = int(len(latencies) * 0.95)
    p95_latency = latencies[p95_index]

    # Assert p95 < 300ms per spec
    assert p95_latency < 300, (
        f"P95 render latency {p95_latency:.1f}ms exceeds 300ms threshold"
    )

    # Additional metrics
    mean_latency = sum(latencies) / len(latencies)
    assert mean_latency < 100, f"Mean latency {mean_latency:.1f}ms is unexpectedly high"


def test_portal_form_submission_performance(test_app) -> None:
    """Test that form submission processing is performant."""
    client = TestClient(test_app)
    latencies = []
    iterations = 50

    # Measure form submission performance
    for i in range(iterations):
        start = time.time()
        response = client.post("/portal/splash", data={"credential": f"test-cred-{i}"})
        latency = (time.time() - start) * 1000
        latencies.append(latency)

        # Should get redirect or error page
        assert response.status_code in [200, 302, 303]

    # Calculate p95
    latencies.sort()
    p95_index = int(len(latencies) * 0.95)
    p95_latency = latencies[p95_index]

    # Form submission should be fast
    assert p95_latency < 500, (
        f"P95 submission latency {p95_latency:.1f}ms exceeds 500ms"
    )


def test_portal_concurrent_render_performance(test_app) -> None:
    """Test portal page rendering under concurrent load."""
    import concurrent.futures

    client = TestClient(test_app)
    concurrent_users = 10
    requests_per_user = 10

    def make_requests() -> None:
        """Make multiple requests."""
        latencies = []
        for _ in range(requests_per_user):
            start = time.time()
            response = client.get("/portal/splash")
            latency = (time.time() - start) * 1000
            latencies.append(latency)
            assert response.status_code == 200
        return latencies

    # Execute concurrent requests
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrent_users
    ) as executor:
        futures = [executor.submit(make_requests) for _ in range(concurrent_users)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Flatten all latencies
    all_latencies = [lat for user_lats in results for lat in user_lats]
    all_latencies.sort()

    # Calculate p95
    p95_index = int(len(all_latencies) * 0.95)
    p95_latency = all_latencies[p95_index]

    # Under concurrent load, allow slightly higher latency but still reasonable
    assert p95_latency < 500, (
        f"P95 concurrent latency {p95_latency:.1f}ms exceeds 500ms threshold"
    )
