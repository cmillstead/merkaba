# Merkaba Security Model

Merkaba is a local AI assistant with tool access, approval workflows, and
persistent memory.  This document describes its security architecture,
threat model, and defense layers.

## Threat Model

Merkaba operates on the user's machine with the user's permissions.
The primary threats are:

| Threat | Vector | Mitigation |
|--------|--------|------------|
| Prompt injection | Malicious user input tricks the LLM into unsafe tool use | Input classifier + regex patterns + permission tiers |
| Memory poisoning | Attacker stores malicious facts that alter agent behavior | Business scoping + token budget + contradiction detection |
| Tool abuse | LLM chains tools to exfiltrate data or modify the system | Allowlists, denied paths, permission tiers, approval workflows |
| Credential leakage | Secrets exposed via tool results, logs, or conversations | Path denylists, config.json blocked, keychain for secrets |
| Remote exploitation | Web UI or Telegram bot exposed to untrusted networks | API key auth, CORS localhost-only, TOTP 2FA |

## Defense Layers

### Layer 1: Input Classification (`security/classifier.py`)

Every user message passes through a safety + complexity classifier before
reaching the agent.  Uses `qwen3:4b` to detect prompt injection attempts.

- **Unsafe inputs** are refused outright
- **Simple queries** are routed to a smaller model without tool access
- **Complex queries** get the full model with tools
- Messages under 10 characters skip classification (fail-open by design)
- If Ollama is unavailable, fails open with `complexity=complex`

### Layer 2: Tool Argument Validation (`security/validation.py`)

All tool arguments are scanned before execution:

- **Prompt injection patterns**: "ignore previous", "you are now", special tokens
- **Homoglyph normalization**: Cyrillic/Greek/fullwidth characters normalized
  via NFKC before pattern matching
- **Type validation**: Arguments checked against expected types
- Runs recursively through nested objects and arrays

### Layer 3: File System Access Control (`tools/builtin/files.py`)

Three tiers of file protection:

- **DENIED_PATHS**: `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.merkaba/config.json`,
  `/etc/passwd`, `/etc/shadow`, etc. — blocked for all operations
- **DENIED_FILENAME_PATTERNS**: `.env`, `credentials.json`, `secrets.yaml`,
  SSH keys — blocked by filename anywhere on disk
- **SHELL_CONFIG_FILES**: `~/.bashrc`, `~/.zshrc` — blocked for writes only

All three checks apply to `file_read`, `file_write`, and `file_list`.
Paths are resolved via `Path.resolve()` to prevent `../` traversal.

### Layer 4: Shell Command Sandboxing (`tools/builtin/shell.py`)

- **Allowlist**: Only specific commands permitted (`git`, `ls`, `grep`, `find`,
  `pytest`, `uv`, `pip`, `npm`, etc.)
- **Subcommand allowlists**: git commands restricted to safe operations
  (`status`, `diff`, `log`, `commit`, etc.)
- **Dangerous construct detection**: Backticks, `$()`, pipes, redirects to `~`
- **Forbidden patterns**: `/etc/passwd`, `~/.ssh`, `.env`, `config.json`
- **60-second timeout** on all commands
- `python` is NOT in the allowlist (prevents upload-to-execute RCE chains)

### Layer 5: Permission Tiers (`tools/base.py`, `security/permissions.py`)

Every tool has a permission tier:

| Tier | Examples | Behavior |
|------|----------|----------|
| SAFE | `file_read`, `memory_search`, `file_list` | Auto-approved |
| MODERATE | `file_write`, `bash`, `web_fetch` | Auto-approved in web chat; requires approval in Telegram |
| SENSITIVE | Integration adapters | Requires explicit approval |
| DESTRUCTIVE | Delete operations | Requires approval + 2FA |

### Layer 6: Approval Workflows (`approval/`)

- **ActionQueue**: All non-trivial actions queued for approval
- **SecureApprovalManager**: Wraps ActionQueue with rate limiting + TOTP 2FA
- **Rate limiting**: Configurable max approvals per time window (default: 5/60s)
- **TOTP 2FA**: Required for `autonomy_level >= 3` actions (configurable threshold)
- **Autonomy levels**: Clamped to 1–5 range; cannot be inflated by workers
- Web and Telegram approval routes both enforce 2FA when configured

### Layer 7: Memory Security (`memory/`)

- **Business scoping**: Facts are scoped to business IDs; cross-tenant queries
  filtered
- **Token budget**: Memory injection capped at ~800 tokens (~3200 chars)
- **Keyword + vector search**: Dual-path retrieval ensures facts are findable
  regardless of indexing method
- **Contradiction detection**: Optional detector flags conflicting facts
  (uses keyword overlap + LLM verification)
- **Lifecycle management**: `SessionExtractor` extracts facts from conversations
  with deduplication (70% overlap threshold)
- **Access tracking**: Unused facts tracked via `last_accessed` / `access_count`

### Layer 8: Web Security (`web/`)

- **API key auth**: Optional `X-API-Key` header, checked via
  `hmac.compare_digest()` (constant-time comparison)
- **CORS**: Restricted to `localhost:5173` and `127.0.0.1:5173`
- **Session IDs**: Validated with `^[\w\-]+$` regex + `realpath` containment check
- **File uploads**: Filenames sanitized via `os.path.basename()`
- **WebSocket**: JSON parsing with graceful fallback; non-string coercion

### Layer 9: Telegram Security (`telegram/`, `approval/secure.py`)

- **TOTP 2FA**: 6-digit time-based codes via pyotp, stored in OS keychain
- **5-minute timeout** for 2FA code entry
- **Rate limiting** on approval actions
- **Lazy agent initialization** to prevent resource exhaustion at import time

### Layer 10: Plugin Sandboxing (`plugins/sandbox.py`)

- **Manifest-based permissions**: Plugins declare file access, network hosts,
  and tool access in their manifest
- **Protected paths**: Security-critical Merkaba files blocked from plugin access
- **Runtime enforcement**: `PluginSandbox.is_path_allowed()` checked before
  every plugin file operation

## Credential Storage

| Secret | Storage | Access |
|--------|---------|--------|
| Integration API keys | OS keychain (`security/secrets.py`) | Retrieved per-use, not cached |
| TOTP secret | OS keychain | Loaded into memory only when 2FA configured |
| Web API key | `~/.merkaba/config.json` | Blocked from file_read/bash tools |
| Conversation history | `~/.merkaba/conversations/*.json` | Unencrypted JSON on disk |

## Known Limitations

These are documented and tested in `tests/test_adversarial.py`:

1. **Memory poisoning**: Stored facts are injected into the system prompt
   without sanitization.  The LLM is the last line of defense against
   malicious fact values.  Mitigated by business scoping and token budget.

2. **Classifier fail-open**: When Ollama is unavailable, the classifier passes
   all inputs as safe with full tool access.

3. **Short input bypass**: Messages under 10 characters skip classification
   entirely (e.g., `rm -rf /` is 9 chars).

4. **Conversation persistence**: Tool results (potentially containing sensitive
   file contents) are saved to unencrypted JSON files and included in backups.

5. **Upload extension preservation**: File uploads preserve original extensions.
   While `python` is not in the bash allowlist, other interpreters could
   theoretically be used.

## Security Testing

- **295 security-focused tests** across dedicated security test files
- **42 adversarial tests** (`tests/test_adversarial.py`) covering:
  - Memory poisoning (8 payloads, all memory types)
  - File upload attack chains
  - Tool chaining / permission escalation
  - Bash escape attempts (pipes, backticks, `$()`, redirects, chaining)
  - Approval & 2FA bypass attempts
  - WebSocket protocol abuse
  - Credential leakage paths
  - Plugin sandbox escapes
  - Classifier evasion
  - Cross-boundary attack chains
  - SQL injection resistance
- **Adversarial scan findings**: `docs/plans/2026-02-28-adversarial-scan-findings.md`

## Reporting Security Issues

If you discover a security vulnerability, please file a private report or
contact the maintainer directly rather than opening a public issue.
