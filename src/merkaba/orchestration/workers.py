# src/merkaba/orchestration/workers.py
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from merkaba.security import PermissionManager, PermissionDenied

logger = logging.getLogger(__name__)

# --- Worker registry ---

WORKER_REGISTRY: dict[str, type["Worker"]] = {}


def register_worker(task_type: str, worker_class: type["Worker"]) -> None:
    WORKER_REGISTRY[task_type] = worker_class


def get_worker_class(task_type: str) -> type["Worker"] | None:
    return WORKER_REGISTRY.get(task_type)


# --- WorkerResult ---


@dataclass
class WorkerResult:
    """Result of a worker task execution."""

    success: bool
    output: dict[str, Any]
    error: str | None = None
    decisions_made: list[dict[str, Any]] = field(default_factory=list)
    facts_learned: list[dict[str, Any]] = field(default_factory=list)
    needs_approval: list[dict[str, Any]] = field(default_factory=list)


# --- Worker base ---


@dataclass
class Worker:
    """Base class for task-executing workers. Single-shot: receive task, do work, return result."""

    business_id: int | None = None
    model: str = None
    max_iterations: int = 5
    memory: Any = None  # MemoryRetrieval, imported lazily
    tools: Any = None  # ToolRegistry, imported lazily
    permission_manager: PermissionManager = field(default_factory=PermissionManager)
    _llm: Any = field(default=None, init=False, repr=False)

    def execute(self, task: dict) -> WorkerResult:
        raise NotImplementedError

    def _get_llm(self):
        if self._llm is None:
            from merkaba.llm import LLMClient
            if self.model is None:
                from merkaba.config.defaults import DEFAULT_MODELS
                self.model = DEFAULT_MODELS["complex"]
            self._llm = LLMClient(model=self.model)
        return self._llm

    def _ask_llm(self, prompt: str, system_prompt: str | None = None) -> str:
        from merkaba.llm import RequestPriority
        llm = self._get_llm()
        response = llm.chat_with_fallback(message=prompt, system_prompt=system_prompt, tier="complex", priority=RequestPriority.SCHEDULED)
        return response.content or ""

    def _ask_llm_with_tools(self, prompt: str, system_prompt: str | None = None) -> str:
        from merkaba.llm import RequestPriority
        llm = self._get_llm()
        tools_fmt = self.tools.to_ollama_format() if self.tools and self.tools.list_tools() else None
        conversation = [{"role": "user", "content": prompt}]
        formatted = prompt

        for _ in range(self.max_iterations):
            response = llm.chat_with_fallback(message=formatted, system_prompt=system_prompt, tools=tools_fmt, tier="complex", priority=RequestPriority.SCHEDULED)
            if response.tool_calls:
                results = []
                for tc in response.tool_calls:
                    tool = self.tools.get(tc.name) if self.tools else None
                    if tool:
                        try:
                            self.permission_manager.check(tc.name, tool.permission_tier)
                        except PermissionDenied as pd:
                            results.append(f"[{tc.name}] Permission denied: {pd}")
                            continue
                        result = tool.execute(**tc.arguments)
                        results.append(f"[{tc.name}] {result.output if result.success else result.error}")
                    else:
                        results.append(f"[{tc.name}] Tool not found")
                tool_output = "\n".join(results)
                formatted = f"{formatted}\n\nTool results:\n{tool_output}\n\nContinue with the task."
            else:
                return response.content or ""
        return ""

    def _build_context(self, task: dict) -> str:
        parts = [f"Task: {task['name']}", f"Type: {task['task_type']}"]
        if task.get("payload"):
            parts.append(f"Payload: {json.dumps(task['payload'])}")
        if self.memory and self.business_id:
            relevant = self.memory.recall(task["name"], self.business_id, limit=5)
            for r in relevant:
                if r.get("type") == "fact":
                    parts.append(f"  [{r['category']}] {r['key']}: {r['value']}")
                elif r.get("type") == "learning":
                    parts.append(f"  [Learning] {r['insight']}")
        return "\n".join(parts)


# --- Concrete workers ---


@dataclass
class HealthCheckWorker(Worker):
    """Checks the health of a business's operations."""

    def execute(self, task: dict) -> WorkerResult:
        context = self._build_context(task)
        prompt = (
            f"{context}\n\n"
            "Analyze the current state of this business based on the context above. "
            'Respond in JSON: {"status": "healthy|warning|critical", "issues": [...], "recommendations": [...]}'
        )
        response = self._ask_llm(prompt, system_prompt="You are a business health checker. Analyze and report status.")
        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = {"status": "unknown", "raw_response": response}
        return WorkerResult(success=True, output=data)


@dataclass
class ResearchWorker(Worker):
    """Performs market research tasks."""

    def execute(self, task: dict) -> WorkerResult:
        payload = task.get("payload") or {}
        query = payload.get("query", task["name"])
        context = self._build_context(task)
        prompt = (
            f"{context}\n\nResearch the following topic: {query}\n"
            'Use available tools to gather information, then summarize.\n'
            'Respond in JSON: {"findings": [...], "recommendations": [...]}'
        )
        response = self._ask_llm_with_tools(prompt, system_prompt="You are a market research agent.")
        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = {"raw_response": response}
        return WorkerResult(
            success=True,
            output=data,
            facts_learned=[{"category": "research", "key": query, "value": str(response)[:500]}],
        )


# Register built-in workers
register_worker("health_check", HealthCheckWorker)
register_worker("research", ResearchWorker)
