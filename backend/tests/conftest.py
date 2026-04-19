"""Test fixtures for the FS Intelligence Platform backend."""

import asyncio
import os
import tempfile
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _default_llm_provider_is_api():
    """Default every test's orchestration provider to ``api``.

    Tests that need a different provider should monkeypatch
    ``app.orchestration.config_resolver.get_configured_llm_provider_name``
    (and, for idea_router, its local binding) explicitly. This fixture
    just prevents leakage from a real database that might have
    ``llm_provider=cursor`` saved — without it, route branching would
    divert tests to the Cursor paste-per-action flow.
    """
    mock = AsyncMock(return_value="api")
    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=mock,
        ),
        patch(
            "app.api.idea_router.get_configured_llm_provider_name",
            new=mock,
        ),
    ):
        yield


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh test database for each test."""
    temp_db_path = os.path.join(tempfile.gettempdir(), f"fs_intel_test_{uuid.uuid4().hex}.db")
    test_database_url = f"sqlite+aiosqlite:///{temp_db_path}"
    engine = create_async_engine(test_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


@pytest_asyncio.fixture(scope="function")
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with overridden DB dependency."""

    async def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
