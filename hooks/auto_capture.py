#!/usr/bin/env python3
"""Open Brain auto-capture worker — invoked (detached) by the Claude Code Stop hook.

Reads the just-finished exchange from the session transcript, asks the local
Qwen3-4B model to extract 0-3 DURABLE facts worth remembering long-term, and
POSTs each to the Open Brain REST API (which embeds, dedups, and stores them).

Design: zero third-party deps (stdlib only, runs on system python3); conservative
(defaults to saving nothing); never blocks Claude; fails silently.

Disable at any time:   touch ~/.openbrain/disable_autocapture
Audit what it saved:   tail -f ~/.openbrain/auto-capture.log
Prune everything it saved:  delete from thoughts where source = 'auto-capture';
"""
import json
import os
import sys
import urllib.request

OPENBRAIN_URL = os.environ.get("OPENBRAIN_URL", "http://localhost:8000")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EXTRACT_MODEL = os.environ.get("OPENBRAIN_AUTOCAPTURE_MODEL", "qwen3:4b")
TOKEN = os.environ.get("OPENBRAIN_TOKEN")

HOME = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME, ".openbrain")
LOG_FILE = os.path.join(LOG_DIR, "auto-capture.log")
DISABLE_FILE = os.path.join(LOG_DIR, "disable_autocapture")

PROMPT = (
    "You extract durable long-term memories from one user/assistant exchange. "
    'Output a JSON object of the form {"memories": ["..."]} containing 0 to 3 '
    "strings. Each string is a self-contained fact, decision, preference, or piece "
    "of context about the USER — their projects, people, or choices — worth "
    "remembering weeks from now, written to stand alone with zero context. Exclude "
    "anything transient: questions, code, debugging chatter, pleasantries, or ideas "
    "the user did not adopt. When in doubt, exclude it. If nothing is durable, "
    'output {"memories": []}. Never invent details not present in the exchange.'
)

# Ollama structured-output schema — forces the model to emit exactly this shape.
# Without it, qwen3 sometimes echoes the task as an object instead of answering.
FORMAT = {
    "type": "object",
    "properties": {
        "memories": {"type": "array", "items": {"type": "string"}, "maxItems": 3}
    },
    "required": ["memories"],
}


def log(msg):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def post_json(url, payload, timeout=60, headers=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def read_last_exchange(transcript_path):
    """Return (last_user_text, last_assistant_text) from the transcript JSONL."""
    user_text, asst_text = "", ""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except Exception:
        return user_text, asst_text
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msg = rec.get("message") or {}
        role = msg.get("role") or rec.get("type")
        text = _content_text(msg.get("content"))
        if not text:
            continue
        if role == "user":
            user_text = text
        elif role == "assistant":
            asst_text = text
    return user_text, asst_text


def extract(exchange):
    body = {
        "model": EXTRACT_MODEL, "think": False, "format": FORMAT, "stream": False,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": exchange},
        ],
        "options": {"temperature": 0},
    }
    resp = post_json(f"{OLLAMA_URL}/api/chat", body, timeout=120)
    data = json.loads(resp["message"]["content"])
    mems = data.get("memories") if isinstance(data, dict) else data
    if not isinstance(mems, list):
        return []
    out = []
    for item in mems:
        s = item if isinstance(item, str) else (
            item.get("text", "") if isinstance(item, dict) else "")
        s = (s or "").strip()
        if 15 <= len(s) <= 500:
            out.append(s)
    return out[:3]


def main():
    if os.path.exists(DISABLE_FILE):
        return
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}
    if event.get("stop_hook_active"):
        return  # avoid re-entrancy
    transcript = event.get("transcript_path")
    cwd = event.get("cwd", "")
    if not transcript or not os.path.exists(transcript):
        return

    # Skip quietly if the brain isn't running.
    try:
        with urllib.request.urlopen(f"{OPENBRAIN_URL}/health", timeout=3) as r:
            if r.status != 200:
                return
    except Exception:
        return

    user_text, asst_text = read_last_exchange(transcript)
    exchange = f"USER:\n{user_text}\n\nASSISTANT:\n{asst_text}".strip()
    if len(exchange) < 60:
        return

    try:
        facts = extract(exchange)
    except Exception as e:
        log(f"[extract-error] {e}")
        return
    if not facts:
        return

    project = os.path.basename(cwd.rstrip("/")) or "unknown"
    headers = {"authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    for fact in facts:
        try:
            res = post_json(f"{OPENBRAIN_URL}/capture", {
                "text": fact,
                "source": "auto-capture",
                "origin_tool": f"claude-code:{project}",
            }, timeout=60, headers=headers)
            log(f"[{'dup' if res.get('duplicate') else 'saved'}] {fact[:110]}")
        except Exception as e:
            log(f"[capture-error] {e} :: {fact[:80]}")


if __name__ == "__main__":
    main()
