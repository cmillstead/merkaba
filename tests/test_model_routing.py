# tests/test_model_routing.py
import json
import os
import tempfile

import pytest

from merkaba.orchestration.supervisor import (
    MODEL_DEFAULTS,
    DEFAULT_MODEL,
    load_model_config,
    resolve_model,
)


@pytest.fixture
def config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _write_config(config_dir, data):
    path = os.path.join(config_dir, "config.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class TestLoadModelConfig:
    def test_defaults_when_no_config(self, config_dir):
        path = os.path.join(config_dir, "config.json")
        mapping = load_model_config(path)
        assert mapping == MODEL_DEFAULTS

    def test_defaults_when_empty_config(self, config_dir):
        path = _write_config(config_dir, {})
        mapping = load_model_config(path)
        assert mapping == MODEL_DEFAULTS

    def test_override_merges_with_defaults(self, config_dir):
        path = _write_config(config_dir, {
            "models": {"task_types": {"research": "deepseek-r1:671b"}}
        })
        mapping = load_model_config(path)
        assert mapping["research"] == "deepseek-r1:671b"
        assert mapping["health_check"] == MODEL_DEFAULTS["health_check"]

    def test_new_task_type_from_config(self, config_dir):
        path = _write_config(config_dir, {
            "models": {"task_types": {"coding": "qwen3-coder:30b"}}
        })
        mapping = load_model_config(path)
        assert mapping["coding"] == "qwen3-coder:30b"
        # Defaults still present
        assert mapping["health_check"] == MODEL_DEFAULTS["health_check"]

    def test_corrupt_json_falls_back(self, config_dir):
        path = os.path.join(config_dir, "config.json")
        with open(path, "w") as f:
            f.write("{bad json")
        mapping = load_model_config(path)
        assert mapping == MODEL_DEFAULTS


class TestResolveModel:
    def test_known_task_type(self, config_dir):
        path = os.path.join(config_dir, "config.json")
        assert resolve_model("health_check", path) == "phi4:14b"

    def test_unknown_task_type_falls_back(self, config_dir):
        path = os.path.join(config_dir, "config.json")
        assert resolve_model("unknown_type", path) == DEFAULT_MODEL

    def test_override_from_config(self, config_dir):
        path = _write_config(config_dir, {
            "models": {"task_types": {"research": "deepseek-r1:671b"}}
        })
        assert resolve_model("research", path) == "deepseek-r1:671b"


class TestSupervisorModelRouting:
    def test_build_worker_uses_routed_model(self, config_dir):
        from unittest.mock import MagicMock, patch
        from merkaba.orchestration.supervisor import Supervisor

        config_path = _write_config(config_dir, {
            "models": {"task_types": {"research": "deepseek-r1:671b"}}
        })

        store = MagicMock()
        store.get_facts.return_value = []
        supervisor = Supervisor(
            memory_store=store,
            config_path=config_path,
        )

        mock_worker_cls = MagicMock()
        task = {"id": 1, "name": "test", "task_type": "research", "autonomy_level": 1}
        supervisor._build_worker(mock_worker_cls, task)

        call_kwargs = mock_worker_cls.call_args[1]
        assert call_kwargs["model"] == "deepseek-r1:671b"

    def test_build_worker_falls_back_for_unknown(self, config_dir):
        from unittest.mock import MagicMock
        from merkaba.orchestration.supervisor import Supervisor

        config_path = os.path.join(config_dir, "config.json")
        store = MagicMock()
        supervisor = Supervisor(
            memory_store=store,
            config_path=config_path,
        )

        mock_worker_cls = MagicMock()
        task = {"id": 1, "name": "test", "task_type": "brand_new_type", "autonomy_level": 1}
        supervisor._build_worker(mock_worker_cls, task)

        call_kwargs = mock_worker_cls.call_args[1]
        assert call_kwargs["model"] == DEFAULT_MODEL
