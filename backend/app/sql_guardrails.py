import re

from app.models import SqlClassification


COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
COMMENT_LINE_RE = re.compile(r"--.*?$", re.MULTILINE)
DELETE_WITHOUT_WHERE_RE = re.compile(r"\bdelete\s+from\b(?![\s\S]*\bwhere\b)", re.IGNORECASE)
UPDATE_WITHOUT_WHERE_RE = re.compile(r"\bupdate\b(?![\s\S]*\bwhere\b)", re.IGNORECASE)

DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdrop\b", re.IGNORECASE), "DROP statement"),
    (re.compile(r"\btruncate\b", re.IGNORECASE), "TRUNCATE statement"),
    (re.compile(r"\balter\s+system\b", re.IGNORECASE), "ALTER SYSTEM statement"),
    (re.compile(r"\breindex\b", re.IGNORECASE), "REINDEX statement"),
    (re.compile(r"\bvacuum\s+full\b", re.IGNORECASE), "VACUUM FULL statement"),
    (re.compile(r"\bgrant\b|\brevoke\b", re.IGNORECASE), "Privilege change"),
    (DELETE_WITHOUT_WHERE_RE, "DELETE without WHERE"),
    (UPDATE_WITHOUT_WHERE_RE, "UPDATE without WHERE"),
]

READ_ONLY_TYPES = {"select", "with", "show", "explain", "values"}


def normalize_sql(sql: str) -> str:
    without_blocks = COMMENT_BLOCK_RE.sub(" ", sql)
    without_lines = COMMENT_LINE_RE.sub(" ", without_blocks)
    return re.sub(r"\s+", " ", without_lines).strip()


def classify_sql(sql: str) -> SqlClassification:
    normalized = normalize_sql(sql)
    first_token_match = re.match(r"([a-zA-Z]+)", normalized)
    statement_type = first_token_match.group(1).lower() if first_token_match else "unknown"
    reasons = [reason for pattern, reason in DANGEROUS_PATTERNS if pattern.search(normalized)]
    is_read_only = statement_type in READ_ONLY_TYPES

    return SqlClassification(
        statementType=statement_type.upper(),
        isReadOnly=is_read_only,
        isDangerous=bool(reasons),
        reasons=reasons,
    )

