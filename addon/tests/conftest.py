# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Shared test configuration and fixtures."""

import asyncio
import tempfile
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.core.config import AddonConfig, ControllerConfig, ThemeConfig


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config() -> AddonConfig:
    """Provide test configuration."""
    return AddonConfig(
        controller=ControllerConfig(
            type="omada",
            url="https://192.168.1.1:8443",
            username="admin",
            password="testpass",
            site_name="Default",
        ),
        theme=ThemeConfig(
            portal_title="Test Portal",
            background_color="#ffffff",
            primary_color="#000000",
        ),
        log_level="debug",
    )


@pytest.fixture
def temp_database() -> Generator[str]:
    """Provide temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def mock_controller() -> MagicMock:
    """Provide mock controller for testing."""
    controller = MagicMock()
    controller.provision_grant.return_value = {
        "status": "success",
        "voucher_id": "test123",
    }
    controller.revoke_grant.return_value = {"status": "success"}
    controller.extend_grant.return_value = {"status": "success"}
    return controller


@pytest.fixture
def test_client(test_config: AddonConfig) -> Generator[TestClient]:
    """Provide FastAPI test client with actual app."""
    # Create the FastAPI app
    app = create_app()

    # Create test client
    with TestClient(app) as client:
        yield client
