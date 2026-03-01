# tests/test_heartbeat.py
import sys
import tempfile
import os
from unittest.mock import MagicMock

import pytest
from merkaba.orchestration.queue import TaskQueue
from merkaba.orchestration.heartbeat import Heartbeat


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        q = TaskQueue(db_path=db_path)
        yield q
        q.close()


@pytest.fixture
def heartbeat(queue):
    return Heartbeat(queue=queue)


@pytest.fixture
def mock_ollama():
    """Inject a mock ollama module so the lazy import inside check() picks it up."""
    mock = MagicMock()
    original = sys.modules.get("ollama")
    sys.modules["ollama"] = mock
    yield mock
    if original is not None:
        sys.modules["ollama"] = original
    else:
        del sys.modules["ollama"]


# --- Response parsing ---


def test_parse_idle(heartbeat):
    assert heartbeat._parse_response("IDLE") == "IDLE"


def test_parse_idle_with_extra(heartbeat):
    assert heartbeat._parse_response("IDLE\nNothing to do.") == "IDLE"


def test_parse_investigate(heartbeat):
    result = heartbeat._parse_response("INVESTIGATE failed email delivery")
    assert result == "INVESTIGATE failed email delivery"


def test_parse_act(heartbeat):
    result = heartbeat._parse_response("ACT retry failed tasks")
    assert result == "ACT retry failed tasks"


def test_parse_with_thinking_prefix(heartbeat):
    raw = "<think>\nLet me analyze...\n</think>\nIDLE"
    assert heartbeat._parse_response(raw) == "IDLE"


def test_parse_unparseable_returns_idle(heartbeat):
    assert heartbeat._parse_response("I'm not sure what to do") == "IDLE"


# --- check() with mocked Ollama ---


def test_check_idle(mock_ollama, heartbeat):
    mock_ollama.chat.return_value = {
        "message": {"content": "IDLE"}
    }
    result = heartbeat.check()
    assert result == "IDLE"
    mock_ollama.chat.assert_called_once()


def test_check_investigate(mock_ollama, heartbeat):
    mock_ollama.chat.return_value = {
        "message": {"content": "INVESTIGATE high failure rate in email tasks"}
    }
    result = heartbeat.check()
    assert result == "INVESTIGATE high failure rate in email tasks"


def test_check_act(mock_ollama, heartbeat):
    mock_ollama.chat.return_value = {
        "message": {"content": "ACT retry task 5"}
    }
    result = heartbeat.check()
    assert result == "ACT retry task 5"


def test_check_model_error_returns_idle(mock_ollama, heartbeat):
    mock_ollama.chat.side_effect = Exception("Connection refused")
    result = heartbeat.check()
    assert result == "IDLE"


def test_check_includes_failed_tasks_in_context(mock_ollama, queue, heartbeat):
    task_id = queue.add_task("Email Check", "check")
    queue.update_task(task_id, status="failed")

    mock_ollama.chat.return_value = {
        "message": {"content": "INVESTIGATE email failures"}
    }

    heartbeat.check()

    call_args = mock_ollama.chat.call_args
    prompt = call_args[1]["messages"][0]["content"]
    assert "Email Check" in prompt


def test_check_includes_recent_runs(mock_ollama, queue, heartbeat):
    task_id = queue.add_task("Task", "check")
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "success")

    mock_ollama.chat.return_value = {
        "message": {"content": "IDLE"}
    }

    heartbeat.check()

    call_args = mock_ollama.chat.call_args
    prompt = call_args[1]["messages"][0]["content"]
    assert "task_id=" in prompt


# --- Integration test (requires Ollama running) ---


@pytest.mark.integration
def test_heartbeat_integration(queue):
    """Test heartbeat with real Ollama model. Requires Ollama running with qwen3:4b."""
    heartbeat = Heartbeat(queue=queue)
    result = heartbeat.check()
    assert result.startswith(("IDLE", "INVESTIGATE", "ACT"))
