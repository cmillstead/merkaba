# tests/test_security.py
import pytest

# Check if required dependencies are available
try:
    from merkaba.security import PermissionManager, PermissionDenied
    from merkaba.tools.base import PermissionTier
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    PermissionManager = None
    PermissionDenied = None
    PermissionTier = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


# --- Audit Log Tests ---


def test_audit_log_records_attempts_and_decisions():
    """Test that entries are logged for attempts and decisions."""
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)
    manager.check("file_read", PermissionTier.SAFE)

    log = manager.get_audit_log()
    assert len(log) == 2

    # First entry should be attempt
    assert log[0]["type"] == "attempt"
    assert log[0]["tool"] == "file_read"
    assert log[0]["tier"] == "SAFE"

    # Second entry should be decision
    assert log[1]["type"] == "decision"
    assert log[1]["tool"] == "file_read"
    assert log[1]["result"] == "auto_approved"


def test_audit_log_entry_structure():
    """Test correct structure of log entries (timestamp, tool, tier, type, result)."""
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)
    manager.check("test_tool", PermissionTier.SAFE)

    log = manager.get_audit_log()

    # Check attempt entry structure
    attempt_entry = log[0]
    assert "timestamp" in attempt_entry
    assert "tool" in attempt_entry
    assert "tier" in attempt_entry
    assert "type" in attempt_entry
    assert attempt_entry["type"] == "attempt"

    # Check decision entry structure
    decision_entry = log[1]
    assert "timestamp" in decision_entry
    assert "tool" in decision_entry
    assert "tier" in decision_entry
    assert "type" in decision_entry
    assert "result" in decision_entry
    assert decision_entry["type"] == "decision"


def test_get_audit_log_returns_copy():
    """Test that get_audit_log() returns a copy (not mutable reference)."""
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)
    manager.check("file_read", PermissionTier.SAFE)

    log1 = manager.get_audit_log()
    log2 = manager.get_audit_log()

    # Should be different objects
    assert log1 is not log2

    # Modifying the returned list should not affect the internal log
    original_length = len(log1)
    log1.append({"fake": "entry"})
    log3 = manager.get_audit_log()
    assert len(log3) == original_length


# --- Callback Rejection Test ---


def test_callback_rejection_raises_permission_denied():
    """Test when callback returns False - should raise PermissionDenied."""
    def rejecting_callback(tool_name, tier):
        return False

    manager = PermissionManager(
        auto_approve_level=PermissionTier.SAFE,
        approval_callback=rejecting_callback,
    )

    with pytest.raises(PermissionDenied):
        manager.check("shell", PermissionTier.SENSITIVE, require_approval=True)


# --- require_approval=False Test ---


def test_require_approval_false_returns_false_without_raising():
    """Test that when require_approval=False and tier exceeds auto_approve_level and no callback, returns False."""
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)

    # This should return False, not raise PermissionDenied
    result = manager.check("shell", PermissionTier.SENSITIVE, require_approval=False)
    assert result is False


# --- Original Tests ---


def test_permission_manager_auto_approves_safe():
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)
    assert manager.check("file_read", PermissionTier.SAFE) is True


def test_permission_manager_blocks_above_level():
    manager = PermissionManager(auto_approve_level=PermissionTier.SAFE)

    with pytest.raises(PermissionDenied):
        manager.check("file_write", PermissionTier.MODERATE, require_approval=True)


def test_permission_manager_with_callback():
    approvals = []

    def approval_callback(tool_name, tier):
        approvals.append((tool_name, tier))
        return True

    manager = PermissionManager(
        auto_approve_level=PermissionTier.SAFE,
        approval_callback=approval_callback,
    )

    result = manager.check("shell", PermissionTier.SENSITIVE)
    assert result is True
    assert ("shell", PermissionTier.SENSITIVE) in approvals
