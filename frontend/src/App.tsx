import { useEffect, useMemo, useState } from "react";
import { format as formatSqlString } from "sql-formatter";

import { DatasetSidebar } from "./components/DatasetSidebar";
import { AdvancedDashboard } from "./components/AdvancedDashboard";
import { LowCodeWorkbench } from "./components/LowCodeWorkbench";
import { LlmChatPanel } from "./components/LlmChatPanel";
import { SqlWorkbench } from "./components/SqlWorkbench";
import { TableBrowser } from "./components/TableBrowser";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { addDashboardWidget, updateDashboardWidget } from "./dashboardStorage";
import type {
  BuilderState,
  ChatMessage,
  DashboardSqlEditSession,
  DashboardWidget,
  DashboardWidgetProposal,
  DatasetCatalogItem,
  DatasetInitResult,
  LlmStatus,
  LlmProgressEvent,
  LlmSqlResponse,
  SchemaInfo,
  SqlHistoryItem,
  SqlResult,
  TableInfo,
  WorkspaceMode
} from "./types";
import {
  API_BASE,
  emptyBuilder,
  makeId,
  parseValue,
  requestJson,
  resolveSelectedTable,
  starterSqlForDataset,
  formatRowEstimate,
  emptySqlMessage
} from "./utils";

type LlmStreamEvent =
  | { event: "progress"; data: LlmProgressEvent }
  | { event: "token"; data: { text: string } }
  | { event: "final"; data: LlmSqlResponse };

async function readLlmStream(
  response: Response,
  onEvent: (event: LlmStreamEvent) => void
): Promise<LlmSqlResponse> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming non supportato dal browser.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: LlmSqlResponse | null = null;

  const consumeEvent = (rawEvent: string) => {
    const lines = rawEvent.split(/\r?\n/);
    const eventName = lines.find((line) => line.startsWith("event: "))?.slice(7) ?? "message";
    const data = lines
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");

    if (!data) return;

    if (eventName === "progress") {
      onEvent({ event: "progress", data: JSON.parse(data) as LlmProgressEvent });
    }
    if (eventName === "token") {
      onEvent({ event: "token", data: JSON.parse(data) as { text: string } });
    }
    if (eventName === "final") {
      finalResponse = JSON.parse(data) as LlmSqlResponse;
      onEvent({ event: "final", data: finalResponse });
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? "";
    chunks.forEach(consumeEvent);
    if (done) break;
  }

  if (buffer.trim()) {
    consumeEvent(buffer.trim());
  }

  if (!finalResponse) {
    throw new Error("Risposta LLM incompleta.");
  }
  return finalResponse;
}

export default function App() {
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [datasets, setDatasets] = useState<DatasetCatalogItem[]>([]);
  const [activeDatasetId, setActiveDatasetId] = useState<string | null>(null);
  const [activeMode, setActiveMode] = useState<WorkspaceMode>("sql");
  const [dbStatus, setDbStatus] = useState<Record<string, unknown> | null>(null);
  const [selectedTable, setSelectedTable] = useState<{ schemaName: string; table: TableInfo } | null>(null);
  const [result, setResult] = useState<SqlResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializingDatasetId, setInitializingDatasetId] = useState<string | null>(null);
  const [sql, setSql] = useState(emptySqlMessage);
  const [selectedStarterTitle, setSelectedStarterTitle] = useState<string | null>(null);
  const [confirmDangerous, setConfirmDangerous] = useState(false);
  const [dangerWarning, setDangerWarning] = useState<string | null>(null);
  const [builder, setBuilder] = useState<BuilderState>(emptyBuilder);
  const [compiledSql, setCompiledSql] = useState("");
  const [llmStatus, setLlmStatus] = useState<LlmStatus | null>(null);
  const [llmPrompt, setLlmPrompt] = useState("Mostra il fatturato per paese negli ultimi 90 giorni");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [llmProgress, setLlmProgress] = useState<LlmProgressEvent[]>([]);
  const [llmStreamingText, setLlmStreamingText] = useState("");
  const [dashboardSqlEdit, setDashboardSqlEdit] = useState<DashboardSqlEditSession | null>(null);
  const [sqlHistory, setSqlHistory] = useState<SqlHistoryItem[]>([]);
  const [tableLimit, setTableLimit] = useState(100);
  const [tableOffset, setTableOffset] = useState(0);

  const activeDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === activeDatasetId) ?? datasets[0] ?? null,
    [datasets, activeDatasetId]
  );

  const selectedTableLabel = selectedTable
    ? `${selectedTable.schemaName}.${selectedTable.table.name}`
    : activeDataset
      ? `${activeDataset.schemaName} / nessuna tabella`
      : "Nessuna raccolta selezionata";

  const activeRelationships = useMemo(
    () => schemas.flatMap((schema) => schema.relationships ?? []),
    [schemas]
  );

  const builderPayload = useMemo(() => {
    if (!selectedTable) return null;
    return {
      table: { schemaName: selectedTable.schemaName, tableName: selectedTable.table.name },
      columns: builder.columns,
      filters: builder.filters
        .filter((item) => item.column)
        .map((item) => ({
          column: item.column,
          operator: item.operator,
          value: parseValue(item.value),
          valueTo: parseValue(item.valueTo)
        })),
      groupBy: builder.groupBy,
      aggregations: builder.aggregations
        .filter((item) => item.function)
        .map((item) => ({
          function: item.function,
          column: item.column || "*",
          alias: item.alias || null
        })),
      orderBy: builder.orderBy.filter((item) => item.expression),
      joins: builder.joins.filter((join) => join.left && join.right),
      relationships: activeRelationships,
      limit: builder.limit,
      offset: builder.offset
    };
  }, [activeRelationships, builder, selectedTable]);

  const loadSchemaForDataset = async (
    dataset: DatasetCatalogItem | null,
    preferredTable: { schemaName: string; tableName: string } | null,
    preserveSql: boolean
  ) => {
    const nextSchemas = dataset?.initialized
      ? (await requestJson<{ schemas: SchemaInfo[] }>(
          `/db/schema?schema=${encodeURIComponent(dataset.schemaName)}`
        )).schemas
      : [];

    setSchemas(nextSchemas);
    setSelectedTable(resolveSelectedTable(nextSchemas, preferredTable));

    if (!preserveSql) {
      setSql(starterSqlForDataset(dataset));
      setSelectedStarterTitle(dataset?.starterQueries[0]?.title ?? null);
    }
  };

  const hydrateWorkspace = async (preferredDatasetId?: string, preserveSql = false) => {
    setLoading(true);
    setError(null);

    try {
      const [datasetResponse, statusResponse, llmResponse] = await Promise.all([
        requestJson<{ datasets: DatasetCatalogItem[] }>("/datasets"),
        requestJson<Record<string, unknown>>("/db/status"),
        requestJson<LlmStatus>("/llm/status")
      ]);

      const nextDatasets = datasetResponse.datasets;
      const nextActiveDataset =
        nextDatasets.find((dataset) => dataset.id === preferredDatasetId) ??
        nextDatasets.find((dataset) => dataset.id === activeDatasetId) ??
        nextDatasets[0] ??
        null;

      const preferredTable =
        selectedTable && nextActiveDataset?.schemaName === selectedTable.schemaName
          ? { schemaName: selectedTable.schemaName, tableName: selectedTable.table.name }
          : null;

      setDatasets(nextDatasets);
      setDbStatus(statusResponse);
      setLlmStatus(llmResponse);
      setActiveDatasetId(nextActiveDataset?.id ?? null);
      await loadSchemaForDataset(nextActiveDataset, preferredTable, preserveSql);

      if (!nextActiveDataset) {
        setNotice("Nessuna raccolta dati disponibile.");
      } else if (!nextActiveDataset.initialized) {
        setNotice(`Inizializza ${nextActiveDataset.name} per caricare tabelle e dati di esempio.`);
      } else if (!preserveSql) {
        setNotice(`Schema ${nextActiveDataset.schemaName} pronto con una workspace UI a modalita.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void hydrateWorkspace();
  }, []);

  useEffect(() => {
    setBuilder(emptyBuilder);
    setCompiledSql("");
    setTableOffset(0);
  }, [selectedTable?.schemaName, selectedTable?.table.name]);

  useEffect(() => {
    if (!builderPayload || activeMode !== "lowcode") {
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const compiled = await requestJson<{ sql: string; params: unknown[] }>("/query-builder/compile", {
          method: "POST",
          body: JSON.stringify(builderPayload)
        });
        setCompiledSql(`${compiled.sql}\n-- params: ${JSON.stringify(compiled.params)}`);
      } catch (err) {
        setCompiledSql("");
        setError(err instanceof Error ? err.message : "Errore sconosciuto");
      }
    }, 180);

    return () => window.clearTimeout(timeoutId);
  }, [builderPayload, activeMode]);

  useEffect(() => {
    if (activeMode !== "tables" || !selectedTable) {
      return;
    }

    void (async () => {
      try {
        const rows = await requestJson<SqlResult>(
          `/db/tables/${selectedTable.schemaName}/${selectedTable.table.name}/rows?limit=${tableLimit}&offset=${tableOffset}`
        );
        setResult(rows);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Errore sconosciuto");
      }
    })();
  }, [activeMode, selectedTable?.schemaName, selectedTable?.table.name, tableLimit, tableOffset]);

  const recordSqlHistory = (statement: string) => {
    const firstLine = statement.trim().split("\n")[0] ?? "Query SQL";
    const label = firstLine.length > 44 ? `${firstLine.slice(0, 44)}...` : firstLine;
    const nextItem: SqlHistoryItem = {
      id: makeId("sql"),
      label,
      sql: statement,
      createdAt: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    };

    setSqlHistory((current) => [nextItem, ...current.filter((item) => item.sql !== statement)].slice(0, 8));
  };

  const dashboardTitleFromSql = (statement: string): string => {
    const candidate = statement
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line && !line.startsWith("--"));
    if (!candidate) return "Query SQL";
    return candidate.length > 48 ? `${candidate.slice(0, 48)}...` : candidate;
  };

  const switchDataset = async (datasetId: string) => {
    const nextDataset = datasets.find((dataset) => dataset.id === datasetId);
    if (!nextDataset) return;

    setLoading(true);
    setError(null);
    setNotice(null);
    setResult(null);
    setDashboardSqlEdit(null);
    setActiveDatasetId(datasetId);

    try {
      await loadSchemaForDataset(nextDataset, null, false);
      if (!nextDataset.initialized) {
        setNotice(`Lo schema ${nextDataset.schemaName} non esiste ancora. Usa Inizializza per popolarlo.`);
      } else {
        setNotice(`Dataset attivo: ${nextDataset.name}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  };

  const initializeDataset = async (datasetId: string) => {
    setInitializingDatasetId(datasetId);
    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const initialized = await requestJson<DatasetInitResult>(`/datasets/${datasetId}/initialize`, {
        method: "POST"
      });

      const summary = initialized.tables
        .map((table) => `${table.name}: ${formatRowEstimate(table.rowCount)}`)
        .join(" | ");

      setResult(null);
      setNotice(
        `${initialized.name} rigenerato in ${initialized.schemaName}: ${formatRowEstimate(
          initialized.totalRows
        )} righe complessive. ${summary}`
      );
      await hydrateWorkspace(datasetId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    } finally {
      setInitializingDatasetId(null);
      setLoading(false);
    }
  };

  const loadRows = async (limit = tableLimit, offset = tableOffset) => {
    if (!selectedTable) return;
    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const rows = await requestJson<SqlResult>(
        `/db/tables/${selectedTable.schemaName}/${selectedTable.table.name}/rows?limit=${limit}&offset=${offset}`
      );
      setResult(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  };

  const compileBuilder = async () => {
    if (!builderPayload) return;
    setError(null);

    try {
      const compiled = await requestJson<{ sql: string; params: unknown[] }>("/query-builder/compile", {
        method: "POST",
        body: JSON.stringify(builderPayload)
      });
      setCompiledSql(`${compiled.sql}\n-- params: ${JSON.stringify(compiled.params)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    }
  };

  const executeBuilder = async () => {
    if (!builderPayload) return;
    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const executed = await requestJson<SqlResult>("/query-builder/execute", {
        method: "POST",
        body: JSON.stringify(builderPayload)
      });
      setResult(executed);
      await compileBuilder();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  };

  const executeSql = async (explain = false) => {
    setLoading(true);
    setError(null);
    setNotice(null);
    setDangerWarning(null);

    try {
      const executed = await requestJson<SqlResult>(explain ? "/sql/explain" : "/sql/execute", {
        method: "POST",
        body: JSON.stringify(explain ? { sql } : { sql, confirmDangerous })
      });
      setResult(executed);
      recordSqlHistory(sql);
    } catch (err) {
      const detailed = err as Error & { status?: number; detail?: { classification?: { reasons?: string[] } } };
      if (detailed.status === 409) {
        const reasons = detailed.detail?.classification?.reasons?.join(", ") ?? "query pericolosa";
        setDangerWarning(`Conferma richiesta: ${reasons}`);
      } else {
        setError(detailed.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const formatSql = () => {
    try {
      setSql(formatSqlString(sql, { language: "postgresql" }));
    } catch {
      setNotice("Impossibile formattare l'SQL corrente. Controlla la sintassi.");
    }
  };

  const askLlm = async () => {
    const trimmed = llmPrompt.trim();
    if (!trimmed) return;

    const userMessage: ChatMessage = {
      id: makeId("chat"),
      role: "user",
      content: trimmed
    };

    setChatMessages((current) => [...current, userMessage]);
    setLlmProgress([{ stage: "request", message: "Invio richiesta all'agente SQL" }]);
    setLlmStreamingText("");
    setLoading(true);

    try {
      if (!activeDataset?.schemaName) {
        throw new Error("Seleziona un dataset prima di usare la chat LLM.");
      }

      const streamResponse = await fetch(`${API_BASE}/llm/generate-sql/stream`, {
        headers: { "Content-Type": "application/json" },
        method: "POST",
        body: JSON.stringify({
          schemaName: activeDataset.schemaName,
          datasetId: activeDataset.id,
          messages: [...chatMessages, userMessage]
            .filter((message) => message.content.trim())
            .map((message) => ({
              role: message.role,
              content: message.content,
              sql: message.sql ?? null
            }))
        })
      });
      const response = await readLlmStream(streamResponse, (event) => {
        if (event.event === "progress") {
          setLlmProgress((current) => [...current, event.data]);
        }
        if (event.event === "token") {
          setLlmStreamingText((current) => `${current}${event.data.text}`);
        }
      });

      setLlmProgress((current) => [
        ...current,
        { stage: response.status, message: response.validationSummary || response.message }
      ]);
      setChatMessages((current) => [
        ...current,
        {
          id: makeId("chat"),
          role: "assistant",
          content: response.message,
          sql: response.sql,
          status: response.status,
          clarifyingQuestions: response.clarifyingQuestions,
          usedTables: response.usedTables,
          assumptions: response.assumptions,
          validationSummary: response.validationSummary,
          dashboardWidget: response.dashboardWidget
        }
      ]);
    } catch (err) {
      setLlmProgress([{ stage: "error", message: err instanceof Error ? err.message : "Errore sconosciuto" }]);
      setChatMessages((current) => [
        ...current,
        {
          id: makeId("chat"),
          role: "assistant",
          content: err instanceof Error ? err.message : "Errore sconosciuto"
        }
      ]);
    } finally {
      setLlmStreamingText("");
      setLoading(false);
    }
  };

  const useSqlFromChat = (nextSql: string) => {
    setDashboardSqlEdit(null);
    setActiveMode("sql");
    setSql(nextSql);
    setSelectedStarterTitle(null);
    setNotice("SQL importato dalla chat LLM nell'editor diretto.");
  };

  const sendWidgetToSqlEditor = (widget: DashboardWidget) => {
    if (!activeDataset?.schemaName) return;
    setDashboardSqlEdit({ schemaName: activeDataset.schemaName, widget });
    setActiveMode("sql");
    setSql(widget.sql);
    setSelectedStarterTitle(null);
    setNotice(`Modifica "${widget.title}" nell'editor SQL e salva per aggiornare la dashboard.`);
  };

  const saveDashboardSqlEdit = () => {
    if (!activeDataset?.initialized || !dashboardSqlEdit) return;
    if (activeDataset.schemaName !== dashboardSqlEdit.schemaName) {
      setError("Il dataset attivo non corrisponde al widget dashboard in modifica.");
      return;
    }

    const updated = updateDashboardWidget(activeDataset, {
      ...dashboardSqlEdit.widget,
      sql
    });
    setDashboardSqlEdit(null);
    setActiveMode("dashboard");
    setNotice(`Modifiche salvate per "${updated.title}".`);
  };

  const cancelDashboardSqlEdit = () => {
    setDashboardSqlEdit(null);
    setNotice("Modifica dashboard annullata. L'editor SQL resta disponibile.");
  };

  const addSqlEditorToDashboard = () => {
    if (!activeDataset?.initialized) {
      setError("Seleziona e inizializza un dataset prima di aggiungere widget alla dashboard.");
      return;
    }
    const trimmedSql = sql.trim();
    if (!trimmedSql) {
      setError("Scrivi una query SQL prima di aggiungerla alla dashboard.");
      return;
    }

    const added = addDashboardWidget(activeDataset, {
      title: selectedStarterTitle ?? dashboardTitleFromSql(trimmedSql),
      type: "table",
      sql: trimmedSql,
      xField: "",
      yField: "",
      refreshMs: 30000
    });
    setActiveMode("dashboard");
    setNotice(`Widget "${added.title}" aggiunto alla dashboard.`);
  };

  const addWidgetFromChat = (widget: DashboardWidgetProposal) => {
    if (!activeDataset?.initialized) {
      setError("Seleziona e inizializza un dataset prima di aggiungere widget alla dashboard.");
      return;
    }

    const added = addDashboardWidget(activeDataset, widget);
    setActiveMode("dashboard");
    setNotice(`Widget "${added.title}" aggiunto alla dashboard.`);
  };

  return (
    <main className="app-shell">
      <DatasetSidebar
        dbName={dbStatus ? String(dbStatus.database) : "connessione..."}
        loading={loading}
        datasets={datasets}
        activeDatasetId={activeDatasetId}
        activeDatasetSchema={activeDataset?.schemaName ?? null}
        initializingDatasetId={initializingDatasetId}
        onRefresh={() => void hydrateWorkspace(activeDatasetId ?? undefined, true)}
        onSelectDataset={(datasetId) => void switchDataset(datasetId)}
        onInitializeDataset={(datasetId) => void initializeDataset(datasetId)}
      />

      <section className="workspace">
        <WorkspaceHeader
          activeMode={activeMode}
          onModeChange={setActiveMode}
          activeDataset={activeDataset}
          selectedTableLabel={selectedTableLabel}
        />

        {activeMode === "sql" && (
          <SqlWorkbench
            activeDataset={activeDataset}
            schemas={schemas}
            selectedTable={selectedTable}
            sql={sql}
            selectedStarterTitle={selectedStarterTitle}
            confirmDangerous={confirmDangerous}
            dangerWarning={dangerWarning}
            loading={loading}
            error={error}
            notice={notice}
            result={result}
            sqlHistory={sqlHistory}
            onSelectTable={(schemaName, table) => setSelectedTable({ schemaName, table })}
            onSqlChange={setSql}
            onSelectStarter={(title, nextSql) => {
              setDashboardSqlEdit(null);
              setSelectedStarterTitle(title);
              setSql(nextSql);
            }}
            onSetConfirmDangerous={setConfirmDangerous}
            onExecuteSql={executeSql}
            onFormatSql={formatSql}
            dashboardEditSession={dashboardSqlEdit}
            onAddSqlToDashboard={addSqlEditorToDashboard}
            onSaveDashboardSqlEdit={saveDashboardSqlEdit}
            onCancelDashboardSqlEdit={cancelDashboardSqlEdit}
            onResetStarter={() => {
              setDashboardSqlEdit(null);
              setSql(starterSqlForDataset(activeDataset));
              setSelectedStarterTitle(activeDataset?.starterQueries[0]?.title ?? null);
            }}
            onRestoreHistory={(item) => {
              setDashboardSqlEdit(null);
              setSql(item.sql);
              setSelectedStarterTitle(null);
            }}
          />
        )}

        {activeMode === "lowcode" && (
          <LowCodeWorkbench
            schemas={schemas}
            relationships={activeRelationships}
            selectedTable={selectedTable}
            builder={builder}
            compiledSql={compiledSql}
            loading={loading}
            result={result}
            error={error}
            notice={notice}
            onSelectTable={(schemaName, table) => setSelectedTable({ schemaName, table })}
            onBuilderChange={setBuilder}
            onCompile={compileBuilder}
            onExecute={executeBuilder}
          />
        )}

        {activeMode === "dashboard" && (
          <AdvancedDashboard
            activeDataset={activeDataset}
            schemas={schemas}
            onSendWidgetToSqlEditor={sendWidgetToSqlEditor}
          />
        )}

        {activeMode === "tables" && (
          <TableBrowser
            schemas={schemas}
            selectedTable={selectedTable}
            loading={loading}
            result={result}
            error={error}
            notice={notice}
            limit={tableLimit}
            offset={tableOffset}
            onLimitChange={(value) => {
              setTableLimit(value);
              setTableOffset(0);
            }}
            onOffsetChange={setTableOffset}
            onSelectTable={(schemaName, table) => setSelectedTable({ schemaName, table })}
            onRefresh={() => loadRows()}
          />
        )}

        {activeMode === "llm" && (
          <LlmChatPanel
            llmStatus={llmStatus}
            activeDataset={activeDataset}
            prompt={llmPrompt}
            loading={loading}
            messages={chatMessages}
            progressEvents={llmProgress}
            streamingText={llmStreamingText}
            onPromptChange={setLlmPrompt}
            onSubmit={askLlm}
            onUseSql={useSqlFromChat}
            onAddDashboardWidget={addWidgetFromChat}
          />
        )}
      </section>
    </main>
  );
}
