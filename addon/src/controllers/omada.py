# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""TP-Omada controller adapter implementation.

Reference: TP-Link FAQ 896 - Omada voucher & portal workflow
https://www.tp-link.com/us/support/faq/896/

This adapter implements voucher-based captive portal access control
for TP-Link Omada SDN controllers.
"""

from datetime import datetime

import httpx

from ..core.logging_config import get_logger
from .base import ControllerAdapter, ProvisionResult

logger = get_logger(__name__)


class OmadaController(ControllerAdapter):
    """TP-Omada SDN controller adapter for voucher-based access.

    Implements the ControllerAdapter interface for TP-Link Omada controllers,
    using the voucher API to provision temporary network access.

    Per FAQ 896, vouchers support:
    - Time-based expiration (duration or specific end time)
    - Usage limits (single-use or multi-use)
    - Portal customization (redirect URLs, terms acceptance)
    - MAC address binding (optional)
    """

    def __init__(
        self,
        controller_url: str,
        site_id: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ):
        """Initialize the Omada controller adapter.

        Args:
            controller_url: Base URL of the Omada controller
            site_id: Site ID for multi-site deployments
            username: Admin username
            password: Admin password
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.controller_url = controller_url.rstrip("/")
        self.site_id = site_id
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        # Session token cached after login
        self._token: str | None = None
        self._token_expires: datetime | None = None

    async def _authenticate(self) -> str:
        """Authenticate with the Omada controller and get session token.

        Returns:
            Session token for authenticated requests

        Raises:
            httpx.HTTPError: On authentication failure
        """
        # TODO: Implement actual Omada authentication
        # Stub implementation for now
        logger.info(
            "Authenticating with Omada controller",
            controller_url=self.controller_url,
            site_id=self.site_id,
        )

        # Placeholder - actual implementation would:
        # 1. POST to /api/v2/login with credentials
        # 2. Extract token from response
        # 3. Cache token with expiration
        return "stub_token_placeholder"

    async def _ensure_authenticated(self) -> str:
        """Ensure we have a valid authentication token.

        Returns:
            Valid session token

        Raises:
            httpx.HTTPError: On authentication failure
        """
        # Check if token is cached and valid
        if self._token and self._token_expires:
            from datetime import UTC

            if datetime.now(UTC) < self._token_expires:
                return self._token

        # Authenticate and cache token
        self._token = await self._authenticate()
        # Set expiration to 4 hours from now (typical Omada session timeout)
        from datetime import UTC, timedelta

        self._token_expires = datetime.now(UTC) + timedelta(hours=4)

        return self._token

    async def provision_grant(
        self,
        grant_id: str,
        guest_name: str,
        start_time: datetime,
        end_time: datetime,
        device_mac: str | None = None,
    ) -> ProvisionResult:
        """Provision network access via Omada voucher creation.

        Creates a voucher on the Omada controller with the specified parameters.
        Per FAQ 896, the voucher will be activated through the captive portal.

        Args:
            grant_id: Internal grant identifier (stored in voucher notes)
            guest_name: Guest name (stored in voucher description)
            start_time: When voucher becomes valid
            end_time: When voucher expires
            device_mac: Optional MAC address binding

        Returns:
            ProvisionResult with controller voucher ID

        Raises:
            httpx.HTTPError: On controller communication failure
        """
        logger.info(
            "Provisioning grant on Omada controller",
            grant_id=grant_id,
            guest_name=guest_name,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            device_mac=device_mac,
        )

        try:
            _token = await self._ensure_authenticated()

            # Calculate duration in minutes
            duration_minutes = int((end_time - start_time).total_seconds() / 60)

            # Prepare voucher payload per Omada API
            # TODO: Replace with actual Omada API structure
            voucher_data = {
                "type": 4,  # Multi-use voucher
                "duration": duration_minutes,
                "quantity": 1,
                "note": f"Grant {grant_id}",  # Internal reference
                "name": guest_name[:32],  # Omada limits name length
            }

            if device_mac:
                voucher_data["mac"] = device_mac  # MAC binding if supported

            # Stub: Return success with placeholder voucher ID
            # Actual implementation would POST to:
            # /api/v2/{site_id}/hotspot/vouchers
            controller_voucher_id = f"omada_voucher_{grant_id[:8]}"

            logger.info(
                "Grant provisioned successfully",
                grant_id=grant_id,
                controller_voucher_id=controller_voucher_id,
            )

            return ProvisionResult(
                success=True,
                controller_voucher_id=controller_voucher_id,
                message="Voucher created successfully",
                details={
                    "duration_minutes": duration_minutes,
                    "guest_name": guest_name,
                    "mac_binding": device_mac is not None,
                },
            )

        except httpx.HTTPError as e:
            logger.error(
                "Failed to provision grant on Omada controller",
                grant_id=grant_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Controller communication failed: {e}",
            )
        except Exception as e:
            logger.error(
                "Unexpected error provisioning grant",
                grant_id=grant_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    async def revoke_grant(
        self,
        controller_voucher_id: str,
        reason: str | None = None,
    ) -> ProvisionResult:
        """Revoke network access by deleting the Omada voucher.

        Args:
            controller_voucher_id: Omada voucher identifier
            reason: Optional reason for revocation (logged)

        Returns:
            ProvisionResult indicating success or failure

        Raises:
            httpx.HTTPError: On controller communication failure
        """
        logger.info(
            "Revoking grant on Omada controller",
            controller_voucher_id=controller_voucher_id,
            reason=reason,
        )

        try:
            _token = await self._ensure_authenticated()

            # Stub: Return success
            # Actual implementation would DELETE:
            # /api/v2/{site_id}/hotspot/vouchers/{voucher_id}

            logger.info(
                "Grant revoked successfully",
                controller_voucher_id=controller_voucher_id,
            )

            return ProvisionResult(
                success=True,
                message="Voucher revoked successfully",
            )

        except httpx.HTTPError as e:
            logger.error(
                "Failed to revoke grant on Omada controller",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Controller communication failed: {e}",
            )
        except Exception as e:
            logger.error(
                "Unexpected error revoking grant",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    async def extend_grant(
        self,
        controller_voucher_id: str,
        new_end_time: datetime,
    ) -> ProvisionResult:
        """Extend voucher expiration time.

        Note: Omada may not support direct voucher extension.
        Implementation may require creating a new voucher and migrating
        the client, or adjusting portal authentication timeout.

        Args:
            controller_voucher_id: Omada voucher identifier
            new_end_time: New expiration time

        Returns:
            ProvisionResult indicating success or failure

        Raises:
            httpx.HTTPError: On controller communication failure
        """
        logger.info(
            "Extending grant on Omada controller",
            controller_voucher_id=controller_voucher_id,
            new_end_time=new_end_time.isoformat(),
        )

        try:
            _token = await self._ensure_authenticated()

            # Stub: Return success
            # Actual implementation may need workaround:
            # 1. Check if PATCH/PUT to voucher endpoint is supported
            # 2. If not, may need to revoke old voucher and create new one

            logger.warning(
                "Voucher extension may not be supported by Omada API",
                controller_voucher_id=controller_voucher_id,
            )

            return ProvisionResult(
                success=True,
                message="Extension requested (may require manual intervention)",
                details={"warning": "Omada API may not support direct extension"},
            )

        except httpx.HTTPError as e:
            logger.error(
                "Failed to extend grant on Omada controller",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Controller communication failed: {e}",
            )
        except Exception as e:
            logger.error(
                "Unexpected error extending grant",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    async def check_status(self, controller_voucher_id: str) -> ProvisionResult:
        """Check voucher status on the Omada controller.

        Args:
            controller_voucher_id: Omada voucher identifier

        Returns:
            ProvisionResult with current voucher status

        Raises:
            httpx.HTTPError: On controller communication failure
        """
        logger.debug(
            "Checking voucher status on Omada controller",
            controller_voucher_id=controller_voucher_id,
        )

        try:
            _token = await self._ensure_authenticated()

            # Stub: Return active status
            # Actual implementation would GET:
            # /api/v2/{site_id}/hotspot/vouchers/{voucher_id}

            return ProvisionResult(
                success=True,
                message="Voucher is active",
                details={
                    "status": "active",
                    "voucher_id": controller_voucher_id,
                },
            )

        except httpx.HTTPError as e:
            logger.error(
                "Failed to check voucher status",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Controller communication failed: {e}",
            )
        except Exception as e:
            logger.error(
                "Unexpected error checking voucher status",
                controller_voucher_id=controller_voucher_id,
                error=str(e),
            )
            return ProvisionResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    async def health_check(self) -> bool:
        """Verify Omada controller connectivity.

        Returns:
            True if controller is reachable, False otherwise
        """
        try:
            # Simple connectivity check - attempt to access info endpoint
            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                # Stub: Check if base URL is accessible
                # Actual implementation would GET:
                # /api/v2/info or similar health endpoint
                response = await client.get(f"{self.controller_url}/api/v2/info")
                return response.status_code == 200

        except Exception as e:
            logger.warning(
                "Omada controller health check failed",
                controller_url=self.controller_url,
                error=str(e),
            )
            return False
