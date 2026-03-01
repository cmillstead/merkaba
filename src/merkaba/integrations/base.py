from dataclasses import dataclass, field


@dataclass
class IntegrationAdapter:
    """Base class for external service adapters."""

    name: str
    business_id: int | None = None
    _connected: bool = field(default=False, init=False, repr=False)

    def connect(self) -> bool:
        raise NotImplementedError

    def execute(self, action: str, params: dict | None = None) -> dict:
        raise NotImplementedError

    def disconnect(self) -> None:
        pass

    def health_check(self) -> dict:
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        return self._connected


ADAPTER_REGISTRY: dict[str, type[IntegrationAdapter]] = {}


def register_adapter(name: str, adapter_class: type[IntegrationAdapter]) -> None:
    ADAPTER_REGISTRY[name] = adapter_class


def get_adapter_class(name: str) -> type[IntegrationAdapter] | None:
    return ADAPTER_REGISTRY.get(name)


def list_adapters() -> list[str]:
    return list(ADAPTER_REGISTRY.keys())
