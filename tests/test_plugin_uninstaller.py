# tests/test_plugin_uninstaller.py
"""Tests for plugin uninstaller."""

import json
import os
import pytest

from merkaba.plugins.uninstaller import PluginUninstaller, UninstallTarget, UninstallResult


class TestPluginUninstallerScan:
    def test_scan_finds_commands_dir(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        commands_dir = claude_dir / "commands" / "myplugin"
        commands_dir.mkdir(parents=True)
        (commands_dir / "do-thing.md").write_text("# Do thing")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "commands"
        assert targets[0].path == str(commands_dir)

    def test_scan_finds_agents(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        agents_dir = claude_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "myplugin-worker.md").write_text("# Worker")
        (agents_dir / "myplugin-reviewer.md").write_text("# Reviewer")
        (agents_dir / "other-agent.md").write_text("# Other")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 2
        assert all(t.category == "agents" for t in targets)
        paths = [t.path for t in targets]
        assert str(agents_dir / "myplugin-worker.md") in paths
        assert str(agents_dir / "myplugin-reviewer.md") in paths

    def test_scan_finds_plugin_cache(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        cache_dir = claude_dir / "plugins" / "cache" / "some-org" / "myplugin"
        cache_dir.mkdir(parents=True)
        (cache_dir / "1.0.0").mkdir()

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "plugin-cache"
        assert targets[0].path == str(cache_dir)

    def test_scan_finds_framework_dir(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        framework_dir = claude_dir / "myplugin-framework"
        framework_dir.mkdir(parents=True)
        (framework_dir / "config.json").write_text("{}")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "framework"
        assert targets[0].description == "framework directory"

    def test_scan_finds_bare_plugin_dir(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        bare_dir = claude_dir / "myplugin"
        bare_dir.mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "framework"
        assert targets[0].description == "plugin directory"

    def test_scan_skips_standard_dirs(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        # These are standard Claude dirs, should not be matched
        for name in ("commands", "agents", "plugins", "projects", "cache"):
            (claude_dir / name).mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        for name in ("commands", "agents", "plugins", "projects", "cache"):
            targets = u.scan(name)
            # Should not find bare dir match for standard dirs
            assert not any(t.description == "plugin directory" for t in targets)

    def test_scan_finds_manifest(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        manifest = claude_dir / "myplugin-file-manifest.json"
        manifest.write_text('{"files": []}')

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "manifest"

    def test_scan_finds_cache_files(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        cache_dir = claude_dir / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "myplugin-state.json").write_text("{}")
        (cache_dir / "myplugin-data.json").write_text("{}")
        (cache_dir / "other-state.json").write_text("{}")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 2
        assert all(t.category == "cache" for t in targets)

    def test_scan_finds_merkaba_imports(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        merkaba_dir = tmp_path / ".merkaba"
        merkaba_plugin = merkaba_dir / "plugins" / "myplugin"
        merkaba_plugin.mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(merkaba_dir))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "merkaba-import"

    def test_scan_finds_settings_entry(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps({
            "enabledPlugins": {"some-org/myplugin": True},
            "otherSetting": "value",
        }))

        u = PluginUninstaller(
            claude_dir=str(claude_dir),
            merkaba_dir=str(tmp_path / ".merkaba"),
            settings_path=str(settings_path),
        )
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "settings"

    def test_scan_finds_installed_plugins_entry(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        installed = plugins_dir / "installed_plugins.json"
        installed.write_text(json.dumps({
            "version": 2,
            "plugins": {
                "myplugin@some-org": [{"scope": "user", "version": "1.0.0"}],
                "other@some-org": [{"scope": "user", "version": "1.0.0"}],
            }
        }))

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "installed-plugins"

    def test_scan_finds_marketplace_metadata(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        marketplace_plugin = claude_dir / "plugins" / "marketplaces" / "some-org" / "plugins" / "myplugin"
        marketplace_plugin.mkdir(parents=True)
        (marketplace_plugin / "hooks").mkdir()
        (marketplace_plugin / "hooks" / "hooks.json").write_text("{}")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")

        assert len(targets) == 1
        assert targets[0].category == "marketplace"
        assert targets[0].description == "marketplace metadata"

    def test_scan_finds_nothing(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("nonexistent")

        assert targets == []

    def test_scan_multiple_locations(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        merkaba_dir = tmp_path / ".merkaba"

        # Create artifacts in multiple locations
        (claude_dir / "commands" / "myplugin").mkdir(parents=True)
        agents_dir = claude_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "myplugin-worker.md").write_text("# Worker")
        (claude_dir / "myplugin-framework").mkdir(parents=True)
        (claude_dir / "myplugin-file-manifest.json").write_text("{}")
        (merkaba_dir / "plugins" / "myplugin").mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(merkaba_dir))
        targets = u.scan("myplugin")

        categories = {t.category for t in targets}
        assert "commands" in categories
        assert "agents" in categories
        assert "framework" in categories
        assert "manifest" in categories
        assert "merkaba-import" in categories
        assert len(targets) == 5


class TestPluginUninstallerUninstall:
    def test_uninstall_removes_targets(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        commands_dir = claude_dir / "commands" / "myplugin"
        commands_dir.mkdir(parents=True)
        (commands_dir / "do-thing.md").write_text("# Do thing")

        manifest = claude_dir / "myplugin-file-manifest.json"
        manifest.write_text("{}")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")
        result = u.uninstall("myplugin", targets)

        assert len(result.targets_removed) == 2
        assert not commands_dir.exists()
        assert not manifest.exists()

    def test_uninstall_cleans_settings_json(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps({
            "enabledPlugins": {
                "some-org/myplugin": True,
                "other-org/otherplugin": True,
            },
            "otherSetting": "value",
        }, indent=2))

        u = PluginUninstaller(
            claude_dir=str(claude_dir),
            merkaba_dir=str(tmp_path / ".merkaba"),
            settings_path=str(settings_path),
        )
        targets = u.scan("myplugin")
        result = u.uninstall("myplugin", targets)

        assert result.settings_cleaned is True

        updated = json.loads(settings_path.read_text())
        assert "some-org/myplugin" not in updated["enabledPlugins"]
        assert "other-org/otherplugin" in updated["enabledPlugins"]
        assert updated["otherSetting"] == "value"

    def test_uninstall_preserves_other_settings(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        settings_path = claude_dir / "settings.json"
        original = {
            "enabledPlugins": {"org/myplugin": True},
            "theme": "dark",
            "fontSize": 14,
        }
        settings_path.write_text(json.dumps(original, indent=2))

        u = PluginUninstaller(
            claude_dir=str(claude_dir),
            merkaba_dir=str(tmp_path / ".merkaba"),
            settings_path=str(settings_path),
        )
        targets = u.scan("myplugin")
        u.uninstall("myplugin", targets)

        updated = json.loads(settings_path.read_text())
        assert updated["theme"] == "dark"
        assert updated["fontSize"] == 14
        assert "org/myplugin" not in updated["enabledPlugins"]

    def test_uninstall_cleans_installed_plugins(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        installed = plugins_dir / "installed_plugins.json"
        installed.write_text(json.dumps({
            "version": 2,
            "plugins": {
                "myplugin@some-org": [{"scope": "user", "version": "1.0.0"}],
                "other@some-org": [{"scope": "user", "version": "2.0.0"}],
            }
        }, indent=2))

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")
        result = u.uninstall("myplugin", targets)

        assert any(t.category == "installed-plugins" for t in result.targets_removed)
        updated = json.loads(installed.read_text())
        assert "myplugin@some-org" not in updated["plugins"]
        assert "other@some-org" in updated["plugins"]
        assert updated["version"] == 2

    def test_uninstall_removes_marketplace_dir(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        marketplace_plugin = claude_dir / "plugins" / "marketplaces" / "some-org" / "plugins" / "myplugin"
        marketplace_plugin.mkdir(parents=True)
        (marketplace_plugin / "hooks.json").write_text("{}")

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")
        result = u.uninstall("myplugin", targets)

        assert any(t.category == "marketplace" for t in result.targets_removed)
        assert not marketplace_plugin.exists()

    def test_uninstall_result_fields(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        (claude_dir / "commands" / "myplugin").mkdir(parents=True)

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        targets = u.scan("myplugin")
        result = u.uninstall("myplugin", targets)

        assert isinstance(result, UninstallResult)
        assert result.name == "myplugin"
        assert len(result.targets_found) == 1
        assert len(result.targets_removed) == 1
        assert result.settings_cleaned is False

    def test_uninstall_handles_missing_path(self, tmp_path):
        """Targets that no longer exist at removal time are skipped gracefully."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        target = UninstallTarget(
            path=str(claude_dir / "nonexistent"),
            category="commands",
            description="already gone",
        )

        u = PluginUninstaller(claude_dir=str(claude_dir), merkaba_dir=str(tmp_path / ".merkaba"))
        result = u.uninstall("myplugin", [target])

        # Should not crash, target just won't be in removed list
        assert len(result.targets_removed) == 0
