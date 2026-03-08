# src/merkaba/orchestration/health.py
import os
import shutil
import sqlite3
from dataclasses import dataclass, field

from merkaba.paths import merkaba_home as _merkaba_home


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    ok: bool
    detail: str


@dataclass
class HealthReport:
    """Aggregated health report from all checks."""

    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail}
                for c in self.checks
            ],
        }


@dataclass
class SystemHealthMonitor:
    """Checks system health: Ollama, databases, disk space, etc."""

    merkaba_dir: str = field(default_factory=_merkaba_home)
    ollama_url: str = "http://localhost:11434"

    def check_ollama(self) -> HealthCheck:
        try:
            import httpx
            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return HealthCheck("ollama", True, f"{len(models)} model(s) available")
        except Exception as e:
            return HealthCheck("ollama", False, f"unreachable: {e}")

    def check_db(self, db_name: str = "tasks.db") -> HealthCheck:
        db_path = os.path.join(self.merkaba_dir, db_name)
        if not os.path.exists(db_path):
            return HealthCheck(f"db:{db_name}", True, "not created yet")
        try:
            conn = sqlite3.connect(db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            ok = result[0] == "ok"
            return HealthCheck(f"db:{db_name}", ok, result[0])
        except Exception as e:
            return HealthCheck(f"db:{db_name}", False, str(e))

    def check_chromadb(self) -> HealthCheck:
        try:
            import chromadb
            client = chromadb.PersistentClient(
                path=os.path.join(self.merkaba_dir, "chroma")
            )
            collections = client.list_collections()
            return HealthCheck("chromadb", True, f"{len(collections)} collection(s)")
        except ImportError:
            return HealthCheck("chromadb", True, "not installed (optional)")
        except Exception as e:
            return HealthCheck("chromadb", False, str(e))

    def check_disk_space(self) -> HealthCheck:
        try:
            usage = shutil.disk_usage(self.merkaba_dir)
            pct_used = (usage.used / usage.total) * 100
            if pct_used > 90:
                return HealthCheck("disk", False, f"{pct_used:.1f}% used — low space")
            return HealthCheck("disk", True, f"{pct_used:.1f}% used")
        except Exception as e:
            return HealthCheck("disk", False, str(e))

    def check_all(self) -> HealthReport:
        checks = [
            self.check_ollama(),
            self.check_db("tasks.db"),
            self.check_db("memory.db"),
            self.check_chromadb(),
            self.check_disk_space(),
        ]
        return HealthReport(checks=checks)
