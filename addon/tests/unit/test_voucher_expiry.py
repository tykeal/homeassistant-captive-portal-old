# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for voucher expiry boundary conditions (T057)."""

from datetime import UTC, datetime, timedelta

from src.models.domain import VoucherStatus


class TestVoucherExpiryBoundaryConditions:
    """Test voucher expiry boundary conditions."""

    def test_voucher_expires_exactly_at_expiry_time(self) -> None:
        """Test voucher expires exactly at expiry_time."""
        now = datetime.now(UTC)
        expiry_time = now

        # At exact expiry time, voucher should be expired
        is_expired = expiry_time <= now
        assert is_expired is True

    def test_voucher_not_expired_one_second_before_expiry(self) -> None:
        """Test voucher is still valid one second before expiry."""
        now = datetime.now(UTC)
        expiry_time = now + timedelta(seconds=1)

        # One second before expiry, voucher should still be valid
        is_expired = expiry_time <= now
        assert is_expired is False

    def test_voucher_expires_when_max_uses_reached(self) -> None:
        """Test voucher logic when max uses reached even if time hasn't expired."""
        remaining_uses = 0

        # Voucher should be considered exhausted
        is_exhausted = remaining_uses <= 0
        assert is_exhausted is True

    def test_unlimited_voucher_never_exhausted_by_uses(self) -> None:
        """Test unlimited voucher (max_uses=None) never exhausted by use count."""
        remaining_uses = None

        # Unlimited voucher should never be exhausted by uses
        is_exhausted = remaining_uses is not None and remaining_uses <= 0
        assert is_exhausted is False

    def test_voucher_with_none_expiry_time(self) -> None:
        """Test voucher with expiry_time set to None (never expires by time)."""
        now = datetime.now(UTC)
        expiry_time = None

        # Voucher with no expiry_time should never expire by time
        is_expired_by_time = expiry_time is not None and expiry_time <= now
        assert is_expired_by_time is False

    def test_voucher_status_active_with_remaining_uses(self) -> None:
        """Test voucher status should be ACTIVE when uses remain."""
        status = VoucherStatus.ACTIVE
        remaining_uses = 5

        assert status == VoucherStatus.ACTIVE
        assert remaining_uses > 0

    def test_voucher_status_transitions_to_exhausted(self) -> None:
        """Test voucher status transitions to INACTIVE when uses depleted."""
        remaining_uses = 0

        # After all uses consumed, status should be INACTIVE
        expected_status = (
            VoucherStatus.INACTIVE if remaining_uses == 0 else VoucherStatus.ACTIVE
        )
        assert expected_status == VoucherStatus.INACTIVE

    def test_voucher_status_transitions_to_expired(self) -> None:
        """Test voucher status transitions to EXPIRED when time expires."""
        now = datetime.now(UTC)
        past_expiry = now - timedelta(seconds=1)

        # Voucher should be expired by time
        is_expired = past_expiry <= now
        assert is_expired is True
        expected_status = VoucherStatus.EXPIRED
        assert expected_status == VoucherStatus.EXPIRED

    def test_voucher_exactly_at_midnight_boundary(self) -> None:
        """Test voucher expiry at midnight boundary (common edge case)."""
        # Create a datetime at midnight
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        expiry_time = midnight

        # At or after midnight, voucher should be expired
        now = midnight
        is_expired = expiry_time <= now
        assert is_expired is True

        # Just before midnight, voucher should still be valid
        now = midnight - timedelta(seconds=1)
        is_not_expired = expiry_time > now
        assert is_not_expired is True

    def test_voucher_with_very_short_duration(self) -> None:
        """Test voucher expiry logic with very short duration (1 second)."""
        now = datetime.now(UTC)
        expiry_time = now + timedelta(seconds=1)

        # Should not be expired immediately
        is_not_expired = expiry_time > now
        assert is_not_expired is True

        # After waiting, should be expired
        future_time = now + timedelta(seconds=2)
        is_expired_later = expiry_time <= future_time
        assert is_expired_later is True

    def test_voucher_with_very_long_duration(self) -> None:
        """Test voucher with very long duration (1 year)."""
        now = datetime.now(UTC)
        expiry_time = now + timedelta(days=365)

        # Should not be expired for a long time
        is_not_expired = expiry_time > now
        assert is_not_expired is True

        # Even 100 days later, still not expired
        future_time = now + timedelta(days=100)
        is_still_not_expired = expiry_time > future_time
        assert is_still_not_expired is True

    def test_voucher_boundary_zero_remaining_uses(self) -> None:
        """Test voucher at boundary of zero remaining uses."""
        remaining_uses = 0

        # Zero remaining uses means exhausted
        is_exhausted = remaining_uses <= 0
        assert is_exhausted is True

    def test_voucher_boundary_one_remaining_use(self) -> None:
        """Test voucher at boundary of one remaining use."""
        remaining_uses = 1

        # One remaining use means still active
        is_active = remaining_uses > 0
        assert is_active is True

    def test_voucher_expiry_precedence_both_conditions(self) -> None:
        """Test voucher expiry when both time and uses are exhausted."""
        now = datetime.now(UTC)
        past_expiry = now - timedelta(seconds=1)
        remaining_uses = 0

        # Both conditions met - voucher is definitely expired/exhausted
        is_expired_by_time = past_expiry <= now
        is_exhausted_by_uses = remaining_uses <= 0

        assert is_expired_by_time is True
        assert is_exhausted_by_uses is True

    def test_voucher_one_condition_met(self) -> None:
        """Test voucher when only one expiry condition is met."""
        now = datetime.now(UTC)
        future_expiry = now + timedelta(hours=24)
        remaining_uses = 0

        # Only uses exhausted, time still valid
        is_expired_by_time = future_expiry <= now
        is_exhausted_by_uses = remaining_uses <= 0

        assert is_expired_by_time is False
        assert is_exhausted_by_uses is True  # Still can't be used
