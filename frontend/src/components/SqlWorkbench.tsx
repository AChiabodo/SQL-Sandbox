import Editor, { type OnMount } from "@monaco-editor/react";
import {
  AlertTriangle,
  ChevronLeft,
  Columns3,
  Database,
  FileSearch,
  HelpCircle,
  History,
  LayoutDashboard,
  Play,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";

import { ResultPanel } from "./ResultPanel";
import type {
  DashboardSqlEditSession,
  DatasetCatalogItem,
  SchemaInfo,
  SqlHistoryItem,
  SqlResult,
  TableInfo
} from "../types";

type SqlWorkbenchProps = {
  activeDataset: DatasetCatalogItem | null;
  schemas: SchemaInfo[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  sql: string;
  selectedStarterTitle: string | null;
  confirmDangerous: boolean;
  dangerWarning: string | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  result: SqlResult | null;
  sqlHistory: SqlHistoryItem[];
  onSelectTable: (schemaName: string, table: TableInfo) => void;
  onSqlChange: (value: string) => void;
  onSelectStarter: (title: string, sql: string) => void;
  onSetConfirmDangerous: (value: boolean) => void;
  onExecuteSql: (explain?: boolean) => Promise<void>;
  onFormatSql: () => void;
  dashboardEditSession: DashboardSqlEditSession | null;
  onAddSqlToDashboard: () => void;
  onSaveDashboardSqlEdit: () => void;
  onCancelDashboardSqlEdit: () => void;
  onResetStarter: () => void;
  onRestoreHistory: (item: SqlHistoryItem) => void;
};

type CompletionSeed = {
  label: string;
  insertText: string;
  detail: string;
  kind: number;
  sortText: string;
};

type TableOption = {
  schemaName: string;
  table: TableInfo;
};

const sqlKeywords = [
  "SELECT",
  "FROM",
  "WHERE",
  "JOIN",
  "LEFT JOIN",
  "RIGHT JOIN",
  "INNER JOIN",
  "GROUP BY",
  "ORDER BY",
  "LIMIT",
  "OFFSET",
  "COUNT",
  "SUM",
  "AVG",
  "MIN",
  "MAX",
  "EXPLAIN",
  "INSERT",
  "UPDATE",
  "DELETE",
  "CASE",
  "WHEN",
  "THEN",
  "ELSE",
  "END"
];

const columnDisplayLimit = 12;

function buildCompletionSeeds(
  schemas: SchemaInfo[],
  selectedTable: { schemaName: string; table: TableInfo } | null,
  monaco: typeof Monaco
): CompletionSeed[] {
  const seeds: CompletionSeed[] = [];

  sqlKeywords.forEach((keyword, index) => {
    seeds.push({
      label: keyword,
      insertText: keyword,
      detail: "Keyword SQL",
      kind: monaco.languages.CompletionItemKind.Keyword,
      sortText: `0-${String(index).padStart(3, "0")}`
    });
  });

  schemas.forEach((schema, schemaIndex) => {
    seeds.push({
      label: schema.name,
      insertText: schema.name,
      detail: "Schema",
      kind: monaco.languages.CompletionItemKind.Module,
      sortText: `1-${String(schemaIndex).padStart(3, "0")}`
    });

    schema.tables.forEach((table, tableIndex) => {
      const qualifiedTable = `${schema.name}.${table.name}`;

      seeds.push({
        label: qualifiedTable,
        insertText: qualifiedTable,
        detail: "Tabella qualificata",
        kind: monaco.languages.CompletionItemKind.Class,
        sortText: `2-${String(schemaIndex).padStart(3, "0")}-${String(tableIndex).padStart(3, "0")}`
      });
      seeds.push({
        label: table.name,
        insertText: table.name,
        detail: `Tabella in ${schema.name}`,
        kind: monaco.languages.CompletionItemKind.Class,
        sortText: `3-${String(schemaIndex).padStart(3, "0")}-${String(tableIndex).padStart(3, "0")}`
      });

      table.columns.forEach((column, columnIndex) => {
        const isSelectedTable =
          selectedTable?.schemaName === schema.name && selectedTable.table.name === table.name;
        const qualifiedColumn = `${table.name}.${column.name}`;
        const prefix = isSelectedTable ? "4" : "5";
        const detail = isSelectedTable
          ? `${column.dataType} - colonna della tabella attiva`
          : `${column.dataType} - ${qualifiedTable}`;

        seeds.push({
          label: column.name,
          insertText: column.name,
          detail,
          kind: monaco.languages.CompletionItemKind.Field,
          sortText: `${prefix}-${String(schemaIndex).padStart(3, "0")}-${String(tableIndex).padStart(3, "0")}-${String(columnIndex).padStart(3, "0")}`
        });
        seeds.push({
          label: qualifiedColumn,
          insertText: qualifiedColumn,
          detail,
          kind: monaco.languages.CompletionItemKind.Field,
          sortText: `6-${String(schemaIndex).padStart(3, "0")}-${String(tableIndex).padStart(3, "0")}-${String(columnIndex).padStart(3, "0")}`
        });
      });
    });
  });

  return seeds;
}

function getTables(schemas: SchemaInfo[]): TableOption[] {
  return schemas.flatMap((schema) => schema.tables.map((table) => ({ schemaName: schema.name, table })));
}

function tableValue(schemaName: string, tableName: string): string {
  return `${schemaName}.${tableName}`;
}

function matchesTable(item: TableOption, search: string): boolean {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return true;
  return `${item.schemaName} ${item.table.name}`.toLowerCase().includes(normalized);
}

function matchesColumn(column: TableInfo["columns"][number], search: string): boolean {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return true;
  return `${column.name} ${column.dataType}`.toLowerCase().includes(normalized);
}

export function SqlWorkbench({
  activeDataset,
  schemas,
  selectedTable,
  sql,
  selectedStarterTitle,
  confirmDangerous,
  dangerWarning,
  loading,
  error,
  notice,
  result,
  sqlHistory,
  onSelectTable,
  onSqlChange,
  onSelectStarter,
  onSetConfirmDangerous,
  onExecuteSql,
  onFormatSql,
  dashboardEditSession,
  onAddSqlToDashboard,
  onSaveDashboardSqlEdit,
  onCancelDashboardSqlEdit,
  onResetStarter,
  onRestoreHistory
}: SqlWorkbenchProps) {
  const monacoRef = useRef<typeof Monaco | null>(null);
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const completionSeedsRef = useRef<CompletionSeed[]>([]);
  const providerDisposableRef = useRef<Monaco.IDisposable | null>(null);
  const [isDatasetPanelOpen, setIsDatasetPanelOpen] = useState(() =>
    typeof window === "undefined" ? true : !window.matchMedia("(max-width: 820px)").matches
  );
  const [tableSearch, setTableSearch] = useState("");
  const [columnSearch, setColumnSearch] = useState("");
  const [showAllColumns, setShowAllColumns] = useState(false);

  const tables = useMemo(() => getTables(schemas), [schemas]);
  const activeColumns = selectedTable?.table.columns ?? [];
  const selectedTableValue = selectedTable ? tableValue(selectedTable.schemaName, selectedTable.table.name) : "";
  const selectedTableName = selectedTable ? `${selectedTable.schemaName}.${selectedTable.table.name}` : "Nessuna tabella";
  const filteredTables = useMemo(() => tables.filter((item) => matchesTable(item, tableSearch)), [tables, tableSearch]);
  const selectedTableInFilteredOptions = filteredTables.some(
    (item) => selectedTableValue === tableValue(item.schemaName, item.table.name)
  );
  const visibleColumns = useMemo(
    () => activeColumns.filter((column) => matchesColumn(column, columnSearch)),
    [activeColumns, columnSearch]
  );
  const shouldLimitColumns = !columnSearch.trim() && !showAllColumns && visibleColumns.length > columnDisplayLimit;
  const displayedColumns = shouldLimitColumns ? visibleColumns.slice(0, columnDisplayLimit) : visibleColumns;

  const completionSeeds = useMemo(
    () => (monacoRef.current ? buildCompletionSeeds(schemas, selectedTable, monacoRef.current) : []),
    [schemas, selectedTable]
  );

  useEffect(() => {
    completionSeedsRef.current = completionSeeds;
  }, [completionSeeds]);

  const handleBeforeMount = (monaco: typeof Monaco) => {
    monaco.editor.defineTheme("sandbox-sql", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "keyword", foreground: "91f2c6" },
        { token: "string", foreground: "f4c66d" },
        { token: "number", foreground: "a8d0ff" }
      ],
      colors: {
        "editor.background": "#0d1614",
        "editorLineNumber.foreground": "#50766a",
        "editorLineNumber.activeForeground": "#d9efe5",
        "editorCursor.foreground": "#8de1ba",
        "editor.selectionBackground": "#24453a",
        "editor.inactiveSelectionBackground": "#1b342c",
        "editorSuggestWidget.background": "#12201d",
        "editorSuggestWidget.border": "#33584f",
        "editorSuggestWidget.selectedBackground": "#213c34"
      }
    });
  };

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    completionSeedsRef.current = buildCompletionSeeds(schemas, selectedTable, monaco);

    if (!providerDisposableRef.current) {
      providerDisposableRef.current = monaco.languages.registerCompletionItemProvider("sql", {
        triggerCharacters: [".", " ", "_"],
        provideCompletionItems(model, position) {
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn
          };

          return {
            suggestions: completionSeedsRef.current.map((seed) => ({
              label: seed.label,
              insertText: seed.insertText,
              detail: seed.detail,
              kind: seed.kind,
              sortText: seed.sortText,
              range
            }))
          };
        }
      });
    }
  };

  const insertAtCursor = (text: string) => {
    const editor = editorRef.current;
    if (!editor) {
      onSqlChange(sql.trim() ? `${sql}\n${text}` : text);
      return;
    }

    const selection = editor.getSelection();
    if (!selection) return;

    editor.executeEdits("sql-dataset-panel", [{ range: selection, text, forceMoveMarkers: true }]);
    editor.focus();
    onSqlChange(editor.getValue());
  };

  const handleTableSelect = (value: string) => {
    if (!value) return;

    const next = tables.find((item) => tableValue(item.schemaName, item.table.name) === value);
    if (next) {
      onSelectTable(next.schemaName, next.table);
      setColumnSearch("");
      setShowAllColumns(false);
    }
  };

  return (
    <div className="mode-layout sql-layout">
      <div className="sql-main-column">
        <section className="workspace-card editor-shell">
          <div className="section-title split">
            <div>
              <p className="section-kicker">Modalita SQL</p>
              <h2>Editor diretto</h2>
            </div>
            <div className="toolbar-actions">
              <button onClick={onFormatSql}>
                <Sparkles size={16} />
                Formatta
              </button>
              {dashboardEditSession ? (
                <>
                  <button className="primary" onClick={onSaveDashboardSqlEdit} disabled={!sql.trim()}>
                    <Save size={16} />
                    Salva modifiche
                  </button>
                  <button onClick={onCancelDashboardSqlEdit}>
                    <X size={16} />
                    Annulla modifica
                  </button>
                </>
              ) : (
                <button onClick={onAddSqlToDashboard} disabled={!activeDataset?.initialized || !sql.trim()}>
                  <LayoutDashboard size={16} />
                  Aggiungi alla dashboard
                </button>
              )}
              <button onClick={onResetStarter}>
                <RotateCcw size={16} />
                Ripristina starter
              </button>
              <button onClick={() => void onExecuteSql(true)} disabled={loading}>
                <FileSearch size={16} />
                Explain
              </button>
              <button className="primary" onClick={() => void onExecuteSql(false)} disabled={loading}>
                <Play size={16} />
                Esegui
              </button>
            </div>
          </div>

          {dashboardEditSession && (
            <div className="dashboard-edit-banner">
              <LayoutDashboard size={16} />
              <span>
                Modifica dashboard: <strong>{dashboardEditSession.widget.title}</strong>
              </span>
            </div>
          )}

          <div className={isDatasetPanelOpen ? "sql-editor-grid" : "sql-editor-grid collapsed"}>
            <div className="sql-editor-primary">
              <div className="sql-context-strip">
                <div>
                  <span>Tabella attiva</span>
                  <strong>{selectedTableName}</strong>
                </div>
                <div>
                  <span>Colonne</span>
                  <strong>{activeColumns.length}</strong>
                </div>
                <button
                  className="sql-panel-toggle"
                  onClick={() => setIsDatasetPanelOpen((current) => !current)}
                  aria-expanded={isDatasetPanelOpen}
                >
                  <Database size={16} />
                  {isDatasetPanelOpen ? "Nascondi dataset" : "Mostra dataset"}
                </button>
              </div>

              <div className="monaco-frame">
                <Editor
                  height="520px"
                  language="sql"
                  value={sql}
                  beforeMount={handleBeforeMount}
                  onMount={handleEditorMount}
                  onChange={(value) => onSqlChange(value ?? "")}
                  theme="sandbox-sql"
                  options={{
                    minimap: { enabled: false },
                    fontSize: 14,
                    padding: { top: 16, bottom: 16 },
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    suggestOnTriggerCharacters: true,
                    quickSuggestions: true,
                    tabSize: 2
                  }}
                />
              </div>
            </div>

            {isDatasetPanelOpen && (
              <aside className="sql-dataset-panel" aria-label="Dataset SQL">
                <div className="sql-panel-header">
                  <div>
                    <p className="section-kicker">Dataset</p>
                    <h3>{activeDataset?.name ?? "Nessuna raccolta"}</h3>
                  </div>
                  <div className="sql-panel-actions">
                    <span
                      className="sql-help-icon"
                      title="Autocomplete attivo su keyword, schema, tabelle e colonne del dataset attivo."
                      aria-label="Informazioni autocomplete"
                      role="img"
                    >
                      <HelpCircle size={16} />
                    </span>
                    <button
                      className="icon-button"
                      onClick={() => setIsDatasetPanelOpen(false)}
                      aria-label="Nascondi pannello dataset"
                    >
                      <ChevronLeft size={16} />
                    </button>
                  </div>
                </div>

                <section className="sql-panel-section">
                  <div className="sql-panel-section-title">
                    <span>Tabelle</span>
                    <small>{tables.length}</small>
                  </div>
                  <label className="search-control">
                    <Search size={15} />
                    <input
                      value={tableSearch}
                      onChange={(event) => setTableSearch(event.target.value)}
                      placeholder="Cerca tabella"
                    />
                  </label>
                  <label className="table-select-control">
                    <span>Tabella attiva</span>
                    <select
                      value={selectedTableInFilteredOptions ? selectedTableValue : ""}
                      onChange={(event) => handleTableSelect(event.target.value)}
                      disabled={tables.length === 0}
                    >
                      {tables.length === 0 ? (
                        <option>Nessuna tabella disponibile</option>
                      ) : filteredTables.length === 0 ? (
                        <option value="">Nessuna tabella trovata</option>
                      ) : (
                        filteredTables.map(({ schemaName, table }) => (
                          <option key={tableValue(schemaName, table.name)} value={tableValue(schemaName, table.name)}>
                            {schemaName}.{table.name} - {table.columns.length} colonne
                          </option>
                        ))
                    )}
                    </select>
                  </label>
                </section>

                <section className="sql-panel-section">
                  <div className="sql-panel-section-title">
                    <span>Colonne</span>
                    <small>{activeColumns.length}</small>
                  </div>
                  <label className="search-control">
                    <Search size={15} />
                    <input
                      value={columnSearch}
                      onChange={(event) => setColumnSearch(event.target.value)}
                      placeholder="Cerca colonna o tipo"
                      disabled={!selectedTable}
                    />
                  </label>
                  <div className="sql-column-token-grid">
                    {displayedColumns.map((column) => (
                      <button
                        key={column.name}
                        className="sql-column-token"
                        onClick={() => insertAtCursor(column.name)}
                        title={`Inserisci ${column.name}`}
                      >
                        <Columns3 size={14} />
                        <span>
                          <strong>{column.name}</strong>
                          <small>{column.dataType}</small>
                        </span>
                      </button>
                    ))}
                    {selectedTable && visibleColumns.length === 0 && (
                      <div className="ghost-row">Nessuna colonna trovata per questa ricerca.</div>
                    )}
                    {!selectedTable && <div className="ghost-row">Seleziona una tabella per vedere le colonne.</div>}
                  </div>
                  {visibleColumns.length > columnDisplayLimit && !columnSearch.trim() && (
                    <button className="sql-show-more-columns" onClick={() => setShowAllColumns((current) => !current)}>
                      {showAllColumns
                        ? "Mostra meno"
                        : `Mostra tutte (${visibleColumns.length})`}
                    </button>
                  )}
                </section>

                <section className="sql-panel-section starter-panel">
                  <div className="sql-panel-section-title">
                    <span>Query starter</span>
                    <small>{activeDataset?.starterQueries.length ?? 0}</small>
                  </div>
                  {activeDataset?.starterQueries.length ? (
                    <div className="starter-card-list">
                      {activeDataset.starterQueries.map((starter) => (
                        <button
                          key={starter.title}
                          className={selectedStarterTitle === starter.title ? "starter-card active" : "starter-card"}
                          onClick={() => onSelectStarter(starter.title, starter.sql)}
                        >
                          <strong>{starter.title}</strong>
                          <small>{selectedStarterTitle === starter.title ? "In uso nell'editor" : "Carica nell'editor"}</small>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">Le query starter compariranno quando selezioni una raccolta dati.</p>
                  )}
                </section>
              </aside>
            )}
          </div>

          {dangerWarning && (
            <div className="warning">
              <AlertTriangle size={16} />
              <span>{dangerWarning}</span>
            </div>
          )}

          <label className="confirm-row editor-confirm">
            <input
              type="checkbox"
              checked={confirmDangerous}
              onChange={(event) => onSetConfirmDangerous(event.target.checked)}
            />
            Confermo esecuzione di query potenzialmente distruttive
          </label>
        </section>

        <ResultPanel result={result} error={error} notice={notice} title="Risultati SQL" />

        <details className="workspace-card history-card">
          <summary className="disclosure-summary">
            <span>
              <History size={18} />
              Cronologia sessione
            </span>
            <small>{sqlHistory.length} query</small>
          </summary>
          {sqlHistory.length === 0 ? (
            <p className="muted">Le query eseguite in questa sessione appariranno qui.</p>
          ) : (
            <div className="history-list">
              {sqlHistory.map((item) => (
                <button key={item.id} className="history-item" onClick={() => onRestoreHistory(item)}>
                  <strong>{item.label}</strong>
                  <span>{item.createdAt}</span>
                  <small>{item.sql.split("\n")[0]}</small>
                </button>
              ))}
            </div>
          )}
        </details>
      </div>
    </div>
  );
}
