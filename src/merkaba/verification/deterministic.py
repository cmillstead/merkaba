# src/friday/verification/deterministic.py
import logging
import shutil
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
}

CHECKS: dict[str, list[tuple[str, list[str]]]] = {
    "python": [
        ("ruff", ["ruff", "check", "{file}"]),
        ("mypy", ["mypy", "{file}", "--no-error-summary"]),
    ],
    "javascript": [
        ("eslint", ["npx", "eslint", "{file}"]),
    ],
    "typescript": [
        ("eslint", ["npx", "eslint", "{file}"]),
        ("tsc", ["npx", "tsc", "--noEmit", "{file}"]),
    ],
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    output: str


@dataclass
class VerificationResult:
    passed: bool
    checks: list[CheckResult]
    summary: str


@dataclass
class DeterministicVerifier:
    enabled: bool = True
    timeout: int = 30

    def verify(self, file_path: str) -> VerificationResult | None:
        if not self.enabled:
            return None

        ext = _get_extension(file_path)
        language = LANGUAGE_MAP.get(ext)
        if not language:
            logger.debug("No verifier for extension: %s", ext)
            return None

        check_defs = CHECKS.get(language, [])
        if not check_defs:
            return None

        results: list[CheckResult] = []
        for name, cmd_template in check_defs:
            result = self._run_check(name, cmd_template, file_path)
            if result:
                results.append(result)

        if not results:
            return None

        passed = all(r.passed for r in results)
        summary = _build_summary(results)
        return VerificationResult(passed=passed, checks=results, summary=summary)

    def _run_check(self, name: str, cmd_template: list[str], file_path: str) -> CheckResult | None:
        executable = cmd_template[0]
        if not shutil.which(executable):
            logger.debug("Skipping %s check: %s not on PATH", name, executable)
            return None

        cmd = [part.replace("{file}", file_path) for part in cmd_template]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            passed = proc.returncode == 0
            output = (proc.stdout + proc.stderr).strip()
            return CheckResult(name=name, passed=passed, output=output)
        except subprocess.TimeoutExpired:
            logger.warning("%s timed out after %ds for %s", name, self.timeout, file_path)
            return CheckResult(name=name, passed=False, output=f"Timed out after {self.timeout}s")
        except Exception as e:
            logger.warning("%s failed for %s: %s", name, file_path, e)
            return None


def _get_extension(file_path: str) -> str:
    dot = file_path.rfind(".")
    if dot == -1:
        return ""
    return file_path[dot:].lower()


def _build_summary(results: list[CheckResult]) -> str:
    failures = [r for r in results if not r.passed]
    if not failures:
        passed_names = ", ".join(r.name for r in results)
        return f"All checks passed: {passed_names}"
    parts = []
    for f in failures:
        parts.append(f"[{f.name}] FAILED:\n{f.output}")
    return "\n\n".join(parts)
