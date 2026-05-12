import asyncio
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sandbox:sandbox@localhost:55432/sandbox",
)


def database_available(database_url: str) -> bool:
    try:
        with psycopg.connect(database_url):
            return True
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(
    not database_available(TEST_DATABASE_URL),
    reason="PostgreSQL test database is not available on localhost:55432",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.db import close_pool
from app.main import app

DATASET_SCHEMAS = ("sales_dw", "saas_billing", "support_ops", "commerce_ops")


def close_backend_pool() -> None:
    asyncio.run(close_pool())


def drop_dataset_schemas() -> None:
    close_backend_pool()
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for schema_name in DATASET_SCHEMAS:
                cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                )


@pytest.fixture(autouse=True)
def clean_database() -> None:
    drop_dataset_schemas()
    yield
    drop_dataset_schemas()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    close_backend_pool()


def test_get_datasets_lists_all_templates(client: TestClient) -> None:
    response = client.get("/datasets")

    assert response.status_code == 200
    payload = response.json()["datasets"]
    assert {item["id"] for item in payload} == {"sales_dw", "saas_billing", "support_ops", "commerce_ops"}
    assert {item["schemaName"] for item in payload} == {"sales_dw", "saas_billing", "support_ops", "commerce_ops"}
    assert all(item["initialized"] is False for item in payload)
    assert all(item["tableCount"] == 0 for item in payload)
    assert all(len(item["starterQueries"]) == 3 for item in payload)


def test_dashboard_query_accepts_read_only_sql(client: TestClient) -> None:
    response = client.post("/dashboard/query", json={"sql": "SELECT 1 AS value"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["columns"] == ["value"]
    assert payload["rows"] == [{"value": 1}]
    assert payload["classification"]["isReadOnly"] is True


@pytest.mark.parametrize("sql_text", ["UPDATE missing SET value = 1", "DELETE FROM missing", "DROP TABLE missing"])
def test_dashboard_query_rejects_mutating_sql(client: TestClient, sql_text: str) -> None:
    response = client.post("/dashboard/query", json={"sql": sql_text})

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["message"] == "Dashboard widgets can only run read-only SQL."
    assert payload["classification"]["isReadOnly"] is False


def test_initialize_sales_dataset_creates_schema_and_rows(client: TestClient) -> None:
    response = client.post("/datasets/sales_dw/initialize")

    assert response.status_code == 200
    payload = response.json()
    table_counts = {table["name"]: table["rowCount"] for table in payload["tables"]}

    assert payload["schemaName"] == "sales_dw"
    assert payload["tableCount"] == 6
    assert payload["totalRows"] >= 70000
    assert table_counts["fact_sales"] == 60000
    assert table_counts["fact_returns"] >= 5000

    schema_response = client.get("/db/schema", params={"schema": "sales_dw"})
    schema_payload = schema_response.json()["schemas"]

    assert schema_response.status_code == 200
    assert len(schema_payload) == 1
    assert schema_payload[0]["name"] == "sales_dw"
    assert {table["name"] for table in schema_payload[0]["tables"]} == {
        "dim_date",
        "dim_customer",
        "dim_product",
        "dim_channel",
        "fact_sales",
        "fact_returns",
    }
    relationships = schema_payload[0]["relationships"]
    assert {
        (
            item["fromTableName"],
            item["fromColumnName"],
            item["toTableName"],
            item["toColumnName"],
        )
        for item in relationships
    } >= {
        ("fact_sales", "customer_key", "dim_customer", "customer_key"),
        ("fact_sales", "product_key", "dim_product", "product_key"),
        ("fact_returns", "sale_id", "fact_sales", "sale_id"),
    }

    with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS invalid_returns
                FROM sales_dw.fact_returns AS returns
                JOIN sales_dw.fact_sales AS sales
                  ON sales.sale_id = returns.sale_id
                WHERE returns.quantity > sales.quantity
                   OR returns.refund_amount < 0
                """
            )
            row = cur.fetchone()

    assert row is not None
    assert row["invalid_returns"] == 0


def test_reinitializing_one_dataset_preserves_other_schemas(client: TestClient) -> None:
    support_response = client.post("/datasets/support_ops/initialize")
    sales_response = client.post("/datasets/sales_dw/initialize")

    assert support_response.status_code == 200
    assert sales_response.status_code == 200
    assert support_response.json()["totalRows"] >= 150000

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE sales_dw.scratch_pad (note TEXT NOT NULL)")
            cur.execute("INSERT INTO sales_dw.scratch_pad (note) VALUES ('temporary')")

    reinit_response = client.post("/datasets/sales_dw/initialize")
    assert reinit_response.status_code == 200

    sales_schema = client.get("/db/schema", params={"schema": "sales_dw"}).json()["schemas"][0]
    support_schema = client.get("/db/schema", params={"schema": "support_ops"}).json()["schemas"][0]

    assert "scratch_pad" not in {table["name"] for table in sales_schema["tables"]}
    assert {table["name"] for table in support_schema["tables"]} == {
        "customers",
        "agents",
        "ticket_categories",
        "tickets",
        "ticket_events",
        "csat_surveys",
    }

    datasets_response = client.get("/datasets")
    dataset_index = {item["id"]: item for item in datasets_response.json()["datasets"]}

    assert dataset_index["sales_dw"]["initialized"] is True
    assert dataset_index["support_ops"]["initialized"] is True
    assert dataset_index["saas_billing"]["initialized"] is False
    assert dataset_index["commerce_ops"]["initialized"] is False


def test_support_ops_temporal_invariants_hold(client: TestClient) -> None:
    response = client.post("/datasets/support_ops/initialize")
    assert response.status_code == 200

    with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS invalid_tickets
                FROM support_ops.tickets
                WHERE first_response_at IS NOT NULL
                  AND first_response_at < opened_at
                """
            )
            invalid_response_order = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS invalid_resolution
                FROM support_ops.tickets
                WHERE resolved_at IS NOT NULL
                  AND first_response_at IS NOT NULL
                  AND resolved_at < first_response_at
                """
            )
            invalid_resolution_order = cur.fetchone()

    assert invalid_response_order is not None
    assert invalid_resolution_order is not None
    assert invalid_response_order["invalid_tickets"] == 0
    assert invalid_resolution_order["invalid_resolution"] == 0


def test_initialize_commerce_ops_dataset_creates_rich_schema(client: TestClient) -> None:
    response = client.post("/datasets/commerce_ops/initialize")

    assert response.status_code == 200
    payload = response.json()
    table_counts = {table["name"]: table["rowCount"] for table in payload["tables"]}

    assert payload["schemaName"] == "commerce_ops"
    assert payload["tableCount"] == 21
    assert payload["totalRows"] >= 45000
    assert table_counts["orders"] == 4200
    assert table_counts["order_items"] >= 9000
    assert table_counts["inventory_movements"] >= 9000

    schema_response = client.get("/db/schema", params={"schema": "commerce_ops"})
    schema_payload = schema_response.json()["schemas"]

    assert schema_response.status_code == 200
    assert len(schema_payload) == 1
    assert schema_payload[0]["name"] == "commerce_ops"
    assert {
        table["name"] for table in schema_payload[0]["tables"]
    } >= {
        "products",
        "sku_variants",
        "orders",
        "order_items",
        "payments",
        "shipments",
        "returns",
        "purchase_orders",
        "inventory_movements",
    }

    relationships = schema_payload[0]["relationships"]
    assert {
        (
            item["fromTableName"],
            item["fromColumnName"],
            item["toTableName"],
            item["toColumnName"],
        )
        for item in relationships
    } >= {
        ("orders", "customer_id", "customers", "customer_id"),
        ("order_items", "order_id", "orders", "order_id"),
        ("shipments", "order_id", "orders", "order_id"),
        ("return_items", "order_item_id", "order_items", "order_item_id"),
        ("purchase_order_items", "purchase_order_id", "purchase_orders", "purchase_order_id"),
    }


def test_commerce_ops_financial_and_fulfillment_invariants_hold(client: TestClient) -> None:
    response = client.post("/datasets/commerce_ops/initialize")
    assert response.status_code == 200

    with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH item_rollup AS (
                  SELECT
                    order_id,
                    ROUND(SUM(quantity * unit_price)::NUMERIC, 2) AS subtotal_amount,
                    ROUND(SUM(discount_amount)::NUMERIC, 2) AS discount_amount,
                    ROUND(SUM(tax_amount)::NUMERIC, 2) AS tax_amount
                  FROM commerce_ops.order_items
                  GROUP BY order_id
                )
                SELECT COUNT(*) AS invalid_orders
                FROM commerce_ops.orders AS orders
                JOIN item_rollup
                  ON item_rollup.order_id = orders.order_id
                WHERE ABS(orders.subtotal_amount - item_rollup.subtotal_amount) > 0.01
                   OR ABS(orders.discount_amount - item_rollup.discount_amount) > 0.01
                   OR ABS(orders.tax_amount - item_rollup.tax_amount) > 0.01
                   OR ABS(
                     orders.total_amount
                     - (
                       orders.subtotal_amount
                       - orders.discount_amount
                       + orders.shipping_amount
                       + orders.tax_amount
                     )
                   ) > 0.01
                """
            )
            invalid_orders = cur.fetchone()

            cur.execute(
                """
                WITH shipped_rollup AS (
                  SELECT order_item_id, SUM(quantity_shipped) AS shipped_qty
                  FROM commerce_ops.shipment_items
                  GROUP BY order_item_id
                )
                SELECT COUNT(*) AS overshipped_items
                FROM commerce_ops.order_items AS order_items
                JOIN shipped_rollup
                  ON shipped_rollup.order_item_id = order_items.order_item_id
                WHERE shipped_rollup.shipped_qty > order_items.quantity
                """
            )
            overshipped_items = cur.fetchone()

            cur.execute(
                """
                WITH returned_rollup AS (
                  SELECT order_item_id, SUM(quantity_returned) AS returned_qty
                  FROM commerce_ops.return_items
                  GROUP BY order_item_id
                )
                SELECT COUNT(*) AS overreturned_items
                FROM commerce_ops.order_items AS order_items
                JOIN returned_rollup
                  ON returned_rollup.order_item_id = order_items.order_item_id
                WHERE returned_rollup.returned_qty > order_items.quantity
                """
            )
            overreturned_items = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS invalid_payments
                FROM commerce_ops.payments
                WHERE amount_refunded > amount_captured
                """
            )
            invalid_payments = cur.fetchone()

    assert invalid_orders is not None
    assert overshipped_items is not None
    assert overreturned_items is not None
    assert invalid_payments is not None
    assert invalid_orders["invalid_orders"] == 0
    assert overshipped_items["overshipped_items"] == 0
    assert overreturned_items["overreturned_items"] == 0
    assert invalid_payments["invalid_payments"] == 0
