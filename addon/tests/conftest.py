# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Shared test configuration and fixtures."""

import asyncio
import os
import tempfile
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.controllers.base import ProvisionResult
from src.core.config import AddonConfig, ControllerConfig, ThemeConfig


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Set up a test database path for all tests automatically."""
    # Create a temporary database file for the entire test session
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Set the environment variable
    os.environ["DB_PATH"] = db_path

    # Initialize database tables
    import asyncio

    from src.storage.database import initialize_database

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_database())
    loop.close()

    yield db_path

    # Cleanup
    if "DB_PATH" in os.environ:
        del os.environ["DB_PATH"]
    if os.path.exists(db_path):
        os.remove(db_path)


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

    # Return ProvisionResult objects instead of dicts
    controller.provision_grant = AsyncMock(
        return_value=ProvisionResult(
            success=True,
            controller_voucher_id="test_voucher_123",
            message="Provisioned successfully",
        )
    )

    controller.revoke_grant = AsyncMock(
        return_value=ProvisionResult(
            success=True,
            message="Revoked successfully",
        )
    )

    controller.extend_grant = AsyncMock(
        return_value=ProvisionResult(
            success=True,
            controller_voucher_id="test_voucher_123",
            message="Extended successfully",
        )
    )

    return controller


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Provide authentication headers for admin API tests.

    Returns headers with Bearer token for authenticated requests.
    """
    return {"Authorization": "Bearer test_api_key_12345"}


@pytest.fixture
def test_client(
    test_config: AddonConfig, temp_database: str, mock_controller: MagicMock
) -> Generator[TestClient]:
    """Provide FastAPI test client with actual app."""
    # Set global config for tests
    import src.core.config as config_module
    import src.storage.database as db_module

    config_module.config = test_config

    # Set up test database path
    os.environ["DB_PATH"] = temp_database

    # Set up test authentication - use API key mode for tests
    os.environ["CAPTIVE_PORTAL_API_KEY"] = "test_api_key_12345"

    # Reset database manager to pick up new DB_PATH
    db_module._db_manager = None

    # Patch the controller factory to return our mock controller
    with patch("src.controllers.factory.get_controller", return_value=mock_controller):
        # Create the FastAPI app
        app = create_app()

        # Create test client
        with TestClient(app) as client:
            yield client

    # Cleanup: reset config and database manager after test
    config_module.config = None
    db_module._db_manager = None
    if "DB_PATH" in os.environ:
        del os.environ["DB_PATH"]
    if "CAPTIVE_PORTAL_API_KEY" in os.environ:
        del os.environ["CAPTIVE_PORTAL_API_KEY"]
