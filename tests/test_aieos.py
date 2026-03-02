# tests/test_aieos.py
import json
from pathlib import Path
from merkaba.identity.aieos import import_aieos, AieosIdentity


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
