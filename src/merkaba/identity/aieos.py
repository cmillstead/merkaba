# src/merkaba/identity/aieos.py
"""AIEOS v1.1 identity import/export.

AIEOS is an identity format used by other agent frameworks.
Import maps AIEOS JSON to Merkaba's SOUL.md format.
Export reconstructs AIEOS from SOUL.md (or round-trips from stored original).
"""

import json
import logging
import re
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


@dataclass
class ExportResult:
    success: bool
    output_path: str | None = None
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
    if merkaba_home:
        merkaba_home = Path(merkaba_home)
    else:
        from merkaba.paths import merkaba_home as _merkaba_home
        merkaba_home = Path(_merkaba_home())

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


def export_aieos(
    business_name: str,
    merkaba_home: Path | None = None,
    output_path: Path | None = None,
) -> ExportResult:
    """Export a Merkaba business identity as AIEOS v1.1 JSON.

    If identity.aieos.json exists (from a prior import), merges any SOUL.md
    edits back into the original. Otherwise, reconstructs AIEOS from SOUL.md.
    Always includes extensions.merkaba.raw_soul_md as a fallback field.
    """
    if merkaba_home:
        merkaba_home = Path(merkaba_home)
    else:
        from merkaba.paths import merkaba_home as _mh
        merkaba_home = Path(_mh())
    output_path = Path(output_path) if output_path else None

    biz_dir = merkaba_home / "businesses" / business_name
    if not biz_dir.exists():
        return ExportResult(
            success=False,
            errors=[f"Business directory not found: {biz_dir}"],
        )

    soul_path = biz_dir / "SOUL.md"
    if not soul_path.exists():
        return ExportResult(
            success=False,
            errors=[f"SOUL.md not found: {soul_path}"],
        )

    soul_text = soul_path.read_text()
    identity = _parse_soul_md(soul_text)
    stored_path = biz_dir / "identity.aieos.json"

    if stored_path.exists():
        # Round-trip: merge SOUL.md edits into stored original
        try:
            data = json.loads(stored_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return ExportResult(success=False, errors=[str(e)])
        data = _merge_identity_into_aieos(identity, data)
    else:
        # Reconstruct from SOUL.md
        data = _identity_to_aieos(identity)

    # Always include raw SOUL.md as fallback
    extensions = data.setdefault("extensions", {})
    merkaba_ext = extensions.setdefault("merkaba", {})
    merkaba_ext["raw_soul_md"] = soul_text

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2) + "\n")

    logger.info("Exported AIEOS identity '%s' to %s", identity.name, output_path)
    return ExportResult(success=True, output_path=str(output_path) if output_path else None)


def _parse_soul_md(text: str) -> AieosIdentity:
    """Parse SOUL.md text back into an AieosIdentity.

    This is the inverse of _render_soul_md — it extracts structured fields
    from the markdown format.
    """
    name = "Agent"
    description = ""
    personality = ""
    communication_style = ""
    tone = ""
    motivations: list[str] = []
    capabilities: list[str] = []

    lines = text.split("\n")
    current_section = "header"

    for line in lines:
        stripped = line.strip()

        # Top-level heading = name
        if stripped.startswith("# ") and not stripped.startswith("## "):
            name = stripped[2:].strip()
            current_section = "description"
            continue

        # Section headings
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            if heading == "personality":
                current_section = "personality"
            elif heading in ("goals", "motivations"):
                current_section = "goals"
            elif heading == "capabilities":
                current_section = "capabilities"
            else:
                current_section = "other"
            continue

        # Empty lines
        if not stripped:
            continue

        # Parse content based on section
        if current_section == "description":
            if description:
                description += "\n" + stripped
            else:
                description = stripped

        elif current_section == "personality":
            # Check for labeled lines
            tone_match = re.match(r"^Tone:\s*(.+)$", stripped)
            style_match = re.match(r"^Communication style:\s*(.+)$", stripped)
            if tone_match:
                tone = tone_match.group(1).strip()
            elif style_match:
                communication_style = style_match.group(1).strip()
            else:
                if personality:
                    personality += "\n" + stripped
                else:
                    personality = stripped

        elif current_section == "goals":
            if stripped.startswith("- "):
                motivations.append(stripped[2:])

        elif current_section == "capabilities":
            if stripped.startswith("- "):
                capabilities.append(stripped[2:])

    return AieosIdentity(
        name=name,
        description=description,
        personality=personality,
        communication_style=communication_style,
        tone=tone,
        motivations=motivations,
        capabilities=capabilities,
    )


def _identity_to_aieos(identity: AieosIdentity) -> dict:
    """Convert an AieosIdentity to an AIEOS v1.1 dict (no prior original)."""
    data: dict = {"version": "1.1"}

    data["identity"] = {"name": identity.name}
    if identity.description:
        data["identity"]["description"] = identity.description

    psych: dict = {}
    if identity.personality:
        psych["personality"] = identity.personality
    if identity.communication_style:
        psych["communication_style"] = identity.communication_style
    if psych:
        data["psychology"] = psych

    ling: dict = {}
    if identity.tone:
        ling["tone"] = identity.tone
    if ling:
        data["linguistics"] = ling

    if identity.motivations:
        data["motivations"] = identity.motivations

    if identity.capabilities:
        data["capabilities"] = identity.capabilities

    return data


def _merge_identity_into_aieos(identity: AieosIdentity, data: dict) -> dict:
    """Merge parsed SOUL.md identity fields into an existing AIEOS dict.

    Overwrites fields that SOUL.md controls while preserving everything else.
    """
    # Update identity section
    data.setdefault("identity", {})
    data["identity"]["name"] = identity.name
    if identity.description:
        data["identity"]["description"] = identity.description

    # Update psychology
    data.setdefault("psychology", {})
    if identity.personality:
        data["psychology"]["personality"] = identity.personality
    if identity.communication_style:
        data["psychology"]["communication_style"] = identity.communication_style

    # Update linguistics
    data.setdefault("linguistics", {})
    if identity.tone:
        data["linguistics"]["tone"] = identity.tone

    # Update lists
    if identity.motivations:
        data["motivations"] = identity.motivations
    if identity.capabilities:
        data["capabilities"] = identity.capabilities

    return data
