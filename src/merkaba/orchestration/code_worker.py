# src/merkaba/orchestration/code_worker.py
"""CodeWorker: generates code from specs with verify/retry/rollback loop."""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from merkaba.orchestration.workers import Worker, WorkerResult, register_worker
from merkaba.verification.deterministic import DeterministicVerifier

logger = logging.getLogger(__name__)

CODE_SYSTEM_PROMPT = """You are a code generation agent. Given a spec and optional context:
1. Read existing files to understand the codebase
2. Generate the implementation using file_write
3. Be precise — write complete, working code

Follow existing patterns and conventions in the codebase."""


@dataclass
class CodeWorker(Worker):
    """Generates code from specs, verifies with DeterministicVerifier,
    retries once on failure, and rolls back if still broken."""

    _verifier: DeterministicVerifier = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._verifier = DeterministicVerifier()

    def execute(self, task: dict) -> WorkerResult:
        payload = task.get("payload") or {}
        spec = payload.get("spec", task.get("name", ""))
        target_files = payload.get("target_files", [])
        stakes = payload.get("stakes", "normal")

        # Snapshot target files before generation
        snapshot = self._snapshot(target_files)

        # Optional exploration for high-complexity tasks
        exploration_context = ""
        if payload.get("complexity") == "high" and payload.get("explore_paths"):
            exploration_context = self._explore(task, payload["explore_paths"])

        # Build prompt
        prompt = self._build_generation_prompt(spec, exploration_context, payload)

        # First attempt: generate code via agentic tool loop
        result_text = self._ask_llm_with_tools(prompt, system_prompt=CODE_SYSTEM_PROMPT)
        written_files = self._extract_written_files(result_text, target_files)

        # Verify
        all_passed, verify_summary = self._verify_files(written_files)

        if not all_passed:
            # Retry once with error feedback
            retry_prompt = (
                f"The code you generated has verification errors:\n\n{verify_summary}\n\n"
                f"Original spec: {spec}\n\n"
                "Fix the issues and rewrite the files using file_write."
            )
            result_text = self._ask_llm_with_tools(retry_prompt, system_prompt=CODE_SYSTEM_PROMPT)
            written_files = self._extract_written_files(result_text, target_files)
            all_passed, verify_summary = self._verify_files(written_files)

        if not all_passed:
            # Rollback on second failure
            self._rollback(snapshot)
            return WorkerResult(
                success=False,
                output={"files_rolled_back": list(snapshot.keys()), "verification": verify_summary},
                error="Verification failed after retry, rolled back",
            )

        # Optional high-stakes review
        if stakes == "high" and written_files:
            review_result = self._review(spec, written_files)
            if not review_result.success:
                self._rollback(snapshot)
                return WorkerResult(
                    success=False,
                    output={
                        "files_rolled_back": list(snapshot.keys()),
                        "review": review_result.output,
                    },
                    error="Review rejected the code, rolled back",
                )

        return WorkerResult(
            success=True,
            output={"files_written": written_files, "verification": "passed"},
        )

    def _build_generation_prompt(self, spec: str, exploration_context: str, payload: dict) -> str:
        parts = [f"## Spec\n{spec}"]
        if exploration_context:
            parts.append(f"## Codebase Context\n{exploration_context}")
        if payload.get("_exploration_context"):
            parts.append(f"## Exploration Context\n{payload['_exploration_context']}")
        target_files = payload.get("target_files", [])
        if target_files:
            parts.append(f"## Target Files\n{', '.join(target_files)}")
        parts.append("Generate the implementation. Use file_read to understand existing code, then file_write to create/modify files.")
        return "\n\n".join(parts)

    def _snapshot(self, paths: list[str]) -> dict[str, str | None]:
        """Read each target file, storing content (None if doesn't exist)."""
        snapshot: dict[str, str | None] = {}
        for path in paths:
            try:
                with open(path, "r") as f:
                    snapshot[path] = f.read()
            except FileNotFoundError:
                snapshot[path] = None
        return snapshot

    def _rollback(self, snapshot: dict[str, str | None]) -> None:
        """Restore files from snapshot. Delete files that didn't exist before."""
        for path, content in snapshot.items():
            if content is None:
                # File didn't exist before — delete if it was created
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass
            else:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)

    def _verify_files(self, paths: list[str]) -> tuple[bool, str]:
        """Run verifier on each path. Returns (all_passed, summary)."""
        if not paths:
            return True, "No files to verify"

        all_passed = True
        summaries: list[str] = []

        for path in paths:
            result = self._verifier.verify(path)
            if result is None:
                # No checks applicable for this file type, treat as passed
                continue
            if not result.passed:
                all_passed = False
            summaries.append(f"{path}: {result.summary}")

        summary = "\n".join(summaries) if summaries else "All checks passed"
        return all_passed, summary

    def _extract_written_files(self, result_text: str, target_files: list[str]) -> list[str]:
        """Extract list of files that were written during the tool loop.

        Parses file_write tool results from the accumulated result text.
        Falls back to target_files if parsing yields nothing.
        """
        written: list[str] = []
        for line in result_text.split("\n"):
            # Tool results contain "[file_write] Successfully wrote ... to <path>"
            if "[file_write] Successfully wrote" in line and " to " in line:
                path = line.split(" to ", 1)[-1].strip()
                if path and path not in written:
                    written.append(path)
        # Fall back to target_files that now exist on disk
        if not written:
            written = [f for f in target_files if os.path.isfile(f)]
        return written

    def _explore(self, task: dict, explore_paths: list[str]) -> str:
        """Run ExplorationOrchestrator and return context string."""
        from merkaba.orchestration.explorer import ExplorationOrchestrator

        orchestrator = ExplorationOrchestrator()
        result = orchestrator.explore(task, explore_paths)
        return result.to_context_string()

    def _review(self, spec: str, file_paths: list[str]) -> WorkerResult:
        """Run a review worker on the generated files.

        Attempts to load a 'review' worker from the worker registry.
        If no review worker is registered, the review is skipped (returns success).
        """
        review_cls = None
        try:
            from merkaba.orchestration.workers import get_worker_class
            review_cls = get_worker_class("review")
        except (KeyError, ImportError):
            logger.debug("No review worker registered — skipping high-stakes review")
            return WorkerResult(success=True, output={"review": "skipped — no review worker available"})

        # Read all written files for review
        file_contents: list[str] = []
        for path in file_paths:
            try:
                with open(path, "r") as f:
                    content = f.read()
                file_contents.append(f"### {path}\n```\n{content}\n```")
            except FileNotFoundError:
                file_contents.append(f"### {path}\n(file not found)")

        output_text = "\n\n".join(file_contents)

        review_task = {
            "id": 0,
            "name": f"Review: {spec[:100]}",
            "task_type": "review",
            "payload": {
                "output_text": output_text,
                "review_criteria": "Check for correctness, completeness, and adherence to the spec.",
                "task_spec": spec,
            },
        }

        reviewer = review_cls(model=self.model)
        return reviewer.execute(review_task)


register_worker("code", CodeWorker)
