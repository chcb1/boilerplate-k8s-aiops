import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.database import Base
from my_agent_app import models  # noqa: F401

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL", "postgresql+asyncpg://aiops:aiops123@localhost:5432/postgres"
)
TEST_DB = "aiops_k8s_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest_asyncio.fixture
async def sessionmaker():
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except Exception as exc:  # banco indisponivel: pula os testes de integracao
        await admin.dispose()
        pytest.skip(f"PostgreSQL indisponivel para testes de integracao: {exc}")
    await admin.dispose()

    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
