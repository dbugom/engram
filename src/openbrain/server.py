"""Open Brain MCP server (FastMCP v3, Streamable HTTP) + a small REST API.

MCP tools (capture/search/list/supersede/forget/stats/verify) are for AI clients
(Claude Code, Desktop, claude.ai). The REST routes (/capture, /search, /health)
are for deterministic automation such as the Claude Code auto-capture hook, which
can't do an MCP handshake. Both go through the same service layer.

Auth: when GOOGLE_CLIENT_ID/SECRET are configured, /mcp is protected by Google
OAuth (FastMCP GoogleProvider) — required for claude.ai. When unset, /mcp is open
(local-only behaviour). The REST routes are separately gated by OPENBRAIN_TOKEN.
"""
from typing import Literal

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config, db, service

INSTRUCTIONS = (
    "This is the user's personal Open Brain — a semantic memory store. "
    "Use `search_thought` to answer questions about the user from their own "
    "stored context ('what do I know about X?', 'what did I decide about Y?', "
    "'who is Z?'). Use `capture_thought` to save new durable facts, decisions, "
    "and context as clear self-contained statements. Never invent memories: if "
    "search returns nothing relevant, say so. Use `supersede_thought` when a "
    "fact changes rather than adding a contradicting one."
)


def _build_auth():
    """Google OAuth provider when configured, else None (open /mcp)."""
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        return None
    from fastmcp.server.auth.providers.google import GoogleProvider
    return GoogleProvider(
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        base_url=config.OAUTH_BASE_URL,
        redirect_path=config.OAUTH_REDIRECT_PATH,
        required_scopes=["openid", "email", "profile"],
    )


mcp = FastMCP("openbrain", instructions=INSTRUCTIONS, auth=_build_auth())


# ---------------------------------------------------------------------------
# MCP tools (for AI clients)
# ---------------------------------------------------------------------------
@mcp.tool()
async def capture_thought(
    text: str,
    source: str | None = None,
    origin_tool: str | None = None,
    type: str | None = None,
    people: list[str] | None = None,
    topics: list[str] | None = None,
    event_date: str | None = None,
    skip_extraction: bool = False,
    on_near_duplicate: Literal["store", "skip"] = "store",
) -> dict:
    """Save a thought to the Open Brain (embeds it + stores with provenance).

    Write a clear, self-contained statement that will make sense when retrieved
    later with zero prior context. `source` = where it came from; `origin_tool` =
    which AI/tool wrote it. Type/people/topics/date are auto-extracted by a local
    model unless you pass them or set skip_extraction=true. `event_date` = 'YYYY-MM-DD'.
    `on_near_duplicate='skip'` refuses to store when an active thought is already
    >= NEAR_DUP_THRESHOLD (0.95) cosine-similar; the result then carries
    skipped=true plus the existing thought's id/text.
    """
    return await service.capture(
        text=text, source=source, origin_tool=origin_tool, type=type,
        people=people, topics=topics, event_date=event_date,
        skip_extraction=skip_extraction, on_near_duplicate=on_near_duplicate,
    )


@mcp.tool()
async def search_thought(
    query: str,
    limit: int = 8,
    min_similarity: float = 0.3,
    person: str | None = None,
    type: str | None = None,
    include_superseded: bool = False,
) -> dict:
    """Search the Open Brain by meaning (cosine similarity).

    Returns the most relevant stored thoughts with a similarity score (0-1) and
    provenance. If the result list is empty, nothing relevant is stored — do NOT
    fabricate.
    """
    return await service.search(
        query=query, limit=limit, min_similarity=min_similarity,
        person=person, type=type, include_superseded=include_superseded,
    )


@mcp.tool()
async def list_thoughts(
    days: int = 7,
    limit: int = 100,
    person: str | None = None,
    type: str | None = None,
) -> dict:
    """List thoughts captured in the last `days` days (default 7), newest first.

    For the weekly review. Uses server time; reports the window and count.
    """
    rows = await db.list_recent(days=days, limit=limit, person=person, type=type)
    truncated = len(rows) >= limit
    return {
        "ok": True, "days": days, "count": len(rows), "truncated": truncated,
        "note": (
            f"Active thoughts from the last {days} days (server time), newest first"
            + (f"; hit the {limit}-row limit — older items not shown."
               if truncated else ".")
        ),
        "results": rows,
    }


@mcp.tool()
async def supersede_thought(
    old_id: str,
    new_text: str,
    source: str | None = None,
    origin_tool: str | None = None,
) -> dict:
    """Replace an outdated thought with a corrected one.

    Saves `new_text` as a new thought, marks `old_id` superseded (kept for
    history), and links them. Use when a fact changed instead of leaving two
    contradictory thoughts.
    """
    new_text = (new_text or "").strip()
    if not new_text:
        return {"ok": False, "error": "empty new_text"}
    # Must stay on on_near_duplicate="store": corrected text is routinely >=0.95
    # similar to the (still-active) thought it replaces — skip mode would make
    # every supersede a no-op.
    saved = await service.capture(
        text=new_text, source=source or "supersede", origin_tool=origin_tool,
    )
    await db.supersede(old_id, saved["id"])
    return {"ok": True, "old_id": old_id, "new_id": saved["id"],
            "new_type": saved.get("type")}


@mcp.tool()
async def forget_thought(id: str) -> dict:
    """Archive a thought so it no longer appears in searches (kept, not deleted)."""
    ok = await db.archive(id)
    return {"ok": ok, "id": id, "status": "archived" if ok else "not_found"}


@mcp.tool()
async def brain_stats() -> dict:
    """Overview of the Open Brain: totals, status breakdown, types, date range."""
    return await db.stats()


@mcp.tool()
async def verify_connection() -> dict:
    """Round-trip health check: write a canary thought, search it back, delete it."""
    canary = "openbrain canary health check token alpha bravo charlie delta"
    wrote = await service.capture(
        text=canary, source="verify_connection", origin_tool="self-test",
        skip_extraction=True,
    )
    got = await service.search(
        query="canary health check alpha bravo charlie", limit=5,
        min_similarity=0.0, include_superseded=True,
    )
    found = any(r["id"] == wrote["id"] for r in got["results"])
    await db.hard_delete(wrote["id"])
    return {
        "ok": found, "wrote_id": wrote["id"], "found_in_search": found,
        "embed_model": config.EMBED_MODEL, "embed_dim": config.EMBED_DIM,
        "message": "Round-trip OK — capture, embed, store, and search all work."
        if found else "Wrote a canary but could not retrieve it — check search/index.",
    }


# ---------------------------------------------------------------------------
# REST API (for the auto-capture hook / scripts). Gated by OPENBRAIN_TOKEN when
# set — required once the server is exposed publicly, since these are not behind
# the OAuth flow that protects /mcp.
# ---------------------------------------------------------------------------
def _authorized(request: Request) -> bool:
    if not config.API_TOKEN:
        return True
    return request.headers.get("authorization", "") == f"Bearer {config.API_TOKEN}"


@mcp.custom_route("/health", methods=["GET"])
async def http_health(request: Request) -> JSONResponse:
    return JSONResponse(
        {"ok": True, "service": "openbrain", "embed_model": config.EMBED_MODEL,
         "embed_dim": config.EMBED_DIM,
         "oauth": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)}
    )


@mcp.custom_route("/capture", methods=["POST"])
async def http_capture(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    if not body.get("text"):
        return JSONResponse({"ok": False, "error": "missing text"}, status_code=400)
    result = await service.capture(
        text=body.get("text"), source=body.get("source"),
        origin_tool=body.get("origin_tool"), type=body.get("type"),
        people=body.get("people"), topics=body.get("topics"),
        event_date=body.get("event_date"),
        skip_extraction=bool(body.get("skip_extraction", False)),
        on_near_duplicate=body.get("on_near_duplicate", "store"),
    )
    return JSONResponse(result)


@mcp.custom_route("/search", methods=["POST"])
async def http_search(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    result = await service.search(
        query=body.get("query", ""), limit=int(body.get("limit", 8)),
        min_similarity=float(body.get("min_similarity", 0.3)),
        person=body.get("person"), type=body.get("type"),
        include_superseded=bool(body.get("include_superseded", False)),
    )
    return JSONResponse(result)


def main() -> None:
    mcp.run(transport="http", host=config.MCP_HOST, port=config.MCP_PORT, path="/mcp")


if __name__ == "__main__":
    main()
