import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { LayoutDashboard, Pause, Pencil, Play, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { ResponsiveGridLayout, useContainerWidth, type Layout, type ResponsiveLayouts } from "react-grid-layout";
import { useEffect, useMemo, useState } from "react";

import type { DatasetCatalogItem, SchemaInfo, SqlResult } from "../types";
import { formatResultColumn, humanizeIdentifier, makeId, requestJson } from "../utils";

type WidgetType = "kpi" | "bar" | "line" | "area" | "pie" | "table";

type DashboardWidget = {
  id: string;
  title: string;
  type: WidgetType;
  sql: string;
  xField: string;
  yField: string;
  refreshMs: number;
};

type WidgetRunState = {
  loading: boolean;
  error: string | null;
  result: SqlResult | null;
  lastUpdated: string | null;
};

type DashboardStorage = {
  widgets: DashboardWidget[];
  layouts: ResponsiveLayouts;
};

type DashboardDraft = DashboardWidget & { mode: "create" | "edit" };

type AdvancedDashboardProps = {
  activeDataset: DatasetCatalogItem | null;
  schemas: SchemaInfo[];
};

const chartColors = ["#1f7d5b", "#2563eb", "#d97706", "#7c3aed", "#be123c", "#0f766e"];
const refreshOptions = [
  { label: "Off", value: 0 },
  { label: "15s", value: 15000 },
  { label: "30s", value: 30000 },
  { label: "60s", value: 60000 },
  { label: "5m", value: 300000 }
];

function storageKey(schemaName: string | null | undefined): string {
  return `dashboard.v1.${schemaName ?? "empty"}`;
}

function defaultWidgetType(title: string, index: number): WidgetType {
  const normalized = title.toLowerCase();
  if (normalized.includes("mensile") || normalized.includes("tempo") || normalized.includes("response")) return "line";
  if (normalized.includes("tasso") || normalized.includes("csat")) return "bar";
  if (index === 0) return "area";
  if (index === 1) return "bar";
  return "table";
}

function defaultWidgets(dataset: DatasetCatalogItem | null): DashboardWidget[] {
  if (!dataset?.starterQueries.length) return [];
  return dataset.starterQueries.map((starter, index) => ({
    id: makeId("widget"),
    title: starter.title,
    type: defaultWidgetType(starter.title, index),
    sql: starter.sql,
    xField: "",
    yField: "",
    refreshMs: 30000
  }));
}

function defaultLayouts(widgets: DashboardWidget[]): ResponsiveLayouts {
  return {
    lg: widgets.map((widget, index) => ({
      i: widget.id,
      x: (index % 2) * 6,
      y: Math.floor(index / 2) * 7,
      w: widget.type === "kpi" ? 3 : 6,
      h: widget.type === "kpi" ? 4 : 7,
      minW: widget.type === "kpi" ? 3 : 4,
      minH: widget.type === "kpi" ? 3 : 5
    }))
  };
}

function loadDashboard(dataset: DatasetCatalogItem | null): DashboardStorage {
  const fallbackWidgets = defaultWidgets(dataset);
  const fallback = { widgets: fallbackWidgets, layouts: defaultLayouts(fallbackWidgets) };
  if (!dataset?.schemaName) return fallback;

  try {
    const raw = window.localStorage.getItem(storageKey(dataset.schemaName));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as DashboardStorage;
    if (!Array.isArray(parsed.widgets) || !parsed.layouts) return fallback;
    return parsed.widgets.length > 0 ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function saveDashboard(schemaName: string | null | undefined, storage: DashboardStorage) {
  if (!schemaName) return;
  window.localStorage.setItem(storageKey(schemaName), JSON.stringify(storage));
}

function numericColumns(result: SqlResult | null): string[] {
  if (!result?.rows.length) return [];
  return result.columns.filter((column) => result.rows.some((row) => Number.isFinite(Number(row[column]))));
}

function preferredMetricColumn(result: SqlResult | null, except = ""): string {
  const candidates = numericColumns(result).filter((column) => column !== except);
  return candidates[candidates.length - 1] ?? result?.columns.find((column) => column !== except) ?? "";
}

function preferredDimensionColumn(result: SqlResult | null, yField = ""): string {
  if (!result?.columns.length) return "";
  const numeric = new Set(numericColumns(result));
  const textDimension = result.columns.find((column) => column !== yField && !numeric.has(column));
  if (textDimension) return textDimension;
  if (result.columns.length > 2) return result.columns[result.columns.length - 2] ?? "";
  return result.columns.find((column) => column !== yField) ?? result.columns[0] ?? "";
}

function resolveChartFields(widget: DashboardWidget, result: SqlResult | null): { xField: string; yField: string } {
  const yField = widget.yField || preferredMetricColumn(result);
  const xField = widget.xField || preferredDimensionColumn(result, yField);
  return { xField, yField };
}

function chartData(result: SqlResult | null, xField: string, yField: string) {
  if (!result) return [];
  return result.rows.map((row) => ({
    ...row,
    [xField]: String(row[xField] ?? ""),
    [yField]: Number(row[yField] ?? 0)
  }));
}

function formatMetric(value: unknown): string {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(numeric);
  }
  return String(value ?? "-");
}

function WidgetPreview({ widget, state }: { widget: DashboardWidget; state: WidgetRunState | undefined }) {
  const result = state?.result ?? null;
  const { xField, yField } = resolveChartFields(widget, result);
  const data = chartData(result, xField, yField);

  if (state?.error) {
    return <div className="dashboard-widget-error">{state.error}</div>;
  }

  if (state?.loading && !result) {
    return <div className="dashboard-widget-empty">Caricamento dati...</div>;
  }

  if (!result || result.rows.length === 0) {
    return <div className="dashboard-widget-empty">Nessun dato disponibile.</div>;
  }

  if (widget.type === "kpi") {
    const metric = widget.yField || preferredMetricColumn(result) || result.columns[0];
    return (
      <div className="kpi-widget">
        <span>{humanizeIdentifier(metric)}</span>
        <strong>{formatMetric(result.rows[0]?.[metric])}</strong>
        <small>{result.rowCount} righe · {result.durationMs} ms</small>
      </div>
    );
  }

  if (widget.type === "table") {
    return (
      <div className="dashboard-table-scroll">
        <table>
          <thead>
            <tr>
              {result.columns.map((column) => {
                const formatted = formatResultColumn(column);
                return (
                  <th key={column} title={formatted.technical}>
                    {formatted.label}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {result.rows.slice(0, 8).map((row, index) => (
              <tr key={index}>
                {result.columns.map((column) => (
                  <td key={column}>{String(row[column] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (!xField || !yField) {
    return <div className="dashboard-widget-empty">Configura asse X e metrica Y.</div>;
  }

  if (widget.type === "pie") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Tooltip />
          <Pie data={data} dataKey={yField} nameKey={xField} innerRadius="48%" outerRadius="76%" paddingAngle={2}>
            {data.map((_, index) => (
              <Cell key={index} fill={chartColors[index % chartColors.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    );
  }

  const commonProps = {
    data,
    margin: { top: 12, right: 16, bottom: 8, left: 0 }
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      {widget.type === "bar" ? (
        <BarChart {...commonProps}>
          <XAxis dataKey={xField} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey={yField} fill="#1f7d5b" radius={[5, 5, 0, 0]} />
        </BarChart>
      ) : widget.type === "area" ? (
        <AreaChart {...commonProps}>
          <XAxis dataKey={xField} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Area type="monotone" dataKey={yField} stroke="#1f7d5b" fill="#b7dfcd" strokeWidth={2} />
        </AreaChart>
      ) : (
        <LineChart {...commonProps}>
          <XAxis dataKey={xField} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey={yField} stroke="#1f7d5b" strokeWidth={2} dot={false} />
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}

function WidgetEditor({
  draft,
  result,
  onChange,
  onClose,
  onSave
}: {
  draft: DashboardDraft;
  result: SqlResult | null;
  onChange: (next: DashboardDraft) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <div className="dashboard-editor-backdrop" role="dialog" aria-modal="true">
      <section className="dashboard-editor">
        <div className="section-title split">
          <div>
            <p className="section-kicker">{draft.mode === "create" ? "Nuovo widget" : "Modifica widget"}</p>
            <h2>{draft.title || "Visualizzazione"}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Chiudi editor">
            <X size={16} />
          </button>
        </div>
        <div className="dashboard-editor-grid">
          <label>
            Titolo
            <input value={draft.title} onChange={(event) => onChange({ ...draft, title: event.target.value })} />
          </label>
          <label>
            Tipo
            <select value={draft.type} onChange={(event) => onChange({ ...draft, type: event.target.value as WidgetType })}>
              <option value="kpi">KPI</option>
              <option value="bar">Bar</option>
              <option value="line">Line</option>
              <option value="area">Area</option>
              <option value="pie">Pie/Donut</option>
              <option value="table">Table</option>
            </select>
          </label>
          <label>
            Refresh
            <select value={draft.refreshMs} onChange={(event) => onChange({ ...draft, refreshMs: Number(event.target.value) })}>
              {refreshOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Asse X / categoria
            <select value={draft.xField} onChange={(event) => onChange({ ...draft, xField: event.target.value })}>
              <option value="">Auto</option>
              {result?.columns.map((column) => (
                <option key={column} value={column}>
                  {humanizeIdentifier(column)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Metrica Y
            <select value={draft.yField} onChange={(event) => onChange({ ...draft, yField: event.target.value })}>
              <option value="">Auto</option>
              {result?.columns.map((column) => (
                <option key={column} value={column}>
                  {humanizeIdentifier(column)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="dashboard-sql-editor">
          Query SQL read-only
          <textarea value={draft.sql} onChange={(event) => onChange({ ...draft, sql: event.target.value })} />
        </label>
        <div className="toolbar-actions">
          <button onClick={onClose}>Annulla</button>
          <button className="primary" onClick={onSave}>
            <Save size={16} />
            Salva
          </button>
        </div>
      </section>
    </div>
  );
}

export function AdvancedDashboard({ activeDataset, schemas }: AdvancedDashboardProps) {
  const [{ widgets, layouts }, setDashboard] = useState<DashboardStorage>(() => loadDashboard(activeDataset));
  const [runs, setRuns] = useState<Record<string, WidgetRunState>>({});
  const [draft, setDraft] = useState<DashboardDraft | null>(null);
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1000 });
  const schema = schemas.find((item) => item.name === activeDataset?.schemaName) ?? schemas[0] ?? null;

  useEffect(() => {
    setDashboard(loadDashboard(activeDataset));
    setRuns({});
    setDraft(null);
  }, [activeDataset?.schemaName]);

  useEffect(() => {
    saveDashboard(activeDataset?.schemaName, { widgets, layouts });
  }, [activeDataset?.schemaName, widgets, layouts]);

  const runWidget = async (widget: DashboardWidget) => {
    setRuns((current) => ({
      ...current,
      [widget.id]: { loading: true, error: null, result: current[widget.id]?.result ?? null, lastUpdated: current[widget.id]?.lastUpdated ?? null }
    }));
    try {
      const result = await requestJson<SqlResult>("/dashboard/query", {
        method: "POST",
        body: JSON.stringify({ sql: widget.sql })
      });
      setRuns((current) => ({
        ...current,
        [widget.id]: {
          loading: false,
          error: null,
          result,
          lastUpdated: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
        }
      }));
    } catch (err) {
      setRuns((current) => ({
        ...current,
        [widget.id]: {
          loading: false,
          error: err instanceof Error ? err.message : "Errore sconosciuto",
          result: current[widget.id]?.result ?? null,
          lastUpdated: current[widget.id]?.lastUpdated ?? null
        }
      }));
    }
  };

  useEffect(() => {
    widgets.forEach((widget) => void runWidget(widget));
  }, [widgets.map((widget) => `${widget.id}:${widget.sql}`).join("|")]);

  useEffect(() => {
    const timers = widgets
      .filter((widget) => widget.refreshMs > 0)
      .map((widget) => window.setInterval(() => void runWidget(widget), widget.refreshMs));
    return () => timers.forEach((timer) => window.clearInterval(timer));
  }, [widgets.map((widget) => `${widget.id}:${widget.refreshMs}:${widget.sql}`).join("|")]);

  const draftResult = draft ? runs[draft.id]?.result ?? null : null;
  const schemaStats = useMemo(
    () => ({
      tables: schema?.tables.length ?? 0,
      columns: schema?.tables.reduce((total, table) => total + table.columns.length, 0) ?? 0
    }),
    [schema]
  );

  const addWidget = () => {
    setDraft({
      id: makeId("widget"),
      mode: "create",
      title: "Nuova vista",
      type: "bar",
      sql: activeDataset?.starterQueries[0]?.sql ?? "SELECT 1 AS value",
      xField: "",
      yField: "",
      refreshMs: 30000
    });
  };

  const saveDraft = () => {
    if (!draft) return;
    const { mode, ...widget } = draft;
    setDashboard((current) => {
      const nextWidgets =
        mode === "create"
          ? [...current.widgets, widget]
          : current.widgets.map((item) => (item.id === widget.id ? widget : item));
      const hasLayout = current.layouts.lg?.some((item) => item.i === widget.id);
      const nextLayouts = hasLayout
        ? current.layouts
        : {
            ...current.layouts,
            lg: [
              ...(current.layouts.lg ?? []),
              {
                i: widget.id,
                x: 0,
                y: Infinity,
                w: widget.type === "kpi" ? 3 : 6,
                h: widget.type === "kpi" ? 4 : 7,
                minW: widget.type === "kpi" ? 3 : 4,
                minH: widget.type === "kpi" ? 3 : 5
              }
            ]
          };
      return { widgets: nextWidgets, layouts: nextLayouts };
    });
    setDraft(null);
  };

  const removeWidget = (widgetId: string) => {
    setDashboard((current) => ({
      widgets: current.widgets.filter((widget) => widget.id !== widgetId),
      layouts: {
        ...current.layouts,
        lg: current.layouts.lg?.filter((layout) => layout.i !== widgetId) ?? []
      }
    }));
    setRuns((current) => {
      const next = { ...current };
      delete next[widgetId];
      return next;
    });
  };

  const resetDashboard = () => {
    const nextWidgets = defaultWidgets(activeDataset);
    setDashboard({ widgets: nextWidgets, layouts: defaultLayouts(nextWidgets) });
  };

  return (
    <div className="mode-layout dashboard-layout">
      <section className="workspace-card dashboard-hero">
        <div className="section-title split">
          <div>
            <p className="section-kicker">Dashboard avanzata</p>
            <h2>{activeDataset?.name ?? "Seleziona un dataset"}</h2>
          </div>
          <div className="toolbar-actions">
            <button onClick={resetDashboard}>
              <RefreshCw size={16} />
              Reset viste
            </button>
            <button className="primary" onClick={addWidget}>
              <Plus size={16} />
              Aggiungi scheda
            </button>
          </div>
        </div>
        <div className="dashboard-overview">
          <div>
            <span>Schema</span>
            <strong>{activeDataset?.schemaName ?? "-"}</strong>
          </div>
          <div>
            <span>Tabelle</span>
            <strong>{schemaStats.tables}</strong>
          </div>
          <div>
            <span>Colonne</span>
            <strong>{schemaStats.columns}</strong>
          </div>
          <div>
            <span>Widget</span>
            <strong>{widgets.length}</strong>
          </div>
        </div>
      </section>

      {widgets.length === 0 ? (
        <section className="workspace-card empty-state">
          <LayoutDashboard size={24} />
          <p>Inizializza un dataset o aggiungi una scheda per costruire la dashboard.</p>
        </section>
      ) : (
        <div ref={containerRef}>
          {mounted && (
            <ResponsiveGridLayout
              className="dashboard-grid"
              width={width}
              layouts={layouts}
              breakpoints={{ lg: 1200, md: 980, sm: 760, xs: 0 }}
              cols={{ lg: 12, md: 8, sm: 4, xs: 1 }}
              rowHeight={34}
              margin={[16, 16]}
              containerPadding={[0, 0]}
              dragConfig={{ handle: ".dashboard-widget-drag", cancel: ".widget-actions button" }}
              onLayoutChange={(layout: Layout, allLayouts: ResponsiveLayouts) =>
                setDashboard((current) => ({ ...current, layouts: allLayouts.lg ? allLayouts : { ...allLayouts, lg: layout } }))
              }
            >
              {widgets.map((widget) => {
                const state = runs[widget.id];
                return (
                  <section key={widget.id} className="workspace-card dashboard-widget">
                    <div className="dashboard-widget-header dashboard-widget-drag">
                      <div>
                        <h3>{widget.title}</h3>
                        <span>
                          {state?.lastUpdated ? `Aggiornato ${state.lastUpdated}` : "In attesa dati"}
                          {widget.refreshMs > 0 ? ` · refresh ${widget.refreshMs / 1000}s` : " · refresh off"}
                        </span>
                      </div>
                      <div className="widget-actions">
                        <button className="icon-button" onClick={() => void runWidget(widget)} aria-label="Aggiorna widget">
                          <RefreshCw size={15} />
                        </button>
                        <button
                          className="icon-button"
                          onClick={() => setDraft({ ...widget, mode: "edit" })}
                          aria-label="Modifica widget"
                        >
                          <Pencil size={15} />
                        </button>
                        <button className="icon-button" onClick={() => removeWidget(widget.id)} aria-label="Elimina widget">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                    <div className="dashboard-widget-body">
                      <WidgetPreview widget={widget} state={state} />
                    </div>
                    <div className="dashboard-widget-footer">
                      <span>{state?.loading ? "Query in corso" : `${state?.result?.durationMs ?? "-"} ms`}</span>
                      <span>{widget.refreshMs > 0 ? <Play size={12} /> : <Pause size={12} />}</span>
                    </div>
                  </section>
                );
              })}
            </ResponsiveGridLayout>
          )}
        </div>
      )}

      {draft && (
        <WidgetEditor
          draft={draft}
          result={draftResult}
          onChange={setDraft}
          onClose={() => setDraft(null)}
          onSave={saveDraft}
        />
      )}
    </div>
  );
}
