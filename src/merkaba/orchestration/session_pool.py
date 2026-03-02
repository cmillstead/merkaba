# src/merkaba/orchestration/session_pool.py
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from merkaba.orchestration.lane_queue import LaneQueue

if TYPE_CHECKING:
    from merkaba.security.pairing import GatewayPairing

logger = logging.getLogger(__name__)

PAIRING_PROMPT = (
    "This channel is not yet paired. "
    "Use `merkaba pair confirm <CODE>` on the CLI to pair it."
)


@dataclass
class SessionEntry:
    """Tracks an Agent instance and its last activity time."""
    agent: Any
    last_active: float = field(default_factory=time.time)


class SessionPool:
    """Manages Agent instances per session with LaneQueue serialization.

    Creates Agent on first message for a session, reuses on subsequent.
    Configurable max_sessions and idle_timeout for eviction.
    """

    def __init__(
        self,
        max_sessions: int = 100,
        idle_timeout: float = 3600.0,
        agent_kwargs: dict | None = None,
        pairing: GatewayPairing | None = None,
    ):
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.agent_kwargs = agent_kwargs or {}
        self.pairing = pairing
        self._agents: dict[str, SessionEntry] = {}
        self._lock = threading.Lock()
        self._lane_queue = LaneQueue()

    def _create_agent(self, **kwargs) -> Any:
        """Create a new Agent instance. Override in tests."""
        from merkaba.agent import Agent
        merged = {**self.agent_kwargs, **kwargs}
        return Agent(**merged)

    def _get_or_create_agent(self, session_id: str) -> Any:
        """Get existing agent or create a new one for this session."""
        with self._lock:
            if session_id in self._agents:
                entry = self._agents[session_id]
                entry.last_active = time.time()
                return entry.agent

            # Evict if at capacity
            if len(self._agents) >= self.max_sessions:
                self._evict_oldest()

            agent = self._create_agent()
            self._agents[session_id] = SessionEntry(agent=agent)
            logger.info("Created agent for session %s (%d active)", session_id, len(self._agents))
            return agent

    @staticmethod
    def _extract_channel(session_id: str) -> str:
        """Extract the channel prefix from a session ID.

        Session IDs use the format ``channel:sender[:topic:id][:biz:id]``.
        Returns the first segment before ``:``, or the full string if no
        colon is present.
        """
        return session_id.split(":", 1)[0]

    def _requires_pairing(self, session_id: str) -> bool:
        """Return True if this session must be paired but is not yet."""
        if self.pairing is None:
            return False
        if self._extract_channel(session_id) == "cli":
            return False
        if self.pairing.is_paired(session_id):
            return False
        return True

    def submit_sync(self, session_id: str, message: str, **kwargs) -> str:
        """Submit a message for processing. Serialized per-session.

        If gateway pairing is configured and the session's channel is not
        CLI and the identity is not yet paired, returns a pairing prompt
        instead of creating an Agent or processing the message.
        """
        if self._requires_pairing(session_id):
            logger.info("Unpaired session blocked: %s", session_id)
            return PAIRING_PROMPT

        agent = self._get_or_create_agent(session_id)
        agent.session_id = session_id

        def handler(msg):
            return agent.run(msg, **kwargs)

        return self._lane_queue.submit_sync(session_id, handler, message)

    async def submit(self, session_id: str, message: str, **kwargs) -> str:
        """Async wrapper for submit_sync."""
        return await asyncio.to_thread(self.submit_sync, session_id, message, **kwargs)

    def evict_idle(self):
        """Remove sessions that have been idle longer than idle_timeout."""
        cutoff = time.time() - self.idle_timeout
        with self._lock:
            expired = [sid for sid, entry in self._agents.items() if entry.last_active < cutoff]
            for sid in expired:
                self._lane_queue.remove_session(sid)
                del self._agents[sid]
                logger.info("Evicted idle session %s", sid)

    def _evict_oldest(self):
        """Evict the oldest session to make room.

        Called under self._lock. Safe because LaneQueue.remove_session()
        does not acquire any locks (just dict.pop).
        """
        if not self._agents:
            return
        oldest = min(self._agents, key=lambda s: self._agents[s].last_active)
        self._lane_queue.remove_session(oldest)
        del self._agents[oldest]
        logger.info("Evicted oldest session %s (at capacity)", oldest)

    def active_session_count(self) -> int:
        with self._lock:
            return len(self._agents)
