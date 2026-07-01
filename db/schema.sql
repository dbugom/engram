-- Open Brain schema: semantic personal memory on Postgres + pgvector (halfvec).
-- Idempotent: safe to run repeatedly.

create extension if not exists vector;

create table if not exists thoughts (
    id             uuid primary key default gen_random_uuid(),
    text           text not null,
    embedding      halfvec(2560) not null,        -- Qwen3-Embedding-4B width
    type           text,                          -- decision|person_note|idea|reference|meeting|task|note
    people         text[] not null default '{}',
    topics         text[] not null default '{}',
    source         text,                          -- provenance: where it came from
    origin_tool    text,                          -- which AI/tool wrote it
    event_date     date,                          -- the date the note is *about* (optional)
    created_at     timestamptz not null default now(),
    supersedes     uuid references thoughts(id) on delete set null,
    superseded_by  uuid references thoughts(id) on delete set null,
    status         text not null default 'active'
                     check (status in ('active', 'superseded', 'archived')),
    content_hash   text,                          -- normalized-text hash for idempotency
    metadata       jsonb not null default '{}'::jsonb
);

-- Fast cosine similarity search. halfvec supports HNSW indexing up to 4000 dims,
-- so 2560-dim vectors index cleanly — a plain vector() column CANNOT be
-- HNSW/IVFFlat-indexed above 2000 dims, which is why halfvec is used here.
create index if not exists thoughts_embedding_hnsw
    on thoughts using hnsw (embedding halfvec_cosine_ops);

create index if not exists thoughts_created_at_idx on thoughts (created_at desc);
create index if not exists thoughts_status_idx     on thoughts (status);
create index if not exists thoughts_type_idx       on thoughts (type);
create index if not exists thoughts_people_gin     on thoughts using gin (people);
create index if not exists thoughts_topics_gin     on thoughts using gin (topics);

-- Exact-duplicate guard (idempotent captures / re-run migrations).
create unique index if not exists thoughts_content_hash_uidx
    on thoughts (content_hash) where content_hash is not null;
