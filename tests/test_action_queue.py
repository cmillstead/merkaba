# tests/test_action_queue.py
import tempfile
import os

import pytest

from merkaba.approval.queue import ActionQueue


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        q = ActionQueue(db_path=db_path)
        yield q
        q.close()


# --- add / get ---


def test_add_action(queue):
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send invoice")
    assert aid == 1


def test_add_action_with_params(queue):
    params = {"to": "user@example.com", "subject": "Invoice"}
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send invoice", params=params)
    action = queue.get_action(aid)
    assert action["params"] == params


def test_get_action(queue):
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send invoice", autonomy_level=2)
    action = queue.get_action(aid)
    assert action["id"] == aid
    assert action["business_id"] == 1
    assert action["action_type"] == "send_email"
    assert action["description"] == "Send invoice"
    assert action["autonomy_level"] == 2
    assert action["status"] == "pending"
    assert action["decided_at"] is None
    assert action["decided_by"] is None


def test_get_action_not_found(queue):
    assert queue.get_action(999) is None


# --- list ---


def test_list_actions(queue):
    queue.add_action(business_id=1, action_type="a", description="First")
    queue.add_action(business_id=1, action_type="b", description="Second")
    actions = queue.list_actions()
    assert len(actions) == 2


def test_list_actions_filter_status(queue):
    aid = queue.add_action(business_id=1, action_type="a", description="First")
    queue.add_action(business_id=1, action_type="b", description="Second")
    queue.decide(aid, approved=True)

    pending = queue.list_actions(status="pending")
    assert len(pending) == 1
    assert pending[0]["action_type"] == "b"

    approved = queue.list_actions(status="approved")
    assert len(approved) == 1
    assert approved[0]["action_type"] == "a"


def test_list_actions_filter_business(queue):
    queue.add_action(business_id=1, action_type="a", description="Biz 1")
    queue.add_action(business_id=2, action_type="b", description="Biz 2")
    actions = queue.list_actions(business_id=1)
    assert len(actions) == 1
    assert actions[0]["business_id"] == 1


# --- decide ---


def test_decide_approve(queue):
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send")
    result = queue.decide(aid, approved=True, decided_by="cli")
    assert result["status"] == "approved"
    assert result["decided_by"] == "cli"
    assert result["decided_at"] is not None


def test_decide_deny(queue):
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send")
    result = queue.decide(aid, approved=False, decided_by="telegram")
    assert result["status"] == "denied"
    assert result["decided_by"] == "telegram"


def test_decide_already_decided(queue):
    aid = queue.add_action(business_id=1, action_type="a", description="X")
    queue.decide(aid, approved=True)
    result = queue.decide(aid, approved=False)
    assert result is None


def test_decide_not_found(queue):
    assert queue.decide(999, approved=True) is None


# --- mark_executed / mark_failed ---


def test_mark_executed(queue):
    aid = queue.add_action(business_id=1, action_type="a", description="X")
    queue.decide(aid, approved=True)
    queue.mark_executed(aid, result={"sent": True})
    action = queue.get_action(aid)
    assert action["status"] == "executed"
    assert action["executed_at"] is not None
    assert action["result"] == {"sent": True}


def test_mark_failed(queue):
    aid = queue.add_action(business_id=1, action_type="a", description="X")
    queue.decide(aid, approved=True)
    queue.mark_failed(aid, result={"error": "timeout"})
    action = queue.get_action(aid)
    assert action["status"] == "failed"
    assert action["result"]["error"] == "timeout"


# --- pending count ---


def test_get_pending_count(queue):
    queue.add_action(business_id=1, action_type="a", description="X")
    queue.add_action(business_id=1, action_type="b", description="Y")
    queue.add_action(business_id=2, action_type="c", description="Z")
    assert queue.get_pending_count() == 3
    assert queue.get_pending_count(business_id=1) == 2


# --- stats ---


def test_stats(queue):
    queue.add_action(business_id=1, action_type="a", description="X")
    aid2 = queue.add_action(business_id=1, action_type="b", description="Y")
    queue.decide(aid2, approved=True)
    counts = queue.stats()
    assert counts["total"] == 2
    assert counts["pending"] == 1
    assert counts["approved"] == 1


# --- approval_stats ---


def test_approval_stats_tracking(queue):
    aid1 = queue.add_action(business_id=1, action_type="send_email", description="A")
    aid2 = queue.add_action(business_id=1, action_type="send_email", description="B")
    aid3 = queue.add_action(business_id=1, action_type="send_email", description="C")

    queue.decide(aid1, approved=True)
    queue.decide(aid2, approved=True)
    queue.decide(aid3, approved=False)

    stats = queue.get_stats(business_id=1, action_type="send_email")
    assert len(stats) == 1
    assert stats[0]["approved_count"] == 2
    assert stats[0]["denied_count"] == 1


# --- close ---


def test_close_idempotent(queue):
    queue.close()
    queue.close()  # should not crash


# --- Context manager ---


def test_context_manager_returns_self():
    """ActionQueue as context manager returns self."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        with ActionQueue(db_path=db_path) as q:
            assert isinstance(q, ActionQueue)
            assert q._conn is not None


def test_context_manager_closes_connection():
    """ActionQueue connection is closed after exiting the with block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        with ActionQueue(db_path=db_path) as q:
            q.add_action(business_id=1, action_type="a", description="X")
        assert q._conn is None


def test_context_manager_closes_on_exception():
    """ActionQueue connection is closed even when an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        with pytest.raises(RuntimeError, match="boom"):
            with ActionQueue(db_path=db_path) as q:
                q.add_action(business_id=1, action_type="a", description="X")
                raise RuntimeError("boom")
        assert q._conn is None
