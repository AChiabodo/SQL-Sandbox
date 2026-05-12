import Editor, { type OnMount } from "@monaco-editor/react";
import { AlertTriangle, FileSearch, History, Play, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import type * as Monaco from "monaco-editor";

import { ResultPanel } from "./ResultPanel";
import { TablePicker } from "./TablePicker";
import type {
  ColumnInfo,
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

function SchemaContextCard({
  selectedTable,
  columns
}: {
  selectedTable: { schemaName: string; table: TableInfo } | null;
  columns: ColumnInfo[];
}) {
  return (
    <section className="sql-context-card">
      <div className="section-title split">
        <div>
          <p className="section-kicker">Contesto</p>
          <h2>{selectedTable ? `${selectedTable.schemaName}.${selectedTable.table.name}` : "Nessuna tabella"}</h2>
        </div>
        <span className="badge-soft">{columns.length} colonne</span>
      </div>
      {selectedTable ? (
        <div className="token-cloud">
          {columns.map((column) => (
            <span key={column.name} className="data-pill">
              <strong>{column.name}</strong>
              <small>{column.dataType}</small>
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">Seleziona una tabella in questa pagina per arricchire i suggerimenti dell'editor.</p>
      )}
    </section>
  );
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
  onResetStarter,
  onRestoreHistory
}: SqlWorkbenchProps) {
  const monacoRef = useRef<typeof Monaco | null>(null);
  const completionSeedsRef = useRef<CompletionSeed[]>([]);
  const providerDisposableRef = useRef<Monaco.IDisposable | null>(null);

  const activeColumns = selectedTable?.table.columns ?? [];

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

  const handleEditorMount: OnMount = (_, monaco) => {
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

          <TablePicker
            schemas={schemas}
            selectedTable={selectedTable}
            onSelectTable={onSelectTable}
            title="Contesto tabella"
            description="Seleziona qui la tabella usata da autocomplete, query starter e lettura dello schema."
          />

          {activeDataset?.starterQueries.length ? (
            <div className="starter-queries">
              {activeDataset.starterQueries.map((starter) => (
                <button
                  key={starter.title}
                  className={selectedStarterTitle === starter.title ? "chip active" : "chip"}
                  onClick={() => onSelectStarter(starter.title, starter.sql)}
                >
                  {starter.title}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">Le query starter compariranno quando selezioni una raccolta dati.</p>
          )}

          <div className="editor-toolbar-note">
            <span>Autocomplete su keyword, schema, tabelle e colonne del dataset attivo.</span>
            <span>
              {selectedTable
                ? `Contesto: ${selectedTable.schemaName}.${selectedTable.table.name}`
                : "Nessun contesto tabella"}
            </span>
          </div>

          <SchemaContextCard selectedTable={selectedTable} columns={activeColumns} />

          <div className="monaco-frame">
            <Editor
              height="440px"
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
