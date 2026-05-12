import { Database, RefreshCw } from "lucide-react";

import type { DatasetCatalogItem } from "../types";
import { formatRowEstimate } from "../utils";

type DatasetSidebarProps = {
  dbName: string;
  loading: boolean;
  datasets: DatasetCatalogItem[];
  activeDatasetId: string | null;
  activeDatasetSchema: string | null;
  initializingDatasetId: string | null;
  onRefresh: () => void;
  onSelectDataset: (datasetId: string) => void;
  onInitializeDataset: (datasetId: string) => void;
};

export function DatasetSidebar({
  dbName,
  loading,
  datasets,
  activeDatasetId,
  activeDatasetSchema,
  initializingDatasetId,
  onRefresh,
  onSelectDataset,
  onInitializeDataset
}: DatasetSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <Database size={24} />
        <div>
          <h1>PostgreSQL Sandbox</h1>
          <p>{dbName}</p>
        </div>
      </div>

      <button className="wide-button" onClick={onRefresh} disabled={loading}>
        <RefreshCw size={16} />
        Aggiorna stato
      </button>

      <section className="dataset-section">
        <div className="sidebar-heading">Raccolte dati</div>
        <div className="dataset-list">
          {datasets.map((dataset) => (
            <div
              key={dataset.id}
              className={activeDatasetId === dataset.id ? "dataset-card active" : "dataset-card"}
            >
              <button className="dataset-select" onClick={() => onSelectDataset(dataset.id)}>
                <div className="dataset-topline">
                  <strong>{dataset.name}</strong>
                  <span>{dataset.initialized ? "pronto" : "vuoto"}</span>
                </div>
                <p>{dataset.description}</p>
                <div className="dataset-meta">
                  <span>{dataset.schemaName}</span>
                  <span>~{formatRowEstimate(dataset.estimatedRows)} righe</span>
                  <span>{dataset.tableCount} tabelle</span>
                </div>
              </button>
              <button
                className="dataset-action"
                onClick={() => onInitializeDataset(dataset.id)}
                disabled={initializingDatasetId === dataset.id}
              >
                <RefreshCw size={14} />
                {dataset.initialized ? "Rigenera" : "Inizializza"}
              </button>
            </div>
          ))}
        </div>
      </section>

      <div className="schema-header dataset-summary">
        <div className="sidebar-heading">Schema attivo</div>
        <small>{activeDatasetSchema ?? "nessuno"}</small>
      </div>

      <div className="sidebar-empty">
        La selezione delle tabelle ora vive nelle pagine operative, accanto a colonne, filtri e risultati.
      </div>
    </aside>
  );
}
