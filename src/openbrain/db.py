"""Postgres (pgvector / halfvec) access layer for the Open Brain."""
import asyncio
import datetime
import hashlib
import json

import asyncpg

from . import config
from .embed import format_vector

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()
_HALF = f"halfvec({config.EMBED_DIM})"


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    dsn=config.DATABASE_URL, min_size=1, max_size=5
                )
    return _pool


def content_hash(text: str) -> str:
    norm = " ".join(text.split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _to_date(value):
    """Coerce event_date (str 'YYYY-MM-DD' | date | None) to a real date object.

    asyncpg encodes a `$n::date` parameter with its date codec, which calls
    .toordinal() on the Python value — so passing a raw string raises
    "'str' object has no attribute 'toordinal'". We convert here instead.
    """
    if value is None or isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _row_to_dict(r: asyncpg.Record) -> dict:
    d = dict(r)
    for k in ("id", "supersedes", "superseded_by"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    if d.get("created_at") is not None:
        d["created_at"] = d["created_at"].isoformat()
    if d.get("event_date") is not None:
        d["event_date"] = d["event_date"].isoformat()
    if d.get("similarity") is not None:
        d["similarity"] = round(float(d["similarity"]), 4)
    if isinstance(d.get("metadata"), str):  # asyncpg returns jsonb as str
        d["metadata"] = json.loads(d["metadata"])
    return d


async def insert_thought(*, text, embedding, type=None, people=None, topics=None,
                         source=None, origin_tool=None, event_date=None,
                         metadata=None) -> dict:
    """Insert a thought. Idempotent on normalized-text hash (exact dupes skip)."""
    pool = await get_pool()
    vec = format_vector(embedding)
    chash = content_hash(text)
    meta_json = json.dumps(metadata) if metadata else None
    row = await pool.fetchrow(
        f"""
        insert into thoughts
            (text, embedding, type, people, topics, source, origin_tool,
             event_date, content_hash, metadata)
        values ($1, $2::{_HALF}, $3, $4::text[], $5::text[], $6, $7,
                $8::date, $9, coalesce($10::jsonb, '{{}}'::jsonb))
        on conflict (content_hash) where content_hash is not null
        do nothing
        returning id, created_at
        """,
        text, vec, type, people or [], topics or [], source, origin_tool,
        _to_date(event_date), chash, meta_json,
    )
    if row is None:  # exact duplicate — return the existing row
        existing = await pool.fetchrow(
            "select id, created_at from thoughts where content_hash = $1", chash
        )
        return {"id": str(existing["id"]),
                "created_at": existing["created_at"].isoformat(), "duplicate": True}
    return {"id": str(row["id"]), "created_at": row["created_at"].isoformat(),
            "duplicate": False}


async def nearest_similarity(embedding) -> dict | None:
    """Top-1 active neighbour and its cosine similarity (None if store empty)."""
    pool = await get_pool()
    vec = format_vector(embedding)
    row = await pool.fetchrow(
        f"""
        select id, text, 1 - (embedding <=> $1::{_HALF}) as similarity
        from thoughts where status = 'active'
        order by embedding <=> $1::{_HALF} asc
        limit 1
        """,
        vec,
    )
    if not row:
        return None
    return {"id": str(row["id"]), "text": row["text"],
            "similarity": float(row["similarity"])}


async def search_thoughts(*, query_embedding, limit=8, min_similarity=0.0,
                          include_superseded=False, person=None,
                          type=None) -> list[dict]:
    pool = await get_pool()
    vec = format_vector(query_embedding)
    rows = await pool.fetch(
        f"""
        select id, text, type, people, topics, source, origin_tool,
               created_at, event_date, status, superseded_by, metadata,
               1 - (embedding <=> $1::{_HALF}) as similarity
        from thoughts
        where status <> 'archived'
          and ($3::boolean or status = 'active')
          and ($4::text is null or type = $4)
          and ($5::text is null or $5 = any(people))
          and (1 - (embedding <=> $1::{_HALF})) >= $6
        order by embedding <=> $1::{_HALF} asc
        limit $2
        """,
        vec, limit, include_superseded, type, person, min_similarity,
    )
    return [_row_to_dict(r) for r in rows]


async def list_recent(*, days=7, limit=100, person=None, type=None) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        select id, text, type, people, topics, source, origin_tool,
               created_at, event_date, status, metadata
        from thoughts
        where created_at >= now() - ($1::int * interval '1 day')
          and status = 'active'
          and ($2::text is null or type = $2)
          and ($3::text is null or $3 = any(people))
        order by created_at desc
        limit $4
        """,
        days, type, person, limit,
    )
    return [_row_to_dict(r) for r in rows]


async def supersede(old_id: str, new_id: str) -> None:
    """Deterministically retire ``old_id`` in favour of ``new_id`` (history kept)."""
    pool = await get_pool()
    async with pool.acquire() as con:
        async with con.transaction():
            await con.execute(
                "update thoughts set status='superseded', superseded_by=$2::uuid "
                "where id=$1::uuid",
                old_id, new_id,
            )
            await con.execute(
                "update thoughts set supersedes=$2::uuid where id=$1::uuid",
                new_id, old_id,
            )


async def archive(thought_id: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        "update thoughts set status='archived' where id=$1::uuid returning id",
        thought_id,
    )
    return row is not None


async def hard_delete(thought_id: str) -> None:
    pool = await get_pool()
    await pool.execute("delete from thoughts where id=$1::uuid", thought_id)


async def stats() -> dict:
    pool = await get_pool()
    base = await pool.fetchrow(
        """
        select count(*) as total,
               count(*) filter (where status='active') as active,
               count(*) filter (where status='superseded') as superseded,
               count(*) filter (where status='archived') as archived,
               min(created_at) as earliest, max(created_at) as latest
        from thoughts
        """
    )
    types = await pool.fetch(
        "select coalesce(type,'unknown') as type, count(*) as c "
        "from thoughts where status='active' group by 1 order by c desc"
    )
    d = dict(base)
    for k in ("earliest", "latest"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    d["by_type"] = {r["type"]: r["c"] for r in types}
    d["ok"] = True
    return d
