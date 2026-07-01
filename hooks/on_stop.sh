#!/usr/bin/env bash
# Open Brain — Claude Code Stop hook.
# Launches the auto-capture worker fully DETACHED so it never delays Claude,
# then exits 0 immediately (no stdout => does not block the stop).
INPUT="$(cat)"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
( printf '%s' "$INPUT" | /usr/bin/env python3 "$DIR/auto_capture.py" \
    >>"$HOME/.openbrain/auto-capture.log" 2>&1 & )
exit 0
