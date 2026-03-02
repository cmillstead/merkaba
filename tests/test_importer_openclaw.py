# tests/test_importer_openclaw.py
"""Tests for OpenClaw workspace migrator."""

from pathlib import Path

from merkaba.plugins.importer_openclaw import OpenClawMigrator


def test_detect_openclaw_workspace(tmp_path):
    (tmp_path / ".openclaw").mkdir()
    (tmp_path / "SOUL.md").write_text("I am an agent.")
    migrator = OpenClawMigrator()
    assert migrator.detect(tmp_path)


def test_detect_not_openclaw(tmp_path):
    migrator = OpenClawMigrator()
    assert not migrator.detect(tmp_path)


def test_detect_soul_md_only(tmp_path):
    """SOUL.md alone is enough to detect an OpenClaw workspace."""
    (tmp_path / "SOUL.md").write_text("Be helpful.")
    migrator = OpenClawMigrator()
    assert migrator.detect(tmp_path)


def test_detect_openclaw_dir_only(tmp_path):
    """.openclaw dir alone is enough to detect."""
    (tmp_path / ".openclaw").mkdir()
    migrator = OpenClawMigrator()
    assert migrator.detect(tmp_path)


def test_migrate_copies_soul_md(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "SOUL.md").write_text("Be helpful.")
    (workspace / "AGENTS.md").write_text("Agent config.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "testbiz")

    assert (output / "businesses" / "testbiz" / "SOUL.md").read_text() == "Be helpful."
    assert len(result.migrated) >= 2


def test_migrate_copies_user_md(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "USER.md").write_text("User preferences.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "mybiz")

    assert (output / "businesses" / "mybiz" / "USER.md").read_text() == "User preferences."
    assert "USER.md" in result.migrated


def test_migrate_copies_heartbeat_md(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "HEARTBEAT.md").write_text("- [ ] Check status")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "mybiz")

    assert (output / "businesses" / "mybiz" / "HEARTBEAT.md").read_text() == "- [ ] Check status"
    assert "HEARTBEAT.md" in result.migrated


def test_migrate_stashes_originals(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "SOUL.md").write_text("Original.")
    (workspace / "AGENTS.md").write_text("Agents.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    migrator.migrate(workspace, "testbiz")

    imported_dir = output / "businesses" / "testbiz" / ".imported"
    assert imported_dir.exists()
    assert (imported_dir / "SOUL.md").read_text() == "Original."
    assert (imported_dir / "AGENTS.md").read_text() == "Agents."


def test_migrate_stash_only_files(tmp_path):
    """AGENTS.md, TOOLS.md, IDENTITY.md are stashed but not copied to biz dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Agent config.")
    (workspace / "TOOLS.md").write_text("Tool defs.")
    (workspace / "IDENTITY.md").write_text("Identity info.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "testbiz")

    biz_dir = output / "businesses" / "testbiz"
    imported_dir = biz_dir / ".imported"

    # Not copied directly to biz dir
    assert not (biz_dir / "AGENTS.md").exists()
    assert not (biz_dir / "TOOLS.md").exists()
    assert not (biz_dir / "IDENTITY.md").exists()

    # But stashed in .imported/
    assert (imported_dir / "AGENTS.md").read_text() == "Agent config."
    assert (imported_dir / "TOOLS.md").read_text() == "Tool defs."
    assert (imported_dir / "IDENTITY.md").read_text() == "Identity info."

    # All reported as migrated (stashed)
    assert "AGENTS.md (stashed)" in result.migrated
    assert "TOOLS.md (stashed)" in result.migrated
    assert "IDENTITY.md (stashed)" in result.migrated


def test_migrate_skips_unknown_files(tmp_path):
    """Unknown files are stashed and reported as skipped."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "random.txt").write_text("Something.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "testbiz")

    assert "random.txt" in result.skipped


def test_migrate_skips_directories(tmp_path):
    """Directories inside workspace are ignored."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "subdir").mkdir()
    (workspace / "SOUL.md").write_text("Soul.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "testbiz")

    assert "SOUL.md" in result.migrated
    # subdir should not appear in any result list
    all_items = result.migrated + result.skipped + result.errors
    assert not any("subdir" in item for item in all_items)


def test_migrate_empty_workspace(tmp_path):
    """Empty workspace produces empty result."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    result = migrator.migrate(workspace, "testbiz")

    assert result.migrated == []
    assert result.skipped == []
    assert result.errors == []


def test_migrate_creates_business_dir(tmp_path):
    """Business directory is created if it doesn't exist."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "SOUL.md").write_text("Soul.")

    output = tmp_path / "merkaba"
    migrator = OpenClawMigrator(merkaba_home=output)
    migrator.migrate(workspace, "newbiz")

    assert (output / "businesses" / "newbiz").is_dir()


def test_migrate_default_merkaba_home():
    """Default merkaba_home resolves to ~/.merkaba."""
    migrator = OpenClawMigrator()
    assert migrator.merkaba_home == Path("~/.merkaba").expanduser()


def test_migrate_result_dataclass():
    """MigrationResult has correct default fields."""
    from merkaba.plugins.importer_openclaw import MigrationResult

    result = MigrationResult()
    assert result.migrated == []
    assert result.skipped == []
    assert result.errors == []
