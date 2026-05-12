import { Rows3, Table2 } from "lucide-react";

import type { SchemaInfo, TableInfo } from "../types";

type TablePickerProps = {
  schemas: SchemaInfo[];
  selectedTable: { schemaName: string; table: TableInfo } | null;
  onSelectTable: (schemaName: string, table: TableInfo) => void;
  title?: string;
  description?: string;
};

function tableValue(schemaName: string, tableName: string) {
  return `${schemaName}::${tableName}`;
}

export function TablePicker({
  schemas,
  selectedTable,
  onSelectTable,
  title = "Tabella di lavoro",
  description = "Scegli la tabella nel punto in cui costruisci o lanci la query."
}: TablePickerProps) {
  const tables = schemas.flatMap((schema) =>
    schema.tables.map((table) => ({
      schemaName: schema.name,
      table
    }))
  );

  const selectedValue = selectedTable
    ? tableValue(selectedTable.schemaName, selectedTable.table.name)
    : "";

  const handleChange = (value: string) => {
    const next = tables.find((item) => tableValue(item.schemaName, item.table.name) === value);
    if (next) {
      onSelectTable(next.schemaName, next.table);
    }
  };

  return (
    <div className="table-picker">
      <div className="table-picker-heading">
        <div className="section-title compact">
          <Table2 size={18} />
          <h2>{title}</h2>
        </div>
        <p className="muted">{description}</p>
      </div>

      <label className="table-select-control">
        <span>Tabella</span>
        <select
          value={selectedValue}
          onChange={(event) => handleChange(event.target.value)}
          disabled={tables.length === 0}
        >
          {tables.length === 0 ? (
            <option>Nessuna tabella disponibile</option>
          ) : (
            tables.map(({ schemaName, table }) => (
              <option key={tableValue(schemaName, table.name)} value={tableValue(schemaName, table.name)}>
                {schemaName}.{table.name}
              </option>
            ))
          )}
        </select>
      </label>

      <div className="table-picker-meta">
        <span>{tables.length} tabelle disponibili</span>
        <Rows3 size={14} />
        <span>
          {selectedTable
            ? `${selectedTable.table.columns.length} colonne nella tabella selezionata`
            : "Nessuna tabella selezionata"}
        </span>
      </div>
    </div>
  );
}
