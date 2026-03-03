# tests/e2e/test_e2e_data.py
"""End-to-end tests for data export and delete-all CLI commands.

Uses real SQLite databases (patched to temp paths) and real CLI invocations.
Only the LLM (Ollama) is mocked via the global conftest sys.modules trick.
"""

import json

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. data export — seeds data, exports, verifies JSON structure
# ---------------------------------------------------------------------------

def test_data_export_all(cli_runner, seeded_memory, tmp_path):
    runner, app = cli_runner
    output_file = str(tmp_path / "export.json")

    result = runner.invoke(app, ["data", "export", "--output", output_file])
    assert result.exit_code == 0, result.output

    # Should report what was exported
    assert "Exported" in result.output
    assert output_file in result.output

    # File must exist and be valid JSON
    with open(output_file) as f:
        data = json.load(f)

    # Required top-level keys
    assert "exported_at" in data
    assert "business_id" in data
    assert "facts" in data
    assert "decisions" in data
    assert "learnings" in data
    assert "episodes" in data
    assert "relationships" in data

    # business_id should be null when no filter applied
    assert data["business_id"] is None

    # seeded_memory adds: 2 facts, 1 decision, 1 learning
    assert len(data["facts"]) >= 2
    assert len(data["decisions"]) >= 1
    assert len(data["learnings"]) >= 1


# ---------------------------------------------------------------------------
# 2. data export --business-id — seeds two businesses, exports one
# ---------------------------------------------------------------------------

def test_data_export_by_business(cli_runner, tmp_path):
    runner, app = cli_runner

    # Create two businesses with distinct facts
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz1 = store.add_business("Alpha Corp", "saas")
        biz2 = store.add_business("Beta Shop", "ecommerce")
        store.add_fact(biz1, "product", "name", "AlphaWidget")
        store.add_fact(biz1, "product", "price", "$50")
        store.add_decision(biz1, "pricing", "Raised price by 5%", "Demand is strong")
        store.add_fact(biz2, "product", "name", "BetaGadget")
        store.add_fact(biz2, "product", "material", "plastic")
    finally:
        store.close()

    output_file = str(tmp_path / "biz1_export.json")

    # Export only business 1
    result = runner.invoke(
        app,
        ["data", "export", "--output", output_file, "--business-id", str(biz1)],
    )
    assert result.exit_code == 0, result.output
    assert "Exported" in result.output

    with open(output_file) as f:
        data = json.load(f)

    # business_id should be set to biz1
    assert data["business_id"] == biz1

    # Facts should belong only to biz1
    for fact in data["facts"]:
        assert fact["business_id"] == biz1

    # Alpha facts present; Beta facts absent
    fact_values = [f["value"] for f in data["facts"]]
    assert "AlphaWidget" in fact_values
    assert "BetaGadget" not in fact_values

    # decisions should belong to biz1 only
    assert len(data["decisions"]) >= 1
    for dec in data["decisions"]:
        assert dec["business_id"] == biz1


# ---------------------------------------------------------------------------
# 3. data delete-all --confirm — seeds data, deletes, verifies gone
# ---------------------------------------------------------------------------

def test_data_delete_all_with_confirm(cli_runner, seeded_memory):
    runner, app = cli_runner
    business_id = seeded_memory["business_id"]

    # Verify data exists before delete
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        facts_before = store.get_facts(business_id)
    finally:
        store.close()
    assert len(facts_before) >= 1

    # Delete with --confirm flag (no interactive prompt)
    result = runner.invoke(
        app,
        ["data", "delete-all", "--business-id", str(business_id), "--confirm"],
    )
    assert result.exit_code == 0, result.output
    assert "Deleted all data" in result.output
    assert str(business_id) in result.output

    # Verify business and its data are gone
    store = MemoryStore()
    try:
        biz = store.get_business(business_id)
        facts_after = store.get_facts(business_id)
        decisions_after = store.get_decisions(business_id)
    finally:
        store.close()

    assert biz is None, "Business record should have been deleted"
    assert len(facts_after) == 0, "Facts should have been deleted"
    assert len(decisions_after) == 0, "Decisions should have been deleted"


# ---------------------------------------------------------------------------
# 4. data delete-all — no --confirm prompts; data survives if not confirmed
# ---------------------------------------------------------------------------

def test_data_delete_all_no_confirm_aborts(cli_runner, seeded_memory):
    runner, app = cli_runner
    business_id = seeded_memory["business_id"]

    # Invoke without --confirm; answer "n" at the prompt
    result = runner.invoke(
        app,
        ["data", "delete-all", "--business-id", str(business_id)],
        input="n\n",  # decline the confirmation prompt
    )
    assert result.exit_code == 0, result.output

    # Output should contain the confirmation question
    assert str(business_id) in result.output

    # Data should still exist
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz = store.get_business(business_id)
        facts = store.get_facts(business_id)
    finally:
        store.close()

    assert biz is not None, "Business should still exist after abort"
    assert len(facts) >= 1, "Facts should survive after abort"
