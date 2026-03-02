"""Platform-aware message chunking and delivery.

Splits long messages at natural boundaries (paragraphs, sentences, words)
while preserving code blocks. Each channel has a character limit.
"""

import re

CHANNEL_LIMITS = {
    "discord": 2000,
    "telegram": 4096,
    "slack": 4000,
    "signal": 4096,
    "web": 100000,  # Effectively unlimited
    "cli": 100000,
}


def chunk_message(text: str, max_chars: int = 2000) -> list[str]:
    """Split a message into chunks that fit within max_chars.

    Split priority:
    1. Paragraph boundaries (double newline)
    2. Line boundaries (single newline)
    3. Sentence boundaries (period + space)
    4. Word boundaries (space)
    5. Hard split (at max_chars)

    Code blocks (```...```) are kept together if they fit in one chunk.
    """
    if len(text) <= max_chars:
        return [text]

    # First, identify code blocks and protect them
    # Split into segments: normal text and code blocks
    segments = _split_preserving_code_blocks(text)

    chunks: list[str] = []
    current = ""

    for segment in segments:
        if segment.startswith("```") and len(segment) <= max_chars:
            # Code block that fits — treat as atomic
            if len(current) + len(segment) + 2 <= max_chars:
                current = current + "\n\n" + segment if current else segment
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = segment
        else:
            # Normal text — split at natural boundaries
            for piece in _split_text(segment, max_chars):
                if len(current) + len(piece) + 2 <= max_chars:
                    current = current + "\n\n" + piece if current else piece
                else:
                    if current.strip():
                        chunks.append(current.strip())
                    current = piece

    if current.strip():
        chunks.append(current.strip())

    # Final pass: ensure no chunk exceeds limit
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            result.append(chunk)
        else:
            result.extend(_hard_split(chunk, max_chars))

    return result


def _split_preserving_code_blocks(text: str) -> list[str]:
    """Split text into alternating normal/code-block segments."""
    parts = re.split(r"(```[\s\S]*?```)", text)
    return [p for p in parts if p.strip()]


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text at natural boundaries."""
    if len(text) <= max_chars:
        return [text]

    # Try paragraph split first
    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        return paragraphs

    # Try line split
    lines = text.split("\n")
    if len(lines) > 1:
        return lines

    # Try sentence split
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 1:
        return sentences

    # Try word split
    words = text.split(" ")
    if len(words) > 1:
        return words

    return [text]


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last resort: split at exact max_chars boundary."""
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
