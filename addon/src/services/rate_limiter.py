# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Rate limiting service for portal authentication attempts.

Implements rate limiting and credential attempt lockout to prevent brute force
attacks (FR-009 security requirement).
"""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Rate limiter for portal authentication attempts.

    Tracks authentication attempts per client IP and implements:
    - Per-IP rate limiting (max attempts per time window)
    - Lockout after repeated failures
    - Automatic lockout reset after cooldown period
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 60,
        lockout_duration_seconds: int = 300,
    ):
        """Initialize rate limiter.

        Args:
            max_attempts: Maximum failed attempts allowed in window
            window_seconds: Time window for attempt counting (seconds)
            lockout_duration_seconds: Lockout duration after exceeding limit (seconds)
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_duration_seconds = lockout_duration_seconds

        # Track attempts: client_ip -> list of attempt timestamps
        self._attempts: dict[str, list[datetime]] = defaultdict(list)

        # Track lockouts: client_ip -> lockout_until timestamp
        self._lockouts: dict[str, datetime] = {}

        # Lock for thread-safe access
        self._lock = asyncio.Lock()

        logger.info(
            "Rate limiter initialized",
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            lockout_duration_seconds=lockout_duration_seconds,
        )

    async def check_rate_limit(self, client_ip: str) -> tuple[bool, dict[str, Any]]:
        """Check if client IP is within rate limits.

        Args:
            client_ip: Client IP address

        Returns:
            Tuple of (is_allowed, metadata):
            - is_allowed: True if request is allowed, False if rate limited
            - metadata: Dict with details (attempts_remaining, lockout_until, etc.)
        """
        async with self._lock:
            now = datetime.now(UTC)

            # Check if client is locked out
            if client_ip in self._lockouts:
                lockout_until = self._lockouts[client_ip]

                if now < lockout_until:
                    # Still locked out
                    remaining_lockout = int((lockout_until - now).total_seconds())

                    logger.warning(
                        "Rate limit lockout active",
                        client_ip=client_ip,
                        lockout_until=lockout_until.isoformat(),
                        remaining_seconds=remaining_lockout,
                    )

                    return False, {
                        "locked_out": True,
                        "lockout_until": lockout_until.isoformat(),
                        "remaining_seconds": remaining_lockout,
                        "attempts_remaining": 0,
                    }
                else:
                    # Lockout expired, clear it
                    logger.info(
                        "Rate limit lockout expired",
                        client_ip=client_ip,
                        locked_duration_seconds=self.lockout_duration_seconds,
                    )
                    del self._lockouts[client_ip]
                    self._attempts[client_ip] = []

            # Clean up old attempts outside the window
            window_start = now - timedelta(seconds=self.window_seconds)
            self._attempts[client_ip] = [
                attempt
                for attempt in self._attempts[client_ip]
                if attempt > window_start
            ]

            # Count attempts in current window
            attempts_in_window = len(self._attempts[client_ip])
            attempts_remaining = max(0, self.max_attempts - attempts_in_window)

            # Check if limit exceeded
            if attempts_in_window >= self.max_attempts:
                # Trigger lockout
                lockout_until = now + timedelta(seconds=self.lockout_duration_seconds)
                self._lockouts[client_ip] = lockout_until

                logger.warning(
                    "Rate limit exceeded, client locked out",
                    client_ip=client_ip,
                    attempts_in_window=attempts_in_window,
                    lockout_until=lockout_until.isoformat(),
                    lockout_duration_seconds=self.lockout_duration_seconds,
                )

                return False, {
                    "locked_out": True,
                    "lockout_until": lockout_until.isoformat(),
                    "remaining_seconds": self.lockout_duration_seconds,
                    "attempts_remaining": 0,
                }

            # Within limits
            return True, {
                "locked_out": False,
                "attempts_remaining": attempts_remaining,
                "window_seconds": self.window_seconds,
            }

    async def record_attempt(self, client_ip: str, success: bool) -> None:
        """Record an authentication attempt.

        Args:
            client_ip: Client IP address
            success: Whether the attempt was successful
        """
        async with self._lock:
            now = datetime.now(UTC)

            if success:
                # Successful attempt - clear history for this IP
                if client_ip in self._attempts:
                    logger.info(
                        "Successful auth, clearing rate limit history",
                        client_ip=client_ip,
                    )
                    del self._attempts[client_ip]

                if client_ip in self._lockouts:
                    del self._lockouts[client_ip]
            else:
                # Failed attempt - record it
                self._attempts[client_ip].append(now)

                # Clean up old attempts
                window_start = now - timedelta(seconds=self.window_seconds)
                self._attempts[client_ip] = [
                    attempt
                    for attempt in self._attempts[client_ip]
                    if attempt > window_start
                ]

                attempts_in_window = len(self._attempts[client_ip])

                logger.info(
                    "Failed auth attempt recorded",
                    client_ip=client_ip,
                    attempts_in_window=attempts_in_window,
                    max_attempts=self.max_attempts,
                )

                # Check if lockout should be triggered
                if attempts_in_window >= self.max_attempts:
                    lockout_until = now + timedelta(
                        seconds=self.lockout_duration_seconds
                    )
                    self._lockouts[client_ip] = lockout_until
                    logger.warning(
                        "Rate limit lockout triggered",
                        client_ip=client_ip,
                        attempts=attempts_in_window,
                        lockout_until=lockout_until.isoformat(),
                        lockout_duration_seconds=self.lockout_duration_seconds,
                    )

    async def reset_client(self, client_ip: str) -> None:
        """Reset rate limit state for a specific client.

        Args:
            client_ip: Client IP address to reset
        """
        async with self._lock:
            if client_ip in self._attempts:
                del self._attempts[client_ip]

            if client_ip in self._lockouts:
                del self._lockouts[client_ip]

            logger.info("Rate limit state reset", client_ip=client_ip)

    async def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics.

        Returns:
            Dictionary with current stats
        """
        async with self._lock:
            now = datetime.now(UTC)

            active_lockouts = sum(
                1 for lockout_until in self._lockouts.values() if lockout_until > now
            )

            return {
                "tracked_ips": len(self._attempts),
                "active_lockouts": active_lockouts,
                "total_lockouts": len(self._lockouts),
                "max_attempts": self.max_attempts,
                "window_seconds": self.window_seconds,
                "lockout_duration_seconds": self.lockout_duration_seconds,
            }


# Global instance (initialized on first use)
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance.

    Returns:
        Rate limiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def set_rate_limiter(rate_limiter: RateLimiter) -> None:
    """Set the global rate limiter instance (for testing).

    Args:
        rate_limiter: Rate limiter instance to use
    """
    global _rate_limiter
    _rate_limiter = rate_limiter
