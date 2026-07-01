# Open Brain

Self-hosted semantic memory for your AI. Capture thoughts once; retrieve them by
meaning from any MCP client. Local Postgres + pgvector, local Qwen3 embeddings,
zero data leaving your machine.

- **Storage**: Supabase local (Postgres + pgvector), `halfvec(2560)` + HNSW cosine
- **Embeddings**: Ollama `qwen3-embedding:4b` (2560-dim)
- **Extraction**: Ollama `qwen3:4b` (people / type / topics / date)
- **Interface**: MCP over Streamable HTTP (`http://localhost:8000/mcp`)

## Quickstart

```bash
ollama pull qwen3-embedding:4b && ollama pull qwen3:4b   # once
supabase start --workdir .                               # Postgres + Studio
docker compose build
docker compose run --rm openbrain-mcp python -m openbrain.migrate
docker compose up -d
docker compose exec openbrain-mcp python -m openbrain.selftest
claude mcp add --transport http openbrain http://localhost:8000/mcp
```

## Docs

- **[MANUAL.md](MANUAL.md)** — how to use it day to day (capture, search, review,
  maintenance, backup, remote access, troubleshooting).
- **[CLAUDE.md](CLAUDE.md)** — architecture, design decisions, and internals.
