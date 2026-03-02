# src/merkaba/orchestration/supervisor.py
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from merkaba.protocols import MemoryBackend
from merkaba.memory.retrieval import MemoryRetrieval
from merkaba.orchestration.workers import Worker, WorkerResult, get_worker_class
from merkaba.orchestration.learnings import LearningExtractor

logger = logging.getLogger(__name__)


class DispatchMode(Enum):
    DIRECT = "direct"
    EXPLORE_THEN_EXECUTE = "explore_then_execute"
    COMPETITIVE = "competitive"


MODEL_DEFAULTS: dict[str, str] = {
    "health_check": "phi4:14b",
    "code": "qwen3.5:122b",
}
DEFAULT_MODEL = "qwen3.5:122b"
CONFIG_PATH = os.path.expanduser("~/.merkaba/config.json")

INTEGRATION_CHECK_MODEL = "qwen3:4b"
SIMPLE_TASK_TYPES = {"health_check"}
CREATIVE_TASK_TYPES: set[str] = set()  # Extenders can add task types that use competitive dispatch

VARIANT_EMPHASES = ["creativity", "clarity", "engagement"]


def load_model_config(config_path: str = CONFIG_PATH) -> dict[str, str]:
    """Load model routing overrides from config.json and merge with defaults."""
    mapping = dict(MODEL_DEFAULTS)
    try:
        with open(config_path) as f:
            data = json.load(f)
        overrides = data.get("models", {}).get("task_types", {})
        mapping.update(overrides)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return mapping


def resolve_model(task_type: str, config_path: str = CONFIG_PATH) -> str:
    """Return the model to use for a given task_type."""
    mapping = load_model_config(config_path)
    return mapping.get(task_type, DEFAULT_MODEL)


@dataclass
class Supervisor:
    """Coordinates task execution by dispatching to appropriate Workers."""

    memory_store: MemoryBackend
    on_needs_approval: Callable[[dict], None] | None = None
    default_model: str = DEFAULT_MODEL
    config_path: str = CONFIG_PATH
    _retrieval: MemoryRetrieval | None = field(default=None, init=False, repr=False)
    _learnings: LearningExtractor | None = field(default=None, init=False, repr=False)
    _model_map: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        vectors = None
        try:
            from merkaba.memory.vectors import VectorMemory
            vectors = VectorMemory()
        except Exception:
            logger.debug("VectorMemory unavailable, using keyword fallback")
        self._retrieval = MemoryRetrieval(store=self.memory_store, vectors=vectors)
        self._learnings = LearningExtractor(memory_store=self.memory_store)
        self._model_map = load_model_config(self.config_path)

        # Load extension workers and adapters from installed packages
        from merkaba.extensions import discover_workers, discover_adapters
        discover_workers()
        discover_adapters()

    def select_dispatch_mode(self, task: dict) -> DispatchMode:
        """Determine dispatch mode for a task based on payload and task_type."""
        payload = task.get("payload") or {}

        # Explicit override takes priority
        override = payload.get("dispatch_mode")
        if override:
            try:
                return DispatchMode(override)
            except ValueError:
                logger.warning("Unknown dispatch_mode '%s', falling back to DIRECT", override)

        # Simple tasks → DIRECT
        if task["task_type"] in SIMPLE_TASK_TYPES:
            return DispatchMode.DIRECT

        # Creative tasks with draft_post action → COMPETITIVE
        if task["task_type"] in CREATIVE_TASK_TYPES and payload.get("action") == "draft_post":
            return DispatchMode.COMPETITIVE

        # Tasks with explore_paths → EXPLORE_THEN_EXECUTE
        if payload.get("explore_paths"):
            return DispatchMode.EXPLORE_THEN_EXECUTE

        return DispatchMode.DIRECT

    def handle_task(self, task: dict) -> dict:
        """Handle a task from the scheduler. This is the on_task_due callback."""
        # Set trace ID for this task
        try:
            from merkaba.observability.tracing import new_trace_id
            new_trace_id(f"task-{task['id']}")
        except Exception:
            pass

        logger.info("Supervisor handling task %s (%s)", task["id"], task["name"])

        worker_class = get_worker_class(task["task_type"])
        if worker_class is None:
            logger.warning("No worker for task_type=%s", task["task_type"])
            return {
                "success": False,
                "error": "No worker for task_type '%s'" % task["task_type"],
                "output": None,
            }

        mode = self.select_dispatch_mode(task)
        logger.info("Dispatch mode for task %s: %s", task["id"], mode.value)

        # Record dispatch decision
        try:
            from merkaba.observability.audit import record_decision
            record_decision(
                decision_type="dispatch_mode",
                decision=mode.value,
                alternatives=[m.value for m in DispatchMode],
                context_summary=f"task={task['name']}, type={task['task_type']}",
            )
        except Exception:
            pass

        if mode == DispatchMode.EXPLORE_THEN_EXECUTE:
            result = self._handle_explore_then_execute(task, worker_class)
        elif mode == DispatchMode.COMPETITIVE:
            result = self._handle_competitive(task)
        else:
            result = self._handle_direct(task, worker_class)

        self._store_facts(task, result)
        self._store_decisions(task, result)
        self._handle_approvals(task, result)
        self._learnings.process(task, result)
        self._record_episode(task, result)

        return {"success": result.success, "output": result.output, "error": result.error}

    def _handle_direct(self, task: dict, worker_class: type[Worker]) -> WorkerResult:
        """Standard single-worker execution."""
        worker = self._build_worker(worker_class, task)

        try:
            result = worker.execute(task)
        except Exception as e:
            logger.error("Worker failed for task %s: %s", task["id"], e)
            result = WorkerResult(success=False, output={}, error=str(e))

        # Integration verification if targets specified
        payload = task.get("payload") or {}
        if payload.get("integration_targets") and result.success:
            status = self.verify_integration(task, result)
            if status == "DISCONNECTED":
                logger.warning("Integration DISCONNECTED for task %s, re-dispatching with wiring", task["id"])
                task_copy = dict(task)
                payload_copy = dict(payload)
                payload_copy["_wiring_instructions"] = (
                    f"Previous attempt had DISCONNECTED integration. "
                    f"Targets: {payload['integration_targets']}. "
                    f"Ensure outputs connect to these targets."
                )
                task_copy["payload"] = payload_copy
                worker = self._build_worker(worker_class, task_copy)
                try:
                    result = worker.execute(task_copy)
                except Exception as e:
                    logger.error("Re-dispatch failed for task %s: %s", task["id"], e)
                    result = WorkerResult(success=False, output={}, error=str(e))
            elif status == "PARTIAL":
                logger.info("Integration PARTIAL for task %s, continuing", task["id"])

        return result

    def _handle_explore_then_execute(self, task: dict, worker_class: type[Worker]) -> WorkerResult:
        """Run exploration agents first, then inject context into the worker."""
        from merkaba.orchestration.explorer import ExplorationOrchestrator

        payload = task.get("payload") or {}
        explore_paths = payload.get("explore_paths", [])

        orchestrator = ExplorationOrchestrator()
        exploration = orchestrator.explore(task, explore_paths)

        context_str = exploration.to_context_string()
        if context_str:
            payload_copy = dict(payload)
            payload_copy["_exploration_context"] = context_str
            task_copy = dict(task)
            task_copy["payload"] = payload_copy
            return self._handle_direct(task_copy, worker_class)

        return self._handle_direct(task, worker_class)

    def _handle_competitive(self, task: dict) -> WorkerResult:
        """Run multiple worker variants and pick the best result."""
        results = self.dispatch_competition(task)
        return self.select_winner(task, results)

    def verify_integration(self, task: dict, result: WorkerResult) -> str:
        """Check whether a worker's output integrates with specified targets.

        Returns: "CONNECTED", "PARTIAL", or "DISCONNECTED".
        """
        if not result.success:
            return "DISCONNECTED"

        payload = task.get("payload") or {}
        targets = payload.get("integration_targets", [])

        prompt = (
            f"Task: {task['name']}\n"
            f"Output: {json.dumps(result.output)}\n"
            f"Integration targets: {targets}\n\n"
            "Does the output properly connect to all integration targets?\n"
            "Reply with exactly one word: CONNECTED, PARTIAL, or DISCONNECTED."
        )

        try:
            from merkaba.llm import LLMClient
            llm = LLMClient()
            from merkaba.llm import RequestPriority
            response = llm.chat_with_fallback(
                message=prompt,
                system_prompt="You are an integration checker. Reply with one word only.",
                tier="classifier",
                priority=RequestPriority.SCHEDULED,
            )
            answer = (response.content or "").strip().upper()
            if answer in ("CONNECTED", "PARTIAL", "DISCONNECTED"):
                return answer
            # If LLM gives unexpected output, assume connected
            logger.warning("Unexpected integration check response: %s", answer)
            return "CONNECTED"
        except Exception as e:
            logger.warning("Integration check failed, assuming CONNECTED: %s", e)
            return "CONNECTED"

    def dispatch_competition(self, task: dict, n_competitors: int = 2) -> list[WorkerResult]:
        """Run N worker variants sequentially with different emphases."""
        worker_class = get_worker_class(task["task_type"])
        if worker_class is None:
            return [WorkerResult(success=False, output={}, error="No worker for task_type")]

        results: list[WorkerResult] = []
        for i in range(n_competitors):
            payload_copy = dict(task.get("payload") or {})
            emphasis = VARIANT_EMPHASES[i % len(VARIANT_EMPHASES)]
            payload_copy["_variant_emphasis"] = emphasis
            payload_copy["_variant_id"] = i

            task_copy = dict(task)
            task_copy["payload"] = payload_copy

            worker = self._build_worker(worker_class, task_copy)
            try:
                result = worker.execute(task_copy)
            except Exception as e:
                logger.error("Competition variant %d failed: %s", i, e)
                result = WorkerResult(success=False, output={}, error=str(e))
            results.append(result)

        return results

    def select_winner(self, task: dict, results: list[WorkerResult]) -> WorkerResult:
        """Pick the best result from a competition. Uses LLM judge if >1 successful."""
        successful = [r for r in results if r.success]

        if not successful:
            return results[0] if results else WorkerResult(success=False, output={}, error="No competition results")

        if len(successful) == 1:
            return successful[0]

        # LLM judge picks the best
        options = "\n\n".join(
            f"Option {i+1}: {json.dumps(r.output)}" for i, r in enumerate(successful)
        )
        prompt = (
            f"Task: {task['name']}\n\n"
            f"{options}\n\n"
            "Which option is best? Reply with just the number (e.g. 1 or 2)."
        )

        try:
            from merkaba.llm import LLMClient
            llm = LLMClient()
            from merkaba.llm import RequestPriority
            response = llm.chat_with_fallback(
                message=prompt,
                system_prompt="You are a content judge. Pick the best option by number.",
                tier="classifier",
                priority=RequestPriority.SCHEDULED,
            )
            answer = (response.content or "").strip()
            # Extract first digit
            for ch in answer:
                if ch.isdigit() and ch != '0':
                    idx = int(ch) - 1
                    if 0 <= idx < len(successful):
                        try:
                            from merkaba.observability.audit import record_decision
                            record_decision(
                                decision_type="competition_winner",
                                decision=f"option_{idx + 1}",
                                alternatives=[f"option_{i + 1}" for i in range(len(successful))],
                                context_summary=f"task={task['name']}",
                                model=INTEGRATION_CHECK_MODEL,
                            )
                        except Exception:
                            pass
                        return successful[idx]
                    break
        except Exception as e:
            logger.warning("Judge failed, using first result: %s", e)

        return successful[0]

    def _build_worker(self, worker_class: type[Worker], task: dict) -> Worker:
        tools = self._build_tool_registry(task)
        model = self._model_map.get(task["task_type"], self.default_model)
        return worker_class(
            business_id=task.get("business_id"),
            model=model,
            memory=self._retrieval,
            tools=tools,
        )

    def _build_tool_registry(self, task: dict):
        from merkaba.tools.registry import ToolRegistry
        registry = ToolRegistry()
        autonomy = task.get("autonomy_level", 1)

        try:
            from merkaba.tools.builtin import file_read, file_list, grep, glob
            for tool in [file_read, file_list, grep, glob]:
                registry.register(tool)
            if autonomy >= 2:
                from merkaba.tools.builtin import web_fetch
                registry.register(web_fetch)
            if autonomy >= 3:
                from merkaba.tools.builtin import bash
                registry.register(bash)
        except ImportError:
            logger.warning("Could not import builtin tools")

        return registry

    def _store_facts(self, task: dict, result: WorkerResult) -> None:
        business_id = task.get("business_id")
        if not business_id:
            return
        for fact in result.facts_learned:
            self.memory_store.add_fact(
                business_id=business_id,
                category=fact.get("category", "general"),
                key=fact.get("key", "unknown"),
                value=fact.get("value", ""),
                source="worker:%s:task:%s" % (task["task_type"], task["id"]),
            )

    def _store_decisions(self, task: dict, result: WorkerResult) -> None:
        business_id = task.get("business_id")
        if not business_id:
            return
        for decision in result.decisions_made:
            self.memory_store.add_decision(
                business_id=business_id,
                action_type=decision.get("action_type", task["task_type"]),
                decision=decision.get("decision", ""),
                reasoning=decision.get("reasoning", ""),
            )

    def _handle_approvals(self, task: dict, result: WorkerResult) -> None:
        if not result.needs_approval:
            return
        if self.on_needs_approval:
            for action in result.needs_approval:
                action["task_id"] = task["id"]
                action["business_id"] = task.get("business_id")
                self.on_needs_approval(action)
        else:
            logger.info(
                "Task %s has %d pending approvals (no handler)",
                task["id"], len(result.needs_approval),
            )

    def _record_episode(self, task: dict, result: WorkerResult) -> None:
        """Record an episode summarizing this task execution."""
        business_id = task.get("business_id")
        if not business_id:
            return
        try:
            from merkaba.llm import LLMClient

            llm = LLMClient()
            prompt = (
                f"Summarize this task execution in 2-3 sentences:\n"
                f"Task: {task['name']}\nType: {task['task_type']}\n"
                f"Outcome: {'success' if result.success else 'failure'}\n"
                f"Details: {result.output or result.error}"
            )
            from merkaba.llm import RequestPriority
            response = llm.chat_with_fallback(
                message=prompt,
                system_prompt="You are a concise summarizer. Write 2-3 sentences.",
                tier="classifier",
                priority=RequestPriority.BACKGROUND,
            )
            summary = response.content or f"Task '{task['name']}' completed"
            self.memory_store.add_episode(
                business_id=business_id,
                task_type=task["task_type"],
                task_id=task["id"],
                summary=summary,
                outcome="success" if result.success else "failure",
                outcome_details=str(result.error or result.output)[:500],
                key_decisions=[d.get("decision", "") for d in result.decisions_made],
            )
        except Exception as e:
            logger.warning("Failed to record episode: %s", e)

    def close(self):
        if self._retrieval:
            self._retrieval.close()
            self._retrieval = None
