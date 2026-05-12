import { ChevronLeft, ChevronRight, RefreshCw, Rows3, Table2 } from "lucide-react";

import { ResultPanel } from "./ResultPanel";
import { TablePicker } from "./TablePicker";
import type { SchemaInfo, SqlResult, TableInfo } from "../types";

type TableBrowserProps = {
  schemas: SchemaInfo[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  loading: boolean;
  result: SqlResult | null;
  error: string | null;
  notice: string | null;
  limit: number;
  offset: number;
  onLimitChange: (value: number) => void;
  onOffsetChange: (value: number) => void;
  onSelectTable: (schemaName: string, table: TableInfo) => void;
  onRefresh: () => Promise<void>;
};

export function TableBrowser({
  schemas,
  selectedTable,
  loading,
  result,
  error,
  notice,
  limit,
  offset,
  onLimitChange,
  onOffsetChange,
  onSelectTable,
  onRefresh
}: TableBrowserProps) {
  const activeColumns = selectedTable?.table.columns ?? [];

  return (
    <div className="mode-layout table-browser-layout">
      <section className="workspace-card table-browser-header">
        <div className="section-title split">
          <div>
            <p className="section-kicker">Browser tabelle</p>
            <h2>
              {selectedTable
                ? `${selectedTable.schemaName}.${selectedTable.table.name}`
                : "Seleziona una tabella"}
            </h2>
          </div>
          <div className="toolbar-actions">
            <label className="inline-control">
              Righe
              <select value={limit} onChange={(event) => onLimitChange(Number(event.target.value))}>
                {[50, 100, 250, 500].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => onOffsetChange(Math.max(offset - limit, 0))}
              disabled={offset === 0 || loading}
            >
              <ChevronLeft size={16} />
              Precedente
            </button>
            <button onClick={() => onOffsetChange(offset + limit)} disabled={!selectedTable || loading}>
              Successiva
              <ChevronRight size={16} />
            </button>
            <button className="primary" onClick={() => void onRefresh()} disabled={!selectedTable || loading}>
              <RefreshCw size={16} />
              Aggiorna righe
            </button>
          </div>
        </div>
        <TablePicker
          schemas={schemas}
          selectedTable={selectedTable}
          onSelectTable={onSelectTable}
          title="Sorgente tabellare"
          description="Cambia tabella direttamente da qui per ispezionare struttura e righe complete."
        />
        <p className="workspace-context spacious">
          <span>Offset attuale: {offset}</span>
          <Rows3 size={14} />
          <span>{activeColumns.length} colonne disponibili</span>
        </p>
      </section>

      <div className="table-browser-grid">
        <section className="workspace-card table-profile-card">
          <div className="section-title">
            <Table2 size={18} />
            <h2>Struttura tabella</h2>
          </div>
          {selectedTable ? (
            <div className="column-list extended">
              {activeColumns.map((column) => (
                <div key={column.name} className="column-row profile">
                  <div>
                    <span>{column.name}</span>
                    <small>{column.dataType}</small>
                  </div>
                  <div className="column-flags">
                    <span>{column.nullable ? "nullable" : "not null"}</span>
                    {column.default && <span>{column.default}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Seleziona una tabella da questa pagina per vedere struttura e contenuti.</p>
          )}
        </section>

        <ResultPanel result={result} error={error} notice={notice} title="Righe tabellari" />
      </div>
    </div>
  );
}
