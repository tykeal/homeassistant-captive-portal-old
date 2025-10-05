# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

# Controller Adapter Extension Guide

This guide explains how to add support for new network controller types to the Captive Portal addon. The pluggable architecture allows adding new controllers without modifying core logic.

## Architecture Overview

The addon uses an adapter pattern to support multiple controller backends:

```
┌─────────────────┐
│  Grant Manager  │ (core logic)
└────────┬────────┘
         │ uses
         ▼
┌─────────────────┐
│ BaseController  │ (abstract interface)
└────────┬────────┘
         │ implements
    ┌────┴────────────┐
    ▼                 ▼
┌──────────┐    ┌──────────┐
│  Omada   │    │  UniFi   │ (example)
│ Adapter  │    │ Adapter  │
└──────────┘    └──────────┘
```

**Key Files**:
- `src/controllers/base.py` - Abstract base class defining the controller interface
- `src/controllers/omada.py` - TP-Omada implementation (reference)
- `src/core/config.py` - Controller configuration loading

## Step-by-Step: Adding a New Adapter

### 1. Review the Base Controller Interface

First, understand the required methods by examining `BaseController`:

```python
# src/controllers/base.py
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

class BaseController(ABC):
    """Abstract base for network controller adapters."""

    @abstractmethod
    async def provision_grant(
        self,
        username: str,
        password: str,
        start_at: datetime,
        end_at: datetime,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Provision network access grant on the controller.

        Args:
            username: Client identifier (may be used as voucher code)
            password: Authentication credential
            start_at: Access validity start time
            end_at: Access validity end time
            metadata: Optional controller-specific parameters

        Returns:
            Controller-generated reference ID (for tracking/revocation)

        Raises:
            ProvisionError: If provisioning fails
            ControllerUnreachableError: If controller API is unavailable
        """
        pass

    @abstractmethod
    async def revoke_grant(self, controller_ref: str) -> None:
        """
        Revoke an active grant on the controller.

        Args:
            controller_ref: The reference ID returned by provision_grant

        Raises:
            RevocationError: If revocation fails
            ControllerUnreachableError: If controller API is unavailable
        """
        pass

    @abstractmethod
    async def extend_grant(
        self,
        controller_ref: str,
        new_end_at: datetime
    ) -> None:
        """
        Extend the expiration time of an existing grant.

        Args:
            controller_ref: The reference ID from provision_grant
            new_end_at: Updated expiration timestamp

        Raises:
            ExtensionError: If extension fails
            ControllerUnreachableError: If controller API is unavailable
        """
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """
        Check controller connectivity and status.

        Returns:
            dict with keys:
                - healthy: bool
                - latency_ms: Optional[float]
                - details: Optional[str] (error message if unhealthy)
        """
        pass
```

### 2. Create Your Adapter File

Create a new file for your adapter in `src/controllers/`:

```bash
# Example: Adding UniFi controller support
touch src/controllers/unifi.py
```

### 3. Implement the Adapter Class

Use the Omada adapter as a reference template:

```python
# src/controllers/unifi.py
"""UniFi Controller adapter for network access provisioning."""

import logging
from datetime import datetime
from typing import Optional

import httpx

from .base import (
    BaseController,
    ProvisionError,
    RevocationError,
    ExtensionError,
    ControllerUnreachableError,
)

logger = logging.getLogger(__name__)


class UniFiAdapter(BaseController):
    """UniFi controller adapter using UniFi API."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        site: str = "default",
        verify_ssl: bool = True,
    ):
        """
        Initialize UniFi controller adapter.

        Args:
            url: UniFi controller base URL (e.g., https://192.168.1.1:8443)
            username: Admin username
            password: Admin password
            site: Site name (default: "default")
            verify_ssl: Whether to verify SSL certificates
        """
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self._session: Optional[httpx.AsyncClient] = None
        self._auth_cookie: Optional[str] = None

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session with authentication."""
        if self._session is None:
            self._session = httpx.AsyncClient(verify=self.verify_ssl, timeout=10.0)

        # Authenticate if no cookie or cookie expired
        if self._auth_cookie is None:
            await self._authenticate()

        return self._session

    async def _authenticate(self) -> None:
        """Authenticate with UniFi controller and obtain session cookie."""
        try:
            response = await self._session.post(
                f"{self.url}/api/login",
                json={"username": self.username, "password": self.password},
            )
            response.raise_for_status()

            # Extract session cookie (UniFi uses unifises cookie)
            self._auth_cookie = response.cookies.get("unifises")

            if not self._auth_cookie:
                raise ProvisionError("Authentication failed: no session cookie received")

            logger.info("UniFi controller authenticated successfully")

        except httpx.RequestError as e:
            raise ControllerUnreachableError(f"UniFi controller unreachable: {e}")
        except httpx.HTTPStatusError as e:
            raise ProvisionError(f"UniFi authentication failed: {e}")

    async def provision_grant(
        self,
        username: str,
        password: str,
        start_at: datetime,
        end_at: datetime,
        metadata: Optional[dict] = None,
    ) -> str:
        """Provision guest access via UniFi voucher system."""
        session = await self._get_session()

        # Calculate duration in minutes (UniFi uses minutes)
        duration_minutes = int((end_at - start_at).total_seconds() / 60)

        try:
            # Create voucher on UniFi controller
            # Note: UniFi API endpoint: /api/s/{site}/cmd/hotspot
            response = await session.post(
                f"{self.url}/api/s/{self.site}/cmd/hotspot",
                json={
                    "cmd": "create-voucher",
                    "n": 1,  # Number of vouchers
                    "quota": 1,  # Single-use
                    "expire": duration_minutes,
                    "note": f"Captive Portal: {username}",
                },
                cookies={"unifises": self._auth_cookie},
            )
            response.raise_for_status()
            data = response.json()

            # Extract voucher code from response
            if data.get("meta", {}).get("rc") != "ok":
                raise ProvisionError(f"UniFi voucher creation failed: {data}")

            voucher_id = data["data"][0]["create_time"]  # UniFi uses timestamp as ID
            voucher_code = data["data"][0]["code"]

            logger.info(
                "Provisioned UniFi voucher",
                extra={
                    "voucher_id": voucher_id,
                    "username": username,
                    "duration_minutes": duration_minutes,
                },
            )

            # Return the voucher ID as controller_ref
            return str(voucher_id)

        except httpx.RequestError as e:
            raise ControllerUnreachableError(f"UniFi controller unreachable: {e}")
        except httpx.HTTPStatusError as e:
            raise ProvisionError(f"UniFi provisioning failed: {e}")

    async def revoke_grant(self, controller_ref: str) -> None:
        """Revoke guest voucher on UniFi controller."""
        session = await self._get_session()

        try:
            response = await session.post(
                f"{self.url}/api/s/{self.site}/cmd/hotspot",
                json={
                    "cmd": "delete-voucher",
                    "_id": controller_ref,
                },
                cookies={"unifises": self._auth_cookie},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("meta", {}).get("rc") != "ok":
                raise RevocationError(f"UniFi revocation failed: {data}")

            logger.info("Revoked UniFi voucher", extra={"voucher_id": controller_ref})

        except httpx.RequestError as e:
            raise ControllerUnreachableError(f"UniFi controller unreachable: {e}")
        except httpx.HTTPStatusError as e:
            raise RevocationError(f"UniFi revocation failed: {e}")

    async def extend_grant(self, controller_ref: str, new_end_at: datetime) -> None:
        """
        Extend voucher expiration.

        Note: UniFi does not support direct voucher extension.
        This implementation revokes the old voucher and creates a new one.
        """
        # UniFi limitation: cannot modify voucher duration
        # Workaround: revoke old, create new (requires re-authentication on portal)
        raise ExtensionError(
            "UniFi controller does not support voucher extension. "
            "Create a new voucher or use UniFi guest portal manually."
        )

    async def health_check(self) -> dict:
        """Check UniFi controller connectivity."""
        try:
            session = await self._get_session()
            start = datetime.now()

            response = await session.get(
                f"{self.url}/api/s/{self.site}/stat/health",
                cookies={"unifises": self._auth_cookie},
            )

            latency_ms = (datetime.now() - start).total_seconds() * 1000
            response.raise_for_status()

            return {
                "healthy": True,
                "latency_ms": latency_ms,
                "details": "UniFi controller reachable",
            }

        except Exception as e:
            return {
                "healthy": False,
                "latency_ms": None,
                "details": f"Health check failed: {e}",
            }

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.aclose()
            self._session = None
            self._auth_cookie = None
```

### 4. Register the Adapter

Update the controller factory in `src/core/config.py` to support your new adapter:

```python
# src/core/config.py
from src.controllers.omada import OmadaAdapter
from src.controllers.unifi import UniFiAdapter  # Add import

def create_controller_adapter(config: dict) -> BaseController:
    """Factory function to create controller adapter from config."""
    controller_type = config.get("controller", {}).get("type", "omada")

    if controller_type == "omada":
        return OmadaAdapter(
            url=config["controller"]["url"],
            username=config["controller"]["username"],
            password=config["controller"]["password"],
            site_name=config["controller"].get("site_name", "Default"),
        )
    elif controller_type == "unifi":  # Add your adapter
        return UniFiAdapter(
            url=config["controller"]["url"],
            username=config["controller"]["username"],
            password=config["controller"]["password"],
            site=config["controller"].get("site", "default"),
        )
    else:
        raise ValueError(f"Unsupported controller type: {controller_type}")
```

### 5. Update Configuration Schema

Add your controller type to the addon configuration schema in `config.yaml`:

```yaml
schema:
  controller:
    type: list(omada|unifi)  # Add unifi to allowed values
    url: url
    username: str
    password: password
    site_name: str?  # For Omada
    site: str?       # For UniFi
  # ... rest of schema
```

### 6. Write Tests

Create comprehensive tests for your adapter:

```python
# tests/unit/test_unifi_adapter.py
"""Unit tests for UniFi controller adapter."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from src.controllers.unifi import UniFiAdapter
from src.controllers.base import ProvisionError, ControllerUnreachableError


@pytest.mark.asyncio
async def test_provision_grant_success():
    """Test successful voucher provisioning."""
    adapter = UniFiAdapter(
        url="https://unifi.local:8443",
        username="admin",
        password="test",
    )

    # Mock HTTP responses
    with patch.object(adapter, "_get_session") as mock_session:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "meta": {"rc": "ok"},
            "data": [{"create_time": "1234567890", "code": "ABC123"}],
        }
        mock_client.post.return_value = mock_response
        mock_session.return_value = mock_client

        start = datetime.now()
        end = start + timedelta(hours=2)

        controller_ref = await adapter.provision_grant(
            username="guest1",
            password="pass123",
            start_at=start,
            end_at=end,
        )

        assert controller_ref == "1234567890"


@pytest.mark.asyncio
async def test_revoke_grant_success():
    """Test successful voucher revocation."""
    adapter = UniFiAdapter(
        url="https://unifi.local:8443",
        username="admin",
        password="test",
    )

    with patch.object(adapter, "_get_session") as mock_session:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = {"meta": {"rc": "ok"}}
        mock_client.post.return_value = mock_response
        mock_session.return_value = mock_client

        await adapter.revoke_grant(controller_ref="1234567890")

        # Verify revoke API was called
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_healthy():
    """Test health check with reachable controller."""
    adapter = UniFiAdapter(
        url="https://unifi.local:8443",
        username="admin",
        password="test",
    )

    with patch.object(adapter, "_get_session") as mock_session:
        mock_client = AsyncMock()
        mock_client.get.return_value = AsyncMock(status_code=200)
        mock_session.return_value = mock_client

        result = await adapter.health_check()

        assert result["healthy"] is True
        assert result["latency_ms"] is not None
```

### 7. Integration Testing

Test the adapter with the full grant manager lifecycle:

```python
# tests/integration/test_unifi_integration.py
"""Integration tests for UniFi adapter with grant manager."""

import pytest
from datetime import datetime, timedelta

from src.services.grant_manager import GrantManager
from src.controllers.unifi import UniFiAdapter
from src.storage.repository import GrantRepository


@pytest.mark.asyncio
async def test_full_grant_lifecycle_unifi(tmp_path):
    """Test complete grant lifecycle with UniFi controller."""
    # Setup
    db_path = tmp_path / "test.db"
    repo = GrantRepository(str(db_path))
    adapter = UniFiAdapter(
        url="https://test-unifi:8443",
        username="admin",
        password="test",
    )
    manager = GrantManager(repository=repo, controller=adapter)

    # Mock controller responses
    # ... (similar pattern to unit tests)

    # Execute lifecycle
    grant_id = await manager.create_grant(
        username="guest1",
        password="pass123",
        start_at=datetime.now(),
        end_at=datetime.now() + timedelta(hours=2),
    )

    # Verify grant created and provisioned
    grant = await repo.get_grant(grant_id)
    assert grant.status == "active"
    assert grant.controller_ref is not None
```

### 8. Documentation

Document controller-specific configuration in the main README:

```markdown
#### UniFi Controller

The addon supports Ubiquiti UniFi controllers with voucher hotspot functionality:

- **URL**: Full HTTPS URL to UniFi controller (e.g., `https://192.168.1.1:8443`)
- **Credentials**: Admin credentials with hotspot voucher permissions
- **Site**: UniFi site name (defaults to "default")
- **API Version**: Compatible with UniFi Controller v6.x/v7.x

**Note**: UniFi does not support voucher extension. Extending a grant will require creating a new voucher.
```

## Testing Your Adapter

### Manual Testing Checklist

- [ ] **Provision Grant**: Create a grant and verify voucher appears in controller UI
- [ ] **Revoke Grant**: Revoke a grant and verify voucher removed from controller
- [ ] **Extend Grant**: Test extension (or document limitation if not supported)
- [ ] **Health Check**: Verify connectivity check works
- [ ] **Error Handling**: Test with controller offline, invalid credentials
- [ ] **Audit Logging**: Verify all operations logged correctly
- [ ] **Metrics**: Check metrics update (provision_latency, failed_provisions)

### Automated Testing

Run the full test suite with your adapter:

```bash
# Unit tests
uv run pytest tests/unit/test_<your_adapter>.py -v

# Integration tests
uv run pytest tests/integration/test_<your_adapter>_integration.py -v

# Full test suite
uv run pytest
```

## Controller-Specific Considerations

### API Authentication

Different controllers use different auth mechanisms:

- **Omada**: API key or username/password with bearer token
- **UniFi**: Cookie-based session authentication
- **Others**: May use OAuth, API keys, etc.

Handle authentication in `_get_session()` or similar method.

### Voucher vs. Client Provisioning

Controllers may support different access models:

1. **Voucher-based** (Omada, UniFi): Generate codes guests enter on portal
2. **MAC/Device-based** (some enterprise controllers): Authorize specific devices
3. **Hybrid**: Support both models

Adapt `provision_grant()` to match your controller's model.

### Duration Granularity

Controllers may have different duration granularities:

- **Omada**: Supports exact timestamps
- **UniFi**: Minutes only
- **Others**: May use hours, days, or fixed durations

Convert timestamps appropriately in your adapter.

### Extension Support

Not all controllers support modifying existing grants:

- **Supported**: Implement `extend_grant()` directly
- **Not Supported**: Raise `ExtensionError` with explanation, or implement revoke+recreate workaround

### Error Handling

Map controller-specific errors to base exceptions:

```python
try:
    # Controller API call
    response = await session.post(...)
    response.raise_for_status()
except httpx.ConnectTimeout:
    raise ControllerUnreachableError("Connection timeout")
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        raise ProvisionError("Authentication failed")
    elif e.response.status_code == 429:
        raise ProvisionError("Rate limit exceeded")
    else:
        raise ProvisionError(f"Controller error: {e}")
```

## Performance Optimization

### Connection Pooling

Reuse HTTP sessions across requests:

```python
async def _get_session(self) -> httpx.AsyncClient:
    if self._session is None:
        self._session = httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=10.0,
            limits=httpx.Limits(max_connections=10),  # Connection pool
        )
    return self._session
```

### Retry Logic

Implement retries for transient failures:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    reraise=True,
)
async def provision_grant(self, ...):
    # Provisioning logic with automatic retries
```

### Batch Operations

If your controller supports batch provisioning, implement batch methods:

```python
async def provision_grants_batch(self, grants: list[GrantInfo]) -> list[str]:
    """Provision multiple grants in a single API call (if supported)."""
    # Controller-specific batch implementation
```

## Security Best Practices

1. **Never log credentials**: Redact passwords, tokens in logs
2. **Validate SSL certificates**: Set `verify_ssl=True` by default
3. **Use secrets management**: Load passwords from Home Assistant secrets
4. **Least privilege**: Use controller accounts with minimal required permissions
5. **Rate limiting**: Respect controller rate limits to avoid lockouts

## Publishing Your Adapter

Once your adapter is complete and tested:

1. **Submit PR**: Include adapter code, tests, and documentation
2. **Update changelog**: Document new controller support
3. **Add to README**: List supported controllers with version compatibility
4. **Provide examples**: Include sample configuration snippets

## Example: Mikrotik Adapter Skeleton

```python
# src/controllers/mikrotik.py
"""Mikrotik RouterOS adapter for hotspot user provisioning."""

from .base import BaseController

class MikrotikAdapter(BaseController):
    """Mikrotik RouterOS adapter using API."""

    def __init__(self, host: str, username: str, password: str, port: int = 8728):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        # TODO: Initialize Mikrotik API connection

    async def provision_grant(self, username, password, start_at, end_at, metadata=None):
        # TODO: Add hotspot user via RouterOS API
        # /ip/hotspot/user/add name=username password=password
        pass

    async def revoke_grant(self, controller_ref):
        # TODO: Remove hotspot user
        # /ip/hotspot/user/remove [find name=username]
        pass

    async def extend_grant(self, controller_ref, new_end_at):
        # TODO: Update user uptime limit
        pass

    async def health_check(self):
        # TODO: Check API reachability
        pass
```

## Resources

- **Omada API Reference**: [TP-Link FAQ 896](https://www.tp-link.com/us/support/faq/896/)
- **UniFi API**: [Unofficial UniFi API Documentation](https://ubntwiki.com/products/software/unifi-controller/api)
- **Base Controller Source**: `src/controllers/base.py`
- **Omada Reference Implementation**: `src/controllers/omada.py`

## Support

Questions about adapter development? Open an issue on GitHub or ask in the Home Assistant community forum.
