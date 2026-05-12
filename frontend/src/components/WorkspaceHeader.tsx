import { Braces, Database, LayoutDashboard, MessageSquareText, Rows3, Table2 } from "lucide-react";

import type { DatasetCatalogItem, WorkspaceMode } from "../types";
import { modeLabel } from "../utils";

type WorkspaceHeaderProps = {
  activeMode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  activeDataset: DatasetCatalogItem | null;
  selectedTableLabel: string;
};

const modeConfig: { mode: WorkspaceMode; icon: typeof Braces }[] = [
  { mode: "sql", icon: Braces },
  { mode: "lowcode", icon: Database },
  { mode: "dashboard", icon: LayoutDashboard },
  { mode: "tables", icon: Table2 },
  { mode: "llm", icon: MessageSquareText }
];

export function WorkspaceHeader({
  activeMode,
  onModeChange,
  activeDataset,
  selectedTableLabel
}: WorkspaceHeaderProps) {
  return (
    <header className="workspace-header">
      <div className="workspace-header-main">
        <div className="workspace-heading">
          <p className="eyeline">Sandbox locale</p>
          <h2>{modeLabel(activeMode)}</h2>
        </div>
        <p className="workspace-context">
          <span>{activeDataset?.name ?? "Nessuna raccolta"}</span>
          <Rows3 size={14} />
          <span>{selectedTableLabel}</span>
        </p>
      </div>

      <nav className="mode-tabs" role="tablist" aria-label="Modalita workspace">
        {modeConfig.map(({ mode, icon: Icon }) => (
          <button
            key={mode}
            className={activeMode === mode ? "mode-tab active" : "mode-tab"}
            onClick={() => onModeChange(mode)}
            role="tab"
            aria-selected={activeMode === mode}
          >
            <Icon size={16} />
            {modeLabel(mode)}
          </button>
        ))}
      </nav>
    </header>
  );
}
