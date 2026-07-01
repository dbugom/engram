# Open Brain — project guide (for Claude Code & humans)

A self-hosted, MCP-accessible **semantic personal memory**. Any MCP client
(Claude Code, Claude Desktop, ChatGPT dev mode, Grok) can capture thoughts and
retrieve them by meaning. Everything runs locally; nothing leaves the machine.

## Architecture

```
Claude Code / Desktop ──(MCP, Streamable HTTP :8000/mcp)──► openbrain-mcp (Docker)
                                                               │
                        embeddings + extraction (HTTP)         ▼
   Ollama (host, Metal) ◄───────────────────────────  Postgres + pgvector
     qwen3-embedding:4b  (2560-dim, stored as halfvec)   (Supabase local :54422)
     qwen3:4b           (metadata extraction)            HNSW cosine index
```

- **DB**: Supabase local stack (Postgres 15 + pgvector), Studio UI at
  http://localhost:54423 to browse/audit thoughts. DB on `:54422`.
  (Ports are shifted +100 from Supabase defaults so this coexists with the
  separate `kms-lab` Supabase project already running on 5432x.)
- **Vectors**: `halfvec(2560)` with an HNSW index using `halfvec_cosine_ops`.
  halfvec is required because pgvector cannot HNSW-index a plain `vector()`
  above 2000 dims; halfvec indexes up to 4000. Cosine similarity = `1 - (a <=> b)`.
- **Embeddings**: local Qwen3-Embedding-4B via Ollama. Asymmetric usage —
  **queries** get an instruction prefix, **documents** are embedded raw
  (the model's training recipe; improves retrieval).
- **Extraction**: local Qwen3-4B fills `type / people / topics / event_date`.
  Best-effort — a failure never blocks a capture (falls back to a heuristic type).
- **Transport**: Streamable HTTP (not stdio) so the *same* server works locally
  now and through a Cloudflare tunnel later, with no code change.

## Layout

```
src/openbrain/
  config.py     env-driven config
  embed.py      Ollama embedding client (asymmetric query/doc)
  extract.py    Ollama metadata extraction (+ heuristic fallback)
  db.py         asyncpg access layer (insert/search/list/supersede/archive/stats)
  server.py     FastMCP server + tools
  migrate.py    applies db/schema.sql
  selftest.py   end-to-end smoke test (bypasses MCP)
db/schema.sql   the thoughts table + indexes
Dockerfile, docker-compose.yml, requirements.txt
```

## Run it (first time)

```bash
cd Downloads/AI_Engine/openbrain

# 1. Start the local Supabase stack (Postgres + pgvector + Studio)
supabase start --workdir .

# 2. Apply the schema (creates the thoughts table + HNSW cosine index)
docker compose build
docker compose run --rm openbrain-mcp python -m openbrain.migrate

# 3. Start the MCP server
docker compose up -d

# 4. Verify the whole stack end to end
docker compose exec openbrain-mcp python -m openbrain.selftest
```

Ollama must be running on the host with the models pulled:
`ollama pull qwen3-embedding:4b` and `ollama pull qwen3:4b`.

## Connect Claude Code

```bash
claude mcp add --transport http openbrain http://localhost:8000/mcp
```

Then, in a session: *"Use the openbrain tools — run verify_connection."* After
that you can just ask naturally (Claude picks the tools up from their
descriptions): *"Search my brain: what did I decide about the launch?"*

## MCP tools

| Tool | Purpose |
|------|---------|
| `capture_thought` | Embed + store a self-contained thought with provenance |
| `search_thought` | Cosine semantic search ("what do I know about X?") |
| `list_thoughts` | Recent thoughts in the last N days (weekly review) |
| `supersede_thought` | Retire an outdated thought in favour of a corrected one |
| `forget_thought` | Archive a thought (kept, hidden from search) |
| `brain_stats` | Totals, status breakdown, types, date range |
| `verify_connection` | Canary round-trip: write → search → delete |

## Automation (REST API + auto-capture hook)

The server also exposes a small REST API on the same port — `GET /health`,
`POST /capture`, `POST /search` — for deterministic automation that can't do an
MCP handshake. MCP tools and REST routes share `service.py`, so both take the
identical embed → extract → dedup → provenance path. Optional bearer auth via
`OPENBRAIN_TOKEN` (off by default; set it before tunnelling).

A Claude Code **Stop hook** (`hooks/on_stop.sh` → `hooks/auto_capture.py`,
registered in `~/.claude/settings.json`) does hands-free capture: after each
turn it extracts 0–3 durable facts with Qwen3-4B (via Ollama **structured
outputs** — a JSON schema, not `format:"json"`, which qwen3 mis-handles) and
POSTs them to `/capture`. It runs detached (never blocks Claude), is strict by
default, tags rows `source="auto-capture"`, and is disabled by
`touch ~/.openbrain/disable_autocapture`.

## Data model notes

- **Provenance** on every row: `source`, `origin_tool`, `created_at`.
- **Conflict resolution is deterministic** (most-recent-wins via
  `supersede_thought`), not LLM-judged. Old rows are kept as `superseded`.
- **Idempotency**: exact re-captures are deduped by a normalized-text hash;
  near-duplicates (cosine ≥ 0.95) return a warning but still save.
- `status`: `active` (searchable) | `superseded` | `archived` (hidden).

## Remote access (Cloudflare tunnel — later)

The server listens on `127.0.0.1:8000`. To reach it from anywhere:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```

That prints a public `https://…trycloudflare.com` URL; connect a web AI to
`<url>/mcp`. **Gate it** — either a named tunnel behind Cloudflare Access
(email policy) or keep it ad-hoc/short-lived. Note: the consumer Gemini app
cannot add custom MCP; ChatGPT needs Developer Mode; Grok needs a paid tier.
Because writes are now possible from web AIs, treat any exposed endpoint as an
attack surface (memory-poisoning) — prefer Access in front of it.

## Troubleshooting

- **`halfvec` type errors on migrate** → the local pgvector is < 0.7. Check
  `select extversion from pg_extension where extname='vector'`. Update the
  Supabase CLI / re-pull images, or fall back to `vector(2560)` with **no** HNSW
  index (brute-force cosine — fine at personal scale).
- **Container can't reach DB/Ollama** → confirm `host.docker.internal` resolves
  (compose sets `extra_hosts`) and that `supabase start` and `ollama` are up.
- **Embedding dim mismatch** → `EMBED_DIM` must equal the model's output (2560
  for qwen3-embedding:4b). Changing the model/dim requires a full re-embed.
- **Slow captures** → the first Qwen3-4B extraction call loads the model; warm
  it with `ollama run qwen3:4b ""` or set `ENABLE_EXTRACTION=false`.
