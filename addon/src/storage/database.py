# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Database connection and session management."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (  # type: ignore[attr-defined]
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from .schema import Base


class DatabaseManager:
    """Database connection and session manager."""

    def __init__(self, database_url: str | None = None):
        """Initialize database manager.

        Args:
            database_url: Database URL. If None, uses default SQLite path.
        """
        if database_url is None:
            # Default to /data/captive_portal.db for HA addon
            db_path = os.getenv("DB_PATH", "/data/captive_portal.db")
            database_url = f"sqlite+aiosqlite:///{db_path}"

        # Configure engine for SQLite
        connect_args = {}
        if "sqlite" in database_url:
            connect_args = {
                "check_same_thread": False,
            }

        self.engine = create_async_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            connect_args=connect_args,
            poolclass=StaticPool if "sqlite" in database_url else None,
        )

        self.async_session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize_database(self) -> None:
        """Initialize database schema."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Get database session context manager."""
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def initialize_database() -> None:
    """Initialize the database schema."""
    db_manager = get_database_manager()
    await db_manager.initialize_database()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Get database session for dependency injection."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        yield session
