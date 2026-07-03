# Open Brain — User Manual

Your self-hosted, private, semantic memory. Capture thoughts once; retrieve them
by meaning from **any** client — local Claude Code, remote Claude Code, or
claude.ai — all sharing one store. Embeddings, database, and extraction run on
your Mac. Remote clients reach it over an OAuth-gated Cloudflare tunnel.

- **Storage**: Supabase local (Postgres + pgvector), `halfvec(2560)` + HNSW cosine
- **Embeddings**: Ollama `qwen3-embedding:4b` (2560-dim) · **Extraction**: `qwen3:4b`
- **Local endpoint** (open): `http://localhost:8000/mcp`
- **Remote endpoint** (Google OAuth): `https://openbrain.example.com/mcp`

---

## Contents
1. [Quick reference](#1-quick-reference)
2. [Turning it on and off](#2-turning-it-on-and-off)
3. [Connecting & triggering from every client](#3-connecting--triggering-from-every-client) ← the important one
4. [How to write good captures](#4-how-to-write-good-captures)
5. [Keeping the brain healthy](#5-keeping-the-brain-healthy)
6. [First fill: migrate your Claude memory](#6-first-fill-migrate-your-claude-memory)
7. [Browsing & backing up your data](#7-browsing--backing-up-your-data)
8. [Automatic capture & REST API](#8-automatic-capture--rest-api)
9. [How remote access is wired](#9-how-remote-access-is-wired)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Quick reference

| Thing | Value |
|---|---|
| Project folder | `~/openbrain` |
| **Local** MCP (open) | `http://localhost:8000/mcp` |
| **Remote** MCP (Google OAuth) | `https://openbrain.example.com/mcp` |
| Postgres (DB) | `localhost:54422` (user/pw `postgres`) · container `supabase_db_openbrain` |
| Supabase Studio | http://localhost:54423 |
| Containers | `openbrain-mcp` (open, local) · `openbrain-oauth` (OAuth, remote) · `openbrain-tunnel` |

Run everything from the project folder: `cd ~/openbrain`

---

## 2. Turning it on and off

Three parts: the **database** (Supabase), the **local** server, and the **remote**
server + tunnel. All auto-restart after a reboot once Docker Desktop is running.

```bash
# START
supabase start --workdir .            # database + Studio
docker compose up -d                  # local server (openbrain-mcp, OPEN)
docker compose --profile tunnel up -d # remote server + tunnel (openbrain-oauth + cloudflared)

# STOP
docker compose --profile tunnel down  # stop remote server + tunnel (local stays up)
docker compose down                   # stop local server too
supabase stop --workdir .             # stop the database (data preserved)

# STATUS / LOGS
docker compose ps
docker compose logs -f openbrain-oauth   # or openbrain-mcp / cloudflared
```

To take Open Brain **off the internet** without disturbing local use:
`docker compose stop cloudflared openbrain-oauth`.

Prerequisite: **Ollama** running on the host with both models
(`ollama list` shows `qwen3-embedding:4b` and `qwen3:4b`).

---

## 3. Connecting & triggering from every client

You drive Open Brain by **talking to your AI in plain language** — it calls the
tools. The trigger phrases are the same everywhere; only the one-time *connection*
differs per client. First time on any client, run **`verify_connection`**.

### A) Local Claude Code (this Mac) — no login

Already connected to the **open** local server. Confirm / re-add:
```bash
claude mcp list                       # shows: openbrain … ✔ Connected
# re-add if needed (user scope = all projects):
claude mcp add --transport http --scope user openbrain http://localhost:8000/mcp
```
No login, lowest latency, works offline. This is your everyday driver.

### B) Remote Claude Code (a different machine) — Google login once

Point Claude Code at the **public** URL; it runs the OAuth flow automatically:
```bash
claude mcp add --transport http --scope user openbrain https://openbrain.example.com/mcp
```
On first use Claude Code opens your browser → **sign in with Google** (the account
allowed by the OAuth app) → consent → it caches the token and connects. No PIN, no
manual headers. (Requires the tunnel to be up on your Mac.)

### C) claude.ai (web / desktop / mobile) — Google login once

1. **claude.ai → Settings → Connectors → Add custom connector**
2. Name `Open Brain` · **URL `https://openbrain.example.com/mcp`**
3. **Connect** → it detects OAuth → **sign in with Google** → consent → connected.
4. In a chat, make sure the connector is enabled, then use it (below).

Only your Google account/org can complete the consent, so the brain stays private.

### Triggering it (identical phrasing on all three)

| You want to… | Say something like… |
|---|---|
| Prove it works | *"Use the Open Brain tools and run **verify_connection**."* |
| Save a thought | *"**Save to my Open Brain**: I decided to store vectors as halfvec because pgvector can't HNSW-index above 2000 dims."* |
| Ask your brain | *"**Search my Open Brain** — what did I decide about the launch date?"* / *"What do I know about Rachel?"* |
| Weekly review | *"Run my **Open Brain weekly review** — list the last 7 days and summarize themes, open items, and anything that changed."* |
| Find duplicates | *"Run **review_duplicates** on my Open Brain and help me consolidate each pair."* |
| Correct a fact | *"That's outdated — **supersede** that Open Brain thought with: 'The launch moved to April 2.'"* |
| Clean up | *"**Forget** that Open Brain thought."* / *"**brain_stats** — how big is my brain?"* |

Tips:
- The first time on a client, be explicit (*"use the Open Brain / openbrain tools"*)
  so it picks the right tool; after that it recognizes them from their descriptions.
- If a real result seems missing from search, say *"search with **min_similarity 0.15**"*
  (default is 0.3; Qwen3 cosine scores run lower than some models).
- Auto-capture (see §8) also saves durable facts hands-free from **local** Claude Code.

---

## 4. How to write good captures

Store **standalone statements** — each is read later with zero context.

| ✅ Good | ❌ Bad |
|---|---|
| "Sarah Chen is my direct report; she focuses on backend and may move to the ML team." | "Sarah – DR – backend" |
| "Decision: launch moved to March 15 — QA found 3 payment-flow blockers. Owner: Rachel." | "launch march 15" |

Sentence patterns that make the local extractor tag things well (hints, not
required syntax): `Decision: … Owner: …` → `decision`; `[Name] — …` →
`person_note`; `Insight: … Triggered by: …` → `idea`; `Meeting with … Action: …`
→ `meeting`; `Saving from [tool]: …` → `reference`. Ask the AI to pass a `source`
so provenance is stored.

---

## 5. Keeping the brain healthy

- **A fact changed → supersede** (don't add a contradiction): *"Supersede thought `<id>`
  with: 'Now uses Postgres instead of SQLite.'"* Keeps history, marks the old one superseded.
- **Remove noise → forget**: *"Forget thought `<id>`."* (archived, not deleted).
- **Weekly duplicate sweep**: *"Run **review_duplicates**."* It lists pairs of
  highly similar active thoughts (default ≥ 0.90 cosine), oriented older/newer.
  For each pair keep one — usually supersede the older with a merged statement,
  or forget the redundant one — then re-run until the list is empty.
- **Monthly hygiene**: *"brain_stats"* for totals and type drift. Exact
  re-captures are auto-deduped; manual near-dupes (≥ 0.95) get a warning;
  auto-capture skips them outright.

---

## 6. First fill: migrate your Claude memory

The MCP server can't *fetch* claude.ai memory — it comes through Claude:
1. In Claude, **Settings → Capabilities → "View and edit your memory"** → **copy it verbatim**
   (the faithful source; better than asking Claude to "recall everything").
2. Paste into a Claude session (Open Brain connected) and say: *"Break this into
   self-contained statements and save each to my Open Brain via capture_thought,
   source 'claude.ai memory'. Show me the batch first."*
3. Repeat per Claude **Project** (each has its own separate memory).

---

## 7. Browsing & backing up your data

**Browse** (Supabase Studio): http://localhost:54423 → Table Editor → `thoughts`,
or the SQL Editor:
```sql
select created_at, type, people, left(text,80) from thoughts
where status='active' order by created_at desc limit 50;
```
**Back up:**
```bash
docker exec supabase_db_openbrain pg_dump -U postgres -d postgres -t thoughts \
  > ~/openbrain-backup-$(date +%Y%m%d).sql
docker exec supabase_db_openbrain psql -U postgres -d postgres -c \
  "\copy (select created_at,type,people,topics,source,text from thoughts where status='active') to stdout with csv header" \
  > ~/openbrain-export.csv
```

---

## 8. Automatic capture & REST API

**Auto-capture** (Claude Code Stop hook, local): after each response a detached
worker asks Qwen3-4B for 0–3 durable facts and saves any it finds — no "save this"
needed. Tagged `source="auto-capture"`.

Noise control (all decisions visible in the audit log):
- Each fact is rated **importance 1–5** (1 = trivial … 5 = critical); anything
  below `OPENBRAIN_MIN_IMPORTANCE` (default **3**, host env var) is dropped —
  log shows `[dropped imp=2]`, saves show `[saved imp=4]`. The rating is stored
  in `thoughts.metadata` (query with `metadata->>'importance'`).
- Facts ≥ 0.95 cosine-similar to something already stored are **skipped**, not
  saved — log shows `[skip-near-dup sim=0.97 existing=<id>]`.
```bash
tail -f ~/.openbrain/auto-capture.log        # audit what it saved/dropped/skipped
touch ~/.openbrain/disable_autocapture       # pause (rm to resume)
export OPENBRAIN_MIN_IMPORTANCE=4            # stricter (in your shell profile)
```
```sql
delete from thoughts where source = 'auto-capture';   -- undo everything it auto-saved
```

**REST API** (used by the hook; also for your scripts): `GET /health`,
`POST /capture`, `POST /search`. On the local server it's open; on the **remote**
server it requires `Authorization: Bearer $OPENBRAIN_TOKEN` (from `.env`).
```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/capture -H 'content-type: application/json' \
  -d '{"text":"I prefer self-hosted pgvector over managed vector DBs.","source":"cli"}'
```

---

## 9. How remote access is wired

For reference / rebuilding. Remote access = **Cloudflare tunnel → OAuth server → Google login**.

- **`.env`** holds: `TUNNEL_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `OAUTH_BASE_URL=https://openbrain.example.com`, `OPENBRAIN_TOKEN`.
- **Google OAuth app** (Google Cloud Console → Credentials → OAuth client ID, Web
  application): redirect URI **`https://openbrain.example.com/auth/callback`**; scopes
  `openid email profile`; restricted to your account (Internal user type, or test
  user). Setting `GOOGLE_CLIENT_ID/SECRET` in `.env` turns OAuth on for `openbrain-oauth`.
- **Cloudflare tunnel** (dashboard): Public Hostname `openbrain.example.com` → Service
  **`http://openbrain-oauth:8000`**. **No Cloudflare Access app** on this hostname —
  the server's Google OAuth is the gate (an Access login page would break the OAuth
  handshake).
- **Bring up / down**: `docker compose --profile tunnel up -d` / `... down`.
- **Verify it's gated correctly** (anonymous request must get OAuth, not your data):
  ```bash
  curl -sS -o /dev/null -w "%{http_code}\n" https://openbrain.example.com/mcp   # expect 401
  curl -s https://openbrain.example.com/health                                  # {"...","oauth":true}
  ```
  `/mcp` → **401 `WWW-Authenticate: Bearer`** = good. If it returns your service JSON,
  it's open; if it redirects to `cloudflareaccess.com`, an Access app is still attached.

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Tool not available (local) | `docker compose ps`; `claude mcp list`; `docker compose up -d`. |
| claude.ai won't connect | Confirm `curl -s .../health` shows `"oauth":true` and `/mcp` → 401 `Bearer` (not a `cloudflareaccess` redirect). Re-check the connector URL ends in `/mcp`. |
| Remote returns `502` right after start | Normal warm-up — cloudflared re-fetching config; wait ~30s. |
| Remote returns `530`/`1033` | Tunnel not serving the hostname — check the Public Hostname Service is `http://openbrain-oauth:8000` and the tunnel is HEALTHY. |
| Google "access blocked" at consent | The account isn't allowed by the OAuth app (Internal org / test users). Add it, or check the app's user type. |
| Captures slow first time | Model cold-start; warm with `ollama run qwen3:4b ""`. |
| Search misses something saved | *"search with min_similarity 0.15."* |
| Ports after a Supabase update | `supabase status --workdir .`. Ports are shifted +100 (`5442x`) to coexist with the `another-supabase-project` project. |

Architecture & design rationale: **[CLAUDE.md](CLAUDE.md)**.
