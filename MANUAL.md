# Open Brain — User Manual

Your self-hosted, private, semantic memory. You capture thoughts once (from any
AI or by hand); you retrieve them by meaning from any connected AI. Everything
runs on your Mac — embeddings, database, and extraction are all local.

- **Storage**: Supabase local (Postgres + pgvector `0.8.0`), `halfvec(2560)` + HNSW cosine
- **Embeddings**: Ollama `qwen3-embedding:4b` (2560-dim)
- **Extraction**: Ollama `qwen3:4b`
- **Interface**: MCP over HTTP → `http://localhost:8000/mcp`

---

## Contents

1. [Quick reference (ports & commands)](#1-quick-reference)
2. [Turning it on and off](#2-turning-it-on-and-off)
3. [Connecting an AI client](#3-connecting-an-ai-client)
4. [Daily use: capture, search, review](#4-daily-use)
5. [How to write good captures](#5-how-to-write-good-captures)
6. [Keeping the brain healthy (maintenance)](#6-maintenance)
7. [First fill: migrate your Claude memory](#7-first-fill-migrate-your-claude-memory)
8. [Browsing & backing up your data](#8-browsing--backing-up-your-data)
9. [Remote access (Cloudflare tunnel)](#9-remote-access)
10. [Tool reference](#10-tool-reference)
11. [Troubleshooting](#11-troubleshooting)
12. [Automatic capture & REST API](#12-automatic-capture--rest-api)

---

## 1. Quick reference

| Thing | Value |
|---|---|
| Project folder | `/Users/mohammadrazavi/Downloads/AI_Engine/openbrain` |
| MCP endpoint | `http://localhost:8000/mcp` |
| Postgres (DB) | `localhost:54422` (user `postgres`, pw `postgres`, db `postgres`) |
| Supabase Studio (browse data) | http://localhost:54423 |
| Supabase API | `http://localhost:54421` |
| DB container name | `supabase_db_openbrain` |

**Everything runs from the project folder.** Open a terminal there first:

```bash
cd /Users/mohammadrazavi/Downloads/AI_Engine/openbrain
```

---

## 2. Turning it on and off

The brain has **two parts**: the Supabase database and the MCP server. Both are
set to auto-restart, so after a reboot they come back once **Docker Desktop** is
running. To control them manually:

```bash
# START (order matters: DB first, then server)
supabase start --workdir .        # database + Studio
docker compose up -d              # MCP server

# STOP
docker compose down               # stop the MCP server
supabase stop --workdir .         # stop the database (data is preserved)

# STATUS / HEALTH
docker compose ps                 # is the MCP server up?
supabase status --workdir .       # is the DB up? shows the ports
docker compose logs -f openbrain-mcp   # live server logs (Ctrl-C to exit)
```

Prerequisite: **Ollama must be running** on the host with the two models pulled
(`ollama list` should show `qwen3-embedding:4b` and `qwen3:4b`). Ollama normally
runs on login; if not, launch the Ollama app or run `ollama serve`.

---

## 3. Connecting an AI client

### Claude Code (already done)

It's registered at **user scope**, so it's available in every project:

```bash
claude mcp list        # should show: openbrain … ✔ Connected
```

If you ever need to re-add it:

```bash
claude mcp add --transport http --scope user openbrain http://localhost:8000/mcp
```

### Claude Desktop

Settings → Developer / Connectors → add an MCP server with URL
`http://localhost:8000/mcp` (type: HTTP).

### ChatGPT / Grok

Only once you've exposed the server through a tunnel (see
[section 9](#9-remote-access)). ChatGPT needs **Developer Mode**; Grok needs a
paid tier; the Gemini consumer app can't connect custom MCP at all.

---

## 4. Daily use

You drive the brain by **talking to your AI in plain language** — it calls the
tools for you. You rarely type tool names yourself.

### First: confirm it works

> **"Use the openbrain tools and run verify_connection."**

You should get "Round-trip OK." Do this once after connecting a new client.

### Capture a thought

> **"Save this to my Open Brain: I decided to store vectors as halfvec because
> pgvector can't HNSW-index above 2000 dimensions."**

The AI calls `capture_thought`. The brain embeds it, auto-extracts metadata
(type, people, topics, date) with the local model, and stores it with
provenance. You'll get back an id and the detected type.

Tips:
- Add where it came from if relevant: *"…save it, source: 'architecture-notes'."*
- If it's very similar to something you already saved, you'll see a
  **near-duplicate warning** (cosine ≥ 0.95) so you can avoid clutter.

### Search / ask the brain

> **"Search my Open Brain: why did I choose halfvec?"**
> **"Ask my brain — what did I decide about the launch date?"**
> **"What do I know about Rachel?"** (add: *"filter by person Rachel"* to narrow)

The AI calls `search_thought`, which returns the most semantically similar
thoughts with a **similarity score (0–1)** and their provenance. If nothing
relevant is stored, it returns an empty list — a good AI will tell you it found
nothing rather than invent an answer.

- Default threshold is `min_similarity = 0.3`. If a real result is being filtered
  out, say *"search with min_similarity 0.15."*
- Qwen3 cosine scores run lower than some models — 0.4–0.7 is a strong match.

### Weekly review

> **"Run my Open Brain weekly review — list_thoughts for the last 7 days and
> summarize the themes, open action items, and anything that changed."**

`list_thoughts` returns everything captured in the window (newest first) and
tells you if it hit the row limit, so the AI can synthesize honestly.

---

## 5. How to write good captures

The brain stores **standalone statements**, not fragments. A thought is read
later with zero surrounding context, so it must make sense on its own.

| ✅ Good | ❌ Bad |
|---|---|
| "Sarah Chen is my direct report; she focuses on backend and is considering a move to the ML team." | "Sarah – DR – backend" |
| "Decision: move the launch to March 15 because QA found 3 payment-flow blockers. Owner: Rachel." | "launch march 15" |

These sentence patterns make the local extractor tag things well (they're
**hints, not required syntax** — plain sentences work too):

| Pattern | Example | Gets typed as |
|---|---|---|
| `Decision: … Context: … Owner: …` | `Decision: adopt halfvec. Context: pgvector 2000-dim index cap. Owner: me.` | `decision` |
| `[Name] — …` | `Marcus — overwhelmed since the reorg; wants the platform team.` | `person_note` |
| `Insight: … Triggered by: …` | `Insight: onboarding assumes users know permissions. Triggered by: watching a new hire.` | `idea` |
| `Meeting with [who] about [what]. …` | `Meeting with design about the dashboard. Action: send API spec Thursday.` | `meeting` |
| `Saving from [tool]: …` | `Saving from Claude: vendor scoring rubric — integration 40%, maintenance 30%, switching 30%.` | `reference` |

> **Provenance matters.** Ask the AI to pass `source` (where it came from) and it
> stores that alongside every thought — useful when you later audit "says who,
> since when?"

---

## 6. Maintenance

Memory that only grows will rot. Two tools keep it trustworthy:

### When a fact changes → supersede (don't add a contradiction)

> **"That's outdated — supersede thought `<id>` with: 'The launch is now April 2,
> after the second QA pass.'"**

`supersede_thought` saves the new version, marks the old one `superseded`
(kept for history, hidden from normal search), and links them. This is
**deterministic most-recent-wins** — the correct way to resolve conflicts.

### To remove noise → forget (archive)

> **"Forget thought `<id>`."**

`forget_thought` archives it — hidden from search, not deleted.

### Periodic hygiene (do monthly)

> **"Search my brain for near-duplicates about `<topic>` and show me clusters I
> should merge or supersede."**
> **"brain_stats — how big is the brain and what types dominate?"**

`brain_stats` shows totals, active/superseded/archived counts, type breakdown,
and date range.

---

## 7. First fill: migrate your Claude memory

The brain is empty. The best first fill is your existing Claude memory:

1. In Claude, open **Settings → Capabilities → View and edit your memory**.
2. **Copy the memory verbatim** (this is the faithful source — better than asking
   Claude to "recall everything," which can omit or confabulate).
3. Paste it into a Claude session connected to Open Brain and say:
   > **"Break this into self-contained statements and save each to my Open Brain
   > via capture_thought, with source 'claude.ai memory'. Show me the batch
   > before saving."**
4. Repeat per Claude **Project** (each project has its own separate memory).

Then top up over time by asking Claude to *"save that to my Open Brain"* whenever
something worth keeping comes up.

---

## 8. Browsing & backing up your data

### Browse visually (Supabase Studio)

Open **http://localhost:54423** → Table Editor → `thoughts`. You can read, edit,
and delete rows by hand, and run SQL in the SQL Editor, e.g.:

```sql
select created_at, type, people, left(text, 80) as preview
from thoughts where status = 'active'
order by created_at desc limit 50;
```

### Back up (do this before big changes)

```bash
# Full table dump (schema + data) to a file
docker exec supabase_db_openbrain pg_dump -U postgres -d postgres -t thoughts \
  > ~/openbrain-backup-$(date +%Y%m%d).sql

# Human-readable CSV export of the text + metadata (no vectors)
docker exec supabase_db_openbrain psql -U postgres -d postgres -c \
  "\copy (select created_at, type, people, topics, source, text from thoughts where status='active') to stdout with csv header" \
  > ~/openbrain-export.csv
```

Your data lives in the Supabase Postgres volume; these dumps are your portable,
own-your-data export.

---

## 9. Remote access

A `cloudflared` sidecar is built into the compose stack (opt-in via the `tunnel`
profile) and is **managed from your Cloudflare dashboard** via a token. This
gives the brain a stable public HTTPS hostname so remote Claude Code or claude.ai
can reach it — without opening any ports on your Mac.

**Prerequisites:** a Cloudflare account, a **domain added to Cloudflare** (needed
for a public hostname), and **Zero Trust** enabled (free tier is fine).

**Setup:**

1. **Create the tunnel.** Cloudflare **Zero Trust dashboard → Networks → Tunnels
   → Create a tunnel → Cloudflared**. Name it e.g. `openbrain`. On the "Install
   connector" screen, **copy the token** (the long string after `--token`). You
   do *not* run the install command it shows — the compose sidecar runs it.

2. **Give the token to the stack.** In the project folder create `.env`:
   ```
   TUNNEL_TOKEN=<paste the token here>
   ```
   (`.env` is gitignored.)

3. **Start the tunnel:**
   ```bash
   docker compose --profile tunnel up -d
   docker compose logs -f cloudflared     # expect "Registered tunnel connection"
   ```
   The tunnel status in the dashboard should flip to **HEALTHY**.

4. **Route a public hostname.** In the tunnel's **Public Hostname** tab → **Add a
   public hostname**:
   - Subdomain + domain: e.g. `openbrain.yourdomain.com`
   - **Type:** `HTTP`  •  **URL:** `openbrain-mcp:8000`

   Use `openbrain-mcp:8000` (the compose service name) — cloudflared reaches the
   MCP container over the shared Docker network, so `localhost` would be wrong.

5. **Gate it (do not skip).** Zero Trust → **Access → Applications → Add →
   Self-hosted**, hostname `openbrain.yourdomain.com`, policy = allow only your
   email. Without this, anyone with the URL can read/write your brain.

**Connect remote clients to** `https://openbrain.yourdomain.com/mcp`.

**Notes & caveats:**
- Local use is unaffected — Claude Code on this Mac and the auto-capture hook keep
  hitting `http://localhost:8000` directly, bypassing the tunnel.
- **Access + claude.ai:** Cloudflare Access expects a browser login, which
  claude.ai's automated connector can't complete. If claude.ai won't connect
  behind Access, either add an Access **service token** the client sends, or drop
  Access for that hostname and set `OPENBRAIN_TOKEN` instead (weaker). Remote
  **Claude Code** can auth through Access via WARP or `cloudflared access`.
- Stop exposing it anytime: `docker compose stop cloudflared`. The brain stays up
  locally.

---

## 10. Tool reference

All tools are called by your AI; parameters shown for reference.

| Tool | Key parameters | What it does |
|---|---|---|
| `capture_thought` | `text` (req), `source`, `origin_tool`, `type`, `people[]`, `topics[]`, `event_date`, `skip_extraction` | Embed + store a thought with provenance; auto-extracts metadata; warns on near-duplicates |
| `search_thought` | `query` (req), `limit=8`, `min_similarity=0.3`, `person`, `type`, `include_superseded=false` | Cosine semantic search; returns matches + similarity + provenance |
| `list_thoughts` | `days=7`, `limit=100`, `person`, `type` | Recent thoughts, newest first (weekly review) |
| `supersede_thought` | `old_id` (req), `new_text` (req), `source`, `origin_tool` | Retire an outdated thought in favour of a corrected one |
| `forget_thought` | `id` (req) | Archive a thought (hidden from search, kept) |
| `brain_stats` | — | Totals, status/type breakdown, date range |
| `verify_connection` | — | Canary round-trip: write → search → delete |

**Types** the extractor uses: `decision`, `person_note`, `idea`, `reference`,
`meeting`, `task`, `note`.
**Statuses**: `active` (searchable), `superseded`, `archived`.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| Claude says the tool isn't available | `docker compose ps` (server up?), then `claude mcp list` (Connected?). Restart: `docker compose up -d`. |
| "Connection refused" / captures fail | Is Ollama running? `ollama list`. Is the DB up? `supabase status --workdir .` |
| Captures are slow the first time | Normal — the first call loads `qwen3:4b`. Warm it: `ollama run qwen3:4b ""`. Or set `ENABLE_EXTRACTION=false` in `docker-compose.yml` and `docker compose up -d`. |
| Search returns nothing for something you saved | Lower the threshold: *"search with min_similarity 0.15."* |
| Wrong `event_date` on a note | Extraction is best-effort and may guess a year. The verbatim `text` is always the source of truth; edit the row in Studio if it matters. |
| Port conflict on start | Open Brain uses shifted ports (`5442x`) to coexist with the `kms-lab` Supabase. Don't revert them. |
| Ports/URLs after a Supabase update | Run `supabase status --workdir .` to see the current values. |

For architecture and design rationale, see [CLAUDE.md](CLAUDE.md).

---

## 12. Automatic capture & REST API

### Automatic capture (Claude Code hook)

A Claude Code **Stop hook** captures durable facts for you — no "save this"
needed. After each Claude response, a *detached* worker reads the exchange, asks
the local Qwen3-4B model for 0–3 genuinely durable facts, and stores any it
finds. It never delays Claude, and it saves nothing on turns with nothing worth
keeping.

- **Registered in** `~/.claude/settings.json` → `hooks.Stop`
  (backup at `~/.claude/settings.json.openbrain-bak`).
- **Scripts**: `hooks/on_stop.sh` (detaches instantly) → `hooks/auto_capture.py`
  (the worker; stdlib-only, runs on system `python3`).
- **Tagged** `source="auto-capture"`, `origin_tool="claude-code:<project>"` so
  it's easy to review or bulk-remove.

```bash
tail -f ~/.openbrain/auto-capture.log        # audit what it captured
touch ~/.openbrain/disable_autocapture       # pause instantly (rm to re-enable)
```
```sql
delete from thoughts where source = 'auto-capture';   -- remove everything it auto-saved
```

**Tune it** by editing the `PROMPT` (how conservative) or `EXTRACT_MODEL` in
`hooks/auto_capture.py`. To disable permanently, remove the `Stop` block from
`~/.claude/settings.json`. Exact duplicates are skipped and near-dupes flagged,
so re-discussing a fact won't clutter the brain.

### REST API (for your own automation)

Alongside MCP, the server exposes a tiny HTTP API (this is what the hook uses),
so any script can reach the brain without an MCP handshake:

| Method & path | Body | Purpose |
|---|---|---|
| `GET /health` | — | Liveness check |
| `POST /capture` | `{"text": "...", "source": "...", ...}` | Store a thought |
| `POST /search` | `{"query": "...", "limit": 8, "min_similarity": 0.3}` | Semantic search |

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/capture -H 'content-type: application/json' \
  -d '{"text":"I prefer self-hosted pgvector over managed vector DBs.","source":"cli"}'
curl -s -X POST localhost:8000/search -H 'content-type: application/json' \
  -d '{"query":"vector db preference","limit":3}'
```

The REST API is unauthenticated while bound to localhost. **Before exposing it
via the Cloudflare tunnel**, set a token: add `OPENBRAIN_TOKEN=<secret>` to
`docker-compose.yml`, run `docker compose up -d`, and send
`Authorization: Bearer <secret>` on `/capture` and `/search`. The hook reads the
same `OPENBRAIN_TOKEN` env var, so set it there too.
