# Merkaba — Local AI Agent Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![Tests: 1635+](https://img.shields.io/badge/Tests-1635%2B-green.svg)](tests/)

Build autonomous AI agents with persistent memory, tool use, multi-model routing, and graduated autonomy. Local-first with optional cloud fallback. No vendor lock-in.

## Why Merkaba?

Most AI agent frameworks are cloud-first wrappers around API calls. Merkaba is different:

- **Local-first** — All inference runs on local models via Ollama. Your data never leaves your machine. Cloud providers (OpenAI, Anthropic) are optional fallbacks, not requirements.
- **Graduated autonomy** — Agents start with full human approval and earn trust over time. The approval system tracks history and promotes tools that consistently get approved.
- **Persistent memory** — SQLite + optional ChromaDB vector search. Agents remember context across sessions, with memory lifecycle management (decay, consolidation, contradiction detection, relationship graphs).
- **Extensible by design** — Register custom workers and adapters from private packages. Build your business logic separately, keep it private, and plug it into the framework.

## Quickstart

```bash
# 1. Install Ollama (or use cloud providers)
brew install ollama && ollama serve    # macOS
# See https://ollama.com for Linux/Windows

# 2. Pull a model
ollama pull qwen3:8b

# 3. Install Merkaba
pip install merkaba

# 4. Chat
merkaba chat "Hello, what can you do?"
```

## Features

- **Persistent memory** — SQLite + optional ChromaDB vector search, auto-injected into agent context, relationship graph traversal
- **Model routing** — Input classifier routes simple queries to small models, complex to large
- **Multi-provider** — Ollama (local), OpenAI, Anthropic, with configurable fallback chains
- **Security layers** — Input classifier, permission tiers, argument validation, memory sanitization
- **Approval workflows** — Human-in-the-loop via Telegram or web UI, with optional TOTP 2FA
- **Task orchestration** — Supervisor dispatches to specialized workers with heartbeat monitoring
- **Web dashboard** — React SPA with real-time chat, task management, analytics, calendar, and configurable settings
- **Prompt personalization** — Per-business SOUL.md/USER.md personality and context files
- **Code agent** — Generates code from specs, verifies with linting, auto-repairs on failure
- **Integrations** — Email, Stripe, Slack, GitHub, Apple Calendar, Discord, Signal (+ bring your own via adapters)
- **Plugin system** — Skills, commands, hooks, and agents with sandboxed execution
- **Conversation encryption** — Optional Fernet encryption for stored conversations
- **Context management** — Automatic compression at ~80% utilization, tool result trimming, conversation tree pruning
- **Hot-reloadable config** — Edit `config.json` at runtime; changes take effect on next request
- **Message interruption** — APPEND/STEER/CANCEL modes let users redirect the agent mid-response
- **Browser automation** — Headless Playwright with semantic snapshots (accessibility tree, ~50KB vs ~5MB screenshots)
- **Multi-channel** — Telegram, Discord, Slack (real-time + Block Kit approvals), Signal, Web, CLI
- **Session pool** — Per-session Agent instances with LRU eviction, idle timeout, and async boundaries
- **Gateway pairing** — One-time 6-char code authenticates new channel connections; CLI always trusted
- **Heartbeat checklist** — User-editable `HEARTBEAT.md` files parsed and executed by the scheduler
- **Message chunking** — Platform-aware delivery splits long responses at paragraph/sentence boundaries
- **Identity portability** — OpenClaw workspace migration and AIEOS v1.1 import/export
- **Formal protocols** — `MemoryBackend`, `VectorBackend`, `Observer`, `ConversationBackend` for dependency injection

## Architecture

```
                         ┌─────────────────────┐
                         │      User Input      │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Input Classifier   │  safety + complexity
                         │   (small model)      │  routing
                         └──────────┬──────────┘
                            simple  │  complex
                       ┌────────────┼────────────┐
                       ▼                         ▼
                ┌─────────────┐         ┌─────────────┐
                │  Small LLM  │         │  Large LLM  │
                │  (no tools) │         │  (+ tools)  │
                └─────────────┘         └──────┬──────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │    Tool Execution    │
                                    │  files, shell, web,  │
                                    │  memory, search ...  │
                                    └──────────┬──────────┘
                                               │
                     ┌─────────────────────────┼─────────────────────────┐
                     ▼                         ▼                         ▼
              ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
              │   Memory    │         │  Approvals  │         │   Workers   │
              │  (SQLite +  │         │ (Telegram / │         │  (code +    │
              │  ChromaDB)  │         │   Web UI)   │         │  your own)  │
              └─────────────┘         └─────────────┘         └─────────────┘
```

<details>
<summary>Project structure</summary>

```
merkaba/
├── agent.py             # Memory-aware agent with model routing
├── llm.py               # LLM client with retry + fallback chains
├── llm_providers/       # Provider adapters (Ollama, Anthropic, OpenAI)
├── cli.py               # Typer CLI (all imports lazy)
├── memory/              # Persistent memory (store, retrieval, vectors, lifecycle, relationships)
├── orchestration/       # Supervisor, workers, scheduler, session pool, interruption
├── approval/            # Action queue, graduation, Telegram approval UI
├── security/            # Input classifier, validation, encryption, permissions
├── verification/        # Deterministic verifier (lint/type-check after writes)
├── config/              # PromptLoader, hot-reload, startup validation
├── integrations/        # Adapter base + email, Stripe, Slack, GitHub, Calendar, Discord, Signal
├── tools/builtin/       # Agent tools (files, shell, search, web, memory, browser)
├── identity/            # AIEOS identity import/export
├── protocols.py         # Formal Protocol definitions for swappable subsystems
├── web/                 # Mission Control (FastAPI + React SPA)
│   ├── app.py           # App factory
│   ├── routes/          # REST + WebSocket endpoints
│   └── static/          # Built React frontend
├── telegram/            # Telegram bot interface
├── observability/       # Token tracking, tracing, audit trail
├── plugins/             # Plugin support with sandboxing
└── examples/            # Extension examples (custom worker, adapter)
```

</details>

## CLI Reference

```bash
merkaba chat "Hello"             # Single message
merkaba chat                     # Interactive mode
merkaba web                      # Start web dashboard on port 5173
merkaba memory status            # Show memory stats
merkaba memory recall "topic"    # Search memories
```

<details>
<summary>Full CLI reference</summary>

### Chat

```bash
merkaba chat "Hello"                     # Single message
merkaba chat                             # Interactive mode
merkaba chat -m gemma3:27b "Hi"          # Use specific model
```

### Mission Control (Web UI)

```bash
merkaba web                              # Start web dashboard on port 5173
merkaba web --port 8080                  # Custom port
```

Provides a React dashboard with:
- Dashboard with KPI cards (active tasks, agents online, pending approvals, connection status)
- Grouped sidebar navigation (Operations, Knowledge, Team, System)
- Calendar view with weekly CSS Grid, month toggle, cron parsing, and click-to-trigger
- Standalone kanban board with worker type filtering
- Notification center with unread badge and event history
- Settings page for models, security, scheduler, and system info
- System status, task queue, and approval management
- Business overview with per-business switcher
- Per-business config editing (SOUL.md/USER.md prompt files)
- Cross-business analytics (tasks, approvals, memory)
- Memory browser with search
- Real-time chat with file upload and tool streaming (WebSocket)
- Chat history with session management
- Keyboard shortcuts: H (dashboard), C (constellation), K (kanban), D (diagnostics)

### Memory

```bash
merkaba memory status                    # Show memory stats
merkaba memory recall "topic"            # Search memories
merkaba memory businesses                # List known businesses
merkaba memory decay                     # Decay stale memories
merkaba memory consolidate               # LLM-summarize related clusters
merkaba memory rebuild-vectors           # Rebuild vector store from SQLite
merkaba memory episodes                  # View episodic memory
merkaba memory archived [table]          # List archived items (facts/decisions/learnings)
merkaba memory unarchive <table> <id>    # Restore an archived item
```

### Scheduler

```bash
merkaba scheduler run                    # Execute one scheduler tick
merkaba scheduler start                  # Run scheduler loop
merkaba scheduler workers                # Show registered workers
merkaba scheduler install                # Install macOS launchd agent
merkaba scheduler remove                 # Remove launchd agent
```

### Approvals

```bash
merkaba approval list                    # Show pending approvals
merkaba approval approve <id>            # Approve an action
merkaba approval deny <id> --reason "…"  # Deny with reason
merkaba approval stats                   # Approval statistics
merkaba approval graduation              # Show tool graduation status
```

### Business Management

```bash
merkaba business add "My Service"        # Register a business
merkaba business list                    # List businesses
merkaba business show <id>              # Show business details
merkaba business update <id>            # Update business settings
merkaba business dashboard <id>         # Business dashboard
```

### Tasks

```bash
merkaba tasks list                       # Show task queue
merkaba tasks add "Task name"            # Add a task
merkaba tasks pause <id>                 # Pause a task
merkaba tasks resume <id>               # Resume a paused task
merkaba tasks runs <id>                  # Show run history for a task
```

### Telegram Bot

```bash
merkaba telegram setup                   # Configure bot token and user ID
merkaba telegram status                  # Check bot configuration
merkaba serve                            # Start with Telegram bot
```

### Code Agent

```bash
merkaba code run "Add validation" --target src/user.py
merkaba code run "Build a parser" --explore src/ --high-stakes
merkaba code review src/user.py --criteria "Check error handling"
merkaba code explore src/orchestration/
```

### Model Management

```bash
merkaba models list                      # Show task_type → model mapping
merkaba models check                     # Check loaded models + fallback coverage
merkaba models set <task_type> <model>   # Override model for a task type
merkaba models providers                 # Show cloud provider status
```

### Integrations

```bash
merkaba integrations list                # Show registered adapters
merkaba integrations test <name>         # Test adapter connectivity
merkaba integrations setup <name>        # Configure adapter credentials
```

### Backup & Restore

```bash
merkaba backup run                       # Backup all databases and config
merkaba backup list                      # List available backups
merkaba backup restore <ts> <db>         # Restore from backup
```

### Prompt Config

```bash
merkaba config show-prompt               # Show resolved prompt chain
merkaba config edit-soul                 # Edit global SOUL.md
merkaba config edit-user --business 1    # Edit business-specific USER.md
```

### Security

```bash
merkaba security status                 # Show 2FA + rate limit status
merkaba security scan                   # Quick security scan
merkaba security scan --full            # Full scan (integrity + CVE + code)
merkaba security scan --regenerate-baseline  # Regenerate integrity baseline
merkaba security setup-2fa              # Generate TOTP secret
merkaba security disable-2fa --yes      # Remove TOTP secret
merkaba security enable-encryption      # Enable conversation encryption
merkaba security disable-encryption     # Disable encryption
```

### Plugins

```bash
merkaba plugins list                     # List installed plugins
merkaba plugins available                # List available plugins to import
merkaba plugins import <path>            # Import a plugin
merkaba plugins inspect <name>           # Inspect plugin details
merkaba plugins uninstall <name>         # Uninstall a plugin
merkaba commands list                    # List plugin commands
```

### Skills

```bash
merkaba skills forge --from <url>            # Generate plugin from ClawHub/GitHub skill
merkaba skills forge --from <url> --name x   # Generate with custom name
merkaba skills forge --from <url> --force    # Proceed even if flagged dangerous
```

### Observability

```bash
merkaba observe tokens                   # Token usage stats
merkaba observe audit                    # Audit trail
merkaba observe trace                    # Tracing logs
```

### Gateway Pairing

```bash
merkaba pair list                        # List paired identities
merkaba pair initiate <channel> <id>     # Generate a 6-char pairing code
merkaba pair confirm <identity> <code>   # Confirm pairing code
merkaba pair revoke <identity>           # Revoke a paired identity
```

### Migration & Identity

```bash
merkaba migrate openclaw <path> --name "My Business"  # Import OpenClaw workspace
merkaba identity import <aieos.json> --name "My Agent" # Import AIEOS v1.1 identity
merkaba identity export <business> --output agent.json  # Export as AIEOS v1.1
```

</details>

## Extending Merkaba

Merkaba is designed to be extended by private packages. The two main extension points:

### Custom Workers

Workers execute tasks dispatched by the supervisor. Subclass `Worker` and register for a task type:

```python
# my_package/workers/analytics.py
from merkaba.orchestration.workers import Worker, WorkerResult, register_worker

class AnalyticsWorker(Worker):
    def execute(self, task: dict) -> WorkerResult:
        prompt = task.get("prompt", "")
        response = self._ask_llm(prompt)
        return WorkerResult(success=True, output={"response": response})

register_worker("analytics", AnalyticsWorker)
```

### Custom Adapters

Adapters connect to external services. Subclass `IntegrationAdapter` and register:

```python
# my_package/adapters/crm.py
from merkaba.integrations.base import IntegrationAdapter, register_adapter

class CRMAdapter(IntegrationAdapter):
    def connect(self) -> bool:
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        return {"status": "ok", "action": action}

    def health_check(self) -> dict:
        return {"healthy": self.is_connected}

register_adapter("crm", CRMAdapter)
```

See [`src/merkaba/examples/`](src/merkaba/examples/) for complete examples.

## Configuration

Merkaba stores all data in `~/.merkaba/`:

```
~/.merkaba/
├── config.json      # API keys, model overrides, cloud providers
├── SOUL.md          # Global agent personality/behavior
├── USER.md          # Global owner context
├── memory.db        # Businesses, facts, decisions, relationships, learnings
├── tasks.db         # Task definitions, schedules, run history
├── actions.db       # Approval queue, approval stats
├── businesses/      # Per-business overrides
│   └── {id}/
│       ├── SOUL.md  # Business-specific personality
│       └── USER.md  # Business-specific owner context
├── conversations/   # JSON session logs
├── memory_vectors/  # ChromaDB collections (optional)
├── backups/         # Timestamped database backups
├── plugins/         # Locally imported plugins
└── logs/            # Scheduler logs
```

## Setup Scenarios

Merkaba supports local-only, cloud-only, and hybrid configurations. Choose what fits your hardware and privacy requirements.

### Fully Local (Ollama)

Everything runs on your machine. No API keys, no cloud, no data leaving your network.

```bash
# Install Ollama
brew install ollama && ollama serve          # macOS
curl -fsSL https://ollama.com/install.sh | sh  # Linux

# Pull models (pick one setup)
ollama pull qwen3:8b                         # Minimum: 8GB VRAM, basic agent
ollama pull qwen3:8b && ollama pull qwen3:4b # Better: adds classifier routing
ollama pull qwen3.5:122b && ollama pull qwen3:8b && ollama pull qwen3:4b  # Full: 80GB+ VRAM

# No config needed — defaults to Ollama
merkaba chat "Hello"
```

**Hardware requirements:**

| Setup | VRAM | Models | Experience |
|-------|------|--------|------------|
| Minimum | 6 GB | `qwen3:8b` | Basic chat, no routing |
| Recommended | 12 GB | `qwen3:8b` + `qwen3:4b` | Classifier routing, fast |
| Full | 80 GB+ | `qwen3.5:122b` + `qwen3:8b` + `qwen3:4b` | Best quality, all features |
| Mac Studio | 64-512 GB unified | Any combination | Unified memory handles large models |

### Cloud Only (no GPU needed)

Run entirely on cloud APIs. No local GPU required.

```bash
pip install merkaba[cloud]
```

`~/.merkaba/config.json`:
```json
{
  "cloud_providers": {
    "anthropic": {"api_key": "sk-ant-..."}
  },
  "models": {
    "task_types": {
      "complex": "anthropic:claude-sonnet-4-20250514",
      "simple": "anthropic:claude-haiku-4-5-20251001",
      "classifier": "anthropic:claude-haiku-4-5-20251001"
    }
  }
}
```

```bash
merkaba chat "Hello"   # Uses Anthropic
```

Or with OpenAI:
```json
{
  "cloud_providers": {
    "openai": {"api_key": "sk-..."}
  },
  "models": {
    "task_types": {
      "complex": "openai:gpt-4o",
      "simple": "openai:gpt-4o-mini",
      "classifier": "openai:gpt-4o-mini"
    }
  }
}
```

API keys can also be set via environment variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

### Hybrid (Local + Cloud Fallback)

Use local models by default, fall back to cloud when they're unavailable or overloaded.

```bash
pip install merkaba[cloud]
ollama pull qwen3.5:122b && ollama pull qwen3:8b && ollama pull qwen3:4b
```

`~/.merkaba/config.json`:
```json
{
  "cloud_providers": {
    "anthropic": {"api_key": "sk-ant-..."},
    "openai": {"api_key": "sk-..."}
  },
  "models": {
    "fallback_chains": {
      "complex": {
        "primary": "qwen3.5:122b",
        "fallbacks": ["qwen3:8b", "anthropic:claude-sonnet-4-20250514"]
      },
      "simple": {
        "primary": "qwen3:8b",
        "fallbacks": ["openai:gpt-4o-mini"]
      }
    }
  }
}
```

If Ollama goes down or a model is unloaded, merkaba automatically tries the next model in the chain.

### OpenRouter (Access Many Providers)

Use [OpenRouter](https://openrouter.ai) to access models from many providers through a single API key.

```bash
pip install merkaba[openai]   # OpenRouter uses the OpenAI-compatible API
```

```json
{
  "cloud_providers": {
    "openrouter": {
      "api_key": "sk-or-...",
      "base_url": "https://openrouter.ai/api/v1"
    }
  }
}
```

```bash
merkaba chat -m openrouter:anthropic/claude-sonnet-4-20250514 "Hello"
merkaba chat -m openrouter:google/gemini-2.5-pro "Hello"
```

### Per-Task Model Routing

Assign different models to different task types:

```json
{
  "models": {
    "task_types": {
      "code": "qwen3.5:122b",
      "health_check": "phi4:14b",
      "complex": "anthropic:claude-sonnet-4-20250514",
      "simple": "qwen3:8b",
      "classifier": "qwen3:4b"
    }
  }
}
```

```bash
merkaba models list      # Show current routing
merkaba models set code anthropic:claude-sonnet-4-20250514  # Change at runtime
```

## Documentation

The README covers installation, quickstart, and configuration. For deeper coverage of every subsystem:

- **[Manual](docs/manual.md)** — Comprehensive reference covering memory (conversation trees, contradiction detection, relationship graphs, episodic memory, lifecycle, context compression), security (classifier, validation, encryption, integrity monitoring, scanner, gateway pairing), approval system (2FA, rate limiting, graduation), orchestration (supervisor dispatch modes, session pool, interruption, heartbeat checklist, code worker, exploration agent, learning extractor, health checks), LLM client (request priority, concurrency gate, fallback chains), browser automation, channel adapters (Discord, Slack RT, Signal), message chunking, hot-reloadable config, startup validation, plugin system (skills, hooks, sandbox manifests, Claude Code import, OpenClaw migration), identity portability (AIEOS import/export), extension system (entry points for workers, adapters, CLI), protocol definitions, and observability (audit trail, token tracking, tracing).
- **[Architecture](docs/architecture.md)** — Module map, data flow diagrams, storage schema, security layers, design decisions.
- **[QMD Integration](docs/integrations/qmd.md)** — On-device document search setup guide.

## Third-Party Integrations

Merkaba integrates with open source tools to extend agent capabilities. These are optional — the framework works fully without them.

| Tool | Purpose | License |
|------|---------|---------|
| [QMD](https://github.com/tobi/qmd) | On-device document search (hybrid BM25 + vector + re-ranking) | MIT |

See [docs/integrations/](docs/integrations/) for setup guides.

## Security

Merkaba has 14 security layers including input classification, permission tiers, approval workflows with optional TOTP 2FA, conversation encryption, memory sanitization, plugin sandboxing, and gateway pairing for new channel connections.

See [SECURITY.md](SECURITY.md) for the full security model.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) for local inference (or configure cloud providers)
- Node.js 18+ to rebuild web frontend (optional — pre-built SPA included)

## Development

```bash
git clone https://github.com/cmillstead/merkaba.git && cd merkaba
pip install -e ".[dev]"
pytest  # 1635+ tests
```

## Acknowledgments

Merkaba's plugin import system can convert skills from these open-source Claude Code plugins:

- [Superpowers](https://github.com/obra/superpowers) by Jesse Vincent — TDD, debugging, and collaboration workflow skills
- [Hugging Face Skills](https://github.com/huggingface/skills) by Hugging Face — AI/ML task skills for datasets, training, and evaluation
- [Vercel Deploy Plugin](https://github.com/vercel/vercel-deploy-claude-code-plugin) by Vercel (MIT) — deployment and monitoring
- [Sentry Plugin](https://github.com/anthropics/claude-plugins-official) by Sentry — error monitoring and code review
- [Pinecone Plugin](https://github.com/anthropics/claude-plugins-official) by Pinecone — vector database integration
- [Frontend Design](https://github.com/anthropics/claude-plugins-official), [Skill Creator](https://github.com/anthropics/claude-plugins-official) by Anthropic

## License

[MIT](LICENSE)
