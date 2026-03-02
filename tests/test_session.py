# tests/test_session.py
from merkaba.orchestration.session import build_session_id


def test_basic_session_id():
    sid = build_session_id("web", "user123")
    assert sid == "web:user123"


def test_session_id_with_topic():
    sid = build_session_id("telegram", "user456", topic_id="789")
    assert sid == "telegram:user456:topic:789"


def test_session_id_with_business():
    sid = build_session_id("web", "user123", business_id="shop1")
    assert sid == "web:user123:biz:shop1"


def test_session_id_full():
    sid = build_session_id("discord", "u1", topic_id="ch5", business_id="biz2")
    assert sid == "discord:u1:topic:ch5:biz:biz2"


def test_session_id_no_empty_segments():
    sid = build_session_id("cli", "local", topic_id=None, business_id=None)
    assert sid == "cli:local"
