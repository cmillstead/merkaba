# Context Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all 7 AGENTS.md files to follow the 5-layer context pipeline defined in the spec.

**Architecture:** Each AGENTS.md is rewritten from scratch using the template structure. System layer content (structure tables, commands, conventions) is preserved from current files. Pipeline layers 1-4 are tailored per repo using the spec's tailoring tables.

**Tech Stack:** Markdown files only. No code changes.

**Spec:** `~/Documents/obsidian-vault/context/patterns/context-pipeline.md`

---

## Chunk 1: Merkaba AGENTS.md

### Task 1: Rewrite merkaba AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/merkaba/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/merkaba/AGENTS.md` to capture System layer content to preserve (Quick Reference, Structure table, Commands, Conventions).

- [ ] **Step 2: Write the new AGENTS.md**

Rewrite the file following the template structure. Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep + auto-memory (`memory/` directory — merkaba only)
- **Task**: codesight-mcp tools (`search_symbols`, `get_symbol`, `get_callers`, `get_impact`, `get_file_outline`). Note scan reports in `docs/plans/`
- **Validation**: `pytest --tb=short -q`, `cd web && npm run build`. CI failures: config loader test ordering, WebSocket tests

Preserve from current file: Quick Reference pointers (CLAUDE.md, docs/architecture.md, docs/manual.md, docs/integrations/qmd.md), Structure table (10 rows), Commands block, Data section, Key Conventions.

- [ ] **Step 3: Verify line count is under 150**

Run: `wc -l /Users/cevin/src/merkaba/AGENTS.md`
Expected: under 150 lines

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/merkaba add AGENTS.md
git -C /Users/cevin/src/merkaba commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 2: Codesight-MCP AGENTS.md

### Task 2: Rewrite codesight-mcp AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/codesight-mcp/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/codesight-mcp/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: codesight-mcp (indexes itself). Pointer to CLAUDE.md for full tool list. See `docs/architecture.md`, `docs/development-guide.md`, `docs/ci.md`
- **Validation**: `.venv/bin/pytest --tb=short -q`. CI failures: stale `uv.lock` after dependency changes

Preserve: Quick Reference pointers (CLAUDE.md, docs/architecture.md, docs/development-guide.md, docs/ci.md, docs/ci-secrets-checklist.md, SECURITY.md, docs/project-overview.md, docs/source-tree-analysis.md), Commands block, Key Rules.

- [ ] **Step 3: Verify line count**

Run: `wc -l /Users/cevin/src/codesight-mcp/AGENTS.md`

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/codesight-mcp add AGENTS.md
git -C /Users/cevin/src/codesight-mcp commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 3: Basalt-MCP AGENTS.md

### Task 3: Rewrite basalt-mcp AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/basalt-mcp/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/basalt-mcp/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: codesight-mcp tools. CRITICAL: read adversarial test files (`tests/security/adversarial*.test.ts`) before changing security tools. Read `SECURITY.md` for threat model
- **Validation**: `npm run lint && npm run build && npm test`. CI failures: `re2` native module install, `npm audit`

Preserve: Quick Reference (CLAUDE.md, SECURITY.md), Structure table (4 rows), Commands block, Critical Security Rules summary.

- [ ] **Step 3: Verify line count**

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/basalt-mcp add AGENTS.md
git -C /Users/cevin/src/basalt-mcp commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 4: Familiar AGENTS.md

### Task 4: Rewrite familiar AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/familiar/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/familiar/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: codesight-mcp tools. `cargo doc --open` for type signatures. Check CLAUDE.md for recent handoff context (if the section exists). Read `docs/QUICKSTART.md`
- **Validation**: `cargo fmt && cargo test && cargo clippy --all-targets -- -D warnings`. CI failures: `cargo fmt --check`, clippy warnings-as-errors

Preserve: Quick Reference (CLAUDE.md, docs/QUICKSTART.md), Structure table (8 rows), Commands block, Key Rules (cargo fmt, real execution over mocks, re-index after automated sessions, coverage baseline).

- [ ] **Step 3: Verify line count**

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/familiar add AGENTS.md
git -C /Users/cevin/src/familiar commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 5: Tao-Gateway AGENTS.md

### Task 5: Rewrite tao-gateway AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/tao-gateway/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/tao-gateway/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: Grep/Glob (no codesight index). Check CLAUDE.md for tech stack details
- **Validation**: `uv run pytest --tb=short -q && uv run ruff check gateway/ tests/ && uv run mypy gateway/`. CI failures: type errors, ruff formatting

Preserve: Quick Reference (CLAUDE.md), Commands block, Key Rules (real Postgres/Redis over mocks, only mock impractical external services).

- [ ] **Step 3: Verify line count**

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/tao-gateway add AGENTS.md
git -C /Users/cevin/src/tao-gateway commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 6: Yoyo-Evolve AGENTS.md

### Task 6: Rewrite yoyo-evolve AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/yoyo-evolve/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/yoyo-evolve/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: Grep/Glob. Single-file agent (~230 lines) so full read of `src/main.rs` is fine. Read `JOURNAL.md` (top entries) for recent evolution sessions. Read `LEARNINGS.md` for cached knowledge. Read skill files before modifying behavior
- **Validation**: `cargo build && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt -- --check`. CI failures: clippy warnings-as-errors, fmt check

Preserve: Quick Reference (CLAUDE.md, IDENTITY.md), Structure table (4 rows), Commands block, Safety Rules (never modify IDENTITY.md/evolve.sh/workflows, revert on build fail, one improvement per session).

- [ ] **Step 3: Verify line count**

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/yoyo-evolve add AGENTS.md
git -C /Users/cevin/src/yoyo-evolve commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```

## Chunk 7: MCP-Console-Automation AGENTS.md

### Task 7: Rewrite mcp-console-automation AGENTS.md

**Files:**
- Modify: `/Users/cevin/src/mcp-console-automation/AGENTS.md`

- [ ] **Step 1: Read the current AGENTS.md**

Read `/Users/cevin/src/mcp-console-automation/AGENTS.md` to capture System layer content.

- [ ] **Step 2: Write the new AGENTS.md**

Tailoring:

- **Environment**: standard git + gh commands
- **Memory**: git memory + QMD + ContextKeep (no auto-memory)
- **Task**: Grep/Glob (no codesight index). Check CLAUDE.md for project rules
- **Validation**: `npm run lint && npm run typecheck`. No test suite currently. CI failures: type errors

Preserve: Quick Reference (CLAUDE.md), Key Components table (3 rows), Commands block, Key Rules (no separate "Improved" versions, use git not file duplication).

- [ ] **Step 3: Verify line count**

- [ ] **Step 4: Commit**

```bash
git -C /Users/cevin/src/mcp-console-automation add AGENTS.md
git -C /Users/cevin/src/mcp-console-automation commit -m "docs: restructure AGENTS.md around 5-layer context pipeline"
```
