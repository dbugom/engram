# Engram 🧠

**A private, self-hosted memory that any AI can read and write.** Capture a thought
once — from Claude Code, claude.ai, or automatically as you work — and retrieve it
by meaning from any of them. Your context follows *you*, not the AI vendor.

Local Postgres + pgvector, local Qwen3 embeddings, MCP — nothing leaves your machine.

- **Storage**: Supabase local (Postgres + pgvector), `halfvec(2560)` + HNSW cosine
- **Embeddings**: Ollama `qwen3-embedding:4b` (2560-dim) · **Extraction**: `qwen3:4b`
- **Interface**: MCP over Streamable HTTP — Claude Code, claude.ai & any MCP client

## 🤖 Deploy with your AI agent (one prompt)

Point your AI agent (Claude Code, etc.) at this repo and let it do the whole setup:

> **"Read https://github.com/dbugom/engram/blob/main/AGENTS.md and deploy Engram on my machine."**

It checks prerequisites, pulls the models, starts the database, applies the schema,
launches the server, and connects your AI — following **[AGENTS.md](AGENTS.md)**.

## Or deploy it yourself

```bash
ollama pull qwen3-embedding:4b && ollama pull qwen3:4b   # once
git clone https://github.com/dbugom/engram.git && cd engram
supabase start --workdir .                               # Postgres + Studio
docker compose build
docker compose run --rm openbrain-mcp python -m openbrain.migrate
docker compose up -d
docker compose exec openbrain-mcp python -m openbrain.selftest
claude mcp add --transport http openbrain http://localhost:8000/mcp
```

## Docs
- **[AGENTS.md](AGENTS.md)** — one-prompt deployment runbook for an AI agent.
- **[MANUAL.md](MANUAL.md)** — day-to-day use (capture, search, review, remote access, troubleshooting).
- **[CLAUDE.md](CLAUDE.md)** — architecture, design decisions, and internals.
