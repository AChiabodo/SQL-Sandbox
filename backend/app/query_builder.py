import re
from collections import deque
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.models import (
    AggregationSpec,
    ColumnRef,
    CompiledQuery,
    JoinSpec,
    QueryBuilderRequest,
    RelationshipSpec,
    TableRef,
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise HTTPException(status_code=400, detail=f"Invalid identifier: {identifier}")
    return f'"{identifier}"'


@dataclass(frozen=True)
class TableKey:
    schema: str
    table: str


@dataclass(frozen=True)
class JoinEdge:
    left: ColumnRef
    right: ColumnRef
    join_type: str
    source: str


def table_key(ref: TableRef | ColumnRef) -> TableKey:
    if isinstance(ref, TableRef):
        return TableKey(ref.schemaName, ref.tableName)
    return TableKey(ref.schemaName, ref.tableName)


def normalize_column(column: ColumnRef | str, base_table: TableRef) -> ColumnRef:
    if isinstance(column, ColumnRef):
        return column
    return ColumnRef(
        schemaName=base_table.schemaName,
        tableName=base_table.tableName,
        columnName=column,
    )


def relationship_to_edge(relationship: RelationshipSpec) -> JoinEdge:
    return JoinEdge(
        left=ColumnRef(
            schemaName=relationship.fromSchemaName,
            tableName=relationship.fromTableName,
            columnName=relationship.fromColumnName,
        ),
        right=ColumnRef(
            schemaName=relationship.toSchemaName,
            tableName=relationship.toTableName,
            columnName=relationship.toColumnName,
        ),
        join_type="inner",
        source="auto",
    )


def manual_join_to_edge(join: JoinSpec) -> JoinEdge:
    return JoinEdge(left=join.left, right=join.right, join_type=join.joinType, source="manual")


def has_qualified_inputs(spec: QueryBuilderRequest) -> bool:
    values: list[Any] = [*spec.columns, *spec.groupBy]
    values.extend(item.column for item in spec.filters)
    values.extend(item.column for item in spec.aggregations if item.column not in (None, "*"))
    values.extend(item.expression for item in spec.orderBy)
    return any(isinstance(value, ColumnRef) for value in values) or bool(spec.joins or spec.relationships)


def alias_for_aggregation(aggregation: AggregationSpec) -> str:
    if aggregation.alias:
        return aggregation.alias
    if aggregation.function == "count" and aggregation.column in (None, "*"):
        return "count_all"
    if isinstance(aggregation.column, ColumnRef):
        return f"{aggregation.function}_{aggregation.column.tableName}_{aggregation.column.columnName}"
    return f"{aggregation.function}_{aggregation.column}"


def compile_legacy_query(spec: QueryBuilderRequest) -> CompiledQuery:
    schema = quote_identifier(spec.table.schemaName)
    table = quote_identifier(spec.table.tableName)
    params: list[Any] = []

    selected: list[str] = []
    for column in spec.columns:
        selected.append(quote_identifier(column))

    for aggregation in spec.aggregations:
        function = aggregation.function.upper()
        if aggregation.function == "count" and aggregation.column in (None, "*"):
            expression = "COUNT(*)"
        elif aggregation.column:
            expression = f"{function}({quote_identifier(aggregation.column)})"
        else:
            raise HTTPException(status_code=400, detail=f"{aggregation.function} requires a column")

        selected.append(f"{expression} AS {quote_identifier(alias_for_aggregation(aggregation))}")

    if not selected:
        selected.append("*")

    sql = f"SELECT {', '.join(selected)} FROM {schema}.{table}"

    where_clauses: list[str] = []
    for item in spec.filters:
        column = quote_identifier(item.column)
        operator = item.operator.upper()

        if operator in {"IS NULL", "IS NOT NULL"}:
            where_clauses.append(f"{column} {operator}")
        elif operator == "IN":
            if not isinstance(item.value, list) or len(item.value) == 0:
                raise HTTPException(status_code=400, detail="IN requires a non-empty array value")
            placeholders = ", ".join(["%s"] * len(item.value))
            where_clauses.append(f"{column} IN ({placeholders})")
            params.extend(item.value)
        elif operator == "BETWEEN":
            where_clauses.append(f"{column} BETWEEN %s AND %s")
            params.extend([item.value, item.valueTo])
        else:
            where_clauses.append(f"{column} {operator} %s")
            params.append(item.value)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    if spec.groupBy:
        sql += " GROUP BY " + ", ".join(quote_identifier(column) for column in spec.groupBy)

    if spec.orderBy:
        order_parts = [
            f"{quote_identifier(item.expression)} {item.direction.upper()}"
            for item in spec.orderBy
        ]
        sql += " ORDER BY " + ", ".join(order_parts)

    sql += " LIMIT %s OFFSET %s"
    params.extend([spec.limit, spec.offset])
    return CompiledQuery(sql=sql, params=params)


def qualified_column(ref: ColumnRef, aliases: dict[TableKey, str]) -> str:
    alias = aliases.get(table_key(ref))
    if alias is None:
        raise HTTPException(
            status_code=400,
            detail=f"Table {ref.schemaName}.{ref.tableName} is not part of the query",
        )
    return f"{alias}.{quote_identifier(ref.columnName)}"


def selected_alias(ref: ColumnRef) -> str:
    return quote_identifier(f"{ref.tableName}_{ref.columnName}")


def edge_tables(edge: JoinEdge) -> tuple[TableKey, TableKey]:
    return table_key(edge.left), table_key(edge.right)


def edge_key(edge: JoinEdge) -> tuple[str, str, str, str, str, str, str]:
    return (
        edge.left.schemaName,
        edge.left.tableName,
        edge.left.columnName,
        edge.right.schemaName,
        edge.right.tableName,
        edge.right.columnName,
        edge.join_type,
    )


def connected_tables(base: TableKey, edges: list[JoinEdge]) -> set[TableKey]:
    adjacency: dict[TableKey, list[TableKey]] = {}
    for edge in edges:
        left, right = edge_tables(edge)
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)

    seen = {base}
    queue: deque[TableKey] = deque([base])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen


def find_unique_shortest_path(
    start_tables: set[TableKey],
    target: TableKey,
    graph: dict[TableKey, list[JoinEdge]],
) -> list[JoinEdge]:
    queue: deque[tuple[TableKey, list[JoinEdge]]] = deque((table, []) for table in start_tables)
    visited_depth: dict[TableKey, int] = {table: 0 for table in start_tables}
    shortest_paths: list[list[JoinEdge]] = []
    shortest_length: int | None = None

    while queue:
        current, path = queue.popleft()
        if shortest_length is not None and len(path) > shortest_length:
            continue
        if current == target and path:
            shortest_length = len(path)
            shortest_paths.append(path)
            continue

        for edge in graph.get(current, []):
            left, right = edge_tables(edge)
            neighbor = right if current == left else left
            next_depth = len(path) + 1
            if shortest_length is not None and next_depth > shortest_length:
                continue
            if visited_depth.get(neighbor, next_depth) < next_depth:
                continue
            visited_depth[neighbor] = next_depth
            queue.append((neighbor, [*path, edge]))

    if not shortest_paths:
        raise HTTPException(
            status_code=400,
            detail=f"No foreign-key path found to table {target.schema}.{target.table}. Add a manual join.",
        )
    unique_edge_paths = {tuple(edge_key(edge) for edge in path) for path in shortest_paths}
    if len(unique_edge_paths) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Ambiguous foreign-key path to table {target.schema}.{target.table}. Add a manual join.",
        )
    return shortest_paths[0]


def resolve_join_edges(base: TableKey, required_tables: set[TableKey], spec: QueryBuilderRequest) -> list[JoinEdge]:
    selected_edges = [manual_join_to_edge(join) for join in spec.joins]
    edge_index = {edge_key(edge) for edge in selected_edges}

    relationship_edges = [relationship_to_edge(relationship) for relationship in spec.relationships]
    graph: dict[TableKey, list[JoinEdge]] = {}
    for edge in relationship_edges:
        left, right = edge_tables(edge)
        graph.setdefault(left, []).append(edge)
        graph.setdefault(right, []).append(edge)

    for join in selected_edges:
        required_tables.update(edge_tables(join))

    while True:
        connected = connected_tables(base, selected_edges)
        missing = sorted(required_tables - connected, key=lambda item: (item.schema, item.table))
        if not missing:
            return selected_edges

        path = find_unique_shortest_path(connected, missing[0], graph)
        for edge in path:
            key = edge_key(edge)
            if key not in edge_index:
                selected_edges.append(edge)
                edge_index.add(key)


def ordered_join_edges(base: TableKey, edges: list[JoinEdge]) -> list[JoinEdge]:
    pending = list(edges)
    joined = {base}
    ordered: list[JoinEdge] = []

    while pending:
        progress = False
        for edge in pending[:]:
            left, right = edge_tables(edge)
            if left in joined or right in joined:
                ordered.append(edge)
                joined.update([left, right])
                pending.remove(edge)
                progress = True
        if not progress:
            raise HTTPException(status_code=400, detail="Manual joins do not connect to the base table")
    return ordered


def compile_query(spec: QueryBuilderRequest) -> CompiledQuery:
    if not has_qualified_inputs(spec):
        return compile_legacy_query(spec)

    base = table_key(spec.table)
    params: list[Any] = []

    required_tables: set[TableKey] = {base}
    selected_refs = [normalize_column(column, spec.table) for column in spec.columns]
    filter_refs = [normalize_column(item.column, spec.table) for item in spec.filters]
    group_refs = [normalize_column(column, spec.table) for column in spec.groupBy]
    aggregation_refs = [
        normalize_column(item.column, spec.table)
        for item in spec.aggregations
        if item.column not in (None, "*")
    ]
    order_refs = [
        normalize_column(item.expression, spec.table)
        for item in spec.orderBy
        if isinstance(item.expression, ColumnRef)
    ]

    for ref in [*selected_refs, *filter_refs, *group_refs, *aggregation_refs, *order_refs]:
        required_tables.add(table_key(ref))

    join_edges = ordered_join_edges(base, resolve_join_edges(base, required_tables, spec))

    tables_in_order = [base]
    for edge in join_edges:
        for item in edge_tables(edge):
            if item not in tables_in_order:
                tables_in_order.append(item)
    aliases = {item: f"t{index}" for index, item in enumerate(tables_in_order)}

    selected: list[str] = []
    for ref in selected_refs:
        selected.append(f"{qualified_column(ref, aliases)} AS {selected_alias(ref)}")

    for aggregation in spec.aggregations:
        function = aggregation.function.upper()
        if aggregation.function == "count" and aggregation.column in (None, "*"):
            expression = "COUNT(*)"
        elif aggregation.column:
            ref = normalize_column(aggregation.column, spec.table)
            expression = f"{function}({qualified_column(ref, aliases)})"
        else:
            raise HTTPException(status_code=400, detail=f"{aggregation.function} requires a column")

        selected.append(f"{expression} AS {quote_identifier(alias_for_aggregation(aggregation))}")

    if not selected:
        selected.append(f"{aliases[base]}.*" if join_edges else "*")

    sql = (
        f"SELECT {', '.join(selected)} "
        f"FROM {quote_identifier(base.schema)}.{quote_identifier(base.table)} AS {aliases[base]}"
    )

    joined_tables = {base}
    for edge in join_edges:
        left_table, right_table = edge_tables(edge)
        joined_table = right_table if left_table in joined_tables else left_table
        joined_tables.add(joined_table)
        join_alias = aliases[joined_table]
        join_type = "LEFT JOIN" if edge.join_type == "left" else "INNER JOIN"
        left_expr = qualified_column(edge.left, aliases)
        right_expr = qualified_column(edge.right, aliases)
        sql += (
            f" {join_type} {quote_identifier(joined_table.schema)}.{quote_identifier(joined_table.table)} "
            f"AS {join_alias} ON {left_expr} = {right_expr}"
        )

    where_clauses: list[str] = []
    for item, ref in zip(spec.filters, filter_refs):
        column = qualified_column(ref, aliases)
        operator = item.operator.upper()

        if operator in {"IS NULL", "IS NOT NULL"}:
            where_clauses.append(f"{column} {operator}")
        elif operator == "IN":
            if not isinstance(item.value, list) or len(item.value) == 0:
                raise HTTPException(status_code=400, detail="IN requires a non-empty array value")
            placeholders = ", ".join(["%s"] * len(item.value))
            where_clauses.append(f"{column} IN ({placeholders})")
            params.extend(item.value)
        elif operator == "BETWEEN":
            where_clauses.append(f"{column} BETWEEN %s AND %s")
            params.extend([item.value, item.valueTo])
        else:
            where_clauses.append(f"{column} {operator} %s")
            params.append(item.value)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    if group_refs:
        sql += " GROUP BY " + ", ".join(qualified_column(ref, aliases) for ref in group_refs)

    if spec.orderBy:
        order_parts: list[str] = []
        for item in spec.orderBy:
            expression = (
                qualified_column(item.expression, aliases)
                if isinstance(item.expression, ColumnRef)
                else quote_identifier(item.expression)
            )
            order_parts.append(f"{expression} {item.direction.upper()}")
        sql += " ORDER BY " + ", ".join(order_parts)

    sql += " LIMIT %s OFFSET %s"
    params.extend([spec.limit, spec.offset])
    return CompiledQuery(sql=sql, params=params)
