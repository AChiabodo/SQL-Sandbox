from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from app.llm_sql.agent import SqlAgentOutput, build_sql_agent
from app.llm_sql.config import get_llm_sql_settings
from app.llm_sql.model_factory import MissingConfigurationError, ModelProvider, UnsupportedProviderError, model_provider
from app.llm_sql.schema_context import SchemaContext, fetch_schema_context
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


def build_request_messages(
    payload: LlmSqlRequest,
    schema_context: SchemaContext,
) -> list[HumanMessage | AIMessage]:
    return [
        HumanMessage(
            content=(
                "Active schema context:\n"
                f"{schema_context.compact_text()}\n\n"
                "Use tools to validate and preview SQL before final success."
            )
        ),
        *to_langchain_messages(payload.messages),
    ]


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
        dashboardWidget=output.dashboardWidget,
    )


def agent_error_message(exc: Exception) -> str:
    if isinstance(exc, GraphRecursionError):
        return (
            "The SQL agent reached its reasoning step limit before producing a final answer. "
            "Try a more specific request, or increase LLM_AGENT_MAX_STEPS if the task needs more validation."
        )
    return f"SQL agent failed: {exc}"


def error_response(provider: str | None, model: str | None, message: str, enabled: bool = True) -> LlmSqlResponse:
    return LlmSqlResponse(
        enabled=enabled,
        provider=provider,
        model=model,
        status="error",
        message=message,
    )


def extract_structured_response(value: Any) -> SqlAgentOutput | None:
    if isinstance(value, SqlAgentOutput):
        return value
    if isinstance(value, dict):
        structured = value.get("structured_response")
        if isinstance(structured, SqlAgentOutput):
            return structured
        for nested in value.values():
            found = extract_structured_response(nested)
            if found:
                return found
    return None


def token_text(token: Any) -> str:
    content = getattr(token, "content", token)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def parsed_tool_detail(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def progress_events_from_update(update: Any) -> list[LlmProgressEvent]:
    if not isinstance(update, dict):
        return []

    events: list[LlmProgressEvent] = []
    if "model" in update:
        model_update = update.get("model")
        if extract_structured_response(model_update):
            events.append(LlmProgressEvent(stage="finalizing", message="Risposta strutturata pronta"))
        else:
            events.append(LlmProgressEvent(stage="model", message="Il modello sta ragionando sulla richiesta"))

    tools_update = update.get("tools")
    if isinstance(tools_update, dict):
        for message in tools_update.get("messages", []):
            tool_name = getattr(message, "name", None) or "tool"
            detail = parsed_tool_detail(getattr(message, "content", None))
            ok = detail.get("ok") if detail else None
            suffix = "completato" if ok is not False else "ha restituito un errore"
            events.append(
                LlmProgressEvent(
                    stage="tool",
                    message=f"{tool_name}: {suffix}",
                    detail={"tool": tool_name, "result": detail} if detail else {"tool": tool_name},
                )
            )
    return events


async def generate_sql(payload: LlmSqlRequest, provider: ModelProvider | None = None) -> LlmSqlResponse:
    selected_provider = provider or model_provider
    status = provider_status(selected_provider)
    if not status["enabled"]:
        return error_response(
            status["provider"],
            status["model"],
            "LLM provider not configured. Configure a provider in .env to enable SQL generation.",
            enabled=False,
        )

    try:
        schema_context = await fetch_schema_context(payload.schemaName)
        agent = build_sql_agent(
            provider=selected_provider,
            provider_name=status["provider"],
            model=status["model"],
        )
        request_messages = build_request_messages(payload, schema_context)
        result = await agent.ainvoke(
            {"messages": request_messages},
            config={"recursion_limit": get_llm_sql_settings().agent_max_steps},
        )
    except (MissingConfigurationError, UnsupportedProviderError) as exc:
        return error_response(status["provider"], status["model"], str(exc), enabled=False)
    except GraphRecursionError as exc:
        return error_response(status["provider"], status["model"], agent_error_message(exc))
    except Exception as exc:
        return error_response(status["provider"], status["model"], agent_error_message(exc))

    structured = extract_structured_response(result)
    if structured:
        return response_from_output(structured, status["provider"], status["model"])

    return error_response(
        status["provider"],
        status["model"],
        "The SQL agent did not return the expected structured response.",
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

    try:
        yield sse_event(
            "progress",
            LlmProgressEvent(
                stage="provider",
                message=f"Provider attivo: {status['provider']} / {status['model']}",
            ).model_dump(),
        )
        yield sse_event("progress", LlmProgressEvent(stage="schema", message="Carico schema e relazioni").model_dump())
        schema_context = await fetch_schema_context(payload.schemaName)
        agent = build_sql_agent(provider_name=status["provider"], model=status["model"])
        request_messages = build_request_messages(payload, schema_context)
        structured: SqlAgentOutput | None = None

        yield sse_event("progress", LlmProgressEvent(stage="agent", message="Avvio agente SQL").model_dump())
        async for mode, data in agent.astream(
            {"messages": request_messages},
            config={"recursion_limit": get_llm_sql_settings().agent_max_steps},
            stream_mode=["updates", "messages"],
        ):
            if mode == "messages":
                token, _metadata = data
                text = token_text(token)
                if text:
                    yield sse_event("token", {"text": text})
                continue

            if mode == "updates":
                structured = extract_structured_response(data) or structured
                for event in progress_events_from_update(data):
                    yield sse_event("progress", event.model_dump())

        if structured:
            yield sse_event("progress", LlmProgressEvent(stage="done", message="Generazione completata").model_dump())
            yield sse_event("final", response_from_output(structured, status["provider"], status["model"]).model_dump())
            return

        yield sse_event(
            "final",
            error_response(
                status["provider"],
                status["model"],
                "The SQL agent did not return the expected structured response.",
            ).model_dump(),
        )
    except (MissingConfigurationError, UnsupportedProviderError) as exc:
        yield sse_event("final", error_response(status["provider"], status["model"], str(exc), enabled=False).model_dump())
    except GraphRecursionError as exc:
        yield sse_event("final", error_response(status["provider"], status["model"], agent_error_message(exc)).model_dump())
    except Exception as exc:
        yield sse_event("final", error_response(status["provider"], status["model"], agent_error_message(exc)).model_dump())
