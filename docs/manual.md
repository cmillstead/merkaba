# Merkaba Manual

This manual covers Merkaba's subsystems in depth. For installation, quickstart, and configuration basics, see the [README](../README.md). For architecture overview, see [architecture.md](architecture.md).

---

## Table of Contents

1. [Onboarding](#onboarding)
   - [Preflight (Phase 1)](#preflight-phase-1)
   - [Interview (Phase 2)](#interview-phase-2)
   - [Extras (Phase 3)](#extras-phase-3)
   - [Re-running Init](#re-running-init)
   - [First-Run Nudge](#first-run-nudge)
2. [Memory System](#memory-system)
   - [Retrieval Pipeline](#retrieval-pipeline)
   - [Conversation Trees](#conversation-trees)
   - [Contradiction Detection](#contradiction-detection)
   - [Memory Lifecycle](#memory-lifecycle)
   - [Episodic Memory](#episodic-memory)
   - [Relationship Graph](#relationship-graph)
   - [Archived Memory](#archived-memory)
   - [Session Extraction](#session-extraction)
   - [Vector Memory](#vector-memory)
3. [Security](#security)
   - [Input Classifier](#input-classifier)
   - [Argument Validation](#argument-validation)
   - [Memory Sanitization](#memory-sanitization)
   - [Permission Tiers](#permission-tiers)
   - [Conversation Encryption](#conversation-encryption)
   - [Integrity Monitoring](#integrity-monitoring)
   - [Security Scanner](#security-scanner)
4. [Approval System](#approval-system)
   - [Action Queue](#action-queue)
   - [TOTP 2FA](#totp-2fa)
   - [Rate Limiting](#rate-limiting)
   - [Graduation](#graduation)
5. [Orchestration](#orchestration)
   - [Supervisor & Dispatch Modes](#supervisor--dispatch-modes)
   - [Workers](#workers)
   - [Code Worker](#code-worker)
   - [Support Worker](#support-worker)
   - [Integration Worker](#integration-worker)
   - [Exploration Agent](#exploration-agent)
   - [Learning Extractor](#learning-extractor)
   - [Health Checks](#health-checks)
   - See also: [Session Management](#session-management), [Message Interruption](#message-interruption), [Heartbeat Checklist](#heartbeat-checklist)
6. [LLM Client](#llm-client)
   - [Request Priority](#request-priority)
   - [Concurrency Gate](#concurrency-gate)
   - [Retry & Fallback Chains](#retry--fallback-chains)
   - [Provider Routing](#provider-routing)
7. [Verification](#verification)
   - [Deterministic Verifier](#deterministic-verifier)
8. [Plugin System](#plugin-system)
   - [Plugin Registry](#plugin-registry)
   - [Skills](#skills)
   - [Commands](#commands)
   - [Hooks](#hooks)
   - [Agents](#agents)
   - [Sandbox & Manifests](#sandbox--manifests)
   - [Importing from Claude Code](#importing-from-claude-code)
   - [Skill Activation](#skill-activation)
9. [Extension System](#extension-system)
   - [Entry Points](#entry-points)
   - [Custom Workers](#custom-workers)
   - [Custom Adapters](#custom-adapters)
   - [Custom CLI Commands](#custom-cli-commands)
10. [Observability](#observability)
    - [Decision Audit Trail](#decision-audit-trail)
    - [Token Usage Tracking](#token-usage-tracking)
    - [Tracing](#tracing)
11. [Web Dashboard](#web-dashboard)
    - [API Authentication](#api-authentication)
12. [Session Management](#session-management)
    - [Session IDs](#session-ids)
    - [SessionPool](#sessionpool)
    - [LaneQueue](#lanequeue)
13. [Context Window Management](#context-window-management)
    - [Token Estimation](#token-estimation)
    - [Tool Result Trimming](#tool-result-trimming)
    - [Automatic Compression](#automatic-compression)
14. [Hot-Reloadable Configuration](#hot-reloadable-configuration)
15. [Message Interruption](#message-interruption)
16. [Startup Configuration Warnings](#startup-configuration-warnings)
17. [Browser Automation](#browser-automation)
18. [Channel Adapters](#channel-adapters)
    - [Discord](#discord)
    - [Slack Real-Time](#slack-real-time)
    - [Signal](#signal)
19. [Gateway Pairing](#gateway-pairing)
20. [Heartbeat Checklist](#heartbeat-checklist)
21. [Message Chunking](#message-chunking)
22. [Migration & Identity Portability](#migration--identity-portability)
    - [OpenClaw Migration](#openclaw-migration)
    - [AIEOS Import/Export](#aieos-importexport)
23. [Protocol Definitions](#protocol-definitions)

---

## Onboarding

The `merkaba init` command runs a layered setup wizard that prepares the `~/.merkaba/` directory, optionally conducts an LLM-driven interview to personalize the agent, and offers to install optional extras. It is the recommended first step after installing Merkaba.

**Key file:** `init.py`

```bash
merkaba init                    # Full wizard (preflight + interview + extras)
merkaba init --no-interview     # Skip the LLM interview, just seed defaults
merkaba init --force            # Back up and overwrite user-edited files
```

### Preflight (Phase 1)

Preflight always runs and handles the foundational setup:

1. **Create directories** -- `~/.merkaba/logs/`, `conversations/`, `plugins/`
2. **Seed `config.json`** -- default model routing (`qwen3:8b` for simple, `qwen3.5:122b` for complex)
3. **Seed `SOUL.md`** -- global agent personality (built-in default)
4. **Seed `USER.md`** -- global owner context (built-in default)
5. **Check Ollama** -- queries `http://127.0.0.1:11434/api/tags` for availability
6. **Model inventory** -- reports which of the three standard models are installed

**Model roles:**

| Role | Default Model | Purpose |
|------|--------------|---------|
| Simple | `qwen3:8b` | Fast responses, routing, classification |
| Complex | `qwen3.5:122b` | Deep reasoning, tool use, long tasks |
| Classifier | `qwen3:4b` | Safety checks, complexity routing |

If `qwen3:8b` is missing and Ollama is running, init offers to pull it automatically (~5GB). Larger models are listed as manual `ollama pull` commands.

**File safety:** When a file already exists and has been edited (content differs from the default), init asks what to do:

- **Overwrite** -- replace with the new default
- **Skip** -- leave the existing file untouched
- **Backup** -- copy the original to `<filename>.bak`, then overwrite

The `--force` flag automatically backs up and overwrites without prompting.

### Interview (Phase 2)

If Ollama is available and at least one model is installed, init offers an LLM-driven interview to personalize `SOUL.md` and `USER.md`. The interview is skipped when `--no-interview` is passed or when no LLM is available.

**Three depth levels:**

| Level | Questions | Topics |
|-------|-----------|--------|
| Quick | 3-4 | Name, what you're building, what you want help with |
| Medium | 5-8 | + communication style, schedule/timezone, pushback preferences |
| Deep | 8-12 | + values, decision-making style, pet peeves, long-term vision |

The interview is conversational -- the LLM asks one question at a time and adapts follow-ups based on answers. When all topics are covered, the LLM signals completion and synthesizes two personalized documents:

- **SOUL.md** -- agent personality tailored to the user (tone, priorities, style)
- **USER.md** -- owner profile (who they are, what they're building, preferences)

The generated documents are shown for review before saving. If declined, the defaults from Phase 1 are kept.

### Extras (Phase 3)

After setup, init offers three optional add-ons:

- **Background scheduler** -- installs a macOS launchd daemon (`merkaba scheduler install`)
- **Telegram bot** -- runs the Telegram setup wizard (`merkaba telegram setup`)
- **Web UI** -- launches the Mission Control dashboard

Each extra is a yes/no prompt. All are optional and can be set up independently later.

### Re-running Init

Running `merkaba init` again is safe and useful for:

- **Re-personalizing** after your goals or preferences change
- **Picking up missing models** that you've pulled since the first run
- **Adding extras** you skipped initially

Without `--force`, init will detect user-edited files and ask before overwriting. The interview can be re-run to generate fresh `SOUL.md` and `USER.md` based on a new conversation.

### First-Run Nudge

If `~/.merkaba/config.json` does not exist, Merkaba prints a one-time suggestion when the memory store initializes:

```
  Welcome to Merkaba! Run `merkaba init` to set up your agent.
```

This nudge appears at most once per process and only when no configuration has been created yet. Running `merkaba init` (or manually creating `config.json`) suppresses it permanently.

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

The scanner produces a `SecurityReport` with `integrity_issues`, `cve_issues`, and `code_warnings`. Quick scan runs automatically on agent startup; both modes are available via CLI:

```bash
merkaba security scan                        # Quick scan (core security files only)
merkaba security scan --full                 # Full scan (integrity + CVE + code patterns)
merkaba security scan --regenerate-baseline  # Regenerate integrity baseline
```

The scan command exits with code 1 when issues are found, making it suitable for CI pipelines.

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

## Skill Forge

Generate merkaba plugins from ClawHub or GitHub skill descriptions. No code is imported -- only the concept is extracted and the LLM generates fresh, merkaba-native content from scratch.

**Key file:** `plugins/forge.py`

### Why Forge?

ClawHub's skill store contains useful concepts but also prompt injections and AI malware. Forge lets you safely adopt skill ideas without importing untrusted code.

### Usage

```bash
# From GitHub
merkaba skills forge --from https://github.com/user/repo/blob/main/skills/my-skill/SKILL.md

# From ClawHub
merkaba skills forge --from https://clawhub.ai/skills/my-skill

# Custom name
merkaba skills forge --from <url> --name my-custom-name

# Force past security warnings
merkaba skills forge --from <url> --force
```

### How It Works

1. **Scrape**: Fetches skill description from URL (httpx first, Playwright fallback for JS-rendered ClawHub pages)
2. **Security gate**: Checks ClawHub security verdict -- Benign passes, Suspicious warns, Malicious double-warns
3. **Generate**: LLM creates a fresh merkaba plugin inspired by the concept (no source code imported)
4. **Scan**: Output checked against `DANGEROUS_SKILL_PATTERNS` before writing
5. **Write**: Plugin saved to `~/.merkaba/plugins/<name>/skills/<name>/SKILL.md`

### Security

- **ClawHub verdicts**: Benign passes, Suspicious warns with confirmation, Malicious requires `--force`
- **Post-generation scan**: All output scanned against `DANGEROUS_SKILL_PATTERNS`
- **No code imported**: Only the skill description is read; the LLM generates from scratch

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
merkaba plugins list             # List all installed plugins
merkaba plugins available        # List available plugins to import
merkaba plugins import <ref>     # Import a Claude Code plugin skill
merkaba plugins inspect <name>   # Show plugin details
merkaba plugins uninstall <name> # Uninstall a plugin
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

---

## Session Management

Multi-channel sessions are managed through `SessionPool` and `LaneQueue`, providing per-session Agent lifecycle management with async boundaries.

**Key files:** `orchestration/session.py`, `orchestration/session_pool.py`, `orchestration/lane_queue.py`

### Session IDs

Session IDs follow a scoped format that prevents context bleeding across topics:

```
channel:sender_id[:topic:topic_id][:biz:business_id]
```

Examples:
- `telegram:12345` -- Telegram user 12345, no topic scoping
- `discord:67890:topic:channel_42` -- Discord user in a specific channel
- `cli:local` -- CLI sessions (always trusted, bypass pairing)

```python
from merkaba.orchestration.session import build_session_id

sid = build_session_id("discord", "67890", topic_id="channel_42", business_id="1")
# -> "discord:67890:topic:channel_42:biz:1"
```

### SessionPool

`SessionPool` manages Agent instances per session with configurable limits:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_sessions` | 100 | Maximum concurrent sessions (LRU eviction at capacity) |
| `idle_timeout` | 3600.0 | Seconds before idle session is evicted |
| `agent_kwargs` | `{}` | Keyword arguments passed to `Agent()` constructor |
| `pairing` | `None` | Optional `GatewayPairing` instance for channel auth |

```python
from merkaba.orchestration.session_pool import SessionPool

pool = SessionPool(max_sessions=50, idle_timeout=1800)

# Sync usage (from a thread)
response = pool.submit_sync("telegram:12345", "Hello")

# Async usage (from web/telegram handler)
response = await pool.submit("telegram:12345", "Hello")

# Periodic cleanup
pool.evict_idle()
```

When a new session arrives and the pool is at capacity, the least-recently-used session is evicted. Non-CLI sessions are gated behind gateway pairing if a `GatewayPairing` instance is configured.

### LaneQueue

`LaneQueue` provides per-session serial execution with cross-session concurrency:

- Each `session_id` gets its own `threading.Lock`
- Messages within a session execute one at a time (serial)
- Messages across different sessions execute concurrently
- `submit()` wraps sync execution via `asyncio.to_thread()` for the async boundary

This fixes Telegram event loop blocking -- the sync `Agent.run()` runs in a worker thread while the event loop remains responsive.

---

## Context Window Management

Automatic context window management prevents token limit errors by compressing conversation history when utilization reaches a configurable threshold.

**Key files:** `memory/context_budget.py`, `memory/compression.py`

### Token Estimation

Token counting uses a ~4 chars/token heuristic (sufficient for threshold detection, not billing):

```python
from merkaba.memory.context_budget import estimate_tokens, ContextBudget

tokens = estimate_tokens("Hello, world!")  # -> 3

budget = ContextBudget(
    max_total_tokens=128000,
    system_prompt_tokens=2000,
    tool_definitions_tokens=3000,
    conversation_history_tokens=50000,
)
print(budget.utilization)         # -> ~0.43
print(budget.available_for_history)  # -> remaining tokens for history
```

### Tool Result Trimming

In `Agent._format_conversation()`, tool results exceeding 4000 characters are trimmed to head + tail with a `[trimmed]` marker:

```
[First 1500 chars]
[... trimmed 12000 chars ...]
[Last 1500 chars]
```

This prevents a single large tool result from consuming the entire context window.

### Automatic Compression

When conversation utilization exceeds 80% of `max_context_tokens`, the agent automatically compresses older conversation turns:

1. Pre-compression: extract facts and relationships to `MemoryStore` (preserving information)
2. Group conversation into turns (user message + all responses until next user message)
3. Prune older turns, keeping the most recent 10
4. Inject a `[context optimized]` summary node before the kept turns

**Configuration** (`ContextWindowConfig`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_context_tokens` | 128000 | Context window size for the model |
| `head_chars` | 1500 | Characters to keep from start of trimmed tool results |
| `tail_chars` | 1500 | Characters to keep from end of trimmed tool results |
| `compaction_threshold` | 0.80 | Utilization fraction that triggers compression |

---

## Hot-Reloadable Configuration

`HotConfig` checks `config.json` file mtime on every `get()` call. If the file has been modified, it re-reads and applies changes immediately.

**Key file:** `config/hot_reload.py`

```python
from merkaba.config.hot_reload import HotConfig

config = HotConfig("~/.merkaba/config.json")

# Auto-reloads if file changed since last read
model = config.get("models", {})

# Register change callbacks
def on_change(changed_keys, old_data, new_data):
    print(f"Config keys changed: {changed_keys}")

config.on_change(on_change)
```

**Thread safety:** Double-checked locking pattern -- the fast path (mtime unchanged) is lock-free. Only actual reloads acquire the lock.

**Security keys** (`api_key`, `encryption_key`, `permissions`, `auto_approve_level`, etc.) log a warning when changed at runtime:

```
WARNING merkaba.config: Security-relevant config changed: api_key, auto_approve_level.
Restart recommended to confirm these changes.
```

The new values are still loaded immediately -- the warning is advisory.

---

## Message Interruption

The interruption system allows users to redirect or cancel the agent while it is processing a response.

**Key file:** `orchestration/interruption.py`

**Three modes:**

| Mode | Behavior | Use Case |
|------|----------|----------|
| `APPEND` | Queue behind current response (default) | Follow-up message |
| `STEER` | Inject at next tool boundary | "Actually, do X instead" |
| `CANCEL` | Abort current response | "Stop, never mind" |

```python
from merkaba.orchestration.interruption import InterruptionManager, InterruptionMode

mgr = InterruptionManager(default_mode=InterruptionMode.APPEND)

# From async boundary (web/telegram handler)
mgr.interrupt("session:123", "Do this instead", InterruptionMode.STEER)

# From sync agent loop (at tool boundaries)
event = mgr.check_urgent("session:123")  # Returns STEER/CANCEL only
if event and event.mode == InterruptionMode.CANCEL:
    return partial_response

# Peek without consuming
if mgr.has_cancel("session:123"):
    # Abort early
    pass
```

The agent checks for interruptions in `_execute_tools()` between tool calls. APPEND events are not consumed at tool boundaries -- they wait until the current response completes.

---

## Startup Configuration Warnings

`validate_config()` runs at CLI and web startup, surfacing issues with severity levels:

**Key file:** `config/validation.py`

| Severity | Meaning | Example |
|----------|---------|---------|
| `ERROR` | Blocks functionality | Ollama not reachable |
| `WARNING` | Degraded mode | ChromaDB not installed, incomplete model routing |
| `INFO` | Advisory | Configuration notes |

**Checks performed:**
- Model routing completeness (simple + complex models set)
- Auto-approve level safety (warns if DESTRUCTIVE)
- Business prompt completeness (SOUL.md per business)
- Ollama connectivity
- ChromaDB availability

Clean configurations produce no output. Issues are printed grouped by severity at startup.

---

## Browser Automation

Headless browser control via Playwright with semantic snapshots instead of screenshots.

**Key file:** `tools/builtin/browser.py`

**Setup:**

```bash
pip install merkaba[browser]              # Installs playwright
python -m playwright install chromium     # Download browser
```

**Tools:**

| Tool | Permission | Description |
|------|-----------|-------------|
| `browser_open` | SENSITIVE | Open URL, return accessibility tree snapshot |
| `browser_snapshot` | MODERATE | Snapshot current page (re-read after actions) |
| `browser_click` | SENSITIVE | Click by `role:name` (e.g., `button:Submit`) or CSS selector |
| `browser_fill` | SENSITIVE | Fill form field by label, placeholder, or CSS selector |
| `browser_navigate` | SENSITIVE | Navigate to new URL in same session |
| `browser_close` | SAFE | Close browser, free resources |

**Semantic snapshots** convert the page's accessibility tree into structured text:

```
[heading (level 1)] "Welcome"
  [navigation] "Main"
    [link] "Home"
    [link] "About"
  [textbox] "Search" value=
  [button] "Submit"
```

This is ~50KB vs ~5MB for a screenshot, and gives the LLM structured, actionable element information. SSRF protection reuses the same URL validation as `web_fetch`.

---

## Channel Adapters

### Discord

Uses `discord.py` with bot token authentication. Routes messages through `SessionPool` for per-user session management.

**Key file:** `integrations/discord_adapter.py`

**Setup:** `pip install discord.py`, store bot token via `CredentialManager`.

**Actions:** `send_message`, `read_messages`, `list_channels`

```python
adapter = DiscordAdapter()
adapter.connect()
adapter.setup_message_handler(pool=session_pool)
adapter.run()  # Blocking — starts the event loop
```

### Slack Real-Time

Extended with Bolt socket mode for real-time event handling and Block Kit approval UI.

**Key file:** `integrations/slack_adapter.py`

**Setup:** `pip install slack-bolt`, store `bot_token` + `app_token` (for Socket Mode).

**New features over base Slack adapter:**
- Real-time message handling via Bolt socket mode
- Block Kit approval buttons (Approve/Deny with action IDs)
- Message routing through SessionPool

**Actions:** `send_message`, `read_messages`, `list_channels`, `send_approval_request`

### Signal

Signal messaging via `signal-cli` JSON-RPC subprocess.

**Key file:** `integrations/signal_adapter.py`

**Setup:** Install [signal-cli](https://github.com/AsamK/signal-cli), register an account. Store `account` (phone number) via `CredentialManager`.

**Actions:** `send_message`, `read_messages`, `list_groups`, `get_contacts`

The adapter communicates with signal-cli by piping JSON-RPC requests through subprocess stdin/stdout. Supports both individual and group messaging.

---

## Gateway Pairing

New channel connections are authenticated via a one-time 6-character code. CLI sessions are always trusted and bypass pairing.

**Key file:** `security/pairing.py`

**Flow:**

```
1. User runs: merkaba pair initiate discord user:67890
   -> Returns code: "A3F7B2"

2. User enters code on Discord: /pair A3F7B2
   -> GatewayPairing.confirm() with constant-time comparison
   -> Identity "discord:67890" is now paired

3. Future messages from discord:67890 are processed normally
```

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `expiry_seconds` | 300.0 | Code expiration time (5 minutes) |

**CLI:**

```bash
merkaba pair list                         # List paired identities
merkaba pair initiate <channel> <identity> # Generate pairing code
merkaba pair confirm <identity> <code>    # Confirm code
merkaba pair revoke <identity>            # Revoke pairing
```

Unpaired non-CLI sessions receive a prompt directing the user to pair via CLI.

---

## Heartbeat Checklist

User-editable `HEARTBEAT.md` files define recurring tasks in checkbox format. The scheduler parses and executes unchecked items on each tick.

**Key file:** `orchestration/heartbeat_checklist.py`

**Format:**

```markdown
- [ ] Check email inbox (every 30m)
- [ ] Review pending approvals (hourly)
- [x] Daily backup (daily)
- [ ] Weekly analytics report (weekly)
```

**Supported schedules:** `every 30m`, `every 1h`, `hourly`, `daily`, `weekly`

Items marked `[x]` are skipped. The scheduler tracks the file's mtime and re-parses on change (hot-reloadable).

**Location:** `~/.merkaba/HEARTBEAT.md` (global) or `~/.merkaba/businesses/{id}/HEARTBEAT.md` (per-business).

---

## Message Chunking

Long agent responses are split at natural boundaries before delivery to channels with character limits.

**Key file:** `integrations/delivery.py`

**Channel limits:**

| Channel | Max Characters |
|---------|---------------|
| Discord | 2,000 |
| Slack | 4,000 |
| Telegram | 4,096 |
| Signal | 4,096 |
| Web/CLI | 100,000 (effectively unlimited) |

**Split priority:**
1. Paragraph boundaries (double newline)
2. Line boundaries (single newline)
3. Sentence boundaries (period + space)
4. Word boundaries (space)
5. Hard split at limit (last resort)

Code blocks (`` ``` ``) are kept together if they fit within a single chunk.

```python
from merkaba.integrations.delivery import chunk_message, CHANNEL_LIMITS

chunks = chunk_message(long_response, max_chars=CHANNEL_LIMITS["discord"])
for chunk in chunks:
    await send(chunk)
```

---

## Migration & Identity Portability

### OpenClaw Migration

Imports OpenClaw workspaces into Merkaba business directories.

**Key file:** `plugins/importer_openclaw.py`

**File mapping:**

| OpenClaw File | Merkaba Destination | Action |
|---------------|---------------------|--------|
| `SOUL.md` | `businesses/{name}/SOUL.md` | Direct copy |
| `USER.md` | `businesses/{name}/USER.md` | Direct copy |
| `HEARTBEAT.md` | `businesses/{name}/HEARTBEAT.md` | Direct copy |
| `AGENTS.md` | `businesses/{name}/.imported/` | Stash only |
| `TOOLS.md` | `businesses/{name}/.imported/` | Stash only |
| `IDENTITY.md` | `businesses/{name}/.imported/` | Stash only |

All originals are also stashed in `.imported/` for lossless round-trip reference.

**CLI:**

```bash
merkaba migrate openclaw /path/to/workspace --name "My Business"
```

### AIEOS Import/Export

AIEOS v1.1 is an identity format used by other agent frameworks. Merkaba can import AIEOS JSON into `SOUL.md` format and export back.

**Key file:** `identity/aieos.py`

**Import:** Parses AIEOS JSON (identity, psychology, linguistics, motivations, capabilities) and generates a structured `SOUL.md`. The original JSON is stored alongside for lossless round-trip on export.

**Export:** If a stored `identity.aieos.json` exists (from prior import), merges SOUL.md edits back into the original. Otherwise, reconstructs AIEOS from SOUL.md. Always includes `extensions.merkaba.raw_soul_md` as a fallback field.

**CLI:**

```bash
merkaba identity import identity.aieos.json --name "My Agent"
merkaba identity export my-business --output agent.aieos.json
```

---

## Protocol Definitions

Four `@runtime_checkable` Protocol classes define the expected interfaces for key Merkaba subsystems, enabling type-safe dependency injection and alternative implementations.

**Key file:** `protocols.py`

| Protocol | Implemented By | Methods |
|----------|---------------|---------|
| `MemoryBackend` | `MemoryStore` | `add_fact`, `get_facts`, `add_decision`, `get_decisions` |
| `VectorBackend` | `VectorMemory` | `search_facts`, `search_decisions`, `search_learnings`, `delete_vectors` |
| `Observer` | (custom) | `on_llm_call`, `on_tool_call`, `on_error` |
| `ConversationBackend` | `ConversationLog` | `append`, `get_history`, `save` |

**Usage:**

```python
from merkaba.protocols import MemoryBackend, Observer

def process(store: MemoryBackend) -> None:
    facts = store.get_facts(business_id=1)
    # Works with MemoryStore or any compatible implementation

# Runtime checking
assert isinstance(my_store, MemoryBackend)
```

These protocols document the minimum interface contract. Implementations may support additional methods beyond what the protocol requires.
