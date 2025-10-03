# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Authentication and authorization for admin API endpoints (T048).

Provides authentication middleware using Home Assistant Supervisor tokens
and API key-based auth as a fallback for development/testing.
"""

import os
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.logging_config import get_logger

logger = get_logger(__name__)

# Security scheme for Bearer token auth
bearer_scheme = HTTPBearer(auto_error=False)


class AuthService:
    """Authentication service for admin API endpoints.

    Supports two authentication modes:
    1. Home Assistant Supervisor token (production)
    2. API key from environment variable (development/testing)

    The service validates tokens against the HA Supervisor API or
    compares with a configured static API key.
    """

    def __init__(self):
        """Initialize authentication service."""
        self.supervisor_url = os.getenv("SUPERVISOR_URL", "http://supervisor")
        self.supervisor_token = os.getenv("SUPERVISOR_TOKEN")
        self.api_key = os.getenv("CAPTIVE_PORTAL_API_KEY")

        # Determine auth mode
        if self.supervisor_token:
            self.auth_mode = "supervisor"
            logger.info("Authentication mode: Home Assistant Supervisor")
        elif self.api_key:
            self.auth_mode = "api_key"
            logger.warning(
                "Authentication mode: Static API key (development only)",
            )
        else:
            self.auth_mode = "disabled"
            logger.warning(
                "Authentication DISABLED - no SUPERVISOR_TOKEN or API_KEY found",
            )

    async def validate_supervisor_token(self, token: str) -> bool:
        """Validate token against Home Assistant Supervisor API.

        Args:
            token: Bearer token to validate

        Returns:
            True if token is valid, False otherwise
        """
        if not self.supervisor_token:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.supervisor_url}/core/api/states",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Supervisor-Token": self.supervisor_token,
                    },
                    timeout=5.0,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.error(
                "Supervisor API token validation failed",
                error=str(e),
            )
            return False

    async def authenticate(
        self,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> bool:
        """Authenticate request using configured auth mode.

        Args:
            credentials: HTTP Bearer credentials from request

        Returns:
            True if authenticated successfully

        Raises:
            HTTPException: If authentication fails (401)
        """
        if self.auth_mode == "disabled":
            logger.warning("Authentication disabled - allowing request")
            return True

        if not credentials:
            logger.warning("No credentials provided in request")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials

        if self.auth_mode == "supervisor":
            if await self.validate_supervisor_token(token):
                logger.debug("Supervisor token validated successfully")
                return True
            logger.warning("Invalid supervisor token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        elif self.auth_mode == "api_key":
            if token == self.api_key:
                logger.debug("API key validated successfully")
                return True
            logger.warning("Invalid API key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Shouldn't reach here, but fail safely
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication configuration error",
        )


# Singleton instance
_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Get the authentication service singleton.

    Returns:
        AuthService instance
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def require_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> bool:
    """FastAPI dependency for endpoints requiring authentication.

    Usage:
        @router.get("/admin/endpoint", dependencies=[Depends(require_auth)])
        async def admin_endpoint():
            ...

    Args:
        credentials: Bearer token from request header
        auth_service: Authentication service instance

    Returns:
        True if authenticated

    Raises:
        HTTPException: 401 if authentication fails
    """
    return await auth_service.authenticate(credentials)


async def optional_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> dict[str, bool]:
    """FastAPI dependency for optional authentication context.

    Provides authentication status without enforcing it.
    Useful for endpoints that behave differently for authenticated users.

    Args:
        request: FastAPI request object
        credentials: Bearer token from request header (optional)

    Returns:
        Dict with 'authenticated' boolean flag
    """
    if not credentials:
        return {"authenticated": False}

    auth_service = get_auth_service()
    try:
        await auth_service.authenticate(credentials)
        return {"authenticated": True}
    except HTTPException:
        return {"authenticated": False}
