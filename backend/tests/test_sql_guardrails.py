from app.sql_guardrails import classify_sql


def test_select_is_read_only() -> None:
    classification = classify_sql("select * from customers")

    assert classification.isReadOnly is True
    assert classification.isDangerous is False
    assert classification.statementType == "SELECT"


def test_drop_is_dangerous() -> None:
    classification = classify_sql("drop table customers")

    assert classification.isDangerous is True
    assert "DROP statement" in classification.reasons


def test_delete_without_where_is_dangerous() -> None:
    classification = classify_sql("delete from orders")

    assert classification.isDangerous is True
    assert "DELETE without WHERE" in classification.reasons


def test_delete_with_where_is_allowed_without_danger_flag() -> None:
    classification = classify_sql("delete from orders where id = 1")

    assert classification.isDangerous is False

