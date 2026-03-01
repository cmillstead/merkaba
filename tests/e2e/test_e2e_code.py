# tests/e2e/test_e2e_code.py
"""E2E tests for code CLI commands (review)."""

import os

import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.e2e]


class TestCodeReview:
    """Test merkaba code review with mocked LLM."""

    def test_review_single_file(self, cli_runner, tmp_path):
        runner, app = cli_runner

        # Create a temp Python file to review
        target = tmp_path / "example.py"
        target.write_text("def add(a, b):\n    return a + b\n")

        with patch(
            "merkaba.orchestration.review_worker.ReviewWorker._ask_llm",
            return_value="**Summary**: Clean implementation. No issues found.",
        ):
            result = runner.invoke(app, ["code", "review", str(target)])

        assert result.exit_code == 0
        assert "Clean implementation" in result.output

    def test_review_directory(self, cli_runner, tmp_path):
        runner, app = cli_runner

        # Create a temp directory with Python files
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n")
        (src / "b.py").write_text("y = 2\n")

        with patch(
            "merkaba.orchestration.review_worker.ReviewWorker._ask_llm",
            return_value="Reviewed 2 files. All good.",
        ):
            result = runner.invoke(app, ["code", "review", str(src)])

        assert result.exit_code == 0
        assert "2 file(s)" in result.output

    def test_review_with_criteria(self, cli_runner, tmp_path):
        runner, app = cli_runner

        target = tmp_path / "handler.py"
        target.write_text("def handle(req): pass\n")

        captured = {}

        def capture_llm(prompt, **kwargs):
            captured["prompt"] = prompt
            return "Error handling review complete."

        with patch(
            "merkaba.orchestration.review_worker.ReviewWorker._ask_llm",
            side_effect=capture_llm,
        ):
            result = runner.invoke(
                app,
                ["code", "review", str(target), "--criteria", "Check error handling"],
            )

        assert result.exit_code == 0
        assert "Check error handling" in captured["prompt"]

    def test_review_nonexistent_path(self, cli_runner):
        runner, app = cli_runner

        result = runner.invoke(app, ["code", "review", "/nonexistent/path.py"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_review_empty_directory(self, cli_runner, tmp_path):
        runner, app = cli_runner

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(app, ["code", "review", str(empty_dir)])

        assert result.exit_code == 0
        assert "No files to review" in result.output
