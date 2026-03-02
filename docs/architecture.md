# Merkaba Architecture

## Overview

Merkaba is a local-first AI agent framework for building autonomous agents with persistent memory, tool use, and multi-model routing. It supports multiple LLM providers (Ollama, OpenAI, Anthropic) and runs on any platform with Python 3.11+. The system is built around graduated autonomy — agents start by asking for approval on actions, and earn the right to act more independently over time.

## Module Map

```
src/merkaba/
├── agent.py             # Core agent loop with memory injection and model routing
├── llm.py               # LLM client with retry, fallback, and rate limiting
├── cli.py               # Typer CLI — all heavy imports are lazy
│
├── llm_providers/
│   ├── base.py           # LLMProvider base class
│   ├── ollama_provider.py # Ollama (local inference)
│   ├── anthropic_provider.py # Anthropic Claude API
│   ├── openai_provider.py # OpenAI API
│   └── registry.py       # Provider registry — auto-detects from model name
│
├── memory/
│   ├── store.py          # MemoryStore — SQLite (businesses, facts, decisions, learnings)
│   ├── retrieval.py      # MemoryRetrieval — unified query (vector + keyword fallback)
│   ├── vectors.py        # VectorMemory — ChromaDB embeddings (optional)
│   ├── conversation.py   # ConversationLog — session-scoped JSON persistence
│   ├── lifecycle.py      # Memory decay, archival, consolidation
│   ├── contradiction.py  # Contradiction detection between facts
│   ├── context_budget.py # Token estimation, ContextBudget, ContextWindowConfig
│   └── compression.py    # Graceful in-place context compression for ConversationTree
│
├── security/
│   ├── classifier.py     # InputClassifier — pre-flight safety + complexity routing
│   ├── validation.py     # Tool argument scanning, homoglyph normalization
│   ├── permissions.py    # PermissionManager — 4-tier approval (SAFE/MODERATE/SENSITIVE/DESTRUCTIVE)
│   ├── scanner.py        # SecurityScanner — integrity checks, CVE audit
│   ├── integrity.py      # SHA256 file hash baselines
│   ├── encryption.py     # Fernet conversation encryption
│   ├── sanitizer.py      # Memory sanitization
│   ├── audit.py          # pip-audit wrapper for CVE detection
│   ├── secrets.py        # OS keychain wrapper via keyring
│   └── pairing.py        # GatewayPairing — one-time 6-char code for channel auth
│
├── orchestration/
│   ├── supervisor.py     # Task dispatch to workers, configurable model routing
│   ├── workers.py        # Worker base class + WorkerResult + WORKER_REGISTRY
│   ├── code_worker.py    # Code generation and review worker
│   ├── explorer.py       # Codebase exploration worker
│   ├── scheduler.py      # Tick-based cron executor + heartbeat checklist
│   ├── queue.py          # TaskQueue — SQLite task + run tracking
│   ├── session.py        # Session ID builder (channel:sender[:topic][:biz])
│   ├── session_pool.py   # SessionPool — per-session Agent lifecycle + LRU eviction
│   ├── lane_queue.py     # LaneQueue — per-session serial execution, cross-session concurrency
│   ├── interruption.py   # InterruptionManager — APPEND/STEER/CANCEL modes
│   ├── heartbeat.py      # Lightweight health triage
│   ├── heartbeat_checklist.py # HEARTBEAT.md parser for user-editable checklists
│   ├── health.py         # System health checks
│   ├── backup.py         # Database backup and restore
│   └── learnings.py      # Rule-based + LLM-based insight extraction
│
├── approval/
│   ├── queue.py          # ActionQueue — pending/approved/denied actions + stats
│   ├── graduation.py     # GraduationChecker — promote action types after N approvals
│   ├── secure.py         # SecureApprovalManager — TOTP 2FA + rate limiting
│   └── telegram.py       # Inline button UI for Telegram approval
│
├── integrations/
│   ├── base.py           # IntegrationAdapter base class + ADAPTER_REGISTRY
│   ├── credentials.py    # CredentialManager — namespaced keychain access
│   ├── email_adapter.py  # SMTP send, IMAP read, LLM parse
│   ├── stripe_adapter.py # Stripe payments adapter
│   ├── github_adapter.py # GitHub API adapter
│   ├── slack_adapter.py  # Slack API + Bolt real-time + Block Kit approvals
│   ├── calendar_adapter.py # Apple Calendar adapter (macOS)
│   ├── discord_adapter.py  # Discord via discord.py — send, read, list channels
│   ├── signal_adapter.py   # Signal via signal-cli JSON-RPC subprocess
│   └── delivery.py         # Platform-aware message chunking (paragraph > sentence > word)
│
├── tools/
│   ├── base.py           # Tool dataclass, ToolResult, PermissionTier enum
│   ├── registry.py       # ToolRegistry — name→Tool dict
│   └── builtin/
│       ├── files.py       # file_read, file_write, file_list (with path restrictions)
│       ├── search.py      # grep, glob
│       ├── web.py         # web_fetch (with SSRF protection)
│       ├── shell.py       # bash (command allowlist)
│       ├── memory_tools.py # memory_search tool
│       └── browser.py     # browser_open/snapshot/click/fill/navigate/close (Playwright)
│
├── config/
│   ├── prompts.py        # PromptLoader — SOUL.md / USER.md per-business prompt files
│   ├── hot_reload.py     # HotConfig — mtime-based config reload with security warnings
│   └── validation.py     # validate_config() — startup configuration warnings
│
├── verification/
│   └── deterministic.py  # Deterministic verification loops
│
├── observability/
│   ├── audit.py          # Audit trail logging
│   ├── tokens.py         # Token usage tracking
│   └── tracing.py        # Logging setup and tracing
│
├── web/
│   ├── app.py            # FastAPI factory with lifespan, auth, CORS
│   ├── routes/
│   │   ├── system.py      # /api/system/status, /api/system/models
│   │   ├── businesses.py  # /api/businesses CRUD + config
│   │   ├── memory.py      # /api/memory/search, /facts, /decisions, /learnings
│   │   ├── tasks.py       # /api/tasks CRUD + runs
│   │   ├── approvals.py   # /api/approvals + approve/deny endpoints
│   │   ├── analytics.py   # /api/analytics/overview — cross-business aggregation
│   │   └── chat.py        # /ws/chat WebSocket, /api/chat/sessions, /api/upload
│   └── static/            # Built React SPA (Vite + TypeScript)
│
├── telegram/
│   ├── bot.py            # TelegramBot — python-telegram-bot Application wrapper
│   ├── commands.py       # Command handlers
│   └── config.py         # Bot token + allowed user IDs
│
├── plugins/
│   ├── registry.py       # PluginRegistry (skills, commands, hooks, agents)
│   ├── skills.py         # Skill loading from markdown + frontmatter
│   ├── commands.py       # Command loading
│   ├── hooks.py          # Hook event system
│   ├── agents.py         # Agent config loading
│   ├── analyzer.py       # Skill compatibility analysis
│   ├── converter.py      # Skill format conversion
│   ├── sandbox.py        # Plugin sandboxing
│   ├── uninstaller.py    # Plugin removal
│   ├── importer.py       # Plugin import pipeline
│   └── importer_openclaw.py # OpenClaw workspace migrator
│
├── identity/
│   └── aieos.py          # AIEOS v1.1 identity import/export
│
├── protocols.py          # Formal Protocol definitions (MemoryBackend, VectorBackend, Observer, ConversationBackend)
│
└── examples/
    ├── custom_worker.py  # How to create a custom worker
    └── custom_adapter.py # How to create a custom adapter
```

## Extension Points

Merkaba is designed to be extended by private packages. The two main extension points are:

**Workers** — Subclass `Worker`, implement `execute()`, call `register_worker("task_type", MyWorker)`. The supervisor automatically routes matching tasks.

**Adapters** — Subclass `IntegrationAdapter`, implement `connect()`/`execute()`/`health_check()`, call `register_adapter("name", MyAdapter)`.

See `src/merkaba/examples/` for working examples.

## Data Flow

### Chat Request (CLI or Web)

```
User input
  → InputClassifier (safety + complexity routing)
      → UNSAFE: return refusal
      → SIMPLE: route to small model, skip tools
      → COMPLEX: route to large model, enable tools
  → _recall_context(): keyword/vector search → inject facts into system prompt
  → LLMClient.chat() via configured provider
      → if tool_calls: validate args → check permissions → execute tool → loop
      → if text response: save to ConversationLog, return
```

### Scheduled Task

```
Scheduler tick (cron or launchd)
  → merkaba scheduler run
  → Scheduler.tick()
  → TaskQueue.get_due_tasks()
  → Supervisor.handle_task(task)
      → resolve Worker class from WORKER_REGISTRY
      → select model per task type (configurable)
      → Worker.execute(task)
      → store facts/decisions in MemoryStore
      → route needs_approval items to ActionQueue
      → LearningExtractor.process()
```

### Approval Flow

```
Worker produces needs_approval items
  → ActionQueue.add_action()
  → Telegram: inline Approve/Deny buttons
     OR Web: /api/approvals endpoints
  → ActionQueue.decide()
  → GraduationChecker: N approvals + 0 denials → suggest promotion
```

## LLM Provider Support

Merkaba supports multiple LLM providers through its provider registry:

| Provider | Local | Cloud | Tool Use |
|----------|-------|-------|----------|
| Ollama | Yes | No | Yes |
| OpenAI | No | Yes | Yes |
| Anthropic | No | Yes | Yes |

The provider is auto-detected from the model name (e.g., `gpt-4o` → OpenAI, `claude-sonnet-4-20250514` → Anthropic, anything else → Ollama). Model routing is configurable per task type via `~/.merkaba/config.json`.

## Storage

All data lives in `~/.merkaba/`:

| File | Contents |
|------|----------|
| `config.json` | API keys, model overrides, web API key, security settings |
| `memory.db` | Businesses, facts, decisions, relationships, state, learnings |
| `tasks.db` | Task definitions, schedules, run history |
| `actions.db` | Approval queue, approval stats |
| `conversations/` | JSON session logs (one per chat session) |
| `memory_vectors/` | ChromaDB collections (optional) |
| `uploads/` | Web chat file uploads |
| `logs/` | Scheduler stdout/stderr |
| `plugins/` | Locally imported plugins |
| `SOUL.md` | Global system prompt personality |
| `USER.md` | Global user context |
| `businesses/{id}/` | Per-business SOUL.md, USER.md, config |

## Security Layers

1. **Input Classifier** — LLM pre-flight blocks prompt injection and routes complexity
2. **Argument Validation** — regex scanning for injection patterns + homoglyph normalization
3. **Permission Tiers** — SAFE/MODERATE/SENSITIVE/DESTRUCTIVE with configurable auto-approve level
4. **Path Restrictions** — file tools block sensitive paths (`.ssh`, `.env`, credentials)
5. **SSRF Protection** — web_fetch blocks localhost, metadata endpoints, RFC-1918 ranges
6. **Shell Allowlist** — bash tool only allows specific commands
7. **Approval Workflows** — actions above threshold require human approval
8. **Tool Graduation** — tools earn trust over time (N approvals, 0 denials)
9. **Integrity Monitoring** — SHA256 baselines for core security files
10. **CVE Scanning** — pip-audit integration for dependency vulnerabilities
11. **Plugin Sandboxing** — isolated execution for untrusted plugins
12. **Conversation Encryption** — optional Fernet encryption for stored conversations
13. **TOTP 2FA** — optional two-factor authentication for sensitive approvals

## Session Management

### SessionPool + LaneQueue

Multi-channel sessions (Telegram, Discord, Slack, Signal, Web) route through `SessionPool` and `LaneQueue`:

```
Inbound message (any channel)
  → build_session_id(channel, sender, topic, business)
  → SessionPool.submit(session_id, message)
      → GatewayPairing check (non-CLI channels)
      → get_or_create Agent (LRU eviction at max_sessions)
      → LaneQueue.submit(session_id, handler, payload)
          → per-session threading.Lock serialization
          → asyncio.to_thread() boundary (async → sync agent.run())
          → Agent.run(message)
              → check interruptions at tool boundaries
              → auto-compress context at ~80% utilization
          → response returned through async boundary
```

**Concurrency model:** Messages within a single session execute serially (one at a time). Messages across different sessions execute concurrently. The sync `Agent.run()` is never modified -- all async wrapping happens at the boundary.

### Context Window Management

```
Agent.run()
  → _format_conversation()
      → trim tool results over 4000 chars (head/tail with [trimmed] marker)
  → estimate_tokens(formatted_text)
  → if utilization > 80%:
      → extract memories to MemoryStore (pre-compression)
      → compress_context(tree, summary, keep_recent_turns=10)
      → inject "[context optimized]" summary node
```

### Message Interruption

```
Async boundary (web/telegram)
  → InterruptionManager.interrupt(session_id, message, mode)
      → APPEND: queue behind current response (default)
      → STEER: inject at next tool boundary
      → CANCEL: abort current response

Agent._execute_tools() loop
  → InterruptionManager.check_urgent(session_id)
      → STEER: inject message, continue with new direction
      → CANCEL: abort loop, return partial response
```

## Protocol Definitions

Four `@runtime_checkable` Protocol classes define the expected interfaces for swappable subsystems:

| Protocol | Implemented By | Purpose |
|----------|---------------|---------|
| `MemoryBackend` | `MemoryStore` | Structured memory CRUD (facts, decisions) |
| `VectorBackend` | `VectorMemory` | Semantic similarity search |
| `Observer` | (custom) | Observability hooks (LLM calls, tool calls, errors) |
| `ConversationBackend` | `ConversationLog` | Conversation history append/read/persist |

These enable dependency injection and alternative implementations without inheriting from concrete classes. All are defined in `protocols.py`.

## Key Design Decisions

- **Local-first, cloud-optional**: Ollama for local inference by default. Cloud providers (OpenAI, Anthropic) available for users who prefer them. No cloud dependency for core operation.
- **SQLite everywhere**: Memory, tasks, approvals — all SQLite. Simple, portable, no server process.
- **Lazy CLI imports**: Every command imports its modules inside the function body to keep `merkaba --help` instant and avoid import-time failures.
- **Graduated autonomy**: `autonomy_level` on businesses and tasks controls what tools workers can use and which actions need approval.
- **Dual-path memory**: ChromaDB for semantic similarity when available; keyword matching as fallback.
- **Plugin-based extension**: Workers and adapters register via registries, so private packages can extend the framework without modifying core code.
- **Multi-business support**: Each business gets its own memory scope, prompt config, and approval settings.
- **Sync core, async boundary**: `Agent.run()` stays synchronous. Async wrappers (`asyncio.to_thread`) are applied at the web/telegram/channel boundary, keeping the core simple.
- **Per-session serialization**: `LaneQueue` uses one `threading.Lock` per session, so messages within a session are ordered but sessions don't block each other.
- **Semantic snapshots over screenshots**: Browser automation uses accessibility tree text (~50KB) instead of screenshots (~5MB), giving LLMs structured, actionable element data.
- **Hot reload safety**: Config changes take effect immediately, but security-critical keys log a warning recommending restart.
