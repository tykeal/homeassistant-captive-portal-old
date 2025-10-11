# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

# Test Suite Documentation

This document provides comprehensive guidance on the test suite structure, fixtures, authentication patterns, and common testing practices for the Captive Portal addon.

## Table of Contents

- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Fixtures](#test-fixtures)
- [Authentication](#authentication)
- [Database Setup](#database-setup)
- [Common Patterns](#common-patterns)
- [Troubleshooting](#troubleshooting)

## Test Structure

The test suite is organized into four categories:

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── contract/                # API contract tests
│   ├── test_audit_api.py
│   ├── test_grants_api.py
│   ├── test_theme_api.py
│   └── test_vouchers_api.py
├── integration/             # Integration tests
│   ├── test_auth_security.py
│   ├── test_graceful_shutdown.py
│   ├── test_portal_scenarios.py
│   └── ...
├── unit/                    # Unit tests
│   ├── test_grant_manager.py
│   ├── test_metrics_export.py
│   ├── test_queue_scaling.py
│   └── ...
└── performance/             # Performance tests
    ├── test_burst_provisioning.py
    └── test_portal_render.py
```

### Test Categories

- **Contract Tests**: Verify API endpoints match their specifications
- **Integration Tests**: Test component interactions and workflows
- **Unit Tests**: Test individual components in isolation
- **Performance Tests**: Verify performance requirements (latency, throughput)

## Running Tests

### Run All Tests

```bash
cd addon
.venv/bin/pytest
```

### Run Specific Test Categories

```bash
# Contract tests only
.venv/bin/pytest tests/contract/

# Integration tests
.venv/bin/pytest tests/integration/

# Unit tests
.venv/bin/pytest tests/unit/

# Performance tests
.venv/bin/pytest tests/performance/
```

### Run Specific Test File

```bash
.venv/bin/pytest tests/contract/test_grants_api.py
```

### Run Specific Test

```bash
.venv/bin/pytest tests/contract/test_grants_api.py::TestGrantsAPI::test_post_grants_provision_from_rental_control
```

### Run with Coverage

```bash
.venv/bin/pytest --cov=src --cov-report=term-missing
```

### Run with Verbose Output

```bash
.venv/bin/pytest -v
.venv/bin/pytest -vv  # Extra verbose
```

## Test Fixtures

### Global Fixtures (conftest.py)

#### `setup_test_database` (session, autouse)

Automatically creates and initializes a temporary database for all tests.

```python
# This fixture runs automatically - no need to explicitly use it
# Database is created once per test session
```

#### `test_config`

Provides a test configuration for the addon.

```python
def test_example(test_config):
    assert test_config.controller.type == "omada"
```

#### `temp_database`

Provides a temporary database file path (per-test).

```python
def test_example(temp_database):
    # temp_database is a file path string
    assert os.path.exists(temp_database)
```

#### `auth_headers`

Provides authentication headers for admin API tests.

```python
def test_example(test_client, auth_headers):
    response = test_client.post("/api/grants", json=data, headers=auth_headers)
    assert response.status_code == 201
```

#### `test_client`

Provides a FastAPI TestClient with the full application.

```python
def test_example(test_client):
    response = test_client.get("/api/health")
    assert response.status_code == 200
```

#### `mock_controller`

Provides a mocked controller adapter.

```python
def test_example(mock_controller):
    mock_controller.provision_grant.return_value = {"status": "success"}
```

## Authentication

### Admin API Endpoints

Most admin API endpoints (`/api/grants`, `/api/theme`, `/api/audit`, etc.) require authentication. Tests must include authentication headers.

#### Pattern for Authenticated Requests

```python
@pytest.mark.asyncio
async def test_authenticated_endpoint(test_client, auth_headers):
    """Test an endpoint that requires authentication."""
    response = test_client.post(
        "/api/grants",
        json={"booking_id": "test", ...},
        headers=auth_headers  # Always include for admin endpoints
    )
    assert response.status_code == 201  # Not 401
```

#### Authentication Modes

The test suite uses **API Key authentication** mode:

- Environment variable: `CAPTIVE_PORTAL_API_KEY=test_api_key_12345`
- Header format: `Authorization: Bearer test_api_key_12345`
- Automatically set by `test_client` fixture

### Portal Endpoints (No Auth Required)

Portal endpoints (`/portal/*`) do not require authentication:

```python
def test_portal_endpoint(test_client):
    """Portal endpoints don't need auth headers."""
    response = test_client.get("/portal/login")
    assert response.status_code == 200
```

## Database Setup

### Automatic Database Initialization

The test suite automatically:

1. Creates a temporary SQLite database file
2. Sets the `DB_PATH` environment variable
3. Initializes all database tables
4. Cleans up after test session completes

### Database in Tests

```python
# Database is automatically available - no setup needed!

async def test_database_operation(test_client, auth_headers):
    # Create a grant
    response = test_client.post("/api/grants", json={...}, headers=auth_headers)

    # It's persisted in the test database
    assert response.status_code == 201

    # Can retrieve it
    grant_id = response.json()["grant_id"]
    response = test_client.get(f"/api/grants/{grant_id}", headers=auth_headers)
    assert response.status_code == 200
```

### In-Memory vs File Database

- Session-scoped fixture uses a temporary **file-based** database
- Shared across all tests in a session
- Automatically cleaned up

## Common Patterns

### Testing API Endpoints

```python
@pytest.mark.asyncio
async def test_api_endpoint(test_client, auth_headers):
    """Standard API endpoint test pattern."""
    # 1. Prepare request data
    request_data = {
        "booking_id": "test_123",
        "start_time": "2025-01-01T10:00:00Z",
        # ... other fields
    }

    # 2. Make request with auth headers
    response = test_client.post(
        "/api/grants",
        json=request_data,
        headers=auth_headers
    )

    # 3. Assert response status
    assert response.status_code == 201

    # 4. Assert response data
    data = response.json()
    assert data["booking_id"] == "test_123"
    assert "grant_id" in data
```

### Testing Async Queue Operations

```python
@pytest.mark.asyncio
async def test_queue_operation(queue_scheduler):
    """Pattern for testing queue scheduler."""
    async def task():
        await asyncio.sleep(0.01)
        return "done"

    # Submit task
    await queue_scheduler.submit(task)

    # Check queue health
    health = queue_scheduler.get_queue_health()
    assert health["active_workers"] >= 1
```

### Testing Error Handling

```python
@pytest.mark.asyncio
async def test_error_handling(test_client, auth_headers):
    """Pattern for testing validation errors."""
    # Invalid request (missing required fields)
    invalid_data = {"booking_id": "test"}

    response = test_client.post(
        "/api/grants",
        json=invalid_data,
        headers=auth_headers
    )

    # Should return 422 validation error
    assert response.status_code == 422
    error = response.json()
    assert "detail" in error
```

### Mocking Dependencies

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mocks():
    """Pattern for mocking dependencies."""
    with patch("src.services.grant_manager.get_grant_manager") as mock_gm:
        mock_gm.return_value = AsyncMock()
        mock_gm.return_value.get_stats = AsyncMock(
            return_value={"total": 100, "active": 50}
        )

        # Test code using the mock
        # ...
```

## Troubleshooting

### Common Issues

#### 401 Unauthorized Errors

**Problem**: Test gets 401 instead of expected status code.

**Solution**: Add `auth_headers` parameter and include headers in request:

```python
# Before (fails with 401)
def test_example(test_client):
    response = test_client.post("/api/grants", json=data)

# After (works)
def test_example(test_client, auth_headers):
    response = test_client.post("/api/grants", json=data, headers=auth_headers)
```

#### Database Errors

**Problem**: `sqlite3.OperationalError: unable to open database file`

**Solution**: The session-scoped database fixture should handle this automatically. If you see this error:

1. Ensure you're using pytest (not running tests directly)
2. Check that `conftest.py` is in the tests directory
3. Verify the `setup_test_database` fixture is being loaded

#### Import Errors

**Problem**: Cannot import modules from `src.*`

**Solution**: Ensure you're running tests from the `addon/` directory:

```bash
cd addon
.venv/bin/pytest
```

#### Async/Await Issues

**Problem**: `RuntimeWarning: coroutine was never awaited`

**Solution**: Ensure you await all async calls:

```python
# Wrong
scheduler.submit(task)  # Returns coroutine, never awaited

# Correct
await scheduler.submit(task)  # Properly awaited

# Or for multiple
await asyncio.gather(*[scheduler.submit(task) for _ in range(10)])
```

#### Queue Scheduler API

**Problem**: `AttributeError: 'AdaptiveQueueScheduler' object has no attribute 'submit'`

**Solution**: The compatibility method `submit()` exists. Check:

1. Using the correct queue scheduler instance
2. Properly awaiting the call
3. Not using an old/cached version

#### Test Isolation Issues

**Problem**: Tests pass individually but fail when run together.

**Solution**: Ensure tests clean up properly:

```python
@pytest.fixture
async def my_resource():
    resource = await create_resource()
    yield resource
    await resource.cleanup()  # Cleanup after test
```

### Debugging Tests

#### Print Debug Info

```python
def test_debug(test_client):
    response = test_client.get("/api/health")
    print(f"Status: {response.status_code}")
    print(f"Body: {response.json()}")
    assert False  # Force test to fail and show output
```

#### Run Single Test with Full Output

```bash
.venv/bin/pytest tests/contract/test_grants_api.py::test_specific -xvs
# -x: stop on first failure
# -v: verbose
# -s: show print statements
```

#### Check Test Coverage

```bash
# Generate HTML coverage report
.venv/bin/pytest --cov=src --cov-report=html
open htmlcov/index.html  # View in browser
```

## Best Practices

1. **Always use fixtures**: Don't create resources manually - use or create fixtures
2. **Clean up**: Ensure tests clean up resources (fixtures handle this automatically)
3. **Test isolation**: Each test should be independent and not rely on other tests
4. **Use auth headers**: Admin API tests always need authentication
5. **Async patterns**: Always await async functions, use `asyncio.gather()` for multiple
6. **Mock external services**: Don't make real network calls in tests
7. **Meaningful assertions**: Test specific behavior, not just status codes
8. **Document complex tests**: Add docstrings explaining what the test verifies

## Performance Testing

Performance tests verify that the system meets latency and throughput requirements.

### Running Performance Tests

```bash
# Run all performance tests
.venv/bin/pytest tests/performance/

# Run specific performance test
.venv/bin/pytest tests/performance/test_burst_provisioning.py -v
```

### Performance Requirements

- **Burst provisioning**: p95 latency < 2s for 50 concurrent grants
- **Portal rendering**: p95 latency < 300ms
- **Queue throughput**: > 10 grants/second

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- Project specification: `specs/001-create-captive-portal/spec.md`
- Implementation plan: `specs/001-create-captive-portal/plan.md`
