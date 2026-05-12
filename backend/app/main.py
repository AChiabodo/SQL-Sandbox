from time import perf_counter
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from psycopg import Error as PsycopgError

from app.config import Settings, get_settings
from app.datasets import initialize_dataset, list_dataset_templates
from app.db import close_pool, get_connection, open_pool
from app.llm import llm_status, translate_query
from app.llm_sql.service import generate_sql, stream_generate_sql
from app.models import (
    CompiledQuery,
    DashboardQueryRequest,
    DatasetInitializeResponse,
    DatasetTemplateSummary,
    ExplainRequest,
    LlmSqlRequest,
    LlmSqlResponse,
    LlmTranslateRequest,
    LlmTranslateResponse,
    QueryBuilderRequest,
    SqlRequest,
    SqlResult,
)
from app.query_builder import compile_query
from app.sql_guardrails import classify_sql

app = FastAPI(title="PostgreSQL Sandbox API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await open_pool()


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_pool()


def sql_error(error: PsycopgError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "message": str(error).strip(),
            "sqlstate": getattr(error, "sqlstate", None),
            "severity": getattr(getattr(error, "diag", None), "severity", None),
        },
    )


def schema_rows_to_response(
    rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schemas: dict[str, dict[str, Any]] = {}
    for row in rows:
        schema_name = row["table_schema"]
        table_name = row["table_name"]
        schema = schemas.setdefault(schema_name, {"name": schema_name, "tables": {}, "relationships": []})
        table = schema["tables"].setdefault(table_name, {"name": table_name, "columns": []})
        table["columns"].append(
            {
                "name": row["column_name"],
                "dataType": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
            }
        )

    for row in relationship_rows or []:
        schema_name = row["from_schema_name"]
        schema = schemas.setdefault(schema_name, {"name": schema_name, "tables": {}, "relationships": []})
        schema["relationships"].append(
            {
                "constraintName": row["constraint_name"],
                "fromSchemaName": row["from_schema_name"],
                "fromTableName": row["from_table_name"],
                "fromColumnName": row["from_column_name"],
                "toSchemaName": row["to_schema_name"],
                "toTableName": row["to_table_name"],
                "toColumnName": row["to_column_name"],
            }
        )

    return {
        "schemas": [
            {
                "name": schema["name"],
                "tables": list(schema["tables"].values()),
                "relationships": schema["relationships"],
            }
            for schema in schemas.values()
        ]
    }


async def run_sql(sql: str, params: list[Any] | None = None) -> SqlResult:
    classification = classify_sql(sql)
    started = perf_counter()

    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params or [])
                columns = [column.name for column in cur.description] if cur.description else []
                rows = await cur.fetchall() if cur.description else []
                await conn.commit()
                duration_ms = round((perf_counter() - started) * 1000, 2)
                return SqlResult(
                    columns=columns,
                    rows=rows,
                    rowCount=len(rows),
                    affectedRows=cur.rowcount if cur.rowcount >= 0 else None,
                    durationMs=duration_ms,
                    commandTag=cur.statusmessage,
                    classification=classification,
                )
    except PsycopgError as error:
        raise sql_error(error) from error


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "postgres-sandbox-api"}


@app.get("/db/status")
async def db_status() -> dict[str, Any]:
    result = await run_sql(
        "SELECT version(), current_database() AS database, current_schema() AS schema, now() AS server_time"
    )
    return result.rows[0]


@app.get("/db/schema")
async def db_schema(schema_name: str | None = Query(default=None, alias="schema")) -> dict[str, Any]:
    column_sql = """
    SELECT
      table_schema,
      table_name,
      column_name,
      data_type,
      is_nullable,
      column_default,
      ordinal_position
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    """
    params: list[Any] = []
    if schema_name:
        column_sql += " AND table_schema = %s"
        params.append(schema_name)
    column_sql += " ORDER BY table_schema, table_name, ordinal_position"

    relationship_sql = """
    SELECT
      constraint_data.constraint_name,
      constraint_data.from_schema_name,
      constraint_data.from_table_name,
      source_column.attname AS from_column_name,
      constraint_data.to_schema_name,
      constraint_data.to_table_name,
      target_column.attname AS to_column_name
    FROM (
      SELECT
        pg_constraint.conname AS constraint_name,
        source_schema.nspname AS from_schema_name,
        source_table.relname AS from_table_name,
        target_schema.nspname AS to_schema_name,
        target_table.relname AS to_table_name,
        key_pair.from_attnum,
        key_pair.to_attnum,
        key_pair.ordinality
      FROM pg_constraint
      JOIN pg_class AS source_table
        ON source_table.oid = pg_constraint.conrelid
      JOIN pg_namespace AS source_schema
        ON source_schema.oid = source_table.relnamespace
      JOIN pg_class AS target_table
        ON target_table.oid = pg_constraint.confrelid
      JOIN pg_namespace AS target_schema
        ON target_schema.oid = target_table.relnamespace
      JOIN LATERAL unnest(pg_constraint.conkey, pg_constraint.confkey)
        WITH ORDINALITY AS key_pair(from_attnum, to_attnum, ordinality)
        ON TRUE
      WHERE pg_constraint.contype = 'f'
        AND source_schema.nspname NOT IN ('pg_catalog', 'information_schema')
    """
    relationship_params: list[Any] = []
    if schema_name:
        relationship_sql += " AND source_schema.nspname = %s"
        relationship_params.append(schema_name)
    relationship_sql += """
    ) AS constraint_data
    JOIN pg_attribute AS source_column
      ON source_column.attrelid = (
        SELECT oid FROM pg_class
        WHERE relname = constraint_data.from_table_name
          AND relnamespace = (
            SELECT oid FROM pg_namespace WHERE nspname = constraint_data.from_schema_name
          )
      )
     AND source_column.attnum = constraint_data.from_attnum
    JOIN pg_attribute AS target_column
      ON target_column.attrelid = (
        SELECT oid FROM pg_class
        WHERE relname = constraint_data.to_table_name
          AND relnamespace = (
            SELECT oid FROM pg_namespace WHERE nspname = constraint_data.to_schema_name
          )
      )
     AND target_column.attnum = constraint_data.to_attnum
    ORDER BY
      constraint_data.from_schema_name,
      constraint_data.from_table_name,
      constraint_data.constraint_name,
      constraint_data.ordinality
    """
    column_result = await run_sql(column_sql, params)
    relationship_result = await run_sql(relationship_sql, relationship_params)
    return schema_rows_to_response(column_result.rows, relationship_result.rows)


@app.get("/datasets")
async def datasets() -> dict[str, list[DatasetTemplateSummary]]:
    async with get_connection() as conn:
        return {"datasets": await list_dataset_templates(conn)}


@app.post("/datasets/{dataset_id}/initialize")
async def dataset_initialize(dataset_id: str) -> DatasetInitializeResponse:
    try:
        async with get_connection() as conn:
            result = await initialize_dataset(conn, dataset_id)
            await conn.commit()
            return result
    except PsycopgError as error:
        raise sql_error(error) from error


@app.get("/db/tables/{schema_name}/{table_name}/rows")
async def table_rows(
    schema_name: str,
    table_name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> SqlResult:
    spec = QueryBuilderRequest(
        table={"schemaName": schema_name, "tableName": table_name},
        limit=limit,
        offset=offset,
    )
    compiled = compile_query(spec)
    return await run_sql(compiled.sql, compiled.params)


@app.post("/sql/execute")
async def execute_sql(payload: SqlRequest) -> SqlResult:
    classification = classify_sql(payload.sql)
    if classification.isDangerous and not payload.confirmDangerous:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dangerous SQL requires explicit confirmation.",
                "classification": classification.model_dump(),
            },
        )
    return await run_sql(payload.sql)


@app.post("/sql/explain")
async def explain_sql(payload: ExplainRequest) -> SqlResult:
    classification = classify_sql(payload.sql)
    if not classification.isReadOnly:
        raise HTTPException(
            status_code=400,
            detail="EXPLAIN is available only for read-only statements in this sandbox.",
        )
    return await run_sql(f"EXPLAIN (FORMAT JSON, ANALYZE FALSE, VERBOSE FALSE) {payload.sql}")


@app.post("/dashboard/query")
async def dashboard_query(payload: DashboardQueryRequest) -> SqlResult:
    classification = classify_sql(payload.sql)
    if not classification.isReadOnly:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Dashboard widgets can only run read-only SQL.",
                "classification": classification.model_dump(),
            },
        )
    return await run_sql(payload.sql)


@app.post("/query-builder/compile")
async def query_builder_compile(payload: QueryBuilderRequest) -> CompiledQuery:
    return compile_query(payload)


@app.post("/query-builder/execute")
async def query_builder_execute(payload: QueryBuilderRequest) -> SqlResult:
    compiled = compile_query(payload)
    return await run_sql(compiled.sql, compiled.params)


@app.get("/llm/status")
async def get_llm_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return llm_status(settings)


@app.post("/llm/translate-query")
async def llm_translate(
    payload: LlmTranslateRequest,
    settings: Settings = Depends(get_settings),
) -> LlmTranslateResponse:
    return await translate_query(payload, settings)


@app.post("/llm/generate-sql")
async def llm_generate_sql(payload: LlmSqlRequest) -> LlmSqlResponse:
    return await generate_sql(payload)


@app.post("/llm/generate-sql/stream")
async def llm_generate_sql_stream(payload: LlmSqlRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_generate_sql(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
