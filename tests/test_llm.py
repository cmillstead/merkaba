import pytest
from unittest.mock import patch, Mock
from merkaba.llm import LLMClient, LLMResponse


def test_llm_client_initialization():
    client = LLMClient(model="qwen2.5:32b")
    assert client.model == "qwen2.5:32b"
    assert client.base_url == "http://localhost:11434"


def test_llm_response_model():
    response = LLMResponse(
        content="Hello!",
        model="qwen2.5:32b",
        tool_calls=None,
    )
    assert response.content == "Hello!"
    assert response.tool_calls is None


@pytest.mark.integration
@pytest.mark.skip(reason="Integration test - requires Ollama running with qwen2.5:32b model")
def test_llm_client_chat():
    """Integration test - requires Ollama running."""
    client = LLMClient(model="qwen2.5:32b")
    response = client.chat("Say 'test' and nothing else.")
    assert response.content is not None
    assert len(response.content) > 0


def test_chat_constructs_messages_correctly():
    """Test that chat correctly constructs messages for Ollama."""
    with patch('ollama.Client') as mock_client_class:
        mock_instance = mock_client_class.return_value

        # Mock the response
        mock_response = Mock()
        mock_response.message.content = "Hello!"
        mock_response.message.tool_calls = None
        mock_response.model = "test-model"
        mock_response.prompt_eval_count = 10
        mock_response.eval_count = 5
        mock_response.total_duration = 1_000_000
        mock_instance.chat.return_value = mock_response

        client = LLMClient(model="test-model")
        response = client.chat("Hi", system_prompt="Be helpful")

        # Verify Ollama was called correctly
        call_args = mock_instance.chat.call_args
        messages = call_args.kwargs['messages']

        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "Hi"}


def test_chat_parses_tool_calls():
    """Test that tool calls from Ollama are correctly parsed."""
    with patch('ollama.Client') as mock_client_class:
        mock_instance = mock_client_class.return_value

        # Mock a response with tool calls
        mock_tool_call = Mock()
        mock_tool_call.function.name = "file_read"
        mock_tool_call.function.arguments = {"path": "/tmp/test.txt"}

        mock_response = Mock()
        mock_response.message.content = None
        mock_response.message.tool_calls = [mock_tool_call]
        mock_response.model = "test-model"
        mock_response.prompt_eval_count = 10
        mock_response.eval_count = 5
        mock_response.total_duration = 1_000_000
        mock_instance.chat.return_value = mock_response

        client = LLMClient(model="test-model")
        response = client.chat("Read the file")

        assert response.content is None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "file_read"
        assert response.tool_calls[0].arguments == {"path": "/tmp/test.txt"}


def test_chat_without_system_prompt():
    """Test chat works without a system prompt."""
    with patch('ollama.Client') as mock_client_class:
        mock_instance = mock_client_class.return_value

        mock_response = Mock()
        mock_response.message.content = "Response"
        mock_response.message.tool_calls = None
        mock_response.model = "test-model"
        mock_response.prompt_eval_count = 10
        mock_response.eval_count = 5
        mock_response.total_duration = 1_000_000
        mock_instance.chat.return_value = mock_response

        client = LLMClient(model="test-model")
        client.chat("Hello")

        call_args = mock_instance.chat.call_args
        messages = call_args.kwargs['messages']

        # Should only have user message, no system
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
