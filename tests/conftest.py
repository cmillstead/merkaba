# tests/conftest.py
"""Pytest configuration and shared fixtures."""

import pytest
import sys
from unittest.mock import MagicMock

# Install a well-behaved ollama mock BEFORE any test module tries to import it.
# Many test modules do sys.modules.setdefault("ollama", MagicMock()) at module
# level. A bare MagicMock has ResponseError/RequestError as Mock objects (not
# exception classes), which breaks ``except ollama.RequestError`` at runtime.
# By installing a mock with real exception subclasses first, all subsequent
# setdefault calls are no-ops and every test sees a consistent mock.
if "ollama" not in sys.modules:
    _ollama_mock = MagicMock()

    class _FakeResponseError(Exception):
        pass

    class _FakeRequestError(Exception):
        pass

    _ollama_mock.ResponseError = _FakeResponseError
    _ollama_mock.RequestError = _FakeRequestError
    sys.modules["ollama"] = _ollama_mock

# Track missing optional dependencies
MISSING_DEPS = []

# Check for optional dependencies
try:
    import keyring
except ImportError:
    MISSING_DEPS.append("keyring")

try:
    import frontmatter
except ImportError:
    MISSING_DEPS.append("frontmatter (python-frontmatter)")

try:
    import telegram
except ImportError:
    MISSING_DEPS.append("telegram (python-telegram-bot)")


def pytest_collection_modifyitems(config, items):
    """Skip tests that require missing dependencies."""
    if not MISSING_DEPS:
        return

    skip_marker = pytest.mark.skip(
        reason=f"Missing optional dependencies: {', '.join(MISSING_DEPS)}"
    )

    for item in items:
        # Get the module path
        module_path = str(item.fspath)

        # Try to import the test module to check for ImportError
        # If the module failed to collect, it won't be in items anyway
        # This is a safety net for modules that did collect but may have issues
        pass


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "requires_keyring: mark test as requiring keyring module"
    )
    config.addinivalue_line(
        "markers", "requires_frontmatter: mark test as requiring frontmatter module"
    )
    config.addinivalue_line(
        "markers", "requires_telegram: mark test as requiring telegram module"
    )


def pytest_runtest_setup(item):
    """Check for required dependencies before running each test."""
    for marker in item.iter_markers():
        if marker.name == "requires_keyring" and "keyring" in MISSING_DEPS:
            pytest.skip("Requires keyring module")
        elif marker.name == "requires_frontmatter" and "frontmatter (python-frontmatter)" in MISSING_DEPS:
            pytest.skip("Requires frontmatter module")
        elif marker.name == "requires_telegram" and "telegram (python-telegram-bot)" in MISSING_DEPS:
            pytest.skip("Requires telegram module")


# --- Shared fixtures ---


@pytest.fixture
def tmp_db_path(tmp_path):
    """Factory returning a fresh SQLite DB path under tmp_path."""
    def _make(name="test.db"):
        return str(tmp_path / name)
    return _make


@pytest.fixture
def memory_store(tmp_db_path):
    """Yields a MemoryStore backed by a temp SQLite DB."""
    from merkaba.memory.store import MemoryStore
    store = MemoryStore(db_path=tmp_db_path("memory.db"))
    yield store
    store.close()


@pytest.fixture
def task_queue(tmp_db_path):
    """Yields a TaskQueue backed by a temp SQLite DB."""
    from merkaba.orchestration.queue import TaskQueue
    queue = TaskQueue(db_path=tmp_db_path("tasks.db"))
    yield queue
    queue.close()


@pytest.fixture
def action_queue(tmp_db_path):
    """Yields an ActionQueue backed by a temp SQLite DB."""
    from merkaba.approval.queue import ActionQueue
    queue = ActionQueue(db_path=tmp_db_path("actions.db"))
    yield queue
    queue.close()


@pytest.fixture
def mock_ollama():
    """Return the existing ollama mock with call state reset for this test."""
    import ollama
    ollama.reset_mock()
    ollama.chat.side_effect = None
    ollama.chat.return_value = MagicMock()
    yield ollama
    ollama.chat.side_effect = None
    ollama.chat.reset_mock()


@pytest.fixture
def make_llm_response():
    """Factory returning LLMResponse objects."""
    from merkaba.llm import LLMResponse
    def _make(content="OK", model="test-model", tool_calls=None):
        return LLMResponse(content=content, model=model, tool_calls=tool_calls)
    return _make


@pytest.fixture(autouse=True)
def disable_llm_gate():
    """Disable LLM gate in all tests to avoid blocking on concurrency limits."""
    from merkaba.llm import get_llm_gate
    gate = get_llm_gate()
    gate.enabled = False
    yield
    gate.enabled = True
