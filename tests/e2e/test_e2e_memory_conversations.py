# tests/e2e/test_e2e_memory_conversations.py
"""End-to-end tests for memory conversations, relationships, and integrations list commands.

Uses real SQLite databases (patched to temp paths) and real CLI invocations.
Only the LLM (Ollama) is mocked via the global conftest sys.modules trick.
"""

import json
import os

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_conversation(convos_dir: str, session_id: str, messages: list[dict]) -> str:
    """Write a fake conversation JSON file and return its path."""
    os.makedirs(convos_dir, exist_ok=True)
    data = {
        "session_id": session_id,
        "messages": messages,
        "saved_at": "2026-03-02T10:00:00",
    }
    fpath = os.path.join(convos_dir, f"{session_id}.json")
    with open(fpath, "w") as f:
        json.dump(data, f)
    return fpath


# ---------------------------------------------------------------------------
# 1. memory conversations list -- empty directory
# ---------------------------------------------------------------------------

def test_memory_conversations_list_empty(cli_runner, merkaba_home, monkeypatch):
    """Verify empty-state message when conversations directory is empty."""
    runner, app = cli_runner
    convos_dir = str(merkaba_home / "conversations")
    monkeypatch.setenv("HOME", str(merkaba_home.parent))
    # Patch the conversations dir to point to our temp location
    import merkaba.cli as _cli
    monkeypatch.setattr(_cli, "MERKABA_DIR", str(merkaba_home))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(app, ["memory", "conversations", "list"])

    assert result.exit_code == 0
    assert "No conversations found" in result.output


# ---------------------------------------------------------------------------
# 2. memory conversations list -- with data
# ---------------------------------------------------------------------------

def test_memory_conversations_list_with_data(cli_runner, merkaba_home, monkeypatch):
    """Verify conversations list shows files."""
    runner, app = cli_runner
    convos_dir = str(merkaba_home / "conversations")
    _write_conversation(
        convos_dir,
        "20260302-100000",
        [
            {"role": "user", "content": "Hello", "timestamp": "2026-03-02T10:00:00"},
            {"role": "assistant", "content": "Hi there!", "timestamp": "2026-03-02T10:00:01"},
        ],
    )

    import merkaba.cli as _cli
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(app, ["memory", "conversations", "list"])

    assert result.exit_code == 0
    assert "20260302-100000" in result.output
    assert "2" in result.output  # message count


# ---------------------------------------------------------------------------
# 3. memory conversations show
# ---------------------------------------------------------------------------

def test_memory_conversations_show(cli_runner, merkaba_home, monkeypatch):
    """Verify conversations show displays messages."""
    runner, app = cli_runner
    convos_dir = str(merkaba_home / "conversations")
    _write_conversation(
        convos_dir,
        "20260302-110000",
        [
            {"role": "user", "content": "What is the weather?", "timestamp": "2026-03-02T11:00:00"},
            {"role": "assistant", "content": "I cannot check the weather.", "timestamp": "2026-03-02T11:00:05"},
        ],
    )

    import merkaba.cli as _cli
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(app, ["memory", "conversations", "show", "20260302-110000"])

    assert result.exit_code == 0
    assert "What is the weather?" in result.output
    assert "I cannot check the weather." in result.output


# ---------------------------------------------------------------------------
# 4. memory conversations show -- not found
# ---------------------------------------------------------------------------

def test_memory_conversations_show_not_found(cli_runner, merkaba_home, monkeypatch):
    """Verify proper error when conversation ID does not exist."""
    runner, app = cli_runner

    import merkaba.cli as _cli
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(app, ["memory", "conversations", "show", "nonexistent-id"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# 5. memory conversations delete
# ---------------------------------------------------------------------------

def test_memory_conversations_delete(cli_runner, merkaba_home, monkeypatch):
    """Verify conversations delete removes the file."""
    runner, app = cli_runner
    convos_dir = str(merkaba_home / "conversations")
    fpath = _write_conversation(
        convos_dir,
        "20260302-120000",
        [{"role": "user", "content": "Test", "timestamp": "2026-03-02T12:00:00"}],
    )
    assert os.path.exists(fpath)

    import merkaba.cli as _cli
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(app, ["memory", "conversations", "delete", "20260302-120000", "--yes"])

    assert result.exit_code == 0
    assert "Deleted" in result.output
    assert not os.path.exists(fpath)


# ---------------------------------------------------------------------------
# 6. memory conversations export
# ---------------------------------------------------------------------------

def test_memory_conversations_export(cli_runner, merkaba_home, monkeypatch, tmp_path):
    """Verify conversations export writes a valid JSON file."""
    runner, app = cli_runner
    convos_dir = str(merkaba_home / "conversations")
    _write_conversation(
        convos_dir,
        "20260302-130000",
        [
            {"role": "user", "content": "Export test", "timestamp": "2026-03-02T13:00:00"},
        ],
    )
    output_path = str(tmp_path / "exported.json")

    import merkaba.cli as _cli
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "merkaba.cli.os.path.expanduser",
            lambda p: p.replace("~/.merkaba", str(merkaba_home)),
        )
        result = runner.invoke(
            app,
            ["memory", "conversations", "export", "20260302-130000", "--output", output_path],
        )

    assert result.exit_code == 0
    assert "Exported" in result.output
    assert os.path.exists(output_path)
    with open(output_path) as f:
        data = json.load(f)
    assert data["session_id"] == "20260302-130000"
    assert len(data["messages"]) == 1


# ---------------------------------------------------------------------------
# 7. memory relationships -- empty
# ---------------------------------------------------------------------------

def test_memory_relationships_empty(cli_runner):
    """Verify empty-state message when no relationships exist."""
    runner, app = cli_runner
    result = runner.invoke(app, ["memory", "relationships"])
    assert result.exit_code == 0
    assert "No relationships found" in result.output


# ---------------------------------------------------------------------------
# 8. memory relationships -- with data
# ---------------------------------------------------------------------------

def test_memory_relationships_with_data(cli_runner):
    """Verify relationships command shows entity relationships."""
    runner, app = cli_runner

    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz_id = store.add_business("Rel Test Co", "services")
        store.add_relationship(
            biz_id,
            entity_type="person",
            entity_id="Alice",
            relation="manages",
            related_entity="Bob",
        )
        store.add_relationship(
            biz_id,
            entity_type="company",
            entity_id="Acme",
            relation="partners_with",
            related_entity="Widget Corp",
        )
    finally:
        store.close()

    result = runner.invoke(app, ["memory", "relationships"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "manages" in result.output
    assert "Bob" in result.output


# ---------------------------------------------------------------------------
# 9. memory relationships -- filter by entity
# ---------------------------------------------------------------------------

def test_memory_relationships_filter_entity(cli_runner):
    """Verify --entity filter narrows results."""
    runner, app = cli_runner

    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz_id = store.add_business("Filter Test Co", "services")
        store.add_relationship(biz_id, "person", "Alice", "reports_to", "Charlie")
        store.add_relationship(biz_id, "company", "Acme", "owns", "Widget Corp")
    finally:
        store.close()

    result = runner.invoke(app, ["memory", "relationships", "--entity", "alice"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    # Acme should not appear since filter is "alice"
    assert "Acme" not in result.output


# ---------------------------------------------------------------------------
# 10. integrations list -- basic run
# ---------------------------------------------------------------------------

def test_integrations_list(cli_runner):
    """Verify integrations list command runs and shows available adapters."""
    runner, app = cli_runner
    result = runner.invoke(app, ["integrations", "list"])
    assert result.exit_code == 0
    # Should show either adapters or "No integrations found"
    assert "Integration" in result.output or "No integrations found" in result.output


# ---------------------------------------------------------------------------
# 11. integrations list -- shows status column
# ---------------------------------------------------------------------------

def test_integrations_list_shows_status(cli_runner):
    """Verify integrations list shows a Status column."""
    runner, app = cli_runner
    result = runner.invoke(app, ["integrations", "list"])
    assert result.exit_code == 0
    # At minimum it should run cleanly; if adapters are loaded, check for Status
    if "Integration" in result.output and "No integrations" not in result.output:
        assert "Status" in result.output or "configured" in result.output or "missing" in result.output


# ---------------------------------------------------------------------------
# 12. memory relationships -- filter by business
# ---------------------------------------------------------------------------

def test_memory_relationships_filter_business(cli_runner):
    """Verify --business filter scopes relationships to one business."""
    runner, app = cli_runner

    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz1 = store.add_business("Business One", "retail")
        biz2 = store.add_business("Business Two", "services")
        store.add_relationship(biz1, "person", "Alpha", "knows", "Beta")
        store.add_relationship(biz2, "company", "Gamma", "owns", "Delta")
    finally:
        store.close()

    result = runner.invoke(app, ["memory", "relationships", "--business", str(biz1)])
    assert result.exit_code == 0
    assert "Alpha" in result.output
    assert "Gamma" not in result.output
