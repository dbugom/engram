"""End-to-end smoke test of the full stack, bypassing the MCP transport.

Exercises: Ollama embedding -> Qwen3-4B extraction -> Postgres halfvec insert ->
cosine search -> cleanup. Run inside the container:

    docker compose exec openbrain-mcp python -m openbrain.selftest
"""
import asyncio

from . import config, db
from .embed import embed_text
from .extract import extract_metadata

STORE_TEXT = (
    "Selftest canary: Rachel owns the payments launch, which moved to March 15 "
    "because QA found three blockers in the payment flow."
)


async def main() -> None:
    print(f"DB      : {config.DATABASE_URL}")
    print(f"Ollama  : {config.OLLAMA_URL}")
    print(f"Embed   : {config.EMBED_MODEL} (dim {config.EMBED_DIM})")
    print(f"Extract : {config.EXTRACT_MODEL} (enabled={config.ENABLE_EXTRACTION})")
    print("-" * 60)

    vec = await embed_text(STORE_TEXT, is_query=False)
    print(f"[1] embed OK               dim={len(vec)}")

    meta = await extract_metadata("Decision: move the launch to March 15. Owner: Rachel.")
    print(f"[2] extract OK             {meta}")

    row = await db.insert_thought(
        text=STORE_TEXT, embedding=vec, type=meta["type"], people=meta["people"],
        topics=meta["topics"], source="selftest", origin_tool="selftest",
    )
    print(f"[3] insert OK              id={row['id']} duplicate={row['duplicate']}")

    qvec = await embed_text("when is the payments launch and who owns it", is_query=True)
    results = await db.search_thoughts(
        query_embedding=qvec, limit=3, min_similarity=0.0, include_superseded=True,
    )
    print("[4] search OK             top hits:")
    for r in results:
        print(f"      {r['similarity']:.3f}  {r['text'][:70]}")

    found = any(r["id"] == row["id"] for r in results)
    await db.hard_delete(row["id"])
    print(f"[5] cleanup OK            retrieved_canary={found}")
    print("-" * 60)
    print("SELFTEST PASSED" if found else "SELFTEST FAILED (stored but not retrieved)")


if __name__ == "__main__":
    asyncio.run(main())
