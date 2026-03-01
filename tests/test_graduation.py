# tests/test_graduation.py
import tempfile
import os

import pytest

from merkaba.approval.queue import ActionQueue
from merkaba.approval.graduation import GraduationChecker


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        q = ActionQueue(db_path=db_path)
        yield q
        q.close()


@pytest.fixture
def checker(queue):
    return GraduationChecker(action_queue=queue, threshold=3)


def _approve_n(queue, n, business_id=1, action_type="send_email"):
    for i in range(n):
        aid = queue.add_action(business_id=business_id, action_type=action_type, description=f"Action {i}")
        queue.decide(aid, approved=True)


def _deny_one(queue, business_id=1, action_type="send_email"):
    aid = queue.add_action(business_id=business_id, action_type=action_type, description="Denied")
    queue.decide(aid, approved=False)


def test_no_suggestion_below_threshold(checker, queue):
    _approve_n(queue, 2)
    result = checker.check(business_id=1, action_type="send_email")
    assert result is None


def test_suggestion_at_threshold(checker, queue):
    _approve_n(queue, 3)
    result = checker.check(business_id=1, action_type="send_email")
    assert result is not None
    assert result["approved_count"] == 3
    assert "Promote" in result["suggestion"]


def test_no_suggestion_with_denials(checker, queue):
    _approve_n(queue, 5)
    _deny_one(queue)
    result = checker.check(business_id=1, action_type="send_email")
    assert result is None


def test_check_all_returns_multiple(checker, queue):
    _approve_n(queue, 3, action_type="send_email")
    _approve_n(queue, 3, action_type="post_content")
    suggestions = checker.check_all(business_id=1)
    assert len(suggestions) == 2
    types = {s["action_type"] for s in suggestions}
    assert types == {"send_email", "post_content"}


def test_check_all_empty(checker, queue):
    suggestions = checker.check_all(business_id=1)
    assert suggestions == []


def test_custom_threshold(queue):
    checker = GraduationChecker(action_queue=queue, threshold=5)
    _approve_n(queue, 4)
    assert checker.check(business_id=1, action_type="send_email") is None
    _approve_n(queue, 1)
    assert checker.check(business_id=1, action_type="send_email") is not None
