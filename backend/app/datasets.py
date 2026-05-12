from __future__ import annotations

from textwrap import dedent

from fastapi import HTTPException
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from app.sql_seeds.commerce_ops_seed import CommerceOpsDatasetTemplate
from app.sql_seeds.saas_billing_seed import SaasBillingDatasetTemplate
from app.sql_seeds.support_ops_seed import SupportOpsDatasetTemplate
from app.sql_seeds.sales_dw_seed import SalesDatasetTemplate

from app.sql_seeds.models import (
    DatasetTemplate
)
from app.models import (
    DatasetInitializeResponse,
    DatasetTableStat,
    DatasetTemplateSummary,
    StarterQuery,
)

DATASET_TEMPLATES: dict[str, DatasetTemplate] = {
    "sales_dw": SalesDatasetTemplate,
    "saas_billing": SaasBillingDatasetTemplate,
    "support_ops": SupportOpsDatasetTemplate,
    "commerce_ops": CommerceOpsDatasetTemplate,
}


def get_dataset_template(dataset_id: str) -> DatasetTemplate:
    template = DATASET_TEMPLATES.get(dataset_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset template: {dataset_id}")
    return template


async def fetch_dataset_state(conn: AsyncConnection[dict]) -> dict[str, int]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
              n.nspname AS schema_name,
              COUNT(c.oid)::INTEGER AS table_count
            FROM pg_namespace AS n
            LEFT JOIN pg_class AS c
              ON c.relnamespace = n.oid
             AND c.relkind = 'r'
            WHERE n.nspname = ANY(%s)
            GROUP BY n.nspname
            """,
            ([template.schema_name for template in DATASET_TEMPLATES.values()],),
        )
        rows = await cur.fetchall()
    return {row["schema_name"]: row["table_count"] for row in rows}


async def list_dataset_templates(conn: AsyncConnection[dict]) -> list[DatasetTemplateSummary]:
    states = await fetch_dataset_state(conn)
    return [
        DatasetTemplateSummary(
            id=template.id,
            name=template.name,
            description=template.description,
            schemaName=template.schema_name,
            initialized=states.get(template.schema_name, 0) > 0,
            tableCount=states.get(template.schema_name, 0),
            estimatedRows=template.estimated_rows,
            starterQueries=list(template.starter_queries),
        )
        for template in DATASET_TEMPLATES.values()
    ]


async def execute_compound_sql(conn: AsyncConnection[dict], sql_text: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(sql_text)


async def drop_dataset_schema(conn: AsyncConnection[dict], schema_name: str) -> None:
    statement = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
    async with conn.cursor() as cur:
        await cur.execute(statement)


async def count_rows_for_table(conn: AsyncConnection[dict], schema_name: str, table_name: str) -> int:
    statement = sql.SQL("SELECT COUNT(*) AS row_count FROM {}.{}").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(statement)
        row = await cur.fetchone()
    return int(row["row_count"]) if row else 0


async def initialize_dataset(conn: AsyncConnection[dict], dataset_id: str) -> DatasetInitializeResponse:
    template = get_dataset_template(dataset_id)
    await drop_dataset_schema(conn, template.schema_name)
    await execute_compound_sql(conn, template.seed_sql)

    table_stats = [
        DatasetTableStat(name=table_name, rowCount=await count_rows_for_table(conn, template.schema_name, table_name))
        for table_name in template.table_names
    ]
    total_rows = sum(item.rowCount for item in table_stats)
    return DatasetInitializeResponse(
        id=template.id,
        name=template.name,
        schemaName=template.schema_name,
        tableCount=len(table_stats),
        totalRows=total_rows,
        tables=table_stats,
    )
