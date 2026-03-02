# tests/test_context_budget.py
from merkaba.memory.context_budget import ContextBudget, ContextWindowConfig, estimate_tokens


def test_estimate_tokens_english():
    text = "Hello world, this is a test."
    tokens = estimate_tokens(text)
    # ~4 chars per token, 27 chars -> ~7 tokens
    assert 5 <= tokens <= 10


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_single_char():
    # Even a single character should produce at least 1 token
    assert estimate_tokens("a") == 1


def test_estimate_tokens_whitespace_only():
    # Whitespace-only strings still have characters
    tokens = estimate_tokens("   ")
    assert tokens >= 1


def test_estimate_tokens_long_text():
    # 4000 chars -> ~1000 tokens
    text = "word " * 800  # 4000 chars
    tokens = estimate_tokens(text)
    assert 900 <= tokens <= 1100


def test_budget_available_for_history():
    budget = ContextBudget(max_total_tokens=8000)
    budget.system_prompt_tokens = 1000
    budget.tool_definitions_tokens = 500
    # reserved_for_response defaults to 4096
    assert budget.available_for_history == 2404


def test_budget_available_for_history_overcommitted():
    # When fixed allocations exceed max, available should be 0 not negative
    budget = ContextBudget(max_total_tokens=2000)
    budget.system_prompt_tokens = 1000
    budget.tool_definitions_tokens = 1000
    budget.reserved_for_response = 4096
    assert budget.available_for_history == 0


def test_budget_utilization():
    budget = ContextBudget(max_total_tokens=10000)
    budget.system_prompt_tokens = 2000
    budget.tool_definitions_tokens = 1000
    budget.conversation_history_tokens = 5000
    assert budget.utilization == 0.8


def test_budget_utilization_zero_max():
    budget = ContextBudget(max_total_tokens=0)
    assert budget.utilization == 0.0


def test_budget_utilization_empty():
    budget = ContextBudget(max_total_tokens=10000)
    assert budget.utilization == 0.0


def test_budget_defaults():
    budget = ContextBudget(max_total_tokens=128000)
    assert budget.system_prompt_tokens == 0
    assert budget.tool_definitions_tokens == 0
    assert budget.conversation_history_tokens == 0
    assert budget.reserved_for_response == 4096


def test_context_window_config_defaults():
    config = ContextWindowConfig()
    assert config.max_context_tokens == 128000
    assert config.head_chars == 1500
    assert config.tail_chars == 1500
    assert config.compaction_threshold == 0.80


def test_context_window_config_custom():
    config = ContextWindowConfig(
        max_context_tokens=32000,
        head_chars=500,
        tail_chars=500,
        compaction_threshold=0.70,
    )
    assert config.max_context_tokens == 32000
    assert config.head_chars == 500
    assert config.tail_chars == 500
    assert config.compaction_threshold == 0.70
