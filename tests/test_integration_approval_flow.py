# tests/test_integration_approval_flow.py
"""Integration tests for ActionQueue + GraduationChecker lifecycle."""

import pytest

from merkaba.approval.queue import ActionQueue
from merkaba.approval.graduation import GraduationChecker, DEFAULT_GRADUATION_THRESHOLD


class TestActionLifecycle:
    def test_pending_to_approved(self, action_queue):
        """Create -> approve should update status."""
        aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
        result = action_queue.decide(aid, approved=True, decided_by="admin")
        assert result["status"] == "approved"
        assert result["decided_by"] == "admin"

    def test_pending_to_denied(self, action_queue):
        """Create -> deny should set decided_by."""
        aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
        result = action_queue.decide(aid, approved=False, decided_by="reviewer")
        assert result["status"] == "denied"
        assert result["decided_by"] == "reviewer"

    def test_approved_action_can_be_executed(self, action_queue):
        """approve -> mark_executed should transition to 'executed'."""
        aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
        action_queue.decide(aid, approved=True)
        action_queue.mark_executed(aid, result={"sent": True})
        action = action_queue.get_action(aid)
        assert action["status"] == "executed"
        assert action["result"] == {"sent": True}

    def test_denied_action_cannot_be_re_decided(self, action_queue):
        """deny -> try approve should return None (already decided)."""
        aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
        action_queue.decide(aid, approved=False)
        result = action_queue.decide(aid, approved=True)
        assert result is None
        # Verify still denied
        action = action_queue.get_action(aid)
        assert action["status"] == "denied"


class TestGraduation:
    def test_triggers_after_threshold(self, action_queue):
        """N approvals with 0 denials should trigger graduation suggestion."""
        checker = GraduationChecker(action_queue=action_queue, threshold=3)
        for _ in range(3):
            aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
            action_queue.decide(aid, approved=True)
        suggestion = checker.check(1, "send_email")
        assert suggestion is not None
        assert suggestion["action_type"] == "send_email"
        assert suggestion["approved_count"] >= 3

    def test_blocked_by_single_denial(self, action_queue):
        """Approvals + 1 denial should block graduation."""
        checker = GraduationChecker(action_queue=action_queue, threshold=3)
        for _ in range(5):
            aid = action_queue.add_action(business_id=1, action_type="send_email", description="test")
            action_queue.decide(aid, approved=True)
        # Add one denial
        aid = action_queue.add_action(business_id=1, action_type="send_email", description="bad")
        action_queue.decide(aid, approved=False)
        suggestion = checker.check(1, "send_email")
        assert suggestion is None

    def test_check_all_finds_multiple_types(self, action_queue):
        """Two action types at threshold should both get suggestions."""
        checker = GraduationChecker(action_queue=action_queue, threshold=2)
        for action_type in ("send_email", "update_listing"):
            for _ in range(2):
                aid = action_queue.add_action(business_id=1, action_type=action_type, description="test")
                action_queue.decide(aid, approved=True)
        suggestions = checker.check_all(1)
        assert len(suggestions) == 2
        types = {s["action_type"] for s in suggestions}
        assert types == {"send_email", "update_listing"}

    def test_graduation_suggestion_includes_count(self, action_queue):
        """Suggestion should include approved_count."""
        checker = GraduationChecker(action_queue=action_queue, threshold=2)
        for _ in range(3):
            aid = action_queue.add_action(business_id=1, action_type="deploy", description="test")
            action_queue.decide(aid, approved=True)
        suggestion = checker.check(1, "deploy")
        assert suggestion["approved_count"] == 3
        assert suggestion["denied_count"] == 0


class TestPendingCountAndStats:
    def test_pending_count_scoped_by_business(self, action_queue):
        """Pending count should be isolated per business."""
        for _ in range(3):
            action_queue.add_action(business_id=1, action_type="email", description="biz1")
        for _ in range(2):
            action_queue.add_action(business_id=2, action_type="email", description="biz2")
        assert action_queue.get_pending_count(business_id=1) == 3
        assert action_queue.get_pending_count(business_id=2) == 2
        assert action_queue.get_pending_count() == 5

    def test_stats_reflect_all_decisions(self, action_queue):
        """approve 3, deny 2 should reflect in stats()."""
        for _ in range(3):
            aid = action_queue.add_action(business_id=1, action_type="email", description="test")
            action_queue.decide(aid, approved=True)
        for _ in range(2):
            aid = action_queue.add_action(business_id=1, action_type="email", description="test")
            action_queue.decide(aid, approved=False)
        stats = action_queue.stats()
        assert stats["approved"] == 3
        assert stats["denied"] == 2

    def test_approval_stats_updated_on_decision(self, action_queue):
        """get_stats() should match decision counts."""
        for _ in range(4):
            aid = action_queue.add_action(business_id=1, action_type="deploy", description="test")
            action_queue.decide(aid, approved=True)
        aid = action_queue.add_action(business_id=1, action_type="deploy", description="test")
        action_queue.decide(aid, approved=False)
        stats = action_queue.get_stats(1, "deploy")
        assert len(stats) == 1
        assert stats[0]["approved_count"] == 4
        assert stats[0]["denied_count"] == 1
