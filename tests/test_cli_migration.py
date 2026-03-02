# tests/test_cli_migration.py
"""Tests for CLI migration and identity import/export commands."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Ensure ollama is mocked before merkaba imports.
sys.modules.setdefault("ollama", MagicMock())

from merkaba.cli import app

runner = CliRunner()


# -- migrate openclaw --


class TestMigrateOpenclawCLI:

    def test_migrate_openclaw_success(self, tmp_path):
        """Successful migration shows migrated files and completion message."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".openclaw").mkdir()
        (workspace / "SOUL.md").write_text("Be helpful.")
        (workspace / "AGENTS.md").write_text("Agent config.")

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=True), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.migrate") as mock_migrate:
            from merkaba.plugins.importer_openclaw import MigrationResult
            mock_migrate.return_value = MigrationResult(
                migrated=["SOUL.md", "AGENTS.md (stashed)"],
                skipped=[],
                errors=[],
            )
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "--business", "testbiz"])

        assert result.exit_code == 0
        assert "SOUL.md" in result.output
        assert "AGENTS.md (stashed)" in result.output
        assert "Migration complete" in result.output
        assert "testbiz" in result.output

    def test_migrate_openclaw_not_a_directory(self, tmp_path):
        """Non-existent path shows error."""
        result = runner.invoke(app, ["migrate", "openclaw", str(tmp_path / "nope"), "--business", "biz"])
        assert result.exit_code == 1
        assert "Not a directory" in result.output

    def test_migrate_openclaw_not_openclaw_workspace(self, tmp_path):
        """Directory without OpenClaw markers shows error."""
        workspace = tmp_path / "empty"
        workspace.mkdir()

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=False):
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "--business", "biz"])

        assert result.exit_code == 1
        assert "Not an OpenClaw workspace" in result.output

    def test_migrate_openclaw_with_errors(self, tmp_path):
        """Migration errors are displayed and exit code is 1."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=True), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.migrate") as mock_migrate:
            from merkaba.plugins.importer_openclaw import MigrationResult
            mock_migrate.return_value = MigrationResult(
                migrated=["SOUL.md"],
                skipped=[],
                errors=["AGENTS.md: Permission denied"],
            )
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "--business", "biz"])

        assert result.exit_code == 1
        assert "Permission denied" in result.output
        assert "Errors" in result.output

    def test_migrate_openclaw_with_skipped(self, tmp_path):
        """Skipped files are displayed."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=True), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.migrate") as mock_migrate:
            from merkaba.plugins.importer_openclaw import MigrationResult
            mock_migrate.return_value = MigrationResult(
                migrated=["SOUL.md"],
                skipped=["random.txt"],
                errors=[],
            )
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "--business", "biz"])

        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "random.txt" in result.output

    def test_migrate_openclaw_empty_workspace(self, tmp_path):
        """Empty workspace shows no-files message."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=True), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.migrate") as mock_migrate:
            from merkaba.plugins.importer_openclaw import MigrationResult
            mock_migrate.return_value = MigrationResult(
                migrated=[],
                skipped=[],
                errors=[],
            )
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "--business", "biz"])

        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_migrate_openclaw_missing_business_flag(self, tmp_path):
        """Missing --business flag produces an error."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        result = runner.invoke(app, ["migrate", "openclaw", str(workspace)])
        assert result.exit_code != 0

    def test_migrate_openclaw_short_flag(self, tmp_path):
        """Short -b flag works for --business."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.detect", return_value=True), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.migrate") as mock_migrate:
            from merkaba.plugins.importer_openclaw import MigrationResult
            mock_migrate.return_value = MigrationResult(
                migrated=["SOUL.md"],
                skipped=[],
                errors=[],
            )
            result = runner.invoke(app, ["migrate", "openclaw", str(workspace), "-b", "mybiz"])

        assert result.exit_code == 0
        assert "mybiz" in result.output

    def test_migrate_help(self):
        """migrate group shows help text."""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output.lower()


# -- identity import --


class TestIdentityImportCLI:

    def test_identity_import_success(self, tmp_path):
        """Successful import shows SOUL.md path and business name."""
        aieos_file = tmp_path / "identity.json"
        aieos_file.write_text(json.dumps({
            "version": "1.1",
            "identity": {"name": "TestAgent"},
        }))

        with patch("merkaba.identity.aieos.import_aieos") as mock_import:
            from merkaba.identity.aieos import ImportResult
            mock_import.return_value = ImportResult(
                success=True,
                soul_md_path="/home/user/.merkaba/businesses/mybiz/SOUL.md",
            )
            result = runner.invoke(app, ["identity", "import", str(aieos_file), "--business", "mybiz"])

        assert result.exit_code == 0
        assert "imported successfully" in result.output.lower()
        assert "mybiz" in result.output
        assert "SOUL.md" in result.output

    def test_identity_import_file_not_found(self, tmp_path):
        """Non-existent file shows error before calling import."""
        result = runner.invoke(app, ["identity", "import", str(tmp_path / "nope.json"), "--business", "biz"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_identity_import_failure(self, tmp_path):
        """Import failure shows error messages."""
        aieos_file = tmp_path / "bad.json"
        aieos_file.write_text("not json")

        with patch("merkaba.identity.aieos.import_aieos") as mock_import:
            from merkaba.identity.aieos import ImportResult
            mock_import.return_value = ImportResult(
                success=False,
                errors=["Invalid JSON"],
            )
            result = runner.invoke(app, ["identity", "import", str(aieos_file), "--business", "biz"])

        assert result.exit_code == 1
        assert "Import failed" in result.output
        assert "Invalid JSON" in result.output

    def test_identity_import_missing_business_flag(self, tmp_path):
        """Missing --business flag produces an error."""
        aieos_file = tmp_path / "identity.json"
        aieos_file.write_text("{}")
        result = runner.invoke(app, ["identity", "import", str(aieos_file)])
        assert result.exit_code != 0

    def test_identity_import_short_flag(self, tmp_path):
        """Short -b flag works for --business."""
        aieos_file = tmp_path / "identity.json"
        aieos_file.write_text("{}")

        with patch("merkaba.identity.aieos.import_aieos") as mock_import:
            from merkaba.identity.aieos import ImportResult
            mock_import.return_value = ImportResult(
                success=True,
                soul_md_path="/tmp/biz/SOUL.md",
            )
            result = runner.invoke(app, ["identity", "import", str(aieos_file), "-b", "mybiz"])

        assert result.exit_code == 0
        assert "mybiz" in result.output


# -- identity export --


class TestIdentityExportCLI:

    def test_identity_export_success(self, tmp_path):
        """Successful export shows output path and business name."""
        output_file = tmp_path / "out.json"

        with patch("merkaba.identity.aieos.export_aieos") as mock_export:
            from merkaba.identity.aieos import ExportResult
            mock_export.return_value = ExportResult(
                success=True,
                output_path=str(output_file),
            )
            result = runner.invoke(app, ["identity", "export", "--business", "mybiz", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "exported successfully" in result.output.lower()
        assert "mybiz" in result.output

    def test_identity_export_failure(self):
        """Export failure shows error messages."""
        with patch("merkaba.identity.aieos.export_aieos") as mock_export:
            from merkaba.identity.aieos import ExportResult
            mock_export.return_value = ExportResult(
                success=False,
                errors=["Business directory not found: /fake"],
            )
            result = runner.invoke(app, ["identity", "export", "--business", "ghost", "--output", "/tmp/out.json"])

        assert result.exit_code == 1
        assert "Export failed" in result.output
        assert "not found" in result.output.lower()

    def test_identity_export_default_output(self):
        """Export without --output uses business name as default filename."""
        with patch("merkaba.identity.aieos.export_aieos") as mock_export:
            from merkaba.identity.aieos import ExportResult
            mock_export.return_value = ExportResult(
                success=True,
                output_path="/somewhere/mybiz.aieos.json",
            )
            result = runner.invoke(app, ["identity", "export", "--business", "mybiz"])

        assert result.exit_code == 0
        # Verify export_aieos was called with an output_path ending in mybiz.aieos.json
        call_args = mock_export.call_args
        output_path = call_args[1].get("output_path") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("output_path")
        assert str(output_path).endswith("mybiz.aieos.json")

    def test_identity_export_missing_business_flag(self):
        """Missing --business flag produces an error."""
        result = runner.invoke(app, ["identity", "export"])
        assert result.exit_code != 0

    def test_identity_export_short_flags(self, tmp_path):
        """Short -b and -o flags work."""
        output_file = tmp_path / "out.json"

        with patch("merkaba.identity.aieos.export_aieos") as mock_export:
            from merkaba.identity.aieos import ExportResult
            mock_export.return_value = ExportResult(
                success=True,
                output_path=str(output_file),
            )
            result = runner.invoke(app, ["identity", "export", "-b", "mybiz", "-o", str(output_file)])

        assert result.exit_code == 0
        assert "mybiz" in result.output

    def test_identity_help(self):
        """identity group shows help text."""
        result = runner.invoke(app, ["identity", "--help"])
        assert result.exit_code == 0
        assert "identity" in result.output.lower()


# -- Integration tests (real filesystem, no mocks) --


class TestMigrateOpenclawIntegration:
    """Integration test using real OpenClawMigrator with temp directories."""

    def test_full_openclaw_migration(self, tmp_path):
        """End-to-end: create a workspace, migrate it, verify files land correctly."""
        workspace = tmp_path / "openclaw_workspace"
        workspace.mkdir()
        (workspace / ".openclaw").mkdir()
        (workspace / "SOUL.md").write_text("Be helpful and kind.")
        (workspace / "USER.md").write_text("User preferences here.")
        (workspace / "AGENTS.md").write_text("Agent definitions.")
        (workspace / "TOOLS.md").write_text("Tool definitions.")

        merkaba_home = tmp_path / "merkaba"
        with patch.dict("os.environ", {"HOME": str(tmp_path)}), \
             patch("merkaba.plugins.importer_openclaw.OpenClawMigrator.__init__",
                   lambda self, merkaba_home=None: setattr(self, "merkaba_home", merkaba_home or Path("~/.merkaba").expanduser())):
            from merkaba.plugins.importer_openclaw import OpenClawMigrator
            # Use real migrator with custom home
            migrator = OpenClawMigrator(merkaba_home=merkaba_home)
            with patch("merkaba.plugins.importer_openclaw.OpenClawMigrator", return_value=migrator):
                result = runner.invoke(app, [
                    "migrate", "openclaw", str(workspace), "--business", "integ_biz",
                ])

        assert result.exit_code == 0
        assert "Migration complete" in result.output
        assert "integ_biz" in result.output

        biz_dir = merkaba_home / "businesses" / "integ_biz"
        assert (biz_dir / "SOUL.md").read_text() == "Be helpful and kind."
        assert (biz_dir / "USER.md").read_text() == "User preferences here."
        assert (biz_dir / ".imported" / "AGENTS.md").read_text() == "Agent definitions."
        assert (biz_dir / ".imported" / "TOOLS.md").read_text() == "Tool definitions."


class TestIdentityIntegration:
    """Integration tests using real import/export with temp directories."""

    def test_full_identity_import_export_roundtrip(self, tmp_path):
        """End-to-end: import AIEOS, then export and verify round-trip."""
        from merkaba.identity.aieos import import_aieos, export_aieos

        aieos_data = {
            "version": "1.1",
            "identity": {
                "name": "RoundTripAgent",
                "description": "An agent for round-trip testing.",
            },
            "psychology": {
                "personality": "Thoughtful and precise",
                "communication_style": "Concise",
            },
            "linguistics": {"tone": "professional"},
            "motivations": ["Test thoroughly"],
            "capabilities": ["testing"],
        }
        aieos_file = tmp_path / "identity.json"
        aieos_file.write_text(json.dumps(aieos_data))

        merkaba_home = tmp_path / "merkaba"

        # Import
        import_result = import_aieos(aieos_file, "rtbiz", merkaba_home=merkaba_home)
        assert import_result.success

        # Export
        export_path = tmp_path / "exported.json"
        export_result = export_aieos("rtbiz", merkaba_home=merkaba_home, output_path=export_path)
        assert export_result.success

        exported = json.loads(export_path.read_text())
        assert exported["version"] == "1.1"
        assert exported["identity"]["name"] == "RoundTripAgent"
        assert exported["identity"]["description"] == "An agent for round-trip testing."
        assert "extensions" in exported
        assert "merkaba" in exported["extensions"]
