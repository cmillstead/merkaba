# Friday Architecture

## Overview

Friday is a local-first AI agent system running entirely on your Mac. It uses Ollama for LLM inference, SQLite for persistence, and has no cloud dependency for core operation. The system is built around graduated autonomy — it starts by asking for approval on actions, and earns the right to act more independently over time.

## Module Map

```
src/friday/
├── agent.py             # Core agent loop with memory injection and model routing
├── llm.py               # Ollama client wrapper (LLMClient, LLMResponse, ToolCall)
├── cli.py               # Typer CLI — all heavy imports are lazy
│
├── memory/
│   ├── store.py          # MemoryStore — SQLite (businesses, facts, decisions, learnings)
│   ├── retrieval.py      # MemoryRetrieval — unified query (vector + keyword fallback)
│   ├── vectors.py        # VectorMemory — ChromaDB with nomic-embed-text (optional)
│   └── conversation.py   # ConversationLog — session-scoped JSON persistence
│
├── security/
│   ├── classifier.py     # InputClassifier — qwen3:4b pre-flight safety + complexity
│   ├── validation.py     # Tool argument scanning, homoglyph normalization
│   ├── permissions.py    # PermissionManager — 4-tier approval (SAFE/MODERATE/SENSITIVE/DESTRUCTIVE)
│   ├── scanner.py        # SecurityScanner — integrity checks, CVE audit
│   ├── integrity.py      # SHA256 file hash baselines
│   ├── audit.py          # pip-audit wrapper for CVE detection
│   └── secrets.py        # Keychain wrapper via keyring
│
├── orchestration/
│   ├── supervisor.py     # Task dispatch to workers, fact/decision storage, approval routing
│   ├── workers.py        # Worker base class + WorkerResult
│   ├── content_worker.py # Content creation tasks (draft, review, publish)
│   ├── ecommerce_worker.py # Listing sync, pricing, inventory
│   ├── integration_worker.py # Delegates to adapter.execute()
│   ├── support_worker.py # Ticket triage, response drafting
│   ├── scheduler.py      # Tick-based cron executor (launchd integration)
│   ├── queue.py          # TaskQueue — SQLite task + run tracking
│   ├── heartbeat.py      # Lightweight triage via qwen3:4b
│   └── learnings.py      # Rule-based + LLM-based insight extraction
│
├── approval/
│   ├── queue.py          # ActionQueue — pending/approved/denied actions + stats
│   ├── graduation.py     # GraduationChecker — promote action types after N approvals
│   └── telegram.py       # Inline button UI for Telegram approval
│
├── integrations/
│   ├── base.py           # IntegrationAdapter ABC + ADAPTER_REGISTRY
│   ├── credentials.py    # CredentialManager — namespaced keychain access
│   ├── email_adapter.py  # SMTP send, IMAP read, LLM parse
│   ├── stripe_adapter.py # Read-only Stripe access
│   └── etsy_adapter.py   # Wraps EtsyClient for adapter interface
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
│       └── research.py    # etsy_search, analyze_results, save_research
│
├── web/
│   ├── app.py            # FastAPI factory with lifespan, auth, CORS
│   ├── routes/
│   │   ├── system.py      # /api/system/status, /api/system/models
│   │   ├── businesses.py  # /api/businesses CRUD
│   │   ├── memory.py      # /api/memory/search, /facts, /decisions, /learnings
│   │   ├── tasks.py       # /api/tasks CRUD + runs
│   │   ├── approvals.py   # /api/approvals + approve/deny endpoints
│   │   └── chat.py        # /ws/chat WebSocket, /api/chat/sessions, /api/upload
│   └── static/            # Built React SPA (Vite + TypeScript)
│
├── telegram/
│   ├── bot.py            # FridayBot — python-telegram-bot Application wrapper
│   ├── briefing.py       # System prompt context for Telegram sessions
│   ├── commands.py       # /research, /generate, /listing handlers
│   └── config.py         # Bot token + allowed user IDs
│
├── research/
│   ├── apify_client.py   # Etsy keyword research via Apify
│   ├── analyzer.py       # Demand/competition/opportunity scoring
│   └── database.py       # ResearchDatabase — SQLite for runs/listings/metrics
│
├── generation/
│   ├── comfyui_client.py # ComfyUI REST API client
│   ├── generator.py      # Image generation orchestrator
│   ├── bundler.py        # ZIP bundler for outputs
│   ├── prompt_suggester.py # Generate prompts from research data
│   └── workflow_manager.py # ComfyUI workflow JSON templates
│
├── listing/
│   ├── auth.py           # Etsy OAuth 2.0 PKCE flow
│   ├── client.py         # EtsyClient — Open API v3
│   ├── config.py         # Etsy credentials in config.json
│   └── generator.py      # LLM-generated listing content
│
└── plugins/
    ├── registry.py       # PluginRegistry (skills, commands, hooks, agents)
    ├── skills.py         # Skill loading from markdown + frontmatter
    ├── commands.py       # Command loading
    ├── hooks.py          # Hook event system
    ├── agents.py         # Agent config loading
    ├── analyzer.py       # Claude Code skill compatibility analysis
    ├── converter.py      # Skill format conversion
    └── importer.py       # Plugin import pipeline
```

## Data Flow

### Chat Request (CLI or Web)

```
User input
  → InputClassifier (qwen3:4b)
      → UNSAFE: return refusal
      → SIMPLE: route to qwen3:8b, skip tools
      → COMPLEX: route to qwen3.5:122b, enable tools
  → _recall_context(): keyword/vector search → inject facts into system prompt
  → LLMClient.chat() via Ollama
      → if tool_calls: validate args → check permissions → execute tool → loop
      → if text response: save to ConversationLog, return
```

### Scheduled Task

```
launchd (every 60s)
  → friday scheduler run
  → Scheduler.tick()
  → TaskQueue.get_due_tasks()
  → Supervisor.handle_task(task)
      → resolve Worker class from WORKER_REGISTRY
      → select model per task type
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

## Model Routing

| Tier | Model | Used By |
|------|-------|---------|
| Complex | `qwen3.5:122b` | Agent (complex queries), research/ecommerce/content workers |
| Simple | `qwen3:8b` | Agent (simple queries, no tools) |
| Classifier | `qwen3:4b` | InputClassifier, Heartbeat, LearningExtractor |
| Integration | `gemma3:27b` | IntegrationWorker |
| Health | `phi4:14b` | HealthCheckWorker |

## Storage

All data lives in `~/.friday/`:

| File | Contents |
|------|----------|
| `config.json` | API keys, OAuth tokens, model overrides, web API key |
| `memory.db` | Businesses, facts, decisions, relationships, state, learnings |
| `tasks.db` | Task definitions, schedules, run history |
| `actions.db` | Approval queue, approval stats |
| `research.db` | Etsy research runs, listings, metrics |
| `conversations/` | JSON session logs (one per chat session) |
| `memory_vectors/` | ChromaDB collections (optional) |
| `uploads/` | Web chat file uploads |
| `outputs/` | Generated images |
| `bundles/` | Packaged ZIPs |
| `workflows/` | ComfyUI templates |
| `logs/` | Scheduler stdout/stderr |
| `plugins/` | Locally imported plugins |

## Security Layers

1. **Input Classifier** — LLM pre-flight blocks prompt injection
2. **Argument Validation** — regex scanning for injection patterns + homoglyph normalization
3. **Permission Tiers** — SAFE/MODERATE/SENSITIVE/DESTRUCTIVE with configurable auto-approve level
4. **Path Restrictions** — file tools block sensitive paths (`.ssh`, `.env`, credentials)
5. **SSRF Protection** — web_fetch blocks localhost, metadata endpoints, RFC-1918 ranges
6. **Shell Allowlist** — bash tool only allows specific commands and git subcommands
7. **Approval Workflows** — actions above threshold require human approval
8. **Tool Graduation** — tools earn trust over time (N approvals, 0 denials)
9. **Integrity Monitoring** — SHA256 baselines for core security files
10. **CVE Scanning** — pip-audit integration for dependency vulnerabilities

## Key Design Decisions

- **Local-first**: All LLM inference through Ollama on localhost. No cloud API keys for core operation.
- **SQLite everywhere**: Memory, tasks, approvals, research — all SQLite. Simple, portable, no server process.
- **Lazy CLI imports**: Every command imports its modules inside the function body to keep `friday --help` instant and avoid import-time failures (SOCKS proxy, missing deps).
- **Graduated autonomy**: `autonomy_level` on businesses and tasks controls what tools workers can use and which actions need approval.
- **Dual-path memory**: ChromaDB for semantic similarity when available; keyword matching as fallback.
- **Thread-safe DB access**: `check_same_thread=False` on SQLite connections for web chat's executor thread pattern.
