from textwrap import dedent
from app.models import (
    StarterQuery,
)
from app.sql_seeds.models import DatasetTemplate, quote_name

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

SupportOpsDatasetTemplate = DatasetTemplate(
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
    )