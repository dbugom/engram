# Open Brain — project guide (for Claude Code & humans)

A self-hosted, MCP-accessible **semantic personal memory**. Capture thoughts once;
retrieve them by meaning from any client — **local Claude Code**, **remote Claude
Code**, or **claude.ai** — all reading and writing one private store. Embeddings,
database, and extraction run locally; nothing leaves the machine except what a
remote client fetches over an OAuth-gated tunnel.

## Architecture (dual-container)

```
  LOCAL (this Mac — no login)
  Claude Code (local) ──► http://localhost:8000/mcp ─────► openbrain-mcp  ─┐
  auto-capture hook   ──► http://localhost:8000/capture ─► (OPEN)          │
                                                                           │ shared
  REMOTE (internet — Google OAuth)                                         │ DB +
  claude.ai / remote Claude Code                                           │ Ollama
     │  https://openbrain.example.com/mcp                                       │
     ▼                                                                     ▼
  Cloudflare tunnel ─────► openbrain-oauth ───────────────► Postgres + pgvector
  (cloudflared sidecar)    (Google OAuth on /mcp)           Supabase local :54422
                                                            halfvec(2560) + HNSW cosine
                               ▲  embeddings + extraction         ▲
                               └── Ollama (host, Metal) ──────────┘
                                   qwen3-embedding:4b (2560d) · qwen3:4b (extraction)
```

**Two app containers, same image (`openbrain-mcp`), same database:**
- **`openbrain-mcp`** — OPEN, bound to `127.0.0.1:8000`. Used by local Claude Code
  and the auto-capture hook. No login.
- **`openbrain-oauth`** — Google OAuth on `/mcp` (FastMCP `GoogleProvider`); REST
  gated by a bearer token. Not published to a host port; the `cloudflared` sidecar
  reaches it over the compose network and the tunnel exposes it at
  `https://openbrain.example.com/mcp`. Opt-in via the `tunnel` compose profile.

## Key design decisions
- **`halfvec(2560)` + HNSW `halfvec_cosine_ops`** — pgvector can't HNSW-index a
  plain `vector()` above 2000 dims; halfvec indexes up to 4000, so Qwen3-4B's
  2560-dim vectors index cleanly. Cosine similarity = `1 - (a <=> b)`.
- **Asymmetric embeddings** — queries get an instruction prefix, documents are
  embedded raw (Qwen3-Embedding's training recipe).
- **FastMCP v3 + GoogleProvider for remote auth** — emits the `401 +
  WWW-Authenticate` header + protected-resource metadata that claude.ai's
  connector requires. Cloudflare's own "Managed OAuth" had a web-connector interop
  bug (Anthropic issue #410), so the *server* owns the OAuth handshake instead.
  **Cloudflare Access is NOT placed in front of `/mcp`** — an Access login page
  would hijack the OAuth handshake; protection is the Google OAuth token itself.
- **Deterministic conflict resolution** (`supersede`), provenance on every row,
  idempotent captures (content-hash), near-duplicate warnings with an optional
  skip policy (`on_near_duplicate="skip"` — used by auto-capture, which also
  rates importance 1–5 and drops low-rated facts), and a `review_duplicates`
  tool for weekly consolidation.

## Layout
```
src/openbrain/
  config.py    env config (DB, Ollama, models, OAuth, REST token)
  embed.py     Ollama embeddings (asymmetric query/doc)
  extract.py   Ollama metadata extraction (+ heuristic fallback)
  db.py        asyncpg access layer
  service.py   shared capture/search logic (MCP tools + REST both call it)
  server.py    FastMCP v3 server: MCP tools + REST routes + Google OAuth
  migrate.py   applies db/schema.sql
  selftest.py  end-to-end smoke test
db/schema.sql  thoughts table + indexes
hooks/         on_stop.sh -> auto_capture.py (Claude Code auto-capture)
Dockerfile, docker-compose.yml, requirements.txt
```

## Run
```bash
supabase start --workdir .                 # Postgres + pgvector + Studio
docker compose run --rm openbrain-mcp python -m openbrain.migrate   # first time
docker compose up -d                       # local server (openbrain-mcp, OPEN)
docker compose --profile tunnel up -d      # + openbrain-oauth + cloudflared (remote)
docker compose exec openbrain-mcp python -m openbrain.selftest
```

## MCP tools / REST API

| MCP tool | REST | Purpose |
|----------|------|---------|
| `capture_thought` | `POST /capture` | Embed + store a thought with provenance |
| `search_thought` | `POST /search` | Cosine semantic search |
| `list_thoughts` | — | Recent thoughts (weekly review) |
| `supersede_thought` | — | Retire an outdated thought for a corrected one |
| `forget_thought` | — | Archive (hide from search, keep) |
| `review_duplicates` | — | Similar-pair report for weekly consolidation |
| `brain_stats` | — | Totals / status / types / date range |
| `verify_connection` | `GET /health` | Round-trip / liveness |

## Auth model
- **Local** (`openbrain-mcp`, localhost): open — no login for Claude Code or the hook.
- **Remote** (`openbrain-oauth`, tunnel): Google OAuth on `/mcp`; REST
  (`/capture`,`/search`) needs `Authorization: Bearer $OPENBRAIN_TOKEN`;
  `/health`, `/.well-known/*`, `/auth/*` are public (required for OAuth discovery).
  Access is restricted to your Google account/org by the Google OAuth app.

## Secrets — `.env` (gitignored, never commit)
`TUNNEL_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_BASE_URL`,
`OPENBRAIN_TOKEN`. The Google OAuth redirect URI is `https://openbrain.example.com/auth/callback`.

## Git branching model
- **`main`** — stable, tagged releases (`v0.1.0`, `v0.2.0`, …). Do not commit directly.
- **`develop`** — integration branch; feature work merges here first.
- **`feature/*`** — one branch per change; branch off `develop`, merge back with `--no-ff`.
- **Release**: merge `develop` → `main` (`--no-ff`), then `git tag -a vX.Y.Z`.

## Everyday use, per-client triggers, remote access, and troubleshooting
See **[MANUAL.md](MANUAL.md)** — especially §3 (triggering from local Claude Code,
remote Claude Code, and claude.ai).
