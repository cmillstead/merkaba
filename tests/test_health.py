# tests/test_health.py
import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from merkaba.orchestration.health import HealthCheck, HealthReport, SystemHealthMonitor


def test_health_report_healthy_when_all_ok():
    report = HealthReport(checks=[
        HealthCheck("a", True, "good"),
        HealthCheck("b", True, "fine"),
    ])
    assert report.healthy is True


def test_health_report_unhealthy_when_any_fail():
    report = HealthReport(checks=[
        HealthCheck("a", True, "good"),
        HealthCheck("b", False, "bad"),
    ])
    assert report.healthy is False


def test_health_report_to_dict():
    report = HealthReport(checks=[
        HealthCheck("test", True, "ok"),
    ])
    d = report.to_dict()
    assert d["healthy"] is True
    assert len(d["checks"]) == 1
    assert d["checks"][0] == {"name": "test", "ok": True, "detail": "ok"}


def test_check_db_ok():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.close()

        monitor = SystemHealthMonitor(merkaba_dir=tmp)
        check = monitor.check_db("test.db")
        assert check.ok is True
        assert check.detail == "ok"


def test_check_db_missing_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = SystemHealthMonitor(merkaba_dir=tmp)
        check = monitor.check_db("nonexistent.db")
        assert check.ok is True
        assert "not created yet" in check.detail


def test_check_disk_space():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = SystemHealthMonitor(merkaba_dir=tmp)
        check = monitor.check_disk_space()
        assert check.name == "disk"
        assert "% used" in check.detail


def test_check_ollama_unreachable():
    monitor = SystemHealthMonitor(ollama_url="http://localhost:99999")
    check = monitor.check_ollama()
    assert check.ok is False
    assert "unreachable" in check.detail


def test_check_all_returns_report():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = SystemHealthMonitor(merkaba_dir=tmp, ollama_url="http://localhost:99999")
        report = monitor.check_all()
        assert isinstance(report, HealthReport)
        assert len(report.checks) >= 4
        names = [c.name for c in report.checks]
        assert "ollama" in names
        assert "disk" in names
