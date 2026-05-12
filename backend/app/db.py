from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global pool
    if pool is None:
        pool = AsyncConnectionPool(
            conninfo=get_settings().database_url,
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=10,
            open=False,
        )
        await pool.open(wait=True)


async def close_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection[Any]]:
    if pool is None:
        await open_pool()
    assert pool is not None
    async with pool.connection() as conn:
        yield conn

