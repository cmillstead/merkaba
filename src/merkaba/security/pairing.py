# src/merkaba/security/pairing.py
"""Gateway pairing for new channel connections.

One-time 6-char alphanumeric code displayed on a trusted channel (CLI).
User enters the code on the new channel to pair it. Codes expire after
a configurable timeout. Paired identities are stored for future sessions.
"""

import logging
import secrets
import time
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PairingSession:
    channel: str
    identity: str
    code: str
    created_at: float = field(default_factory=time.time)


class GatewayPairing:
    """Manages gateway pairing authentication.

    New channels must pair via a 6-character code before they can
    interact with the agent. CLI is always trusted (bypasses pairing).
    """

    def __init__(self, expiry_seconds: float = 300.0):
        self.expiry_seconds = expiry_seconds
        self._sessions: dict[str, PairingSession] = {}
        self._paired: set[str] = set()
        self._lock = threading.Lock()

    def initiate(self, channel: str, identity: str) -> str:
        """Start a pairing session. Returns a 6-char code."""
        code = secrets.token_hex(3).upper()[:6]  # 6 hex chars
        with self._lock:
            self._sessions[identity] = PairingSession(
                channel=channel,
                identity=identity,
                code=code,
            )
        logger.info("Pairing initiated for %s on %s", identity, channel)
        return code

    def confirm(self, identity: str, code: str) -> bool:
        """Confirm a pairing code. Returns True if valid and not expired."""
        with self._lock:
            session = self._sessions.get(identity)
            if not session:
                return False

            # Check expiry
            if time.time() - session.created_at > self.expiry_seconds:
                del self._sessions[identity]
                return False

            # Check code (constant-time comparison)
            if not secrets.compare_digest(session.code, code):
                return False

            # Pair the identity
            self._paired.add(identity)
            del self._sessions[identity]
            logger.info("Identity paired: %s", identity)
            return True

    def is_paired(self, identity: str) -> bool:
        """Check if an identity is paired."""
        with self._lock:
            return identity in self._paired

    def revoke(self, identity: str):
        """Revoke a paired identity."""
        with self._lock:
            self._paired.discard(identity)
            logger.info("Identity revoked: %s", identity)

    def list_paired(self) -> list[str]:
        """List all paired identities."""
        with self._lock:
            return sorted(self._paired)
