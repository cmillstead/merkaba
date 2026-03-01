# src/merkaba/agent.py
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
from merkaba.llm import LLMClient, LLMUnavailableError, AllModelsUnavailableError, RequestPriority
from merkaba.memory import ConversationLog, ConversationTree
from merkaba.tools.registry import ToolRegistry
from merkaba.tools.builtin import (
    file_read, file_write, file_list,
    etsy_search, analyze_results, save_research,
    grep, glob,
    web_fetch,
    bash,
    memory_search, set_memory_retrieval, set_active_business,
)
from merkaba.memory.store import MemoryStore
from merkaba.memory.retrieval import MemoryRetrieval
from merkaba.security import PermissionManager, PermissionDenied, validate_tool_arguments, ValidationError
from merkaba.security.scanner import SecurityScanner, SecurityReport
from merkaba.security.classifier import InputClassifier
from merkaba.plugins import PluginRegistry, Skill, PluginSandbox, PluginPermissionError
from merkaba.verification.deterministic import DeterministicVerifier
from merkaba.config.prompts import PromptLoader
from merkaba.security.sanitizer import sanitize_memory_value


SIMPLE_MODEL = "qwen3:8b"


@dataclass
class Agent:
    """The core agent that orchestrates LLM and tools."""

    model: str = "qwen3.5:122b"
    simple_model: str = SIMPLE_MODEL
    max_iterations: int = 10
    memory_storage_dir: str | None = None
    plugins_enabled: bool = True
    extra_context: str | None = None
    active_business_id: int | None = None
    prompt_dir: str | None = None
    llm: LLMClient = field(init=False)
    registry: ToolRegistry = field(init=False)
    memory: ConversationLog = field(init=False)
    _tree: ConversationTree = field(init=False)
    permission_manager: PermissionManager = field(init=False)
    input_classifier: InputClassifier = field(init=False)
    retrieval: MemoryRetrieval | None = field(init=False, default=None)
    plugin_registry: PluginRegistry | None = field(init=False, default=None)
    active_skill: Skill | None = field(init=False, default=None)
    _prompt_loader: PromptLoader = field(init=False)
    _verifier: DeterministicVerifier = field(init=False)

    def __post_init__(self):
        self.llm = LLMClient(model=self.model)
        self.registry = ToolRegistry()
        self._prompt_loader = PromptLoader(base_dir=self.prompt_dir)
        self._tree = ConversationTree()
        if self.memory_storage_dir:
            self.memory = ConversationLog(storage_dir=self.memory_storage_dir)
        else:
            self.memory = ConversationLog()
        self.permission_manager = PermissionManager()
        self.input_classifier = InputClassifier()
        self._verifier = DeterministicVerifier()
        self._init_memory_retrieval()
        self._register_builtin_tools()
        if self.plugins_enabled:
            self.plugin_registry = PluginRegistry.default()

        # Run security quick scan
        self._run_security_check()

    @property
    def conversation(self) -> list[dict]:
        """Backward-compatible view of the active branch as list[dict]."""
        result = []
        for msg in self._tree.get_active_branch():
            entry: dict = {"role": msg.role, "content": msg.content}
            if msg.metadata.get("tool_calls"):
                entry["tool_calls"] = msg.metadata["tool_calls"]
            result.append(entry)
        return result

    def _init_memory_retrieval(self):
        """Initialize structured memory retrieval (MemoryStore + optional vectors)."""
        try:
            store = MemoryStore()
            vectors = None
            try:
                from merkaba.memory.vectors import VectorMemory
                vectors = VectorMemory()
            except Exception:
                pass
            self.retrieval = MemoryRetrieval(store=store, vectors=vectors)
            set_memory_retrieval(self.retrieval)
            logger.info("Memory retrieval initialized (db=%s, vectors=%s)",
                        store.db_path, vectors is not None)
        except Exception as e:
            logger.warning("Memory retrieval init failed: %s", e)
            self.retrieval = None

    def _register_builtin_tools(self):
        """Register all built-in tools."""
        # Memory tools (registered first — agent should check memory before other tools)
        if self.retrieval:
            self.registry.register(memory_search)
        # File tools
        self.registry.register(file_read)
        self.registry.register(file_write)
        self.registry.register(file_list)
        # Search tools
        self.registry.register(grep)
        self.registry.register(glob)
        # Web tools
        self.registry.register(web_fetch)
        # Shell tools
        self.registry.register(bash)
        # Research tools
        self.registry.register(etsy_search)
        self.registry.register(analyze_results)
        self.registry.register(save_research)

    def _run_security_check(self):
        """Run security quick scan and display alert if issues found."""
        try:
            scanner = SecurityScanner()
            report = scanner.quick_scan()
            if report.has_issues:
                self._print_security_banner(report)
        except Exception:
            # Don't block startup on scan errors
            pass

    def _print_security_banner(self, report: SecurityReport):
        """Print prominent security alert banner."""
        issue_count = (
            len(report.integrity_issues) +
            len(report.cve_issues) +
            len(report.code_warnings)
        )

        print("+" + "=" * 60 + "+")
        print(f"|  WARNING: SECURITY ALERT - {issue_count} issue(s) need attention")
        print("|")

        for issue in report.integrity_issues[:3]:
            print(f"|  * {issue}")
        for cve in report.cve_issues[:3]:
            print(f"|  * {cve.cve_id} in {cve.package}")

        if issue_count > 6:
            print(f"|  * ... and {issue_count - 6} more")

        print("|")
        print("|  Run `/security-scan` for details")
        print("+" + "=" * 60 + "+")

    def activate_skill(self, skill_name: str) -> bool:
        """Activate a skill by name."""
        if not self.plugin_registry:
            return False
        skill = self.plugin_registry.skills.get(skill_name)
        if skill:
            self.active_skill = skill
            return True
        return False

    def deactivate_skill(self):
        """Deactivate the current skill."""
        self.active_skill = None

    def _build_system_prompt(self, user_message: str | None = None) -> str:
        """Build system prompt with memory context and active skill if any."""
        soul, user = self._prompt_loader.load(business_id=self.active_business_id)
        prompt = f"{soul}\n\n{user}"

        # Keep extra_context for backward compat (workers, etc.)
        if self.extra_context:
            prompt = f"{prompt}\n\n{self.extra_context}"

        if self.active_skill:
            prompt = f"{self.active_skill.content}\n\n---\n\n{prompt}"

        # Add global skill context
        if self.plugin_registry and self.plugin_registry.skill_context:
            prompt = f"{prompt}\n\n---\n\n{self.plugin_registry.skill_context}"

        # Auto-inject relevant memory context for the current message
        if user_message and self.retrieval:
            memory_context = self._recall_context(user_message)
            if memory_context:
                prompt = f"{prompt}\n\n---\n[MEMORY]\n{memory_context}\n[/MEMORY]\nIMPORTANT: Present these facts when the user asks about these topics. Do NOT say you have no information if facts are listed above."

        return prompt

    def _recall_context(self, query: str) -> str | None:
        """Recall relevant memories for auto-injection into system prompt."""
        if not self.retrieval:
            return None
        try:
            results = self.retrieval.recall(query, business_id=self.active_business_id)
            logger.debug(
                "recall returned %d results, vectors=%s",
                len(results) if results else 0,
                self.retrieval.vectors is not None,
            )
            if not results:
                logger.debug("No memory results for: %s", query[:80])
                return None
            lines = []
            for r in results:
                if r["type"] == "fact":
                    val = sanitize_memory_value(r.get("value", ""))
                    lines.append(f"- [Fact] {r.get('category', '')}: {r.get('key', '')} = {val}")
                elif r["type"] == "decision":
                    dec = sanitize_memory_value(r.get("decision", ""))
                    reas = sanitize_memory_value(r.get("reasoning", ""))
                    lines.append(f"- [Decision] {dec} — {reas}")
                elif r["type"] == "learning":
                    ins = sanitize_memory_value(r.get("insight", ""))
                    lines.append(f"- [Learning] {ins}")
            logger.debug("Auto-injecting %d memories for: %s", len(lines), query[:80])
            return "\n".join(lines) if lines else None
        except Exception as e:
            logger.debug("Memory recall failed: %s", e)
            return None

    def _extract_session_memories(self):
        """Extract and store facts from the current conversation."""
        if not self.retrieval or len(self.conversation) < 4:
            return
        try:
            from merkaba.memory.lifecycle import SessionExtractor
            extractor = SessionExtractor(
                llm=self.llm,
                store=self.retrieval.store,
                model=self.simple_model,
            )
            bid = self.active_business_id or 0
            extractor.extract(self.conversation, business_id=bid)
        except Exception as e:
            logger.debug("Session extraction failed: %s", e)

    def run(self, user_message: str, on_tool_call=None) -> str:
        """Process a user message and return a response.

        Args:
            user_message: The user's input message.
            on_tool_call: Optional callback fired after each tool execution.
                Called with (tool_name, arguments, result_text).
        """
        # Set trace ID for this run
        try:
            from merkaba.observability.tracing import new_trace_id
            new_trace_id("agent")
        except Exception:
            pass

        # Sync active business into memory tool
        set_active_business(self.active_business_id)

        # Pre-flight classification: safety + complexity routing
        is_safe, reason, complexity = self.input_classifier.classify(user_message)
        logger.debug("Classifier: safe=%s, complexity=%s", is_safe, complexity)

        # Record routing decision
        try:
            from merkaba.observability.audit import record_decision
            record_decision(
                decision_type="classifier_routing",
                decision=f"safe={is_safe}, complexity={complexity}",
                alternatives=["simple", "complex"],
                context_summary=user_message[:200],
                model=self.simple_model if complexity == "simple" else self.model,
            )
        except Exception:
            pass
        if not is_safe:
            refusal = "I can't process that request — it was flagged as a potential prompt injection attempt."
            self.memory.append("user", user_message)
            self.memory.append("assistant", refusal, {"blocked": True, "reason": reason})
            self.memory.save()
            return refusal

        self._tree.append("user", user_message)
        self.memory.append("user", user_message)

        # Simple queries skip tools (lighter models may not support them)
        # "no_tools" = classifier was unavailable, allow response but without tools
        use_tools = complexity not in ("simple", "no_tools")

        # Track repeated verification failures for branching
        failure_count: dict[str, int] = {}
        first_failure_parent: dict[str, str] = {}

        for _ in range(self.max_iterations):
            pre_iteration_leaf = self._tree.current_leaf_id

            tier = "simple" if complexity == "simple" else "complex"  # no_tools uses complex model
            try:
                response = self.llm.chat_with_fallback(
                    message=self._format_conversation(),
                    system_prompt=self._build_system_prompt(user_message),
                    tools=self.registry.to_ollama_format() if use_tools else None,
                    tier=tier,
                    priority=RequestPriority.INTERACTIVE,
                )
            except (LLMUnavailableError, AllModelsUnavailableError) as e:
                logger.error("LLM unavailable: %s", e)
                return "I'm unable to reach the language model right now. Please check that Ollama is running and try again."

            logger.debug("Model=%s, tool_calls=%s, use_tools=%s", response.model, bool(response.tool_calls), use_tools)
            if response.tool_calls:
                logger.debug("Tool calls: %s", [tc.name for tc in response.tool_calls])
                tool_results = self._execute_tools(response.tool_calls, on_tool_call=on_tool_call)
                self._tree.append(
                    "assistant", None,
                    {"tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ]},
                )
                self._tree.append("tool", tool_results)
                self.memory.append(
                    "tool",
                    tool_results,
                    {"tool_calls": [tc.name for tc in response.tool_calls]}
                )

                # Branch on repeated verification failures for the same file
                if "\u26a0 VERIFICATION FAILED" in tool_results:
                    for tc in response.tool_calls:
                        if tc.name == "file_write":
                            fpath = tc.arguments.get("path", "")
                            if not fpath:
                                continue
                            failure_count[fpath] = failure_count.get(fpath, 0) + 1
                            if failure_count[fpath] == 1:
                                first_failure_parent[fpath] = pre_iteration_leaf
                            elif failure_count[fpath] >= 2:
                                branch_point = first_failure_parent[fpath]
                                self._tree.branch_from(branch_point)
                                self._tree.inject_summary(
                                    branch_point,
                                    f"Previous attempts to write {fpath} failed verification. "
                                    f"Try a different approach. Errors: {tool_results}",
                                )
                                del failure_count[fpath]
                                del first_failure_parent[fpath]
                                logger.debug("Branched conversation after repeated failure on %s", fpath)
            else:
                # Final response
                self._tree.append("assistant", response.content)
                self.memory.append("assistant", response.content)
                self.memory.save()
                self._extract_session_memories()
                return response.content

        self.memory.save()
        self._extract_session_memories()
        return "I've reached my iteration limit. Please try a simpler request."

    def _format_conversation(self) -> str:
        """Format conversation history for the LLM."""
        parts = []
        for msg in self._tree.get_active_branch():
            if msg.role == "user":
                parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                if msg.content:
                    parts.append(f"Assistant: {msg.content}")
                elif msg.metadata.get("tool_calls"):
                    tool_names = [tc["name"] for tc in msg.metadata["tool_calls"]]
                    parts.append(f"Assistant: [Called tools: {', '.join(tool_names)}]")
            elif msg.role == "tool":
                parts.append(f"Tool Result: {msg.content}")
            elif msg.role == "system":
                parts.append(f"System: {msg.content}")
        return "\n\n".join(parts)

    def _execute_tools(self, tool_calls: list, on_tool_call=None) -> str:
        """Execute a list of tool calls and return results."""
        results = []
        for tc in tool_calls:
            tool = self.registry.get(tc.name)
            if tool:
                try:
                    # Validate arguments before executing
                    is_valid, error_msg = validate_tool_arguments(
                        tc.name,
                        tool.parameters,
                        tc.arguments,
                    )
                    if not is_valid:
                        result_text = f"[{tc.name}] Validation error: {error_msg}"
                        results.append(result_text)
                        if on_tool_call:
                            on_tool_call(tc.name, tc.arguments, result_text)
                        continue

                    # Plugin sandbox check (if active skill has manifest)
                    if self.active_skill and self.active_skill.manifest:
                        sandbox = PluginSandbox(manifest=self.active_skill.manifest)
                        sandbox.check_tool_access(tc.name)
                        sandbox.check_path_access(tc.name, tc.arguments)

                    # Check permission before executing
                    self.permission_manager.check(tc.name, tool.permission_tier)
                    result = tool.execute(**tc.arguments)
                    if result.success:
                        result_text = f"[{tc.name}] Success:\n{result.output}"
                        if tc.name == "file_write" and self._verifier.enabled:
                            try:
                                verification = self._verifier.verify(tc.arguments.get("path", ""))
                                if verification and not verification.passed:
                                    result_text += f"\n\n⚠ VERIFICATION FAILED:\n{verification.summary}"
                            except Exception as ve:
                                logger.warning("Verification error for %s: %s", tc.arguments.get("path", ""), ve)
                    else:
                        result_text = f"[{tc.name}] Error:\n{result.error}"
                    results.append(result_text)
                    if on_tool_call:
                        on_tool_call(tc.name, tc.arguments, result_text)
                except (PermissionDenied, PluginPermissionError) as e:
                    result_text = f"[{tc.name}] Permission denied: {e}"
                    results.append(result_text)
                    if on_tool_call:
                        on_tool_call(tc.name, tc.arguments, result_text)
            else:
                result_text = f"[{tc.name}] Error: Tool not found"
                results.append(result_text)
                if on_tool_call:
                    on_tool_call(tc.name, tc.arguments, result_text)
        return "\n\n".join(results)
