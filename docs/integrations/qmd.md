# QMD Integration

[QMD](https://github.com/tobi/qmd) is an on-device hybrid search engine for markdown files. It combines BM25 full-text search, vector semantic search, query expansion, and LLM re-ranking — all running locally.

Merkaba integrates with QMD in two ways:

1. **Claude Code MCP server** — QMD tools available directly in Claude Code sessions
2. **Merkaba agent tools** — `document_search` and `document_get` tools the agent can call during conversations

## Prerequisites

- Node.js >= 22 or Bun >= 1.0.0
- macOS (for launchd daemon; Linux users can adapt to systemd)
- ~2GB disk space for QMD models (auto-downloaded on first use)

## Installation

```bash
npm install -g @tobilu/qmd
```

Verify:

```bash
qmd --version
```

## Configure Collections

Add directories of markdown files for QMD to index:

```bash
# Your Obsidian vault
qmd collection add ~/Documents/Obsidian\ Vault/ --name obsidian

# All markdown across source repos
qmd collection add ~/src/ --name src --mask "**/*.md"

# List collections
qmd collection list
```

### Add Context (optional but recommended)

Context helps QMD understand what each collection contains:

```bash
qmd context add qmd://obsidian "Personal knowledge base, project notes, research"
qmd context add qmd://src "Source code documentation and READMEs"
```

### Generate Embeddings

```bash
qmd embed
```

This downloads the embedding model (~300MB) on first run and indexes all documents. Re-run after adding new collections or to pick up new files.

## Claude Code MCP Setup

Add QMD as an MCP server in `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

This gives Claude Code access to `qmd_search`, `qmd_vector_search`, `qmd_deep_search`, `qmd_get`, `qmd_multi_get`, and `qmd_status` tools.

## QMD HTTP Daemon

For Merkaba agent integration, QMD runs as a persistent HTTP daemon so models stay loaded in memory.

### Install the launchd service (macOS)

```bash
# Copy the plist
cp src/merkaba/resources/com.qmd.server.plist ~/Library/LaunchAgents/

# Load and start
launchctl load ~/Library/LaunchAgents/com.qmd.server.plist
```

Verify the daemon is running:

```bash
curl http://localhost:8181/health
```

### Manage the daemon

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.qmd.server.plist

# Restart (unload + load)
launchctl unload ~/Library/LaunchAgents/com.qmd.server.plist
launchctl load ~/Library/LaunchAgents/com.qmd.server.plist

# View logs
tail -f /tmp/qmd-stdout.log
tail -f /tmp/qmd-stderr.log
```

### Custom port

Edit the plist or `~/.merkaba/config.json`:

```json
{
  "qmd": {
    "host": "localhost",
    "port": 8181
  }
}
```

## Merkaba Agent Tools

Once the QMD daemon is running, Merkaba's agent has access to:

- **`document_search`** — Search your documents with a natural language query. Returns ranked results with relevance scores.
- **`document_get`** — Retrieve a document's full content by file path or document ID.

Verify with the CLI:

```bash
merkaba integrations test qmd
```

## Maintenance

```bash
# Re-index all collections (picks up new/changed files)
qmd update

# Force re-embed everything
qmd embed -f

# Show index status
qmd status

# Remove orphaned data
qmd cleanup
```

## Resource Usage

QMD models (~2-3GB total, downloaded to `~/.cache/qmd/models/`):

| Model | Size | Purpose |
|-------|------|---------|
| embedding-gemma-300M | ~300MB | Vector embeddings |
| qwen3-reranker-0.6b | ~640MB | Result re-ranking |
| qmd-query-expansion-1.7B | ~1.1GB | Query expansion |

When running as an HTTP daemon, models stay loaded in memory (~2-3GB resident).
