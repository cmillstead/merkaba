# src/merkaba/plugins/importer.py
"""Plugin import orchestration."""

from dataclasses import dataclass, field
from pathlib import Path

from merkaba.plugins.analyzer import SkillAnalyzer, ConversionStrategy
from merkaba.plugins.converter import SkillConverter


@dataclass
class ImportResult:
    """Result of importing a skill."""
    skill_name: str
    success: bool = False
    skipped: bool = False
    compatibility: int = 0
    conversion: str = ""
    missing_tools: set[str] = field(default_factory=set)
    error: str = ""


@dataclass
class PluginImporter:
    """Imports and converts Claude Code plugins."""

    source_dirs: list[str]
    dest_dir: str

    def find_skill(self, plugin_name: str, skill_name: str) -> Path | None:
        """Find a skill file in source directories.

        Handles nested structure: cache/org/plugin/version/skills/skill-name/SKILL.md
        """
        for source_dir in self.source_dirs:
            source_path = Path(source_dir)
            if not source_path.exists():
                continue

            # Search through org directories
            for org_path in source_path.iterdir():
                if not org_path.is_dir():
                    continue

                plugin_path = org_path / plugin_name
                if not plugin_path.exists():
                    continue

                # Find latest version
                for version_path in sorted(plugin_path.iterdir(), reverse=True):
                    if not version_path.is_dir():
                        continue

                    skill_path = version_path / "skills" / skill_name / "SKILL.md"
                    if skill_path.exists():
                        return skill_path

        return None

    def import_skill(self, plugin_name: str, skill_name: str, force: bool = False) -> ImportResult:
        """Import a single skill with conversion."""
        result = ImportResult(skill_name=skill_name)

        # Find source
        skill_path = self.find_skill(plugin_name, skill_name)
        if not skill_path:
            result.error = f"Skill not found: {plugin_name}/{skill_name}"
            return result

        content = skill_path.read_text()

        # Analyze
        analyzer = SkillAnalyzer(content)
        result.compatibility = analyzer.compatibility_score
        result.missing_tools = analyzer.missing_tools

        # Decide strategy
        if analyzer.strategy == ConversionStrategy.SKIP and not force:
            result.skipped = True
            return result

        # Convert
        converter = SkillConverter(content)

        if analyzer.strategy == ConversionStrategy.RULE_BASED:
            converted = converter.apply_rule_based()
            result.conversion = "rule_based"
        else:
            converted = converter.apply_llm_assisted()
            result.conversion = "llm_assisted"

        # Add metadata - need to update converter content first
        converter_with_converted = SkillConverter(converted)
        final_content = converter_with_converted.add_metadata(
            imported_from=plugin_name,
            compatibility=analyzer.compatibility_score,
            conversion=result.conversion,
        )

        # Write to destination
        dest_path = Path(self.dest_dir) / plugin_name / "skills" / skill_name
        dest_path.mkdir(parents=True, exist_ok=True)
        (dest_path / "SKILL.md").write_text(final_content)

        result.success = True
        return result
