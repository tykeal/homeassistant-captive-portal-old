# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Retry and backoff policy for controller operations.

Implements exponential backoff with jitter for controller unreachability.
Tracks metrics for failed provisions and retries.
"""

import asyncio
import random
from typing import Any

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class RetryPolicy:
    """Retry policy with exponential backoff and jitter.

    Implements retry logic for controller operations with:
    - Exponential backoff
    - Random jitter to prevent thundering herd
    - Max retry limits
    - Retry tracking and metrics
    """

    def __init__(
        self,
        max_retries: int = 5,
        initial_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,  # 5 minutes
        backoff_multiplier: float = 2.0,
        jitter_factor: float = 0.1,
    ):
        """Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts (default 5)
            initial_backoff_seconds: Initial backoff delay (default 2.0)
            max_backoff_seconds: Maximum backoff delay (default 300.0)
            backoff_multiplier: Backoff multiplier for exponential growth (default 2.0)
            jitter_factor: Jitter factor as fraction of backoff (default 0.1)
        """
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff_seconds
        self.max_backoff = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.jitter_factor = jitter_factor

        # Metrics
        self.total_retries = 0
        self.failed_after_retries = 0
        self.successful_after_retry = 0

    def calculate_backoff(self, retry_count: int) -> float:
        """Calculate backoff delay with exponential growth and jitter.

        Args:
            retry_count: Current retry attempt number (0-indexed)

        Returns:
            Backoff delay in seconds
        """
        # Exponential backoff
        backoff = min(
            self.initial_backoff * (self.backoff_multiplier**retry_count),
            self.max_backoff,
        )

        # Add jitter: +/- jitter_factor * backoff
        jitter = backoff * self.jitter_factor * (2 * random.random() - 1)
        backoff_with_jitter = backoff + jitter

        # Ensure non-negative
        return max(0.1, backoff_with_jitter)

    async def execute_with_retry(
        self,
        operation: Any,  # Callable async function
        operation_name: str,
        grant_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute operation with retry and backoff.

        Args:
            operation: Async operation to execute
            operation_name: Name of operation for logging
            grant_id: Grant ID for logging
            **kwargs: Additional arguments to pass to operation

        Returns:
            Result from operation

        Raises:
            Exception: If operation fails after all retries
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # Calculate and apply backoff
                    backoff_delay = self.calculate_backoff(attempt - 1)

                    logger.info(
                        "Retrying operation after backoff",
                        operation=operation_name,
                        grant_id=grant_id,
                        attempt=attempt,
                        max_retries=self.max_retries,
                        backoff_seconds=round(backoff_delay, 2),
                    )

                    await asyncio.sleep(backoff_delay)

                # Execute operation
                result = await operation(**kwargs)

                # Success
                if attempt > 0:
                    self.successful_after_retry += 1
                    logger.info(
                        "Operation succeeded after retry",
                        operation=operation_name,
                        grant_id=grant_id,
                        attempts=attempt + 1,
                    )

                return result

            except Exception as e:
                last_exception = e
                self.total_retries += 1

                if attempt < self.max_retries:
                    logger.warning(
                        "Operation failed, will retry",
                        operation=operation_name,
                        grant_id=grant_id,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        error=str(e),
                    )
                else:
                    self.failed_after_retries += 1
                    logger.error(
                        "Operation failed after all retries",
                        operation=operation_name,
                        grant_id=grant_id,
                        attempts=attempt + 1,
                        error=str(e),
                    )

        # All retries exhausted
        raise last_exception  # type: ignore[misc]

    def should_retry(self, retry_count: int) -> bool:
        """Check if operation should be retried.

        Args:
            retry_count: Current retry count

        Returns:
            True if should retry, False otherwise
        """
        return retry_count < self.max_retries

    def get_metrics(self) -> dict[str, int]:
        """Get retry metrics.

        Returns:
            Dictionary with retry statistics
        """
        return {
            "total_retries": self.total_retries,
            "failed_after_retries": self.failed_after_retries,
            "successful_after_retry": self.successful_after_retry,
        }

    def reset_metrics(self) -> None:
        """Reset retry metrics."""
        self.total_retries = 0
        self.failed_after_retries = 0
        self.successful_after_retry = 0


# Global retry policy instance
_retry_policy: RetryPolicy | None = None


def get_retry_policy() -> RetryPolicy:
    """Get the global retry policy instance."""
    global _retry_policy
    if _retry_policy is None:
        _retry_policy = RetryPolicy()
    return _retry_policy


def set_retry_policy(policy: RetryPolicy) -> None:
    """Set a custom retry policy (for testing)."""
    global _retry_policy
    _retry_policy = policy
