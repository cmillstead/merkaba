# tests/test_cli_config.py
import sys
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Mock ollama before merkaba imports
_original_ollama = sys.modules.get("ollama")
sys.modules["ollama"] = MagicMock()

from merkaba.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True, scope="module")
def _restore_ollama():
    yield
    if _original_ollama is not None:
        sys.modules["ollama"] = _original_ollama
    else:
        sys.modules.pop("ollama", None)


class TestConfigShowPrompt:
    def test_show_prompt_displays_resolved(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("My soul")
        (tmp_path / "USER.md").write_text("My user")
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert result.exit_code == 0
        assert "My soul" in result.output

    def test_show_prompt_with_business(self, tmp_path):
        biz_dir = tmp_path / "businesses" / "1"
        biz_dir.mkdir(parents=True)
        (biz_dir / "SOUL.md").write_text("Biz soul")
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt", "--business", "1"])
        assert result.exit_code == 0
        assert "Biz soul" in result.output

    def test_show_prompt_shows_sources(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Global")
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert "global" in result.output.lower()

    def test_show_prompt_shows_builtin_when_no_files(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)):
            result = runner.invoke(app, ["config", "show-prompt"])
        assert result.exit_code == 0
        assert "builtin" in result.output.lower()
        assert "Friday" in result.output


class TestConfigEditSoul:
    def test_edit_soul_seeds_default(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-soul"])
        assert result.exit_code == 0
        assert (tmp_path / "SOUL.md").exists()
        mock_run.assert_called_once()

    def test_edit_soul_business_creates_dir(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-soul", "--business", "5"])
        assert result.exit_code == 0
        biz_path = tmp_path / "businesses" / "5" / "SOUL.md"
        assert biz_path.exists()


class TestConfigEditUser:
    def test_edit_user_seeds_default(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-user"])
        assert result.exit_code == 0
        assert (tmp_path / "USER.md").exists()
        mock_run.assert_called_once()

    def test_edit_user_business_creates_dir(self, tmp_path):
        with patch("merkaba.cli.FRIDAY_DIR", str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["config", "edit-user", "--business", "3"])
        assert result.exit_code == 0
        biz_path = tmp_path / "businesses" / "3" / "USER.md"
        assert biz_path.exists()
