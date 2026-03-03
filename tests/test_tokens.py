# tests/test_tokens.py
"""Tests for TokenUsageStore and the _SAFE_COLUMNS defense-in-depth mapping."""
import tempfile

import pytest

from merkaba.observability.tokens import TokenUsageStore, _SAFE_COLUMNS


# ---------------------------------------------------------------------------
# _SAFE_COLUMNS module-level constant
# ---------------------------------------------------------------------------

def test_safe_columns_contains_model():
    assert "model" in _SAFE_COLUMNS
    assert _SAFE_COLUMNS["model"] == "model"


def test_safe_columns_contains_worker_type():
    assert "worker_type" in _SAFE_COLUMNS
    assert _SAFE_COLUMNS["worker_type"] == "worker_type"


def test_safe_columns_does_not_contain_arbitrary_keys():
    assert "'; DROP TABLE token_usage; --" not in _SAFE_COLUMNS
    assert "id" not in _SAFE_COLUMNS
    assert "timestamp" not in _SAFE_COLUMNS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = TokenUsageStore(db_path=db_path)
    # Seed some records spanning the last 2 days
    s.record("gpt-4o", input_tokens=100, output_tokens=50, worker_type="code")
    s.record("gpt-4o", input_tokens=200, output_tokens=100, worker_type="review")
    s.record("claude-3", input_tokens=80, output_tokens=40, worker_type="code")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# group_by="model" (default)
# ---------------------------------------------------------------------------

def test_get_summary_default_groups_by_model(store):
    rows = store.get_summary()
    assert len(rows) > 0
    # Every row must have a "model" key (not "worker_type")
    for row in rows:
        assert "model" in row


def test_get_summary_model_aggregates_correctly(store):
    rows = store.get_summary(group_by="model")
    by_model = {r["model"]: r for r in rows}
    assert "gpt-4o" in by_model
    assert by_model["gpt-4o"]["call_count"] == 2
    assert by_model["gpt-4o"]["total_input"] == 300
    assert by_model["gpt-4o"]["total_output"] == 150
    assert by_model["gpt-4o"]["total_tokens"] == 450


# ---------------------------------------------------------------------------
# group_by="worker_type"
# ---------------------------------------------------------------------------

def test_get_summary_worker_type_groups_correctly(store):
    rows = store.get_summary(group_by="worker_type")
    assert len(rows) > 0
    for row in rows:
        assert "worker_type" in row


def test_get_summary_worker_type_aggregates_correctly(store):
    rows = store.get_summary(group_by="worker_type")
    by_wt = {r["worker_type"]: r for r in rows}
    assert "code" in by_wt
    assert by_wt["code"]["call_count"] == 2


# ---------------------------------------------------------------------------
# Invalid / malicious group_by values fall back to "model"
# ---------------------------------------------------------------------------

def test_invalid_group_by_falls_back_to_model(store):
    rows = store.get_summary(group_by="invalid_column")
    # Should not raise; result is grouped by model
    for row in rows:
        assert "model" in row


def test_sql_injection_attempt_in_group_by_falls_back_to_model(store):
    malicious = "'; DROP TABLE token_usage; --"
    rows = store.get_summary(group_by=malicious)
    # Must not raise an sqlite3 error; result grouped by model
    for row in rows:
        assert "model" in row


def test_empty_string_group_by_falls_back_to_model(store):
    rows = store.get_summary(group_by="")
    for row in rows:
        assert "model" in row


def test_none_like_string_group_by_falls_back_to_model(store):
    rows = store.get_summary(group_by="None")
    for row in rows:
        assert "model" in row


# ---------------------------------------------------------------------------
# Dict-lookup is the mechanism (structural test)
# ---------------------------------------------------------------------------

def test_safe_columns_get_valid_returns_correct_column():
    assert _SAFE_COLUMNS.get("model", "model") == "model"
    assert _SAFE_COLUMNS.get("worker_type", "model") == "worker_type"


def test_safe_columns_get_invalid_returns_default():
    assert _SAFE_COLUMNS.get("bogus", "model") == "model"
    assert _SAFE_COLUMNS.get("", "model") == "model"
    assert _SAFE_COLUMNS.get("1 OR 1=1", "model") == "model"


# ---------------------------------------------------------------------------
# record() and get_by_trace()
# ---------------------------------------------------------------------------

def test_record_returns_id():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        s = TokenUsageStore(db_path=f.name)
        rid = s.record("test-model", input_tokens=10, output_tokens=5)
        assert isinstance(rid, str)
        assert len(rid) == 12
        s.close()


def test_get_by_trace_returns_matching_records():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        s = TokenUsageStore(db_path=f.name)
        s.record("model-a", input_tokens=1, trace_id="trace-abc")
        s.record("model-b", input_tokens=2, trace_id="trace-abc")
        s.record("model-c", input_tokens=3, trace_id="trace-xyz")
        result = s.get_by_trace("trace-abc")
        assert len(result) == 2
        models = {r["model"] for r in result}
        assert models == {"model-a", "model-b"}
        s.close()
