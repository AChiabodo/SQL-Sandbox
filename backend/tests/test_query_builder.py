import pytest
from fastapi import HTTPException

from app.models import QueryBuilderRequest
from app.query_builder import compile_query


def test_compile_query_with_filter_group_and_aggregation() -> None:
    compiled = compile_query(
        QueryBuilderRequest(
            table={"schemaName": "public", "tableName": "orders"},
            columns=["status"],
            filters=[{"column": "status", "operator": "IN", "value": ["paid", "shipped"]}],
            groupBy=["status"],
            aggregations=[{"function": "count", "column": "*", "alias": "orders_count"}],
            orderBy=[{"expression": "orders_count", "direction": "desc"}],
            limit=50,
        )
    )

    assert compiled.sql == (
        'SELECT "status", COUNT(*) AS "orders_count" FROM "public"."orders" '
        'WHERE "status" IN (%s, %s) GROUP BY "status" ORDER BY "orders_count" DESC '
        "LIMIT %s OFFSET %s"
    )
    assert compiled.params == ["paid", "shipped", 50, 0]


def relationship(
    constraint_name: str,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
    schema: str = "sales_dw",
) -> dict[str, str]:
    return {
        "constraintName": constraint_name,
        "fromSchemaName": schema,
        "fromTableName": from_table,
        "fromColumnName": from_column,
        "toSchemaName": schema,
        "toTableName": to_table,
        "toColumnName": to_column,
    }


def column(table: str, name: str, schema: str = "sales_dw") -> dict[str, str]:
    return {"schemaName": schema, "tableName": table, "columnName": name}


def test_compile_query_with_automatic_join() -> None:
    compiled = compile_query(
        QueryBuilderRequest(
            table={"schemaName": "sales_dw", "tableName": "fact_sales"},
            columns=[column("dim_customer", "country_code")],
            groupBy=[column("dim_customer", "country_code")],
            aggregations=[{"function": "sum", "column": column("fact_sales", "net_amount")}],
            relationships=[
                relationship("fact_sales_customer_key_fkey", "fact_sales", "customer_key", "dim_customer", "customer_key")
            ],
        )
    )

    assert compiled.sql == (
        'SELECT t1."country_code" AS "dim_customer_country_code", '
        'SUM(t0."net_amount") AS "sum_fact_sales_net_amount" '
        'FROM "sales_dw"."fact_sales" AS t0 '
        'INNER JOIN "sales_dw"."dim_customer" AS t1 ON t0."customer_key" = t1."customer_key" '
        'GROUP BY t1."country_code" LIMIT %s OFFSET %s'
    )
    assert compiled.params == [100, 0]


def test_compile_query_with_automatic_multi_hop_join() -> None:
    compiled = compile_query(
        QueryBuilderRequest(
            table={"schemaName": "sales_dw", "tableName": "fact_returns"},
            columns=[column("dim_customer", "country_code")],
            relationships=[
                relationship("returns_sale_id_fkey", "fact_returns", "sale_id", "fact_sales", "sale_id"),
                relationship("sales_customer_key_fkey", "fact_sales", "customer_key", "dim_customer", "customer_key"),
            ],
        )
    )

    assert 'INNER JOIN "sales_dw"."fact_sales" AS t1 ON t0."sale_id" = t1."sale_id"' in compiled.sql
    assert 'INNER JOIN "sales_dw"."dim_customer" AS t2 ON t1."customer_key" = t2."customer_key"' in compiled.sql
    assert 't2."country_code" AS "dim_customer_country_code"' in compiled.sql


def test_compile_query_requires_known_foreign_key_path() -> None:
    with pytest.raises(HTTPException) as exc:
        compile_query(
            QueryBuilderRequest(
                table={"schemaName": "sales_dw", "tableName": "fact_sales"},
                columns=[column("dim_customer", "country_code")],
                relationships=[],
            )
        )
    assert "No foreign-key path" in exc.value.detail


def test_compile_query_rejects_ambiguous_foreign_key_path() -> None:
    with pytest.raises(HTTPException) as exc:
        compile_query(
            QueryBuilderRequest(
                table={"schemaName": "sales_dw", "tableName": "base_table"},
                columns=[column("target_table", "target_value")],
                relationships=[
                    relationship("base_first_fkey", "base_table", "first_id", "first_bridge", "id"),
                    relationship("first_target_fkey", "first_bridge", "target_id", "target_table", "id"),
                    relationship("base_second_fkey", "base_table", "second_id", "second_bridge", "id"),
                    relationship("second_target_fkey", "second_bridge", "target_id", "target_table", "id"),
                ],
            )
        )
    assert "Ambiguous foreign-key path" in exc.value.detail


def test_compile_query_with_manual_left_join() -> None:
    compiled = compile_query(
        QueryBuilderRequest(
            table={"schemaName": "sales_dw", "tableName": "fact_sales"},
            columns=[column("dim_customer", "country_code")],
            joins=[
                {
                    "joinType": "left",
                    "left": column("fact_sales", "customer_key"),
                    "right": column("dim_customer", "customer_key"),
                }
            ],
        )
    )

    assert (
        'LEFT JOIN "sales_dw"."dim_customer" AS t1 ON t0."customer_key" = t1."customer_key"'
        in compiled.sql
    )
