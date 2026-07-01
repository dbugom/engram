"""Shared capture/search logic used by BOTH the MCP tools and the REST API.

Keeping this in one place means an auto-capture hook (REST) and an AI client
(MCP) go through identical embedding, extraction, dedup, and provenance paths.
"""
from . import config, db
from .embed import embed_text
from .extract import extract_metadata


async def capture(text, source=None, origin_tool=None, type=None, people=None,
                  topics=None, event_date=None, skip_extraction=False) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty text"}

    embedding = await embed_text(text, is_query=False)

    m_type, m_people, m_topics, m_date = type, people, topics, event_date
    if not skip_extraction and (type is None or people is None or topics is None):
        ex = await extract_metadata(text)
        m_type = type or ex["type"]
        m_people = people if people is not None else ex["people"]
        m_topics = topics if topics is not None else ex["topics"]
        m_date = event_date or ex["event_date"]
    else:
        m_type = type or "note"
        m_people = people or []
        m_topics = topics or []

    near = await db.nearest_similarity(embedding)
    result = await db.insert_thought(
        text=text, embedding=embedding, type=m_type, people=m_people,
        topics=m_topics, source=source, origin_tool=origin_tool, event_date=m_date,
    )
    result.update({"ok": True, "type": m_type, "people": m_people, "topics": m_topics})
    if (near and not result.get("duplicate")
            and near["similarity"] >= config.NEAR_DUP_THRESHOLD):
        result["near_duplicate_warning"] = {
            "similarity": round(near["similarity"], 3),
            "existing_id": near["id"],
            "existing_text": near["text"],
        }
    return result


async def search(query, limit=8, min_similarity=0.3, person=None, type=None,
                 include_superseded=False) -> dict:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    emb = await embed_text(q, is_query=True)
    rows = await db.search_thoughts(
        query_embedding=emb, limit=limit, min_similarity=min_similarity,
        include_superseded=include_superseded, person=person, type=type,
    )
    return {"ok": True, "count": len(rows), "results": rows}
