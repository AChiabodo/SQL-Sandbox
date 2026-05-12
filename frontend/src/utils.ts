import type {
  BuilderState,
  ColumnRef,
  DatasetCatalogItem,
  SchemaInfo,
  TableInfo,
  TableSelectionRef
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const emptySqlMessage = "-- Inizializza una raccolta dati dalla sidebar per iniziare.";

export const emptyBuilder: BuilderState = {
  columns: [],
  filters: [],
  groupBy: [],
  aggregations: [],
  orderBy: [],
  joins: [],
  limit: 100,
  offset: 0
};

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });

  const text = await response.text();
  const body = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : body?.detail?.message ?? response.statusText;
    const error = new Error(message) as Error & { status?: number; detail?: unknown };
    error.status = response.status;
    error.detail = body?.detail;
    throw error;
  }

  return body as T;
}

export function parseValue(value: string): unknown {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (!Number.isNaN(Number(trimmed))) return Number(trimmed);
  if (trimmed.includes(",") && !trimmed.startsWith("{")) {
    return trimmed.split(",").map((part) => parseValue(part));
  }
  return trimmed;
}

export function starterSqlForDataset(dataset: DatasetCatalogItem | null): string {
  return dataset?.starterQueries[0]?.sql ?? emptySqlMessage;
}

export function resolveSelectedTable(
  schemas: SchemaInfo[],
  preferredTable: TableSelectionRef | null
): { schemaName: string; table: TableInfo } | null {
  if (preferredTable) {
    const preferredSchema = schemas.find((schema) => schema.name === preferredTable.schemaName);
    const preferred = preferredSchema?.tables.find((table) => table.name === preferredTable.tableName);
    if (preferredSchema && preferred) {
      return { schemaName: preferredSchema.name, table: preferred };
    }
  }

  const firstSchema = schemas[0];
  const firstTable = firstSchema?.tables[0];
  return firstSchema && firstTable ? { schemaName: firstSchema.name, table: firstTable } : null;
}

export function formatRowEstimate(value: number): string {
  return new Intl.NumberFormat("it-IT").format(value);
}

export function humanizeIdentifier(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatColumnRef(ref: ColumnRef, dataType?: string): { label: string; context: string; technical: string } {
  const technical = `${ref.schemaName}.${ref.tableName}.${ref.columnName}`;
  return {
    label: humanizeIdentifier(ref.columnName),
    context: [ref.tableName, dataType].filter(Boolean).join(" · "),
    technical
  };
}

export function formatResultColumn(column: string): { label: string; technical: string } {
  const parts = column.split(".");
  return {
    label: humanizeIdentifier(parts[parts.length - 1] || column),
    technical: column
  };
}

export function modeLabel(mode: "sql" | "lowcode" | "dashboard" | "tables" | "llm"): string {
  return {
    sql: "SQL diretto",
    lowcode: "Low code",
    dashboard: "Dashboard",
    tables: "Tabelle complete",
    llm: "Chat LLM"
  }[mode];
}

export function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
