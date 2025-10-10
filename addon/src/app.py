# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Main FastAPI application for the captive portal addon."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    audit_router,
    grants_router,
    health_router,
    system_router,
    theme_router,
    vouchers_router,
)
from .core.config import AddonConfig, get_config
from .core.logging_config import configure_logging, get_logger
from .portal import portal_router
from .services.event_ingestion import get_event_ingestion_service
from .services.expiry_scheduler import get_expiry_scheduler
from .services.grant_manager import get_grant_manager
from .services.queue_integration import get_queued_operations
from .storage.database import initialize_database

logger = get_logger(__name__)


def validate_startup_config(config: AddonConfig) -> None:
    """Validate addon configuration at startup (T036).

    Performs comprehensive validation of controller and theme configuration
    to ensure all required settings are present and valid before starting services.

    Args:
        config: Addon configuration to validate

    Raises:
        ValueError: If configuration is invalid
    """
    # Validate controller configuration
    if not config.controller.url:
        raise ValueError("Controller URL is required")

    if not config.controller.username or not config.controller.password:
        raise ValueError("Controller credentials (username/password) are required")

    # Validate controller type
    if config.controller.type not in ("omada",):
        raise ValueError(
            f"Unsupported controller type: {config.controller.type}. "
            "Supported types: omada"
        )

    # Validate theme configuration
    if not config.theme.portal_title or len(config.theme.portal_title.strip()) == 0:
        raise ValueError("Theme portal_title cannot be empty")

    # Validate hex color format for theme colors
    for color_name, color_value in [
        ("background_color", config.theme.background_color),
        ("primary_color", config.theme.primary_color),
    ]:
        if not color_value.startswith("#") or len(color_value) != 7:
            raise ValueError(
                f"Theme {color_name} must be in hex format (#rrggbb), "
                f"got: {color_value}"
            )
        try:
            int(color_value[1:], 16)
        except ValueError as e:
            raise ValueError(
                f"Theme {color_name} has invalid hex value: {color_value}"
            ) from e

    # Validate optional logo URL if present
    if config.theme.logo_url:
        logo_str = str(config.theme.logo_url)
        if not logo_str.startswith(("http://", "https://")):
            raise ValueError(
                f"Theme logo_url must be a valid HTTP/HTTPS URL, got: {logo_str}"
            )

    logger.debug(
        "Configuration validation passed",
        controller_type=config.controller.type,
        controller_url=str(config.controller.url),
        portal_title=config.theme.portal_title,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager for startup and shutdown tasks."""
    # Startup
    logger.info("Starting captive portal addon")

    try:
        # Initialize and validate configuration (T036)
        config = get_config()
        validate_startup_config(config)
        configure_logging(log_level=config.log_level, json_format=True)
        logger.info("Configuration validated successfully")
    except (ValueError, RuntimeError) as e:
        logger.error("Configuration validation failed", error=str(e))
        raise RuntimeError(f"Invalid configuration: {e}") from e

    # Initialize database
    await initialize_database()
    logger.info("Database initialized")

    # Start event ingestion service for Rental Control integration
    event_service = get_event_ingestion_service()
    await event_service.start()
    logger.info("Event ingestion service started")

    # Start expiry scheduler for automatic grant expiry
    expiry_scheduler = get_expiry_scheduler()
    await expiry_scheduler.start()
    logger.info("Expiry scheduler started")

    yield

    # Shutdown (T059: graceful shutdown - drain queue & mark in-flight tasks)
    logger.info("Shutting down captive portal addon")

    # Stop accepting new provisioning requests
    logger.info("Stopping grant manager (no new grants)")
    grant_manager = get_grant_manager()
    if hasattr(grant_manager, "stop_accepting_new_grants"):
        await grant_manager.stop_accepting_new_grants()

    # Drain the queue - wait for in-flight provisioning tasks to complete
    logger.info("Draining queue - waiting for in-flight provisioning to complete")
    queued_ops = get_queued_operations()

    try:
        # Give in-flight tasks up to 30 seconds to complete
        await queued_ops.drain(timeout_seconds=30)
        logger.info("Queue drained successfully")
    except Exception as e:
        logger.warning(
            "Queue drain timeout or error - some tasks may be incomplete",
            error=str(e),
        )

    # Stop scheduler services
    await expiry_scheduler.stop()
    logger.info("Expiry scheduler stopped")

    await event_service.stop()
    logger.info("Event ingestion service stopped")

    # Final cleanup
    logger.info("Graceful shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Captive Portal Addon",
        description="Home Assistant addon for guest network access management",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware for Home Assistant frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict to HA frontend origin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(portal_router)  # Portal first for captive redirect
    app.include_router(grants_router)
    app.include_router(vouchers_router)
    app.include_router(theme_router)
    app.include_router(audit_router)
    app.include_router(health_router)
    app.include_router(system_router)

    logger.info("FastAPI application configured")

    return app


# Create application instance
app = create_app()


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint - provides API information."""
    return {
        "service": "Captive Portal Addon",
        "version": "1.0.0",
        "status": "operational",
        "api_docs": "/docs",
        "health": "/api/health",
    }
