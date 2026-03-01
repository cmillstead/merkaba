# tests/test_explorer.py
"""Tests for ExplorationAgent, ExplorationResult, and ExplorationOrchestrator."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before any merkaba imports
sys.modules.setdefault("ollama", MagicMock())

from merkaba.orchestration.explorer import (
    ExplorationAgent,
    ExplorationOrchestrator,
    ExplorationResult,
    FILE_PREVIEW_BYTES,
    MAX_DIR_DEPTH,
    MAX_FILES_PER_DIR,
)


# --- ExplorationResult ---


class TestExplorationResult:
    def test_to_context_string_with_summaries(self):
        result = ExplorationResult(summaries=["Summary A", "Summary B", "Summary C"])
        ctx = result.to_context_string()
        assert "[Exploration 1] Summary A" in ctx
        assert "[Exploration 2] Summary B" in ctx
        assert "[Exploration 3] Summary C" in ctx
        # Summaries are separated by double newlines
        assert "\n\n" in ctx

    def test_to_context_string_single_summary(self):
        result = ExplorationResult(summaries=["Only one"])
        ctx = result.to_context_string()
        assert ctx == "[Exploration 1] Only one"

    def test_to_context_string_empty(self):
        result = ExplorationResult()
        assert result.to_context_string() == ""

    def test_token_estimate_default(self):
        result = ExplorationResult()
        assert result.token_estimate == 0


# --- ExplorationAgent._gather_listing / _walk ---


class TestGatherListing:
    def test_gather_listing_basic(self, tmp_path):
        (tmp_path / "a.py").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "c.py").write_text("nested")

        agent = ExplorationAgent()
        listing = agent._gather_listing(str(tmp_path))

        assert "a.py" in listing
        assert "b.txt" in listing
        assert "subdir/" in listing
        assert "c.py" in listing

    def test_gather_listing_empty_dir(self, tmp_path):
        agent = ExplorationAgent()
        listing = agent._gather_listing(str(tmp_path))
        assert listing == "(empty)"

    def test_depth_limiting(self, tmp_path):
        # Create a directory tree deeper than MAX_DIR_DEPTH
        # _walk starts at depth=0 for root; depth increments on each subdirectory.
        # Guard is `if depth > max_depth: return`, so:
        #   depth 0 = root (listed), depth 1 = level0 (listed),
        #   depth 2 = level1 (listed, == MAX_DIR_DEPTH),
        #   depth 3 = level2 (> MAX_DIR_DEPTH, skipped)
        current = tmp_path
        for i in range(MAX_DIR_DEPTH + 3):
            current = current / f"level{i}"
            current.mkdir()
            (current / f"file{i}.py").write_text(f"depth {i}")

        agent = ExplorationAgent()
        listing = agent._gather_listing(str(tmp_path))

        # Files within reachable depth should appear
        assert "file0.py" in listing  # depth 1
        assert "file1.py" in listing  # depth 2 (== MAX_DIR_DEPTH)
        # level2/ directory name appears at depth 2 but its contents (depth 3) are skipped
        assert "level2/" in listing
        assert "file2.py" not in listing  # depth 3, beyond MAX_DIR_DEPTH
        assert "file3.py" not in listing  # depth 4, well beyond

    def test_file_count_limiting(self, tmp_path):
        # Create more files than MAX_FILES_PER_DIR
        for i in range(MAX_FILES_PER_DIR + 10):
            (tmp_path / f"file_{i:04d}.txt").write_text(f"content {i}")

        agent = ExplorationAgent()
        listing = agent._gather_listing(str(tmp_path))

        # Should have the truncation message
        assert f"... and 10 more files" in listing

    def test_permission_denied(self, tmp_path):
        agent = ExplorationAgent()

        with patch("os.listdir", side_effect=PermissionError("nope")):
            lines: list[str] = []
            agent._walk(str(tmp_path), "", 0, MAX_DIR_DEPTH, lines)

        assert any("permission denied" in line for line in lines)

    def test_walk_separates_files_and_dirs(self, tmp_path):
        (tmp_path / "alpha.py").write_text("")
        (tmp_path / "beta_dir").mkdir()

        agent = ExplorationAgent()
        lines: list[str] = []
        agent._walk(str(tmp_path), "", 0, MAX_DIR_DEPTH, lines)

        # Files come before directories in output
        file_idx = next(i for i, line in enumerate(lines) if "alpha.py" in line)
        dir_idx = next(i for i, line in enumerate(lines) if "beta_dir/" in line)
        assert file_idx < dir_idx

    def test_walk_indentation(self, tmp_path):
        sub = tmp_path / "child"
        sub.mkdir()
        (sub / "nested.py").write_text("")

        agent = ExplorationAgent()
        lines: list[str] = []
        agent._walk(str(tmp_path), "", 0, MAX_DIR_DEPTH, lines)

        # Child dir should have its files indented
        nested_line = [line for line in lines if "nested.py" in line][0]
        assert nested_line.startswith("  ")


# --- ExplorationAgent._read_file_preview ---


class TestReadFilePreview:
    def test_read_file_within_limit(self, tmp_path):
        f = tmp_path / "small.py"
        content = "print('hello world')\n"
        f.write_text(content)

        agent = ExplorationAgent()
        preview = agent._read_file_preview(str(f))
        assert preview == content

    def test_read_file_truncation(self, tmp_path):
        f = tmp_path / "large.py"
        content = "x" * (FILE_PREVIEW_BYTES * 2)
        f.write_text(content)

        agent = ExplorationAgent()
        preview = agent._read_file_preview(str(f))
        assert len(preview) == FILE_PREVIEW_BYTES

    def test_read_file_oserror(self, tmp_path):
        agent = ExplorationAgent()
        preview = agent._read_file_preview(str(tmp_path / "nonexistent.py"))
        assert "could not read" in preview

    def test_read_file_unicode_error(self, tmp_path):
        # The code uses errors="replace" so UnicodeDecodeError is caught at open() level
        # We can simulate an OSError instead, which is more realistic
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x80\x81\x82\x00\xff")

        agent = ExplorationAgent()
        # With errors="replace", binary files are read with replacement chars, not errors
        preview = agent._read_file_preview(str(f))
        assert isinstance(preview, str)

    def test_read_file_oserror_via_mock(self):
        agent = ExplorationAgent()
        with patch("builtins.open", side_effect=OSError("disk error")):
            preview = agent._read_file_preview("/fake/path.py")
        assert "could not read" in preview
        assert "disk error" in preview


# --- ExplorationAgent.map_directory ---


class TestMapDirectory:
    def test_map_directory_nonexistent(self):
        agent = ExplorationAgent()
        result = agent.map_directory("/nonexistent/path/abc123")
        assert "does not exist" in result

    def test_map_directory_calls_llm(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")

        agent = ExplorationAgent()
        with patch.object(agent, "_ask", return_value="This is a Python project with a main entry point.") as mock_ask:
            result = agent.map_directory(str(tmp_path), focus="entry points")

        mock_ask.assert_called_once()
        call_args = mock_ask.call_args
        prompt = call_args[0][0]
        assert "main.py" in prompt
        assert "Focus: entry points" in prompt
        assert result == "This is a Python project with a main entry point."

    def test_map_directory_without_focus(self, tmp_path):
        (tmp_path / "app.py").write_text("")

        agent = ExplorationAgent()
        with patch.object(agent, "_ask", return_value="Summary") as mock_ask:
            agent.map_directory(str(tmp_path))

        prompt = mock_ask.call_args[0][0]
        assert "Focus:" not in prompt


# --- ExplorationAgent.trace_functionality ---


class TestTraceFunctionality:
    def test_trace_nonexistent_file(self):
        agent = ExplorationAgent()
        result = agent.trace_functionality("/nonexistent/file.py")
        assert "does not exist" in result

    def test_trace_calls_llm_with_preview(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("class Foo:\n    pass\n")

        agent = ExplorationAgent()
        with patch.object(agent, "_ask", return_value="A simple class definition.") as mock_ask:
            result = agent.trace_functionality(str(f), question="What does Foo do?")

        mock_ask.assert_called_once()
        prompt = mock_ask.call_args[0][0]
        assert "class Foo" in prompt
        assert "Question: What does Foo do?" in prompt
        assert result == "A simple class definition."

    def test_trace_without_question(self, tmp_path):
        f = tmp_path / "util.py"
        f.write_text("def helper(): pass\n")

        agent = ExplorationAgent()
        with patch.object(agent, "_ask", return_value="Helper utility.") as mock_ask:
            agent.trace_functionality(str(f))

        prompt = mock_ask.call_args[0][0]
        assert "Question:" not in prompt


# --- ExplorationOrchestrator.explore ---


class TestExplorationOrchestrator:
    def test_explore_directory_partition(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.py").write_text("entry point")

        orchestrator = ExplorationOrchestrator()
        task = {"name": "Understand codebase"}

        with patch.object(
            ExplorationAgent, "map_directory", return_value="Directory summary here."
        ):
            result = orchestrator.explore(task, [str(sub)])

        assert len(result.summaries) == 1
        assert "Directory summary here." in result.summaries[0]
        assert result.token_estimate > 0

    def test_explore_file_partition(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text("SETTING = True")

        orchestrator = ExplorationOrchestrator()
        task = {"name": "Understand config"}

        with patch.object(
            ExplorationAgent, "trace_functionality", return_value="Config file with settings."
        ):
            result = orchestrator.explore(task, [str(f)])

        assert len(result.summaries) == 1
        assert "Config file with settings." in result.summaries[0]

    def test_explore_multi_partition(self, tmp_path):
        dir1 = tmp_path / "pkg1"
        dir1.mkdir()
        file1 = tmp_path / "standalone.py"
        file1.write_text("")
        dir2 = tmp_path / "pkg2"
        dir2.mkdir()

        orchestrator = ExplorationOrchestrator()
        task = {"name": "Full exploration"}

        with patch.object(
            ExplorationAgent, "map_directory", return_value="Dir summary"
        ), patch.object(
            ExplorationAgent, "trace_functionality", return_value="File summary"
        ):
            result = orchestrator.explore(task, [str(dir1), str(file1), str(dir2)])

        assert len(result.summaries) == 3
        # Token estimate is cumulative
        assert result.token_estimate > 0

    def test_explore_empty_partitions(self):
        orchestrator = ExplorationOrchestrator()
        task = {"name": "Nothing to explore"}

        result = orchestrator.explore(task, [])

        assert len(result.summaries) == 0
        assert result.token_estimate == 0
        assert result.to_context_string() == ""

    def test_explore_uses_task_name_as_focus(self, tmp_path):
        sub = tmp_path / "mydir"
        sub.mkdir()

        orchestrator = ExplorationOrchestrator()
        task = {"name": "Find authentication logic"}

        with patch.object(ExplorationAgent, "map_directory", return_value="Auth summary") as mock_map:
            orchestrator.explore(task, [str(sub)])

        mock_map.assert_called_once_with(str(sub), focus="Find authentication logic")

    def test_explore_token_estimate_accumulates(self, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("")
        f2 = tmp_path / "b.py"
        f2.write_text("")

        orchestrator = ExplorationOrchestrator()
        task = {"name": "test"}

        # Each summary is 20 chars => ~5 tokens each
        with patch.object(
            ExplorationAgent, "trace_functionality", return_value="x" * 20
        ):
            result = orchestrator.explore(task, [str(f1), str(f2)])

        assert result.token_estimate == 10  # 20//4 + 20//4
