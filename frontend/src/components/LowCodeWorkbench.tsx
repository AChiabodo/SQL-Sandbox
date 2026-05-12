import { Braces, Database, FlaskConical, Play, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ResultPanel } from "./ResultPanel";
import type {
  BuilderJoinSpec,
  BuilderState,
  ColumnInfo,
  ColumnRef,
  RelationshipInfo,
  SchemaInfo,
  SqlResult,
  TableInfo
} from "../types";
import { formatColumnRef, humanizeIdentifier } from "../utils";

type LowCodeWorkbenchProps = {
  schemas: SchemaInfo[];
  relationships: RelationshipInfo[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  builder: BuilderState;
  compiledSql: string;
  loading: boolean;
  result: SqlResult | null;
  error: string | null;
  notice: string | null;
  onSelectTable: (schemaName: string, table: TableInfo) => void;
  onBuilderChange: (next: BuilderState) => void;
  onCompile: () => Promise<void>;
  onExecute: () => Promise<void>;
};

type ColumnOption = {
  ref: ColumnRef;
  column: ColumnInfo;
};

type TableOption = {
  schemaName: string;
  table: TableInfo;
};

const filterOperators = ["=", "!=", ">", ">=", "<", "<=", "LIKE", "ILIKE", "IN", "BETWEEN", "IS NULL", "IS NOT NULL"];
const aggregationFunctions = ["count", "sum", "avg", "min", "max"];

function columnValue(ref: ColumnRef): string {
  return `${ref.schemaName}.${ref.tableName}.${ref.columnName}`;
}

function tableValue(schemaName: string, tableName: string): string {
  return `${schemaName}.${tableName}`;
}

function sameColumn(left: ColumnRef | null | undefined, right: ColumnRef | null | undefined): boolean {
  return Boolean(
    left &&
      right &&
      left.schemaName === right.schemaName &&
      left.tableName === right.tableName &&
      left.columnName === right.columnName
  );
}

function toggleColumn(list: ColumnRef[], value: ColumnRef): ColumnRef[] {
  return list.some((item) => sameColumn(item, value))
    ? list.filter((item) => !sameColumn(item, value))
    : [...list, value];
}

function tableLabel(ref: ColumnRef): string {
  return `${ref.schemaName}.${ref.tableName}`;
}

function getTables(schemas: SchemaInfo[]): TableOption[] {
  return schemas.flatMap((schema) => schema.tables.map((table) => ({ schemaName: schema.name, table })));
}

function getColumnOptions(schemas: SchemaInfo[]): ColumnOption[] {
  return schemas.flatMap((schema) =>
    schema.tables.flatMap((table) =>
      table.columns.map((column) => ({
        ref: { schemaName: schema.name, tableName: table.name, columnName: column.name },
        column
      }))
    )
  );
}

function findColumn(options: ColumnOption[], value: string): ColumnRef | null {
  return options.find((item) => columnValue(item.ref) === value)?.ref ?? null;
}

function findColumnMeta(options: ColumnOption[], ref: ColumnRef | null | undefined): ColumnInfo | undefined {
  return options.find((item) => sameColumn(item.ref, ref))?.column;
}

function selectedTables(builder: BuilderState): Set<string> {
  const tables = new Set<string>();
  builder.columns.forEach((item) => tables.add(tableLabel(item)));
  builder.groupBy.forEach((item) => tables.add(tableLabel(item)));
  builder.filters.forEach((item) => {
    if (item.column) tables.add(tableLabel(item.column));
  });
  builder.aggregations.forEach((item) => {
    if (item.column !== "*") tables.add(tableLabel(item.column));
  });
  builder.joins.forEach((join) => {
    if (join.left) tables.add(tableLabel(join.left));
    if (join.right) tables.add(tableLabel(join.right));
  });
  return tables;
}

function matchesColumn(item: ColumnOption, search: string): boolean {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return true;
  return `${item.ref.columnName} ${item.ref.tableName} ${item.column.dataType}`.toLowerCase().includes(normalized);
}

function tableDisplay(table: TableOption): string {
  return `${humanizeIdentifier(table.table.name)} (${table.schemaName})`;
}

function EnhancedTablePicker({
  tables,
  selectedTable,
  onSelectTable
}: {
  tables: TableOption[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  onSelectTable: (schemaName: string, table: TableInfo) => void;
}) {
  const [search, setSearch] = useState("");
  const selected = selectedTable ? tableValue(selectedTable.schemaName, selectedTable.table.name) : "";
  const filtered = tables.filter((item) =>
    `${item.schemaName} ${item.table.name} ${humanizeIdentifier(item.table.name)}`.toLowerCase().includes(search.toLowerCase())
  );
  const visibleTables = filtered.length > 0 ? filtered : tables;

  return (
    <div className="lowcode-table-picker">
      <label className="search-control">
        <Search size={15} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Cerca tabella, es. vendite, customer, invoices"
        />
      </label>
      <label className="table-select-control">
        <span>Tabella base</span>
        <select
          value={selected}
          onChange={(event) => {
            const next = tables.find((item) => tableValue(item.schemaName, item.table.name) === event.target.value);
            if (next) onSelectTable(next.schemaName, next.table);
          }}
          disabled={tables.length === 0}
        >
          {visibleTables.map((item) => (
            <option key={tableValue(item.schemaName, item.table.name)} value={tableValue(item.schemaName, item.table.name)}>
              {tableDisplay(item)} · {item.table.columns.length} colonne
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function ColumnToken({
  ref,
  column,
  active,
  onClick
}: {
  ref: ColumnRef;
  column: ColumnInfo;
  active: boolean;
  onClick: () => void;
}) {
  const formatted = formatColumnRef(ref, column.dataType);
  return (
    <button className={active ? "column-token active" : "column-token"} onClick={onClick} title={formatted.technical}>
      <strong>{formatted.label}</strong>
      <small>{formatted.context}</small>
    </button>
  );
}

function ColumnSelectionPanel({
  title,
  description,
  tables,
  columns,
  selectedTable,
  selectedColumns,
  onToggle
}: {
  title: string;
  description: string;
  tables: TableOption[];
  columns: ColumnOption[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  selectedColumns: ColumnRef[];
  onToggle: (ref: ColumnRef) => void;
}) {
  const defaultScope = selectedTable
    ? tableValue(selectedTable.schemaName, selectedTable.table.name)
    : tables[0]
      ? tableValue(tables[0].schemaName, tables[0].table.name)
      : "";
  const [scope, setScope] = useState(defaultScope);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (defaultScope && !tables.some((item) => tableValue(item.schemaName, item.table.name) === scope)) {
      setScope(defaultScope);
    }
  }, [defaultScope, scope, tables]);

  const scopedColumns = columns.filter((item) => tableValue(item.ref.schemaName, item.ref.tableName) === scope);
  const visibleColumns = scopedColumns.filter((item) => matchesColumn(item, search));

  return (
    <section className="builder-stack-card column-selector-panel">
      <div className="row-header">
        <span>{title}</span>
        <span className="count-badge">{selectedColumns.length}</span>
      </div>
      <p className="helper-copy">{description}</p>
      <div className="selector-toolbar">
        <select value={scope} onChange={(event) => setScope(event.target.value)} disabled={tables.length === 0}>
          {tables.map((item) => (
            <option key={tableValue(item.schemaName, item.table.name)} value={tableValue(item.schemaName, item.table.name)}>
              {tableDisplay(item)}
            </option>
          ))}
        </select>
        <label className="search-control compact-search">
          <Search size={15} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cerca campo o tipo"
          />
        </label>
      </div>
      <div className="column-token-grid">
        {visibleColumns.map(({ ref, column }) => (
          <ColumnToken
            key={columnValue(ref)}
            ref={ref}
            column={column}
            active={selectedColumns.some((item) => sameColumn(item, ref))}
            onClick={() => onToggle(ref)}
          />
        ))}
        {visibleColumns.length === 0 && <div className="ghost-row">Nessun campo trovato per questa ricerca.</div>}
      </div>
      {selectedColumns.length > 0 && (
        <div className="selected-column-strip">
          {selectedColumns.map((ref) => {
            const formatted = formatColumnRef(ref, findColumnMeta(columns, ref)?.dataType);
            return (
              <button key={columnValue(ref)} className="selected-chip" onClick={() => onToggle(ref)} title={formatted.technical}>
                {formatted.label}
                <X size={13} />
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function CompactColumnSelect({
  value,
  tables,
  columns,
  includeStar = false,
  placeholder = "Seleziona colonna",
  onChange
}: {
  value: ColumnRef | "*" | null;
  tables: TableOption[];
  columns: ColumnOption[];
  includeStar?: boolean;
  placeholder?: string;
  onChange: (value: ColumnRef | "*") => void;
}) {
  const valueTable =
    value && value !== "*"
      ? tableValue(value.schemaName, value.tableName)
      : tables[0]
        ? tableValue(tables[0].schemaName, tables[0].table.name)
        : "";
  const [scope, setScope] = useState(valueTable);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (value && value !== "*") {
      setScope(tableValue(value.schemaName, value.tableName));
    }
  }, [value]);

  const scopedColumns = columns.filter((item) => tableValue(item.ref.schemaName, item.ref.tableName) === scope);
  const visibleColumns = scopedColumns.filter((item) => matchesColumn(item, search));
  const selectedValue = value === "*" ? "*" : value ? columnValue(value) : "";

  return (
    <div className="compact-column-select">
      <select value={scope} onChange={(event) => setScope(event.target.value)} disabled={tables.length === 0}>
        {tables.map((item) => (
          <option key={tableValue(item.schemaName, item.table.name)} value={tableValue(item.schemaName, item.table.name)}>
            {humanizeIdentifier(item.table.name)}
          </option>
        ))}
      </select>
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Cerca campo" />
      <select
        value={selectedValue}
        onChange={(event) => {
          if (event.target.value === "*") {
            onChange("*");
            return;
          }
          const next = findColumn(columns, event.target.value);
          if (next) onChange(next);
        }}
      >
        {!value && <option value="">{placeholder}</option>}
        {includeStar && <option value="*">Tutte le righe (*)</option>}
        {visibleColumns.map(({ ref, column }) => {
          const formatted = formatColumnRef(ref, column.dataType);
          return (
            <option key={columnValue(ref)} value={columnValue(ref)}>
              {formatted.label} · {column.dataType}
            </option>
          );
        })}
      </select>
    </div>
  );
}

function defaultManualJoin(
  selectedTable: { schemaName: string; table: TableInfo } | null,
  relationships: RelationshipInfo[],
  columns: ColumnOption[]
): BuilderJoinSpec {
  if (!selectedTable) {
    return { joinType: "inner", left: columns[0]?.ref ?? null, right: columns[1]?.ref ?? null };
  }

  const baseSchema = selectedTable.schemaName;
  const baseTable = selectedTable.table.name;
  const relationship = relationships.find(
    (item) =>
      (item.fromSchemaName === baseSchema && item.fromTableName === baseTable) ||
      (item.toSchemaName === baseSchema && item.toTableName === baseTable)
  );

  if (relationship) {
    return {
      joinType: "inner",
      left: {
        schemaName: relationship.fromSchemaName,
        tableName: relationship.fromTableName,
        columnName: relationship.fromColumnName
      },
      right: {
        schemaName: relationship.toSchemaName,
        tableName: relationship.toTableName,
        columnName: relationship.toColumnName
      }
    };
  }

  const baseColumn = columns.find(
    (item) => item.ref.schemaName === baseSchema && item.ref.tableName === baseTable
  )?.ref;
  const otherColumn = columns.find(
    (item) => item.ref.schemaName !== baseSchema || item.ref.tableName !== baseTable
  )?.ref;
  return { joinType: "inner", left: baseColumn ?? null, right: otherColumn ?? null };
}

function SelectionCard({
  tables,
  relationships,
  selectedTable,
  columns,
  builder,
  onSelectTable,
  onBuilderChange
}: {
  tables: TableOption[];
  relationships: RelationshipInfo[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  columns: ColumnOption[];
  builder: BuilderState;
  onSelectTable: (schemaName: string, table: TableInfo) => void;
  onBuilderChange: (next: BuilderState) => void;
}) {
  const tablesInUse = selectedTables(builder);
  const selectedTableTitle = selectedTable ? humanizeIdentifier(selectedTable.table.name) : "Nessuna tabella";

  return (
    <section className="workspace-card data-selection-card">
      <div className="section-title">
        <FlaskConical size={18} />
        <h2>Seleziona dati</h2>
      </div>
      <EnhancedTablePicker tables={tables} selectedTable={selectedTable} onSelectTable={onSelectTable} />
      <div className="query-summary-grid">
        <div>
          <span>Base</span>
          <strong>{selectedTableTitle}</strong>
          <small>{selectedTable ? `${selectedTable.schemaName}.${selectedTable.table.name}` : "Scegli una tabella"}</small>
        </div>
        <div>
          <span>Select</span>
          <strong>{builder.columns.length > 0 ? builder.columns.length : "tutte"}</strong>
          <small>colonne in output</small>
        </div>
        <div>
          <span>Group by</span>
          <strong>{builder.groupBy.length}</strong>
          <small>dimensioni</small>
        </div>
        <div>
          <span>Join</span>
          <strong>{builder.joins.length || "auto"}</strong>
          <small>{tablesInUse.size || 1} tabelle coinvolte · {relationships.length} FK</small>
        </div>
      </div>
      <ColumnSelectionPanel
        title="Select"
        description="Scegli una tabella, cerca i campi e aggiungili all'output senza scorrere l'intero schema."
        tables={tables}
        columns={columns}
        selectedTable={selectedTable}
        selectedColumns={builder.columns}
        onToggle={(ref) => onBuilderChange({ ...builder, columns: toggleColumn(builder.columns, ref) })}
      />
    </section>
  );
}

export function LowCodeWorkbench({
  schemas,
  relationships,
  selectedTable,
  builder,
  compiledSql,
  loading,
  result,
  error,
  notice,
  onSelectTable,
  onBuilderChange,
  onCompile,
  onExecute
}: LowCodeWorkbenchProps) {
  const allColumns = useMemo(() => getColumnOptions(schemas), [schemas]);
  const tables = useMemo(() => getTables(schemas), [schemas]);

  return (
    <div className="mode-layout lowcode-layout">
      <div className="lowcode-main-column">
        <SelectionCard
          tables={tables}
          relationships={relationships}
          selectedTable={selectedTable}
          columns={allColumns}
          builder={builder}
          onSelectTable={onSelectTable}
          onBuilderChange={onBuilderChange}
        />

        <section className="workspace-card builder-flow-card">
          <div className="section-title split">
            <div>
              <p className="section-kicker">Componi la query</p>
              <h2>Filtri, join e trasformazioni</h2>
            </div>
            <div className="toolbar-actions">
              <button onClick={() => void onCompile()} disabled={!selectedTable}>
                <Braces size={16} />
                Anteprima SQL
              </button>
              <button className="primary" onClick={() => void onExecute()} disabled={!selectedTable || loading}>
                <Play size={16} />
                Esegui
              </button>
            </div>
          </div>

          <div className="builder-grid">
            <ColumnSelectionPanel
              title="Group by"
              description="Raggruppa per dimensioni leggibili scegliendo prima la tabella e poi i campi."
              tables={tables}
              columns={allColumns}
              selectedTable={selectedTable}
              selectedColumns={builder.groupBy}
              onToggle={(ref) => onBuilderChange({ ...builder, groupBy: toggleColumn(builder.groupBy, ref) })}
            />

            <section className="builder-stack-card">
              <div className="row-header">
                <span>Filtri</span>
                <button
                  onClick={() =>
                    onBuilderChange({
                      ...builder,
                      filters: [
                        ...builder.filters,
                        { column: allColumns[0]?.ref ?? null, operator: "=", value: "", valueTo: "" }
                      ]
                    })
                  }
                >
                  <Plus size={16} />
                </button>
              </div>
              <p className="helper-copy">Definisci condizioni usando colonne da qualsiasi tabella collegata.</p>
              {builder.filters.length === 0 ? (
                <div className="ghost-row">Nessun filtro attivo.</div>
              ) : (
                builder.filters.map((filter, index) => (
                  <div className="builder-row-card" key={`filter-${index}`}>
                    <div className="builder-row-grid readable-builder-row">
                      <CompactColumnSelect
                        value={filter.column}
                        tables={tables}
                        columns={allColumns}
                        onChange={(value) => {
                          if (value === "*") return;
                          const next = [...builder.filters];
                          next[index] = { ...filter, column: value };
                          onBuilderChange({ ...builder, filters: next });
                        }}
                      />
                      <select
                        value={filter.operator}
                        onChange={(event) => {
                          const next = [...builder.filters];
                          next[index] = { ...filter, operator: event.target.value };
                          onBuilderChange({ ...builder, filters: next });
                        }}
                      >
                        {filterOperators.map((operator) => (
                          <option key={operator}>{operator}</option>
                        ))}
                      </select>
                      <input
                        placeholder="Valore"
                        value={filter.value}
                        onChange={(event) => {
                          const next = [...builder.filters];
                          next[index] = { ...filter, value: event.target.value };
                          onBuilderChange({ ...builder, filters: next });
                        }}
                      />
                      <button
                        className="icon-button"
                        onClick={() =>
                          onBuilderChange({
                            ...builder,
                            filters: builder.filters.filter((_, itemIndex) => itemIndex !== index)
                          })
                        }
                      >
                        <X size={15} />
                      </button>
                    </div>
                    {filter.operator === "BETWEEN" && (
                      <input
                        placeholder="Valore finale"
                        value={filter.valueTo}
                        onChange={(event) => {
                          const next = [...builder.filters];
                          next[index] = { ...filter, valueTo: event.target.value };
                          onBuilderChange({ ...builder, filters: next });
                        }}
                      />
                    )}
                  </div>
                ))
              )}
            </section>

            <section className="builder-stack-card">
              <div className="row-header">
                <span>Aggregazioni</span>
                <button
                  onClick={() =>
                    onBuilderChange({
                      ...builder,
                      aggregations: [
                        ...builder.aggregations,
                        { function: "count", column: "*", alias: "count_all" }
                      ]
                    })
                  }
                >
                  <Plus size={16} />
                </button>
              </div>
              <p className="helper-copy">Somma, conta o calcola medie con campi cercabili e nomi leggibili.</p>
              {builder.aggregations.length === 0 ? (
                <div className="ghost-row">Nessuna aggregazione attiva.</div>
              ) : (
                builder.aggregations.map((aggregation, index) => (
                  <div className="builder-row-card" key={`aggregation-${index}`}>
                    <div className="builder-row-grid readable-builder-row">
                      <select
                        value={aggregation.function}
                        onChange={(event) => {
                          const next = [...builder.aggregations];
                          next[index] = { ...aggregation, function: event.target.value };
                          onBuilderChange({ ...builder, aggregations: next });
                        }}
                      >
                        {aggregationFunctions.map((fn) => (
                          <option key={fn}>{fn}</option>
                        ))}
                      </select>
                      <CompactColumnSelect
                        value={aggregation.column}
                        tables={tables}
                        columns={allColumns}
                        includeStar
                        onChange={(value) => {
                          const next = [...builder.aggregations];
                          next[index] = { ...aggregation, column: value };
                          onBuilderChange({ ...builder, aggregations: next });
                        }}
                      />
                      <input
                        placeholder="Alias leggibile"
                        value={aggregation.alias}
                        onChange={(event) => {
                          const next = [...builder.aggregations];
                          next[index] = { ...aggregation, alias: event.target.value };
                          onBuilderChange({ ...builder, aggregations: next });
                        }}
                      />
                      <button
                        className="icon-button"
                        onClick={() =>
                          onBuilderChange({
                            ...builder,
                            aggregations: builder.aggregations.filter((_, itemIndex) => itemIndex !== index)
                          })
                        }
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </section>

            <section className="builder-stack-card">
              <div className="row-header">
                <span>Join manuali</span>
                <button
                  onClick={() =>
                    onBuilderChange({
                      ...builder,
                      joins: [...builder.joins, defaultManualJoin(selectedTable, relationships, allColumns)]
                    })
                  }
                >
                  <Plus size={16} />
                </button>
              </div>
              <p className="helper-copy">
                Opzionale: usa questo blocco quando il percorso automatico e ambiguo o vuoi una LEFT JOIN.
              </p>
              {builder.joins.length === 0 ? (
                <div className="ghost-row">Nessuna join manuale. Verranno usate le FK disponibili.</div>
              ) : (
                builder.joins.map((join, index) => (
                  <div className="builder-row-card" key={`join-${index}`}>
                    <div className="manual-join-grid readable-join-grid">
                      <select
                        value={join.joinType}
                        onChange={(event) => {
                          const next = [...builder.joins];
                          next[index] = { ...join, joinType: event.target.value as "inner" | "left" };
                          onBuilderChange({ ...builder, joins: next });
                        }}
                      >
                        <option value="inner">INNER JOIN</option>
                        <option value="left">LEFT JOIN</option>
                      </select>
                      <CompactColumnSelect
                        value={join.left}
                        tables={tables}
                        columns={allColumns}
                        onChange={(value) => {
                          if (value === "*") return;
                          const next = [...builder.joins];
                          next[index] = { ...join, left: value };
                          onBuilderChange({ ...builder, joins: next });
                        }}
                      />
                      <span className="join-equals">=</span>
                      <CompactColumnSelect
                        value={join.right}
                        tables={tables}
                        columns={allColumns}
                        onChange={(value) => {
                          if (value === "*") return;
                          const next = [...builder.joins];
                          next[index] = { ...join, right: value };
                          onBuilderChange({ ...builder, joins: next });
                        }}
                      />
                      <button
                        className="icon-button"
                        onClick={() =>
                          onBuilderChange({
                            ...builder,
                            joins: builder.joins.filter((_, itemIndex) => itemIndex !== index)
                          })
                        }
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </section>

            <section className="builder-stack-card">
              <div className="section-title compact">
                <h2>Order by</h2>
              </div>
              <p className="helper-copy">Ordina per alias generato o alias di aggregazione.</p>
              <div className="builder-row-grid order-grid">
                <input
                  placeholder="Alias, es. dim_customer_country_code"
                  value={builder.orderBy[0]?.expression ?? ""}
                  onChange={(event) =>
                    onBuilderChange({
                      ...builder,
                      orderBy: [
                        {
                          expression: event.target.value,
                          direction: builder.orderBy[0]?.direction ?? "asc"
                        }
                      ]
                    })
                  }
                />
                <select
                  value={builder.orderBy[0]?.direction ?? "asc"}
                  onChange={(event) =>
                    onBuilderChange({
                      ...builder,
                      orderBy: [
                        {
                          expression: builder.orderBy[0]?.expression ?? "",
                          direction: event.target.value as "asc" | "desc"
                        }
                      ]
                    })
                  }
                >
                  <option value="asc">ascendente</option>
                  <option value="desc">discendente</option>
                </select>
              </div>
              <div className="form-grid">
                <label>
                  Limit
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={builder.limit}
                    onChange={(event) => onBuilderChange({ ...builder, limit: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Offset
                  <input
                    type="number"
                    min={0}
                    value={builder.offset}
                    onChange={(event) => onBuilderChange({ ...builder, offset: Number(event.target.value) })}
                  />
                </label>
              </div>
            </section>
          </div>
        </section>

        <details className="workspace-card sql-preview-card">
          <summary className="disclosure-summary">
            <span>
              <Braces size={18} />
              SQL generato
            </span>
            <small>
              {compiledSql
                ? `${builder.joins.length} join manuali`
                : `${relationships.length} FK disponibili`}
            </small>
          </summary>
          {compiledSql ? (
            <pre className="compiled preview-sql">{compiledSql}</pre>
          ) : (
            <p className="muted">
              Compila la query per vedere l'SQL risultante, incluse le join automatiche o manuali.
            </p>
          )}
        </details>

        <ResultPanel result={result} error={error} notice={notice} title="Preview risultato" />
      </div>
    </div>
  );
}
