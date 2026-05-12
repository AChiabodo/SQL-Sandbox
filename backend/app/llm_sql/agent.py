from __future__ import annotations

from typing import Literal

from langchain.agents import create_agent
from pydantic import BaseModel, Field

from app.llm_sql.model_factory import ModelProvider, model_provider
from app.llm_sql.tools import build_sql_tools


class SqlAgentOutput(BaseModel):
    status: Literal["success", "clarification_needed", "error"]
    message: str
    sql: str | None = None
    clarifyingQuestions: list[str] = Field(default_factory=list)
    usedTables: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validationSummary: str = ""


SYSTEM_PROMPT = """
You are a senior PostgreSQL data analyst embedded in a local SQL sandbox.

Goal:
- Translate the user's natural-language analytics request into one valid PostgreSQL query.
- Return structured output only.

Hard constraints:
- Use only tables, columns, data types, and foreign keys present in the schema context.
- Never invent tables, columns, metrics, or relationships.
- Generate read-only SQL only. Prefer SELECT/WITH. Never generate INSERT, UPDATE, DELETE, DDL, grants, or destructive SQL.
- Fully qualify table names with the schema, for example sales_dw.fact_sales.
- Use real foreign keys from schema context for joins.
- If a query can return many rows and the user did not request all rows, include a reasonable LIMIT.
- If a request is ambiguous and materially changes the SQL, ask clarifying questions instead of guessing.
- If a column name appears in multiple tables and the user does not make the intended table clear, ask a clarification.
- Validate SQL with validate_sql before final success.
- Use preview_sql or explain_sql when useful to catch syntax/table/column errors before final success.
- If preview_sql reports an error, revise the SQL and try again. Do not retry indefinitely.

Response policy:
- status=success only when sql is syntactically plausible, read-only, and validated.
- status=clarification_needed when the user must choose tables, columns, filters, date ranges, or metric definitions.
- status=error when the request cannot be satisfied with the configured schema or tools.
- Keep message concise and useful for the UI.
"""


def build_sql_agent(provider: ModelProvider | None = None, provider_name: str | None = None, model: str | None = None):
    selected_provider = provider or model_provider
    chat_model = selected_provider.get_model(provider=provider_name, model=model)
    return create_agent(
        model=chat_model,
        tools=build_sql_tools(),
        system_prompt=SYSTEM_PROMPT,
        response_format=SqlAgentOutput,
    )
