# Context Pipeline Design — AGENTS.md Restructuring

**Date:** 2026-03-16
**Status:** Approved
**Scope:** 7 repos in `~/src/` (merkaba, codesight-mcp, basalt-mcp, familiar, tao-gateway, yoyo-evolve, mcp-console-automation)

## Problem

Agents start work without systematically assembling context. They miss in-progress work, don't check CI state, re-solve problems that were already addressed in prior scans, and claim "done" without verifying. The current AGENTS.md files have Context Recovery and Discovery sections that partially address this, but they're unstructured and missing key layers (Environment, Memory, Validation).

## Solution

Restructure every AGENTS.md around a 5-layer context pipeline. Each layer has a clear purpose and concrete commands/tools. Agents follow the layers in order at session start and task completion.

The content lives in AGENTS.md (Approach A — inline, not a separate file). This ensures agents encounter the pipeline in the pre-loaded system context without needing to follow pointers.

## Design Principles

- **Progressive disclosure**: AGENTS.md is the map (Level 0). CLAUDE.md is detail (Level 1). `docs/` is depth (Level 2).
- **Just-in-time loading**: Don't pre-read everything. Load context on demand as the task requires.
- **Tailored per repo**: Search tools, test commands, CI patterns, and memory tiers vary by repo.
- **Portable**: Content is markdown instructions. Works in Claude Code (CLAUDE.md), Gemini (GEMINI.md), Codex (AGENTS.md), or any agent system.

## Context Window Budgets

Rough guidelines, not hard constraints. Actual usage depends on task complexity.

| Layer | Budget | Purpose |
|-------|--------|---------|
| System | ~10-15% | Pre-loaded project context |
| Environment | ~10% | World state before starting |
| Memory | ~5-10% | Prior knowledge retrieval |
| Task | ~40-50% | Task-specific files and context |
| Validation | ~15-20% | Verify → fix loop |

These overlap intentionally (a git log result informs both Environment and Task). The key constraint: Task gets the largest share, Validation gets dedicated headroom.

## Pipeline Layers

### System (pre-loaded, no section number)

Pre-loaded at session start. Already exists in current AGENTS.md files. No changes needed.

In the template, this is the content *without* a numbered heading: project title, Quick Reference, Structure table, Commands, Key Conventions. These appear at the top (Quick Reference) and between Task and Validation (Structure, Commands, Conventions) where they're most useful as reference during implementation.

**Contents:**
- Project description (one line)
- Quick Reference — pointers to CLAUDE.md, docs/architecture.md, etc.
- Structure table — modules, locations, purposes
- Commands — test, lint, build, dev server
- Key Conventions — commit style, patterns, gotchas

### 1. Environment — Check Before Starting

Check the state of the world before touching code. Replaces the first half of "Context Recovery."

**Contents:**

```markdown
## 1. Environment — Check Before Starting

**Repository state** — don't clobber existing work:
- `git status` — uncommitted changes from a previous session?
- `git stash list` — stashed work?
- `git branch` — feature branch already exists for this task?

**CI/PR state** — know what's broken before you break something:
- `gh run list --limit 5` — is CI green or already failing?
- `gh pr list` — open PRs that might conflict with your work?
- `gh pr view` — if you're on a PR branch, read the description for task context

**Recent history**:
- `git log --oneline -20` — recent project activity
```

**Tailoring:** All repos get git commands. All repos get `gh` commands (all have CI).

**Escalation:** If CI is already failing on an unrelated issue, note which workflow/test is broken and proceed — don't chase pre-existing failures.

### 2. Memory — Check Prior Knowledge

Check prior knowledge before re-solving solved problems or contradicting past decisions.

**Contents:**

```markdown
## 2. Memory — Check Prior Knowledge

Before diving in, check what's already known about this area:

**Git memory** — commits are decisions with context:
- `git log --oneline -- <file>` — why was this file last changed?
- `git blame -L <start>,<end> <file>` — who wrote this code and when?

**QMD vault** — cross-project knowledge base (if available):
- Use the QMD `search` tool for keyword search on relevant decisions, patterns, prior work
- Use the QMD `vector_search` tool for semantic search when you're not sure of exact terms
- QMD indexes the `src` collection (`~/src/**/*.md`) — all repos are covered

**ContextKeep** — persistent agent memory (when configured):
- Use the `list_all_memories` tool to browse stored decisions and context
- Use the `retrieve_memory` tool to pull specific prior decisions related to the current task
- Note: ContextKeep may not be running — if tools are unavailable, skip this tier
```

**Tailoring:**
- **Merkaba only** — add auto-memory tier: "Check `memory/` directory for topic files related to the area you're working in"
- All repos get git memory + QMD + ContextKeep tiers

**Escalation:** If Memory reveals a prior decision that contradicts the current task, surface the conflict to the user before proceeding.

### 3. Task — Assemble Context for the Work

Assemble context for the specific work. Replaces the current "Discovery" section with a structured protocol.

**Contents:**

```markdown
## 3. Task — Assemble Context for the Work

Once you understand the task, systematically load what you need:

**Identify affected files**:
- From the task description, identify which files/modules will change
- `git log --oneline -- <file>` for each affected file — understand recent changes

**Load implementation context** (just-in-time, not everything):
- Read the specific functions you'll modify, not whole files
- Read the test file for each module you'll change — tests document expected behavior
- Read the doc file for the subsystem if one exists

**Check prior analysis**:
- Look for scan reports in `docs/` — security scans, code scans, product scans
- Check for plan/design docs related to the area you're working in (`docs/plans/`)
- These contain decisions, known issues, and constraints that aren't in the code

**Load related context**:
- Check callers/callees of functions you'll change — understand blast radius
- Check for related open issues or PRs that might affect your approach
- If the task references a previous conversation or decision, find it in QMD/ContextKeep

**Don't pre-load**:
- Don't read files you won't modify
- Don't read entire directories "to understand the project"
- Load incrementally — each discovery informs the next
```

**Tailoring per repo:**

| Repo | Search tools | Notes |
|------|-------------|-------|
| merkaba | codesight-mcp (`search_symbols`, `get_symbol`, `get_callers`, `get_impact`, `get_file_outline`) | Multiple scan phases documented in `docs/plans/` |
| codesight-mcp | codesight-mcp (indexes itself) | See CLAUDE.md for full tool list |
| basalt-mcp | codesight-mcp | Read adversarial test files before changing security tools. Read `SECURITY.md` for threat model |
| familiar | codesight-mcp | `cargo doc --open` for type signatures. Check CLAUDE.md for recent handoff context (if the section exists) |
| tao-gateway | Grep/Glob | No codesight index |
| yoyo-evolve | Grep/Glob (single-file agent, full read is fine) | Read `JOURNAL.md` for recent evolution sessions. Read skill files before modifying behavior |
| mcp-console-automation | Grep/Glob | No codesight index |

### 4. Validation — Before Claiming Done

Generate → verify → fix loop. Includes CI monitoring after push.

**Contents:**

```markdown
## 4. Validation — Before Claiming Done

**Self-review your changes**:
- `git diff --stat` — did you touch files you didn't intend to?
- `git diff` — any debug prints, leftover comments, accidental changes?
- Re-read the original task/issue — did you meet every acceptance criterion?

**Run the full verification suite locally**:
- Run tests (not just the ones you think are relevant)
- Run linter/type-checker
- Run formatter if the project requires it

**After pushing — monitor CI**:
- `gh run list --limit 1` — watch the CI run you triggered
- `gh run view <id>` — check status and logs
- If CI fails, diagnose and fix immediately — don't leave it broken
- Common CI failures: formatting, type errors missed locally, test ordering issues
- Push the fix, monitor again until green

**Don't claim done until**:
- Local tests pass
- CI is green (or you've confirmed failures are pre-existing)
- Your diff contains only intentional changes
```

**Tailoring per repo:**

| Repo | Local verification | Common CI failures |
|------|-------------------|-------------------|
| merkaba | `pytest --tb=short -q`, `cd web && npm run build` | Config loader test ordering, WebSocket tests |
| codesight-mcp | `.venv/bin/pytest --tb=short -q` | Stale `uv.lock` after dependency changes |
| basalt-mcp | `npm run lint && npm run build && npm test` | `re2` native module install, `npm audit` |
| familiar | `cargo fmt && cargo test && cargo clippy --all-targets -- -D warnings` | `cargo fmt --check`, clippy warnings-as-errors |
| tao-gateway | `uv run pytest --tb=short -q && uv run ruff check && uv run mypy gateway/` | Type errors, ruff formatting |
| yoyo-evolve | `cargo build && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt -- --check` | clippy warnings-as-errors, fmt check |
| mcp-console-automation | `npm run lint && npm run typecheck` | No test suite currently |

## AGENTS.md Final Structure (template)

```
# <Project> — Agent Navigation

<one-line description>

## Quick Reference
- pointers to CLAUDE.md, docs, architecture

## 1. Environment — Check Before Starting
<tailored environment checks>

## 2. Memory — Check Prior Knowledge
<tailored memory tiers>

## 3. Task — Assemble Context for the Work
<tailored search tools and task assembly protocol>

## Structure
<module table>

## Commands
<test, lint, build>

## Key Conventions
<commit style, patterns, gotchas>

## 4. Validation — Before Claiming Done
<tailored verification suite and CI monitoring>
```

The numbered sections (1-4) are the pipeline steps agents follow. The unnumbered sections (Quick Reference, Structure, Commands, Conventions) are System layer reference content — pre-loaded and available throughout.

Structure, Commands, and Conventions sit between Task and Validation because that's where they're most useful: after the agent has assembled task context and before they start the validation loop.

## Migration

Each repo's AGENTS.md will be rewritten to follow this template. The current Context Recovery and Discovery sections are replaced by the pipeline layers. Existing System content (structure, commands, conventions) is preserved.

## Non-Goals

- This design does not change CLAUDE.md files — those remain Level 1 detail docs
- This design does not implement multi-agent context narrowing (orchestrator → domain → worker) — that's a merkaba-internal concern for later
- This design does not set up ContextKeep — that's a separate task (tool references are marked "when configured" and agents skip if unavailable)
- This design does not create CI pipelines — assumes all repos already have CI
