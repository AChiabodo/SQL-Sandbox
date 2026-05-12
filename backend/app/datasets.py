from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent

from fastapi import HTTPException
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from app.models import (
    DatasetInitializeResponse,
    DatasetTableStat,
    DatasetTemplateSummary,
    StarterQuery,
)


@dataclass(frozen=True)
class DatasetTemplate:
    id: str
    name: str
    description: str
    schema_name: str
    estimated_rows: int
    table_names: tuple[str, ...]
    starter_queries: tuple[StarterQuery, ...]
    seed_sql: str


def quote_name(identifier: str) -> str:
    return f'"{identifier}"'


def sales_dw_sql(schema_name: str) -> str:
    schema = quote_name(schema_name)
    return dedent(
        f"""
        SELECT setseed(0.1101);

        CREATE SCHEMA {schema};

        CREATE TABLE {schema}.dim_date (
          day_key INTEGER PRIMARY KEY,
          full_date DATE NOT NULL UNIQUE,
          calendar_year INTEGER NOT NULL,
          calendar_quarter INTEGER NOT NULL,
          month_number INTEGER NOT NULL,
          month_name TEXT NOT NULL,
          week_number INTEGER NOT NULL,
          day_of_week INTEGER NOT NULL,
          weekday_name TEXT NOT NULL,
          is_weekend BOOLEAN NOT NULL
        );

        INSERT INTO {schema}.dim_date (
          day_key,
          full_date,
          calendar_year,
          calendar_quarter,
          month_number,
          month_name,
          week_number,
          day_of_week,
          weekday_name,
          is_weekend
        )
        SELECT
          TO_CHAR(day_value, 'YYYYMMDD')::INTEGER,
          day_value,
          EXTRACT(YEAR FROM day_value)::INTEGER,
          EXTRACT(QUARTER FROM day_value)::INTEGER,
          EXTRACT(MONTH FROM day_value)::INTEGER,
          TO_CHAR(day_value, 'Mon'),
          EXTRACT(WEEK FROM day_value)::INTEGER,
          EXTRACT(ISODOW FROM day_value)::INTEGER,
          TO_CHAR(day_value, 'Dy'),
          EXTRACT(ISODOW FROM day_value) IN (6, 7)
        FROM generate_series(DATE '2023-01-01', DATE '2026-03-31', INTERVAL '1 day') AS generated(day_value);

        CREATE TABLE {schema}.dim_customer (
          customer_key INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          customer_code TEXT NOT NULL UNIQUE,
          customer_name TEXT NOT NULL,
          country_code TEXT NOT NULL,
          region_name TEXT NOT NULL,
          segment TEXT NOT NULL,
          loyalty_tier TEXT NOT NULL,
          signup_date DATE NOT NULL
        );

        INSERT INTO {schema}.dim_customer (
          customer_code,
          customer_name,
          country_code,
          region_name,
          segment,
          loyalty_tier,
          signup_date
        )
        SELECT
          FORMAT('CUST-%05s', seq),
          first_name || ' ' || last_name,
          country_code,
          CASE
            WHEN country_code IN ('IT', 'DE', 'FR', 'ES', 'NL') THEN 'EMEA'
            WHEN country_code IN ('US', 'CA', 'MX') THEN 'Americas'
            ELSE 'APAC'
          END,
          segment,
          CASE
            WHEN random() < 0.12 THEN 'platinum'
            WHEN random() < 0.42 THEN 'gold'
            WHEN random() < 0.75 THEN 'silver'
            ELSE 'standard'
          END,
          DATE '2020-01-01' + ((random() * 1700)::INTEGER)
        FROM (
          SELECT
            seq,
            (ARRAY['Luca', 'Marta', 'Giulia', 'Alessandro', 'Chiara', 'Davide', 'Elena', 'Francesco', 'Sara', 'Marco', 'Priya', 'Jon', 'Nora', 'Hugo', 'Amina'])[1 + (random() * 14)::INTEGER] AS first_name,
            (ARRAY['Rossi', 'Bianchi', 'Verdi', 'Costa', 'Silva', 'Martin', 'Klein', 'Muller', 'Patel', 'Santos', 'Nguyen', 'Smith', 'Dubois', 'Ivanov', 'Lopez'])[1 + (random() * 14)::INTEGER] AS last_name,
            (ARRAY['IT', 'DE', 'FR', 'ES', 'NL', 'US', 'CA', 'MX', 'IN', 'SG', 'JP', 'AU'])[1 + (random() * 11)::INTEGER] AS country_code,
            (ARRAY['consumer', 'small_business', 'mid_market', 'enterprise'])[1 + (random() * 3)::INTEGER] AS segment
          FROM generate_series(1, 4000) AS generated(seq)
        ) AS seeded_customers;

        CREATE TABLE {schema}.dim_product (
          product_key INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          sku TEXT NOT NULL UNIQUE,
          product_name TEXT NOT NULL,
          category_name TEXT NOT NULL,
          brand_name TEXT NOT NULL,
          list_price NUMERIC(12, 2) NOT NULL,
          launch_date DATE NOT NULL,
          is_active BOOLEAN NOT NULL
        );

        INSERT INTO {schema}.dim_product (
          sku,
          product_name,
          category_name,
          brand_name,
          list_price,
          launch_date,
          is_active
        )
        SELECT
          FORMAT('SKU-%04s', seq),
          brand_name || ' ' || category_name || ' ' || FORMAT('%s', seq),
          category_name,
          brand_name,
          ROUND((base_price * (0.9 + random() * 0.35))::NUMERIC, 2),
          DATE '2021-01-01' + ((random() * 1400)::INTEGER),
          random() > 0.04
        FROM (
          SELECT
            seq,
            (ARRAY['Analytics', 'Storage', 'Compute', 'Security', 'Collaboration', 'Support', 'Devices', 'Accessories'])[1 + (random() * 7)::INTEGER] AS category_name,
            (ARRAY['Northwind', 'BluePeak', 'Aster', 'Nimbus', 'Helios', 'Vertex', 'Acumen', 'Solstice'])[1 + (random() * 7)::INTEGER] AS brand_name,
            (ARRAY[19, 29, 49, 79, 99, 149, 199, 249, 399, 599, 899, 1299])[1 + (random() * 11)::INTEGER] AS base_price
          FROM generate_series(1, 800) AS generated(seq)
        ) AS seeded_products;

        CREATE TABLE {schema}.dim_channel (
          channel_key INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          channel_name TEXT NOT NULL UNIQUE,
          channel_group TEXT NOT NULL,
          cost_ratio NUMERIC(6, 4) NOT NULL
        );

        INSERT INTO {schema}.dim_channel (channel_name, channel_group, cost_ratio) VALUES
          ('direct_web', 'digital', 0.0225),
          ('marketplace', 'digital', 0.0950),
          ('inside_sales', 'assisted', 0.0710),
          ('field_sales', 'assisted', 0.1100),
          ('partner', 'indirect', 0.1320),
          ('retail', 'offline', 0.0840);

        CREATE TABLE {schema}.fact_sales (
          sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_code TEXT NOT NULL UNIQUE,
          day_key INTEGER NOT NULL REFERENCES {schema}.dim_date(day_key),
          customer_key INTEGER NOT NULL REFERENCES {schema}.dim_customer(customer_key),
          product_key INTEGER NOT NULL REFERENCES {schema}.dim_product(product_key),
          channel_key INTEGER NOT NULL REFERENCES {schema}.dim_channel(channel_key),
          quantity INTEGER NOT NULL CHECK (quantity > 0),
          gross_amount NUMERIC(12, 2) NOT NULL,
          discount_amount NUMERIC(12, 2) NOT NULL,
          net_amount NUMERIC(12, 2) NOT NULL,
          returned BOOLEAN NOT NULL DEFAULT FALSE
        );

        INSERT INTO {schema}.fact_sales (
          order_code,
          day_key,
          customer_key,
          product_key,
          channel_key,
          quantity,
          gross_amount,
          discount_amount,
          net_amount
        )
        SELECT
          FORMAT('SO-%s-%06s', TO_CHAR(seed.sale_date, 'YYYYMM'), seed.seq),
          TO_CHAR(seed.sale_date, 'YYYYMMDD')::INTEGER,
          seed.customer_key,
          seed.product_key,
          seed.channel_key,
          seed.quantity,
          amounts.gross_amount,
          amounts.discount_amount,
          GREATEST(amounts.gross_amount - amounts.discount_amount, 0.01)
        FROM (
          SELECT
            seq,
            DATE '2024-01-01' + ((random() * 660)::INTEGER) AS sale_date,
            ((POWER(random(), 2.2) * 3999)::INTEGER + 1) AS customer_key,
            ((POWER(random(), 1.35) * 799)::INTEGER + 1) AS product_key,
            CASE
              WHEN random() < 0.38 THEN 1
              WHEN random() < 0.62 THEN 2
              WHEN random() < 0.77 THEN 3
              WHEN random() < 0.88 THEN 4
              WHEN random() < 0.95 THEN 5
              ELSE 6
            END AS channel_key,
            CASE
              WHEN random() < 0.56 THEN 1
              WHEN random() < 0.83 THEN 2
              WHEN random() < 0.94 THEN 3
              ELSE 4 + (random() * 3)::INTEGER
            END AS quantity
          FROM generate_series(1, 60000) AS generated(seq)
        ) AS seed
        JOIN {schema}.dim_product AS product
          ON product.product_key = seed.product_key
        CROSS JOIN LATERAL (
          SELECT
            ROUND((seed.quantity * product.list_price * (0.88 + random() * 0.28))::NUMERIC, 2) AS gross_amount,
            ROUND((
              CASE
                WHEN random() < 0.47 THEN seed.quantity * product.list_price * (0.02 + random() * 0.16)
                ELSE 0
              END
            )::NUMERIC, 2) AS discount_amount
        ) AS amounts;

        CREATE TABLE {schema}.fact_returns (
          return_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          sale_id BIGINT NOT NULL UNIQUE REFERENCES {schema}.fact_sales(sale_id) ON DELETE CASCADE,
          day_key INTEGER NOT NULL REFERENCES {schema}.dim_date(day_key),
          reason_code TEXT NOT NULL,
          quantity INTEGER NOT NULL CHECK (quantity > 0),
          refund_amount NUMERIC(12, 2) NOT NULL CHECK (refund_amount >= 0)
        );

        WITH selected_sales AS (
          SELECT
            sale_id,
            day_key,
            quantity,
            net_amount,
            (
              TO_DATE(day_key::TEXT, 'YYYYMMDD') +
              (1 + (random() * 45)::INTEGER)
            ) AS return_date
          FROM {schema}.fact_sales
          WHERE random() < 0.11
          LIMIT 7000
        ),
        inserted_returns AS (
          INSERT INTO {schema}.fact_returns (
            sale_id,
            day_key,
            reason_code,
            quantity,
            refund_amount
          )
          SELECT
            sale_id,
            TO_CHAR(return_date, 'YYYYMMDD')::INTEGER,
            (ARRAY['damaged', 'late_delivery', 'incorrect_item', 'not_as_expected', 'duplicate_order'])[1 + (random() * 4)::INTEGER],
            GREATEST(1, LEAST(quantity, CASE WHEN random() < 0.72 THEN 1 ELSE 2 END)),
            ROUND((net_amount * (0.35 + random() * 0.6))::NUMERIC, 2)
          FROM selected_sales
          RETURNING sale_id
        )
        UPDATE {schema}.fact_sales
        SET returned = TRUE
        WHERE sale_id IN (SELECT sale_id FROM inserted_returns);

        CREATE INDEX idx_sales_dw_fact_sales_customer_day ON {schema}.fact_sales(customer_key, day_key DESC);
        CREATE INDEX idx_sales_dw_fact_sales_product_day ON {schema}.fact_sales(product_key, day_key DESC);
        CREATE INDEX idx_sales_dw_fact_returns_day ON {schema}.fact_returns(day_key DESC);
        """
    )


def saas_billing_sql(schema_name: str) -> str:
    schema = quote_name(schema_name)
    return dedent(
        f"""
        SELECT setseed(0.2202);

        CREATE SCHEMA {schema};

        CREATE TABLE {schema}.accounts (
          account_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          account_code TEXT NOT NULL UNIQUE,
          company_name TEXT NOT NULL,
          region_name TEXT NOT NULL,
          industry TEXT NOT NULL,
          account_tier TEXT NOT NULL,
          seats_committed INTEGER NOT NULL,
          created_at TIMESTAMPTZ NOT NULL
        );

        INSERT INTO {schema}.accounts (
          account_code,
          company_name,
          region_name,
          industry,
          account_tier,
          seats_committed,
          created_at
        )
        SELECT
          FORMAT('ACC-%05s', seq),
          company_prefix || ' ' || company_suffix,
          region_name,
          industry,
          CASE
            WHEN random() < 0.14 THEN 'strategic'
            WHEN random() < 0.39 THEN 'enterprise'
            WHEN random() < 0.72 THEN 'growth'
            ELSE 'startup'
          END,
          5 + (random() * 450)::INTEGER,
          TIMESTAMPTZ '2021-01-01 00:00:00+00' + (((random() * 1400)::INTEGER) || ' days')::INTERVAL
        FROM (
          SELECT
            seq,
            (ARRAY['Bright', 'North', 'Summit', 'Vector', 'Orbit', 'Nimbus', 'Atlas', 'Apex', 'Signal', 'Harbor', 'Cobalt', 'Nova'])[1 + (random() * 11)::INTEGER] AS company_prefix,
            (ARRAY['Labs', 'Systems', 'Works', 'Cloud', 'Dynamics', 'Partners', 'Logistics', 'Retail', 'Health', 'Capital', 'Analytics', 'Foods'])[1 + (random() * 11)::INTEGER] AS company_suffix,
            (ARRAY['EMEA', 'Americas', 'APAC'])[1 + (random() * 2)::INTEGER] AS region_name,
            (ARRAY['fintech', 'healthcare', 'retail', 'manufacturing', 'media', 'education', 'logistics', 'software'])[1 + (random() * 7)::INTEGER] AS industry
          FROM generate_series(1, 4200) AS generated(seq)
        ) AS seeded_accounts;

        CREATE TABLE {schema}.plans (
          plan_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          plan_code TEXT NOT NULL UNIQUE,
          plan_name TEXT NOT NULL,
          billing_interval TEXT NOT NULL,
          base_price NUMERIC(12, 2) NOT NULL,
          included_units INTEGER NOT NULL,
          overage_unit_price NUMERIC(12, 4) NOT NULL
        );

        INSERT INTO {schema}.plans (
          plan_code,
          plan_name,
          billing_interval,
          base_price,
          included_units,
          overage_unit_price
        ) VALUES
          ('starter-monthly', 'Starter Monthly', 'monthly', 79.00, 5000, 0.0180),
          ('growth-monthly', 'Growth Monthly', 'monthly', 249.00, 18000, 0.0145),
          ('scale-monthly', 'Scale Monthly', 'monthly', 699.00, 65000, 0.0105),
          ('enterprise-annual', 'Enterprise Annual', 'annual', 9500.00, 1200000, 0.0075),
          ('usage-flex', 'Usage Flex', 'monthly', 39.00, 1200, 0.0220);

        CREATE TABLE {schema}.subscriptions (
          subscription_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          account_id INTEGER NOT NULL REFERENCES {schema}.accounts(account_id),
          plan_id INTEGER NOT NULL REFERENCES {schema}.plans(plan_id),
          subscription_code TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL,
          seats INTEGER NOT NULL,
          monthly_recurring_revenue NUMERIC(12, 2) NOT NULL,
          started_at TIMESTAMPTZ NOT NULL,
          cancelled_at TIMESTAMPTZ
        );

        INSERT INTO {schema}.subscriptions (
          account_id,
          plan_id,
          subscription_code,
          status,
          seats,
          monthly_recurring_revenue,
          started_at,
          cancelled_at
        )
        SELECT
          account_id,
          plan_id,
          FORMAT('SUB-%05s', seq),
          status,
          seats,
          ROUND((
            CASE
              WHEN plan_id = 4 THEN (plan_price / 12.0) + seats * 7.5
              ELSE plan_price + seats * seat_multiplier
            END
          )::NUMERIC, 2),
          started_at,
          CASE
            WHEN status IN ('cancelled', 'expired')
              THEN started_at + ((60 + (random() * 420)::INTEGER) || ' days')::INTERVAL
            ELSE NULL
          END
        FROM (
          SELECT
            seq,
            ((POWER(random(), 2.0) * 4199)::INTEGER + 1) AS account_id,
            CASE
              WHEN random() < 0.24 THEN 1
              WHEN random() < 0.52 THEN 2
              WHEN random() < 0.74 THEN 3
              WHEN random() < 0.9 THEN 4
              ELSE 5
            END AS plan_id,
            CASE
              WHEN random() < 0.67 THEN 'active'
              WHEN random() < 0.79 THEN 'trialing'
              WHEN random() < 0.91 THEN 'past_due'
              WHEN random() < 0.97 THEN 'cancelled'
              ELSE 'expired'
            END AS status,
            3 + (random() * 290)::INTEGER AS seats,
            TIMESTAMPTZ '2022-01-01 00:00:00+00' + (((random() * 1200)::INTEGER) || ' days')::INTERVAL AS started_at
          FROM generate_series(1, 6200) AS generated(seq)
        ) AS seeds
        JOIN LATERAL (
          SELECT
            CASE plan_id
              WHEN 1 THEN 79.0
              WHEN 2 THEN 249.0
              WHEN 3 THEN 699.0
              WHEN 4 THEN 9500.0
              ELSE 39.0
            END AS plan_price,
            CASE
              WHEN plan_id = 1 THEN 3.5
              WHEN plan_id = 2 THEN 4.2
              WHEN plan_id = 3 THEN 5.8
              WHEN plan_id = 4 THEN 7.5
              ELSE 2.2
            END AS seat_multiplier
        ) AS pricing ON TRUE;

        CREATE TABLE {schema}.invoices (
          invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          invoice_number TEXT NOT NULL UNIQUE,
          subscription_id INTEGER NOT NULL REFERENCES {schema}.subscriptions(subscription_id),
          account_id INTEGER NOT NULL REFERENCES {schema}.accounts(account_id),
          status TEXT NOT NULL,
          issued_at TIMESTAMPTZ NOT NULL,
          due_at TIMESTAMPTZ NOT NULL,
          paid_at TIMESTAMPTZ,
          subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
          tax_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
          total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0
        );

        INSERT INTO {schema}.invoices (
          invoice_number,
          subscription_id,
          account_id,
          status,
          issued_at,
          due_at,
          paid_at
        )
        SELECT
          FORMAT('INV-%s-%06s', TO_CHAR(invoice_seed.issued_at, 'YYYYMM'), invoice_seed.seq),
          invoice_seed.subscription_id,
          invoice_seed.account_id,
          invoice_seed.status,
          invoice_seed.issued_at,
          invoice_seed.issued_at + INTERVAL '15 days',
          CASE
            WHEN invoice_seed.status = 'paid'
              THEN invoice_seed.issued_at + ((1 + (random() * 12)::INTEGER) || ' days')::INTERVAL
            ELSE NULL
          END
        FROM (
          SELECT
            seeded_invoices.seq,
            seeded_invoices.subscription_id,
            subscriptions.account_id,
            TIMESTAMPTZ '2024-01-01 00:00:00+00' + (((random() * 680)::INTEGER) || ' days')::INTERVAL AS issued_at,
            CASE
              WHEN random() < 0.79 THEN 'paid'
              WHEN random() < 0.9 THEN 'open'
              WHEN random() < 0.96 THEN 'past_due'
              WHEN random() < 0.985 THEN 'void'
              ELSE 'uncollectible'
            END AS status
          FROM (
            SELECT
              seq,
              ((POWER(random(), 1.8) * 6199)::INTEGER + 1) AS subscription_id
            FROM generate_series(1, 24000) AS generated(seq)
          ) AS seeded_invoices
          JOIN {schema}.subscriptions AS subscriptions
            ON subscriptions.subscription_id = seeded_invoices.subscription_id
        ) AS invoice_seed;

        CREATE TABLE {schema}.invoice_items (
          invoice_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          invoice_id BIGINT NOT NULL REFERENCES {schema}.invoices(invoice_id) ON DELETE CASCADE,
          line_type TEXT NOT NULL,
          description TEXT NOT NULL,
          quantity INTEGER NOT NULL,
          unit_price NUMERIC(12, 2) NOT NULL,
          amount NUMERIC(12, 2) NOT NULL
        );

        INSERT INTO {schema}.invoice_items (
          invoice_id,
          line_type,
          description,
          quantity,
          unit_price,
          amount
        )
        SELECT
          invoices.invoice_id,
          'recurring',
          plans.plan_name || ' base subscription',
          1,
          ROUND((
            CASE
              WHEN plans.plan_id = 4 THEN subscriptions.monthly_recurring_revenue * 0.74
              ELSE subscriptions.monthly_recurring_revenue * 0.82
            END
          )::NUMERIC, 2),
          ROUND((
            CASE
              WHEN plans.plan_id = 4 THEN subscriptions.monthly_recurring_revenue * 0.74
              ELSE subscriptions.monthly_recurring_revenue * 0.82
            END
          )::NUMERIC, 2)
        FROM {schema}.invoices AS invoices
        JOIN {schema}.subscriptions AS subscriptions
          ON subscriptions.subscription_id = invoices.subscription_id
        JOIN {schema}.plans AS plans
          ON plans.plan_id = subscriptions.plan_id;

        INSERT INTO {schema}.invoice_items (
          invoice_id,
          line_type,
          description,
          quantity,
          unit_price,
          amount
        )
        SELECT
          invoices.invoice_id,
          'seat_expansion',
          'Additional seats',
          seat_line.extra_seats,
          seat_line.unit_price,
          ROUND((seat_line.extra_seats * seat_line.unit_price)::NUMERIC, 2)
        FROM {schema}.invoices AS invoices
        JOIN {schema}.subscriptions AS subscriptions
          ON subscriptions.subscription_id = invoices.subscription_id
        CROSS JOIN LATERAL (
          SELECT
            1 + (random() * GREATEST(subscriptions.seats / 6, 1))::INTEGER AS extra_seats,
            ROUND((2.5 + random() * 22)::NUMERIC, 2) AS unit_price
        ) AS seat_line
        WHERE random() < 0.58;

        INSERT INTO {schema}.invoice_items (
          invoice_id,
          line_type,
          description,
          quantity,
          unit_price,
          amount
        )
        SELECT
          invoices.invoice_id,
          'usage_overage',
          'API overage units',
          overage_line.quantity,
          overage_line.unit_price,
          ROUND((overage_line.quantity * overage_line.unit_price)::NUMERIC, 2)
        FROM {schema}.invoices AS invoices
        JOIN {schema}.subscriptions AS subscriptions
          ON subscriptions.subscription_id = invoices.subscription_id
        JOIN {schema}.plans AS plans
          ON plans.plan_id = subscriptions.plan_id
        CROSS JOIN LATERAL (
          SELECT
            50 + (random() * 950)::INTEGER AS quantity,
            ROUND((plans.overage_unit_price * (0.9 + random() * 0.25))::NUMERIC, 4) AS unit_price
        ) AS overage_line
        WHERE random() < 0.64;

        INSERT INTO {schema}.invoice_items (
          invoice_id,
          line_type,
          description,
          quantity,
          unit_price,
          amount
        )
        SELECT
          invoice_id,
          'setup',
          'One-time onboarding',
          1,
          setup_line.amount,
          setup_line.amount
        FROM {schema}.invoices
        CROSS JOIN LATERAL (
          SELECT ROUND((150 + random() * 1850)::NUMERIC, 2) AS amount
        ) AS setup_line
        WHERE random() < 0.14;

        UPDATE {schema}.invoices AS invoices
        SET
          subtotal = totals.subtotal,
          tax_amount = totals.tax_amount,
          total_amount = totals.subtotal + totals.tax_amount
        FROM (
          SELECT
            invoices.invoice_id,
            ROUND(SUM(items.amount)::NUMERIC, 2) AS subtotal,
            ROUND((SUM(items.amount) * (
              CASE accounts.region_name
                WHEN 'EMEA' THEN 0.22
                WHEN 'Americas' THEN 0.08
                ELSE 0.11
              END
            ))::NUMERIC, 2) AS tax_amount
          FROM {schema}.invoices AS invoices
          JOIN {schema}.invoice_items AS items
            ON items.invoice_id = invoices.invoice_id
          JOIN {schema}.accounts AS accounts
            ON accounts.account_id = invoices.account_id
          GROUP BY invoices.invoice_id, accounts.region_name
        ) AS totals
        WHERE invoices.invoice_id = totals.invoice_id;

        CREATE TABLE {schema}.usage_events (
          usage_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          subscription_id INTEGER NOT NULL REFERENCES {schema}.subscriptions(subscription_id),
          account_id INTEGER NOT NULL REFERENCES {schema}.accounts(account_id),
          feature_name TEXT NOT NULL,
          event_ts TIMESTAMPTZ NOT NULL,
          units INTEGER NOT NULL,
          billable_amount NUMERIC(12, 4) NOT NULL
        );

        INSERT INTO {schema}.usage_events (
          subscription_id,
          account_id,
          feature_name,
          event_ts,
          units,
          billable_amount
        )
        SELECT
          subscriptions.subscription_id,
          subscriptions.account_id,
          (ARRAY['api_calls', 'storage_gb', 'workflow_runs', 'agent_minutes', 'alerts'])[1 + (random() * 4)::INTEGER],
          TIMESTAMPTZ '2024-01-01 00:00:00+00' + (((random() * 720 * 24)::INTEGER) || ' hours')::INTERVAL,
          units,
          ROUND((
            units * plans.overage_unit_price * (0.45 + random() * 0.85)
          )::NUMERIC, 4)
        FROM (
          SELECT
            ((POWER(random(), 1.75) * 6199)::INTEGER + 1) AS subscription_id,
            25 + (random() * 4500)::INTEGER AS units
          FROM generate_series(1, 85000)
        ) AS seeded_events
        JOIN {schema}.subscriptions AS subscriptions
          ON subscriptions.subscription_id = seeded_events.subscription_id
        JOIN {schema}.plans AS plans
          ON plans.plan_id = subscriptions.plan_id;

        CREATE INDEX idx_saas_billing_subscriptions_account ON {schema}.subscriptions(account_id);
        CREATE INDEX idx_saas_billing_invoices_subscription_date ON {schema}.invoices(subscription_id, issued_at DESC);
        CREATE INDEX idx_saas_billing_usage_subscription_ts ON {schema}.usage_events(subscription_id, event_ts DESC);
        """
    )


def support_ops_sql(schema_name: str) -> str:
    schema = quote_name(schema_name)
    return dedent(
        f"""
        SELECT setseed(0.3303);

        CREATE SCHEMA {schema};

        CREATE TABLE {schema}.customers (
          customer_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          customer_code TEXT NOT NULL UNIQUE,
          customer_name TEXT NOT NULL,
          region_name TEXT NOT NULL,
          plan_name TEXT NOT NULL,
          joined_at TIMESTAMPTZ NOT NULL
        );

        INSERT INTO {schema}.customers (
          customer_code,
          customer_name,
          region_name,
          plan_name,
          joined_at
        )
        SELECT
          FORMAT('CUS-%05s', seq),
          organization_name,
          region_name,
          (ARRAY['starter', 'growth', 'business', 'enterprise'])[1 + (random() * 3)::INTEGER],
          TIMESTAMPTZ '2021-01-01 00:00:00+00' + (((random() * 1500)::INTEGER) || ' days')::INTERVAL
        FROM (
          SELECT
            seq,
            (ARRAY['Acorn', 'Bluebird', 'Crescent', 'Delta', 'Evergreen', 'Falcon', 'Granite', 'Harbor', 'Ivory', 'Juniper', 'Keystone', 'Lumen', 'Maple', 'Northstar'])[1 + (random() * 13)::INTEGER] ||
              ' ' ||
              (ARRAY['Retail', 'Health', 'Logistics', 'Media', 'Tech', 'Foods', 'Advisory', 'Mobility', 'Works', 'Capital', 'Studios', 'Energy'])[1 + (random() * 11)::INTEGER] AS organization_name,
            (ARRAY['EMEA', 'Americas', 'APAC'])[1 + (random() * 2)::INTEGER] AS region_name
          FROM generate_series(1, 6000) AS generated(seq)
        ) AS seeded_customers;

        CREATE TABLE {schema}.agents (
          agent_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          full_name TEXT NOT NULL,
          squad_name TEXT NOT NULL,
          locale TEXT NOT NULL,
          tenure_months INTEGER NOT NULL,
          active BOOLEAN NOT NULL
        );

        INSERT INTO {schema}.agents (
          full_name,
          squad_name,
          locale,
          tenure_months,
          active
        )
        SELECT
          first_name || ' ' || last_name,
          (ARRAY['core_support', 'billing', 'platform', 'enterprise', 'weekend'])[1 + (random() * 4)::INTEGER],
          (ARRAY['it-IT', 'en-US', 'en-GB', 'es-ES', 'de-DE', 'fr-FR'])[1 + (random() * 5)::INTEGER],
          1 + (random() * 60)::INTEGER,
          random() > 0.08
        FROM (
          SELECT
            (ARRAY['Luca', 'Marta', 'Giada', 'Federico', 'Sofia', 'Elisa', 'Matteo', 'Noah', 'Priya', 'Javier', 'Hana', 'Eva', 'Dario', 'Irene'])[1 + (random() * 13)::INTEGER] AS first_name,
            (ARRAY['Rossi', 'Bernard', 'Costa', 'Patel', 'Kim', 'Miller', 'Garcia', 'Klein', 'Dubois', 'Brown', 'Conti', 'Silva'])[1 + (random() * 11)::INTEGER] AS last_name
          FROM generate_series(1, 180) AS generated(seq)
        ) AS seeded_agents;

        CREATE TABLE {schema}.ticket_categories (
          category_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          category_name TEXT NOT NULL UNIQUE,
          default_sla_hours INTEGER NOT NULL
        );

        INSERT INTO {schema}.ticket_categories (category_name, default_sla_hours) VALUES
          ('login_access', 4),
          ('billing', 8),
          ('bug_report', 12),
          ('performance', 8),
          ('api_integration', 16),
          ('feature_request', 48),
          ('data_export', 12),
          ('security_review', 6);

        CREATE TABLE {schema}.tickets (
          ticket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          ticket_code TEXT NOT NULL UNIQUE,
          customer_id INTEGER NOT NULL REFERENCES {schema}.customers(customer_id),
          assigned_agent_id INTEGER REFERENCES {schema}.agents(agent_id),
          category_id INTEGER NOT NULL REFERENCES {schema}.ticket_categories(category_id),
          priority TEXT NOT NULL,
          support_channel TEXT NOT NULL,
          status TEXT NOT NULL,
          opened_at TIMESTAMPTZ NOT NULL,
          first_response_at TIMESTAMPTZ,
          resolved_at TIMESTAMPTZ,
          sla_breached BOOLEAN NOT NULL
        );

        INSERT INTO {schema}.tickets (
          ticket_code,
          customer_id,
          assigned_agent_id,
          category_id,
          priority,
          support_channel,
          status,
          opened_at,
          first_response_at,
          resolved_at,
          sla_breached
        )
        SELECT
          FORMAT('TCK-%s-%06s', TO_CHAR(seeded_tickets.opened_at, 'YYYYMM'), seeded_tickets.seq),
          seeded_tickets.customer_id,
          seeded_tickets.assigned_agent_id,
          seeded_tickets.category_id,
          seeded_tickets.priority,
          seeded_tickets.support_channel,
          ticket_shape.status,
          seeded_tickets.opened_at,
          ticket_shape.first_response_at,
          resolution.resolved_at,
          seeded_tickets.response_hours > ticket_shape.sla_hours
        FROM (
          SELECT
            seq,
            ((POWER(random(), 1.85) * 5999)::INTEGER + 1) AS customer_id,
            ((random() * 179)::INTEGER + 1) AS assigned_agent_id,
            ((random() * 7)::INTEGER + 1) AS category_id,
            (ARRAY['low', 'medium', 'high', 'urgent'])[1 + (random() * 3)::INTEGER] AS priority,
            (ARRAY['email', 'chat', 'phone', 'portal'])[1 + (random() * 3)::INTEGER] AS support_channel,
            TIMESTAMPTZ '2024-01-01 00:00:00+00' + (((random() * 700 * 24)::INTEGER) || ' hours')::INTERVAL AS opened_at,
            1 + (random() * 60)::INTEGER AS response_hours,
            6 + (random() * 240)::INTEGER AS resolve_hours
          FROM generate_series(1, 30000) AS generated(seq)
        ) AS seeded_tickets
        JOIN {schema}.ticket_categories AS categories
          ON categories.category_id = seeded_tickets.category_id
        CROSS JOIN LATERAL (
          SELECT
            seeded_tickets.opened_at + (seeded_tickets.response_hours || ' hours')::INTERVAL AS first_response_at,
            CASE
              WHEN random() < 0.68 THEN 'resolved'
              WHEN random() < 0.84 THEN 'closed'
              WHEN random() < 0.93 THEN 'pending_customer'
              ELSE 'open'
            END AS status,
            categories.default_sla_hours AS sla_hours
        ) AS ticket_shape
        CROSS JOIN LATERAL (
          SELECT
            CASE
              WHEN ticket_shape.status IN ('resolved', 'closed')
                THEN ticket_shape.first_response_at + (seeded_tickets.resolve_hours || ' hours')::INTERVAL
              ELSE NULL
            END AS resolved_at
        ) AS resolution;

        CREATE TABLE {schema}.ticket_events (
          ticket_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          ticket_id BIGINT NOT NULL REFERENCES {schema}.tickets(ticket_id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          status_after TEXT NOT NULL,
          actor_type TEXT NOT NULL,
          occurred_at TIMESTAMPTZ NOT NULL,
          note_length INTEGER NOT NULL
        );

        INSERT INTO {schema}.ticket_events (
          ticket_id,
          event_type,
          status_after,
          actor_type,
          occurred_at,
          note_length
        )
        SELECT
          tickets.ticket_id,
          event_type,
          status_after,
          actor_type,
          occurred_at,
          note_length
        FROM {schema}.tickets AS tickets
        CROSS JOIN LATERAL (
          VALUES
            ('created', 'open', 'customer', tickets.opened_at, 90 + (random() * 140)::INTEGER),
            ('assigned', 'open', 'system', tickets.opened_at + ((5 + random() * 180)::INTEGER || ' minutes')::INTERVAL, 35 + (random() * 45)::INTEGER),
            ('responded', 'in_progress', 'agent', COALESCE(tickets.first_response_at, tickets.opened_at + INTERVAL '1 hour'), 120 + (random() * 180)::INTEGER),
            (
              CASE
                WHEN tickets.status IN ('resolved', 'closed') THEN 'resolved'
                WHEN tickets.status = 'pending_customer' THEN 'waiting_customer'
                ELSE 'follow_up'
              END,
              tickets.status,
              CASE WHEN tickets.status IN ('resolved', 'closed') THEN 'agent' ELSE 'system' END,
              COALESCE(tickets.resolved_at, tickets.first_response_at + ((6 + random() * 72)::INTEGER || ' hours')::INTERVAL),
              80 + (random() * 160)::INTEGER
            )
        ) AS event_rows(event_type, status_after, actor_type, occurred_at, note_length);

        CREATE TABLE {schema}.csat_surveys (
          survey_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          ticket_id BIGINT NOT NULL UNIQUE REFERENCES {schema}.tickets(ticket_id) ON DELETE CASCADE,
          submitted_at TIMESTAMPTZ NOT NULL,
          score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
          sentiment TEXT NOT NULL,
          response_channel TEXT NOT NULL
        );

        INSERT INTO {schema}.csat_surveys (
          ticket_id,
          submitted_at,
          score,
          sentiment,
          response_channel
        )
        SELECT
          ticket_id,
          resolved_at + ((6 + random() * 120)::INTEGER || ' hours')::INTERVAL,
          score,
          CASE
            WHEN score >= 5 THEN 'promoter'
            WHEN score = 4 THEN 'satisfied'
            WHEN score = 3 THEN 'neutral'
            ELSE 'detractor'
          END,
          (ARRAY['email', 'portal', 'in_app'])[1 + (random() * 2)::INTEGER]
        FROM (
          SELECT
            ticket_id,
            resolved_at,
            CASE
              WHEN sla_breached THEN 2 + (random() * 2)::INTEGER
              WHEN priority = 'urgent' THEN 3 + (random() * 2)::INTEGER
              ELSE 3 + (random() * 2)::INTEGER
            END AS score
          FROM {schema}.tickets
          WHERE resolved_at IS NOT NULL
            AND random() < 0.32
        ) AS eligible_surveys;

        CREATE INDEX idx_support_ops_tickets_customer_opened ON {schema}.tickets(customer_id, opened_at DESC);
        CREATE INDEX idx_support_ops_tickets_status_priority ON {schema}.tickets(status, priority);
        CREATE INDEX idx_support_ops_ticket_events_ticket_time ON {schema}.ticket_events(ticket_id, occurred_at);
        """
    )


DATASET_TEMPLATES: dict[str, DatasetTemplate] = {
    "sales_dw": DatasetTemplate(
        id="sales_dw",
        name="Sales Data Warehouse",
        description="Star schema di vendite con dimensioni clienti, prodotti, canali e fatti di vendita e reso.",
        schema_name="sales_dw",
        estimated_rows=78900,
        table_names=("dim_date", "dim_customer", "dim_product", "dim_channel", "fact_sales", "fact_returns"),
        starter_queries=(
            StarterQuery(
                title="Ricavi mensili",
                sql=dedent(
                    """
                    SELECT d.calendar_year, d.month_number, ROUND(SUM(s.net_amount), 2) AS revenue
                    FROM sales_dw.fact_sales s
                    JOIN sales_dw.dim_date d ON d.day_key = s.day_key
                    GROUP BY d.calendar_year, d.month_number
                    ORDER BY d.calendar_year, d.month_number;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Top categorie",
                sql=dedent(
                    """
                    SELECT p.category_name, ROUND(SUM(s.net_amount), 2) AS revenue
                    FROM sales_dw.fact_sales s
                    JOIN sales_dw.dim_product p ON p.product_key = s.product_key
                    GROUP BY p.category_name
                    ORDER BY revenue DESC
                    LIMIT 10;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Tasso resi per paese",
                sql=dedent(
                    """
                    SELECT c.country_code,
                           COUNT(r.return_id) AS returns_count,
                           COUNT(s.sale_id) AS sales_count,
                           ROUND(COUNT(r.return_id)::NUMERIC / NULLIF(COUNT(s.sale_id), 0), 4) AS return_rate
                    FROM sales_dw.fact_sales s
                    JOIN sales_dw.dim_customer c ON c.customer_key = s.customer_key
                    LEFT JOIN sales_dw.fact_returns r ON r.sale_id = s.sale_id
                    GROUP BY c.country_code
                    ORDER BY return_rate DESC NULLS LAST, sales_count DESC;
                    """
                ).strip(),
            ),
        ),
        seed_sql=sales_dw_sql("sales_dw"),
    ),
    "saas_billing": DatasetTemplate(
        id="saas_billing",
        name="SaaS Billing",
        description="Account, sottoscrizioni, fatture, line item e usage events per workload SaaS a consumo.",
        schema_name="saas_billing",
        estimated_rows=181400,
        table_names=("accounts", "plans", "subscriptions", "invoices", "invoice_items", "usage_events"),
        starter_queries=(
            StarterQuery(
                title="MRR per piano",
                sql=dedent(
                    """
                    SELECT p.plan_name,
                           ROUND(SUM(s.monthly_recurring_revenue), 2) AS mrr
                    FROM saas_billing.subscriptions s
                    JOIN saas_billing.plans p ON p.plan_id = s.plan_id
                    WHERE s.status IN ('active', 'trialing', 'past_due')
                    GROUP BY p.plan_name
                    ORDER BY mrr DESC;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Fatturato mensile",
                sql=dedent(
                    """
                    SELECT DATE_TRUNC('month', issued_at) AS month,
                           ROUND(SUM(total_amount), 2) AS invoiced_total,
                           COUNT(*) AS invoices
                    FROM saas_billing.invoices
                    WHERE status <> 'void'
                    GROUP BY month
                    ORDER BY month;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Top account per usage",
                sql=dedent(
                    """
                    SELECT a.company_name,
                           SUM(u.units) AS total_units,
                           ROUND(SUM(u.billable_amount), 2) AS billable
                    FROM saas_billing.usage_events u
                    JOIN saas_billing.accounts a ON a.account_id = u.account_id
                    GROUP BY a.company_name
                    ORDER BY total_units DESC
                    LIMIT 15;
                    """
                ).strip(),
            ),
        ),
        seed_sql=saas_billing_sql("saas_billing"),
    ),
    "support_ops": DatasetTemplate(
        id="support_ops",
        name="Support Operations",
        description="Clienti, agenti, ticket, storico eventi e survey CSAT per simulare un help desk operativo.",
        schema_name="support_ops",
        estimated_rows=163200,
        table_names=("customers", "agents", "ticket_categories", "tickets", "ticket_events", "csat_surveys"),
        starter_queries=(
            StarterQuery(
                title="Backlog per stato",
                sql=dedent(
                    """
                    SELECT status, priority, COUNT(*) AS tickets
                    FROM support_ops.tickets
                    GROUP BY status, priority
                    ORDER BY tickets DESC;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Tempo medio di risposta",
                sql=dedent(
                    """
                    SELECT c.category_name,
                           ROUND(AVG(EXTRACT(EPOCH FROM (t.first_response_at - t.opened_at)) / 3600)::NUMERIC, 2) AS avg_response_hours
                    FROM support_ops.tickets t
                    JOIN support_ops.ticket_categories c ON c.category_id = t.category_id
                    WHERE t.first_response_at IS NOT NULL
                    GROUP BY c.category_name
                    ORDER BY avg_response_hours DESC;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="CSAT per regione",
                sql=dedent(
                    """
                    SELECT customers.region_name,
                           ROUND(AVG(s.score)::NUMERIC, 2) AS avg_csat,
                           COUNT(*) AS surveys
                    FROM support_ops.csat_surveys s
                    JOIN support_ops.tickets t ON t.ticket_id = s.ticket_id
                    JOIN support_ops.customers customers ON customers.customer_id = t.customer_id
                    GROUP BY customers.region_name
                    ORDER BY avg_csat DESC;
                    """
                ).strip(),
            ),
        ),
        seed_sql=support_ops_sql("support_ops"),
    ),
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
