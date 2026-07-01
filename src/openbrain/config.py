"""Runtime configuration, all overridable via environment variables."""
import os


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# --- Database (Supabase local Postgres by default) ---------------------------
# Inside Docker this is overridden to host.docker.internal:54322 by compose.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54322/postgres",
)

# --- Ollama (runs natively on the host for Metal acceleration) ---------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen3-embedding:4b")
EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "qwen3:4b")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "2560"))

# --- Behaviour ---------------------------------------------------------------
ENABLE_EXTRACTION = _bool(os.environ.get("ENABLE_EXTRACTION"), True)

# Qwen3-Embedding is asymmetric: the *query* gets an instruction prefix, while
# stored documents are embedded raw. This follows the model's training recipe
# and materially improves retrieval quality.
USE_QUERY_INSTRUCTION = _bool(os.environ.get("USE_QUERY_INSTRUCTION"), True)
EMBED_QUERY_INSTRUCTION = os.environ.get(
    "EMBED_QUERY_INSTRUCTION",
    "Given a search query, retrieve relevant personal notes, decisions, and facts.",
)

# Cosine-similarity threshold above which a new capture is flagged as a likely
# near-duplicate of something already stored.
NEAR_DUP_THRESHOLD = float(os.environ.get("NEAR_DUP_THRESHOLD", "0.95"))

# --- HTTP transport ----------------------------------------------------------
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "60"))

# Optional bearer token for the REST API (used by automation hooks). If unset,
# the REST API is open — fine while the server is bound to localhost, but set
# this before exposing the server through a Cloudflare tunnel.
API_TOKEN = os.environ.get("OPENBRAIN_TOKEN")
