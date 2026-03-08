import heapq
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)

from merkaba.paths import config_path as _config_path

CONFIG_PATH = _config_path()


# --- Rate Limiting & Resource Management ---


class RequestPriority(IntEnum):
    """Priority levels for LLM requests. Lower value = higher priority."""

    INTERACTIVE = 0
    APPROVAL = 1
    SCHEDULED = 2
    BACKGROUND = 3


@dataclass
class GateConfig:
    """Configuration for the LLM concurrency gate."""

    max_concurrent: int = 2
    queue_depth_warning: int = 5


class LLMGate:
    """Priority-aware concurrency gate for LLM requests.

    Uses a heapq-based priority queue so interactive requests are served
    before scheduled/background work, preventing GPU thrashing on single-GPU
    machines.
    """

    def __init__(self, config: GateConfig | None = None):
        self.config = config or GateConfig()
        self.enabled = True
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(self.config.max_concurrent)
        self._queue: list[tuple[int, int, threading.Event]] = []  # (priority, counter, event)
        self._counter = 0
        self._active = 0

    def acquire(self, priority: RequestPriority = RequestPriority.SCHEDULED) -> None:
        """Acquire a slot, blocking until one is available. Higher-priority requests are served first."""
        if not self.enabled:
            return

        event = threading.Event()
        with self._lock:
            self._counter += 1
            heapq.heappush(self._queue, (int(priority), self._counter, event))
            queue_depth = len(self._queue)

        if queue_depth > self.config.queue_depth_warning:
            logger.warning("LLM gate queue depth %d exceeds warning threshold %d",
                           queue_depth, self.config.queue_depth_warning)

        # Try to dispatch from the queue
        self._try_dispatch()

        # Wait for our turn
        event.wait()

    def release(self) -> None:
        """Release a slot, allowing the next queued request to proceed."""
        if not self.enabled:
            return

        with self._lock:
            self._active -= 1

        self._try_dispatch()

    def _try_dispatch(self) -> None:
        """Dispatch the highest-priority waiting request if a slot is available."""
        with self._lock:
            while self._queue and self._active < self.config.max_concurrent:
                _, _, event = heapq.heappop(self._queue)
                self._active += 1
                event.set()

    def reset(self) -> None:
        """Reset gate state. For use in tests."""
        with self._lock:
            self._queue.clear()
            self._counter = 0
            self._active = 0
            self._semaphore = threading.Semaphore(self.config.max_concurrent)

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active


def _load_gate_config() -> GateConfig:
    """Load gate config from ~/.merkaba/config.json if available."""
    from merkaba.config.loader import load_config

    data = load_config()
    rl = data.get("rate_limiting", {})
    if rl:
        return GateConfig(
            max_concurrent=rl.get("max_concurrent", 2),
            queue_depth_warning=rl.get("queue_depth_warning", 5),
        )
    return GateConfig()


_llm_gate: LLMGate | None = None
_gate_lock = threading.Lock()


def get_llm_gate() -> LLMGate:
    """Get the module-level LLM gate singleton."""
    global _llm_gate
    if _llm_gate is None:
        with _gate_lock:
            if _llm_gate is None:
                _llm_gate = LLMGate(config=_load_gate_config())
    return _llm_gate

@dataclass
class ToolCall:
    """Represents a tool call requested by the LLM."""

    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from the LLM."""

    content: str | None
    model: str
    tool_calls: list[ToolCall] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


class LLMUnavailableError(Exception):
    """Raised when LLM is unreachable after all retry attempts."""


class AllModelsUnavailableError(Exception):
    """Raised when all models in a fallback chain are unavailable."""


@dataclass
class ModelTier:
    """A model with ordered fallbacks."""

    primary: str
    fallbacks: list[str] = field(default_factory=list)
    timeout: float = 120.0


from merkaba.config.defaults import DEFAULT_MODELS, FALLBACK_CHAINS

MODEL_CHAINS: dict[str, ModelTier] = {
    tier: ModelTier(primary=cfg["primary"], fallbacks=cfg["fallbacks"], timeout=cfg["timeout"])
    for tier, cfg in FALLBACK_CHAINS.items()
}


def load_fallback_chains(config_path: str = CONFIG_PATH) -> dict[str, ModelTier]:
    """Load MODEL_CHAINS with optional overrides from config.json.

    Config format: {"models": {"fallback_chains": {"complex": {"primary": "...", "fallbacks": [...]}}}}
    """
    from merkaba.config.loader import load_config

    chains = {k: ModelTier(primary=v.primary, fallbacks=list(v.fallbacks), timeout=v.timeout)
              for k, v in MODEL_CHAINS.items()}
    data = load_config(path=config_path, use_cache=False)
    model_overrides = data.get("models", {})
    for tier_name in ("complex", "simple", "classifier"):
        primary = model_overrides.get(tier_name)
        if primary and tier_name in chains:
            chains[tier_name].primary = primary
    overrides = data.get("models", {}).get("fallback_chains", {})
    for tier_name, tier_data in overrides.items():
        if isinstance(tier_data, dict):
            primary = tier_data.get("primary")
            if primary:
                fallbacks = tier_data.get("fallbacks", [])
                timeout = tier_data.get("timeout", 120.0)
                chains[tier_name] = ModelTier(primary=primary, fallbacks=fallbacks, timeout=timeout)
    return chains


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


@dataclass
class LLMClient:
    """Client for interacting with Ollama LLM."""

    model: str = None
    base_url: str = "http://localhost:11434"
    _client: Any = field(default=None, init=False, repr=False)
    last_fallback: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.model is None:
            self.model = DEFAULT_MODELS["complex"]
        import ollama
        self._client = ollama.Client(host=self.base_url)

    def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
        model_override: str | None = None,
    ) -> LLMResponse:
        """Send a message and get a response.

        Args:
            model_override: Use a different model for this call only.

        Routes cloud-prefixed models (e.g. "anthropic:claude-sonnet-4-20250514")
        through the appropriate provider adapter. Unprefixed models use Ollama.
        """
        effective_model = model_override or self.model
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": message})

        # Check if this is a cloud model
        from merkaba.llm_providers.registry import is_cloud_model, resolve_provider
        if is_cloud_model(effective_model):
            provider, actual_model = resolve_provider(effective_model)
            if provider is None:
                raise LLMUnavailableError(
                    f"Provider unavailable for model '{effective_model}' "
                    "(missing SDK or API key)"
                )
            resp = provider.chat(actual_model, messages, tools)
            tool_calls = None
            if resp.tool_calls:
                tool_calls = [
                    ToolCall(name=tc["name"], arguments=tc["arguments"])
                    for tc in resp.tool_calls
                ]
            return LLMResponse(
                content=resp.content,
                model=resp.model,
                tool_calls=tool_calls,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                duration_ms=resp.duration_ms,
            )

        # Default: Ollama
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        response = self._client.chat(**kwargs)

        tool_calls = None
        if getattr(response.message, "tool_calls", None):
            tool_calls = [
                ToolCall(
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in response.message.tool_calls
            ]

        return LLMResponse(
            content=response.message.content,
            model=response.model,
            tool_calls=tool_calls,
            input_tokens=getattr(response, "prompt_eval_count", 0) or 0,
            output_tokens=getattr(response, "eval_count", 0) or 0,
            duration_ms=int((getattr(response, "total_duration", 0) or 0) / 1_000_000),
        )

    def chat_with_retry(
        self,
        message: str,
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
        model_override: str | None = None,
        retry_config: RetryConfig | None = None,
        priority: RequestPriority = RequestPriority.SCHEDULED,
    ) -> LLMResponse:
        """Send a message with automatic retry on transient failures.

        Retries on ConnectionError and server errors (ollama.ResponseError).
        Does NOT retry on ollama.RequestError (bad model name, etc.).

        The gate is held for the full retry cycle so the slot is reserved
        during backoff (prevents another request from thrashing the GPU).
        """
        import ollama as ollama_lib

        gate = get_llm_gate()
        gate.acquire(priority)
        try:
            config = retry_config or RetryConfig()
            last_error: Exception | None = None

            # Build list of retryable error types
            retryable = [ConnectionError, ollama_lib.ResponseError]
            try:
                import anthropic as anthropic_lib
                retryable.append(anthropic_lib.APIConnectionError)
                retryable.append(anthropic_lib.RateLimitError)
                retryable.append(anthropic_lib.APIStatusError)
            except ImportError:
                pass
            try:
                import openai as openai_lib
                retryable.append(openai_lib.APIConnectionError)
                retryable.append(openai_lib.RateLimitError)
                retryable.append(openai_lib.APIStatusError)
            except ImportError:
                pass
            retryable_errors = tuple(retryable)

            for attempt in range(config.max_retries + 1):
                try:
                    result = self.chat(
                        message=message,
                        system_prompt=system_prompt,
                        tools=tools,
                        model_override=model_override,
                    )
                    try:
                        if result.input_tokens or result.output_tokens:
                            from merkaba.observability.tokens import get_token_store
                            from merkaba.observability.tracing import get_trace_id
                            store = get_token_store()
                            if store:
                                store.record(
                                    model=result.model,
                                    input_tokens=result.input_tokens,
                                    output_tokens=result.output_tokens,
                                    duration_ms=result.duration_ms,
                                    trace_id=get_trace_id(),
                                )
                    except Exception:
                        pass
                    return result
                except ollama_lib.RequestError:
                    raise  # bad model name, etc. — will never succeed
                except LLMUnavailableError:
                    raise  # cloud provider missing SDK/key — will never succeed on retry
                except retryable_errors as e:
                    last_error = e
                    if attempt < config.max_retries:
                        delay = min(
                            config.base_delay * config.exponential_base ** attempt,
                            config.max_delay,
                        )
                        logger.warning(
                            "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                            attempt + 1, config.max_retries + 1, e, delay,
                        )
                        time.sleep(delay)

            raise LLMUnavailableError(
                f"LLM unreachable after {config.max_retries + 1} attempts: {last_error}"
            )
        finally:
            gate.release()

    def get_available_models(self) -> set[str]:
        """Query Ollama for currently available model names. Returns empty set on failure."""
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            return {m["name"] for m in data.get("models", [])}
        except Exception as e:
            logger.debug("Failed to query available models: %s", e)
            return set()

    def get_all_available_models(self) -> set[str]:
        """Query Ollama + configured cloud providers for available model names."""
        models = self.get_available_models()
        from merkaba.llm_providers.registry import get_configured_providers
        for provider_name, available in get_configured_providers().items():
            if available:
                models.add(f"{provider_name}:*")
        return models

    def select_best_available(self, tier: str) -> str:
        """Pick the best model from a tier that's actually loaded.

        Cloud-prefixed models (e.g. "anthropic:claude-sonnet-4-20250514") are checked
        via their provider's is_available() instead of the Ollama model list.

        Raises AllModelsUnavailableError if no model in the chain is available.
        Raises KeyError if tier is unknown.
        """
        from merkaba.llm_providers.registry import is_cloud_model, resolve_provider

        chains = load_fallback_chains()
        if tier not in chains:
            raise KeyError(f"Unknown model tier: {tier}")
        chain = chains[tier]
        available = self.get_available_models()
        if not available:
            # Can't determine Ollama availability — optimistically return primary
            # (unless primary is a cloud model we can check)
            if is_cloud_model(chain.primary):
                provider, _ = resolve_provider(chain.primary)
                if provider is not None:
                    return chain.primary
            else:
                return chain.primary
        for model in [chain.primary] + chain.fallbacks:
            if is_cloud_model(model):
                provider, _ = resolve_provider(model)
                if provider is not None:
                    return model
            elif model in available:
                return model
        raise AllModelsUnavailableError(
            f"No models available for tier '{tier}'. "
            f"Tried: {[chain.primary] + chain.fallbacks}"
        )

    def chat_with_fallback(
        self,
        message: str,
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
        tier: str = "complex",
        retry_config: RetryConfig | None = None,
        priority: RequestPriority = RequestPriority.SCHEDULED,
    ) -> LLMResponse:
        """Send a message with model fallback chain.

        Tries primary model first via chat_with_retry(). On LLMUnavailableError
        or RequestError (model not found), tries each fallback in order.
        Raises AllModelsUnavailableError if all models fail.
        """
        try:
            import ollama as ollama_lib
            request_error = ollama_lib.RequestError
            if not (isinstance(request_error, type) and issubclass(request_error, BaseException)):
                request_error = LLMUnavailableError  # fallback when ollama is mocked
        except Exception:
            request_error = LLMUnavailableError

        chains = load_fallback_chains()
        if tier not in chains:
            raise KeyError(f"Unknown model tier: {tier}")
        chain = chains[tier]
        models_to_try = [chain.primary] + chain.fallbacks
        last_error: Exception | None = None

        for i, model in enumerate(models_to_try):
            try:
                result = self.chat_with_retry(
                    message=message,
                    system_prompt=system_prompt,
                    tools=tools,
                    model_override=model,
                    retry_config=retry_config,
                    priority=priority,
                )
                if i > 0:
                    self.last_fallback = model
                return result
            except (LLMUnavailableError, request_error) as e:
                last_error = e
                if i < len(models_to_try) - 1:
                    next_model = models_to_try[i + 1]
                    logger.warning(
                        "Model '%s' unavailable (%s), falling back to '%s'",
                        model, e, next_model,
                    )
                    try:
                        from merkaba.observability.audit import record_decision
                        record_decision(
                            decision_type="model_fallback",
                            decision=f"{model} -> {next_model}",
                            alternatives=models_to_try,
                            context_summary=f"tier={tier}, error={e}",
                            model=next_model,
                        )
                    except Exception:
                        pass

        raise AllModelsUnavailableError(
            f"All models unavailable for tier '{tier}': {models_to_try}. Last error: {last_error}"
        )
