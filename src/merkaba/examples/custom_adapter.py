"""Example: how to create a custom integration adapter for Merkaba.

Adapters connect to external services. Create an adapter by subclassing
IntegrationAdapter and registering it.

Usage in your private package:
    # my_package/adapters/my_service.py
    from merkaba.integrations.base import IntegrationAdapter, register_adapter

    class MyServiceAdapter(IntegrationAdapter):
        def connect(self):
            ...

    register_adapter("my_service", MyServiceAdapter)
"""

from merkaba.integrations.base import IntegrationAdapter, register_adapter


class CustomAdapter(IntegrationAdapter):
    """A minimal custom adapter example.

    Adapters provide a uniform interface for external services.
    The framework manages connection lifecycle and health checks.
    """

    def connect(self) -> bool:
        # Connect to your service here
        # Return True on success, False on failure
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        if not self.is_connected:
            return {"error": "Not connected"}
        return {"status": "ok", "action": action, "params": params}

    def health_check(self) -> dict:
        return {"healthy": self.is_connected, "service": self.name}

    def disconnect(self) -> None:
        self._connected = False


# Register so the framework knows about this adapter
register_adapter("custom_service", CustomAdapter)
