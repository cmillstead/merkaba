# tests/test_builtin_tools.py
import tempfile
import os
import pytest
from merkaba.tools.builtin.files import file_read, file_write, file_list
from merkaba.tools.base import PermissionTier


def test_file_read_tool_exists():
    assert file_read.name == "file_read"
    assert file_read.permission_tier == PermissionTier.SAFE


def test_file_write_tool_exists():
    assert file_write.name == "file_write"
    assert file_write.permission_tier == PermissionTier.MODERATE


def test_file_read_execution():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello, Friday!")
        temp_path = f.name

    try:
        result = file_read.execute(path=temp_path)
        assert result.success is True
        assert result.output == "Hello, Friday!"
    finally:
        os.unlink(temp_path)


def test_file_read_nonexistent():
    result = file_read.execute(path="/nonexistent/file.txt")
    assert result.success is False
    assert "No such file" in result.error or "FileNotFoundError" in result.error


def test_file_write_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.txt")
        result = file_write.execute(path=path, content="Test content")
        assert result.success is True

        with open(path) as f:
            assert f.read() == "Test content"


def test_file_list_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        open(os.path.join(tmpdir, "file1.txt"), "w").close()
        open(os.path.join(tmpdir, "file2.txt"), "w").close()
        os.mkdir(os.path.join(tmpdir, "subdir"))

        result = file_list.execute(path=tmpdir)
        assert result.success is True
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert "subdir" in result.output
