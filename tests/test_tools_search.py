# tests/test_tools_search.py
import pytest
from merkaba.tools.builtin.search import grep, glob


class TestGrepTool:
    def test_grep_finds_pattern(self, tmp_path):
        """grep should find matching lines."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line one\nline two\nline three\n")
        result = grep.execute(pattern="two", path=str(test_file))
        assert result.success
        assert "line two" in result.output

    def test_grep_returns_line_numbers(self, tmp_path):
        """grep should include line numbers."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo\nbar\nfoo again\n")
        result = grep.execute(pattern="foo", path=str(test_file))
        assert result.success
        assert "1:" in result.output
        assert "3:" in result.output

    def test_grep_regex_pattern(self, tmp_path):
        """grep should support regex patterns."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("apple\nbanana\napricot\n")
        result = grep.execute(pattern="^a", path=str(test_file))
        assert result.success
        assert "apple" in result.output
        assert "apricot" in result.output
        assert "banana" not in result.output

    def test_grep_no_match(self, tmp_path):
        """grep should return empty output when no match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line one\nline two\n")
        result = grep.execute(pattern="xyz", path=str(test_file))
        assert result.success
        assert result.output == ""

    def test_grep_directory_recursive(self, tmp_path):
        """grep should search recursively in directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("hello world\n")
        (subdir / "file2.txt").write_text("hello again\n")
        result = grep.execute(pattern="hello", path=str(tmp_path))
        assert result.success
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output

    def test_grep_directory_includes_filepath(self, tmp_path):
        """grep on directory should include filepath:linenum:content format."""
        (tmp_path / "test.txt").write_text("match here\n")
        result = grep.execute(pattern="match", path=str(tmp_path))
        assert result.success
        # Format should be filepath:linenum:content
        assert "test.txt:1:match here" in result.output

    def test_grep_handles_unicode_error(self, tmp_path):
        """grep should handle binary/non-UTF8 files gracefully."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x80\x81\x82\x83invalid utf8")
        result = grep.execute(pattern="test", path=str(binary_file))
        # Should not crash, should succeed (just skip the file)
        assert result.success

    def test_grep_handles_permission_error(self, tmp_path):
        """grep should handle permission errors gracefully."""
        test_file = tmp_path / "restricted.txt"
        test_file.write_text("secret content\n")
        test_file.chmod(0o000)
        try:
            result = grep.execute(pattern="secret", path=str(test_file))
            # Should not crash
            assert result.success or result.error is not None
        finally:
            # Restore permissions for cleanup
            test_file.chmod(0o644)

    def test_grep_nonexistent_path(self, tmp_path):
        """grep should handle nonexistent paths."""
        result = grep.execute(pattern="test", path=str(tmp_path / "nonexistent.txt"))
        assert not result.success
        assert result.error is not None


class TestGlobTool:
    def test_glob_finds_files(self, tmp_path):
        """glob should find matching files."""
        (tmp_path / "foo.py").write_text("")
        (tmp_path / "bar.py").write_text("")
        (tmp_path / "baz.txt").write_text("")
        result = glob.execute(pattern="*.py", path=str(tmp_path))
        assert result.success
        assert "foo.py" in result.output
        assert "bar.py" in result.output
        assert "baz.txt" not in result.output

    def test_glob_recursive(self, tmp_path):
        """glob should support ** for recursive matching."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.py").write_text("")
        result = glob.execute(pattern="**/*.py", path=str(tmp_path))
        assert result.success
        assert "nested.py" in result.output
