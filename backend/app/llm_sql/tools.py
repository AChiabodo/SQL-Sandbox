from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from langchain_core.tools import StructuredTool
from psycopg import Error as PsycopgError
from psycopg import sql as psycopg_sql
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.db import get_connection
from app.llm_sql.schema_context import fetch_schema_context
from app.sql_guardrails import classify_sql


class SqlInput(BaseModel):
    sql: str = Field(description="Complete PostgreSQL SQL query.")


class PreviewSqlInput(BaseModel):
    sql: str = Field(description="Complete PostgreSQL SQL query to preview.")
    limit: int = Field(default=20, ge=1, le=50, description="Maximum rows to return.")


class SchemaContextInput(BaseModel):
    schema_name: str = Field(description="PostgreSQL schema name.")


class TableProfileInput(BaseModel):
    schema_name: str = Field(description="PostgreSQL schema name.")
    table_name: str = Field(description="PostgreSQL table name.")
    sample_limit: int = Field(default=5, ge=1, le=10, description="Maximum sample rows to return.")


def strip_trailing_semicolon(sql: str) -> str:
    return re.sub(r";+\s*$", "", sql.strip())


def json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


async def _execute_read_only(sql: str, params: list[Any] | None = None) -> dict[str, Any]:
    started = perf_counter()
    async with get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params or [])
            columns = [column.name for column in cur.description] if cur.description else []
            rows = await cur.fetchall() if cur.description else []
            await conn.rollback()
    return {
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "durationMs": round((perf_counter() - started) * 1000, 2),
    }


async def get_schema_context(schema_name: str) -> str:
    """Return compact schema context with tables, columns, data types, and foreign keys."""
    context = await fetch_schema_context(schema_name)
    return context.compact_text()


async def get_table_profile(schema_name: str, table_name: str, sample_limit: int = 5) -> str:
    """Return row count, column metadata, and a tiny sample for one table."""
    safe_limit = max(1, min(sample_limit, 10))
    columns_sql = """
    SELECT column_name, data_type, is_nullable, column_default, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position
    """
    count_sql = psycopg_sql.SQL("SELECT COUNT(*) AS row_count FROM {}.{}").format(
        psycopg_sql.Identifier(schema_name),
        psycopg_sql.Identifier(table_name),
    )
    sample_sql = psycopg_sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
        psycopg_sql.Identifier(schema_name),
        psycopg_sql.Identifier(table_name),
    )

    try:
        async with get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(columns_sql, [schema_name, table_name])
                columns = await cur.fetchall()
                if not columns:
                    return json_result({"ok": False, "error": "Table was not found in the active schema."})

                await cur.execute(count_sql)
                row_count = (await cur.fetchone() or {}).get("row_count", 0)
                await cur.execute(sample_sql, [safe_limit])
                sample_rows = await cur.fetchall()
                await conn.rollback()
    except PsycopgError as exc:
        return json_result({"ok": False, "error": str(exc).strip()})

    return json_result(
        {
            "ok": True,
            "schema": schema_name,
            "table": table_name,
            "rowCount": row_count,
            "columns": [
                {
                    "name": row["column_name"],
                    "dataType": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                }
                for row in columns
            ],
            "sampleRows": sample_rows,
        }
    )


async def validate_sql(sql: str) -> str:
    """Validate SQL guardrails and report whether the query is read-only and safe to preview."""
    classification = classify_sql(sql)
    return json_result(
        {
            "ok": classification.isReadOnly and not classification.isDangerous,
            "statementType": classification.statementType,
            "isReadOnly": classification.isReadOnly,
            "isDangerous": classification.isDangerous,
            "reasons": classification.reasons,
        }
    )


async def explain_sql(sql: str) -> str:
    """Run EXPLAIN JSON for a read-only PostgreSQL query without executing it."""
    classification = classify_sql(sql)
    if not classification.isReadOnly or classification.isDangerous:
        return json_result({"ok": False, "error": "Only safe read-only SQL can be explained."})

    try:
        result = await _execute_read_only(
            f"EXPLAIN (FORMAT JSON, ANALYZE FALSE, VERBOSE FALSE) {strip_trailing_semicolon(sql)}"
        )
    except PsycopgError as exc:
        return json_result({"ok": False, "error": str(exc).strip()})
    return json_result({"ok": True, **result})


async def preview_sql(sql: str, limit: int = 20) -> str:
    """Execute a read-only SQL query with a hard row limit and return a small preview."""
    classification = classify_sql(sql)
    if not classification.isReadOnly or classification.isDangerous:
        return json_result({"ok": False, "error": "Only safe read-only SQL can be previewed."})

    safe_limit = max(1, min(limit, 50))
    preview_query = f"SELECT * FROM ({strip_trailing_semicolon(sql)}) AS llm_preview LIMIT %s"
    try:
        result = await _execute_read_only(preview_query, [safe_limit])
    except PsycopgError as exc:
        return json_result({"ok": False, "error": str(exc).strip()})
    return json_result({"ok": True, **result})


def build_sql_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=get_schema_context,
            name="get_schema_context",
            description="Return compact schema context with tables, columns, data types, and foreign keys.",
            args_schema=SchemaContextInput,
        ),
        StructuredTool.from_function(
            coroutine=get_table_profile,
            name="get_table_profile",
            description="Return row count, column metadata, and a tiny sample for one table when schema context is not enough.",
            args_schema=TableProfileInput,
        ),
        StructuredTool.from_function(
            coroutine=validate_sql,
            name="validate_sql",
            description="Validate whether SQL is safe, read-only PostgreSQL.",
            args_schema=SqlInput,
        ),
        StructuredTool.from_function(
            coroutine=explain_sql,
            name="explain_sql",
            description="Run EXPLAIN JSON for safe read-only SQL without executing it.",
            args_schema=SqlInput,
        ),
        StructuredTool.from_function(
            coroutine=preview_sql,
            name="preview_sql",
            description="Run a safe read-only SQL query with a small hard row limit.",
            args_schema=PreviewSqlInput,
        ),
    ]
