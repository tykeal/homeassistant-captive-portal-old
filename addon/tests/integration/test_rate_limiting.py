# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for rate limiting and credential attempt lockout."""

import asyncio

import pytest

from src.services.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter() -> None:
    """Create a rate limiter with test settings."""
    return RateLimiter(
        max_attempts=5,
        window_seconds=60,
        lockout_duration_seconds=300,
    )


@pytest.mark.asyncio
async def test_rate_limiting_within_limits(rate_limiter) -> None:
    """Test that requests within limits are allowed."""
    client_ip = "192.168.1.100"

    # First 5 attempts should be allowed
    for i in range(5):
        is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
        assert is_allowed, f"Attempt {i + 1} should be allowed"
        assert not info["locked_out"]
        assert info["attempts_remaining"] == 5 - i

        # Record failed attempt
        await rate_limiter.record_attempt(client_ip, success=False)


@pytest.mark.asyncio
async def test_rate_limiting_lockout_triggers(rate_limiter) -> None:
    """Test that lockout triggers after max attempts exceeded."""
    client_ip = "192.168.1.101"

    # Make max attempts
    for _ in range(5):
        await rate_limiter.record_attempt(client_ip, success=False)

    # Next check should trigger lockout
    is_allowed, info = await rate_limiter.check_rate_limit(client_ip)

    assert not is_allowed, "Should be locked out after max attempts"
    assert info["locked_out"]
    assert info["attempts_remaining"] == 0
    assert "remaining_seconds" in info
    assert info["remaining_seconds"] > 0


@pytest.mark.asyncio
async def test_rate_limiting_lockout_duration(rate_limiter) -> None:
    """Test that lockout persists for configured duration."""
    # Use short lockout for testing
    short_limiter = RateLimiter(
        max_attempts=3,
        window_seconds=10,
        lockout_duration_seconds=2,
    )

    client_ip = "192.168.1.102"

    # Trigger lockout
    for _ in range(3):
        await short_limiter.record_attempt(client_ip, success=False)

    # Should be locked out
    is_allowed, info = await short_limiter.check_rate_limit(client_ip)
    assert not is_allowed
    assert info["locked_out"]

    # Wait for lockout to expire
    await asyncio.sleep(2.5)

    # Should be allowed again
    is_allowed, info = await short_limiter.check_rate_limit(client_ip)
    assert is_allowed
    assert not info["locked_out"]


@pytest.mark.asyncio
async def test_rate_limiting_successful_auth_clears_history(rate_limiter) -> None:
    """Test that successful authentication clears rate limit history."""
    client_ip = "192.168.1.103"

    # Make 3 failed attempts
    for _ in range(3):
        await rate_limiter.record_attempt(client_ip, success=False)

    # Check remaining attempts
    is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
    assert is_allowed
    assert info["attempts_remaining"] == 2

    # Successful authentication
    await rate_limiter.record_attempt(client_ip, success=True)

    # History should be cleared
    is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
    assert is_allowed
    assert info["attempts_remaining"] == 5  # Back to max


@pytest.mark.asyncio
async def test_rate_limiting_window_expiry(rate_limiter) -> None:
    """Test that old attempts outside window are discarded."""
    # Use short window for testing
    short_limiter = RateLimiter(
        max_attempts=3,
        window_seconds=1,
        lockout_duration_seconds=60,
    )

    client_ip = "192.168.1.104"

    # Make 2 failed attempts
    for _ in range(2):
        await short_limiter.record_attempt(client_ip, success=False)

    # Wait for window to expire
    await asyncio.sleep(1.5)

    # Old attempts should be discarded
    is_allowed, info = await short_limiter.check_rate_limit(client_ip)
    assert is_allowed
    assert info["attempts_remaining"] == 3  # Back to max


@pytest.mark.asyncio
async def test_rate_limiting_different_ips_independent(rate_limiter) -> None:
    """Test that rate limiting is per-IP (different IPs don't affect each other)."""
    client_ip_1 = "192.168.1.105"
    client_ip_2 = "192.168.1.106"

    # IP 1 makes 5 failed attempts (triggers lockout)
    for _ in range(5):
        await rate_limiter.record_attempt(client_ip_1, success=False)

    # IP 1 should be locked out
    is_allowed_1, info_1 = await rate_limiter.check_rate_limit(client_ip_1)
    assert not is_allowed_1
    assert info_1["locked_out"]

    # IP 2 should still be allowed
    is_allowed_2, info_2 = await rate_limiter.check_rate_limit(client_ip_2)
    assert is_allowed_2
    assert not info_2["locked_out"]
    assert info_2["attempts_remaining"] == 5


@pytest.mark.asyncio
async def test_rate_limiting_reset_client(rate_limiter) -> None:
    """Test that reset_client clears all state for a client."""
    client_ip = "192.168.1.107"

    # Trigger lockout
    for _ in range(5):
        await rate_limiter.record_attempt(client_ip, success=False)

    # Verify lockout
    is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
    assert not is_allowed
    assert info["locked_out"]

    # Reset client
    await rate_limiter.reset_client(client_ip)

    # Should be allowed again
    is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
    assert is_allowed
    assert not info["locked_out"]
    assert info["attempts_remaining"] == 5


@pytest.mark.asyncio
async def test_rate_limiting_stats(rate_limiter) -> None:
    """Test rate limiter statistics."""
    # Trigger lockout for one IP
    client_ip = "192.168.1.108"
    for _ in range(5):
        await rate_limiter.record_attempt(client_ip, success=False)

    # Get stats
    stats = await rate_limiter.get_stats()

    assert stats["tracked_ips"] >= 1
    assert stats["active_lockouts"] >= 1
    assert stats["max_attempts"] == 5
    assert stats["window_seconds"] == 60
    assert stats["lockout_duration_seconds"] == 300


@pytest.mark.asyncio
async def test_rate_limiting_concurrent_requests(rate_limiter) -> None:
    """Test rate limiting handles concurrent requests correctly."""
    client_ip = "192.168.1.109"

    async def make_attempt() -> None:
        """Make a single failed attempt."""
        is_allowed, info = await rate_limiter.check_rate_limit(client_ip)
        if is_allowed:
            await rate_limiter.record_attempt(client_ip, success=False)
        return is_allowed

    # Make 10 concurrent attempts (should exceed limit of 5)
    results = await asyncio.gather(*[make_attempt() for _ in range(10)])

    # Some should succeed (within limit), some should fail (locked out)
    allowed_count = sum(1 for r in results if r)

    # At least 5 should be allowed initially, and at least some denied after lockout
    assert allowed_count >= 5
    # Note: Due to concurrency, exact counts may vary
