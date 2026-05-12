from app.config import Settings
from app.llm_sql.service import generate_sql, provider_status
from app.models import LlmChatMessage, LlmSqlRequest, LlmTranslateRequest, LlmTranslateResponse


def llm_status(settings: Settings) -> dict[str, object]:
    return provider_status()


def schema_name_from_legacy_payload(payload: LlmTranslateRequest) -> str | None:
    schemas = payload.schemaContext.get("schemas") if payload.schemaContext else None
    if isinstance(schemas, list) and schemas:
        first = schemas[0]
        if isinstance(first, dict) and isinstance(first.get("name"), str):
            return first["name"]
    return None


async def translate_query(
    payload: LlmTranslateRequest,
    settings: Settings,
) -> LlmTranslateResponse:
    schema_name = schema_name_from_legacy_payload(payload)
    if not schema_name:
        status = provider_status()
        return LlmTranslateResponse(
            enabled=bool(status["enabled"]),
            provider=str(status["provider"]) if status["provider"] else None,
            model=str(status["model"]) if status["model"] else None,
            status="clarification_needed",
            sql=None,
            message="Seleziona o inizializza un dataset prima di generare SQL.",
            clarifyingQuestions=["Su quale schema o dataset devo costruire la query?"],
        )

    return await generate_sql(
        LlmSqlRequest(
            schemaName=schema_name,
            messages=[LlmChatMessage(role="user", content=payload.prompt)],
        )
    )
