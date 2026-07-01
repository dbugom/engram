"""Apply db/schema.sql to the configured Postgres database (idempotent)."""
import asyncio
import os

import asyncpg

from . import config


async def main() -> None:
    schema_path = os.environ.get("SCHEMA_PATH", "/app/db/schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    con = await asyncpg.connect(config.DATABASE_URL)
    try:
        before = await con.fetchval(
            "select extversion from pg_extension where extname='vector'"
        )
        print(f"pgvector (before): {before or 'not installed'}")
        await con.execute(sql)
        after = await con.fetchval(
            "select extversion from pg_extension where extname='vector'"
        )
        n = await con.fetchval("select count(*) from thoughts")
        idx = await con.fetchval(
            "select indexdef from pg_indexes where indexname='thoughts_embedding_hnsw'"
        )
        print(f"pgvector (after):  {after}")
        print(f"thoughts rows:     {n}")
        print(f"hnsw index:        {'present' if idx else 'MISSING'}")
        print("SCHEMA APPLIED OK")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
