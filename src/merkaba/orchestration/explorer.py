# src/friday/orchestration/explorer.py
"""Exploration agents for context scouting before complex task execution."""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_DIR_DEPTH = 2
MAX_FILES_PER_DIR = 50
FILE_PREVIEW_BYTES = 2048
EXPLORATION_MODEL = "qwen3:4b"


@dataclass
class ExplorationResult:
    """Aggregated output from one or more exploration agents."""

    summaries: list[str] = field(default_factory=list)
    token_estimate: int = 0

    def to_context_string(self) -> str:
        if not self.summaries:
            return ""
        parts = [f"[Exploration {i+1}] {s}" for i, s in enumerate(self.summaries)]
        return "\n\n".join(parts)


@dataclass
class ExplorationAgent:
    """Lightweight scout that reads files/dirs and summarises via a small LLM."""

    _llm: Any = field(default=None, init=False, repr=False)

    def _get_llm(self):
        if self._llm is None:
            from friday.llm import LLMClient
            self._llm = LLMClient()
        return self._llm

    def _ask(self, prompt: str, system_prompt: str = "You are a concise code analyst.") -> str:
        from friday.llm import RequestPriority
        llm = self._get_llm()
        response = llm.chat_with_retry(
            message=prompt,
            system_prompt=system_prompt,
            model_override=EXPLORATION_MODEL,
            priority=RequestPriority.BACKGROUND,
        )
        return response.content or ""

    # --- Directory mapping ---

    def map_directory(self, path: str, focus: str = "") -> str:
        """Scan a directory tree (depth-limited) and return an LLM summary."""
        if not os.path.isdir(path):
            return f"Directory does not exist: {path}"

        listing = self._gather_listing(path, max_depth=MAX_DIR_DEPTH)
        prompt = (
            f"Here is a file listing of {path}:\n\n{listing}\n\n"
            f"{'Focus: ' + focus + chr(10) if focus else ''}"
            "Summarise the structure in 3-5 sentences. "
            "Highlight key modules, entry points, and config files."
        )
        return self._ask(prompt)

    def _gather_listing(self, root: str, max_depth: int = MAX_DIR_DEPTH) -> str:
        """Walk the directory tree up to max_depth, capping files per dir."""
        lines: list[str] = []
        self._walk(root, "", 0, max_depth, lines)
        return "\n".join(lines) if lines else "(empty)"

    def _walk(self, base: str, prefix: str, depth: int, max_depth: int, lines: list[str]) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(base))
        except PermissionError:
            lines.append(f"{prefix}(permission denied)")
            return

        dirs = []
        files = []
        for entry in entries:
            full = os.path.join(base, entry)
            if os.path.isdir(full):
                dirs.append(entry)
            else:
                files.append(entry)

        for f in files[:MAX_FILES_PER_DIR]:
            lines.append(f"{prefix}{f}")
        if len(files) > MAX_FILES_PER_DIR:
            lines.append(f"{prefix}... and {len(files) - MAX_FILES_PER_DIR} more files")

        for d in dirs:
            lines.append(f"{prefix}{d}/")
            self._walk(os.path.join(base, d), prefix + "  ", depth + 1, max_depth, lines)

    # --- File tracing ---

    def trace_functionality(self, entry_point: str, question: str = "") -> str:
        """Read a file preview and return an LLM summary answering the question."""
        if not os.path.isfile(entry_point):
            return f"File does not exist: {entry_point}"

        preview = self._read_file_preview(entry_point)
        prompt = (
            f"Here is the first portion of {entry_point}:\n\n```\n{preview}\n```\n\n"
            f"{'Question: ' + question + chr(10) if question else ''}"
            "Summarise what this file does, its key classes/functions, and how it fits into the larger system."
        )
        return self._ask(prompt)

    def _read_file_preview(self, path: str) -> str:
        """Read up to FILE_PREVIEW_BYTES from the file."""
        try:
            with open(path, "r", errors="replace") as f:
                return f.read(FILE_PREVIEW_BYTES)
        except (OSError, UnicodeDecodeError) as e:
            return f"(could not read: {e})"


@dataclass
class ExplorationOrchestrator:
    """Runs one ExplorationAgent per partition and aggregates results."""

    def explore(self, task: dict, partitions: list[str]) -> ExplorationResult:
        """Explore each partition (file or directory) and return aggregated results."""
        result = ExplorationResult()
        focus = task.get("name", "")

        for partition in partitions:
            agent = ExplorationAgent()
            if os.path.isdir(partition):
                summary = agent.map_directory(partition, focus=focus)
            else:
                summary = agent.trace_functionality(partition, question=focus)
            result.summaries.append(summary)
            result.token_estimate += len(summary) // 4  # rough estimate

        return result
