"""Open Brain — a self-hosted, MCP-accessible semantic memory.

Postgres + pgvector (halfvec) for storage and cosine search, local Ollama
(Qwen3-Embedding-4B) for embeddings and Qwen3-4B for metadata extraction,
exposed to any MCP client over Streamable HTTP.
"""

__version__ = "0.1.0"
