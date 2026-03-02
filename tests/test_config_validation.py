# tests/test_config_validation.py
from pathlib import Path
from merkaba.config.validation import validate_config, Severity


def test_clean_config_no_issues(tmp_path):
    config = {"models": {"simple": "qwen3:8b", "complex": "qwen3.5:122b"}}
    issues = validate_config(config, tmp_path, _skip_runtime_checks=True)
    assert len(issues) == 0


def test_missing_model_routing_warns(tmp_path):
    config = {"models": {}}
    issues = validate_config(config, tmp_path, _skip_runtime_checks=True)
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    assert any("routing" in i.component for i in warnings)


def test_high_auto_approve_warns(tmp_path):
    config = {"auto_approve_level": "DESTRUCTIVE", "models": {"simple": "a", "complex": "b"}}
    issues = validate_config(config, tmp_path, _skip_runtime_checks=True)
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    assert any("auto_approve" in i.message.lower() or "security" in i.component for i in warnings)


def test_missing_soul_md_warns(tmp_path):
    biz_dir = tmp_path / "businesses" / "testbiz"
    biz_dir.mkdir(parents=True)
    config = {"models": {"simple": "a", "complex": "b"}}
    issues = validate_config(config, tmp_path, _skip_runtime_checks=True)
    assert any("SOUL.md" in i.message for i in issues)


def test_print_startup_report_no_crash(capsys):
    from merkaba.config.validation import print_startup_report, ConfigIssue
    issues = [
        ConfigIssue(Severity.ERROR, "llm", "No LLM", "Start ollama"),
        ConfigIssue(Severity.WARNING, "memory", "No ChromaDB"),
        ConfigIssue(Severity.INFO, "security", "Encryption disabled"),
    ]
    print_startup_report(issues)
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "WARNING" in captured.out
