# src/merkaba/security/sanitizer.py
"""Sanitize memory values before injection into system prompts."""

import re
import unicodedata

INJECTION_PATTERNS = [
    (r"(?i)ignore\s+(all\s+)?previous\s+instructions?", "[redacted]"),
    (r"(?i)you\s+are\s+now\b", "[redacted]"),
    (r"(?i)reveal\s+(your\s+)?system\s+prompt", "[redacted]"),
    (r"(?i)disregard\s+(all\s+)?(above|prior|previous)", "[redacted]"),
    (r"(?i)new\s+instructions?:\s*", "[redacted]"),
    (r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>", "[redacted]"),
    (r"(?i)\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "[redacted]"),
]

BLOCK_ESCAPE_PATTERNS = [
    re.compile(r"\[/(?:MEMORY|SYSTEM|USER|CONTEXT|INST)\]", re.IGNORECASE),
    re.compile(r"\[(?:MEMORY|SYSTEM|USER|CONTEXT|INST)\]", re.IGNORECASE),
]


def sanitize_skill_content(content: str) -> str:
    """Sanitize skill content before injection into system prompt."""
    # Normalize Unicode to catch homoglyph attacks
    result = unicodedata.normalize("NFKD", content)
    # Apply standard injection patterns
    for pattern, replacement in INJECTION_PATTERNS:
        result = re.sub(pattern, replacement, result)
    # Block tag escapes
    for pattern in BLOCK_ESCAPE_PATTERNS:
        result = pattern.sub("[redacted-tag]", result)
    return result


def sanitize_memory_value(value: str) -> str:
    """Sanitize a memory value before it enters the system prompt."""
    result = unicodedata.normalize("NFKD", value)
    for pattern, replacement in INJECTION_PATTERNS:
        result = re.sub(pattern, replacement, result)
    for pattern in BLOCK_ESCAPE_PATTERNS:
        result = pattern.sub("[redacted-tag]", result)
    return result
