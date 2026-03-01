# src/friday/plugins/uninstaller.py
"""Plugin uninstaller — scan and remove plugin artifacts from Claude Code and Friday."""

import glob
import json
import logging
import os
import shutil
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class UninstallTarget:
    """A file or directory that belongs to a plugin."""
    path: str
    category: str       # e.g. "commands", "agents", "plugin-cache", "framework", "manifest", "cache", "friday-import"
    description: str    # human-readable, e.g. "command directory"


@dataclass
class UninstallResult:
    """Result of an uninstall operation."""
    name: str
    targets_found: list[UninstallTarget] = field(default_factory=list)
    targets_removed: list[UninstallTarget] = field(default_factory=list)
    settings_cleaned: bool = False


class PluginUninstaller:
    """Scans for and removes plugin artifacts across Claude Code and Friday directories."""

    def __init__(
        self,
        claude_dir: str | None = None,
        friday_dir: str | None = None,
        settings_path: str | None = None,
    ):
        self.claude_dir = claude_dir or os.path.expanduser("~/.claude")
        self.friday_dir = friday_dir or os.path.expanduser("~/.friday")
        self.settings_path = settings_path or os.path.join(self.claude_dir, "settings.json")

    def scan(self, name: str) -> list[UninstallTarget]:
        """Find all files/dirs matching this plugin name. Read-only."""
        targets: list[UninstallTarget] = []

        # 1. Commands: ~/.claude/commands/{name}/
        commands_dir = os.path.join(self.claude_dir, "commands", name)
        if os.path.isdir(commands_dir):
            targets.append(UninstallTarget(
                path=commands_dir,
                category="commands",
                description=f"command directory",
            ))

        # 2. Agents: ~/.claude/agents/{name}-*.md
        agents_dir = os.path.join(self.claude_dir, "agents")
        if os.path.isdir(agents_dir):
            pattern = os.path.join(agents_dir, f"{name}-*.md")
            for agent_file in sorted(glob.glob(pattern)):
                targets.append(UninstallTarget(
                    path=agent_file,
                    category="agents",
                    description="agent file",
                ))

        # 3. Plugin cache: ~/.claude/plugins/cache/*/{name}/
        cache_base = os.path.join(self.claude_dir, "plugins", "cache")
        if os.path.isdir(cache_base):
            for org_dir in _iter_dirs(cache_base):
                plugin_dir = os.path.join(org_dir, name)
                if os.path.isdir(plugin_dir):
                    targets.append(UninstallTarget(
                        path=plugin_dir,
                        category="plugin-cache",
                        description="plugin cache directory",
                    ))

        # 4. Framework dirs: ~/.claude/{name}-framework/
        framework_dir = os.path.join(self.claude_dir, f"{name}-framework")
        if os.path.isdir(framework_dir):
            targets.append(UninstallTarget(
                path=framework_dir,
                category="framework",
                description="framework directory",
            ))

        # 4b. Also check ~/.claude/{name}/ (heuristic — only non-standard dirs)
        bare_dir = os.path.join(self.claude_dir, name)
        if os.path.isdir(bare_dir) and name not in (
            "commands", "agents", "plugins", "projects", "cache",
            "debug", "worktrees", "etc", "var", "usr", "System", "Library",
        ):
            targets.append(UninstallTarget(
                path=bare_dir,
                category="framework",
                description="plugin directory",
            ))

        # 5. Manifests: ~/.claude/{name}-file-manifest.json
        manifest_path = os.path.join(self.claude_dir, f"{name}-file-manifest.json")
        if os.path.isfile(manifest_path):
            targets.append(UninstallTarget(
                path=manifest_path,
                category="manifest",
                description="file manifest",
            ))

        # 6. Cache files: ~/.claude/cache/{name}-*.json
        cache_dir = os.path.join(self.claude_dir, "cache")
        if os.path.isdir(cache_dir):
            pattern = os.path.join(cache_dir, f"{name}-*.json")
            for cache_file in sorted(glob.glob(pattern)):
                targets.append(UninstallTarget(
                    path=cache_file,
                    category="cache",
                    description="cache file",
                ))

        # 7. Friday imports: ~/.friday/plugins/{name}/
        friday_plugin_dir = os.path.join(self.friday_dir, "plugins", name)
        if os.path.isdir(friday_plugin_dir):
            targets.append(UninstallTarget(
                path=friday_plugin_dir,
                category="friday-import",
                description="Friday plugin import",
            ))

        # 8. Check settings.json for enabledPlugins reference
        if self._has_settings_entry(name):
            targets.append(UninstallTarget(
                path=self.settings_path,
                category="settings",
                description="enabledPlugins entry in settings.json",
            ))

        # 9. installed_plugins.json entry
        installed_path = os.path.join(self.claude_dir, "plugins", "installed_plugins.json")
        if self._has_installed_entry(name, installed_path):
            targets.append(UninstallTarget(
                path=installed_path,
                category="installed-plugins",
                description="entry in installed_plugins.json",
            ))

        # 10. Marketplace metadata: ~/.claude/plugins/marketplaces/*/plugins/{name}/
        marketplaces_dir = os.path.join(self.claude_dir, "plugins", "marketplaces")
        if os.path.isdir(marketplaces_dir):
            for marketplace in _iter_dirs(marketplaces_dir):
                plugin_meta = os.path.join(marketplace, "plugins", name)
                if os.path.isdir(plugin_meta):
                    targets.append(UninstallTarget(
                        path=plugin_meta,
                        category="marketplace",
                        description="marketplace metadata",
                    ))

        return targets

    def uninstall(self, name: str, targets: list[UninstallTarget]) -> UninstallResult:
        """Remove the given targets and clean settings.json."""
        result = UninstallResult(name=name, targets_found=list(targets))

        for target in targets:
            if target.category == "settings":
                if self._clean_settings(name):
                    result.settings_cleaned = True
                    result.targets_removed.append(target)
                continue

            if target.category == "installed-plugins":
                if self._clean_installed_plugins(name, target.path):
                    result.targets_removed.append(target)
                continue

            try:
                if os.path.isdir(target.path):
                    shutil.rmtree(target.path)
                    result.targets_removed.append(target)
                elif os.path.isfile(target.path):
                    os.remove(target.path)
                    result.targets_removed.append(target)
                else:
                    logger.debug("Already gone: %s", target.path)
                    continue
                logger.debug("Removed %s: %s", target.category, target.path)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", target.path, e)

        return result

    def _has_installed_entry(self, name: str, path: str) -> bool:
        """Check if installed_plugins.json has an entry matching name."""
        if not os.path.isfile(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            plugins = data.get("plugins", {})
            return any(name in key for key in plugins)
        except (json.JSONDecodeError, OSError):
            return False

    def _clean_installed_plugins(self, name: str, path: str) -> bool:
        """Remove entries matching name from installed_plugins.json."""
        if not os.path.isfile(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)

            plugins = data.get("plugins", {})
            keys_to_remove = [key for key in plugins if name in key]
            if not keys_to_remove:
                return False

            for key in keys_to_remove:
                del plugins[key]

            with open(path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")

            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to clean installed_plugins.json: %s", e)
            return False

    def _has_settings_entry(self, name: str) -> bool:
        """Check if settings.json has an enabledPlugins entry matching name."""
        if not os.path.isfile(self.settings_path):
            return False
        try:
            with open(self.settings_path) as f:
                settings = json.load(f)
            enabled = settings.get("enabledPlugins", {})
            return any(name in key for key in enabled)
        except (json.JSONDecodeError, OSError):
            return False

    def _clean_settings(self, name: str) -> bool:
        """Remove enabledPlugins entries matching name from settings.json."""
        if not os.path.isfile(self.settings_path):
            return False
        try:
            with open(self.settings_path) as f:
                settings = json.load(f)

            enabled = settings.get("enabledPlugins", {})
            keys_to_remove = [key for key in enabled if name in key]
            if not keys_to_remove:
                return False

            for key in keys_to_remove:
                del enabled[key]

            with open(self.settings_path, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")

            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to clean settings.json: %s", e)
            return False


def _iter_dirs(parent: str):
    """Yield full paths of immediate subdirectories."""
    try:
        for entry in os.scandir(parent):
            if entry.is_dir():
                yield entry.path
    except OSError:
        pass
