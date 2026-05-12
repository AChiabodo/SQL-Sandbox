import { AlertTriangle, Rows3 } from "lucide-react";

import type { SqlResult } from "../types";
import { formatResultColumn } from "../utils";

type ResultPanelProps = {
  result: SqlResult | null;
  error: string | null;
  notice: string | null;
  title?: string;
};

type ExplainPlanNode = Record<string, unknown> & {
  Plans?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function extractExplainPlans(value: unknown): ExplainPlanNode[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const plans = value
    .map((item) => {
      if (!isRecord(item) || !isRecord(item.Plan)) {
        return null;
      }
      return item.Plan as ExplainPlanNode;
    })
    .filter((plan): plan is ExplainPlanNode => plan !== null);

  return plans.length ? plans : null;
}

function describeExplainNode(plan: ExplainPlanNode): string {
  const nodeType = typeof plan["Node Type"] === "string" ? plan["Node Type"] : "Plan";
  const joinType = typeof plan["Join Type"] === "string" ? ` (${plan["Join Type"]})` : "";
  const relationName =
    typeof plan["Relation Name"] === "string" ? ` on ${plan["Relation Name"]}` : "";
  const rows = typeof plan["Plan Rows"] === "number" ? ` | rows ${plan["Plan Rows"]}` : "";
  const cost =
    typeof plan["Total Cost"] === "number" ? ` | cost ${plan["Total Cost"].toFixed(2)}` : "";
  return `${nodeType}${joinType}${relationName}${rows}${cost}`;
}

function formatExplainTree(plan: ExplainPlanNode, depth = 0): string[] {
  const indent = "  ".repeat(depth);
  const linePrefix = depth === 0 ? "" : "- ";
  const lines = [`${indent}${linePrefix}${describeExplainNode(plan)}`];
  const children = Array.isArray(plan.Plans)
    ? plan.Plans.filter(isRecord).map((child) => child as ExplainPlanNode)
    : [];

  children.forEach((child) => {
    lines.push(...formatExplainTree(child, depth + 1));
  });

  return lines;
}

function renderResultCell(value: unknown, column: string, result: SqlResult) {
  if (
    result.classification.statementType === "EXPLAIN" &&
    column === "QUERY PLAN"
  ) {
    const plans = extractExplainPlans(value);
    if (plans) {
      return (
        <div className="explain-plan-tree">
          <pre>{plans.flatMap((plan) => formatExplainTree(plan)).join("\n")}</pre>
        </div>
      );
    }
  }

  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return (
    <div className="result-json-cell">
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function extractExplainHeadline(result: SqlResult): string | null {
  if (result.classification.statementType !== "EXPLAIN" || result.rows.length === 0) {
    return null;
  }

  const plans = extractExplainPlans(result.rows[0]?.["QUERY PLAN"]);
  if (!plans?.length) {
    return null;
  }

  const plan = plans[0];
  const nodeType = typeof plan["Node Type"] === "string" ? plan["Node Type"] : "Plan";
  const relationName =
    typeof plan["Relation Name"] === "string" ? ` on ${plan["Relation Name"]}` : "";
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
                  <td key={column}>{renderResultCell(row[column], column, result)}</td>
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
