# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Queue scheduler with adaptive concurrency scaling."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class QueueTask:
    """Represents a task in the queue."""

    task_id: str
    priority: TaskPriority
    created_at: float
    coro: Callable[[], Awaitable[Any]]
    retry_count: int = 0
    max_retries: int = 3
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize task after creation."""
        if self.created_at == 0:
            self.created_at = time.time()


@dataclass
class QueueMetrics:
    """Queue performance metrics."""

    queue_depth: int = 0
    active_workers: int = 0
    max_workers: int = 5
    min_workers: int = 2
    tasks_processed: int = 0
    tasks_failed: int = 0
    avg_processing_time: float = 0.0
    p95_processing_time: float = 0.0
    last_scale_up: float = 0.0
    last_scale_down: float = 0.0
    scale_decisions: int = 0


class AdaptiveQueueScheduler:
    """Queue scheduler with adaptive concurrency scaling (2→5 workers)."""

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 5,
        latency_threshold_ms: float = 400.0,
        scale_up_threshold_ms: float = 600.0,
        scale_down_threshold_ms: float = 200.0,
        scale_cooldown_seconds: float = 10.0,
        metrics_window_size: int = 100,
    ):
        """Initialize adaptive queue scheduler.

        Args:
            min_workers: Minimum number of concurrent workers
            max_workers: Maximum number of concurrent workers
            latency_threshold_ms: Target latency threshold for scaling decisions
            scale_up_threshold_ms: Latency threshold for scaling up
            scale_down_threshold_ms: Latency threshold for scaling down
            scale_cooldown_seconds: Minimum time between scaling decisions
            metrics_window_size: Number of recent tasks to track for metrics
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.latency_threshold_ms = latency_threshold_ms
        self.scale_up_threshold_ms = scale_up_threshold_ms
        self.scale_down_threshold_ms = scale_down_threshold_ms
        self.scale_cooldown_seconds = scale_cooldown_seconds
        self.metrics_window_size = metrics_window_size

        # Queue and worker management
        self._task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Metrics tracking
        self._metrics = QueueMetrics(min_workers=min_workers, max_workers=max_workers)
        self._processing_times: list[float] = []
        self._last_metrics_update = time.time()

        # Adaptive scaling state
        self._current_workers = min_workers
        self._last_scale_decision = 0.0
        self._consecutive_high_latency = 0
        self._consecutive_low_latency = 0

        # Task tracking
        self._active_tasks: dict[str, float] = {}  # task_id -> start_time

    async def start(self) -> None:
        """Start the queue scheduler."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Start initial workers
        await self._scale_workers(self.min_workers)

        # Start metrics collection task
        asyncio.create_task(self._metrics_collector())

        logger.info(
            "Queue scheduler started",
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            latency_threshold_ms=self.latency_threshold_ms,
        )

    async def stop(self) -> None:
        """Stop the queue scheduler gracefully."""
        if not self._running:
            return

        logger.info("Stopping queue scheduler...")

        self._running = False
        self._shutdown_event.set()

        # Wait for all workers to finish current tasks
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        self._current_workers = 0

        logger.info("Queue scheduler stopped", final_metrics=self.get_metrics())

    async def submit_task(
        self,
        task_id: str,
        coro: Callable[[], Awaitable[Any]],
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Submit a task to the queue.

        Args:
            task_id: Unique task identifier
            coro: Coroutine to execute
            priority: Task priority
            max_retries: Maximum retry attempts
            context: Additional task context
        """
        if not self._running:
            raise RuntimeError("Queue scheduler is not running")

        task = QueueTask(
            task_id=task_id,
            priority=priority,
            created_at=time.time(),
            coro=coro,
            max_retries=max_retries,
            context=context or {},
        )

        # Priority queue uses negative priority for max-heap behavior
        priority_value = -priority.value
        await self._task_queue.put((priority_value, task.created_at, task))

        self._metrics.queue_depth = self._task_queue.qsize()

        logger.debug(
            "Task submitted to queue",
            task_id=task_id,
            priority=priority.name,
            queue_depth=self._metrics.queue_depth,
        )

        # Check if we need to scale up due to queue pressure
        await self._evaluate_scaling()

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that processes tasks from the queue.

        Args:
            worker_id: Worker identifier
        """
        logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # Wait for task with timeout to allow graceful shutdown
                try:
                    priority, created_at, task = await asyncio.wait_for(
                        self._task_queue.get(), timeout=1.0
                    )
                except TimeoutError:
                    continue

                # Track task as active IMMEDIATELY after consuming from queue
                # This prevents race condition where drain() sees queue empty
                # and no active tasks before task processing actually starts
                start_time = time.time()
                self._active_tasks[task.task_id] = start_time

                self._metrics.queue_depth = self._task_queue.qsize()

                try:
                    # Execute the task
                    logger.debug(
                        "Processing task",
                        task_id=task.task_id,
                        worker_id=worker_id,
                        priority=task.priority.name,
                        queue_wait_time_ms=(start_time - task.created_at) * 1000,
                    )

                    await task.coro()

                    # Task completed successfully
                    processing_time = (time.time() - start_time) * 1000  # Convert to ms
                    self._record_task_completion(task, processing_time, True)

                    logger.debug(
                        "Task completed successfully",
                        task_id=task.task_id,
                        worker_id=worker_id,
                        processing_time_ms=processing_time,
                    )

                except Exception as e:
                    # Task failed
                    processing_time = (time.time() - start_time) * 1000
                    self._record_task_completion(task, processing_time, False)

                    logger.error(
                        "Task execution failed",
                        task_id=task.task_id,
                        worker_id=worker_id,
                        error=str(e),
                        retry_count=task.retry_count,
                        max_retries=task.max_retries,
                    )

                    # Retry if possible
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        # Re-queue with slight delay
                        await asyncio.sleep(0.1 * task.retry_count)
                        priority_value = -task.priority.value
                        await self._task_queue.put((priority_value, time.time(), task))
                        logger.info(
                            "Task re-queued for retry",
                            task_id=task.task_id,
                            retry_count=task.retry_count,
                        )

                finally:
                    # Clean up task tracking
                    self._active_tasks.pop(task.task_id, None)
                    self._task_queue.task_done()

            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(0.1)

        logger.debug(f"Worker {worker_id} stopped")

    def _record_task_completion(
        self, task: QueueTask, processing_time_ms: float, success: bool
    ) -> None:
        """Record task completion metrics.

        Args:
            task: Completed task
            processing_time_ms: Processing time in milliseconds
            success: Whether task completed successfully
        """
        self._processing_times.append(processing_time_ms)

        # Keep only recent measurements for rolling window
        if len(self._processing_times) > self.metrics_window_size:
            self._processing_times = self._processing_times[-self.metrics_window_size :]

        # Update metrics
        if success:
            self._metrics.tasks_processed += 1
        else:
            self._metrics.tasks_failed += 1

        # Update latency metrics
        if self._processing_times:
            self._metrics.avg_processing_time = sum(self._processing_times) / len(
                self._processing_times
            )

            # Calculate P95
            sorted_times = sorted(self._processing_times)
            p95_index = int(0.95 * len(sorted_times))
            self._metrics.p95_processing_time = sorted_times[
                min(p95_index, len(sorted_times) - 1)
            ]

    async def _evaluate_scaling(self) -> None:
        """Evaluate whether to scale workers up or down."""
        current_time = time.time()

        # Respect cooldown period
        if current_time - self._last_scale_decision < self.scale_cooldown_seconds:
            return

        # Get current metrics
        queue_depth = self._task_queue.qsize()
        current_latency = self._metrics.p95_processing_time

        # Decision logic
        should_scale_up = False
        should_scale_down = False

        # Scale up conditions
        if self._current_workers < self.max_workers and (
            queue_depth > self._current_workers * 2  # Queue pressure
            or current_latency > self.scale_up_threshold_ms
        ):  # High latency
            self._consecutive_high_latency += 1
            self._consecutive_low_latency = 0

            # Scale up after 2 consecutive high latency measurements
            if self._consecutive_high_latency >= 2:
                should_scale_up = True

        # Scale down conditions
        elif (
            self._current_workers > self.min_workers
            and queue_depth == 0  # Empty queue
            and current_latency < self.scale_down_threshold_ms
        ):  # Low latency
            self._consecutive_low_latency += 1
            self._consecutive_high_latency = 0

            # Scale down after 5 consecutive low latency measurements
            if self._consecutive_low_latency >= 5:
                should_scale_down = True

        else:
            # Reset counters if conditions not met
            self._consecutive_high_latency = 0
            self._consecutive_low_latency = 0

        # Execute scaling decision
        if should_scale_up:
            new_worker_count = min(self._current_workers + 1, self.max_workers)
            await self._scale_workers(new_worker_count)
            self._metrics.last_scale_up = current_time
            self._metrics.scale_decisions += 1

            logger.info(
                "Scaled up workers",
                old_workers=self._current_workers,
                new_workers=new_worker_count,
                queue_depth=queue_depth,
                p95_latency_ms=current_latency,
                trigger="high_latency"
                if current_latency > self.scale_up_threshold_ms
                else "queue_pressure",
            )

        elif should_scale_down:
            new_worker_count = max(self._current_workers - 1, self.min_workers)
            await self._scale_workers(new_worker_count)
            self._metrics.last_scale_down = current_time
            self._metrics.scale_decisions += 1

            logger.info(
                "Scaled down workers",
                old_workers=self._current_workers,
                new_workers=new_worker_count,
                queue_depth=queue_depth,
                p95_latency_ms=current_latency,
                trigger="low_utilization",
            )

        if should_scale_up or should_scale_down:
            self._last_scale_decision = current_time
            self._consecutive_high_latency = 0
            self._consecutive_low_latency = 0

    async def _scale_workers(self, target_count: int) -> None:
        """Scale workers to target count.

        Args:
            target_count: Target number of workers
        """
        current_count = len(self._workers)

        if target_count > current_count:
            # Scale up - start new workers
            for i in range(current_count, target_count):
                worker = asyncio.create_task(self._worker(i))
                self._workers.append(worker)

        elif target_count < current_count:
            # Scale down - cancel excess workers
            workers_to_remove = self._workers[target_count:]
            self._workers = self._workers[:target_count]

            for worker in workers_to_remove:
                worker.cancel()

            # Wait for cancelled workers to finish
            if workers_to_remove:
                await asyncio.gather(*workers_to_remove, return_exceptions=True)

        self._current_workers = target_count
        self._metrics.active_workers = len([w for w in self._workers if not w.done()])

    async def _metrics_collector(self) -> None:
        """Background task to periodically evaluate scaling and update metrics."""
        while self._running:
            try:
                await asyncio.sleep(1.0)  # Evaluate every second

                if self._running:
                    await self._evaluate_scaling()

                    # Update active metrics
                    self._metrics.queue_depth = self._task_queue.qsize()
                    self._metrics.active_workers = len(
                        [w for w in self._workers if not w.done()]
                    )

            except Exception as e:
                logger.error(f"Metrics collector error: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get current queue metrics.

        Returns:
            Dictionary with current metrics
        """
        return {
            "queue_depth": self._metrics.queue_depth,
            "active_workers": self._metrics.active_workers,
            "max_workers": self._metrics.max_workers,
            "min_workers": self._metrics.min_workers,
            "tasks_processed": self._metrics.tasks_processed,
            "tasks_failed": self._metrics.tasks_failed,
            "avg_processing_time_ms": round(self._metrics.avg_processing_time, 2),
            "p95_processing_time_ms": round(self._metrics.p95_processing_time, 2),
            "scale_decisions": self._metrics.scale_decisions,
            "last_scale_up": self._metrics.last_scale_up,
            "last_scale_down": self._metrics.last_scale_down,
            "active_tasks": len(self._active_tasks),
            "latency_threshold_ms": self.latency_threshold_ms,
            "is_running": self._running,
        }

    # Compatibility methods for tests (T066, T067)
    async def submit(
        self,
        coro: Callable[[], Awaitable[Any]],
        task_id: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Submit a task to the queue (compatibility alias for submit_task).

        Args:
            coro: Coroutine to execute
            task_id: Unique task identifier (generated if not provided)
            priority: Task priority
            max_retries: Maximum retry attempts
            context: Additional task context
        """
        if task_id is None:
            import uuid

            task_id = f"task_{uuid.uuid4().hex[:8]}"
        return await self.submit_task(task_id, coro, priority, max_retries, context)

    async def shutdown(self, timeout: int = 30) -> None:
        """Shutdown the queue scheduler (compatibility method for tests).

        Args:
            timeout: Maximum time to wait for shutdown (unused, kept for compatibility)
        """
        await self.stop()

    def get_queue_health(self) -> dict[str, Any]:
        """Get queue health status (compatibility alias for get_queue_status).

        Returns:
            Dictionary with queue health/status
        """
        return self.get_queue_status()

    def get_queue_status(self) -> dict[str, Any]:
        """Get detailed queue status.

        Returns:
            Dictionary with queue status
        """
        return {
            "queue_size": self._task_queue.qsize(),
            "active_tasks": len(self._active_tasks),
            "worker_count": len(self._workers),
            "running_workers": len([w for w in self._workers if not w.done()]),
            "processing_times_count": len(self._processing_times),
            "consecutive_high_latency": self._consecutive_high_latency,
            "consecutive_low_latency": self._consecutive_low_latency,
            "last_scale_decision": self._last_scale_decision,
            "cooldown_remaining": max(
                0,
                self.scale_cooldown_seconds - (time.time() - self._last_scale_decision),
            ),
        }


# Global queue scheduler instance
_queue_scheduler: AdaptiveQueueScheduler | None = None


def get_queue_scheduler() -> AdaptiveQueueScheduler:
    """Get the global queue scheduler instance."""
    global _queue_scheduler
    if _queue_scheduler is None:
        _queue_scheduler = AdaptiveQueueScheduler()
    return _queue_scheduler


async def initialize_queue_scheduler() -> None:
    """Initialize and start the global queue scheduler."""
    scheduler = get_queue_scheduler()
    await scheduler.start()


async def shutdown_queue_scheduler() -> None:
    """Shutdown the global queue scheduler."""
    global _queue_scheduler
    if _queue_scheduler:
        await _queue_scheduler.stop()
        _queue_scheduler = None
