import type { ResponsiveLayouts } from "react-grid-layout";

export type ColumnInfo = {
  name: string;
  dataType: string;
  nullable: boolean;
  default: string | null;
};

export type ColumnRef = {
  schemaName: string;
  tableName: string;
  columnName: string;
};

export type RelationshipInfo = {
  constraintName: string;
  fromSchemaName: string;
  fromTableName: string;
  fromColumnName: string;
  toSchemaName: string;
  toTableName: string;
  toColumnName: string;
};

export type BuilderJoinSpec = {
  joinType: "inner" | "left";
  left: ColumnRef | null;
  right: ColumnRef | null;
};

export type TableInfo = {
  name: string;
  columns: ColumnInfo[];
};

export type SchemaInfo = {
  name: string;
  tables: TableInfo[];
  relationships: RelationshipInfo[];
};

export type SqlClassification = {
  statementType: string;
  isReadOnly: boolean;
  isDangerous: boolean;
  reasons: string[];
};

export type SqlResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  affectedRows: number | null;
  durationMs: number;
  commandTag: string | null;
  classification: SqlClassification;
};

export type FilterSpec = {
  column: ColumnRef | null;
  operator: string;
  value: string;
  valueTo: string;
};

export type AggregationSpec = {
  function: string;
  column: ColumnRef | "*";
  alias: string;
};

export type OrderSpec = {
  expression: string;
  direction: "asc" | "desc";
};

export type BuilderState = {
  columns: ColumnRef[];
  filters: FilterSpec[];
  groupBy: ColumnRef[];
  aggregations: AggregationSpec[];
  orderBy: OrderSpec[];
  joins: BuilderJoinSpec[];
  limit: number;
  offset: number;
};

export type LlmStatus = {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  providers?: {
    name: string;
    configured: boolean;
    model: string | null;
    missing: string[];
  }[];
  previewLimit?: number;
};

export type StarterQuery = {
  title: string;
  sql: string;
};

export type DatasetCatalogItem = {
  id: string;
  name: string;
  description: string;
  schemaName: string;
  initialized: boolean;
  tableCount: number;
  estimatedRows: number;
  starterQueries: StarterQuery[];
};

export type DatasetInitResult = {
  id: string;
  name: string;
  schemaName: string;
  tableCount: number;
  totalRows: number;
  tables: { name: string; rowCount: number }[];
};

export type TableSelectionRef = {
  schemaName: string;
  tableName: string;
};

export type WorkspaceMode = "sql" | "lowcode" | "dashboard" | "tables" | "llm";

export type WidgetType = "kpi" | "bar" | "line" | "area" | "pie" | "table";

export type DashboardWidgetProposal = {
  title: string;
  type: WidgetType;
  sql: string;
  xField: string;
  yField: string;
  refreshMs: number;
};

export type DashboardWidget = DashboardWidgetProposal & {
  id: string;
};

export type DashboardSqlEditSession = {
  schemaName: string;
  widget: DashboardWidget;
};

export type DashboardStorage = {
  widgets: DashboardWidget[];
  layouts: ResponsiveLayouts;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql?: string | null;
  status?: "success" | "clarification_needed" | "error";
  clarifyingQuestions?: string[];
  usedTables?: string[];
  assumptions?: string[];
  validationSummary?: string;
  dashboardWidget?: DashboardWidgetProposal | null;
};

export type LlmSqlResponse = {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  status: "success" | "clarification_needed" | "error";
  message: string;
  sql: string | null;
  clarifyingQuestions: string[];
  usedTables: string[];
  assumptions: string[];
  validationSummary: string;
  dashboardWidget: DashboardWidgetProposal | null;
};

export type LlmProgressEvent = {
  stage: string;
  message: string;
  detail?: Record<string, unknown> | null;
};

export type SqlHistoryItem = {
  id: string;
  label: string;
  sql: string;
  createdAt: string;
};
