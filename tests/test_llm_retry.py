# tests/test_llm_retry.py
import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub ollama before importing merkaba.llm
ollama_stub = MagicMock()


class FakeResponseError(Exception):
    pass


class FakeRequestError(Exception):
    pass


ollama_stub.ResponseError = FakeResponseError
ollama_stub.RequestError = FakeRequestError
sys.modules.setdefault("ollama", ollama_stub)

from merkaba.llm import LLMClient, LLMResponse, RetryConfig, LLMUnavailableError


def test_retry_config_defaults():
    cfg = RetryConfig()
    assert cfg.max_retries == 3
    assert cfg.base_delay == 1.0
    assert cfg.max_delay == 30.0
    assert cfg.exponential_base == 2.0


def test_chat_with_retry_succeeds_first_try():
    client = LLMClient.__new__(LLMClient)
    expected = LLMResponse(content="hello", model="test")
    with patch.object(client, "chat", return_value=expected):
        result = client.chat_with_retry("hi", retry_config=RetryConfig(max_retries=2))
    assert result.content == "hello"


@patch("time.sleep")
def test_chat_with_retry_retries_on_connection_error(mock_sleep):
    client = LLMClient.__new__(LLMClient)
    expected = LLMResponse(content="recovered", model="test")
    with patch.object(
        client,
        "chat",
        side_effect=[ConnectionError("down"), ConnectionError("still down"), expected],
    ):
        result = client.chat_with_retry("hi", retry_config=RetryConfig(max_retries=2, base_delay=0.01))
    assert result.content == "recovered"
    assert mock_sleep.call_count == 2


@patch("time.sleep")
def test_chat_with_retry_raises_after_exhaustion(mock_sleep):
    client = LLMClient.__new__(LLMClient)
    with patch.object(
        client,
        "chat",
        side_effect=ConnectionError("down"),
    ):
        with pytest.raises(LLMUnavailableError, match="unreachable after 3 attempts"):
            client.chat_with_retry("hi", retry_config=RetryConfig(max_retries=2, base_delay=0.01))


def test_chat_with_retry_does_not_retry_request_error():
    client = LLMClient.__new__(LLMClient)
    with patch.object(
        client,
        "chat",
        side_effect=FakeRequestError("bad model"),
    ):
        with pytest.raises(FakeRequestError):
            client.chat_with_retry("hi", retry_config=RetryConfig(max_retries=2))
