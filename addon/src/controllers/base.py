# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Base controller adapter interface for network access provisioning."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProvisionResult(BaseModel):
    """Result of a provision operation."""

    success: bool
    controller_voucher_id: str | None = None
    message: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None


class ControllerAdapter(ABC):
    """Abstract base class for network controller adapters.

    This interface defines the contract for interacting with network
    controllers to provision, extend, revoke, and manage network access.
    Implementations should handle controller-specific API calls, error
    handling, and retry logic.
    """

    @abstractmethod
    async def provision_grant(
        self,
        grant_id: str,
        guest_name: str,
        start_time: datetime,
        end_time: datetime,
        device_mac: str | None = None,
    ) -> ProvisionResult:
        """Provision network access for a grant.

        Args:
            grant_id: Internal grant identifier
            guest_name: Name of the guest
            start_time: When access should start
            end_time: When access should end
            device_mac: Optional device MAC address for binding

        Returns:
            ProvisionResult with controller voucher ID if successful

        Raises:
            Exception: On controller communication failure
        """
        pass

    @abstractmethod
    async def revoke_grant(
        self,
        controller_voucher_id: str,
        reason: str | None = None,
    ) -> ProvisionResult:
        """Revoke network access for a previously provisioned grant.

        Args:
            controller_voucher_id: Controller's voucher identifier
            reason: Optional reason for revocation

        Returns:
            ProvisionResult indicating success or failure

        Raises:
            Exception: On controller communication failure
        """
        pass

    @abstractmethod
    async def extend_grant(
        self,
        controller_voucher_id: str,
        new_end_time: datetime,
    ) -> ProvisionResult:
        """Extend the expiration time of an existing grant.

        Args:
            controller_voucher_id: Controller's voucher identifier
            new_end_time: New expiration time

        Returns:
            ProvisionResult indicating success or failure

        Raises:
            Exception: On controller communication failure
        """
        pass

    @abstractmethod
    async def check_status(self, controller_voucher_id: str) -> ProvisionResult:
        """Check the status of a voucher on the controller.

        Args:
            controller_voucher_id: Controller's voucher identifier

        Returns:
            ProvisionResult with current status details

        Raises:
            Exception: On controller communication failure
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify controller connectivity and health.

        Returns:
            True if controller is reachable and healthy, False otherwise
        """
        pass
