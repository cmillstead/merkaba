# src/merkaba/identity/aieos.py
"""AIEOS v1.1 identity import/export.

AIEOS is an identity format used by other agent frameworks.
Import maps AIEOS JSON to Merkaba's SOUL.md format.
Export reconstructs AIEOS from SOUL.md (or round-trips from stored original).
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AieosIdentity:
    name: str
    description: str = ""
    personality: str = ""
    communication_style: str = ""
    tone: str = ""
    motivations: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    success: bool
    soul_md_path: str | None = None
    errors: list[str] = field(default_factory=list)


def import_aieos(
    aieos_path: Path,
    business_name: str,
    merkaba_home: Path | None = None,
) -> ImportResult:
    """Import an AIEOS v1.1 JSON file into a Merkaba business.

    Creates SOUL.md from the identity data and stores the original
    JSON for lossless round-trip on export.
    """
    merkaba_home = Path(merkaba_home) if merkaba_home else Path("~/.merkaba").expanduser()

    try:
        data = json.loads(Path(aieos_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        return ImportResult(success=False, errors=[str(e)])

    # Parse identity
    identity = _parse_identity(data)

    # Create business directory
    biz_dir = merkaba_home / "businesses" / business_name
    biz_dir.mkdir(parents=True, exist_ok=True)

    # Generate SOUL.md
    soul_content = _render_soul_md(identity)
    soul_path = biz_dir / "SOUL.md"
    soul_path.write_text(soul_content)

    # Store original for round-trip
    stored_path = biz_dir / "identity.aieos.json"
    shutil.copy2(aieos_path, stored_path)

    logger.info("Imported AIEOS identity '%s' to %s", identity.name, biz_dir)
    return ImportResult(success=True, soul_md_path=str(soul_path))


def _parse_identity(data: dict) -> AieosIdentity:
    """Parse AIEOS JSON into an AieosIdentity."""
    identity_data = data.get("identity", {})
    psych = data.get("psychology", {})
    ling = data.get("linguistics", {})

    return AieosIdentity(
        name=identity_data.get("name", "Agent"),
        description=identity_data.get("description", ""),
        personality=psych.get("personality", ""),
        communication_style=psych.get("communication_style", ""),
        tone=ling.get("tone", ""),
        motivations=data.get("motivations", []),
        capabilities=data.get("capabilities", []),
    )


def _render_soul_md(identity: AieosIdentity) -> str:
    """Render an AieosIdentity as SOUL.md content."""
    sections = [f"# {identity.name}"]

    if identity.description:
        sections.append(f"\n{identity.description}")

    if identity.personality or identity.communication_style:
        sections.append("\n## Personality")
        if identity.personality:
            sections.append(f"\n{identity.personality}")
        if identity.communication_style:
            sections.append(f"\nCommunication style: {identity.communication_style}")

    if identity.tone:
        sections.append(f"\nTone: {identity.tone}")

    if identity.motivations:
        sections.append("\n## Goals")
        for m in identity.motivations:
            sections.append(f"- {m}")

    if identity.capabilities:
        sections.append("\n## Capabilities")
        for c in identity.capabilities:
            sections.append(f"- {c}")

    return "\n".join(sections) + "\n"
