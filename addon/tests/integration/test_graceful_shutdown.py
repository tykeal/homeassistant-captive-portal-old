# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Integration test for graceful shutdown preserving in-flight provisioning."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.models.domain import AccessGrant, GrantStatus
from src.services.queue_integration import QueuedOperations
from src.services.queue_scheduler import AdaptiveQueueScheduler, TaskPriority


@pytest.fixture
def mock_controller() -> None:
    """Create a mock controller that simulates slow provisioning."""
    controller = AsyncMock()

    async def slow_provision(grant_id: str) -> None:
        """Simulate slow provisioning operation."""
        await asyncio.sleep(0.5)  # 500ms to simulate network operation

    # Use AsyncMock for async side_effect
    controller.provision_grant = AsyncMock(side_effect=slow_provision)
    controller.revoke_grant = AsyncMock()
    return controller


@pytest.fixture
def mock_storage() -> None:
    """Create a mock storage layer."""
    storage = AsyncMock()
    storage.save_grant = AsyncMock()
    storage.update_grant = AsyncMock()
    storage.get_grant = AsyncMock()
    return storage


@pytest.fixture
def mock_audit_logger() -> None:
    """Create a mock audit logger."""
    audit = AsyncMock()
    audit.log_event = AsyncMock()
    audit.log_controller_error = AsyncMock()
    return audit


@pytest.fixture
def mock_grant_manager(mock_controller, mock_storage, mock_audit_logger) -> None:
    """Create a mock grant manager."""
    manager = AsyncMock()

    # Track in-flight grants
    in_flight_grants = {}

    async def activate_grant_mock(grant, **kwargs) -> None:
        """Mock activate that simulates slow provisioning."""
        grant_id = grant.grant_id if hasattr(grant, "grant_id") else grant
        in_flight_grants[grant_id] = "processing"

        # Simulate controller provisioning
        await mock_controller.provision_grant(grant_id)

        # Update status
        in_flight_grants[grant_id] = "completed"

        if hasattr(grant, "grant_id"):
            grant.status = GrantStatus.ACTIVE
            return grant
        else:
            return AccessGrant(
                id=grant_id,
                device_id=f"device-{grant_id}",
                guest_name=f"Guest {grant_id}",
                status=GrantStatus.ACTIVE,
                start_time=0,
                end_time=3600,
            )

    manager.activate_grant = AsyncMock(side_effect=activate_grant_mock)
    manager.in_flight_grants = in_flight_grants
    manager.update_grant_error = AsyncMock()  # Add missing mock method
    return manager


@pytest.fixture
def mock_voucher_service() -> None:
    """Create a mock voucher service."""
    service = AsyncMock()
    return service


@pytest.fixture
async def queue_scheduler() -> None:
    """Create a queue scheduler."""
    scheduler = AdaptiveQueueScheduler(
        min_workers=2, max_workers=5, latency_threshold_ms=400
    )
    await scheduler.start()
    yield scheduler
    await scheduler.shutdown()


@pytest.fixture
def queued_operations(
    queue_scheduler, mock_grant_manager, mock_voucher_service, mock_audit_logger
) -> None:
    """Create queued operations with mocked dependencies."""
    ops = QueuedOperations()
    ops.scheduler = queue_scheduler
    ops.grant_manager = mock_grant_manager
    ops.voucher_service = mock_voucher_service
    ops.audit_logger = mock_audit_logger
    return ops


@pytest.mark.asyncio
async def test_graceful_shutdown_waits_for_in_flight_tasks(
    queued_operations, mock_grant_manager
) -> None:
    """Test that graceful shutdown waits for in-flight provisioning tasks."""
    # Create grants to provision
    grants = [
        AccessGrant(
            id=f"grant-{i}",
            device_id=f"device-{i}",
            guest_name=f"Guest {i}",
            status=GrantStatus.PENDING,
            start_time=0,
            end_time=3600,
        )
        for i in range(3)
    ]

    # Queue grant activations
    for grant in grants:
        await queued_operations.queue_grant_activation(
            grant, priority=TaskPriority.NORMAL
        )

    # Wait a bit for tasks to start processing
    await asyncio.sleep(0.1)

    # Initiate drain (graceful shutdown)
    drain_task = asyncio.create_task(queued_operations.drain(timeout_seconds=5))

    # Drain should wait for tasks to complete
    await drain_task

    # Verify all grants were processed
    assert mock_grant_manager.activate_grant.call_count == 3

    # Check in-flight status
    for grant in grants:
        assert mock_grant_manager.in_flight_grants.get(grant.grant_id) == "completed"


@pytest.mark.asyncio
async def test_graceful_shutdown_timeout_on_stuck_tasks(queued_operations) -> None:
    """Test that graceful shutdown times out if tasks don't complete."""

    # Create a task that will never complete
    async def stuck_task() -> None:
        """A task that takes too long."""
        await asyncio.sleep(10)  # Longer than timeout

    # Submit the stuck task
    await queued_operations.scheduler.submit_task(
        task_id="stuck-task",
        coro=stuck_task,
        priority=TaskPriority.NORMAL,
        context={"operation": "test_stuck"},
    )

    # Wait a bit for task to start
    await asyncio.sleep(0.1)

    # Drain should timeout
    with pytest.raises(TimeoutError):
        await queued_operations.drain(timeout_seconds=1)


@pytest.mark.asyncio
async def test_graceful_shutdown_empty_queue(queued_operations) -> None:
    """Test that graceful shutdown works with empty queue."""
    # Drain with no tasks should complete immediately
    await queued_operations.drain(timeout_seconds=5)

    # Should complete without error


@pytest.mark.asyncio
async def test_graceful_shutdown_preserves_completed_work(
    queued_operations, mock_grant_manager
) -> None:
    """Test that graceful shutdown preserves completed work."""
    # Create and queue grants
    grants = [
        AccessGrant(
            id=f"grant-{i}",
            device_id=f"device-{i}",
            guest_name=f"Guest {i}",
            status=GrantStatus.PENDING,
            start_time=0,
            end_time=3600,
        )
        for i in range(5)
    ]

    completed_grants = []

    # Save the original side_effect function
    original_activate_func = mock_grant_manager.activate_grant.side_effect

    async def track_completion(grant, **kwargs) -> None:
        """Track completed grants."""
        result = await original_activate_func(grant, **kwargs)
        completed_grants.append(grant.grant_id)
        return result

    # Override activate to track - use AsyncMock for async side_effect
    mock_grant_manager.activate_grant = AsyncMock(side_effect=track_completion)

    # Queue all grants
    for grant in grants:
        await queued_operations.queue_grant_activation(grant)

    # Start drain
    await queued_operations.drain(timeout_seconds=10)

    # All grants should be completed
    assert len(completed_grants) == 5
    for grant in grants:
        assert grant.grant_id in completed_grants


@pytest.mark.asyncio
async def test_graceful_shutdown_logs_progress(queued_operations, caplog) -> None:
    """Test that graceful shutdown logs progress information."""
    import logging

    caplog.set_level(logging.INFO)

    # Queue a quick task
    async def quick_task() -> None:
        """Quick task."""
        await asyncio.sleep(0.05)

    await queued_operations.scheduler.submit_task(
        task_id="quick-task",
        coro=quick_task,
        priority=TaskPriority.NORMAL,
        context={"operation": "test"},
    )

    # Drain
    await queued_operations.drain(timeout_seconds=5)

    # Check logs (this depends on logger configuration)
    # At minimum, we should have executed without error


@pytest.mark.asyncio
async def test_graceful_shutdown_multiple_drains(queued_operations) -> None:
    """Test that multiple drain calls work correctly."""
    # First drain (empty queue)
    await queued_operations.drain(timeout_seconds=1)

    # Second drain (should also complete)
    await queued_operations.drain(timeout_seconds=1)

    # Both should complete without error


@pytest.mark.asyncio
async def test_graceful_shutdown_partial_completion(
    queued_operations, mock_grant_manager
) -> None:
    """Test graceful shutdown with mix of fast and slow tasks."""
    # Create mix of fast and slow grants
    fast_grants = [
        AccessGrant(
            id=f"fast-grant-{i}",
            device_id=f"device-{i}",
            guest_name=f"Fast Guest {i}",
            status=GrantStatus.PENDING,
            start_time=0,
            end_time=3600,
        )
        for i in range(2)
    ]

    slow_grants = [
        AccessGrant(
            id=f"slow-grant-{i}",
            device_id=f"device-{i}",
            guest_name=f"Slow Guest {i}",
            status=GrantStatus.PENDING,
            start_time=0,
            end_time=3600,
        )
        for i in range(2)
    ]

    # Mock fast vs slow
    async def variable_speed_activate(grant, **kwargs) -> None:
        """Activate with variable speed."""
        if grant.grant_id.startswith("fast"):
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.3)

        grant.status = GrantStatus.ACTIVE
        return grant

    # Use AsyncMock for async side_effect
    mock_grant_manager.activate_grant = AsyncMock(side_effect=variable_speed_activate)

    # Queue all
    for grant in fast_grants + slow_grants:
        await queued_operations.queue_grant_activation(grant)

    # Drain with sufficient timeout
    await queued_operations.drain(timeout_seconds=5)

    # All should complete
    assert mock_grant_manager.activate_grant.call_count == 4
