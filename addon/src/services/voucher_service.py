# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Voucher service for create, expire, and list operations."""

import secrets
import string
from datetime import UTC, datetime

from ..core.logging_config import get_logger
from ..models.domain import Voucher, VoucherStatus
from ..services.audit_logger import get_audit_logger
from ..storage.database import get_db_session
from ..storage.repository import VoucherRepository

logger = get_logger(__name__)


class VoucherService:
    """Service for voucher management operations."""

    def __init__(self) -> None:
        """Initialize voucher service."""
        self.audit_logger = get_audit_logger()

    def _generate_voucher_code(self, length: int = 8) -> str:
        """Generate a secure voucher code.

        Args:
            length: Length of the code

        Returns:
            Generated voucher code
        """
        # Use uppercase letters and digits, excluding confusing characters
        alphabet = string.ascii_uppercase + string.digits
        alphabet = (
            alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
        )

        code = "".join(secrets.choice(alphabet) for _ in range(length))
        return code

    async def create_voucher(
        self,
        duration_hours: int,
        description: str,
        created_by: str,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        user_id: str | None = None,
        **audit_context,
    ) -> Voucher:
        """Create a new voucher.

        Args:
            duration_hours: Duration in hours for grants created from this voucher
            description: Voucher description
            created_by: Creator identifier
            max_uses: Maximum number of uses (-1 for unlimited)
            expires_at: Optional expiry time for the voucher itself
            user_id: User creating the voucher (for audit)
            **audit_context: Additional audit context

        Returns:
            Created voucher

        Raises:
            ValueError: If parameters are invalid
        """
        if duration_hours <= 0:
            raise ValueError("Duration must be positive")

        if max_uses < -1 or max_uses == 0:
            raise ValueError("Max uses must be -1 (unlimited) or positive")

        # Generate unique code
        max_attempts = 10
        for _attempt in range(max_attempts):
            code = self._generate_voucher_code()

            # Check if code already exists
            async with get_db_session() as session:
                repository = VoucherRepository(session)
                existing = await repository.get_by_code(code)

                if not existing:
                    # Code is unique, create voucher
                    voucher = Voucher(
                        code=code,
                        duration_hours=duration_hours,
                        description=description,
                        created_by=created_by,
                        max_uses=max_uses,
                        expires_at=expires_at,
                    )

                    # Save to database
                    await repository.create(voucher)

                    # Log creation
                    await self.audit_logger.log_voucher_created(
                        voucher=voucher, user_id=user_id, **audit_context
                    )

                    logger.info(
                        "Voucher created",
                        voucher_id=voucher.voucher_id,
                        code=voucher.code,
                        duration_hours=duration_hours,
                        max_uses=max_uses,
                        created_by=created_by,
                    )

                    return voucher

        # If we get here, we couldn't generate a unique code
        raise RuntimeError(
            "Failed to generate unique voucher code after maximum attempts"
        )

    async def get_voucher_by_id(self, voucher_id: str) -> Voucher | None:
        """Get voucher by ID.

        Args:
            voucher_id: Voucher ID

        Returns:
            Voucher if found, None otherwise
        """
        async with get_db_session() as session:
            repository = VoucherRepository(session)
            return await repository.get_by_id(voucher_id)

    async def get_voucher_by_code(self, code: str) -> Voucher | None:
        """Get voucher by code.

        Args:
            code: Voucher code

        Returns:
            Voucher if found, None otherwise
        """
        async with get_db_session() as session:
            repository = VoucherRepository(session)
            return await repository.get_by_code(code)

    async def validate_voucher_code(
        self, code: str
    ) -> tuple[bool, str | None, Voucher | None]:
        """Validate a voucher code for use.

        Args:
            code: Voucher code to validate

        Returns:
            Tuple of (is_valid, error_message, voucher)
        """
        voucher = await self.get_voucher_by_code(code)

        if not voucher:
            return False, "Invalid voucher code", None

        if not voucher.is_valid():
            # Determine specific reason
            if voucher.status != VoucherStatus.ACTIVE:
                return False, f"Voucher is {voucher.status.value}", voucher

            now = datetime.now(UTC)
            if voucher.expires_at and now > voucher.expires_at:
                return False, "Voucher has expired", voucher

            if voucher.max_uses > 0 and voucher.uses_count >= voucher.max_uses:
                return False, "Voucher usage limit reached", voucher

            return False, "Voucher is not valid", voucher

        return True, None, voucher

    async def use_voucher(self, voucher: Voucher, **audit_context) -> Voucher:
        """Mark voucher as used (increment use count).

        Args:
            voucher: Voucher to use
            **audit_context: Additional audit context

        Returns:
            Updated voucher

        Raises:
            ValueError: If voucher is not valid for use
        """
        if not voucher.is_valid():
            raise ValueError("Voucher is not valid for use")

        # Update voucher
        voucher.use_voucher()

        # Save to database
        async with get_db_session() as session:
            repository = VoucherRepository(session)
            await repository.update(voucher)

        logger.info(
            "Voucher used",
            voucher_id=voucher.voucher_id,
            code=voucher.code,
            uses_count=voucher.uses_count,
            max_uses=voucher.max_uses,
            status=voucher.status.value,
        )

        return voucher

    async def deactivate_voucher(
        self, voucher_id: str, reason: str, user_id: str | None = None, **audit_context
    ) -> Voucher | None:
        """Deactivate a voucher.

        Args:
            voucher_id: Voucher ID to deactivate
            reason: Reason for deactivation
            user_id: User deactivating the voucher
            **audit_context: Additional audit context

        Returns:
            Updated voucher if found, None otherwise
        """
        voucher = await self.get_voucher_by_id(voucher_id)
        if not voucher:
            return None

        # Deactivate voucher
        voucher.deactivate()

        # Save to database
        async with get_db_session() as session:
            repository = VoucherRepository(session)
            await repository.update(voucher)

        # Log deactivation
        await self.audit_logger.log_voucher_deactivated(
            voucher=voucher, reason=reason, user_id=user_id, **audit_context
        )

        logger.info(
            "Voucher deactivated",
            voucher_id=voucher.voucher_id,
            code=voucher.code,
            reason=reason,
            deactivated_by=user_id,
        )

        return voucher

    async def list_vouchers(
        self, status: VoucherStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[Voucher]:
        """List vouchers with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of vouchers
        """
        async with get_db_session() as session:
            repository = VoucherRepository(session)
            return await repository.list_vouchers(
                status=status, limit=limit, offset=offset
            )

    async def expire_vouchers(self) -> int:
        """Expire vouchers that are past their expiry time.

        Returns:
            Number of vouchers expired
        """
        # Get active vouchers that should be expired
        active_vouchers = await self.list_vouchers(status=VoucherStatus.ACTIVE)

        now = datetime.now(UTC)
        expired_count = 0

        for voucher in active_vouchers:
            if voucher.expires_at and now > voucher.expires_at:
                voucher.status = VoucherStatus.EXPIRED

                # Save to database
                async with get_db_session() as session:
                    repository = VoucherRepository(session)
                    await repository.update(voucher)

                # Log expiry
                await self.audit_logger.log_voucher_deactivated(
                    voucher=voucher, reason="Automatic expiry", user_id="system"
                )

                expired_count += 1

                logger.info(
                    "Voucher automatically expired",
                    voucher_id=voucher.voucher_id,
                    code=voucher.code,
                    expires_at=voucher.expires_at.isoformat(),
                )

        if expired_count > 0:
            logger.info("Voucher expiry check completed", expired_count=expired_count)

        return expired_count

    async def get_voucher_stats(self) -> dict:
        """Get voucher statistics.

        Returns:
            Dictionary with voucher statistics
        """
        all_vouchers = await self.list_vouchers(limit=10000)  # Get all vouchers

        stats = {
            "total": len(all_vouchers),
            "active": 0,
            "inactive": 0,
            "expired": 0,
            "total_uses": 0,
            "available_uses": 0,
        }

        for voucher in all_vouchers:
            stats[voucher.status.value] += 1
            stats["total_uses"] += voucher.uses_count

            if voucher.status == VoucherStatus.ACTIVE and voucher.is_valid():
                if voucher.max_uses == -1:
                    stats["available_uses"] = float("inf")  # type: ignore[assignment]
                elif stats["available_uses"] != float("inf"):
                    stats["available_uses"] += voucher.max_uses - voucher.uses_count

        return stats


# Global voucher service instance
_voucher_service: VoucherService | None = None


def get_voucher_service() -> VoucherService:
    """Get the global voucher service instance."""
    global _voucher_service
    if _voucher_service is None:
        _voucher_service = VoucherService()
    return _voucher_service
