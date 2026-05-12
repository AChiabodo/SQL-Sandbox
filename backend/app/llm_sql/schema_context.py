from __future__ import annotations

from pydantic import BaseModel
from psycopg.rows import dict_row

from app.db import get_connection


class ColumnContext(BaseModel):
    name: str
    dataType: str
    nullable: bool
    default: str | None = None


class TableContext(BaseModel):
    name: str
    columns: list[ColumnContext]


class RelationshipContext(BaseModel):
    constraintName: str
    fromSchemaName: str
    fromTableName: str
    fromColumnName: str
    toSchemaName: str
    toTableName: str
    toColumnName: str


class SchemaContext(BaseModel):
    name: str
    tables: list[TableContext]
    relationships: list[RelationshipContext]

    def compact_text(self) -> str:
        lines = [f"Schema: {self.name}", "", "Tables and columns:"]
        for table in self.tables:
            column_text = ", ".join(
                f"{column.name} {column.dataType}{' nullable' if column.nullable else ' not null'}"
                for column in table.columns
            )
            lines.append(f"- {self.name}.{table.name}: {column_text}")

        lines.append("")
        lines.append("Foreign keys:")
        if self.relationships:
            for relation in self.relationships:
                lines.append(
                    "- "
                    f"{relation.fromSchemaName}.{relation.fromTableName}.{relation.fromColumnName} -> "
                    f"{relation.toSchemaName}.{relation.toTableName}.{relation.toColumnName}"
                )
        else:
            lines.append("- none")
        return "\n".join(lines)


async def fetch_schema_context(schema_name: str) -> SchemaContext:
    column_sql = """
    SELECT table_name, column_name, data_type, is_nullable, column_default, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = %s
    ORDER BY table_name, ordinal_position
    """
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
      JOIN pg_class AS source_table ON source_table.oid = pg_constraint.conrelid
      JOIN pg_namespace AS source_schema ON source_schema.oid = source_table.relnamespace
      JOIN pg_class AS target_table ON target_table.oid = pg_constraint.confrelid
      JOIN pg_namespace AS target_schema ON target_schema.oid = target_table.relnamespace
      JOIN LATERAL unnest(pg_constraint.conkey, pg_constraint.confkey)
        WITH ORDINALITY AS key_pair(from_attnum, to_attnum, ordinality)
        ON TRUE
      WHERE pg_constraint.contype = 'f'
        AND source_schema.nspname = %s
    ) AS constraint_data
    JOIN pg_attribute AS source_column
      ON source_column.attrelid = (
        SELECT oid FROM pg_class
        WHERE relname = constraint_data.from_table_name
          AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = constraint_data.from_schema_name)
      )
     AND source_column.attnum = constraint_data.from_attnum
    JOIN pg_attribute AS target_column
      ON target_column.attrelid = (
        SELECT oid FROM pg_class
        WHERE relname = constraint_data.to_table_name
          AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = constraint_data.to_schema_name)
      )
     AND target_column.attnum = constraint_data.to_attnum
    ORDER BY constraint_data.from_table_name, constraint_data.constraint_name, constraint_data.ordinality
    """

    async with get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(column_sql, [schema_name])
            column_rows = await cur.fetchall()
            await cur.execute(relationship_sql, [schema_name])
            relationship_rows = await cur.fetchall()

    table_index: dict[str, TableContext] = {}
    for row in column_rows:
        table = table_index.setdefault(row["table_name"], TableContext(name=row["table_name"], columns=[]))
        table.columns.append(
            ColumnContext(
                name=row["column_name"],
                dataType=row["data_type"],
                nullable=row["is_nullable"] == "YES",
                default=row["column_default"],
            )
        )

    return SchemaContext(
        name=schema_name,
        tables=list(table_index.values()),
        relationships=[
            RelationshipContext(
                constraintName=row["constraint_name"],
                fromSchemaName=row["from_schema_name"],
                fromTableName=row["from_table_name"],
                fromColumnName=row["from_column_name"],
                toSchemaName=row["to_schema_name"],
                toTableName=row["to_table_name"],
                toColumnName=row["to_column_name"],
            )
            for row in relationship_rows
        ],
    )
