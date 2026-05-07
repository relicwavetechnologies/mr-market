"""Async database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class SessionManager:
    """Manages async SQLAlchemy engine and session factory.

    Usage:
        manager = SessionManager("postgresql+asyncpg://user:pass@host/db")
        async with manager.session() as session:
            ...
    """

    def __init__(
        self,
        database_url: str,
        *,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> None:
        self.engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def session(self) -> AsyncSession:
        """Return a new async session from the factory."""
        return self._session_factory()

    async def close(self) -> None:
        """Dispose of the engine connection pool."""
        await self.engine.dispose()


# Module-level singleton — initialised by the application at startup.
_manager: SessionManager | None = None


def init_session_manager(database_url: str, **kwargs: object) -> SessionManager:
    """Initialise the module-level SessionManager singleton."""
    global _manager  # noqa: PLW0603
    _manager = SessionManager(database_url, **kwargs)
    return _manager


def get_session_manager() -> SessionManager:
    """Return the current SessionManager or raise if not initialised."""
    if _manager is None:
        raise RuntimeError(
            "SessionManager not initialised. Call init_session_manager() first."
        )
    return _manager


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    manager = get_session_manager()
    async with manager.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
