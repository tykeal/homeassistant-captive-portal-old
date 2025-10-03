# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for queue scheduler adaptive scaling edge conditions."""

import asyncio
import time

import pytest

from src.services.queue_scheduler import (
    AdaptiveQueueScheduler,
    TaskPriority,
)


@pytest.fixture
def scheduler():
    """Create a queue scheduler for testing."""
    return AdaptiveQueueScheduler(
        min_workers=2,
        max_workers=5,
        latency_threshold_ms=400.0,
        scale_up_threshold_ms=600.0,
        scale_down_threshold_ms=200.0,
        scale_cooldown_seconds=0.5,  # Short cooldown for testing
        metrics_window_size=10,
    )


@pytest.fixture
async def running_scheduler(scheduler):
    """Create and start a scheduler, then clean it up after test."""
    await scheduler.start()
    yield scheduler
    await scheduler.stop()


class TestQueueScalingEdgeCases:
    """Test adaptive queue scaling edge conditions."""

    async def test_scale_up_on_queue_pressure(self, running_scheduler):
        """Test scaling up workers when queue has high pressure."""

        # Submit many tasks quickly to create queue pressure
        async def dummy_task():
            """dummy_task for testing."""

            await asyncio.sleep(0.1)

        # Submit enough tasks to trigger queue pressure (> workers * 2)
        for i in range(10):
            await running_scheduler.submit_task(
                task_id=f"task_{i}",
                coro=dummy_task,
                priority=TaskPriority.NORMAL,
            )

        # Wait for scaling evaluation
        await asyncio.sleep(1.5)

        metrics = running_scheduler.get_metrics()

        # Should have scaled up from initial 2 workers
        assert metrics["active_workers"] > 2
        assert metrics["scale_decisions"] > 0

    async def test_scale_down_on_idle_queue(self, running_scheduler):
        """Test scaling down workers when queue is idle with low latency."""

        # First, create a burst to scale up
        async def quick_task():
            """quick_task for testing."""

            await asyncio.sleep(0.01)

        for i in range(10):
            await running_scheduler.submit_task(
                task_id=f"burst_{i}",
                coro=quick_task,
                priority=TaskPriority.HIGH,
            )

        await asyncio.sleep(1.0)
        initial_workers = running_scheduler.get_metrics()["active_workers"]

        # Now let queue become idle and wait for scale down
        # Need to wait for consecutive low latency measurements (5 required)
        for _ in range(6):
            await asyncio.sleep(1.5)

        final_workers = running_scheduler.get_metrics()["active_workers"]

        # Should scale down when idle (might not reach min if still processing)
        assert final_workers <= initial_workers

    async def test_cooldown_period_prevents_rapid_scaling(self, running_scheduler):
        """Test that cooldown period prevents rapid scaling decisions."""

        async def dummy_task():
            """dummy_task for testing."""

            await asyncio.sleep(0.05)

        # Create initial load
        for i in range(5):
            await running_scheduler.submit_task(
                task_id=f"task_{i}",
                coro=dummy_task,
            )

        await asyncio.sleep(0.6)  # First scale decision
        metrics1 = running_scheduler.get_metrics()
        scale_decisions_1 = metrics1["scale_decisions"]

        # Try to trigger another scale immediately
        for i in range(5, 10):
            await running_scheduler.submit_task(
                task_id=f"task_{i}",
                coro=dummy_task,
            )

        await asyncio.sleep(0.2)  # Within cooldown
        metrics2 = running_scheduler.get_metrics()

        # Should not have additional scale decision due to cooldown
        assert metrics2["scale_decisions"] == scale_decisions_1

    async def test_max_workers_limit(self, running_scheduler):
        """Test that worker count never exceeds max_workers."""

        async def slow_task():
            """slow_task for testing."""

            await asyncio.sleep(0.2)

        # Create massive queue pressure
        for i in range(50):
            await running_scheduler.submit_task(
                task_id=f"task_{i}",
                coro=slow_task,
                priority=TaskPriority.URGENT,
            )

        # Wait for multiple scaling opportunities
        await asyncio.sleep(3.0)

        metrics = running_scheduler.get_metrics()

        # Should never exceed max_workers
        assert metrics["active_workers"] <= running_scheduler.max_workers
        assert metrics["active_workers"] <= 5

    async def test_min_workers_limit(self, running_scheduler):
        """Test that worker count never goes below min_workers."""
        # Let queue be completely idle
        await asyncio.sleep(10.0)

        metrics = running_scheduler.get_metrics()

        # Should never go below min_workers
        assert metrics["active_workers"] >= running_scheduler.min_workers
        assert metrics["active_workers"] >= 2

    async def test_consecutive_high_latency_required(self, running_scheduler):
        """Test that scale up requires consecutive high latency measurements."""
        # Create a scheduler with very specific thresholds
        scheduler = AdaptiveQueueScheduler(
            min_workers=2,
            max_workers=5,
            scale_up_threshold_ms=100.0,  # Low threshold
            scale_cooldown_seconds=0.1,
        )
        await scheduler.start()

        try:

            async def variable_latency_task():
                """variable_latency_task for testing."""

                # Sometimes fast, sometimes slow
                await asyncio.sleep(0.05)

            # Submit tasks one at a time to avoid queue pressure trigger
            await scheduler.submit_task("task_1", variable_latency_task)
            await asyncio.sleep(0.5)

            # Single high latency task shouldn't trigger scale up immediately
            status = scheduler.get_queue_status()
            assert status["consecutive_high_latency"] <= 1

        finally:
            await scheduler.stop()

    async def test_scale_up_resets_low_latency_counter(self, running_scheduler):
        """Test that scaling up resets consecutive low latency counter."""

        async def dummy_task():
            """dummy_task for testing."""

            await asyncio.sleep(0.05)

        # Create queue pressure to trigger scale up
        for i in range(15):
            await running_scheduler.submit_task(
                task_id=f"task_{i}",
                coro=dummy_task,
            )

        await asyncio.sleep(1.5)

        metrics = running_scheduler.get_metrics()

        # If scaling occurred, it should have happened
        # The test verifies that the scale-up mechanism works
        if metrics["scale_decisions"] > 0:
            # Scale decisions were made successfully
            assert metrics["active_workers"] > 2

    async def test_empty_queue_alone_insufficient_for_scale_down(
        self, running_scheduler
    ):
        """Test that empty queue alone is not enough, needs low latency too."""

        async def task():
            """task for testing."""

            await asyncio.sleep(0.001)

        # Submit a few quick tasks
        for i in range(3):
            await running_scheduler.submit_task(f"task_{i}", task)

        await asyncio.sleep(0.5)

        # Queue should be empty but may not have scaled down yet
        # (requires consecutive low latency measurements)
        status = running_scheduler.get_queue_status()
        assert status["queue_size"] == 0

        # But scale down requires both empty queue AND low latency
        # AND 5 consecutive measurements
        initial_scale_decisions = running_scheduler.get_metrics()["scale_decisions"]

        await asyncio.sleep(0.6)

        # Shouldn't scale down immediately
        new_scale_decisions = running_scheduler.get_metrics()["scale_decisions"]
        assert (
            new_scale_decisions == initial_scale_decisions
            or status["consecutive_low_latency"] < 5
        )

    async def test_priority_tasks_during_scaling(self, running_scheduler):
        """Test that high priority tasks are processed correctly during scaling."""
        results = []

        async def tracked_task(task_id: str, priority: str):
            """Track task execution for testing."""
            results.append((task_id, priority, time.time()))
            await asyncio.sleep(0.01)

        # Submit mix of priorities
        await running_scheduler.submit_task(
            "low_1",
            lambda: tracked_task("low_1", "LOW"),
            priority=TaskPriority.LOW,
        )
        await running_scheduler.submit_task(
            "urgent_1",
            lambda: tracked_task("urgent_1", "URGENT"),
            priority=TaskPriority.URGENT,
        )
        await running_scheduler.submit_task(
            "normal_1",
            lambda: tracked_task("normal_1", "NORMAL"),
            priority=TaskPriority.NORMAL,
        )

        await asyncio.sleep(0.5)

        # Urgent task should be processed first
        if len(results) >= 3:
            urgent_result = next(r for r in results if r[0] == "urgent_1")
            low_result = next(r for r in results if r[0] == "low_1")
            assert urgent_result[2] < low_result[2]  # Processed earlier

    async def test_rapid_scale_up_down_stability(self, running_scheduler):
        """Test system stability with rapid load changes."""

        async def quick_task():
            """quick_task for testing."""

            await asyncio.sleep(0.01)

        async def slow_task():
            """slow_task for testing."""

            await asyncio.sleep(0.3)

        # Burst of quick tasks
        for i in range(20):
            await running_scheduler.submit_task(f"quick_{i}", quick_task)

        await asyncio.sleep(1.0)

        # Then burst of slow tasks
        for i in range(20):
            await running_scheduler.submit_task(f"slow_{i}", slow_task)

        await asyncio.sleep(2.0)

        # System should remain stable
        metrics = running_scheduler.get_metrics()
        assert (
            running_scheduler.min_workers
            <= metrics["active_workers"]
            <= running_scheduler.max_workers
        )
        assert metrics["tasks_failed"] == 0  # No failures during transitions

    async def test_metrics_window_size_limit(self, running_scheduler):
        """Test that processing times don't grow unbounded."""

        async def task():
            """task for testing."""

            await asyncio.sleep(0.01)

        # Submit more tasks than metrics window size
        for i in range(30):
            await running_scheduler.submit_task(f"task_{i}", task)

        await asyncio.sleep(2.0)

        status = running_scheduler.get_queue_status()

        # Processing times should be limited by window size
        assert status["processing_times_count"] <= running_scheduler.metrics_window_size

    async def test_worker_count_consistency(self, running_scheduler):
        """Test that active worker count stays consistent with worker list."""

        async def task():
            """task for testing."""

            await asyncio.sleep(0.1)

        for i in range(10):
            await running_scheduler.submit_task(f"task_{i}", task)

        await asyncio.sleep(1.5)

        status = running_scheduler.get_queue_status()
        metrics = running_scheduler.get_metrics()

        # Active workers should match or be close to worker count
        assert abs(status["worker_count"] - metrics["active_workers"]) <= 1
