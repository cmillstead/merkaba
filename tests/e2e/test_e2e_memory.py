# tests/e2e/test_e2e_memory.py
"""End-to-end tests for memory lifecycle CLI commands.

Uses real SQLite databases (patched to temp paths) and real CLI invocations.
Only the LLM (Ollama) is mocked via the global conftest sys.modules trick.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. memory status — empty DB
# ---------------------------------------------------------------------------

def test_memory_status_empty_db(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "status"])
    assert result.exit_code == 0
    assert "Memory Status" in result.output
    # All counts should be zero in a fresh database
    for category in ("Businesses", "Facts", "Decisions", "Learnings", "Episodes"):
        assert category in result.output
    # Every row should show 0
    lines = result.output.strip().splitlines()
    count_lines = [l for l in lines if any(c in l for c in ("Businesses", "Facts", "Decisions", "Learnings", "Episodes", "Relationships", "State"))]
    for line in count_lines:
        assert "0" in line


# ---------------------------------------------------------------------------
# 2. memory status — with seeded data
# ---------------------------------------------------------------------------

def test_memory_status_with_data(cli_runner, seeded_memory):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "status"])
    assert result.exit_code == 0
    assert "Memory Status" in result.output
    # seeded_memory adds: 1 business, 2 facts, 1 decision, 1 learning
    # At least businesses and facts should be non-zero
    lines = result.output.strip().splitlines()
    # Find the Businesses row — it should not be 0
    for line in lines:
        if "Businesses" in line:
            # The line contains some non-zero digit
            assert any(c.isdigit() and c != "0" for c in line), f"Expected non-zero businesses count: {line}"
            break
    else:
        pytest.fail("Businesses row not found in status output")


# ---------------------------------------------------------------------------
# 3. memory businesses — empty DB
# ---------------------------------------------------------------------------

def test_memory_businesses_empty(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "businesses"])
    assert result.exit_code == 0
    assert "No businesses" in result.output


# ---------------------------------------------------------------------------
# 4. memory businesses — with seeded data
# ---------------------------------------------------------------------------

def test_memory_businesses_with_data(cli_runner, seeded_memory):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "businesses"])
    assert result.exit_code == 0
    assert "Test Shop" in result.output
    assert "ecommerce" in result.output


# ---------------------------------------------------------------------------
# 5. Add business via CLI, store facts, verify status
# ---------------------------------------------------------------------------

def test_memory_add_business_then_store_facts(cli_runner):
    runner, app = cli_runner

    # Add a business via the business CLI
    result = runner.invoke(app, ["business", "add", "--name", "Widget Co", "--type", "saas"])
    assert result.exit_code == 0
    assert "Widget Co" in result.output

    # Manually add facts through the store (no CLI command for add-fact)
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        businesses = store.list_businesses()
        biz_id = businesses[0]["id"]
        store.add_fact(biz_id, "product", "name", "Super Widget")
        store.add_fact(biz_id, "product", "price", "$9.99")
    finally:
        store.close()

    # Verify status shows the counts
    result = runner.invoke(app, ["memory", "status"])
    assert result.exit_code == 0
    # Should show 1 business and 2 facts
    lines = result.output.strip().splitlines()
    for line in lines:
        if "Facts" in line:
            assert "2" in line
            break
    else:
        pytest.fail("Facts row not found in status output")


# ---------------------------------------------------------------------------
# 6. memory recall — keyword match
# ---------------------------------------------------------------------------

def test_memory_recall_keyword_match(cli_runner, seeded_memory):
    runner, app = cli_runner

    # Force VectorMemory to fail so the CLI falls back to keyword-only search.
    # Without this, a real ChromaDB + mocked ollama produces empty embeddings.
    with patch("merkaba.memory.vectors.VectorMemory", side_effect=RuntimeError("skip")):
        result = runner.invoke(app, ["memory", "recall", "cotton"])
    assert result.exit_code == 0
    # The seeded data has "organic cotton" as a fact value
    assert "cotton" in result.output.lower()


# ---------------------------------------------------------------------------
# 7. memory recall — no match
# ---------------------------------------------------------------------------

def test_memory_recall_no_match(cli_runner, seeded_memory):
    runner, app = cli_runner
    with patch("merkaba.memory.vectors.VectorMemory", side_effect=RuntimeError("skip")):
        result = runner.invoke(app, ["memory", "recall", "xyznonexistent"])
    assert result.exit_code == 0
    # Should indicate nothing was found
    assert "don't have any information" in result.output.lower() or "no" in result.output.lower()


# ---------------------------------------------------------------------------
# 8. memory recall — business-scoped
# ---------------------------------------------------------------------------

def test_memory_recall_business_scoped(cli_runner):
    runner, app = cli_runner

    # Create two businesses with distinct facts
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz1 = store.add_business("Bakery", "food")
        biz2 = store.add_business("Garage", "automotive")
        store.add_fact(biz1, "product", "specialty", "sourdough bread")
        store.add_fact(biz2, "service", "specialty", "oil change")
    finally:
        store.close()

    # Recall scoped to bakery should find bread but not oil change
    with patch("merkaba.memory.vectors.VectorMemory", side_effect=RuntimeError("skip")):
        result = runner.invoke(app, ["memory", "recall", "specialty", "--business", str(biz1)])
    assert result.exit_code == 0
    assert "sourdough" in result.output.lower() or "bread" in result.output.lower()

    # Recall scoped to garage should find oil change but not bread
    with patch("merkaba.memory.vectors.VectorMemory", side_effect=RuntimeError("skip")):
        result = runner.invoke(app, ["memory", "recall", "specialty", "--business", str(biz2)])
    assert result.exit_code == 0
    assert "oil" in result.output.lower() or "change" in result.output.lower()


# ---------------------------------------------------------------------------
# 9. memory decay — fresh DB (nothing to decay)
# ---------------------------------------------------------------------------

def test_memory_decay_on_fresh_db(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "decay", "--yes"])
    assert result.exit_code == 0
    assert "0 decayed" in result.output
    assert "0 archived" in result.output


# ---------------------------------------------------------------------------
# 9b. memory decay — prompts for confirmation without --yes
# ---------------------------------------------------------------------------

def test_memory_decay_confirms(cli_runner):
    """Verify decay asks for confirmation when --yes is not passed."""
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "decay"], input="y\n")
    assert result.exit_code == 0
    assert "Continue?" in result.output
    assert "0 decayed" in result.output
    assert "0 archived" in result.output


def test_memory_decay_yes_skips_confirm(cli_runner):
    """Verify --yes bypasses the confirmation prompt entirely."""
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "decay", "--yes"])
    assert result.exit_code == 0
    assert "Continue?" not in result.output
    assert "0 decayed" in result.output
    assert "0 archived" in result.output


def test_memory_decay_aborts_on_no(cli_runner):
    """Verify decay aborts when user says no at the confirmation prompt."""
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "decay"], input="n\n")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 10. memory archived — empty (no archived items)
# ---------------------------------------------------------------------------

def test_memory_archived_empty(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "archived", "facts"])
    assert result.exit_code == 0
    assert "No archived facts" in result.output


# ---------------------------------------------------------------------------
# 11. memory unarchive — archive an item, then restore it
# ---------------------------------------------------------------------------

def test_memory_unarchive_item(cli_runner):
    runner, app = cli_runner

    # Insert a business and a fact, then archive the fact directly
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz_id = store.add_business("Archive Test", "ecommerce")
        fact_id = store.add_fact(biz_id, "test", "key", "archived_value")
        store._conn.execute("UPDATE facts SET archived = 1 WHERE id = ?", (fact_id,))
        store._conn.commit()
    finally:
        store.close()

    # Confirm it shows up in archived list
    result = runner.invoke(app, ["memory", "archived", "facts"])
    assert result.exit_code == 0
    assert "archived_value" in result.output

    # Unarchive it
    result = runner.invoke(app, ["memory", "unarchive", "facts", str(fact_id)])
    assert result.exit_code == 0
    assert f"Unarchived facts #{fact_id}" in result.output

    # Confirm archived list is now empty
    result = runner.invoke(app, ["memory", "archived", "facts"])
    assert result.exit_code == 0
    assert "No archived facts" in result.output


# ---------------------------------------------------------------------------
# 12. memory episodes — empty DB
# ---------------------------------------------------------------------------

def test_memory_episodes_empty(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "episodes"])
    assert result.exit_code == 0
    assert "No episodes" in result.output
