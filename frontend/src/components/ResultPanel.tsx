import { AlertTriangle, Rows3 } from "lucide-react";

import type { SqlResult } from "../types";
import { formatResultColumn } from "../utils";

type ResultPanelProps = {
  result: SqlResult | null;
  error: string | null;
  notice: string | null;
  title?: string;
};

function extractExplainHeadline(result: SqlResult): string | null {
  if (result.classification.statementType !== "EXPLAIN" || result.rows.length === 0) {
    return null;
  }

  const root = result.rows[0]?.["QUERY PLAN"];
  if (!Array.isArray(root) || root.length === 0) {
    return null;
  }

  const plan = root[0]?.Plan;
  if (!plan || typeof plan !== "object") {
    return null;
  }

  const nodeType = typeof plan["Node Type"] === "string" ? plan["Node Type"] : "Plan";
  const relationName =
    typeof plan["Relation Name"] === "string" ? ` su ${plan["Relation Name"]}` : "";
  return `${nodeType}${relationName}`;
}

export function ResultPanel({ result, error, notice, title = "Risultato" }: ResultPanelProps) {
  if (error) {
    return (
      <section className="workspace-card result-shell error-state">
        <div className="section-title">
          <AlertTriangle size={18} />
          <h2>Errore</h2>
        </div>
        <pre>{error}</pre>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="workspace-card result-shell empty-state">
        <Rows3 size={22} />
        <p>{notice ?? "Esegui una query o seleziona una tabella per vedere i risultati."}</p>
      </section>
    );
  }

  const explainHeadline = extractExplainHeadline(result);

  return (
    <section className="workspace-card result-shell">
      <div className="section-title split">
        <div>
          <p className="section-kicker">Output</p>
          <h2>{title}</h2>
        </div>
        <div className="result-meta">
          <span>{result.commandTag ?? result.classification.statementType}</span>
          <span>{result.rowCount} righe</span>
          <span>{result.durationMs} ms</span>
          {result.affectedRows !== null && <span>{result.affectedRows} affette</span>}
        </div>
      </div>

      {notice && <div className="notice-banner">{notice}</div>}
      {explainHeadline && (
        <div className="explain-banner">
          <strong>Explain plan</strong>
          <span>{explainHeadline}</span>
        </div>
      )}

      <div className="table-scroll">
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
            {result.rows.map((row, index) => (
              <tr key={index}>
                {result.columns.map((column) => (
                  <td key={column}>{String(row[column] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details>
        <summary>JSON raw</summary>
        <pre>{JSON.stringify(result.rows, null, 2)}</pre>
      </details>
    </section>
  );
}
