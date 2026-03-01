# tests/test_code_worker.py
"""Tests for CodeWorker: snapshot/rollback, verification loop, execute flow, review."""

import os
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before any merkaba imports
sys.modules.setdefault("ollama", MagicMock())

from merkaba.orchestration.code_worker import CodeWorker
from merkaba.orchestration.workers import WorkerResult
from merkaba.verification.deterministic import VerificationResult, CheckResult


# --- Helpers ---


def _make_worker(**kwargs) -> CodeWorker:
    """Create a CodeWorker with no tools (tests mock _ask_llm_with_tools)."""
    return CodeWorker(**kwargs)


# --- Snapshot / Rollback tests ---


class TestSnapshot:
    def test_snapshot_captures_existing_files(self, tmp_path):
        f = tmp_path / "existing.py"
        f.write_text("original content")

        worker = _make_worker()
        snapshot = worker._snapshot([str(f)])

        assert snapshot[str(f)] == "original content"

    def test_snapshot_records_none_for_missing(self, tmp_path):
        missing = str(tmp_path / "no_such_file.py")

        worker = _make_worker()
        snapshot = worker._snapshot([missing])

        assert snapshot[missing] is None

    def test_rollback_restores_original(self, tmp_path):
        existing = tmp_path / "restore_me.py"
        existing.write_text("original")

        new_file = tmp_path / "delete_me.py"

        worker = _make_worker()
        snapshot = worker._snapshot([str(existing), str(new_file)])

        # Simulate modifications
        existing.write_text("modified")
        new_file.write_text("should be deleted")

        worker._rollback(snapshot)

        assert existing.read_text() == "original"
        assert not new_file.exists()


# --- Verification tests ---


class TestVerifyFiles:
    def test_verify_files_all_pass(self, tmp_path):
        f = tmp_path / "good.py"
        f.write_text("x = 1\n")

        worker = _make_worker()
        passed_result = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )
        with patch.object(worker._verifier, "verify", return_value=passed_result):
            all_passed, summary = worker._verify_files([str(f)])

        assert all_passed is True
        assert "All checks passed" in summary

    def test_verify_files_with_failures(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("import os\n")

        worker = _make_worker()
        failed_result = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="unused import")],
            summary="[ruff] FAILED:\nunused import",
        )
        with patch.object(worker._verifier, "verify", return_value=failed_result):
            all_passed, summary = worker._verify_files([str(f)])

        assert all_passed is False
        assert "FAILED" in summary

    def test_execute_retries_on_verification_failure(self, tmp_path):
        target = tmp_path / "retry.py"

        worker = _make_worker()

        # First call: generate code (verification will fail)
        # Second call: fix code (verification will pass)
        call_count = [0]

        def mock_ask_llm(prompt, system_prompt=None):
            call_count[0] += 1
            target.write_text("fixed code\n")
            return f"[file_write] Successfully wrote 11 characters to {target}"

        failed = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="error")],
            summary="[ruff] FAILED:\nerror",
        )
        passed = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )

        verify_results = iter([failed, passed])

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker._verifier, "verify", side_effect=lambda _: next(verify_results)):
            task = {
                "id": 1,
                "name": "Fix retry",
                "task_type": "code",
                "payload": {"spec": "Fix the code", "target_files": [str(target)]},
            }
            result = worker.execute(task)

        assert result.success is True
        assert call_count[0] == 2


# --- Execute flow tests ---


class TestExecuteFlow:
    def test_execute_basic_success(self, tmp_path):
        target = tmp_path / "hello.py"

        worker = _make_worker()

        def mock_ask_llm(prompt, system_prompt=None):
            target.write_text("print('hello')\n")
            return f"[file_write] Successfully wrote 16 characters to {target}"

        passed = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker._verifier, "verify", return_value=passed):
            task = {
                "id": 1,
                "name": "Write hello",
                "task_type": "code",
                "payload": {"spec": "Write a hello world", "target_files": [str(target)]},
            }
            result = worker.execute(task)

        assert result.success is True
        assert result.output["verification"] == "passed"
        assert str(target) in result.output["files_written"]

    def test_execute_rollback_after_double_failure(self, tmp_path):
        target = tmp_path / "fail.py"
        target.write_text("original\n")

        worker = _make_worker()

        def mock_ask_llm(prompt, system_prompt=None):
            target.write_text("bad code\n")
            return f"[file_write] Successfully wrote 9 characters to {target}"

        failed = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="syntax error")],
            summary="[ruff] FAILED:\nsyntax error",
        )

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker._verifier, "verify", return_value=failed):
            task = {
                "id": 1,
                "name": "Bad code",
                "task_type": "code",
                "payload": {"spec": "Write something", "target_files": [str(target)]},
            }
            result = worker.execute(task)

        assert result.success is False
        assert "rolled back" in result.error.lower()
        # File should be restored to original
        assert target.read_text() == "original\n"

    def test_execute_with_exploration(self, tmp_path):
        target = tmp_path / "explored.py"

        worker = _make_worker()

        explore_called = [False]

        def mock_explore(task, paths):
            explore_called[0] = True
            return "Explored context here"

        def mock_ask_llm(prompt, system_prompt=None):
            target.write_text("# explored\n")
            return f"[file_write] Successfully wrote 12 characters to {target}"

        passed = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker, "_explore", side_effect=mock_explore), \
             patch.object(worker._verifier, "verify", return_value=passed):
            task = {
                "id": 1,
                "name": "Explore and code",
                "task_type": "code",
                "payload": {
                    "spec": "Build with exploration",
                    "target_files": [str(target)],
                    "complexity": "high",
                    "explore_paths": [str(tmp_path)],
                },
            }
            result = worker.execute(task)

        assert result.success is True
        assert explore_called[0] is True

    def test_execute_high_stakes_review(self, tmp_path):
        target = tmp_path / "reviewed.py"

        worker = _make_worker()

        def mock_ask_llm(prompt, system_prompt=None):
            target.write_text("reviewed code\n")
            return f"[file_write] Successfully wrote 14 characters to {target}"

        passed = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )

        review_ok = WorkerResult(
            success=True,
            output={"approved": True, "issues": [], "suggestions": []},
        )

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker._verifier, "verify", return_value=passed), \
             patch.object(worker, "_review", return_value=review_ok):
            task = {
                "id": 1,
                "name": "High stakes code",
                "task_type": "code",
                "payload": {
                    "spec": "Critical code",
                    "target_files": [str(target)],
                    "stakes": "high",
                },
            }
            result = worker.execute(task)

        assert result.success is True


# --- Review integration tests ---


class TestReviewIntegration:
    def test_review_skipped_when_no_review_worker(self, tmp_path):
        """When no review worker is registered, review returns success with skipped note."""
        target = tmp_path / "approved.py"
        target.write_text("good code\n")

        worker = _make_worker()
        with patch("merkaba.orchestration.workers.WORKER_REGISTRY", {}):
            result = worker._review("Write good code", [str(target)])

        assert result.success is True
        assert "skipped" in str(result.output.get("review", "")).lower()

    def test_review_rejected_triggers_rollback(self, tmp_path):
        target = tmp_path / "rejected.py"
        target.write_text("original\n")

        worker = _make_worker()

        def mock_ask_llm(prompt, system_prompt=None):
            target.write_text("new code\n")
            return f"[file_write] Successfully wrote 9 characters to {target}"

        passed = VerificationResult(
            passed=True,
            checks=[CheckResult(name="ruff", passed=True, output="")],
            summary="All checks passed: ruff",
        )

        review_rejected = WorkerResult(
            success=False,
            output={"approved": False, "issues": ["Missing error handling"]},
        )

        with patch.object(worker, "_ask_llm_with_tools", side_effect=mock_ask_llm), \
             patch.object(worker._verifier, "verify", return_value=passed), \
             patch.object(worker, "_review", return_value=review_rejected):
            task = {
                "id": 1,
                "name": "Rejected code",
                "task_type": "code",
                "payload": {
                    "spec": "Write something",
                    "target_files": [str(target)],
                    "stakes": "high",
                },
            }
            result = worker.execute(task)

        assert result.success is False
        assert "review rejected" in result.error.lower()
        # File should be rolled back
        assert target.read_text() == "original\n"
