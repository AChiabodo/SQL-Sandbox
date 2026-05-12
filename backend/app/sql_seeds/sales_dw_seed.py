from textwrap import dedent


from app.sql_seeds.models import DatasetTemplate, quote_name

from app.models import (
    StarterQuery,
)

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

SalesDatasetTemplate = DatasetTemplate(
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
    )