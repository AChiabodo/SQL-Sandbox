from textwrap import dedent
from app.models import (
    StarterQuery,
)
from app.sql_seeds.models import DatasetTemplate, quote_name


def commerce_ops_sql(schema_name: str) -> str:
    schema = quote_name(schema_name)
    return dedent(
        f"""
        SELECT setseed(0.4404);

        CREATE SCHEMA {schema};

        CREATE TABLE {schema}.countries (
          country_code TEXT PRIMARY KEY,
          country_name TEXT NOT NULL,
          region_name TEXT NOT NULL,
          currency_code TEXT NOT NULL,
          vat_rate NUMERIC(5, 2) NOT NULL CHECK (vat_rate >= 0)
        );

        CREATE TABLE {schema}.sales_channels (
          channel_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          channel_code TEXT NOT NULL UNIQUE,
          channel_name TEXT NOT NULL,
          channel_type TEXT NOT NULL,
          default_currency TEXT NOT NULL,
          launched_at DATE NOT NULL
        );

        CREATE TABLE {schema}.warehouses (
          warehouse_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          warehouse_code TEXT NOT NULL UNIQUE,
          warehouse_name TEXT NOT NULL,
          country_code TEXT NOT NULL REFERENCES {schema}.countries(country_code),
          city_name TEXT NOT NULL,
          timezone_name TEXT NOT NULL,
          is_fulfillment_center BOOLEAN NOT NULL,
          opened_at DATE NOT NULL
        );

        CREATE TABLE {schema}.carriers (
          carrier_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          carrier_code TEXT NOT NULL UNIQUE,
          carrier_name TEXT NOT NULL,
          service_level TEXT NOT NULL,
          supports_express BOOLEAN NOT NULL
        );

        CREATE TABLE {schema}.suppliers (
          supplier_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          supplier_code TEXT NOT NULL UNIQUE,
          supplier_name TEXT NOT NULL,
          country_code TEXT NOT NULL REFERENCES {schema}.countries(country_code),
          supplier_tier TEXT NOT NULL,
          lead_time_days INTEGER NOT NULL CHECK (lead_time_days > 0),
          payment_terms_days INTEGER NOT NULL CHECK (payment_terms_days > 0),
          status TEXT NOT NULL
        );

        CREATE TABLE {schema}.product_categories (
          category_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          category_code TEXT NOT NULL UNIQUE,
          category_name TEXT NOT NULL,
          parent_category_code TEXT NULL REFERENCES {schema}.product_categories(category_code),
          department_name TEXT NOT NULL
        );

        CREATE TABLE {schema}.products (
          product_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          product_code TEXT NOT NULL UNIQUE,
          category_id INTEGER NOT NULL REFERENCES {schema}.product_categories(category_id),
          primary_supplier_id INTEGER NOT NULL REFERENCES {schema}.suppliers(supplier_id),
          product_name TEXT NOT NULL,
          brand_name TEXT NOT NULL,
          product_status TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          discontinued_at TIMESTAMPTZ NULL
        );

        CREATE TABLE {schema}.sku_variants (
          sku_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          product_id INTEGER NOT NULL REFERENCES {schema}.products(product_id),
          sku_code TEXT NOT NULL UNIQUE,
          variant_name TEXT NOT NULL,
          color_name TEXT NOT NULL,
          size_label TEXT NOT NULL,
          unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
          list_price NUMERIC(12, 2) NOT NULL CHECK (list_price >= unit_cost),
          weight_grams INTEGER NOT NULL CHECK (weight_grams > 0),
          launch_date DATE NOT NULL,
          is_active BOOLEAN NOT NULL
        );

        CREATE TABLE {schema}.supplier_skus (
          supplier_sku_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          supplier_id INTEGER NOT NULL REFERENCES {schema}.suppliers(supplier_id),
          sku_id INTEGER NOT NULL REFERENCES {schema}.sku_variants(sku_id),
          supplier_item_code TEXT NOT NULL UNIQUE,
          is_primary BOOLEAN NOT NULL,
          min_order_qty INTEGER NOT NULL CHECK (min_order_qty > 0),
          case_pack_qty INTEGER NOT NULL CHECK (case_pack_qty > 0),
          latest_unit_cost NUMERIC(12, 2) NOT NULL CHECK (latest_unit_cost >= 0),
          lead_time_days INTEGER NOT NULL CHECK (lead_time_days > 0)
        );

        CREATE TABLE {schema}.customers (
          customer_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          customer_code TEXT NOT NULL UNIQUE,
          first_name TEXT NOT NULL,
          last_name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE,
          phone_number TEXT NOT NULL,
          country_code TEXT NOT NULL REFERENCES {schema}.countries(country_code),
          acquisition_channel_id INTEGER NOT NULL REFERENCES {schema}.sales_channels(channel_id),
          loyalty_tier TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          birth_date DATE NULL
        );

        CREATE TABLE {schema}.customer_addresses (
          address_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          customer_id INTEGER NOT NULL REFERENCES {schema}.customers(customer_id),
          address_type TEXT NOT NULL CHECK (address_type IN ('billing', 'shipping')),
          recipient_name TEXT NOT NULL,
          line1 TEXT NOT NULL,
          line2 TEXT NULL,
          postal_code TEXT NOT NULL,
          city_name TEXT NOT NULL,
          country_code TEXT NOT NULL REFERENCES {schema}.countries(country_code),
          is_default BOOLEAN NOT NULL,
          created_at TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE {schema}.orders (
          order_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_number TEXT NOT NULL UNIQUE,
          customer_id INTEGER NOT NULL REFERENCES {schema}.customers(customer_id),
          billing_address_id INTEGER NOT NULL REFERENCES {schema}.customer_addresses(address_id),
          shipping_address_id INTEGER NOT NULL REFERENCES {schema}.customer_addresses(address_id),
          sales_channel_id INTEGER NOT NULL REFERENCES {schema}.sales_channels(channel_id),
          warehouse_id INTEGER NOT NULL REFERENCES {schema}.warehouses(warehouse_id),
          order_status TEXT NOT NULL CHECK (order_status IN ('pending_payment', 'processing', 'packed', 'shipped', 'delivered', 'partially_returned', 'cancelled')),
          currency_code TEXT NOT NULL,
          placed_at TIMESTAMPTZ NOT NULL,
          paid_at TIMESTAMPTZ NULL,
          shipped_at TIMESTAMPTZ NULL,
          promised_ship_by TIMESTAMPTZ NOT NULL,
          subtotal_amount NUMERIC(12, 2) NOT NULL CHECK (subtotal_amount >= 0),
          discount_amount NUMERIC(12, 2) NOT NULL CHECK (discount_amount >= 0),
          shipping_amount NUMERIC(12, 2) NOT NULL CHECK (shipping_amount >= 0),
          tax_amount NUMERIC(12, 2) NOT NULL CHECK (tax_amount >= 0),
          total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
          payment_status TEXT NOT NULL CHECK (payment_status IN ('pending', 'paid', 'partially_refunded', 'voided')),
          fulfillment_status TEXT NOT NULL CHECK (fulfillment_status IN ('unallocated', 'allocated', 'packed', 'shipped', 'delivered', 'cancelled'))
        );

        CREATE TABLE {schema}.order_items (
          order_item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_id INTEGER NOT NULL REFERENCES {schema}.orders(order_id),
          sku_id INTEGER NOT NULL REFERENCES {schema}.sku_variants(sku_id),
          quantity INTEGER NOT NULL CHECK (quantity > 0),
          unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
          discount_amount NUMERIC(12, 2) NOT NULL CHECK (discount_amount >= 0),
          tax_amount NUMERIC(12, 2) NOT NULL CHECK (tax_amount >= 0),
          line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0),
          requested_delivery_date DATE NOT NULL
        );

        CREATE TABLE {schema}.payments (
          payment_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_id INTEGER NOT NULL REFERENCES {schema}.orders(order_id),
          payment_reference TEXT NOT NULL UNIQUE,
          payment_method TEXT NOT NULL,
          processor_name TEXT NOT NULL,
          payment_status TEXT NOT NULL CHECK (payment_status IN ('authorized', 'captured', 'partially_refunded', 'voided')),
          authorized_at TIMESTAMPTZ NOT NULL,
          captured_at TIMESTAMPTZ NULL,
          amount_authorized NUMERIC(12, 2) NOT NULL CHECK (amount_authorized >= 0),
          amount_captured NUMERIC(12, 2) NOT NULL CHECK (amount_captured >= 0),
          amount_refunded NUMERIC(12, 2) NOT NULL CHECK (amount_refunded >= 0)
        );

        CREATE TABLE {schema}.shipments (
          shipment_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_id INTEGER NOT NULL REFERENCES {schema}.orders(order_id),
          warehouse_id INTEGER NOT NULL REFERENCES {schema}.warehouses(warehouse_id),
          carrier_id INTEGER NOT NULL REFERENCES {schema}.carriers(carrier_id),
          shipment_number TEXT NOT NULL UNIQUE,
          shipment_status TEXT NOT NULL CHECK (shipment_status IN ('label_created', 'in_transit', 'delivered')),
          shipped_at TIMESTAMPTZ NOT NULL,
          delivered_at TIMESTAMPTZ NULL,
          shipping_service TEXT NOT NULL,
          tracking_number TEXT NOT NULL UNIQUE,
          freight_cost NUMERIC(12, 2) NOT NULL CHECK (freight_cost >= 0),
          recipient_country_code TEXT NOT NULL REFERENCES {schema}.countries(country_code)
        );

        CREATE TABLE {schema}.shipment_items (
          shipment_item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          shipment_id INTEGER NOT NULL REFERENCES {schema}.shipments(shipment_id),
          order_item_id INTEGER NOT NULL REFERENCES {schema}.order_items(order_item_id),
          quantity_shipped INTEGER NOT NULL CHECK (quantity_shipped > 0)
        );

        CREATE TABLE {schema}.returns (
          return_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          order_id INTEGER NOT NULL REFERENCES {schema}.orders(order_id),
          return_number TEXT NOT NULL UNIQUE,
          return_status TEXT NOT NULL CHECK (return_status IN ('requested', 'received', 'refunded')),
          requested_at TIMESTAMPTZ NOT NULL,
          received_at TIMESTAMPTZ NULL,
          refund_issued_at TIMESTAMPTZ NULL,
          return_reason TEXT NOT NULL,
          refund_amount NUMERIC(12, 2) NOT NULL CHECK (refund_amount >= 0)
        );

        CREATE TABLE {schema}.return_items (
          return_item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          return_id INTEGER NOT NULL REFERENCES {schema}.returns(return_id),
          order_item_id INTEGER NOT NULL REFERENCES {schema}.order_items(order_item_id),
          quantity_returned INTEGER NOT NULL CHECK (quantity_returned > 0),
          disposition TEXT NOT NULL CHECK (disposition IN ('restock', 'open_box', 'damaged')),
          refund_amount NUMERIC(12, 2) NOT NULL CHECK (refund_amount >= 0)
        );

        CREATE TABLE {schema}.purchase_orders (
          purchase_order_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          po_number TEXT NOT NULL UNIQUE,
          supplier_id INTEGER NOT NULL REFERENCES {schema}.suppliers(supplier_id),
          warehouse_id INTEGER NOT NULL REFERENCES {schema}.warehouses(warehouse_id),
          po_status TEXT NOT NULL CHECK (po_status IN ('approved', 'in_transit', 'partially_received', 'received')),
          ordered_at TIMESTAMPTZ NOT NULL,
          expected_at TIMESTAMPTZ NOT NULL,
          received_at TIMESTAMPTZ NULL,
          currency_code TEXT NOT NULL
        );

        CREATE TABLE {schema}.purchase_order_items (
          po_item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          purchase_order_id INTEGER NOT NULL REFERENCES {schema}.purchase_orders(purchase_order_id),
          sku_id INTEGER NOT NULL REFERENCES {schema}.sku_variants(sku_id),
          quantity_ordered INTEGER NOT NULL CHECK (quantity_ordered > 0),
          quantity_received INTEGER NOT NULL CHECK (quantity_received >= 0),
          unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
          line_cost NUMERIC(12, 2) NOT NULL CHECK (line_cost >= 0)
        );

        CREATE TABLE {schema}.inventory_movements (
          movement_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          sku_id INTEGER NOT NULL REFERENCES {schema}.sku_variants(sku_id),
          warehouse_id INTEGER NOT NULL REFERENCES {schema}.warehouses(warehouse_id),
          reference_type TEXT NOT NULL,
          reference_id TEXT NOT NULL,
          movement_reason TEXT NOT NULL,
          quantity_delta INTEGER NOT NULL,
          moved_at TIMESTAMPTZ NOT NULL,
          unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
          note_text TEXT NOT NULL
        );

        INSERT INTO {schema}.countries (country_code, country_name, region_name, currency_code, vat_rate) VALUES
          ('IT', 'Italy', 'EMEA', 'EUR', 22.00),
          ('DE', 'Germany', 'EMEA', 'EUR', 19.00),
          ('FR', 'France', 'EMEA', 'EUR', 20.00),
          ('ES', 'Spain', 'EMEA', 'EUR', 21.00),
          ('NL', 'Netherlands', 'EMEA', 'EUR', 21.00),
          ('US', 'United States', 'Americas', 'USD', 8.25),
          ('CA', 'Canada', 'Americas', 'CAD', 13.00),
          ('AE', 'United Arab Emirates', 'MEA', 'AED', 5.00),
          ('SG', 'Singapore', 'APAC', 'SGD', 9.00),
          ('AU', 'Australia', 'APAC', 'AUD', 10.00);

        INSERT INTO {schema}.sales_channels (
          channel_code,
          channel_name,
          channel_type,
          default_currency,
          launched_at
        ) VALUES
          ('web_store', 'Direct Web Store', 'direct_to_consumer', 'EUR', DATE '2021-02-01'),
          ('mobile_app', 'Mobile App', 'direct_to_consumer', 'EUR', DATE '2022-05-15'),
          ('marketplace', 'Marketplace Partners', 'third_party_marketplace', 'EUR', DATE '2021-09-01'),
          ('inside_sales', 'Inside Sales', 'b2b_assisted', 'USD', DATE '2020-11-01'),
          ('retail_ops', 'Retail Operations', 'store_replenishment', 'EUR', DATE '2023-01-10');

        INSERT INTO {schema}.warehouses (
          warehouse_code,
          warehouse_name,
          country_code,
          city_name,
          timezone_name,
          is_fulfillment_center,
          opened_at
        ) VALUES
          ('MIL-01', 'Milan Fulfillment Center', 'IT', 'Milan', 'Europe/Rome', TRUE, DATE '2020-01-15'),
          ('RTM-01', 'Rotterdam Distribution Hub', 'NL', 'Rotterdam', 'Europe/Amsterdam', TRUE, DATE '2021-03-10'),
          ('CHI-01', 'Chicago Central Warehouse', 'US', 'Chicago', 'America/Chicago', TRUE, DATE '2019-09-01'),
          ('DXB-01', 'Dubai Regional Hub', 'AE', 'Dubai', 'Asia/Dubai', TRUE, DATE '2022-02-18'),
          ('SIN-01', 'Singapore APAC Hub', 'SG', 'Singapore', 'Asia/Singapore', TRUE, DATE '2021-07-12');

        INSERT INTO {schema}.carriers (
          carrier_code,
          carrier_name,
          service_level,
          supports_express
        ) VALUES
          ('DHL', 'DHL Express', 'air_priority', TRUE),
          ('UPS', 'UPS', 'ground_plus', TRUE),
          ('DPD', 'DPD', 'parcel_standard', FALSE),
          ('FEDEX', 'FedEx', 'economy_express', TRUE);

        INSERT INTO {schema}.suppliers (
          supplier_code,
          supplier_name,
          country_code,
          supplier_tier,
          lead_time_days,
          payment_terms_days,
          status
        ) VALUES
          ('SUP-001', 'Aster Components', 'DE', 'strategic', 18, 45, 'active'),
          ('SUP-002', 'Blue Harbor Goods', 'NL', 'core', 12, 30, 'active'),
          ('SUP-003', 'Keystone Audio Labs', 'US', 'strategic', 21, 45, 'active'),
          ('SUP-004', 'Luma Smart Living', 'IT', 'core', 15, 30, 'active'),
          ('SUP-005', 'North Ridge Sports', 'CA', 'core', 24, 30, 'active'),
          ('SUP-006', 'Meridian Mobility', 'AU', 'core', 28, 45, 'active'),
          ('SUP-007', 'Nimbus Devices', 'SG', 'strategic', 16, 60, 'active'),
          ('SUP-008', 'Orchid Home Tech', 'FR', 'approved', 20, 30, 'active'),
          ('SUP-009', 'Peakline Distribution', 'ES', 'approved', 14, 30, 'active'),
          ('SUP-010', 'Sunset Accessories', 'AE', 'approved', 10, 21, 'active'),
          ('SUP-011', 'Vertex Commerce Supply', 'US', 'strategic', 26, 60, 'active'),
          ('SUP-012', 'Wildflower Lifestyle', 'IT', 'approved', 17, 30, 'active'),
          ('SUP-013', 'Zenith Gadgets', 'SG', 'core', 19, 45, 'active'),
          ('SUP-014', 'Atlas Industrial Trading', 'DE', 'approved', 22, 30, 'active');

        INSERT INTO {schema}.product_categories (
          category_code,
          category_name,
          parent_category_code,
          department_name
        ) VALUES
          ('tech', 'Technology', NULL, 'Technology'),
          ('home', 'Connected Home', NULL, 'Home'),
          ('lifestyle', 'Lifestyle', NULL, 'Lifestyle'),
          ('audio', 'Audio', 'tech', 'Technology'),
          ('computing', 'Computing', 'tech', 'Technology'),
          ('smart_home', 'Smart Home', 'home', 'Home'),
          ('mobility', 'Mobility', 'lifestyle', 'Lifestyle'),
          ('fitness', 'Fitness', 'lifestyle', 'Lifestyle'),
          ('accessories', 'Accessories', 'tech', 'Technology');

        INSERT INTO {schema}.products (
          product_code,
          category_id,
          primary_supplier_id,
          product_name,
          brand_name,
          product_status,
          created_at,
          discontinued_at
        )
        SELECT
          FORMAT('PRD-%04s', seq),
          category.category_id,
          1 + ((seq * 5 - 1) % 14),
          CASE category.category_code
            WHEN 'audio' THEN
              (ARRAY['Wireless Earbuds', 'Studio Headphones', 'Conference Speaker', 'USB Microphone', 'Soundbar'])[1 + ((seq - 1) % 5)]
            WHEN 'computing' THEN
              (ARRAY['Docking Station', 'Portable Monitor', 'Mechanical Keyboard', 'USB-C Hub', 'Ergonomic Mouse'])[1 + ((seq - 1) % 5)]
            WHEN 'smart_home' THEN
              (ARRAY['Smart Sensor', 'Indoor Camera', 'Thermostat', 'Air Quality Monitor', 'Smart Plug'])[1 + ((seq - 1) % 5)]
            WHEN 'mobility' THEN
              (ARRAY['Travel Backpack', 'Carry Case', 'Portable Battery', 'Commuter Light', 'Phone Mount'])[1 + ((seq - 1) % 5)]
            WHEN 'fitness' THEN
              (ARRAY['Recovery Gun', 'Smart Scale', 'Hydration Bottle', 'Yoga Kit', 'Heart Rate Strap'])[1 + ((seq - 1) % 5)]
            ELSE
              (ARRAY['Cable Kit', 'Laptop Sleeve', 'Power Adapter', 'Desk Stand', 'Wireless Charger'])[1 + ((seq - 1) % 5)]
          END
          || ' '
          || (ARRAY['Core', 'Plus', 'Pro', 'Max', 'Edge', 'Lite'])[1 + ((seq * 3 - 1) % 6)],
          (ARRAY['Northstar', 'Helio', 'Nimbus', 'Peakline', 'Altura', 'Keystone', 'Monarch', 'Vertex'])[1 + ((seq * 2 - 1) % 8)],
          CASE
            WHEN seq % 17 = 0 THEN 'discontinued'
            WHEN seq % 9 = 0 THEN 'seasonal'
            ELSE 'active'
          END,
          TIMESTAMPTZ '2022-01-01 09:00:00+00' + ((seq * 11) || ' days')::INTERVAL,
          CASE
            WHEN seq % 17 = 0 THEN TIMESTAMPTZ '2025-06-01 08:00:00+00' + ((seq * 5) || ' days')::INTERVAL
            ELSE NULL
          END
        FROM generate_series(1, 120) AS generated(seq)
        JOIN {schema}.product_categories AS category
          ON category.category_code = (ARRAY['audio', 'computing', 'smart_home', 'mobility', 'fitness', 'accessories'])[1 + ((seq - 1) % 6)];

        INSERT INTO {schema}.sku_variants (
          product_id,
          sku_code,
          variant_name,
          color_name,
          size_label,
          unit_cost,
          list_price,
          weight_grams,
          launch_date,
          is_active
        )
        SELECT
          product.product_id,
          FORMAT('SKU-%04s-%s', product.product_id, CASE variant.variant_idx WHEN 1 THEN 'STD' ELSE 'PLUS' END),
          CASE
            WHEN category.category_code IN ('audio', 'computing') THEN
              (ARRAY['Standard', 'Extended Memory'])[variant.variant_idx]
            WHEN category.category_code = 'smart_home' THEN
              (ARRAY['Starter Kit', 'Automation Bundle'])[variant.variant_idx]
            WHEN category.category_code = 'mobility' THEN
              (ARRAY['City Pack', 'Travel Pack'])[variant.variant_idx]
            WHEN category.category_code = 'fitness' THEN
              (ARRAY['Everyday', 'Performance'])[variant.variant_idx]
            ELSE
              (ARRAY['Single Unit', '2-Pack'])[variant.variant_idx]
          END,
          (ARRAY['graphite', 'white', 'navy', 'olive', 'sand', 'crimson'])[1 + ((product.product_id + variant.variant_idx - 1) % 6)],
          CASE
            WHEN category.category_code IN ('audio', 'computing') THEN (ARRAY['standard', 'premium'])[variant.variant_idx]
            WHEN category.category_code = 'accessories' THEN (ARRAY['single', 'bundle'])[variant.variant_idx]
            ELSE (ARRAY['standard', 'plus'])[variant.variant_idx]
          END,
          ROUND((
            CASE category.category_code
              WHEN 'audio' THEN 28 + (product.product_id % 7) * 5.3
              WHEN 'computing' THEN 42 + (product.product_id % 8) * 7.1
              WHEN 'smart_home' THEN 24 + (product.product_id % 6) * 4.6
              WHEN 'mobility' THEN 18 + (product.product_id % 5) * 3.8
              WHEN 'fitness' THEN 16 + (product.product_id % 6) * 3.2
              ELSE 9 + (product.product_id % 4) * 2.7
            END
            * (CASE variant.variant_idx WHEN 1 THEN 1.00 ELSE 1.22 END)
          )::NUMERIC, 2),
          ROUND((
            CASE category.category_code
              WHEN 'audio' THEN 79 + (product.product_id % 7) * 11.5
              WHEN 'computing' THEN 119 + (product.product_id % 8) * 16.5
              WHEN 'smart_home' THEN 64 + (product.product_id % 6) * 8.2
              WHEN 'mobility' THEN 45 + (product.product_id % 5) * 7.8
              WHEN 'fitness' THEN 39 + (product.product_id % 6) * 6.5
              ELSE 19 + (product.product_id % 4) * 4.5
            END
            * (CASE variant.variant_idx WHEN 1 THEN 1.00 ELSE 1.28 END)
          )::NUMERIC, 2),
          CASE category.category_code
            WHEN 'audio' THEN 220 + (product.product_id % 6) * 35
            WHEN 'computing' THEN 480 + (product.product_id % 8) * 90
            WHEN 'smart_home' THEN 160 + (product.product_id % 5) * 40
            WHEN 'mobility' THEN 300 + (product.product_id % 5) * 55
            WHEN 'fitness' THEN 250 + (product.product_id % 6) * 45
            ELSE 90 + (product.product_id % 4) * 18
          END,
          product.created_at::DATE + ((variant.variant_idx - 1) * 14),
          product.product_status <> 'discontinued' OR variant.variant_idx = 1
        FROM {schema}.products AS product
        JOIN {schema}.product_categories AS category
          ON category.category_id = product.category_id
        CROSS JOIN (VALUES (1), (2)) AS variant(variant_idx);

        INSERT INTO {schema}.supplier_skus (
          supplier_id,
          sku_id,
          supplier_item_code,
          is_primary,
          min_order_qty,
          case_pack_qty,
          latest_unit_cost,
          lead_time_days
        )
        SELECT
          product.primary_supplier_id,
          sku.sku_id,
          FORMAT('PS-%03s-%05s', product.primary_supplier_id, sku.sku_id),
          TRUE,
          10 + ((sku.sku_id - 1) % 4) * 5,
          6 + ((sku.sku_id - 1) % 5) * 2,
          ROUND((sku.unit_cost * (0.94 + ((sku.sku_id % 4) * 0.015)))::NUMERIC, 2),
          supplier.lead_time_days
        FROM {schema}.sku_variants AS sku
        JOIN {schema}.products AS product
          ON product.product_id = sku.product_id
        JOIN {schema}.suppliers AS supplier
          ON supplier.supplier_id = product.primary_supplier_id;

        INSERT INTO {schema}.supplier_skus (
          supplier_id,
          sku_id,
          supplier_item_code,
          is_primary,
          min_order_qty,
          case_pack_qty,
          latest_unit_cost,
          lead_time_days
        )
        SELECT
          alternate_map.alternate_supplier_id,
          sku.sku_id,
          FORMAT('PS-%03s-%05s-ALT', alternate_map.alternate_supplier_id, sku.sku_id),
          FALSE,
          20 + ((sku.sku_id - 1) % 3) * 10,
          8 + ((sku.sku_id - 1) % 4) * 3,
          ROUND((sku.unit_cost * (0.98 + ((sku.sku_id % 3) * 0.02)))::NUMERIC, 2),
          alt_supplier.lead_time_days
        FROM (
          SELECT
            sku.sku_id,
            sku.product_id,
            CASE
              WHEN 1 + ((sku_id + 6) % 14) = product.primary_supplier_id THEN 1 + ((sku_id + 7) % 14)
              ELSE 1 + ((sku_id + 6) % 14)
            END AS alternate_supplier_id
          FROM {schema}.sku_variants AS sku
          JOIN {schema}.products AS product
            ON product.product_id = sku.product_id
          WHERE sku.sku_id % 4 = 0
        ) AS alternate_map
        JOIN {schema}.sku_variants AS sku
          ON sku.sku_id = alternate_map.sku_id
        JOIN {schema}.suppliers AS alt_supplier
          ON alt_supplier.supplier_id = alternate_map.alternate_supplier_id;

        INSERT INTO {schema}.customers (
          customer_code,
          first_name,
          last_name,
          email,
          phone_number,
          country_code,
          acquisition_channel_id,
          loyalty_tier,
          created_at,
          birth_date
        )
        SELECT
          FORMAT('CUS-%05s', seq),
          first_name,
          last_name,
          LOWER(REPLACE(first_name, ' ', '')) || '.' || LOWER(REPLACE(last_name, ' ', '')) || seq || '@' ||
            (ARRAY['acme-mail.com', 'bluebox.io', 'nexa.co', 'brightmail.net'])[1 + ((seq - 1) % 4)],
          FORMAT('+1-555-%04s-%04s', 1000 + (seq % 9000), 2000 + ((seq * 7) % 8000)),
          country_code,
          1 + ((seq * 7 - 1) % 5),
          CASE
            WHEN seq % 19 = 0 THEN 'platinum'
            WHEN seq % 7 = 0 THEN 'gold'
            WHEN seq % 3 = 0 THEN 'silver'
            ELSE 'standard'
          END,
          TIMESTAMPTZ '2021-01-05 10:00:00+00' + ((seq * 19) || ' hours')::INTERVAL,
          CASE
            WHEN seq % 8 = 0 THEN NULL
            ELSE DATE '1972-01-01' + ((seq * 29) % 12000)
          END
        FROM (
          SELECT
            seq,
            (ARRAY['Luca', 'Marta', 'Giulia', 'Elena', 'Marco', 'Priya', 'Jon', 'Nora', 'Amina', 'Sara', 'Davide', 'Chiara'])[1 + ((seq - 1) % 12)] AS first_name,
            (ARRAY['Rossi', 'Bianchi', 'Dubois', 'Garcia', 'Muller', 'Patel', 'Smith', 'Tan', 'Nguyen', 'Marin', 'Conti', 'Khan'])[1 + ((seq * 3 - 1) % 12)] AS last_name,
            (ARRAY['IT', 'DE', 'FR', 'ES', 'NL', 'US', 'US', 'CA', 'AE', 'SG', 'AU', 'IT'])[1 + ((seq * 5 - 1) % 12)] AS country_code
          FROM generate_series(1, 900) AS generated(seq)
        ) AS seeded_customers;

        INSERT INTO {schema}.customer_addresses (
          customer_id,
          address_type,
          recipient_name,
          line1,
          line2,
          postal_code,
          city_name,
          country_code,
          is_default,
          created_at
        )
        SELECT
          customer.customer_id,
          address_variant.address_type,
          customer.first_name || ' ' || customer.last_name,
          FORMAT(
            '%s %s',
            10 + ((customer.customer_id * 7 + address_variant.address_rank * 13) % 180),
            (ARRAY['Market Street', 'Via Centrale', 'Rue des Fleurs', 'Avenida Norte', 'Canal Road', 'Harbor Lane'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 6)]
          ),
          CASE
            WHEN address_variant.address_rank = 3 THEN 'Unit ' || (1 + (customer.customer_id % 20))
            WHEN customer.customer_id % 11 = 0 THEN 'Building ' || (1 + (customer.customer_id % 9))
            ELSE NULL
          END,
          LPAD((10000 + ((customer.customer_id * 37 + address_variant.address_rank * 19) % 89999))::TEXT, 5, '0'),
          CASE customer.country_code
            WHEN 'IT' THEN (ARRAY['Milan', 'Rome', 'Turin', 'Bologna'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'DE' THEN (ARRAY['Berlin', 'Munich', 'Hamburg', 'Cologne'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'FR' THEN (ARRAY['Paris', 'Lyon', 'Lille', 'Bordeaux'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'ES' THEN (ARRAY['Madrid', 'Barcelona', 'Valencia', 'Seville'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'NL' THEN (ARRAY['Amsterdam', 'Rotterdam', 'Utrecht', 'Eindhoven'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'US' THEN (ARRAY['Chicago', 'Austin', 'Seattle', 'Boston'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'CA' THEN (ARRAY['Toronto', 'Montreal', 'Vancouver', 'Calgary'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'AE' THEN (ARRAY['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            WHEN 'SG' THEN (ARRAY['Singapore', 'Singapore', 'Singapore', 'Singapore'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
            ELSE (ARRAY['Sydney', 'Melbourne', 'Brisbane', 'Perth'])[1 + ((customer.customer_id + address_variant.address_rank - 1) % 4)]
          END,
          customer.country_code,
          address_variant.is_default,
          customer.created_at + (address_variant.address_rank || ' days')::INTERVAL
        FROM {schema}.customers AS customer
        JOIN (
          VALUES
            ('billing', 1, TRUE),
            ('shipping', 2, TRUE),
            ('shipping', 3, FALSE)
        ) AS address_variant(address_type, address_rank, is_default)
          ON address_variant.address_rank < 3
          OR customer.customer_id % 3 = 0;

        INSERT INTO {schema}.orders (
          order_number,
          customer_id,
          billing_address_id,
          shipping_address_id,
          sales_channel_id,
          warehouse_id,
          order_status,
          currency_code,
          placed_at,
          paid_at,
          shipped_at,
          promised_ship_by,
          subtotal_amount,
          discount_amount,
          shipping_amount,
          tax_amount,
          total_amount,
          payment_status,
          fulfillment_status
        )
        SELECT
          FORMAT('ORD-%06s', seq),
          customer.customer_id,
          billing_address.address_id,
          shipping_address.address_id,
          1 + ((seq * 5 - 1) % 5),
          CASE country.region_name
            WHEN 'Americas' THEN 3
            WHEN 'MEA' THEN 4
            WHEN 'APAC' THEN 5
            ELSE CASE WHEN seq % 2 = 0 THEN 1 ELSE 2 END
          END,
          status_map.order_status,
          country.currency_code,
          placed_ts.placed_at,
          NULL,
          NULL,
          placed_ts.placed_at + ((2 + (seq % 4)) || ' days')::INTERVAL,
          0,
          0,
          0,
          0,
          0,
          status_map.payment_status,
          status_map.fulfillment_status
        FROM generate_series(1, 4200) AS generated(seq)
        JOIN {schema}.customers AS customer
          ON customer.customer_id = 1 + ((seq * 13 - 1) % 900)
        JOIN {schema}.countries AS country
          ON country.country_code = customer.country_code
        JOIN LATERAL (
          SELECT address_id
          FROM {schema}.customer_addresses
          WHERE customer_id = customer.customer_id
            AND address_type = 'billing'
            AND is_default
          ORDER BY address_id
          LIMIT 1
        ) AS billing_address ON TRUE
        JOIN LATERAL (
          SELECT address_id
          FROM {schema}.customer_addresses
          WHERE customer_id = customer.customer_id
            AND address_type = 'shipping'
            AND is_default
          ORDER BY address_id
          LIMIT 1
        ) AS shipping_address ON TRUE
        JOIN LATERAL (
          SELECT TIMESTAMPTZ '2024-01-01 08:00:00+00'
            + (((seq * 7) % 760) || ' days')::INTERVAL
            + (((seq * 11) % 14) || ' hours')::INTERVAL AS placed_at
        ) AS placed_ts ON TRUE
        JOIN LATERAL (
          SELECT
            CASE
              WHEN placed_ts.placed_at > TIMESTAMPTZ '2026-04-01 00:00:00+00' AND seq % 5 = 0 THEN 'pending_payment'
              WHEN seq % 23 = 0 THEN 'cancelled'
              WHEN seq % 13 = 0 THEN 'processing'
              WHEN seq % 11 = 0 THEN 'packed'
              WHEN seq % 7 = 0 THEN 'shipped'
              WHEN seq % 9 = 0 THEN 'partially_returned'
              ELSE 'delivered'
            END AS order_status,
            CASE
              WHEN placed_ts.placed_at > TIMESTAMPTZ '2026-04-01 00:00:00+00' AND seq % 5 = 0 THEN 'pending'
              WHEN seq % 23 = 0 THEN 'voided'
              WHEN seq % 9 = 0 THEN 'partially_refunded'
              ELSE 'paid'
            END AS payment_status,
            CASE
              WHEN placed_ts.placed_at > TIMESTAMPTZ '2026-04-01 00:00:00+00' AND seq % 5 = 0 THEN 'unallocated'
              WHEN seq % 23 = 0 THEN 'cancelled'
              WHEN seq % 13 = 0 THEN 'allocated'
              WHEN seq % 11 = 0 THEN 'packed'
              WHEN seq % 7 = 0 THEN 'shipped'
              ELSE 'delivered'
            END AS fulfillment_status
        ) AS status_map ON TRUE;

        INSERT INTO {schema}.order_items (
          order_id,
          sku_id,
          quantity,
          unit_price,
          discount_amount,
          tax_amount,
          line_total,
          requested_delivery_date
        )
        SELECT
          orders.order_id,
          sku.sku_id,
          quantity_calc.quantity,
          price_calc.unit_price,
          discount_calc.discount_amount,
          tax_calc.tax_amount,
          ROUND(((quantity_calc.quantity * price_calc.unit_price) - discount_calc.discount_amount + tax_calc.tax_amount)::NUMERIC, 2),
          (orders.placed_at::DATE + (4 + ((orders.order_id + line_idx.line_no) % 6)))
        FROM {schema}.orders AS orders
        JOIN LATERAL generate_series(1, 1 + ((orders.order_id * 7) % 4)) AS line_idx(line_no)
          ON TRUE
        JOIN {schema}.sku_variants AS sku
          ON sku.sku_id = 1 + ((orders.order_id * 19 + line_idx.line_no * 23 - 1) % 240)
        JOIN {schema}.countries AS ship_country
          ON ship_country.country_code = (
            SELECT country_code
            FROM {schema}.customer_addresses
            WHERE address_id = orders.shipping_address_id
          )
        JOIN LATERAL (
          SELECT
            CASE
              WHEN sku.size_label = 'bundle' THEN 1 + ((orders.order_id + line_idx.line_no) % 2)
              WHEN orders.sales_channel_id = 5 THEN 2 + ((orders.order_id + line_idx.line_no) % 3)
              ELSE 1 + ((orders.order_id + line_idx.line_no) % 3)
            END AS quantity
        ) AS quantity_calc ON TRUE
        JOIN LATERAL (
          SELECT ROUND((
            sku.list_price *
            CASE
              WHEN orders.sales_channel_id = 3 THEN 0.94
              WHEN orders.sales_channel_id = 5 THEN 0.90
              ELSE 1.00
            END
          )::NUMERIC, 2) AS unit_price
        ) AS price_calc ON TRUE
        JOIN LATERAL (
          SELECT ROUND((
            CASE
              WHEN quantity_calc.quantity >= 3 THEN quantity_calc.quantity * price_calc.unit_price * 0.08
              WHEN (orders.order_id + line_idx.line_no) % 9 = 0 THEN price_calc.unit_price * 0.05
              ELSE 0
            END
          )::NUMERIC, 2) AS discount_amount
        ) AS discount_calc ON TRUE
        JOIN LATERAL (
          SELECT ROUND((((quantity_calc.quantity * price_calc.unit_price) - discount_calc.discount_amount) * (ship_country.vat_rate / 100.0))::NUMERIC, 2) AS tax_amount
        ) AS tax_calc ON TRUE;

        WITH order_rollup AS (
          SELECT
            order_id,
            ROUND(SUM(quantity * unit_price)::NUMERIC, 2) AS subtotal_amount,
            ROUND(SUM(discount_amount)::NUMERIC, 2) AS discount_amount,
            ROUND(SUM(tax_amount)::NUMERIC, 2) AS tax_amount,
            COUNT(*) AS line_count
          FROM {schema}.order_items
          GROUP BY order_id
        )
        UPDATE {schema}.orders AS orders
        SET
          subtotal_amount = order_rollup.subtotal_amount,
          discount_amount = order_rollup.discount_amount,
          shipping_amount = CASE
            WHEN orders.order_status = 'cancelled' THEN 0
            WHEN orders.sales_channel_id = 3 THEN ROUND((7.90 + order_rollup.line_count * 0.45)::NUMERIC, 2)
            WHEN orders.sales_channel_id = 5 THEN ROUND((12.50 + order_rollup.line_count * 0.60)::NUMERIC, 2)
            ELSE ROUND((4.90 + order_rollup.line_count * 0.35)::NUMERIC, 2)
          END,
          tax_amount = order_rollup.tax_amount,
          total_amount = ROUND((
            order_rollup.subtotal_amount
            - order_rollup.discount_amount
            + order_rollup.tax_amount
            + CASE
                WHEN orders.order_status = 'cancelled' THEN 0
                WHEN orders.sales_channel_id = 3 THEN 7.90 + order_rollup.line_count * 0.45
                WHEN orders.sales_channel_id = 5 THEN 12.50 + order_rollup.line_count * 0.60
                ELSE 4.90 + order_rollup.line_count * 0.35
              END
          )::NUMERIC, 2)
        FROM order_rollup
        WHERE order_rollup.order_id = orders.order_id;

        UPDATE {schema}.orders
        SET paid_at = CASE
          WHEN payment_status = 'pending' THEN NULL
          ELSE placed_at + (((order_id % 6) + 1) || ' hours')::INTERVAL
        END;

        INSERT INTO {schema}.shipments (
          order_id,
          warehouse_id,
          carrier_id,
          shipment_number,
          shipment_status,
          shipped_at,
          delivered_at,
          shipping_service,
          tracking_number,
          freight_cost,
          recipient_country_code
        )
        SELECT
          orders.order_id,
          orders.warehouse_id,
          1 + ((orders.order_id * 5 + shipment_seq.shipment_no - 1) % 4),
          FORMAT('SHP-%06s-%s', orders.order_id, shipment_seq.shipment_no),
          CASE
            WHEN orders.order_status IN ('delivered', 'partially_returned') THEN 'delivered'
            ELSE 'in_transit'
          END,
          orders.paid_at + ((18 + shipment_seq.shipment_no * 10 + (orders.order_id % 30)) || ' hours')::INTERVAL,
          CASE
            WHEN orders.order_status IN ('delivered', 'partially_returned') THEN
              orders.paid_at + ((54 + shipment_seq.shipment_no * 12 + (orders.order_id % 60)) || ' hours')::INTERVAL
            ELSE NULL
          END,
          CASE
            WHEN orders.sales_channel_id IN (2, 3) THEN 'express'
            ELSE 'standard'
          END,
          FORMAT('TRK-%06s-%s-%s', orders.order_id, shipment_seq.shipment_no, orders.warehouse_id),
          ROUND((4.50 + shipment_seq.shipment_no * 1.15 + (orders.order_id % 5) * 0.70)::NUMERIC, 2),
          shipping_country.country_code
        FROM {schema}.orders AS orders
        JOIN {schema}.countries AS shipping_country
          ON shipping_country.country_code = (
            SELECT country_code
            FROM {schema}.customer_addresses
            WHERE address_id = orders.shipping_address_id
          )
        JOIN LATERAL (
          SELECT COUNT(*) AS line_count
          FROM {schema}.order_items
          WHERE order_id = orders.order_id
        ) AS item_stats ON TRUE
        JOIN LATERAL generate_series(
          1,
          CASE
            WHEN item_stats.line_count >= 3 AND orders.order_status IN ('delivered', 'partially_returned') AND orders.order_id % 7 = 0 THEN 2
            ELSE 1
          END
        ) AS shipment_seq(shipment_no) ON TRUE
        WHERE orders.order_status IN ('shipped', 'delivered', 'partially_returned');

        INSERT INTO {schema}.shipment_items (
          shipment_id,
          order_item_id,
          quantity_shipped
        )
        SELECT
          shipments.shipment_id,
          order_items.order_item_id,
          order_items.quantity
        FROM {schema}.order_items AS order_items
        JOIN {schema}.orders AS orders
          ON orders.order_id = order_items.order_id
        JOIN LATERAL (
          SELECT COUNT(*) AS shipment_count
          FROM {schema}.shipments
          WHERE order_id = orders.order_id
        ) AS shipment_stats ON TRUE
        JOIN {schema}.shipments AS shipments
          ON shipments.order_id = orders.order_id
         AND (
           shipment_stats.shipment_count = 1
           OR (
             shipment_stats.shipment_count = 2
             AND ((order_items.order_item_id % 2) + 1) = SPLIT_PART(shipments.shipment_number, '-', 3)::INTEGER
           )
         );

        WITH shipment_rollup AS (
          SELECT
            order_id,
            MIN(shipped_at) AS first_shipped_at
          FROM {schema}.shipments
          GROUP BY order_id
        )
        UPDATE {schema}.orders AS orders
        SET shipped_at = shipment_rollup.first_shipped_at
        FROM shipment_rollup
        WHERE shipment_rollup.order_id = orders.order_id;

        INSERT INTO {schema}.returns (
          order_id,
          return_number,
          return_status,
          requested_at,
          received_at,
          refund_issued_at,
          return_reason,
          refund_amount
        )
        SELECT
          orders.order_id,
          FORMAT('RET-%06s', orders.order_id),
          'refunded',
          delivery_stats.last_delivered_at + ((2 + (orders.order_id % 10)) || ' days')::INTERVAL,
          delivery_stats.last_delivered_at + ((5 + (orders.order_id % 12)) || ' days')::INTERVAL,
          delivery_stats.last_delivered_at + ((7 + (orders.order_id % 14)) || ' days')::INTERVAL,
          (ARRAY['damaged_on_arrival', 'wrong_item', 'buyer_remorse', 'quality_issue', 'late_delivery'])[1 + ((orders.order_id - 1) % 5)],
          0
        FROM {schema}.orders AS orders
        JOIN LATERAL (
          SELECT MAX(delivered_at) AS last_delivered_at
          FROM {schema}.shipments
          WHERE order_id = orders.order_id
            AND delivered_at IS NOT NULL
        ) AS delivery_stats ON TRUE
        WHERE orders.order_status = 'partially_returned';

        WITH candidate_return_items AS (
          SELECT
            returns.return_id,
            order_items.order_item_id,
            order_items.quantity,
            order_items.line_total,
            ROW_NUMBER() OVER (PARTITION BY returns.return_id ORDER BY order_items.order_item_id) AS row_num
          FROM {schema}.returns AS returns
          JOIN {schema}.order_items AS order_items
            ON order_items.order_id = returns.order_id
        )
        INSERT INTO {schema}.return_items (
          return_id,
          order_item_id,
          quantity_returned,
          disposition,
          refund_amount
        )
        SELECT
          candidate_return_items.return_id,
          candidate_return_items.order_item_id,
          LEAST(
            candidate_return_items.quantity,
            CASE
              WHEN candidate_return_items.row_num = 1 THEN 1
              ELSE 1 + (candidate_return_items.order_item_id % 2)
            END
          ),
          CASE
            WHEN candidate_return_items.order_item_id % 5 = 0 THEN 'damaged'
            WHEN candidate_return_items.order_item_id % 3 = 0 THEN 'open_box'
            ELSE 'restock'
          END,
          ROUND((
            (candidate_return_items.line_total / candidate_return_items.quantity)
            * LEAST(
                candidate_return_items.quantity,
                CASE
                  WHEN candidate_return_items.row_num = 1 THEN 1
                  ELSE 1 + (candidate_return_items.order_item_id % 2)
                END
              )
          )::NUMERIC, 2)
        FROM candidate_return_items
        WHERE candidate_return_items.row_num <= 1 + (candidate_return_items.return_id % 2);

        WITH return_rollup AS (
          SELECT
            return_id,
            ROUND(SUM(refund_amount)::NUMERIC, 2) AS refund_amount
          FROM {schema}.return_items
          GROUP BY return_id
        )
        UPDATE {schema}.returns AS returns
        SET refund_amount = return_rollup.refund_amount
        FROM return_rollup
        WHERE return_rollup.return_id = returns.return_id;

        INSERT INTO {schema}.payments (
          order_id,
          payment_reference,
          payment_method,
          processor_name,
          payment_status,
          authorized_at,
          captured_at,
          amount_authorized,
          amount_captured,
          amount_refunded
        )
        SELECT
          orders.order_id,
          FORMAT('PAY-%06s', orders.order_id),
          (ARRAY['card', 'wallet', 'invoice', 'bank_transfer'])[1 + ((orders.order_id - 1) % 4)],
          (ARRAY['stripe', 'adyen', 'braintree'])[1 + ((orders.order_id * 2 - 1) % 3)],
          CASE orders.payment_status
            WHEN 'pending' THEN 'authorized'
            WHEN 'voided' THEN 'voided'
            WHEN 'partially_refunded' THEN 'partially_refunded'
            ELSE 'captured'
          END,
          orders.placed_at + (((orders.order_id % 3) + 1) || ' hours')::INTERVAL,
          CASE
            WHEN orders.payment_status IN ('paid', 'partially_refunded') THEN orders.paid_at
            ELSE NULL
          END,
          orders.total_amount,
          CASE
            WHEN orders.payment_status IN ('paid', 'partially_refunded') THEN orders.total_amount
            ELSE 0
          END,
          COALESCE(return_rollup.refund_amount, 0)
        FROM {schema}.orders AS orders
        LEFT JOIN (
          SELECT order_id, ROUND(SUM(refund_amount)::NUMERIC, 2) AS refund_amount
          FROM {schema}.returns
          GROUP BY order_id
        ) AS return_rollup
          ON return_rollup.order_id = orders.order_id;

        INSERT INTO {schema}.purchase_orders (
          po_number,
          supplier_id,
          warehouse_id,
          po_status,
          ordered_at,
          expected_at,
          received_at,
          currency_code
        )
        SELECT
          FORMAT('PO-%05s', seq),
          supplier.supplier_id,
          1 + ((seq * 5 - 1) % 5),
          CASE
            WHEN seq % 6 = 0 THEN 'approved'
            WHEN seq % 5 = 0 THEN 'in_transit'
            WHEN seq % 4 = 0 THEN 'partially_received'
            ELSE 'received'
          END,
          TIMESTAMPTZ '2024-01-10 08:00:00+00' + ((seq * 3) || ' days')::INTERVAL,
          TIMESTAMPTZ '2024-01-10 08:00:00+00' + (((seq * 3) + supplier.lead_time_days) || ' days')::INTERVAL,
          CASE
            WHEN seq % 6 = 0 OR seq % 5 = 0 THEN NULL
            ELSE TIMESTAMPTZ '2024-01-10 08:00:00+00' + (((seq * 3) + supplier.lead_time_days + (seq % 4)) || ' days')::INTERVAL
          END,
          supplier_country.currency_code
        FROM generate_series(1, 220) AS generated(seq)
        JOIN {schema}.suppliers AS supplier
          ON supplier.supplier_id = 1 + ((seq * 7 - 1) % 14)
        JOIN {schema}.countries AS supplier_country
          ON supplier_country.country_code = supplier.country_code;

        WITH ranked_supplier_skus AS (
          SELECT
            supplier_id,
            sku_id,
            case_pack_qty,
            latest_unit_cost,
            ROW_NUMBER() OVER (PARTITION BY supplier_id ORDER BY sku_id) AS row_num,
            COUNT(*) OVER (PARTITION BY supplier_id) AS sku_count
          FROM {schema}.supplier_skus
        )
        INSERT INTO {schema}.purchase_order_items (
          purchase_order_id,
          sku_id,
          quantity_ordered,
          quantity_received,
          unit_cost,
          line_cost
        )
        SELECT
          purchase_orders.purchase_order_id,
          ranked_supplier_skus.sku_id,
          ordered_qty.quantity_ordered,
          CASE purchase_orders.po_status
            WHEN 'received' THEN ordered_qty.quantity_ordered
            WHEN 'partially_received' THEN GREATEST(1, FLOOR(ordered_qty.quantity_ordered * 0.6)::INTEGER)
            ELSE 0
          END,
          ranked_supplier_skus.latest_unit_cost,
          ROUND((ordered_qty.quantity_ordered * ranked_supplier_skus.latest_unit_cost)::NUMERIC, 2)
        FROM {schema}.purchase_orders AS purchase_orders
        JOIN LATERAL generate_series(1, 3) AS line_idx(line_no)
          ON TRUE
        JOIN ranked_supplier_skus
          ON ranked_supplier_skus.supplier_id = purchase_orders.supplier_id
         AND ranked_supplier_skus.row_num = 1 + ((purchase_orders.purchase_order_id * 3 + line_idx.line_no * 5 - 1) % ranked_supplier_skus.sku_count)
        JOIN LATERAL (
          SELECT ranked_supplier_skus.case_pack_qty * (2 + ((purchase_orders.purchase_order_id + line_idx.line_no) % 6)) AS quantity_ordered
        ) AS ordered_qty ON TRUE;

        INSERT INTO {schema}.inventory_movements (
          sku_id,
          warehouse_id,
          reference_type,
          reference_id,
          movement_reason,
          quantity_delta,
          moved_at,
          unit_cost,
          note_text
        )
        SELECT
          purchase_order_items.sku_id,
          purchase_orders.warehouse_id,
          'purchase_order',
          purchase_orders.po_number,
          'receipt',
          purchase_order_items.quantity_received,
          COALESCE(purchase_orders.received_at, purchase_orders.expected_at),
          purchase_order_items.unit_cost,
          'Inbound receipt from supplier'
        FROM {schema}.purchase_orders AS purchase_orders
        JOIN {schema}.purchase_order_items AS purchase_order_items
          ON purchase_order_items.purchase_order_id = purchase_orders.purchase_order_id
        WHERE purchase_order_items.quantity_received > 0;

        INSERT INTO {schema}.inventory_movements (
          sku_id,
          warehouse_id,
          reference_type,
          reference_id,
          movement_reason,
          quantity_delta,
          moved_at,
          unit_cost,
          note_text
        )
        SELECT
          order_items.sku_id,
          shipments.warehouse_id,
          'shipment',
          shipments.shipment_number,
          'customer_shipment',
          -shipment_items.quantity_shipped,
          shipments.shipped_at,
          sku.unit_cost,
          'Outbound shipment to customer'
        FROM {schema}.shipment_items AS shipment_items
        JOIN {schema}.shipments AS shipments
          ON shipments.shipment_id = shipment_items.shipment_id
        JOIN {schema}.order_items AS order_items
          ON order_items.order_item_id = shipment_items.order_item_id
        JOIN {schema}.sku_variants AS sku
          ON sku.sku_id = order_items.sku_id;

        INSERT INTO {schema}.inventory_movements (
          sku_id,
          warehouse_id,
          reference_type,
          reference_id,
          movement_reason,
          quantity_delta,
          moved_at,
          unit_cost,
          note_text
        )
        SELECT
          order_items.sku_id,
          orders.warehouse_id,
          'return',
          returns.return_number,
          'customer_return',
          return_items.quantity_returned,
          COALESCE(returns.received_at, returns.requested_at),
          sku.unit_cost,
          'Returned item back into warehouse'
        FROM {schema}.return_items AS return_items
        JOIN {schema}.returns AS returns
          ON returns.return_id = return_items.return_id
        JOIN {schema}.order_items AS order_items
          ON order_items.order_item_id = return_items.order_item_id
        JOIN {schema}.orders AS orders
          ON orders.order_id = returns.order_id
        JOIN {schema}.sku_variants AS sku
          ON sku.sku_id = order_items.sku_id
        WHERE return_items.disposition = 'restock';

        INSERT INTO {schema}.inventory_movements (
          sku_id,
          warehouse_id,
          reference_type,
          reference_id,
          movement_reason,
          quantity_delta,
          moved_at,
          unit_cost,
          note_text
        )
        SELECT
          1 + ((seq * 17 - 1) % 240),
          1 + ((seq * 5 - 1) % 5),
          'adjustment',
          FORMAT('ADJ-%05s', seq),
          CASE
            WHEN seq % 5 = 0 THEN 'writeoff'
            WHEN seq % 3 = 0 THEN 'cycle_count_gain'
            ELSE 'cycle_count_loss'
          END,
          CASE
            WHEN seq % 5 = 0 THEN -2
            WHEN seq % 3 = 0 THEN 3
            ELSE -1
          END,
          TIMESTAMPTZ '2025-01-05 07:00:00+00' + ((seq * 2) || ' days')::INTERVAL,
          sku.unit_cost,
          CASE
            WHEN seq % 5 = 0 THEN 'Damaged stock write-off'
            WHEN seq % 3 = 0 THEN 'Cycle count positive adjustment'
            ELSE 'Cycle count negative adjustment'
          END
        FROM generate_series(1, 320) AS generated(seq)
        JOIN {schema}.sku_variants AS sku
          ON sku.sku_id = 1 + ((seq * 17 - 1) % 240);

        CREATE INDEX idx_commerce_ops_orders_customer_placed
          ON {schema}.orders(customer_id, placed_at DESC);
        CREATE INDEX idx_commerce_ops_orders_channel_placed
          ON {schema}.orders(sales_channel_id, placed_at DESC);
        CREATE INDEX idx_commerce_ops_order_items_order
          ON {schema}.order_items(order_id);
        CREATE INDEX idx_commerce_ops_payments_order_captured
          ON {schema}.payments(order_id, captured_at DESC);
        CREATE INDEX idx_commerce_ops_shipments_order_shipped
          ON {schema}.shipments(order_id, shipped_at DESC);
        CREATE INDEX idx_commerce_ops_returns_order_requested
          ON {schema}.returns(order_id, requested_at DESC);
        CREATE INDEX idx_commerce_ops_purchase_orders_supplier_ordered
          ON {schema}.purchase_orders(supplier_id, ordered_at DESC);
        CREATE INDEX idx_commerce_ops_inventory_movements_sku_warehouse_time
          ON {schema}.inventory_movements(sku_id, warehouse_id, moved_at DESC);
        """
    )

CommerceOpsDatasetTemplate=DatasetTemplate(
        id="commerce_ops",
        name="Commerce Operations",
        description="Schema OLTP omnichannel con catalogo, clienti, ordini, pagamenti, spedizioni, resi, procurement e movimenti inventariali.",
        schema_name="commerce_ops",
        estimated_rows=52500,
        table_names=(
            "countries",
            "sales_channels",
            "warehouses",
            "carriers",
            "suppliers",
            "product_categories",
            "products",
            "sku_variants",
            "supplier_skus",
            "customers",
            "customer_addresses",
            "orders",
            "order_items",
            "payments",
            "shipments",
            "shipment_items",
            "returns",
            "return_items",
            "purchase_orders",
            "purchase_order_items",
            "inventory_movements",
        ),
        starter_queries=(
            StarterQuery(
                title="Margine mensile per canale",
                sql=dedent(
                    """
                    WITH order_margin AS (
                      SELECT
                        o.order_id,
                        DATE_TRUNC('month', o.placed_at) AS month,
                        ch.channel_name,
                        o.total_amount,
                        SUM(oi.quantity * sku.unit_cost) AS cogs
                      FROM commerce_ops.orders o
                      JOIN commerce_ops.sales_channels ch ON ch.channel_id = o.sales_channel_id
                      JOIN commerce_ops.order_items oi ON oi.order_id = o.order_id
                      JOIN commerce_ops.sku_variants sku ON sku.sku_id = oi.sku_id
                      WHERE o.order_status <> 'cancelled'
                      GROUP BY o.order_id, month, ch.channel_name, o.total_amount
                    )
                    SELECT
                      month,
                      channel_name,
                      ROUND(SUM(total_amount), 2) AS gmv,
                      ROUND(SUM(total_amount - cogs), 2) AS gross_margin,
                      COUNT(*) AS orders
                    FROM order_margin
                    GROUP BY month, channel_name
                    ORDER BY month, gmv DESC;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="SLA spedizioni per hub e carrier",
                sql=dedent(
                    """
                    SELECT
                      w.warehouse_name,
                      c.carrier_name,
                      s.shipping_service,
                      COUNT(*) AS shipments,
                      ROUND(AVG(EXTRACT(EPOCH FROM (s.delivered_at - s.shipped_at)) / 3600)::NUMERIC, 2) AS avg_delivery_hours,
                      ROUND(AVG(s.freight_cost)::NUMERIC, 2) AS avg_freight_cost
                    FROM commerce_ops.shipments s
                    JOIN commerce_ops.warehouses w ON w.warehouse_id = s.warehouse_id
                    JOIN commerce_ops.carriers c ON c.carrier_id = s.carrier_id
                    WHERE s.delivered_at IS NOT NULL
                    GROUP BY w.warehouse_name, c.carrier_name, s.shipping_service
                    ORDER BY avg_delivery_hours ASC, shipments DESC;
                    """
                ).strip(),
            ),
            StarterQuery(
                title="Stock coverage e inbound aperto",
                sql=dedent(
                    """
                    WITH on_hand AS (
                      SELECT sku_id, warehouse_id, SUM(quantity_delta) AS on_hand_qty
                      FROM commerce_ops.inventory_movements
                      GROUP BY sku_id, warehouse_id
                    ),
                    inbound_open AS (
                      SELECT
                        poi.sku_id,
                        po.warehouse_id,
                        SUM(poi.quantity_ordered - poi.quantity_received) AS inbound_qty
                      FROM commerce_ops.purchase_order_items poi
                      JOIN commerce_ops.purchase_orders po ON po.purchase_order_id = poi.purchase_order_id
                      WHERE po.po_status IN ('approved', 'in_transit', 'partially_received')
                      GROUP BY poi.sku_id, po.warehouse_id
                    )
                    SELECT
                      w.warehouse_name,
                      cat.category_name,
                      sku.sku_code,
                      p.product_name,
                      COALESCE(on_hand.on_hand_qty, 0) AS on_hand_qty,
                      COALESCE(inbound_open.inbound_qty, 0) AS inbound_qty,
                      ROUND(sku.list_price, 2) AS list_price
                    FROM commerce_ops.sku_variants sku
                    JOIN commerce_ops.products p ON p.product_id = sku.product_id
                    JOIN commerce_ops.product_categories cat ON cat.category_id = p.category_id
                    CROSS JOIN commerce_ops.warehouses w
                    LEFT JOIN on_hand ON on_hand.sku_id = sku.sku_id AND on_hand.warehouse_id = w.warehouse_id
                    LEFT JOIN inbound_open ON inbound_open.sku_id = sku.sku_id AND inbound_open.warehouse_id = w.warehouse_id
                    WHERE COALESCE(on_hand.on_hand_qty, 0) < 25
                       OR COALESCE(inbound_open.inbound_qty, 0) > 0
                    ORDER BY on_hand_qty ASC, inbound_qty DESC, sku.sku_code
                    LIMIT 30;
                    """
                ).strip(),
            ),
        ),
        seed_sql=commerce_ops_sql("commerce_ops"),
    )