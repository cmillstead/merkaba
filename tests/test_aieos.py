# tests/test_aieos.py
import json
from pathlib import Path
from merkaba.identity.aieos import (
    import_aieos,
    export_aieos,
    AieosIdentity,
    ExportResult,
)


def test_import_basic_identity(tmp_path):
    """Import basic AIEOS identity creates SOUL.md."""
    aieos_data = {
        "version": "1.1",
        "identity": {
            "name": "TestAgent",
            "description": "A test agent for unit testing."
        },
        "psychology": {
            "personality": "Friendly and helpful",
            "communication_style": "Direct and concise"
        },
        "linguistics": {
            "tone": "professional",
            "vocabulary_level": "moderate"
        },
        "motivations": ["Help users accomplish goals", "Learn from interactions"],
    }
    aieos_file = tmp_path / "identity.json"
    aieos_file.write_text(json.dumps(aieos_data))

    merkaba_home = tmp_path / "merkaba"
    result = import_aieos(aieos_file, "testbiz", merkaba_home=merkaba_home)

    soul_path = merkaba_home / "businesses" / "testbiz" / "SOUL.md"
    assert soul_path.exists()
    soul_content = soul_path.read_text()
    assert "TestAgent" in soul_content
    assert "Friendly and helpful" in soul_content
    assert result.success


def test_import_stores_original(tmp_path):
    """Import stores original AIEOS JSON for round-trip."""
    aieos_data = {"version": "1.1", "identity": {"name": "Agent"}}
    aieos_file = tmp_path / "identity.json"
    aieos_file.write_text(json.dumps(aieos_data))

    merkaba_home = tmp_path / "merkaba"
    import_aieos(aieos_file, "testbiz", merkaba_home=merkaba_home)

    stored = merkaba_home / "businesses" / "testbiz" / "identity.aieos.json"
    assert stored.exists()
    assert json.loads(stored.read_text())["identity"]["name"] == "Agent"


def test_import_missing_file(tmp_path):
    """Import nonexistent file returns failure."""
    result = import_aieos(tmp_path / "nope.json", "testbiz", merkaba_home=tmp_path / "merkaba")
    assert not result.success


def test_import_with_capabilities(tmp_path):
    """Capabilities are stored in SOUL.md."""
    aieos_data = {
        "version": "1.1",
        "identity": {"name": "CapAgent"},
        "capabilities": ["web_search", "code_generation", "data_analysis"],
    }
    aieos_file = tmp_path / "identity.json"
    aieos_file.write_text(json.dumps(aieos_data))

    merkaba_home = tmp_path / "merkaba"
    import_aieos(aieos_file, "testbiz", merkaba_home=merkaba_home)

    soul = (merkaba_home / "businesses" / "testbiz" / "SOUL.md").read_text()
    assert "web_search" in soul or "Capabilities" in soul


# --- Export tests ---


def _make_aieos_data(**overrides):
    """Helper to create a complete AIEOS identity dict."""
    data = {
        "version": "1.1",
        "identity": {
            "name": "TestAgent",
            "description": "A test agent for export testing.",
        },
        "psychology": {
            "personality": "Analytical and thorough",
            "communication_style": "Clear and structured",
        },
        "linguistics": {
            "tone": "professional",
            "vocabulary_level": "advanced",
        },
        "motivations": ["Solve problems", "Learn continuously"],
        "capabilities": ["code_generation", "web_search"],
    }
    data.update(overrides)
    return data


def _setup_imported_business(tmp_path, aieos_data=None, business_name="testbiz"):
    """Import an AIEOS identity and return (merkaba_home, biz_dir)."""
    if aieos_data is None:
        aieos_data = _make_aieos_data()
    aieos_file = tmp_path / "source.json"
    aieos_file.write_text(json.dumps(aieos_data))
    merkaba_home = tmp_path / "merkaba"
    import_aieos(aieos_file, business_name, merkaba_home=merkaba_home)
    biz_dir = merkaba_home / "businesses" / business_name
    return merkaba_home, biz_dir


def test_export_produces_valid_json(tmp_path):
    """Export from an imported identity produces valid AIEOS JSON."""
    merkaba_home, _ = _setup_imported_business(tmp_path)
    output = tmp_path / "exported.json"

    result = export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)

    assert result.success
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["version"] == "1.1"
    assert data["identity"]["name"] == "TestAgent"
    assert data["identity"]["description"] == "A test agent for export testing."


def test_export_round_trip_preserves_original_fields(tmp_path):
    """Round-trip (import then export) preserves all original AIEOS fields."""
    original = _make_aieos_data()
    # Add extra fields that SOUL.md doesn't capture
    original["linguistics"]["vocabulary_level"] = "advanced"
    original["custom_field"] = {"nested": "data"}

    merkaba_home, _ = _setup_imported_business(tmp_path, aieos_data=original)
    output = tmp_path / "exported.json"

    export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)
    exported = json.loads(output.read_text())

    # Original fields that exist outside SOUL.md are preserved
    assert exported["linguistics"]["vocabulary_level"] == "advanced"
    assert exported["custom_field"] == {"nested": "data"}
    assert exported["version"] == "1.1"


def test_export_includes_raw_soul_md(tmp_path):
    """Export includes extensions.merkaba.raw_soul_md with full SOUL.md text."""
    merkaba_home, biz_dir = _setup_imported_business(tmp_path)
    output = tmp_path / "exported.json"

    export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)
    exported = json.loads(output.read_text())

    soul_text = (biz_dir / "SOUL.md").read_text()
    assert "extensions" in exported
    assert "merkaba" in exported["extensions"]
    assert exported["extensions"]["merkaba"]["raw_soul_md"] == soul_text


def test_export_without_prior_import(tmp_path):
    """Export without prior import reconstructs AIEOS from SOUL.md."""
    merkaba_home = tmp_path / "merkaba"
    biz_dir = merkaba_home / "businesses" / "frombiz"
    biz_dir.mkdir(parents=True)

    soul_content = """# ReconstructedAgent

An agent built from scratch.

## Personality

Creative and adaptive

Communication style: Warm and casual

Tone: friendly

## Goals
- Assist with creative tasks
- Generate new ideas

## Capabilities
- text_generation
- brainstorming
"""
    (biz_dir / "SOUL.md").write_text(soul_content)
    output = tmp_path / "exported.json"

    result = export_aieos("frombiz", merkaba_home=merkaba_home, output_path=output)

    assert result.success
    data = json.loads(output.read_text())
    assert data["version"] == "1.1"
    assert data["identity"]["name"] == "ReconstructedAgent"
    assert data["identity"]["description"] == "An agent built from scratch."
    assert data["psychology"]["personality"] == "Creative and adaptive"
    assert data["psychology"]["communication_style"] == "Warm and casual"
    assert data["linguistics"]["tone"] == "friendly"
    assert "Assist with creative tasks" in data["motivations"]
    assert "text_generation" in data["capabilities"]
    assert data["extensions"]["merkaba"]["raw_soul_md"] == soul_content


def test_export_merges_soul_md_changes(tmp_path):
    """Export merges SOUL.md edits back into stored AIEOS JSON."""
    merkaba_home, biz_dir = _setup_imported_business(tmp_path)

    # Simulate user editing SOUL.md after import
    soul_path = biz_dir / "SOUL.md"
    soul_content = soul_path.read_text()
    # Change the name and description
    soul_content = soul_content.replace("TestAgent", "UpdatedAgent")
    soul_path.write_text(soul_content)

    output = tmp_path / "exported.json"
    export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)
    exported = json.loads(output.read_text())

    # Merged: name from edited SOUL.md
    assert exported["identity"]["name"] == "UpdatedAgent"
    # Original fields preserved
    assert exported["version"] == "1.1"


def test_export_missing_business(tmp_path):
    """Export for nonexistent business returns failure."""
    merkaba_home = tmp_path / "merkaba"
    output = tmp_path / "exported.json"

    result = export_aieos("nonexistent", merkaba_home=merkaba_home, output_path=output)

    assert not result.success
    assert len(result.errors) > 0
    assert not output.exists()


def test_export_missing_soul_md(tmp_path):
    """Export with business dir but no SOUL.md returns failure."""
    merkaba_home = tmp_path / "merkaba"
    biz_dir = merkaba_home / "businesses" / "empty"
    biz_dir.mkdir(parents=True)
    output = tmp_path / "exported.json"

    result = export_aieos("empty", merkaba_home=merkaba_home, output_path=output)

    assert not result.success
    assert len(result.errors) > 0


def test_export_result_contains_output_path(tmp_path):
    """ExportResult includes the output file path on success."""
    merkaba_home, _ = _setup_imported_business(tmp_path)
    output = tmp_path / "exported.json"

    result = export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)

    assert result.success
    assert result.output_path == str(output)


def test_export_psychology_and_linguistics(tmp_path):
    """Export correctly maps personality/tone fields to AIEOS sections."""
    merkaba_home, _ = _setup_imported_business(tmp_path)
    output = tmp_path / "exported.json"

    export_aieos("testbiz", merkaba_home=merkaba_home, output_path=output)
    exported = json.loads(output.read_text())

    assert "psychology" in exported
    assert "linguistics" in exported
    assert exported["psychology"]["personality"] == "Analytical and thorough"
    assert exported["psychology"]["communication_style"] == "Clear and structured"
    assert exported["linguistics"]["tone"] == "professional"
