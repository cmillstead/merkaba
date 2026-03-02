# tests/test_pairing.py
"""Tests for gateway pairing authentication."""

import time

from merkaba.security.pairing import GatewayPairing


def test_initiate_returns_code():
    gp = GatewayPairing()
    code = gp.initiate("telegram", "user123")
    assert len(code) == 6
    assert code.isalnum()


def test_confirm_valid_code():
    gp = GatewayPairing()
    code = gp.initiate("telegram", "user123")
    assert gp.confirm("user123", code)
    assert gp.is_paired("user123")


def test_confirm_wrong_code():
    gp = GatewayPairing()
    gp.initiate("telegram", "user123")
    assert not gp.confirm("user123", "WRONG1")


def test_confirm_expired_code():
    gp = GatewayPairing(expiry_seconds=0.01)
    code = gp.initiate("telegram", "user123")
    time.sleep(0.02)
    assert not gp.confirm("user123", code)


def test_cross_channel_trust():
    gp = GatewayPairing()
    gp.initiate("telegram", "tg:user1")
    code = gp._sessions["tg:user1"].code
    assert gp.confirm("tg:user1", code)
    assert gp.is_paired("tg:user1")


def test_unpaired_identity():
    gp = GatewayPairing()
    assert not gp.is_paired("unknown")
