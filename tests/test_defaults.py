"""Tests for centralised default model names."""

import subprocess
import sys


from merkaba.config.defaults import DEFAULT_MODELS, FALLBACK_CHAINS


class TestDefaultModels:
    """Verify DEFAULT_MODELS contains all expected keys and values."""

    def test_has_expected_keys(self):
        expected = {"complex", "simple", "classifier", "embedding", "health_check"}
        assert set(DEFAULT_MODELS.keys()) == expected

    def test_values_are_nonempty_strings(self):
        for key, value in DEFAULT_MODELS.items():
            assert isinstance(value, str), f"{key} should be a string"
            assert len(value) > 0, f"{key} should be non-empty"

    def test_complex_model(self):
        assert DEFAULT_MODELS["complex"] == "qwen3.5:122b"

    def test_simple_model(self):
        assert DEFAULT_MODELS["simple"] == "qwen3:8b"

    def test_classifier_model(self):
        assert DEFAULT_MODELS["classifier"] == "qwen3:4b"

    def test_embedding_model(self):
        assert DEFAULT_MODELS["embedding"] == "nomic-embed-text"

    def test_health_check_model(self):
        assert DEFAULT_MODELS["health_check"] == "phi4:14b"


class TestFallbackChains:
    """Verify FALLBACK_CHAINS structure references DEFAULT_MODELS."""

    def test_has_expected_tiers(self):
        assert set(FALLBACK_CHAINS.keys()) == {"complex", "simple", "classifier"}

    def test_complex_chain(self):
        chain = FALLBACK_CHAINS["complex"]
        assert chain["primary"] == DEFAULT_MODELS["complex"]
        assert DEFAULT_MODELS["simple"] in chain["fallbacks"]

    def test_simple_chain(self):
        chain = FALLBACK_CHAINS["simple"]
        assert chain["primary"] == DEFAULT_MODELS["simple"]
        assert DEFAULT_MODELS["classifier"] in chain["fallbacks"]

    def test_classifier_chain(self):
        chain = FALLBACK_CHAINS["classifier"]
        assert chain["primary"] == DEFAULT_MODELS["classifier"]
        assert chain["fallbacks"] == []

    def test_all_chains_have_timeout(self):
        for tier, chain in FALLBACK_CHAINS.items():
            assert "timeout" in chain, f"{tier} missing timeout"
            assert isinstance(chain["timeout"], (int, float))


class TestNoHardcodedModelStrings:
    """Verify that hardcoded model name strings only appear in defaults.py
    (and comments/docstrings in other files)."""

    def test_qwen_only_in_defaults(self):
        """Grep the source tree for hardcoded qwen model strings.

        They should only appear in config/defaults.py (the single definition)
        and in comments/docstrings elsewhere.
        """
        # Use a subprocess that skips comments AND docstrings
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import ast, pathlib, re, sys, tokenize, io\n"
                "root = pathlib.Path('src/merkaba')\n"
                "pattern = re.compile(r'[\"\\']qwen3[^\"\\']+')\n"
                "hits = []\n"
                "for p in sorted(root.rglob('*.py')):\n"
                "    if '__pycache__' in str(p):\n"
                "        continue\n"
                "    source = p.read_text()\n"
                "    # Find lines that are inside docstrings\n"
                "    docstring_lines = set()\n"
                "    try:\n"
                "        tree = ast.parse(source)\n"
                "        for node in ast.walk(tree):\n"
                "            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):\n"
                "                ds = ast.get_docstring(node, clean=False)\n"
                "                if ds and hasattr(node, 'body') and node.body:\n"
                "                    ds_node = node.body[0]\n"
                "                    if isinstance(ds_node, ast.Expr) and isinstance(ds_node.value, (ast.Constant, ast.Str)):\n"
                "                        for ln in range(ds_node.lineno, ds_node.end_lineno + 1):\n"
                "                            docstring_lines.add(ln)\n"
                "    except SyntaxError:\n"
                "        continue\n"
                "    for i, line in enumerate(source.splitlines(), 1):\n"
                "        stripped = line.lstrip()\n"
                "        if stripped.startswith('#'):\n"
                "            continue\n"
                "        if i in docstring_lines:\n"
                "            continue\n"
                "        if pattern.search(line):\n"
                "            hits.append(f'{p}:{i}: {line.strip()}')\n"
                "for h in hits:\n"
                "    print(h)\n"
                "sys.exit(len(hits))\n"
            ],
            capture_output=True,
            text=True,
            cwd=str(subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True
            ).stdout.strip()),
        )

        # Filter: only defaults.py should contain quoted qwen model strings
        lines = [l for l in result.stdout.strip().splitlines() if l]
        non_defaults = [l for l in lines if "config/defaults.py" not in l]

        assert non_defaults == [], (
            "Hardcoded qwen model strings found outside defaults.py:\n"
            + "\n".join(non_defaults)
        )
