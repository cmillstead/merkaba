# tests/test_prompt_loader.py
import pytest
from merkaba.config.prompts import PromptLoader, DEFAULT_SOUL, DEFAULT_USER


class TestPromptLoader:
    def test_returns_builtin_defaults_when_no_files(self, tmp_path):
        loader = PromptLoader(base_dir=str(tmp_path))
        soul, user = loader.load()
        assert "Merkaba" in soul
        assert len(user) > 0

    def test_loads_global_soul_file(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Custom soul")
        loader = PromptLoader(base_dir=str(tmp_path))
        soul, user = loader.load()
        assert soul == "Custom soul"

    def test_loads_global_user_file(self, tmp_path):
        (tmp_path / "USER.md").write_text("Custom user")
        loader = PromptLoader(base_dir=str(tmp_path))
        soul, user = loader.load()
        assert user == "Custom user"

    def test_business_overrides_global(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Global soul")
        biz_dir = tmp_path / "businesses" / "1"
        biz_dir.mkdir(parents=True)
        (biz_dir / "SOUL.md").write_text("Business 1 soul")
        loader = PromptLoader(base_dir=str(tmp_path))
        soul, user = loader.load(business_id=1)
        assert soul == "Business 1 soul"

    def test_business_falls_back_to_global(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Global soul")
        loader = PromptLoader(base_dir=str(tmp_path))
        soul, user = loader.load(business_id=99)
        assert soul == "Global soul"

    def test_resolve_shows_fallback_chain(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("Global")
        biz_dir = tmp_path / "businesses" / "1"
        biz_dir.mkdir(parents=True)
        (biz_dir / "USER.md").write_text("Biz user")
        loader = PromptLoader(base_dir=str(tmp_path))
        info = loader.resolve(business_id=1)
        assert info["soul_source"] == "global"
        assert info["user_source"] == "business"

    def test_seed_creates_default_files(self, tmp_path):
        loader = PromptLoader(base_dir=str(tmp_path))
        loader.seed()
        assert (tmp_path / "SOUL.md").exists()
        assert (tmp_path / "USER.md").exists()
        assert "Merkaba" in (tmp_path / "SOUL.md").read_text()

    def test_seed_does_not_overwrite_existing(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("My custom soul")
        loader = PromptLoader(base_dir=str(tmp_path))
        loader.seed()
        assert (tmp_path / "SOUL.md").read_text() == "My custom soul"
