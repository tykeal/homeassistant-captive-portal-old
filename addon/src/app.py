# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Main FastAPI application for the captive portal addon."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    audit_router,
    grants_router,
    health_router,
    theme_router,
    vouchers_router,
)
from .core.config import get_config
from .core.logging_config import configure_logging, get_logger
from .storage.database import initialize_database

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown tasks."""
    # Startup
    logger.info("Starting captive portal addon")

    # Initialize configuration
    config = get_config()
    configure_logging(log_level=config.log_level, json_format=True)

    # Initialize database
    await initialize_database()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down captive portal addon")


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
    app.include_router(grants_router)
    app.include_router(vouchers_router)
    app.include_router(theme_router)
    app.include_router(audit_router)
    app.include_router(health_router)

    logger.info("FastAPI application configured")

    return app


# Create application instance
app = create_app()


@app.get("/")
async def root():
    """Root endpoint - provides API information."""
    return {
        "service": "Captive Portal Addon",
        "version": "1.0.0",
        "status": "operational",
        "api_docs": "/docs",
        "health": "/api/health",
    }
