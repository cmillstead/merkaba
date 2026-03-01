# src/friday/security/sanitizer.py
"""Sanitize memory values before injection into system prompts."""

import re

INJECTION_PATTERNS = [
    (r"(?i)ignore\s+(all\s+)?previous\s+instructions?", "[redacted]"),
    (r"(?i)you\s+are\s+now\b", "[redacted]"),
    (r"(?i)reveal\s+(your\s+)?system\s+prompt", "[redacted]"),
    (r"(?i)disregard\s+(all\s+)?(above|prior|previous)", "[redacted]"),
    (r"(?i)new\s+instructions?:\s*", "[redacted]"),
    (r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>", "[redacted]"),
    (r"(?i)\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "[redacted]"),
]


def sanitize_memory_value(value: str) -> str:
    """Strip known prompt injection patterns from a memory value."""
    result = value
    for pattern, replacement in INJECTION_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result
