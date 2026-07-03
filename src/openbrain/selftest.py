"""End-to-end smoke test of the full stack, bypassing the MCP transport.

Exercises: Ollama embedding -> Qwen3-4B extraction -> Postgres halfvec insert ->
cosine search -> cleanup. Run inside the container:

    docker compose exec openbrain-mcp python -m openbrain.selftest
"""
import asyncio

from . import config, db, service
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

    # --- Noise-control checks (service layer) --------------------------------
    created: list[str] = []
    noise_ok = False
    try:
        base = await service.capture(
            text=STORE_TEXT, source="selftest", origin_tool="selftest",
            skip_extraction=True,
        )
        created.append(base["id"])
        # "!" defeats the content hash (normalization keeps punctuation) while
        # cosine similarity stays ~0.99 — exercises the semantic path.
        skipped = await service.capture(
            text=STORE_TEXT + "!", source="selftest", origin_tool="selftest",
            skip_extraction=True, on_near_duplicate="skip",
        )
        skip_ok = (skipped.get("skipped") is True
                   and skipped.get("existing_id") == base["id"])
        if not skip_ok and skipped.get("id"):
            created.append(skipped["id"])
        print(f"[6] near-dup skip OK      skipped={skipped.get('skipped')} "
              f"sim={skipped.get('similarity')}")

        tagged = await service.capture(
            text="Selftest canary two: the roadmap review moved to Thursday.",
            source="selftest", origin_tool="selftest", skip_extraction=True,
            metadata={"importance": 4},
        )
        created.append(tagged["id"])
        pool = await db.get_pool()
        imp = await pool.fetchval(
            "select metadata->>'importance' from thoughts where id=$1::uuid",
            tagged["id"],
        )
        meta_ok = imp == "4"
        print(f"[7] metadata OK           importance={imp}")

        near_dup_for_pair = await service.capture(
            text=STORE_TEXT + " Kickoff is next week.", source="selftest",
            origin_tool="selftest", skip_extraction=True,
        )
        created.append(near_dup_for_pair["id"])
        pairs = await db.find_duplicate_pairs(threshold=0.9)
        pair_ids = {p["older"]["id"] for p in pairs} | {p["newer"]["id"] for p in pairs}
        pairs_ok = base["id"] in pair_ids and near_dup_for_pair["id"] in pair_ids
        print(f"[8] duplicate pairs OK    found={len(pairs)} seeded_pair={pairs_ok}")

        noise_ok = skip_ok and meta_ok and pairs_ok
    finally:
        for tid in created:
            await db.hard_delete(tid)
        print(f"[9] cleanup OK            removed={len(created)}")

    print("-" * 60)
    ok = found and noise_ok
    print("SELFTEST PASSED" if ok else "SELFTEST FAILED "
          f"(retrieved={found}, noise_control={noise_ok})")


if __name__ == "__main__":
    asyncio.run(main())
