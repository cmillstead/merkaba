from dataclasses import dataclass

import pytest

from merkaba.integrations.base import (
    IntegrationAdapter,
    ADAPTER_REGISTRY,
    register_adapter,
    get_adapter_class,
    list_adapters,
)


def test_base_connect_raises():
    adapter = IntegrationAdapter(name="test")
    with pytest.raises(NotImplementedError):
        adapter.connect()


def test_base_execute_raises():
    adapter = IntegrationAdapter(name="test")
    with pytest.raises(NotImplementedError):
        adapter.execute("action")


def test_base_health_check_raises():
    adapter = IntegrationAdapter(name="test")
    with pytest.raises(NotImplementedError):
        adapter.health_check()


def test_base_disconnect_does_nothing():
    adapter = IntegrationAdapter(name="test")
    adapter.disconnect()


def test_is_connected_default_false():
    adapter = IntegrationAdapter(name="test")
    assert adapter.is_connected is False


def test_business_id_default_none():
    adapter = IntegrationAdapter(name="test")
    assert adapter.business_id is None


def test_business_id_set():
    adapter = IntegrationAdapter(name="test", business_id=42)
    assert adapter.business_id == 42


def test_register_and_get_adapter():
    @dataclass
    class DummyAdapter(IntegrationAdapter):
        def connect(self):
            self._connected = True
            return True
        def execute(self, action, params=None):
            return {"ok": True}
        def health_check(self):
            return {"ok": True}

    register_adapter("_test_dummy", DummyAdapter)
    assert get_adapter_class("_test_dummy") is DummyAdapter
    del ADAPTER_REGISTRY["_test_dummy"]


def test_get_adapter_class_missing():
    assert get_adapter_class("nonexistent_adapter_xyz") is None


def test_list_adapters_returns_names():
    @dataclass
    class A(IntegrationAdapter):
        def connect(self): return True
        def execute(self, action, params=None): return {}
        def health_check(self): return {"ok": True}

    register_adapter("_test_a", A)
    names = list_adapters()
    assert "_test_a" in names
    del ADAPTER_REGISTRY["_test_a"]
