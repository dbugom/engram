# Deploy Engram with an AI agent 🤖

**You are an AI agent with shell access (e.g. Claude Code), deploying Engram on the
user's machine. Follow these steps in order.** Run each command, verify its result
before moving on, and report progress. Only pause to ask the user where a step is
marked **[ASK USER]**. If a command fails, show the error and apply the matching fix
from *Troubleshooting* rather than continuing blindly.

Engram is a self-hosted, MCP-accessible semantic memory: capture a thought once and
retrieve it by meaning from any AI. This runbook deploys the **local** setup fully
automatically. Remote access (claude.ai over a tunnel) is optional and needs
user-provided secrets — see the end.

---

## 0. Platform
Targets **macOS or Linux** with a shell. Confirm before proceeding.

## 1. Check prerequisites
```bash
for c in git docker ollama supabase; do command -v "$c" >/dev/null 2>&1 && echo "$c: OK" || echo "$c: MISSING"; done
docker info >/dev/null 2>&1 && echo "docker daemon: running" || echo "docker daemon: NOT running"
```
Install anything MISSING, then re-check:
- **Docker Desktop** → https://www.docker.com/products/docker-desktop/ (install *and start it*)
- **Ollama** → https://ollama.com/download
- **Supabase CLI** → `brew install supabase/tap/supabase` (macOS) or https://supabase.com/docs/guides/cli
- **git** → usually preinstalled

## 2. Pull the local models (~5 GB, one-time)
```bash
ollama pull qwen3-embedding:4b
ollama pull qwen3:4b
```

## 3. Clone the repo
```bash
git clone https://github.com/dbugom/engram.git
cd engram
```

## 4. Start the database (Postgres + pgvector + Studio)
```bash
supabase start --workdir .
```
Prints the DB URL (port **54422**) and Studio (**54423**). If it fails with *"port
already allocated"*, another Supabase project is running — `supabase stop` it, or
shift the ports in `supabase/config.toml`.

## 5. Build the image and apply the schema
```bash
docker compose build
docker compose run --rm openbrain-mcp python -m openbrain.migrate
```
Expect `pgvector (after): 0.8.0` … `SCHEMA APPLIED OK`.

## 6. Start the local server (open, localhost only)
```bash
docker compose up -d
```

## 7. Verify end-to-end
```bash
docker compose exec openbrain-mcp python -m openbrain.selftest   # expect: SELFTEST PASSED
curl -s localhost:8000/health                                     # expect: {"ok":true,...}
```

## 8. Connect the user's AI client
**Claude Code** (all projects):
```bash
claude mcp add --transport http --scope user openbrain http://localhost:8000/mcp
claude mcp list        # expect: openbrain … ✔ Connected
```
**Claude Desktop**: Settings → Connectors → add an HTTP MCP server with URL
`http://localhost:8000/mcp`.

## 9. [OPTIONAL] Hands-free auto-capture (Claude Code)
Merge the Stop hook into `~/.claude/settings.json` so durable facts save
automatically (see `hooks/` and **MANUAL.md §8**):
```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command",
  "command": "<ABSOLUTE_PATH>/engram/hooks/on_stop.sh" } ] } ] } }
```
Merge — don't overwrite existing settings. Disable anytime: `touch ~/.openbrain/disable_autocapture`.

## ✅ Done (local)
Tell the user:
- Capture: *"save to my brain: …"* · Recall: *"search my brain: …"* · Review: *"brain_stats"*.
- Data lives in local Postgres. Browse it in Supabase Studio → http://localhost:54423 → `thoughts` table.

---

## [OPTIONAL · ADVANCED] Remote access for claude.ai — [ASK USER]
This exposes the brain to claude.ai / remote clients and **cannot be fully
automated** — it needs the user's own accounts and secrets:
- a **domain on Cloudflare** + a **tunnel token** (Zero Trust → Networks → Tunnels)
- a **Google OAuth** client ID + secret (Google Cloud Console; redirect URI
  `https://<their-domain>/auth/callback`, scopes `openid email profile`)

If the user wants it: collect those, put `TUNNEL_TOKEN`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `OAUTH_BASE_URL`, `OPENBRAIN_TOKEN` in `.env`, run
`docker compose --profile tunnel up -d`, and follow **MANUAL.md §9** exactly
(route the tunnel to `openbrain-oauth:8000`; do NOT put a Cloudflare Access login
in front of `/mcp` — it breaks the OAuth handshake). Otherwise skip; local works fully.

## Troubleshooting
Full guides: **MANUAL.md** (§10) and **CLAUDE.md** (architecture). Common:
- *Tool not available* → `docker compose ps` · `claude mcp list` · `docker compose up -d`.
- *First capture slow* → model cold-start; warm it: `ollama run qwen3:4b ""`.
- *Ports/URLs* → `supabase status --workdir .`.
- *`.env` is gitignored* — never commit secrets.
