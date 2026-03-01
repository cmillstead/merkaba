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
│   └── contradiction.py  # Contradiction detection between facts
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
│   └── secrets.py        # OS keychain wrapper via keyring
│
├── orchestration/
│   ├── supervisor.py     # Task dispatch to workers, configurable model routing
│   ├── workers.py        # Worker base class + WorkerResult + WORKER_REGISTRY
│   ├── code_worker.py    # Code generation and review worker
│   ├── explorer.py       # Codebase exploration worker
│   ├── scheduler.py      # Tick-based cron executor
│   ├── queue.py          # TaskQueue — SQLite task + run tracking
│   ├── heartbeat.py      # Lightweight health triage
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
│   ├── slack_adapter.py  # Slack API adapter
│   └── calendar_adapter.py # Apple Calendar adapter (macOS)
│
├── tools/
│   ├── base.py           # Tool dataclass, ToolResult, PermissionTier enum
│   ├── registry.py       # ToolRegistry — name→Tool dict
│   └── builtin/
│       ├── files.py       # file_read, file_write, file_list (with path restrictions)
│       ├── search.py      # grep, glob
│       ├── web.py         # web_fetch (with SSRF protection)
│       ├── shell.py       # bash (command allowlist)
│       └── memory_tools.py # memory_search tool
│
├── config/
│   └── prompts.py        # PromptLoader — SOUL.md / USER.md per-business prompt files
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
│   └── importer.py       # Plugin import pipeline
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

## Key Design Decisions

- **Local-first, cloud-optional**: Ollama for local inference by default. Cloud providers (OpenAI, Anthropic) available for users who prefer them. No cloud dependency for core operation.
- **SQLite everywhere**: Memory, tasks, approvals — all SQLite. Simple, portable, no server process.
- **Lazy CLI imports**: Every command imports its modules inside the function body to keep `merkaba --help` instant and avoid import-time failures.
- **Graduated autonomy**: `autonomy_level` on businesses and tasks controls what tools workers can use and which actions need approval.
- **Dual-path memory**: ChromaDB for semantic similarity when available; keyword matching as fallback.
- **Plugin-based extension**: Workers and adapters register via registries, so private packages can extend the framework without modifying core code.
- **Multi-business support**: Each business gets its own memory scope, prompt config, and approval settings.
