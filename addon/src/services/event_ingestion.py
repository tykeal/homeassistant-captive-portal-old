# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Event ingestion service for Rental Control integration events."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from ..core.logging_config import get_logger
from ..models.domain import GrantSource
from ..services.grant_manager import get_grant_manager

logger = get_logger(__name__)


class EventIngestionService:
    """Service for ingesting Rental Control integration events.

    This service watches for new booking events from the Rental Control
    integration and creates corresponding network access grants.

    FR-001: Obtain guest access grant inputs from Rental Control events
    """

    def __init__(self):
        """Initialize the event ingestion service."""
        self._running = False
        self._watch_task: asyncio.Task | None = None
        self._poll_interval_seconds = 60  # Poll every minute

    async def start(self) -> None:
        """Start the event ingestion service."""
        if self._running:
            logger.warning("Event ingestion service already running")
            return

        self._running = True
        logger.info("Starting Rental Control event ingestion service")

        # Start background task
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop the event ingestion service."""
        if not self._running:
            return

        logger.info("Stopping Rental Control event ingestion service")
        self._running = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        logger.info("Event ingestion service stopped")

    async def _watch_loop(self) -> None:
        """Background task that polls for new Rental Control events."""
        logger.info("Event watch loop started")

        while self._running:
            try:
                await self._check_for_new_events()
            except Exception as e:
                logger.error(
                    "Error in event watch loop",
                    error=str(e),
                )

            # Wait before next poll
            try:
                await asyncio.sleep(self._poll_interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("Event watch loop stopped")

    async def _check_for_new_events(self) -> None:
        """Check for new Rental Control events and process them.

        This is a stub implementation. In a real system, this would:
        1. Query Home Assistant for new booking events
        2. Check Rental Control integration state
        3. Detect new/updated bookings since last check
        4. Create grants for new bookings
        """
        # TODO: Implement actual HA event listening
        # For now, this is a placeholder that logs the check

        logger.debug("Checking for new Rental Control events")

        # Stub: In real implementation would:
        # events = await self._fetch_rental_control_events()
        # for event in events:
        #     await self._process_event(event)

    async def ingest_rental_control_event(self, event_data: dict[str, Any]) -> str:
        """Manually ingest a Rental Control event and create a grant.

        This method provides a way to manually trigger event ingestion,
        useful for testing and initial implementation.

        Args:
            event_data: Event data containing booking information
                Required fields:
                - booking_id: Unique booking identifier
                - start_time: ISO 8601 timestamp for access start
                - end_time: ISO 8601 timestamp for access end
                - guest_name: Guest name
                Optional fields:
                - device_mac: Device MAC address

        Returns:
            Created grant ID

        Raises:
            ValueError: If required fields are missing or invalid
        """
        logger.info(
            "Ingesting Rental Control event",
            booking_id=event_data.get("booking_id"),
        )

        # Validate required fields
        required_fields = ["booking_id", "start_time", "end_time", "guest_name"]
        for field in required_fields:
            if field not in event_data:
                raise ValueError(f"Missing required field: {field}")

        # Parse timestamps
        try:
            if isinstance(event_data["start_time"], str):
                start_time = datetime.fromisoformat(
                    event_data["start_time"].replace("Z", "+00:00")
                )
            else:
                start_time = event_data["start_time"]

            if isinstance(event_data["end_time"], str):
                end_time = datetime.fromisoformat(
                    event_data["end_time"].replace("Z", "+00:00")
                )
            else:
                end_time = event_data["end_time"]
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp format: {e}") from e

        # Check for duplicate booking
        grant_manager = get_grant_manager()
        existing_grants = await grant_manager.list_grants(limit=10000)
        for existing in existing_grants:
            if existing.booking_id == event_data["booking_id"]:
                logger.warning(
                    "Grant already exists for booking",
                    booking_id=event_data["booking_id"],
                    grant_id=existing.grant_id,
                )
                return existing.grant_id

        # Create grant
        grant = await grant_manager.create_grant(
            booking_id=event_data["booking_id"],
            guest_name=event_data["guest_name"],
            start_time=start_time,
            end_time=end_time,
            source=GrantSource.RENTAL_CONTROL,
            device_mac=event_data.get("device_mac"),
        )

        logger.info(
            "Created grant from Rental Control event",
            grant_id=grant.grant_id,
            booking_id=event_data["booking_id"],
            status=grant.status.value,
        )

        # If start time is now or past, attempt activation
        now = datetime.now(UTC)
        if start_time <= now < end_time:
            try:
                activated_grant = await grant_manager.activate_grant(grant)
                logger.info(
                    "Grant activated immediately",
                    grant_id=activated_grant.grant_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to activate grant immediately",
                    grant_id=grant.grant_id,
                    error=str(e),
                )
                # Grant remains in pending state for retry

        return grant.grant_id

    async def process_pending_activations(self) -> int:
        """Process pending grants that should now be activated.

        This method checks all pending grants and activates those whose
        start time has arrived.

        Returns:
            Number of grants activated

        Raises:
            Exception: On database or controller errors
        """
        grant_manager = get_grant_manager()
        now = datetime.now(UTC)

        # Get all pending grants
        all_grants = await grant_manager.list_grants(limit=10000)
        pending_grants = [g for g in all_grants if g.status.value == "pending"]

        activated_count = 0

        for grant in pending_grants:
            # Check if start time has arrived
            if grant.start_time <= now < grant.end_time:
                try:
                    await grant_manager.activate_grant(grant)
                    activated_count += 1

                    logger.info(
                        "Activated pending grant",
                        grant_id=grant.grant_id,
                        booking_id=grant.booking_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to activate pending grant",
                        grant_id=grant.grant_id,
                        error=str(e),
                    )
                    # Will retry on next check

        if activated_count > 0:
            logger.info(
                "Pending grant activation complete",
                activated_count=activated_count,
            )

        return activated_count


# Global service instance
_event_ingestion_service: EventIngestionService | None = None


def get_event_ingestion_service() -> EventIngestionService:
    """Get the global event ingestion service instance."""
    global _event_ingestion_service
    if _event_ingestion_service is None:
        _event_ingestion_service = EventIngestionService()
    return _event_ingestion_service
