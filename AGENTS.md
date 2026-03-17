# Merkaba — Agent Navigation

Full-stack AI agent system: LLM routing, memory, security, orchestration, web UI, plugins.

## Quick Reference

- **Setup**: See `CLAUDE.md` for code navigation, key files, and conventions
- **Architecture**: See `docs/architecture.md` for module map, data flow, storage schema
- **Manual**: See `docs/manual.md` for comprehensive subsystem documentation
- **QMD integration**: See `docs/integrations/qmd.md` for document search setup

## 1. Environment — Check Before Starting

- **Repository state**: `git status`, `git stash list`, `git branch`
- **CI/PR state**: `gh run list --limit 5`, `gh pr list`, `gh pr view`
- **Recent history**: `git log --oneline -20`
- **Escalation**: If CI is already failing on an unrelated issue, note it and proceed

## 2. Memory — Check Prior Knowledge

- **Git memory**: `git log --oneline -- <file>`, `git blame -L <start>,<end> <file>`
- **QMD vault**: Use QMD `search` and `vector_search` tools. QMD indexes `~/src/**/*.md`
- **ContextKeep**: `list_all_memories`, `retrieve_memory` (when configured, skip if unavailable)
- **Auto-memory**: Check `memory/` directory for topic files related to the area
- **Escalation**: If Memory reveals a prior decision that contradicts the current task, surface to user

## 3. Task — Assemble Context for the Work

- **Find code** via codesight-mcp: `search_symbols`, `get_symbol`, `get_callers`, `get_impact`, `get_file_outline`
- Read specific functions, not whole files
- Read test files for modules you'll change
- Check prior analysis: scan reports and plan/design docs in `docs/` and `docs/plans/`
- Check callers/callees for blast radius
- Don't pre-load — load incrementally

## Structure

| Area | Location | Purpose |
|------|----------|---------|
| Agent core | `src/merkaba/agent.py` | Memory-aware agent, model routing, tool harness |
| LLM | `src/merkaba/llm.py`, `llm_providers/` | Ollama/Anthropic/OpenAI, fallback chains |
| Memory | `src/merkaba/memory/` | SQLite + ChromaDB, retrieval, lifecycle |
| Security | `src/merkaba/security/` | Classifier, encryption, sandbox, permissions |
| Orchestration | `src/merkaba/orchestration/` | Supervisor, workers, scheduler, heartbeat |
| Web | `src/merkaba/web/` | FastAPI + React SPA, WebSocket |
| Plugins | `src/merkaba/plugins/` | Registry, sandbox, hooks, skills, forge |
| CLI | `src/merkaba/cli.py` | All lazy imports, ~3000 lines |
| Config | `src/merkaba/config/` | Loader, defaults, utils, validation |
| Frontend | `web/src/` | React components, Mission Control UI |

## Commands

```bash
pytest --tb=short -q              # Unit tests
pytest -m e2e                     # E2E tests only
pytest -m "not e2e"               # Unit tests only
cd web && npm run build           # Build frontend
cd web && npm run dev             # Dev server
```

## Data

- Config/DBs: `~/.merkaba/`
- Models: Ollama (qwen3.5:122b, qwen3:8b, qwen3:4b)

## Key Conventions

- All CLI imports are lazy (no import-time failures)
- Mock ollama in tests via `sys.modules` injection
- Commit style: `feat:`, `fix:`, `test:`, `docs:`
- `.example` pattern for user-customizable files

## 4. Validation — Before Claiming Done

- **Self-review**: `git diff --stat`, `git diff`, re-read task/issue for acceptance criteria
- **Local verification**: `pytest --tb=short -q`, `cd web && npm run build`
- **After pushing**: `gh run list --limit 1`, `gh run view <id>`, fix CI failures immediately
- **Common CI failures**: config loader test ordering, WebSocket tests
- **Don't claim done until**: local tests pass, CI green, diff is intentional only


## Boundaries

### Always Do
- Run tests and linting before committing — NEVER commit without verification
- Follow the architectural layer structure defined above
- Use real implementations in tests — NEVER use mocks, patches, or stubs
- Use existing utilities before creating new ones — search before writing
- Write tests alongside new code — NEVER ship untested business logic
- Read the spec/plan before implementing — understand "done" before starting

### Ask First
- Adding a new external dependency
- Modifying database schema or migrations
- Changing public API contracts or interfaces
- Deleting or moving files in shared directories
- Any change affecting more than 3 modules

### Never Do
- NEVER commit secrets, tokens, API keys, or credentials
- NEVER modify deployed migration files
- NEVER skip or disable tests to make CI pass
- NEVER force push to main or release branches
- NEVER commit .env files or sensitive configuration
- NEVER introduce a new framework or library without explicit approval
- NEVER claim work is done without running verification
- NEVER retry the same failed approach more than 3 times — escalate instead
- NEVER expand task scope without asking — park new ideas separately

## Golden Principles
Read docs/golden-principles.md when: making architectural decisions, resolving ambiguity, or unsure which approach to take.
