from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.llm_sql.agent import SqlAgentOutput, build_sql_agent
from app.llm_sql.config import get_llm_sql_settings
from app.llm_sql.model_factory import MissingConfigurationError, ModelProvider, UnsupportedProviderError, model_provider
from app.llm_sql.schema_context import fetch_schema_context
from app.models import LlmChatMessage, LlmProgressEvent, LlmSqlRequest, LlmSqlResponse


def provider_status(provider: ModelProvider | None = None) -> dict[str, Any]:
    selected_provider = provider or model_provider
    settings = get_llm_sql_settings()
    statuses = selected_provider.list_provider_statuses()
    active_provider = selected_provider.get_default_provider()
    active = next((status for status in statuses if status.name == active_provider), None)
    return {
        "enabled": bool(active and active.is_configured),
        "provider": active_provider,
        "model": active.default_model if active else None,
        "providers": [
            {
                "name": status.name,
                "configured": status.is_configured,
                "model": status.default_model,
                "missing": status.missing,
            }
            for status in statuses
        ],
        "previewLimit": settings.preview_limit,
    }


def to_langchain_messages(messages: list[LlmChatMessage]) -> list[HumanMessage | AIMessage]:
    converted: list[HumanMessage | AIMessage] = []
    for message in messages:
        if message.role == "assistant":
            converted.append(AIMessage(content=message.content))
        else:
            converted.append(HumanMessage(content=message.content))
    return converted


def response_from_output(output: SqlAgentOutput, provider: str | None, model: str | None) -> LlmSqlResponse:
    return LlmSqlResponse(
        enabled=True,
        provider=provider,
        model=model,
        status=output.status,
        message=output.message,
        sql=output.sql,
        clarifyingQuestions=output.clarifyingQuestions,
        usedTables=output.usedTables,
        assumptions=output.assumptions,
        validationSummary=output.validationSummary,
    )


async def generate_sql(payload: LlmSqlRequest, provider: ModelProvider | None = None) -> LlmSqlResponse:
    selected_provider = provider or model_provider
    status = provider_status(selected_provider)
    if not status["enabled"]:
        return LlmSqlResponse(
            enabled=False,
            provider=status["provider"],
            model=status["model"],
            status="error",
            message="LLM provider not configured. Configure a provider in .env to enable SQL generation.",
        )

    try:
        schema_context = await fetch_schema_context(payload.schemaName)
        agent = build_sql_agent(
            provider=selected_provider,
            provider_name=status["provider"],
            model=status["model"],
        )
        request_messages = [
            HumanMessage(
                content=(
                    "Active schema context:\n"
                    f"{schema_context.compact_text()}\n\n"
                    "Use tools to validate and preview SQL before final success."
                )
            ),
            *to_langchain_messages(payload.messages),
        ]
        result = await agent.ainvoke(
            {"messages": request_messages},
            config={"recursion_limit": get_llm_sql_settings().agent_max_steps},
        )
    except (MissingConfigurationError, UnsupportedProviderError) as exc:
        return LlmSqlResponse(
            enabled=False,
            provider=status["provider"],
            model=status["model"],
            status="error",
            message=str(exc),
        )
    except Exception as exc:
        return LlmSqlResponse(
            enabled=True,
            provider=status["provider"],
            model=status["model"],
            status="error",
            message=f"SQL agent failed: {exc}",
        )

    structured = result.get("structured_response")
    if isinstance(structured, SqlAgentOutput):
        return response_from_output(structured, status["provider"], status["model"])

    return LlmSqlResponse(
        enabled=True,
        provider=status["provider"],
        model=status["model"],
        status="error",
        message="The SQL agent did not return the expected structured response.",
    )


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


async def stream_generate_sql(payload: LlmSqlRequest) -> AsyncIterator[str]:
    status = provider_status()
    yield sse_event("progress", LlmProgressEvent(stage="status", message="Verifica provider LLM").model_dump())
    if not status["enabled"]:
        response = await generate_sql(payload)
        yield sse_event("final", response.model_dump())
        return

    yield sse_event("progress", LlmProgressEvent(stage="schema", message="Carico schema e relazioni").model_dump())
    yield sse_event("progress", LlmProgressEvent(stage="agent", message="Genero e valido SQL").model_dump())
    response = await generate_sql(payload)
    yield sse_event("final", response.model_dump())
