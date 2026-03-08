"""Default configuration values for Merkaba.

Centralises model name strings so they are defined in exactly one place.
Import ``DEFAULT_MODELS`` wherever a model default is needed instead of
hard-coding the string.
"""

DEFAULT_MODELS: dict[str, str] = {
    "complex": "qwen3.5:122b",
    "simple": "qwen3:8b",
    "classifier": "qwen3:4b",
    "embedding": "nomic-embed-text",
    "health_check": "phi4:14b",
}

# Convenience aliases used by the fallback-chain builder in llm.py.
FALLBACK_CHAINS: dict[str, dict] = {
    "complex": {
        "primary": DEFAULT_MODELS["complex"],
        "fallbacks": [DEFAULT_MODELS["simple"]],
        "timeout": 120.0,
    },
    "simple": {
        "primary": DEFAULT_MODELS["simple"],
        "fallbacks": [DEFAULT_MODELS["classifier"]],
        "timeout": 30.0,
    },
    "classifier": {
        "primary": DEFAULT_MODELS["classifier"],
        "fallbacks": [],
        "timeout": 10.0,
    },
}
