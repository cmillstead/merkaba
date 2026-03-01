"""Tests for file integrity checking."""

import json
import pytest
from pathlib import Path

# Check if required dependencies are available
try:
    from merkaba.security.integrity import compute_file_hash, compute_directory_hashes, compare_with_baseline, IntegrityReport, save_baseline, load_baseline
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    compute_file_hash = None
    compute_directory_hashes = None
    compare_with_baseline = None
    IntegrityReport = None
    save_baseline = None
    load_baseline = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestFileHashing:
    def test_compute_file_hash_returns_sha256(self, tmp_path):
        """Should return SHA256 hash of file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = compute_file_hash(test_file)

        # SHA256 of "hello world"
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_compute_file_hash_nonexistent_returns_none(self, tmp_path):
        """Should return None for missing files."""
        result = compute_file_hash(tmp_path / "missing.txt")
        assert result is None


class TestDirectoryHashing:
    def test_compute_directory_hashes_returns_dict(self, tmp_path):
        """Should return dict of relative paths to hashes."""
        (tmp_path / "a.py").write_text("content a")
        (tmp_path / "b.py").write_text("content b")

        result = compute_directory_hashes(tmp_path, pattern="*.py")

        assert len(result) == 2
        assert "a.py" in result
        assert "b.py" in result

    def test_compute_directory_hashes_uses_relative_paths(self, tmp_path):
        """Paths should be relative to the directory."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "file.py").write_text("content")

        result = compute_directory_hashes(tmp_path, pattern="**/*.py")

        assert "sub/file.py" in result


class TestBaselineComparison:
    def test_no_changes_returns_empty_report(self):
        """Should report no issues when hashes match."""
        current = {"a.py": "hash1", "b.py": "hash2"}
        baseline = {"a.py": "hash1", "b.py": "hash2"}

        report = compare_with_baseline(current, baseline)

        assert report.modified == []
        assert report.added == []
        assert report.removed == []
        assert report.has_issues is False

    def test_modified_file_detected(self):
        """Should detect when file hash changes."""
        current = {"a.py": "new_hash"}
        baseline = {"a.py": "old_hash"}

        report = compare_with_baseline(current, baseline)

        assert report.modified == ["a.py"]
        assert report.has_issues is True

    def test_added_file_detected(self):
        """Should detect new files not in baseline."""
        current = {"a.py": "hash1", "new.py": "hash2"}
        baseline = {"a.py": "hash1"}

        report = compare_with_baseline(current, baseline)

        assert report.added == ["new.py"]

    def test_removed_file_detected(self):
        """Should detect files missing from current."""
        current = {"a.py": "hash1"}
        baseline = {"a.py": "hash1", "old.py": "hash2"}

        report = compare_with_baseline(current, baseline)

        assert report.removed == ["old.py"]


class TestBaselinePersistence:
    def test_save_baseline_creates_json(self, tmp_path):
        """Should save hashes to JSON file."""
        baseline_file = tmp_path / "baseline.json"
        hashes = {"a.py": "hash1", "b.py": "hash2"}

        save_baseline(hashes, baseline_file)

        assert baseline_file.exists()
        loaded = json.loads(baseline_file.read_text())
        assert loaded == hashes

    def test_load_baseline_reads_json(self, tmp_path):
        """Should load hashes from JSON file."""
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text('{"a.py": "hash1"}')

        result = load_baseline(baseline_file)

        assert result == {"a.py": "hash1"}

    def test_load_baseline_returns_empty_if_missing(self, tmp_path):
        """Should return empty dict if file doesn't exist."""
        result = load_baseline(tmp_path / "missing.json")
        assert result == {}