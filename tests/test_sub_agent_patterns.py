# tests/test_sub_agent_patterns.py
"""Tests for Phase 5: Sub-Agent Patterns — dispatch modes, exploration, integration, competition."""

import os
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ollama", MagicMock())

from merkaba.orchestration.explorer import (
    ExplorationAgent,
    ExplorationOrchestrator,
    ExplorationResult,
    MAX_DIR_DEPTH,
)
from merkaba.orchestration.workers import (
    Worker,
    WorkerResult,
    register_worker,
    WORKER_REGISTRY,
)
from merkaba.orchestration.supervisor import (
    DispatchMode,
    Supervisor,
    SIMPLE_TASK_TYPES,
    CREATIVE_TASK_TYPES,
)


# --- Stub workers ---


@dataclass
class StubContentWorker(Worker):
    def execute(self, task):
        payload = task.get("payload") or {}
        variant = payload.get("_variant_id", -1)
        return WorkerResult(
            success=True,
            output={"draft": f"content from variant {variant}", "variant": variant},
        )


@dataclass
class IntegrationStubWorker(Worker):
    def execute(self, task):
        return WorkerResult(success=True, output={"connected": True})


@pytest.fixture(autouse=True)
def register_test_workers():
    register_worker("_sub_content", StubContentWorker)
    register_worker("_sub_integration", IntegrationStubWorker)
    yield
    WORKER_REGISTRY.pop("_sub_content", None)
    WORKER_REGISTRY.pop("_sub_integration", None)


@pytest.fixture
def supervisor(memory_store):
    sup = Supervisor(memory_store=memory_store)
    yield sup
    sup.close()


# =====================================================================
# ExplorationAgent tests
# =====================================================================


class TestExplorationAgent:
    def test_map_directory_returns_summary(self, tmp_path):
        """map_directory scans a real directory and passes file names to _ask."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        agent = ExplorationAgent()
        prompts_seen = []

        def fake_ask(prompt, system_prompt=""):
            prompts_seen.append(prompt)
            return "This directory has main.py and utils.py."

        agent._ask = fake_ask
        result = agent.map_directory(str(tmp_path), focus="entry points")

        assert result == "This directory has main.py and utils.py."
        assert len(prompts_seen) == 1
        assert "main.py" in prompts_seen[0]
        assert "utils.py" in prompts_seen[0]

    def test_map_directory_nonexistent(self):
        agent = ExplorationAgent()
        result = agent.map_directory("/nonexistent/path/xyz")
        assert "does not exist" in result

    def test_trace_functionality(self, tmp_path):
        """trace_functionality reads file content and passes it to _ask."""
        src = tmp_path / "handler.py"
        src.write_text("class RequestHandler:\n    def handle(self): pass\n")

        agent = ExplorationAgent()
        prompts_seen = []

        def fake_ask(prompt, system_prompt=""):
            prompts_seen.append(prompt)
            return "This file defines RequestHandler."

        agent._ask = fake_ask
        result = agent.trace_functionality(str(src), question="What does this handle?")

        assert result == "This file defines RequestHandler."
        assert "RequestHandler" in prompts_seen[0]
        assert "What does this handle?" in prompts_seen[0]

    def test_gather_listing_respects_depth_limit(self, tmp_path):
        """Directories deeper than MAX_DIR_DEPTH are not listed."""
        # Create nested dirs: d1/d2/d3/deep.txt
        deep = tmp_path / "d1" / "d2" / "d3"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("hidden")
        (tmp_path / "top.txt").write_text("visible")

        agent = ExplorationAgent()
        listing = agent._gather_listing(str(tmp_path), max_depth=MAX_DIR_DEPTH)

        assert "top.txt" in listing
        # d1/ and d1/d2/ should appear (depth 1 and 2), but d3/ contents should not
        assert "d1/" in listing
        assert "d2/" in listing
        # At depth 2 we see d3/ dir name, but its contents (deep.txt) are at depth 3
        assert "deep.txt" not in listing


# =====================================================================
# ExplorationOrchestrator tests
# =====================================================================


class TestExplorationOrchestrator:
    def test_explore_multiple_partitions(self, tmp_path):
        """Orchestrator assembles summaries from a directory and a file."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("# app")
        readme = tmp_path / "README.md"
        readme.write_text("# Project README")

        orchestrator = ExplorationOrchestrator()
        task = {"name": "Understand project", "task_type": "research"}

        with patch.object(ExplorationAgent, "_ask", return_value="Summary of partition"):
            result = orchestrator.explore(task, [str(tmp_path / "src"), str(readme)])

        assert len(result.summaries) == 2
        context = result.to_context_string()
        assert "[Exploration 1]" in context
        assert "[Exploration 2]" in context
        assert result.token_estimate > 0


# =====================================================================
# DispatchMode selection tests
# =====================================================================


class TestDispatchModeSelection:
    def test_simple_task_returns_direct(self, supervisor):
        task = {"id": 1, "name": "Health", "task_type": "health_check"}
        assert supervisor.select_dispatch_mode(task) == DispatchMode.DIRECT

    def test_explore_paths_triggers_explore(self, supervisor):
        task = {
            "id": 2,
            "name": "Research",
            "task_type": "research",
            "payload": {"explore_paths": ["/some/path"]},
        }
        assert supervisor.select_dispatch_mode(task) == DispatchMode.EXPLORE_THEN_EXECUTE

    def test_explicit_competitive_override(self, supervisor):
        """Explicit dispatch_mode override triggers COMPETITIVE."""
        task = {
            "id": 3,
            "name": "Blog Post",
            "task_type": "general",
            "payload": {"dispatch_mode": "competitive"},
        }
        assert supervisor.select_dispatch_mode(task) == DispatchMode.COMPETITIVE

    def test_explicit_dispatch_mode_override(self, supervisor):
        task = {
            "id": 4,
            "name": "Custom",
            "task_type": "research",
            "payload": {"dispatch_mode": "competitive"},
        }
        assert supervisor.select_dispatch_mode(task) == DispatchMode.COMPETITIVE


# =====================================================================
# Integration verification tests
# =====================================================================


class TestIntegrationVerification:
    def test_verify_connected(self, supervisor):
        """Mocked LLM returns CONNECTED."""
        result = WorkerResult(success=True, output={"data": "ok"})
        task = {
            "id": 10,
            "name": "Task",
            "task_type": "_sub_integration",
            "payload": {"integration_targets": ["api", "db"]},
        }

        with patch("merkaba.llm.LLMClient") as MockLLM:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CONNECTED"
            mock_instance.chat_with_fallback.return_value = mock_response
            MockLLM.return_value = mock_instance

            status = supervisor.verify_integration(task, result)

        assert status == "CONNECTED"

    def test_verify_disconnected(self, supervisor):
        """Mocked LLM returns DISCONNECTED."""
        result = WorkerResult(success=True, output={"data": "broken"})
        task = {
            "id": 11,
            "name": "Task",
            "task_type": "_sub_integration",
            "payload": {"integration_targets": ["api"]},
        }

        with patch("merkaba.llm.LLMClient") as MockLLM:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "DISCONNECTED"
            mock_instance.chat_with_fallback.return_value = mock_response
            MockLLM.return_value = mock_instance

            status = supervisor.verify_integration(task, result)

        assert status == "DISCONNECTED"

    def test_verify_failed_result(self, supervisor):
        """Failed WorkerResult returns DISCONNECTED without LLM call."""
        result = WorkerResult(success=False, output={}, error="boom")
        task = {
            "id": 12,
            "name": "Task",
            "task_type": "_sub_integration",
            "payload": {"integration_targets": ["api"]},
        }

        with patch("merkaba.llm.LLMClient") as MockLLM:
            status = supervisor.verify_integration(task, result)
            MockLLM.assert_not_called()

        assert status == "DISCONNECTED"


# =====================================================================
# Competition tests
# =====================================================================


class TestCompetition:
    def test_dispatch_competition_runs_n_variants(self, supervisor):
        """dispatch_competition produces N results with different variant_ids."""
        task = {
            "id": 20,
            "name": "Draft Post",
            "task_type": "_sub_content",
            "payload": {"action": "draft_post", "topic": "AI"},
        }

        results = supervisor.dispatch_competition(task, n_competitors=2)
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is True
        # Each variant should have a different variant_id
        variants = {r.output["variant"] for r in results}
        assert variants == {0, 1}

    def test_select_winner_picks_best(self, supervisor):
        """Mocked LLM judge picks option 1."""
        task = {"id": 21, "name": "Pick Best", "task_type": "_sub_content"}
        results = [
            WorkerResult(success=True, output={"draft": "A", "quality": "high"}),
            WorkerResult(success=True, output={"draft": "B", "quality": "medium"}),
        ]

        with patch("merkaba.llm.LLMClient") as MockLLM:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "1"
            mock_instance.chat_with_retry.return_value = mock_response
            MockLLM.return_value = mock_instance

            winner = supervisor.select_winner(task, results)

        assert winner.output["draft"] == "A"
