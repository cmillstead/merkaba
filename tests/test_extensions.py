"""Tests for entry point discovery of workers, adapters, and CLI extensions."""

import importlib.metadata
from unittest.mock import MagicMock, patch

import pytest


def _make_entry_point(name, value, group):
    """Create a mock entry point."""
    ep = MagicMock(spec=importlib.metadata.EntryPoint)
    ep.name = name
    ep.value = value
    ep.group = group
    return ep


class TestDiscoverWorkers:
    def test_loads_worker_from_entry_point(self):
        from merkaba.extensions import discover_workers
        from merkaba.orchestration.workers import WORKER_REGISTRY

        mock_cls = MagicMock()
        ep = _make_entry_point("test_task", "my_pkg.workers:TestWorker", "merkaba.workers")
        ep.load.return_value = mock_cls

        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            discover_workers()

        assert "test_task" in WORKER_REGISTRY
        assert WORKER_REGISTRY["test_task"] is mock_cls

        # Cleanup
        del WORKER_REGISTRY["test_task"]

    def test_skips_failed_worker_import(self):
        from merkaba.extensions import discover_workers
        from merkaba.orchestration.workers import WORKER_REGISTRY

        ep = _make_entry_point("bad_worker", "bad_pkg:Bad", "merkaba.workers")
        ep.load.side_effect = ImportError("no such module")

        before = dict(WORKER_REGISTRY)
        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            discover_workers()  # should not raise

        assert WORKER_REGISTRY == before


class TestDiscoverAdapters:
    def test_loads_adapter_from_entry_point(self):
        from merkaba.extensions import discover_adapters
        from merkaba.integrations.base import ADAPTER_REGISTRY

        mock_cls = MagicMock()
        ep = _make_entry_point("test_svc", "my_pkg.adapters:TestAdapter", "merkaba.adapters")
        ep.load.return_value = mock_cls

        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            discover_adapters()

        assert "test_svc" in ADAPTER_REGISTRY
        assert ADAPTER_REGISTRY["test_svc"] is mock_cls

        # Cleanup
        del ADAPTER_REGISTRY["test_svc"]

    def test_skips_failed_adapter_import(self):
        from merkaba.extensions import discover_adapters
        from merkaba.integrations.base import ADAPTER_REGISTRY

        ep = _make_entry_point("bad_adapter", "bad_pkg:Bad", "merkaba.adapters")
        ep.load.side_effect = ImportError("no such module")

        before = dict(ADAPTER_REGISTRY)
        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            discover_adapters()

        assert ADAPTER_REGISTRY == before


class TestDiscoverCli:
    def test_loads_cli_app_from_entry_point(self):
        from merkaba.extensions import discover_cli_apps

        mock_app = MagicMock()
        ep = _make_entry_point("my_biz", "my_pkg.cli:app", "merkaba.cli")
        ep.load.return_value = mock_app

        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            apps = discover_cli_apps()

        assert apps["my_biz"] is mock_app

    def test_skips_failed_cli_import(self):
        from merkaba.extensions import discover_cli_apps

        ep = _make_entry_point("bad_cli", "bad_pkg:app", "merkaba.cli")
        ep.load.side_effect = ImportError("nope")

        with patch("merkaba.extensions._get_entry_points", return_value=[ep]):
            apps = discover_cli_apps()

        assert "bad_cli" not in apps
