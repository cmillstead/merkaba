# Merkaba Manual

This manual covers Merkaba's subsystems in depth. For installation, quickstart, and configuration basics, see the [README](../README.md). For architecture overview, see [architecture.md](architecture.md).

---

## Table of Contents

1. [Memory System](#memory-system)
   - [Retrieval Pipeline](#retrieval-pipeline)
   - [Conversation Trees](#conversation-trees)
   - [Contradiction Detection](#contradiction-detection)
   - [Memory Lifecycle](#memory-lifecycle)
   - [Episodic Memory](#episodic-memory)
   - [Relationship Graph](#relationship-graph)
   - [Archived Memory](#archived-memory)
   - [Session Extraction](#session-extraction)
   - [Vector Memory](#vector-memory)
2. [Security](#security)
   - [Input Classifier](#input-classifier)
   - [Argument Validation](#argument-validation)
   - [Memory Sanitization](#memory-sanitization)
   - [Permission Tiers](#permission-tiers)
   - [Conversation Encryption](#conversation-encryption)
   - [Integrity Monitoring](#integrity-monitoring)
   - [Security Scanner](#security-scanner)
3. [Approval System](#approval-system)
   - [Action Queue](#action-queue)
   - [TOTP 2FA](#totp-2fa)
   - [Rate Limiting](#rate-limiting)
   - [Graduation](#graduation)
4. [Orchestration](#orchestration)
   - [Supervisor & Dispatch Modes](#supervisor--dispatch-modes)
   - [Workers](#workers)
   - [Code Worker](#code-worker)
   - [Support Worker](#support-worker)
   - [Integration Worker](#integration-worker)
   - [Exploration Agent](#exploration-agent)
   - [Learning Extractor](#learning-extractor)
   - [Health Checks](#health-checks)
5. [LLM Client](#llm-client)
   - [Request Priority](#request-priority)
   - [Concurrency Gate](#concurrency-gate)
   - [Retry & Fallback Chains](#retry--fallback-chains)
   - [Provider Routing](#provider-routing)
6. [Verification](#verification)
   - [Deterministic Verifier](#deterministic-verifier)
7. [Plugin System](#plugin-system)
   - [Plugin Registry](#plugin-registry)
   - [Skills](#skills)
   - [Commands](#commands)
   - [Hooks](#hooks)
   - [Agents](#agents)
   - [Sandbox & Manifests](#sandbox--manifests)
   - [Importing from Claude Code](#importing-from-claude-code)
   - [Skill Activation](#skill-activation)
8. [Extension System](#extension-system)
   - [Entry Points](#entry-points)
   - [Custom Workers](#custom-workers)
   - [Custom Adapters](#custom-adapters)
   - [Custom CLI Commands](#custom-cli-commands)
9. [Observability](#observability)
   - [Decision Audit Trail](#decision-audit-trail)
   - [Token Usage Tracking](#token-usage-tracking)
   - [Tracing](#tracing)
10. [Web Dashboard](#web-dashboard)
    - [API Authentication](#api-authentication)

---

## Memory System

Merkaba's memory is built on SQLite with optional ChromaDB vector search. The agent remembers facts, decisions, learnings, episodes, and entity relationships across sessions.

**Key files:** `memory/store.py`, `memory/retrieval.py`, `memory/vectors.py`, `memory/lifecycle.py`, `memory/contradiction.py`, `memory/conversation.py`

### Retrieval Pipeline

When the agent needs context, `MemoryRetrieval.recall()` runs a multi-stage pipeline:

```
Query
  1. Vector search (ChromaDB) -> semantic matches
  2. Keyword backfill -> fill gaps if vectors returned few results
  3. Relationship traversal -> BFS over entity graph
  4. Episode recall -> recent task episodes
  5. Access tracking -> update last_accessed + access_count
  6. Token budget -> trim to max_context_tokens
```

If ChromaDB is unavailable, step 1 falls back entirely to keyword search.

**Configuration** (`RetrievalConfig`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_items` | 5 | Max results per recall |
| `min_relevance_score` | 0.25 | Keyword overlap threshold (0.0-1.0) |
| `max_distance` | 1.5 | ChromaDB L2 distance threshold |
| `max_context_tokens` | 800 | Token budget for results (~4 chars/token) |

**CLI:**

```bash
merkaba memory recall "topic"      # Search memories
merkaba memory status              # Show memory stats
```

### Conversation Trees

Beyond flat chat logs, Merkaba supports tree-structured conversations with branching, pruning, and summary injection.

`ConversationTree` maintains a DAG of `Message` nodes:

```python
tree = ConversationTree(session_id="my-session")

# Normal conversation
tree.append("user", "Hello")
tree.append("assistant", "Hi there!")
tree.append("user", "Tell me about Python")
tree.append("assistant", "Python is a programming language...")

# Branch from an earlier message to explore alternatives
branch_point = tree.messages[1].id  # "Hi there!"
tree.branch_from(branch_point)
tree.append("user", "Tell me about Rust instead")
tree.append("assistant", "Rust is a systems programming language...")

# Get the current active path (root -> current leaf)
active = tree.get_active_branch()

# Prune a branch (soft-delete all descendants)
tree.prune_branch(branch_point)

# Inject a summary at a branch point
tree.inject_summary(branch_point, "User explored Python and Rust topics")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `append(role, content, metadata)` | Add message as child of current leaf |
| `get_active_branch()` | Linear path from root to current leaf (skips pruned) |
| `branch_from(message_id)` | Set leaf to an earlier message for branching |
| `prune_branch(from_message_id)` | Soft-delete all descendants |
| `inject_summary(after_message_id, summary)` | Insert system summary after a branch point |
| `to_serializable()` / `from_serializable()` | JSON round-trip |

`ConversationLog` handles persistence with optional encryption:

- Auto-saves to `~/.merkaba/conversations/{session_id}.json`
- Detects `MERKABA_ENC:` prefix for encrypted files
- Uses `fsync` for durability

### Contradiction Detection

When new facts are written, the `ContradictionDetector` can check for conflicts with existing knowledge.

**Flow:**

```
New fact written (check_contradictions=True)
  -> Fetch existing facts for same business + category
  -> Compute keyword overlap (Jaccard similarity)
  -> If overlap >= 0.7: ask LLM "Do these contradict?"
  -> If LLM says YES: archive the old fact
```

**Example:**

```python
store.add_fact(
    business_id=1,
    category="pricing",
    key="monthly_plan",
    value="$29/month",
    check_contradictions=True,  # Enable detection
)
# If an existing fact says "$19/month", the old one gets archived
```

**Deduplication** also uses keyword overlap. `deduplicate_by_recency()` groups similar results (overlap >= 0.85) and keeps only the most recent per group. This runs during recall to prevent stale duplicates from filling the context window.

### Memory Lifecycle

Three automated processes manage memory health:

**1. Decay** (`MemoryDecayJob`)

Reduces relevance scores for stale memories. Configured as a scheduled worker (daily at 3 AM).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `decay_factor` | 0.95 | Multiplier per stale period |
| `stale_days` | 7 | Days since last access to trigger decay |
| `archive_threshold` | 0.1 | Min relevance_score before archiving |

Items below the archive threshold are automatically archived (soft-deleted).

```bash
merkaba memory decay  # Run manually
```

**2. Consolidation** (`MemoryConsolidationJob`)

Groups related facts by category and summarizes them with an LLM. Configured as a scheduled worker (weekly, Sunday at 4 AM).

- Groups facts by category per business
- If a group has >= 5 facts, generates an LLM summary
- Stores summary as a new fact (source="consolidation", confidence=80)
- Archives the original individual facts
- Optionally rebuilds vector indexes after consolidation

```bash
merkaba memory consolidate  # Run manually
```

**3. Session Extraction** (`SessionExtractor`)

See [Session Extraction](#session-extraction) below.

### Episodic Memory

Episodes capture completed task outcomes as structured records:

```python
store.add_episode(
    business_id=1,
    task_type="support",
    task_id=42,
    summary="Triaged customer billing complaint",
    outcome="resolved",
    outcome_details="Issued partial refund",
    key_decisions=["escalated to billing team", "approved 50% refund"],
    duration_seconds=300,
    tags=["billing", "refund"],
)
```

**Fields:** business_id, task_type, task_id, summary, outcome, outcome_details, key_decisions (JSON), duration_seconds, tags (JSON), created_at.

**CLI:**

```bash
merkaba memory episodes                    # List recent episodes
merkaba memory episodes <episode_id>       # View details
```

Episodes are also included in the retrieval pipeline -- the 3 most recent episodes for the active business are appended to recall results.

### Relationship Graph

Merkaba tracks entity relationships as a graph stored in SQLite:

```python
store.add_relationship(
    business_id=1,
    entity_type="customer",
    entity_id="alice",
    relation="purchased",
    related_entity="premium_plan",
    metadata={"date": "2026-01-15"},
)
```

**Graph traversal** uses BFS to walk relationships:

```python
# Find all entities within 2 hops of "alice"
results = store.traverse("alice", depth=2, business_id=1)
# -> [{"entity_id": "alice", "relation": "purchased", "related_entity": "premium_plan"}, ...]
```

During recall, `_recall_relationships()` finds entities mentioned in the query and traverses their graph to surface related context. Entity matching is case-insensitive.

**Entity discovery:**

```python
# Find known entities mentioned in free text
entities = store.find_entities("What did alice buy?", business_id=1)
# -> ["alice"]
```

### Archived Memory

Facts, decisions, and learnings can be archived (soft-deleted) and restored:

```bash
merkaba memory archived facts              # List archived facts
merkaba memory archived decisions          # List archived decisions
merkaba memory archived learnings          # List archived learnings
merkaba memory unarchive facts <id>        # Restore a fact
merkaba memory unarchive decisions <id>    # Restore a decision
merkaba memory unarchive learnings <id>    # Restore a learning
```

Archives are used by:
- **Contradiction detection** -- contradicted facts are archived
- **Memory decay** -- items below relevance threshold are archived
- **Consolidation** -- original facts are archived after summarization

Archived items are excluded from recall results by default. Pass `include_archived=True` to `get_facts()`, `get_decisions()`, or `get_learnings()` to include them.

### Session Extraction

After each chat session (if >= 4 messages), the agent automatically extracts facts and relationships from the conversation:

```
Agent.run() completes
  -> _extract_session_memories()
  -> SessionExtractor.extract(conversation, business_id)
  -> LLM extracts {"facts": [...], "relationships": [...]}
  -> Dedup against existing store
  -> Store new facts and relationships
```

Uses the small model (`qwen3:8b`) for efficiency. This is fire-and-forget -- extraction failures never block the agent response.

**Extracted format:**

```json
{
  "facts": [
    {"category": "preference", "key": "language", "value": "Python", "confidence": 70}
  ],
  "relationships": [
    {"entity": "user", "entity_type": "person", "relation": "prefers",
     "related_entity": "Python", "related_type": "language"}
  ]
}
```

### Vector Memory

ChromaDB provides semantic search alongside SQLite keyword search.

**Setup:**

```bash
pip install merkaba[vectors]  # Installs chromadb
ollama pull nomic-embed-text  # Embedding model
```

**Collections:** `facts`, `decisions`, `learnings` -- each stored separately in ChromaDB with Ollama embeddings (`nomic-embed-text`).

**Rebuild:**

```bash
merkaba memory rebuild-vectors  # Rebuild all collections from SQLite
```

This drops and recreates all vector collections, re-indexing all non-archived items. Useful after bulk imports or if vectors get out of sync.

**Search flow:**
1. Query embedded via `nomic-embed-text`
2. L2 distance search across collections
3. Distance converted to relevance: `score = max(0.0, 1.0 - distance / 1.5)`
4. Results merged with keyword search for coverage

---

## Security

Merkaba implements defense-in-depth with multiple security layers.

**Key files:** `security/classifier.py`, `security/validation.py`, `security/sanitizer.py`, `security/permissions.py`, `security/encryption.py`, `security/integrity.py`, `security/scanner.py`

### Input Classifier

A lightweight LLM (`qwen3:4b`) pre-screens every user message for safety and complexity before it reaches the main agent.

**Output:** `(is_safe: bool, reason: str, complexity: str)`

| Result | Meaning |
|--------|---------|
| `SAFE SIMPLE` | Route to small model, no tools |
| `SAFE COMPLEX` | Route to large model, enable tools |
| `UNSAFE *` | Block with refusal message |

**Graceful degradation:**
- If classifier is unavailable and `classifier_required=True` (default): route to large model in `no_tools` mode (safe fallback)
- If `classifier_required=False`: fail open to `complex` mode

The classifier detects prompt injection attempts that bypass regex patterns -- poetic jailbreaks, roleplay, creative rephrasing.

### Argument Validation

Every tool call's arguments are validated before execution:

1. **Type checking** -- arguments match the tool's JSON schema types
2. **Unknown argument detection** -- extra arguments are rejected
3. **Required field checking** -- missing required fields are caught
4. **Prompt injection scanning** -- recursive scan through all string values:
   - 17 regex patterns covering common jailbreak attempts
   - Unicode normalization (NFKC) to catch full-width character tricks
   - Homoglyph detection (16 Cyrillic/Greek lookalike mappings)
   - Nested structure traversal (arrays, objects to arbitrary depth)

**Detected patterns include:**
- "ignore previous instructions"
- "you are now"
- "reveal system prompt"
- "disregard above/prior"
- Special tokens: `<|im_start|>`, `[INST]`, `<<SYS>>`, etc.

### Memory Sanitization

Before recalled memories are injected into the system prompt, `sanitize_memory_value()` strips known injection patterns and replaces them with `[redacted]`. This is a separate layer from argument validation -- defense in depth against stored prompt injection.

### Permission Tiers

Every tool has an assigned permission tier:

| Tier | Level | Examples |
|------|-------|----------|
| `SAFE` | 0 | file_read, file_list, grep, glob, memory_search |
| `MODERATE` | 1 | file_write, web_fetch |
| `SENSITIVE` | 2 | bash (shell commands) |
| `DESTRUCTIVE` | 3 | delete, publish, spend money |

The `PermissionManager` auto-approves tools at or below the configured `auto_approve_level`. Tools above the level trigger the approval callback (Telegram or Web UI) or raise `PermissionDenied`.

All permission checks are audit-logged with timestamp, tool name, tier, and decision.

### Conversation Encryption

Conversations stored on disk can be encrypted with Fernet (AES-128 in CBC mode + HMAC):

```bash
merkaba security enable-encryption   # Prompts for passphrase
merkaba security disable-encryption  # Remove encryption key
```

**How it works:**
- Key derived via PBKDF2-HMAC-SHA256 (480,000 iterations)
- Stored in OS keychain (macOS Keychain, Linux Secret Service, Windows Credential Locker)
- Encrypted files prefixed with `MERKABA_ENC:`
- Transparent load -- `ConversationLog` auto-detects and decrypts

If the encryption key is unavailable (e.g., on a different machine), encrypted conversations are skipped gracefully rather than erroring.

### Integrity Monitoring

SHA256 file hashes are computed for security-critical source files and compared against a baseline:

```
Core security files monitored:
  security/permissions.py
  security/validation.py
  security/secrets.py
  security/integrity.py
  security/audit.py
  security/scanner.py
```

The `IntegrityReport` tracks three categories:
- **Modified** -- hash changed from baseline
- **Added** -- new files not in baseline
- **Removed** -- baseline files no longer present

Baselines can be regenerated with `SecurityScanner.regenerate_baseline()`.

### Security Scanner

Two scan modes:

**Quick scan** -- runs on agent startup. Checks only core security files against the integrity baseline. Fast.

**Full scan** -- comprehensive check:
1. Integrity check on all `*.py` source files
2. Dependency CVE audit via `pip-audit`
3. Code pattern self-scan (detects dangerous constructs like code execution primitives, deserialization, XSS vectors, shell injection patterns, etc.)

The scanner produces a `SecurityReport` with `integrity_issues`, `cve_issues`, and `code_warnings`. There is currently no CLI command exposed for the scanner -- it runs automatically on startup (quick scan only).

---

## Approval System

Actions above the auto-approve threshold require human approval. The approval system supports multiple interfaces (CLI, Telegram, Web), with optional 2FA and rate limiting.

**Key files:** `approval/queue.py`, `approval/secure.py`, `approval/graduation.py`, `approval/telegram.py`

### Action Queue

The `ActionQueue` stores pending actions in SQLite (`actions.db`):

```bash
merkaba approval list                    # Show pending
merkaba approval approve <id>            # Approve
merkaba approval deny <id> --reason "..."  # Deny with reason
merkaba approval stats                   # Statistics
```

Each action records: business_id, action_type, details, autonomy_level, status (pending/approved/denied), decided_by, timestamp.

### TOTP 2FA

For high-autonomy actions, optional TOTP two-factor authentication adds a second verification layer:

```bash
merkaba security setup-2fa     # Generate and store TOTP secret
merkaba security disable-2fa   # Remove TOTP secret
merkaba security status        # Show 2FA status
```

**Configuration** (`~/.merkaba/config.json`):

```json
{
  "security": {
    "totp_threshold": 3
  }
}
```

Actions with `autonomy_level >= totp_threshold` require a TOTP code. The secret is stored in the OS keychain and works with any TOTP app (Google Authenticator, Authy, etc.).

**Exceptions raised:**
- `TotpRequired` -- TOTP code needed but not provided
- `TotpInvalid` -- TOTP code verification failed
- Both include the action_id for reference

### Rate Limiting

Approval rate limiting prevents automated approval flooding:

```json
{
  "security": {
    "approval_rate_limit": {
      "max_approvals": 5,
      "window_seconds": 60
    }
  }
}
```

If the limit is exceeded, `RateLimitExceeded` is raised. Rate limiting is checked before TOTP verification to prevent DoS on the 2FA system.

### Graduation

The `GraduationChecker` analyzes approval history and suggests which tools should be promoted from "ask" to "notify" mode:

```bash
merkaba approval graduation              # Show graduation suggestions
merkaba approval graduation --business 1 # Per-business
```

**Promotion criteria:**
- At least N consecutive approvals (default: 5)
- Zero denials (zero-tolerance policy)

Example output:

```
Promote 'publish_listing' from ask -> notify? (5 consecutive approvals, 0 denials)
```

A single denial resets the counter and blocks graduation -- the trust model is deliberately strict.

---

## Orchestration

The orchestration layer manages task dispatch, worker execution, and cross-task learning.

**Key files:** `orchestration/supervisor.py`, `orchestration/workers.py`, `orchestration/code_worker.py`, `orchestration/support_worker.py`, `orchestration/integration_worker.py`, `orchestration/explorer.py`, `orchestration/learnings.py`, `orchestration/health.py`, `orchestration/scheduler.py`

### Supervisor & Dispatch Modes

The `Supervisor` is the central coordinator. When a task is due, it:

1. Resolves the worker class from `WORKER_REGISTRY`
2. Selects a dispatch mode
3. Executes the task
4. Stores facts, decisions, and approvals
5. Runs learning extraction
6. Records an episode

**Three dispatch modes:**

| Mode | When Used | Behavior |
|------|-----------|----------|
| `DIRECT` | Default, simple tasks | Single worker execution |
| `EXPLORE_THEN_EXECUTE` | `explore_paths` in payload | Run exploration agent first, inject context, then execute |
| `COMPETITIVE` | Creative tasks (drafting) | Generate N variants, LLM judge picks winner |

**Explicit override:** Set `payload["dispatch_mode"]` to force a mode.

**Model selection** per task type (`~/.merkaba/config.json`):

```json
{
  "models": {
    "task_types": {
      "code": "qwen3.5:122b",
      "support": "qwen3:8b",
      "health_check": "phi4:14b"
    }
  }
}
```

Per-business model overrides via CLI:

```bash
merkaba models set code anthropic:claude-sonnet-4 --business 1
```

**Tool availability** scales with autonomy level:

| Level | Tools Available |
|-------|----------------|
| 1 | file_read, file_list, grep, glob |
| 2 | + web_fetch |
| 3 | + bash |

### Workers

Workers are the execution units for tasks. Every worker inherits from `Worker` and implements `execute(task) -> WorkerResult`:

```python
class WorkerResult:
    success: bool
    output: dict
    error: str | None
    facts_learned: list[dict]      # Auto-stored to memory
    decisions_made: list[dict]     # Auto-stored to memory
    needs_approval: list[dict]     # Auto-routed to approval queue
```

**Built-in workers:**

| Worker | Task Type | Purpose |
|--------|-----------|---------|
| `CodeWorker` | `code` | Code generation with verification |
| `SupportWorker` | `support` | Customer support workflows |
| `IntegrationWorker` | `integration` | Adapter dispatch bridge |
| `MemoryDecayWorker` | `memory_decay` | Scheduled memory cleanup |
| `MemoryConsolidationWorker` | `memory_consolidation` | Scheduled memory summarization |

**Scheduler:**

```bash
merkaba scheduler workers    # Show registered workers
merkaba scheduler run        # Execute one tick
merkaba scheduler start      # Run scheduler loop
merkaba scheduler install    # Install macOS launchd agent
merkaba scheduler remove     # Remove launchd agent
```

The launchd agent runs every 60 seconds. It auto-detects pyenv shims and resolves the real Python binary. Logs go to `~/.merkaba/logs/scheduler.log`.

### Code Worker

The code worker generates code from specifications with a multi-phase pipeline:

```
Phase 1: Snapshot  -> Save current state of target files
Phase 2: Exploration -> (optional) Scout codebase with ExplorationAgent
Phase 3: Generation  -> LLM generates code via tool loop
Phase 4: Verification -> Lint + type-check with DeterministicVerifier
Phase 5: Retry     -> If verification failed, LLM attempts fix with error feedback
Phase 6: Rollback  -> If retry also failed, restore files from snapshot
Phase 7: Review    -> (high-stakes only) Delegate to review worker
```

**CLI:**

```bash
merkaba code run "Add validation" --target src/user.py
merkaba code run "Build parser" --explore src/ --high-stakes
merkaba code review src/user.py --criteria "Check error handling"
merkaba code explore src/orchestration/
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--target` | Pin specific files to modify |
| `--explore` | Scout directories before generation |
| `--high-stakes` | Enable post-generation review; rollback on rejection |

**Auto-rollback:** If verification or review fails, all modified files are restored to their pre-generation state. Files that didn't exist before are deleted.

### Support Worker

A domain worker for customer support workflows with four actions:

| Action | Description | Output |
|--------|-------------|--------|
| `triage_ticket` | LLM classifies priority (low/medium/high/critical) and category | JSON with priority, category, summary |
| `draft_response` | Generates empathetic response using ticket context | JSON with response, tone, follow_up_needed |
| `escalate_ticket` | Routes to approval queue for human review | Pending approval action |
| `analyze_satisfaction` | Analyzes support quality across interactions | JSON with satisfaction_summary, recommendations |

Registered via entry point: `merkaba.workers:support`.

### Integration Worker

Bridges integration adapters into the task pipeline:

```python
# Task payload:
{
    "adapter": "stripe",         # Adapter name
    "action": "get_balance",     # Action to call
    "params": {"currency": "usd"}
}
```

Flow: lookup adapter -> instantiate -> connect -> execute -> disconnect. Results stored as facts (truncated to 500 chars).

### Exploration Agent

Lightweight codebase reconnaissance for pre-task context gathering:

```python
agent = ExplorationAgent()

# Summarize directory structure (depth-limited)
summary = agent.map_directory("src/merkaba/", focus="memory system")

# Analyze a specific file
trace = agent.trace_functionality(
    "src/merkaba/memory/store.py",
    question="How are facts stored?"
)
```

**Constraints:**
- Max directory depth: 2
- Max files per directory: 50
- File preview: 2048 bytes
- Uses small model (`qwen3:4b`) for summaries

The `ExplorationOrchestrator` runs multiple agents in parallel across partitions (files/directories) and aggregates results.

**CLI:**

```bash
merkaba code explore src/orchestration/
```

### Learning Extractor

Automatically extracts generalizable insights from completed tasks:

**Rule-based extraction** (per task):
- Detects failure patterns from task errors
- Stores with 40% confidence baseline
- Deduplicates against existing learnings

**LLM-based extraction** (batched):
- Triggers every N completed tasks (default: 10)
- Summarizes accumulated task results
- LLM identifies cross-task patterns
- Higher confidence (varies)

Learnings are stored globally (not business-scoped) so insights from one business benefit others.

### Health Checks

`SystemHealthMonitor` runs diagnostic checks:

| Check | What It Tests | Failure Threshold |
|-------|---------------|-------------------|
| `check_ollama()` | HTTP GET to Ollama API | Connection timeout (5s) |
| `check_db(name)` | SQLite `PRAGMA integrity_check` | Non-"ok" result |
| `check_chromadb()` | ChromaDB client creation | Import/connection error (ok if not installed) |
| `check_disk_space()` | `shutil.disk_usage()` | > 90% disk usage |

```python
monitor = SystemHealthMonitor()
report = monitor.check_all()  # Checks: ollama, tasks.db, memory.db, chromadb, disk
print(report.healthy)  # True if all pass
```

Currently no CLI command is exposed for health checks -- they run internally during agent startup and scheduled health check tasks.

---

## LLM Client

The LLM client manages model communication with priority queuing, retry logic, and fallback chains.

**Key files:** `llm.py`, `llm_providers/`

### Request Priority

Every LLM request has a priority level:

| Priority | Level | Used By |
|----------|-------|---------|
| `INTERACTIVE` | 0 (highest) | User-facing chat responses |
| `APPROVAL` | 1 | Approval flow decisions |
| `SCHEDULED` | 2 | Orchestration tasks |
| `BACKGROUND` | 3 (lowest) | Learning extraction, episodes, memory updates |

Higher-priority requests are served first when the GPU is busy.

### Concurrency Gate

The `LLMGate` prevents GPU thrashing on single-GPU machines:

- **Max concurrent requests:** 2 (configurable)
- **Priority queue:** Heapq with monotonic counter for FIFO within same priority
- **Queue depth warning:** Logged when queue exceeds threshold (default: 5)
- **Gate holds through retries:** A single request holds its slot for the entire retry cycle

**Configuration** (`~/.merkaba/config.json`):

```json
{
  "rate_limiting": {
    "max_concurrent": 2,
    "queue_depth_warning": 5
  }
}
```

### Retry & Fallback Chains

**Retry** (`chat_with_retry`):
- Retries on: `ConnectionError`, `ollama.ResponseError`, cloud provider errors
- Does NOT retry on: `ollama.RequestError` (bad model name -- no point retrying)
- Exponential backoff: `delay = base_delay * (2 ^ attempt)`, capped at `max_delay`
- Default: 3 retries, 1s base delay, 30s max delay

**Fallback chains** (`chat_with_fallback`):
- If primary model fails all retries, try next model in the chain
- Records `model_fallback` decision to audit trail
- Raises `AllModelsUnavailableError` if entire chain exhausted

**Configuration:**

```json
{
  "models": {
    "fallback_chains": {
      "complex": {
        "primary": "qwen3.5:122b",
        "fallbacks": ["qwen3:8b", "anthropic:claude-sonnet-4-20250514"],
        "timeout": 120.0
      },
      "simple": {
        "primary": "qwen3:8b",
        "fallbacks": ["qwen3:4b", "openai:gpt-4o-mini"],
        "timeout": 30.0
      }
    }
  }
}
```

### Provider Routing

Model names with a provider prefix are routed to cloud providers:

| Prefix | Provider |
|--------|----------|
| `anthropic:` | Anthropic Claude API |
| `openai:` | OpenAI API |
| `openrouter:` | OpenRouter (OpenAI-compatible) |
| No prefix | Ollama (local) |

```bash
merkaba chat -m anthropic:claude-sonnet-4-20250514 "Hello"
merkaba chat -m openrouter:google/gemini-2.5-pro "Hello"
merkaba models providers  # Show cloud provider status
```

---

## Verification

### Deterministic Verifier

After code generation, the `DeterministicVerifier` runs language-appropriate linters and type checkers:

| Language | Checks |
|----------|--------|
| Python (`.py`) | `ruff check`, `mypy` |
| JavaScript (`.js`, `.jsx`) | `npx eslint` |
| TypeScript (`.ts`, `.tsx`) | `npx eslint`, `npx tsc --noEmit` |

**Behavior:**
- Gracefully skips unavailable tools (e.g., if `ruff` isn't installed)
- 30-second timeout per check
- Returns `VerificationResult` with per-check pass/fail and combined summary
- Returns `None` if disabled or no checks exist for the file type

The code worker uses verification results to decide whether to retry, rollback, or proceed.

---

## Plugin System

Merkaba's plugin system supports four component types: skills, commands, hooks, and agents.

**Key files:** `plugins/registry.py`, `plugins/skills.py`, `plugins/commands.py`, `plugins/hooks.py`, `plugins/agents.py`, `plugins/sandbox.py`, `plugins/importer.py`

### Plugin Registry

The `PluginRegistry` loads plugins from two directories:

1. `~/.claude/plugins/cache` -- Claude Code plugins
2. `~/.merkaba/plugins` -- Merkaba-native plugins

It also loads global skill context from `~/.merkaba/skill-context.md`.

```bash
merkaba plugins list       # List all installed plugins
merkaba plugins inspect <name>  # Show plugin details
```

### Skills

Skills are markdown files with YAML frontmatter that inject instructions into the agent's system prompt:

```markdown
---
name: python-expert
description: Expert Python coding assistance
permission_tier: SAFE
required_tools:
  - file_read
  - file_write
max_context_tokens: 4000
---
You are an expert Python developer. Follow PEP 8, use type hints...
```

**Directory structure:**

```
~/.merkaba/plugins/
  my-plugin/
    skills/
      python-expert/
        SKILL.md
      debugging/
        SKILL.md
```

**Skill matching:** The `SkillManager.match()` method finds skills by keyword matching on descriptions. Built-in keyword mappings:
- "design", "feature", "create", "build" -> brainstorming
- "tdd", "test first" -> test-driven-development
- "debug", "bug", "fix" -> systematic-debugging
- "plan", "implementation plan" -> writing-plans

**Security scanning:** All skills are scanned for dangerous patterns on load (shell injection, code execution primitives, XSS vectors, deserialization risks, etc.). Warnings are attached to the skill but don't block loading.

### Commands

Commands are markdown files in the `commands/` subdirectory:

```
my-plugin/
  commands/
    generate.md
    review.md
```

```bash
merkaba commands list  # List plugin commands
```

### Hooks

Hooks subscribe to lifecycle events:

| Event | When Fired |
|-------|------------|
| `session-start` | Session initialization |
| `pre-message` | Before message processing |
| `post-message` | After message processing |
| `pre-tool` | Before tool execution |
| `post-tool` | After tool execution |
| `file-changed` | File system change detected |

**Hook file format:**

```markdown
---
name: log-messages
event: pre-message
---
Log all incoming messages to the audit trail...
```

**Directory structure:**

```
my-plugin/
  hooks/
    log-messages.md
    validate-output.md
```

### Agents

Agent configurations define LLM-powered sub-agents:

```markdown
---
name: research-agent
description: Deep research on technical topics
model: qwen3.5:122b
max_iterations: 10
---
You are a research agent. Search thoroughly, cite sources...
```

```
my-plugin/
  agents/
    research-agent.md
```

### Sandbox & Manifests

Plugins declare their permissions in YAML frontmatter (the **manifest**):

| Field | Default | Description |
|-------|---------|-------------|
| `required_tools` | `[]` | Tools the plugin can call |
| `required_integrations` | `[]` | External integrations needed |
| `file_access` | `[]` | Glob patterns for allowed paths |
| `max_context_tokens` | 4000 | Token budget |
| `permission_tier` | `MODERATE` | Required permission level |

The `PluginSandbox` enforces these at runtime:
- **Tool access:** Only declared tools can be called
- **Path access:** File tools check paths against the manifest allowlist
- **Protected paths:** Always blocked regardless of manifest:
  - `**/merkaba/security/*`
  - `**/merkaba/approval/*`
  - `**/.merkaba/config.json`
  - `**/.merkaba/memory.db`
  - `**/.merkaba/actions.db`
  - `**/.merkaba/tasks.db`

### Importing from Claude Code

Merkaba can import and convert Claude Code plugins:

```bash
merkaba plugins import <plugin:skill>        # Import a specific skill
merkaba plugins import <plugin> --all        # Import all skills from a plugin
merkaba plugins import <plugin> --force      # Force import low-compatibility skills
merkaba plugins available                    # List available Claude Code plugins
```

**Import pipeline:**
1. Find skill in `~/.claude/plugins/cache`
2. Analyze compatibility (score 0-100)
3. Identify missing tools
4. Choose conversion strategy:
   - **RULE_BASED** -- direct text transformation
   - **LLM_ASSISTED** -- LLM rewrites incompatible sections
   - **SKIP** -- too incompatible (unless `--force`)
5. Convert and write to `~/.merkaba/plugins/`

**Metadata added to imported skills:**
- `imported_from` -- source plugin name
- `compatibility` -- score at import time
- `conversion` -- method used (rule_based or llm_assisted)

### Skill Activation

Skills can be activated at runtime to inject their content into the agent's system prompt:

```python
agent.activate_skill("python-expert")   # Enable skill
# Next agent.run() call includes skill content in system prompt
agent.deactivate_skill()                # Disable
```

When active, the skill content is prepended to the system prompt before every LLM call.

---

## Extension System

Merkaba uses Python entry points for zero-configuration extension discovery.

**Key file:** `extensions.py`

### Entry Points

Three entry point groups:

| Group | Purpose | Registration |
|-------|---------|-------------|
| `merkaba.workers` | Custom task workers | `register_worker(name, class)` |
| `merkaba.adapters` | Integration adapters | `register_adapter(name, class)` |
| `merkaba.cli` | CLI subcommands | Returned as Typer apps |

### Custom Workers

In your package's `pyproject.toml`:

```toml
[project.entry-points."merkaba.workers"]
analytics = "my_package.workers:AnalyticsWorker"
```

```python
# my_package/workers.py
from merkaba.orchestration.workers import Worker, WorkerResult

class AnalyticsWorker(Worker):
    def execute(self, task: dict) -> WorkerResult:
        prompt = task.get("prompt", "")
        response = self._ask_llm(prompt)
        return WorkerResult(success=True, output={"response": response})
```

Workers are discovered automatically on startup -- no code changes to Merkaba needed.

### Custom Adapters

```toml
[project.entry-points."merkaba.adapters"]
shopify = "my_package.adapters:ShopifyAdapter"
```

```python
# my_package/adapters.py
from merkaba.integrations.base import IntegrationAdapter

class ShopifyAdapter(IntegrationAdapter):
    def connect(self) -> bool:
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        return {"status": "ok"}

    def health_check(self) -> dict:
        return {"healthy": self.is_connected}
```

### Custom CLI Commands

```toml
[project.entry-points."merkaba.cli"]
generate = "my_package.cli:generate_app"
```

```python
# my_package/cli.py
import typer
generate_app = typer.Typer()

@generate_app.command()
def listing(name: str):
    """Generate a listing."""
    typer.echo(f"Generating: {name}")
```

This exposes `merkaba generate listing "My Product"` without modifying Merkaba's CLI.

**Error handling:** Entry point load failures are logged as warnings and skipped -- a broken extension never prevents Merkaba from starting.

---

## Observability

**Key files:** `observability/audit.py`, `observability/tokens.py`, `observability/tracing.py`

### Decision Audit Trail

Every significant decision is recorded in the `decision_audit` table:

| Field | Description |
|-------|-------------|
| `id` | UUID |
| `trace_id` | Links to request execution context |
| `decision_type` | e.g., `dispatch_mode`, `model_fallback`, `competition_winner`, `2fa_approval` |
| `decision` | The decision made |
| `alternatives` | JSON array of other options considered |
| `context_summary` | Why this decision was made |
| `model` | Which LLM made the decision (if applicable) |
| `confidence` | 0.0-1.0 confidence score |
| `timestamp` | UTC ISO format |

**CLI:**

```bash
merkaba observe audit                    # Recent decisions
merkaba observe trace <trace_id>         # All decisions for a trace
```

All audit recording is fire-and-forget -- exceptions never propagate to the caller.

### Token Usage Tracking

LLM token consumption is tracked per call:

| Field | Description |
|-------|-------------|
| `model` | Model used |
| `worker_type` | Which worker made the call |
| `input_tokens` / `output_tokens` | Token counts |
| `duration_ms` | Call duration |
| `trace_id` | Links to request context |

**CLI:**

```bash
merkaba observe tokens                          # Usage summary (last 7 days)
merkaba observe tokens --group-by model         # Group by model
merkaba observe tokens --group-by worker_type   # Group by worker
```

Summary includes: call count, total input/output tokens, total duration, grouped by the selected dimension.

### Tracing

Trace IDs are generated per request and threaded through all subsystems (LLM calls, decisions, token records). Use `merkaba observe trace <id>` to cross-reference everything that happened during a single request.

---

## Web Dashboard

### API Authentication

The web dashboard supports optional API key authentication:

```json
{
  "api_key": "your-secret-key"
}
```

Set this in `~/.merkaba/config.json`. When configured, all API requests must include the key. When not set, the dashboard is open (suitable for local-only use).

---

## State Table

The `state` table provides per-entity key-value storage:

```python
store.set_state(
    business_id=1,
    entity_type="customer",
    entity_id="alice",
    key="last_contact",
    value="2026-03-01",
)

states = store.get_state(business_id=1, entity_type="customer")
```

Uses UPSERT -- setting the same key again updates it. Ordered by `updated_at DESC`.

---

## Per-Business Configuration

Each business can have its own personality and context:

```
~/.merkaba/businesses/
  1/
    SOUL.md    # Business-specific agent personality
    USER.md    # Business-specific owner context
```

**Prompt resolution chain:** Business-specific > Global (`~/.merkaba/SOUL.md`) > Built-in default.

```bash
merkaba config edit-soul                 # Edit global SOUL.md
merkaba config edit-soul --business 1    # Edit business-specific
merkaba config edit-user --business 1    # Edit business-specific USER.md
merkaba config show-prompt               # Show resolved prompt chain
```

Uses `$EDITOR` environment variable (falls back to `nano`).
