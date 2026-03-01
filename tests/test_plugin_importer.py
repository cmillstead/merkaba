# tests/test_plugin_importer.py
import pytest
from pathlib import Path

# Check if required dependencies are available
try:
    from merkaba.plugins.importer import PluginImporter, ImportResult
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    PluginImporter = None
    ImportResult = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestPluginImporter:
    def test_import_high_compatibility_skill(self, tmp_path):
        # Create source skill (org/plugin/version/skills/skill-name structure)
        source_dir = tmp_path / "source" / "test-org" / "myplugin" / "1.0.0" / "skills" / "myskill"
        source_dir.mkdir(parents=True)
        (source_dir / "SKILL.md").write_text("""---
name: myskill
description: A simple helper
---
# My Helper

Use file_read to check files.
""")

        dest_dir = tmp_path / "dest"
        importer = PluginImporter(
            source_dirs=[str(tmp_path / "source")],
            dest_dir=str(dest_dir),
        )

        result = importer.import_skill("myplugin", "myskill")

        assert result.success is True
        assert result.compatibility == 100
        assert (dest_dir / "myplugin" / "skills" / "myskill" / "SKILL.md").exists()

    def test_skip_low_compatibility_skill(self, tmp_path):
        # Create source skill with unsupported tools (WebSearch has weight 0)
        source_dir = tmp_path / "source" / "test-org" / "myplugin" / "1.0.0" / "skills" / "searchskill"
        source_dir.mkdir(parents=True)
        (source_dir / "SKILL.md").write_text("""---
name: searchskill
description: Needs web search
---
# Search helper

Use WebSearch to find information online.
""")

        dest_dir = tmp_path / "dest"
        importer = PluginImporter(
            source_dirs=[str(tmp_path / "source")],
            dest_dir=str(dest_dir),
        )

        result = importer.import_skill("myplugin", "searchskill")

        assert result.success is False
        assert result.skipped is True
        assert "WebSearch" in result.missing_tools
