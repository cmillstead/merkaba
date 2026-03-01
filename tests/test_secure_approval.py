# tests/test_secure_approval.py
"""Tests for SecureApprovalManager: TOTP 2FA and rate limiting."""

import os
import tempfile
import time
from unittest.mock import patch

import pytest

from merkaba.approval.queue import ActionQueue
from merkaba.approval.secure import (
    RateLimitConfig,
    RateLimitExceeded,
    SecureApprovalManager,
    TotpInvalid,
    TotpRequired,
)


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        q = ActionQueue(db_path=db_path)
        yield q
        q.close()


@pytest.fixture
def totp_secret():
    """A fixed TOTP secret for testing."""
    import pyotp
    return pyotp.random_base32()


@pytest.fixture
def valid_code(totp_secret):
    """Generate a currently valid TOTP code."""
    import pyotp
    return pyotp.TOTP(totp_secret).now()


@pytest.fixture
def manager(queue, totp_secret):
    """SecureApprovalManager with 2FA configured."""
    return SecureApprovalManager(
        action_queue=queue,
        totp_secret=totp_secret,
        totp_threshold=3,
        rate_limit=RateLimitConfig(max_approvals=5, window_seconds=60),
    )


@pytest.fixture
def manager_no_totp(queue):
    """SecureApprovalManager without 2FA."""
    return SecureApprovalManager(
        action_queue=queue,
        totp_secret=None,
        totp_threshold=3,
        rate_limit=RateLimitConfig(max_approvals=5, window_seconds=60),
    )


# --- requires_second_factor ---


def test_requires_2fa_when_configured_and_high_level(manager):
    action = {"autonomy_level": 3}
    assert manager.requires_second_factor(action) is True


def test_requires_2fa_when_not_configured(manager_no_totp):
    action = {"autonomy_level": 5}
    assert manager_no_totp.requires_second_factor(action) is False


def test_requires_2fa_low_autonomy_level(manager):
    action = {"autonomy_level": 2}
    assert manager.requires_second_factor(action) is False


def test_requires_2fa_at_threshold(manager):
    action = {"autonomy_level": 3}
    assert manager.requires_second_factor(action) is True


# --- verify_totp ---


def test_verify_totp_valid(manager, valid_code):
    assert manager.verify_totp(valid_code) is True


def test_verify_totp_invalid(manager):
    assert manager.verify_totp("000000") is False


def test_verify_totp_not_configured(manager_no_totp):
    assert manager_no_totp.verify_totp("123456") is False


# --- approve ---


def test_approve_low_risk_no_2fa(manager, queue):
    aid = queue.add_action(business_id=1, action_type="read", description="Low risk", autonomy_level=1)
    result = manager.approve(aid, decided_by="test")
    assert result is not None
    assert result["status"] == "approved"


def test_approve_high_risk_requires_totp(manager, queue):
    aid = queue.add_action(business_id=1, action_type="delete", description="High risk", autonomy_level=4)
    with pytest.raises(TotpRequired) as exc_info:
        manager.approve(aid, decided_by="test")
    assert exc_info.value.action_id == aid


def test_approve_high_risk_invalid_totp(manager, queue):
    aid = queue.add_action(business_id=1, action_type="delete", description="High risk", autonomy_level=4)
    with pytest.raises(TotpInvalid) as exc_info:
        manager.approve(aid, decided_by="test", totp_code="000000")
    assert exc_info.value.action_id == aid


def test_approve_high_risk_valid_totp(manager, queue, valid_code):
    aid = queue.add_action(business_id=1, action_type="delete", description="High risk", autonomy_level=4)
    result = manager.approve(aid, decided_by="test", totp_code=valid_code)
    assert result is not None
    assert result["status"] == "approved"


def test_approve_skip_2fa(manager, queue):
    aid = queue.add_action(business_id=1, action_type="delete", description="High risk", autonomy_level=4)
    result = manager.approve(aid, decided_by="web", skip_2fa=True)
    assert result is not None
    assert result["status"] == "approved"


def test_approve_no_2fa_configured(manager_no_totp, queue):
    """When TOTP not configured, high-risk actions pass without 2FA."""
    aid = queue.add_action(business_id=1, action_type="delete", description="High risk", autonomy_level=5)
    result = manager_no_totp.approve(aid, decided_by="test")
    assert result is not None
    assert result["status"] == "approved"


# --- deny ---


def test_deny_always_works(manager, queue):
    aid = queue.add_action(business_id=1, action_type="delete", description="Deny test", autonomy_level=4)
    result = manager.deny(aid, decided_by="test")
    assert result is not None
    assert result["status"] == "denied"


# --- rate limiting ---


def test_rate_limit_under_limit(queue):
    mgr = SecureApprovalManager(
        action_queue=queue,
        rate_limit=RateLimitConfig(max_approvals=3, window_seconds=60),
    )
    aid = queue.add_action(business_id=1, action_type="test", description="OK", autonomy_level=1)
    result = mgr.approve(aid, decided_by="test")
    assert result["status"] == "approved"


def test_rate_limit_exceeded(queue):
    mgr = SecureApprovalManager(
        action_queue=queue,
        rate_limit=RateLimitConfig(max_approvals=2, window_seconds=60),
    )
    # Approve 2 actions to fill the rate limit
    for i in range(2):
        aid = queue.add_action(business_id=1, action_type="test", description=f"Action {i}", autonomy_level=1)
        mgr.approve(aid, decided_by="test")

    # Third should be blocked
    aid = queue.add_action(business_id=1, action_type="test", description="Blocked", autonomy_level=1)
    with pytest.raises(RateLimitExceeded) as exc_info:
        mgr.approve(aid, decided_by="test")
    assert exc_info.value.max_approvals == 2


def test_deny_not_rate_limited(queue):
    mgr = SecureApprovalManager(
        action_queue=queue,
        rate_limit=RateLimitConfig(max_approvals=1, window_seconds=60),
    )
    # Fill the rate limit
    aid1 = queue.add_action(business_id=1, action_type="test", description="A1", autonomy_level=1)
    mgr.approve(aid1, decided_by="test")

    # Deny should still work
    aid2 = queue.add_action(business_id=1, action_type="test", description="A2", autonomy_level=1)
    result = mgr.deny(aid2, decided_by="test")
    assert result["status"] == "denied"


# --- count_recent_approvals ---


def test_count_recent_approvals_within_window(queue):
    aid1 = queue.add_action(business_id=1, action_type="test", description="A1")
    aid2 = queue.add_action(business_id=1, action_type="test", description="A2")
    queue.decide(aid1, approved=True, decided_by="test")
    queue.decide(aid2, approved=True, decided_by="test")
    assert queue.count_recent_approvals(window_seconds=60) == 2


def test_count_recent_excludes_denials(queue):
    aid1 = queue.add_action(business_id=1, action_type="test", description="A1")
    aid2 = queue.add_action(business_id=1, action_type="test", description="A2")
    queue.decide(aid1, approved=True, decided_by="test")
    queue.decide(aid2, approved=False, decided_by="test")
    assert queue.count_recent_approvals(window_seconds=60) == 1


def test_count_recent_excludes_old_approvals(queue):
    """Approvals outside the window should not be counted."""
    # Use a very short window — approvals from datetime.now() should still be within 60s
    aid = queue.add_action(business_id=1, action_type="test", description="A1")
    queue.decide(aid, approved=True, decided_by="test")
    # With a 0-second window, all approvals are "old"
    assert queue.count_recent_approvals(window_seconds=0) == 0


# --- from_config ---


def test_from_config_no_keychain_no_config(queue):
    with patch("merkaba.security.secrets.get_secret", return_value=None):
        mgr = SecureApprovalManager.from_config(queue)
    assert mgr._totp is None
    assert mgr.totp_threshold == 3
    assert mgr.rate_limit.max_approvals == 5


def test_from_config_with_totp(queue, totp_secret):
    with patch("merkaba.security.secrets.get_secret", return_value=totp_secret):
        mgr = SecureApprovalManager.from_config(queue)
    assert mgr._totp is not None
