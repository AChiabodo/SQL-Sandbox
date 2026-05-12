import type {
  DashboardStorage,
  DashboardWidget,
  DashboardWidgetProposal,
  DatasetCatalogItem,
  WidgetType
} from "./types";
import { makeId } from "./utils";

export function dashboardStorageKey(schemaName: string | null | undefined): string {
  return `dashboard.v1.${schemaName ?? "empty"}`;
}

export function defaultWidgetType(title: string, index: number): WidgetType {
  const normalized = title.toLowerCase();
  if (normalized.includes("mensile") || normalized.includes("tempo") || normalized.includes("response")) return "line";
  if (normalized.includes("tasso") || normalized.includes("csat")) return "bar";
  if (index === 0) return "area";
  if (index === 1) return "bar";
  return "table";
}

export function defaultWidgets(dataset: DatasetCatalogItem | null): DashboardWidget[] {
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

export function layoutForWidget(widget: DashboardWidget) {
  return {
    i: widget.id,
    x: 0,
    y: Infinity,
    w: widget.type === "kpi" ? 3 : 6,
    h: widget.type === "kpi" ? 4 : 7,
    minW: widget.type === "kpi" ? 3 : 4,
    minH: widget.type === "kpi" ? 3 : 5
  };
}

export function defaultLayouts(widgets: DashboardWidget[]) {
  return {
    lg: widgets.map((widget, index) => ({
      ...layoutForWidget(widget),
      x: (index % 2) * 6,
      y: Math.floor(index / 2) * 7
    }))
  };
}

export function loadDashboard(dataset: DatasetCatalogItem | null): DashboardStorage {
  const fallbackWidgets = defaultWidgets(dataset);
  const fallback = { widgets: fallbackWidgets, layouts: defaultLayouts(fallbackWidgets) };
  if (!dataset?.schemaName) return fallback;

  try {
    const raw = window.localStorage.getItem(dashboardStorageKey(dataset.schemaName));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as DashboardStorage;
    if (!Array.isArray(parsed.widgets) || !parsed.layouts) return fallback;
    return parsed.widgets.length > 0 ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function saveDashboard(schemaName: string | null | undefined, storage: DashboardStorage) {
  if (!schemaName) return;
  window.localStorage.setItem(dashboardStorageKey(schemaName), JSON.stringify(storage));
}

export function addDashboardWidget(
  dataset: DatasetCatalogItem,
  proposal: DashboardWidgetProposal
): DashboardWidget {
  const widget: DashboardWidget = {
    id: makeId("widget"),
    title: proposal.title,
    type: proposal.type,
    sql: proposal.sql,
    xField: proposal.xField,
    yField: proposal.yField,
    refreshMs: proposal.refreshMs
  };
  const current = loadDashboard(dataset);
  const next: DashboardStorage = {
    widgets: [...current.widgets, widget],
    layouts: {
      ...current.layouts,
      lg: [...(current.layouts.lg ?? []), layoutForWidget(widget)]
    }
  };
  saveDashboard(dataset.schemaName, next);
  return widget;
}

export function updateDashboardWidget(
  dataset: DatasetCatalogItem,
  widget: DashboardWidget
): DashboardWidget {
  const current = loadDashboard(dataset);
  const hasWidget = current.widgets.some((item) => item.id === widget.id);
  const next: DashboardStorage = {
    widgets: hasWidget
      ? current.widgets.map((item) => (item.id === widget.id ? widget : item))
      : [...current.widgets, widget],
    layouts: {
      ...current.layouts,
      lg: current.layouts.lg?.some((item) => item.i === widget.id)
        ? current.layouts.lg
        : [...(current.layouts.lg ?? []), layoutForWidget(widget)]
    }
  };
  saveDashboard(dataset.schemaName, next);
  return widget;
}
