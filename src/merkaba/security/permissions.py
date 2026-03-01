# src/merkaba/security.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from merkaba.tools.base import PermissionTier


class PermissionDenied(Exception):
    """Raised when a tool execution is denied."""

    def __init__(self, tool_name: str, tier: PermissionTier):
        self.tool_name = tool_name
        self.tier = tier
        super().__init__(f"Permission denied for {tool_name} (requires {tier.name})")


@dataclass
class PermissionManager:
    """Manages tool execution permissions."""

    auto_approve_level: PermissionTier = PermissionTier.SAFE
    approval_callback: Callable[[str, PermissionTier], bool] | None = None
    _audit_log: list[dict] = field(default_factory=list)

    def check(
        self,
        tool_name: str,
        tier: PermissionTier,
        require_approval: bool = True,
    ) -> bool:
        """Check if a tool execution is permitted."""
        self._log_attempt(tool_name, tier)

        # Auto-approve if within threshold
        if tier <= self.auto_approve_level:
            self._log_decision(tool_name, tier, "auto_approved")
            return True

        # If callback provided, ask for approval
        if self.approval_callback:
            approved = self.approval_callback(tool_name, tier)
            self._log_decision(tool_name, tier, "approved" if approved else "denied")
            if approved:
                return True

        # Deny if approval required
        if require_approval:
            self._log_decision(tool_name, tier, "denied")
            raise PermissionDenied(tool_name, tier)

        return False

    def _log_attempt(self, tool_name: str, tier: PermissionTier):
        """Log a permission check attempt."""
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "tier": tier.name,
            "type": "attempt",
        })

    def _log_decision(self, tool_name: str, tier: PermissionTier, decision: str):
        """Log a permission decision."""
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "tier": tier.name,
            "type": "decision",
            "result": decision,
        })

    def get_audit_log(self) -> list[dict]:
        """Return the audit log."""
        return self._audit_log.copy()
