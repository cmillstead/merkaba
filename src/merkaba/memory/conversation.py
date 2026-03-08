# src/merkaba/memory/conversation.py
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from merkaba.paths import subdir as _subdir

try:
    from merkaba.security.file_permissions import ensure_secure_permissions as _secure
except ImportError:  # pragma: no cover
    _secure = None


@dataclass
class ConversationLog:
    """Persistent conversation logging."""

    storage_dir: str = field(default_factory=lambda: _subdir("conversations"))
    session_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    encryptor: Any = field(default=None)
    _history: list[dict[str, Any]] = field(default_factory=list, init=False)
    _tree_data: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        os.makedirs(self.storage_dir, exist_ok=True)
        if _secure:
            _secure(self.storage_dir)
        self._load()

    @property
    def _filepath(self) -> str:
        return os.path.join(self.storage_dir, f"{self.session_id}.json")

    def _load(self):
        """Load existing conversation if present, decrypting if needed."""
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r") as f:
                    raw = f.read()
                if raw.startswith("MERKABA_ENC:"):
                    if not self.encryptor:
                        self._history = []
                        return
                    raw = self.encryptor.decrypt(raw)
                data = json.loads(raw)
                self._history = data.get("messages", [])
                tree_data = data.get("tree")
                self._tree_data = tree_data if isinstance(tree_data, dict) else None
            except (json.JSONDecodeError, OSError, ValueError, Exception):
                self._history = []
                self._tree_data = None

    def append(self, role: str, content: str, metadata: dict | None = None):
        """Append a message to the conversation."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        if metadata:
            entry["metadata"] = metadata
        self._history.append(entry)

    def get_history(self, limit: int | None = None) -> list[dict]:
        """Get conversation history, optionally limited."""
        if limit is not None:
            if limit == 0:
                return []
            return self._history[-limit:]
        return self._history.copy()

    def save(self, tree: "ConversationTree | None" = None):
        """Persist conversation to disk, encrypting if encryptor is available."""
        data = {
            "session_id": self.session_id,
            "messages": self._history,
            "saved_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        if tree is not None:
            data["tree"] = tree.to_serializable()
            self._tree_data = data["tree"]
        content = json.dumps(data, indent=2)
        if self.encryptor:
            content = self.encryptor.encrypt(content)
        with open(self._filepath, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if _secure:
            _secure(self._filepath)

    def bind_session(self, session_id: str):
        """Rebind this log to a different session and load any persisted history."""
        if self.session_id == session_id:
            return
        self.session_id = session_id
        self._history = []
        self._tree_data = None
        self._load()

    def get_tree(self) -> "ConversationTree | None":
        """Return the persisted conversation tree if present."""
        if self._tree_data is None:
            return None
        try:
            return ConversationTree.from_serializable(self._tree_data)
        except (KeyError, TypeError, ValueError):
            return None

    def clear(self):
        """Clear conversation history."""
        self._history = []
        self._tree_data = None


@dataclass
class Message:
    """A single message node in a conversation tree."""

    id: str
    parent_id: str | None
    role: str  # user | assistant | tool | system
    content: str | None
    timestamp: str
    metadata: dict
    pruned: bool = False


@dataclass
class ConversationTree:
    """Tree-structured conversation history supporting branching and pruning."""

    session_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    messages: dict[str, Message] = field(default_factory=dict)
    current_leaf_id: str | None = None

    def append(self, role: str, content: str | None, metadata: dict | None = None) -> Message:
        """Create a new message as a child of the current leaf."""
        msg_id = str(uuid.uuid4())
        msg = Message(
            id=msg_id,
            parent_id=self.current_leaf_id,
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            metadata=metadata or {},
        )
        self.messages[msg_id] = msg
        self.current_leaf_id = msg_id
        return msg

    def get_active_branch(self) -> list[Message]:
        """Walk from current leaf to root, return the linear path (skipping pruned)."""
        if self.current_leaf_id is None:
            return []
        branch: list[Message] = []
        msg_id: str | None = self.current_leaf_id
        while msg_id is not None:
            msg = self.messages[msg_id]
            if not msg.pruned:
                branch.append(msg)
            msg_id = msg.parent_id
        branch.reverse()
        return branch

    def branch_from(self, message_id: str) -> str:
        """Set current leaf to an earlier message, creating a branch point."""
        if message_id not in self.messages:
            raise KeyError(f"Message {message_id} not found")
        self.current_leaf_id = message_id
        return message_id

    def prune_branch(self, from_message_id: str) -> None:
        """Soft-delete all descendants of a message."""
        for desc_id in self._get_descendants(from_message_id):
            self.messages[desc_id].pruned = True

    def inject_summary(self, after_message_id: str, summary: str) -> Message:
        """Insert a system summary after a branch point."""
        self.current_leaf_id = after_message_id
        return self.append("system", summary, metadata={"type": "branch_summary"})

    def _get_descendants(self, message_id: str) -> list[str]:
        """BFS to find all children (direct and indirect) of a message."""
        descendants: list[str] = []
        queue: list[str] = []
        # Seed with direct children
        for mid, msg in self.messages.items():
            if msg.parent_id == message_id:
                queue.append(mid)
        while queue:
            current = queue.pop(0)
            descendants.append(current)
            for mid, msg in self.messages.items():
                if msg.parent_id == current:
                    queue.append(mid)
        return descendants

    def to_serializable(self) -> dict:
        """Convert tree to a JSON-friendly dict."""
        return {
            "session_id": self.session_id,
            "current_leaf_id": self.current_leaf_id,
            "messages": {
                mid: {
                    "id": msg.id,
                    "parent_id": msg.parent_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata,
                    "pruned": msg.pruned,
                }
                for mid, msg in self.messages.items()
            },
        }

    @classmethod
    def from_serializable(cls, data: dict) -> "ConversationTree":
        """Reconstruct a ConversationTree from a serialized dict."""
        tree = cls(session_id=data["session_id"])
        tree.current_leaf_id = data.get("current_leaf_id")
        for mid, mdata in data.get("messages", {}).items():
            tree.messages[mid] = Message(
                id=mdata["id"],
                parent_id=mdata["parent_id"],
                role=mdata["role"],
                content=mdata["content"],
                timestamp=mdata["timestamp"],
                metadata=mdata.get("metadata", {}),
                pruned=mdata.get("pruned", False),
            )
        return tree
