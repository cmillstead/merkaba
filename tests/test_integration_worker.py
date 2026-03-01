"""Tests for the generic integration worker."""

from unittest.mock import MagicMock, patch

import pytest

from merkaba.orchestration.workers import WorkerResult


@pytest.fixture
def worker():
    from merkaba.orchestration.integration_worker import IntegrationWorker
    return IntegrationWorker(business_id=1)


class TestIntegrationWorker:
    def test_missing_adapter_name_fails(self, worker):
        result = worker.execute({"payload": {"action": "test"}})
        assert not result.success
        assert "adapter" in result.error

    def test_missing_action_fails(self, worker):
        result = worker.execute({"payload": {"adapter": "stripe"}})
        assert not result.success
        assert "action" in result.error

    def test_unknown_adapter_fails(self, worker):
        with patch("merkaba.orchestration.integration_worker.get_adapter_class", return_value=None):
            result = worker.execute({"payload": {"adapter": "nonexistent", "action": "test"}})
        assert not result.success
        assert "not found" in result.error

    def test_successful_execution(self, worker):
        mock_adapter = MagicMock()
        mock_adapter.connect.return_value = True
        mock_adapter.execute.return_value = {"balance": 100}
        mock_cls = MagicMock(return_value=mock_adapter)

        with patch("merkaba.orchestration.integration_worker.get_adapter_class", return_value=mock_cls):
            result = worker.execute({"payload": {"adapter": "stripe", "action": "get_balance"}})

        assert result.success
        assert result.output["balance"] == 100
        mock_adapter.disconnect.assert_called_once()

    def test_connect_failure(self, worker):
        mock_adapter = MagicMock()
        mock_adapter.connect.return_value = False
        mock_cls = MagicMock(return_value=mock_adapter)

        with patch("merkaba.orchestration.integration_worker.get_adapter_class", return_value=mock_cls):
            result = worker.execute({"payload": {"adapter": "stripe", "action": "test"}})

        assert not result.success
        assert "connect" in result.error.lower()
