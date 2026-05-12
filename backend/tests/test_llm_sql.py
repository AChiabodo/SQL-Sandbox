import asyncio

import pytest
from langgraph.errors import GraphRecursionError

from app.llm_sql.config import (
    AnthropicConfig,
    AzureConfig,
    LMStudioConfig,
    LlmSqlSettings,
    OpenAIConfig,
    OpenRouterConfig,
    ProviderName,
)
from app.llm_sql.model_factory import MissingConfigurationError, ModelProvider, UnsupportedProviderError
from app.llm_sql.schema_context import ColumnContext, RelationshipContext, SchemaContext, TableContext
from app.llm_sql.service import agent_error_message, provider_status, sse_event
from app.llm_sql.tools import validate_sql
from app.models import DashboardWidgetProposal, LlmSqlResponse


def configured_settings() -> LlmSqlSettings:
    return LlmSqlSettings(
        _env_file=None,
        default_provider=ProviderName.OPENAI,
        openai=OpenAIConfig(api_key="test", default_model="gpt-test"),
        azure=AzureConfig(api_key="test", endpoint="https://example.openai.azure.com", default_model="gpt-test"),
        anthropic=AnthropicConfig(api_key="test", default_model="claude-test"),
        openrouter=OpenRouterConfig(api_key="test", default_model="openai/gpt-test"),
        lm_studio=LMStudioConfig(base_url="http://localhost:1234/v1", default_model="local-test"),
    )


def test_model_factory_reports_configured_providers() -> None:
    provider = ModelProvider(settings=configured_settings())

    statuses = {status.name: status for status in provider.list_provider_statuses()}

    assert set(statuses) == {"openai", "azure", "anthropic", "openrouter", "lm_studio"}
    assert all(status.is_configured for status in statuses.values())
    assert statuses["openai"].default_model == "gpt-test"


def test_model_factory_rejects_unsupported_provider() -> None:
    provider = ModelProvider(settings=configured_settings())

    with pytest.raises(UnsupportedProviderError):
        provider.get_model(provider="unknown")


def test_model_factory_rejects_missing_configuration() -> None:
    settings = LlmSqlSettings(_env_file=None, openai=OpenAIConfig(default_model="gpt-test"))
    provider = ModelProvider(settings=settings)

    with pytest.raises(MissingConfigurationError):
        provider.get_model(provider="openai")


def test_provider_status_includes_active_provider_and_missing_fields() -> None:
    settings = configured_settings()
    settings.openai.api_key = None
    status = provider_status(ModelProvider(settings=settings))

    assert status["enabled"] is False
    assert status["provider"] == "openai"
    assert status["providers"][0]["missing"] == ["api_key"]


def test_agent_max_steps_default_is_30() -> None:
    assert LlmSqlSettings.model_fields["agent_max_steps"].default == 30


def test_llm_sql_response_serializes_dashboard_widget() -> None:
    response = LlmSqlResponse(
        enabled=True,
        provider="openai",
        model="gpt-test",
        status="success",
        message="Query pronta.",
        sql="SELECT 1 AS value",
        dashboardWidget=DashboardWidgetProposal(
            title="Valore",
            type="kpi",
            sql="SELECT 1 AS value",
            yField="value",
        ),
    )

    payload = response.model_dump()

    assert payload["dashboardWidget"]["title"] == "Valore"
    assert payload["dashboardWidget"]["type"] == "kpi"
    assert payload["dashboardWidget"]["refreshMs"] == 30000


def test_sse_event_serializes_token_event() -> None:
    event = sse_event("token", {"text": "ciao"})

    assert event.startswith("event: token\n")
    assert 'data: {"text": "ciao"}' in event
    assert event.endswith("\n\n")


def test_recursion_error_message_hides_langgraph_limit_details() -> None:
    message = agent_error_message(GraphRecursionError("Recursion limit of 10 reached without hitting a stop condition."))

    assert "reasoning step limit" in message
    assert "Recursion limit of 10" not in message


def test_schema_context_compact_text_includes_fk() -> None:
    context = SchemaContext(
        name="sales_dw",
        tables=[
            TableContext(
                name="fact_sales",
                columns=[ColumnContext(name="customer_key", dataType="integer", nullable=False)],
            ),
            TableContext(
                name="dim_customer",
                columns=[ColumnContext(name="country_code", dataType="text", nullable=False)],
            ),
        ],
        relationships=[
            RelationshipContext(
                constraintName="sales_customer_fkey",
                fromSchemaName="sales_dw",
                fromTableName="fact_sales",
                fromColumnName="customer_key",
                toSchemaName="sales_dw",
                toTableName="dim_customer",
                toColumnName="customer_key",
            )
        ],
    )

    compact = context.compact_text()

    assert "sales_dw.fact_sales" in compact
    assert "customer_key integer not null" in compact
    assert "sales_dw.fact_sales.customer_key -> sales_dw.dim_customer.customer_key" in compact


def test_validate_sql_accepts_select_and_rejects_delete() -> None:
    select_result = asyncio.run(validate_sql("SELECT * FROM sales_dw.fact_sales LIMIT 10"))
    delete_result = asyncio.run(validate_sql("DELETE FROM sales_dw.fact_sales"))

    assert '"ok": true' in select_result
    assert '"ok": false' in delete_result
    assert "DELETE without WHERE" in delete_result
