from textwrap import dedent
from app.models import (
    StarterQuery,
)

from app.sql_seeds.models import DatasetTemplate, quote_name

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

SaasBillingDatasetTemplate = DatasetTemplate(
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
    )