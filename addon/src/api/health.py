# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Health check API router."""

from fastapi import APIRouter

from ..core.logging_config import get_logger
from ..services.grant_manager import get_grant_manager
from ..services.queue_integration import get_queued_operations
from .models import HealthResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint for monitoring and orchestration (T037).

    Provides comprehensive health status including:
    - Queue depth and processing status
    - Controller connectivity and operational status
    - Active and pending grants counts

    Returns:
        Health response with status and detailed metrics
    """
    try:
        # Get queue status
        queued_ops = get_queued_operations()
        queue_metrics = await queued_ops.get_queue_health()

        # Get grant stats
        grant_manager = get_grant_manager()
        grant_stats = await grant_manager.get_stats()

        # Check controller health (T037: controller status sample)
        from ..controllers.factory import get_controller

        controller = get_controller()
        controller_healthy = False
        try:
            controller_healthy = await controller.health_check()
        except Exception as controller_error:
            logger.warning(
                "Controller health check failed", error=str(controller_error)
            )

        # Determine overall health
        health_status = "healthy"
        controller_status = "operational" if controller_healthy else "unreachable"

        # Check queue depth
        queue_depth = queue_metrics.get("queue_depth", 0)
        if queue_depth > 100:
            health_status = "degraded"

        # If controller is down, overall status is degraded
        if not controller_healthy:
            health_status = "degraded"

        return HealthResponse(
            status=health_status,
            queue_depth=queue_depth,
            controller_status=controller_status,
            details={
                "active_grants": grant_stats.get("current_active", 0),
                "pending_grants": grant_stats.get("pending", 0),
                "queue_metrics": queue_metrics,
                "controller_healthy": controller_healthy,
            },
        )

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return HealthResponse(
            status="unhealthy",
            details={"error": str(e)},
        )


@router.get("/metrics")
async def get_metrics() -> dict:
    """Prometheus-style metrics endpoint."""
    try:
        # Get queue metrics
        queued_ops = get_queued_operations()
        queue_metrics = await queued_ops.get_queue_health()

        # Get grant stats
        grant_manager = get_grant_manager()
        grant_stats = await grant_manager.get_stats()

        # Format as Prometheus-style metrics
        metrics = []

        # Grant metrics
        metrics.append(f"captive_portal_grants_total {grant_stats.get('total', 0)}")
        metrics.append(
            f"captive_portal_grants_active {grant_stats.get('current_active', 0)}"
        )
        metrics.append(f"captive_portal_grants_pending {grant_stats.get('pending', 0)}")
        metrics.append(f"captive_portal_grants_expired {grant_stats.get('expired', 0)}")
        metrics.append(f"captive_portal_grants_revoked {grant_stats.get('revoked', 0)}")

        # Queue metrics
        metrics.append(
            f"captive_portal_queue_depth {queue_metrics.get('queue_depth', 0)}"
        )
        metrics.append(
            f"captive_portal_queue_workers {queue_metrics.get('active_workers', 0)}"
        )

        # Return as plain text (Prometheus format)
        return {"metrics": "\n".join(metrics)}

    except Exception as e:
        logger.error("Metrics collection failed", error=str(e))
        return {"error": str(e)}
