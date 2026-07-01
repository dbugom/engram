"""Embedding client — local Ollama (Qwen3-Embedding-4B)."""
import httpx

from . import config


def format_vector(vec: list[float]) -> str:
    """Serialize a vector to pgvector's text form: '[0.1,0.2,...]'.

    Cast to ``halfvec`` happens in SQL, so no client-side codec is needed.
    """
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


async def embed_text(text: str, *, is_query: bool = False) -> list[float]:
    """Return the embedding for ``text`` from the local Ollama model.

    Qwen3-Embedding is trained asymmetrically: search queries are prefixed with
    an instruction, stored documents are embedded raw. We honour that split.
    """
    payload_input = text
    if is_query and config.USE_QUERY_INSTRUCTION:
        payload_input = f"Instruct: {config.EMBED_QUERY_INSTRUCTION}\nQuery: {text}"

    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        resp = await client.post(
            f"{config.OLLAMA_URL}/api/embed",
            json={"model": config.EMBED_MODEL, "input": payload_input},
        )
        resp.raise_for_status()
        data = resp.json()

    embeddings = data.get("embeddings")
    if not embeddings or not embeddings[0]:
        raise RuntimeError(f"Ollama returned no embeddings: {data}")
    vec = embeddings[0]
    if len(vec) != config.EMBED_DIM:
        raise RuntimeError(
            f"Embedding dim {len(vec)} != expected {config.EMBED_DIM}. "
            "Check EMBED_MODEL / EMBED_DIM — the DB column is fixed at that width."
        )
    return vec
