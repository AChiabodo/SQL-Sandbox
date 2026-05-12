from dataclasses import dataclass

from app.models import StarterQuery


@dataclass(frozen=True)
class DatasetTemplate:
    id: str
    name: str
    description: str
    schema_name: str
    estimated_rows: int
    table_names: tuple[str, ...]
    starter_queries: tuple[StarterQuery, ...]
    seed_sql: str

def quote_name(identifier: str) -> str:
    return f'"{identifier}"'