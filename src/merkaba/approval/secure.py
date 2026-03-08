# src/merkaba/approval/secure.py
"""Secure approval manager with TOTP 2FA and rate limiting."""

import json
import logging
import os
from dataclasses import dataclass, field

from merkaba.approval.queue import ActionQueue

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when approval rate limit is exceeded."""

    def __init__(self, recent_count: int, max_approvals: int, window_seconds: int):
        self.recent_count = recent_count
        self.max_approvals = max_approvals
        self.window_seconds = window_seconds
        super().__init__(
            f"Rate limit exceeded: {recent_count}/{max_approvals} "
            f"approvals in last {window_seconds}s"
        )


class TotpRequired(Exception):
    """Raised when TOTP code is required but not provided."""

    def __init__(self, action_id: int):
        self.action_id = action_id
        super().__init__(f"TOTP code required for action #{action_id}")


class TotpInvalid(Exception):
    """Raised when TOTP code is invalid."""

    def __init__(self, action_id: int):
        self.action_id = action_id
        super().__init__(f"Invalid TOTP code for action #{action_id}")


@dataclass
class RateLimitConfig:
    """Configuration for approval rate limiting."""

    max_approvals: int = 5
    window_seconds: int = 60


@dataclass
class SecureApprovalManager:
    """Wraps ActionQueue with TOTP 2FA and rate limiting."""

    action_queue: ActionQueue
    totp_secret: str | None = None
    totp_threshold: int = 3
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    _totp: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.totp_secret:
            import pyotp

            self._totp = pyotp.TOTP(self.totp_secret)

    def requires_second_factor(self, action: dict) -> bool:
        """Check if action requires TOTP 2FA."""
        if self._totp is None:
            return False
        return action.get("autonomy_level", 0) >= self.totp_threshold

    def verify_totp(self, code: str) -> bool:
        """Verify a TOTP code. Returns False if 2FA not configured."""
        if self._totp is None:
            return False
        return self._totp.verify(code)

    def check_rate_limit(self) -> tuple[bool, int]:
        """Check if approval rate limit allows another approval.

        Returns (allowed, recent_count).
        """
        recent = self.action_queue.count_recent_approvals(
            window_seconds=self.rate_limit.window_seconds
        )
        return recent < self.rate_limit.max_approvals, recent

    def approve(
        self,
        action_id: int,
        decided_by: str = "cli",
        totp_code: str | None = None,
        skip_2fa: bool = False,
    ) -> dict | None:
        """Approve an action with rate limiting and optional 2FA.

        Raises:
            RateLimitExceeded: If too many recent approvals.
            TotpRequired: If 2FA is needed but no code provided.
            TotpInvalid: If the provided TOTP code is wrong.
        """
        # Rate limit check
        allowed, recent_count = self.check_rate_limit()
        if not allowed:
            self._audit("rate_limit_blocked", f"action #{action_id} blocked")
            raise RateLimitExceeded(
                recent_count, self.rate_limit.max_approvals, self.rate_limit.window_seconds
            )

        # 2FA check
        if not skip_2fa:
            action = self.action_queue.get_action(action_id)
            if action and self.requires_second_factor(action):
                if totp_code is None:
                    raise TotpRequired(action_id)
                if not self.verify_totp(totp_code):
                    self._audit("2fa_failure", f"invalid TOTP for action #{action_id}")
                    raise TotpInvalid(action_id)
                self._audit("2fa_approval", f"action #{action_id} approved with 2FA")

        result = self.action_queue.decide(action_id, approved=True, decided_by=decided_by)
        return result

    def deny(self, action_id: int, decided_by: str = "cli") -> dict | None:
        """Deny an action. No rate limit or 2FA required for denials."""
        return self.action_queue.decide(action_id, approved=False, decided_by=decided_by)

    def _audit(self, decision_type: str, decision: str) -> None:
        """Record to audit trail. Fire-and-forget."""
        try:
            from merkaba.observability.audit import record_decision

            record_decision(decision_type=decision_type, decision=decision)
        except Exception:
            pass

    @classmethod
    def from_config(cls, action_queue: ActionQueue) -> "SecureApprovalManager":
        """Create from keychain + config file."""
        # Load TOTP secret
        totp_secret = None
        try:
            from merkaba.security.secrets import get_secret

            totp_secret = get_secret("totp_secret")
        except Exception:
            pass

        # Load config
        totp_threshold = 3
        rate_config = RateLimitConfig()
        from merkaba.config.loader import load_config
        config = load_config()
        security = config.get("security", {})
        totp_threshold = security.get("totp_threshold", 3)
        rl = security.get("approval_rate_limit", {})
        if rl:
            rate_config = RateLimitConfig(
                max_approvals=rl.get("max_approvals", 5),
                window_seconds=rl.get("window_seconds", 60),
            )

        return cls(
            action_queue=action_queue,
            totp_secret=totp_secret,
            totp_threshold=totp_threshold,
            rate_limit=rate_config,
        )
