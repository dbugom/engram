"""Best-effort metadata extraction via a local Ollama chat model (Qwen3-4B).

Design rule: extraction must NEVER block a capture. Any failure (model not
pulled yet, bad JSON, timeout) falls back to a cheap heuristic type with empty
people/topics, so a thought is always saved.
"""
import json
import re

import httpx

from . import config

VALID_TYPES = {
    "decision", "person_note", "idea", "reference", "meeting", "task", "note",
}

_SYSTEM = (
    "You extract structured metadata from a single personal note. "
    "Return ONLY a JSON object with exactly these keys: "
    '"type" (one of: decision, person_note, idea, reference, meeting, task, note), '
    '"people" (array of person names explicitly mentioned), '
    '"topics" (array of 1-4 short lowercase topic keywords), '
    '"event_date" (YYYY-MM-DD if the note refers to a specific date, else null). '
    "Never invent people, topics, or dates that are not present in the note."
)


def heuristic_type(text: str) -> str:
    """Cheap prefix/shape-based type guess used as the extraction fallback."""
    t = text.strip().lower()
    if t.startswith(("decision:", "decided")):
        return "decision"
    if t.startswith(("insight:", "idea:")):
        return "idea"
    if t.startswith(("meeting with", "meeting:")):
        return "meeting"
    if t.startswith(("saving from", "save from", "from claude", "from chatgpt")):
        return "reference"
    if t.startswith(("todo:", "action:", "action item")):
        return "task"
    # "Name — ..." or "Name - ..." person-note shape
    if re.match(r"^[A-Z][\w.'-]+(\s[A-Z][\w.'-]+)?\s[—-]\s", text.strip()):
        return "person_note"
    return "note"


async def extract_metadata(text: str) -> dict:
    fallback = {
        "type": heuristic_type(text),
        "people": [],
        "topics": [],
        "event_date": None,
    }
    if not config.ENABLE_EXTRACTION:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": config.EXTRACT_MODEL,
                    "think": False,          # skip Qwen3 reasoning for a fast, clean JSON
                    "format": "json",
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": text},
                    ],
                    "options": {"temperature": 0},
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
        data = json.loads(content)
    except Exception:
        return fallback

    typ = data.get("type")
    if typ not in VALID_TYPES:
        typ = heuristic_type(text)

    people = [str(p).strip() for p in (data.get("people") or []) if str(p).strip()][:20]
    topics = [str(t).strip().lower() for t in (data.get("topics") or []) if str(t).strip()][:8]
    event_date = data.get("event_date") or None
    if event_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(event_date)):
        event_date = None

    return {"type": typ, "people": people, "topics": topics, "event_date": event_date}
