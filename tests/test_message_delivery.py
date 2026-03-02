# tests/test_message_delivery.py
from merkaba.integrations.delivery import chunk_message, CHANNEL_LIMITS


def test_short_message_no_chunking():
    chunks = chunk_message("Hello world", max_chars=2000)
    assert chunks == ["Hello world"]


def test_chunks_at_paragraph_boundary():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_message(text, max_chars=30)
    assert len(chunks) >= 2
    assert all(len(c) <= 30 for c in chunks)


def test_chunks_at_sentence_boundary():
    text = "First sentence. Second sentence. Third sentence."
    chunks = chunk_message(text, max_chars=25)
    assert all(len(c) <= 25 for c in chunks)


def test_code_block_not_split():
    text = "Before.\n\n```python\nprint('hello')\nprint('world')\n```\n\nAfter."
    chunks = chunk_message(text, max_chars=100)
    # Code block should be in one chunk
    code_chunk = [c for c in chunks if "```" in c]
    assert len(code_chunk) == 1


def test_discord_limit():
    assert CHANNEL_LIMITS["discord"] == 2000


def test_telegram_limit():
    assert CHANNEL_LIMITS["telegram"] == 4096
