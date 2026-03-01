# src/merkaba/integrations/credentials.py
"""Credential manager for integration adapters.

Builds on security/secrets.py. Keys namespaced as integration:{adapter}:{key}.
"""

from merkaba.security.secrets import store_secret, get_secret, delete_secret


class CredentialManager:
    PREFIX = "integration"

    def _key(self, adapter_name: str, key: str) -> str:
        return f"{self.PREFIX}:{adapter_name}:{key}"

    def store(self, adapter_name: str, key: str, value: str) -> None:
        store_secret(self._key(adapter_name, key), value)

    def get(self, adapter_name: str, key: str) -> str | None:
        return get_secret(self._key(adapter_name, key))

    def delete(self, adapter_name: str, key: str) -> None:
        delete_secret(self._key(adapter_name, key))

    def has_required(self, adapter_name: str, required_keys: list[str]) -> tuple[bool, list[str]]:
        missing = [k for k in required_keys if self.get(adapter_name, k) is None]
        return (len(missing) == 0, missing)
