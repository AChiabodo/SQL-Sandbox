from typing import Any, Literal

from pydantic import BaseModel, Field


class SqlClassification(BaseModel):
    statementType: str
    isReadOnly: bool
    isDangerous: bool
    reasons: list[str] = Field(default_factory=list)


class SqlRequest(BaseModel):
    sql: str = Field(min_length=1)
    confirmDangerous: bool = False


class DashboardQueryRequest(BaseModel):
    sql: str = Field(min_length=1)


class ExplainRequest(BaseModel):
    sql: str = Field(min_length=1)


class SqlResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    rowCount: int
    affectedRows: int | None = None
    durationMs: float
    commandTag: str | None = None
    classification: SqlClassification


class TableRef(BaseModel):
    schemaName: str = "public"
    tableName: str


class ColumnRef(BaseModel):
    schemaName: str = "public"
    tableName: str
    columnName: str


class RelationshipSpec(BaseModel):
    constraintName: str
    fromSchemaName: str
    fromTableName: str
    fromColumnName: str
    toSchemaName: str
    toTableName: str
    toColumnName: str


class JoinSpec(BaseModel):
    joinType: Literal["inner", "left"] = "inner"
    left: ColumnRef
    right: ColumnRef


class FilterSpec(BaseModel):
    column: ColumnRef | str
    operator: Literal[
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "LIKE",
        "ILIKE",
        "IN",
        "BETWEEN",
        "IS NULL",
        "IS NOT NULL",
    ]
    value: Any | None = None
    valueTo: Any | None = None


class AggregationSpec(BaseModel):
    function: Literal["count", "sum", "avg", "min", "max"]
    column: ColumnRef | str | None = None
    alias: str | None = None


class OrderSpec(BaseModel):
    expression: ColumnRef | str
    direction: Literal["asc", "desc"] = "asc"


class QueryBuilderRequest(BaseModel):
    table: TableRef
    columns: list[ColumnRef | str] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    groupBy: list[ColumnRef | str] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(default_factory=list)
    orderBy: list[OrderSpec] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    relationships: list[RelationshipSpec] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CompiledQuery(BaseModel):
    sql: str
    params: list[Any]


class StarterQuery(BaseModel):
    title: str
    sql: str


class DatasetTemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    schemaName: str
    initialized: bool
    tableCount: int
    estimatedRows: int
    starterQueries: list[StarterQuery]


class DatasetTableStat(BaseModel):
    name: str
    rowCount: int


class DatasetInitializeResponse(BaseModel):
    id: str
    name: str
    schemaName: str
    tableCount: int
    totalRows: int
    tables: list[DatasetTableStat]


class LlmTranslateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    schemaContext: dict[str, Any] | None = None


class LlmChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    sql: str | None = None


class LlmSqlRequest(BaseModel):
    messages: list[LlmChatMessage] = Field(min_length=1)
    schemaName: str
    datasetId: str | None = None


class LlmProgressEvent(BaseModel):
    stage: str
    message: str
    detail: dict[str, Any] | None = None


class DashboardWidgetProposal(BaseModel):
    title: str = Field(min_length=1)
    type: Literal["kpi", "bar", "line", "area", "pie", "table"] = "table"
    sql: str = Field(min_length=1)
    xField: str = ""
    yField: str = ""
    refreshMs: int = Field(default=30000, ge=0, le=300000)


class LlmTranslateResponse(BaseModel):
    enabled: bool
    provider: str | None
    model: str | None
    status: Literal["success", "clarification_needed", "error"] = "error"
    sql: str | None = None
    message: str
    clarifyingQuestions: list[str] = Field(default_factory=list)
    usedTables: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validationSummary: str = ""


class LlmSqlResponse(LlmTranslateResponse):
    dashboardWidget: DashboardWidgetProposal | None = None
