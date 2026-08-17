#!/usr/bin/env python3
"""
Loop Engineering — Component 4.4: chat-surfacing watcher.

supervisor.sh runs headless and only writes to .claude/state/*.json and
supervisor.log -- it never pushes anywhere. This script is the other half:
call it from an interactive Claude Code session (the one polling via its
own ScheduleWakeup, per LOOP.md's "Getting notified" section) and it
reports only what's NEW since the last call, using a cursor file so
nothing needs to be remembered across wakeups. Nothing here auto-resolves
anything -- it's read-only, purely for surfacing.

Usage:
    python watch_supervisor.py check

Exits 0 always; prints a JSON report. `has_news: true` means something
changed and is worth a chat message -- new pending items, a fresh
auto_resolved item since last check, or the supervisor stopping (any
reason: production_ready, parked, circuit breaker, or a hard error).
`has_news: false` means nothing changed, don't message the user.
"""
import json
import sys
from pathlib import Path

STATE_DIR = Path(".claude/state")
ATTENTION_QUEUE = STATE_DIR / "attention-queue.json"
SUPERVISOR_LOG = STATE_DIR / "supervisor.log"
CURSOR_PATH = STATE_DIR / "watcher-cursor.json"

STOP_MARKERS = (
    "production_ready: true",
    "Everything is parked awaiting the attention queue",
    "State unchanged for",
    "CIRCUIT BREAKER TRIPPED",
    "Stopping rather than guessing",
)


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def cmd_check(_args):
    cursor = load_json(CURSOR_PATH, {"seen_item_ids": [], "log_byte_offset": 0})
    seen = set(cursor["seen_item_ids"])

    aq = load_json(ATTENTION_QUEUE, {"items": []})
    all_items = aq["items"]
    new_items = [i for i in all_items if i["id"] not in seen]

    new_stop_lines = []
    log_size = SUPERVISOR_LOG.stat().st_size if SUPERVISOR_LOG.exists() else 0
    if SUPERVISOR_LOG.exists() and log_size >= cursor["log_byte_offset"]:
        with SUPERVISOR_LOG.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(cursor["log_byte_offset"])
            new_log_text = f.read()
        new_stop_lines = [
            line for line in new_log_text.splitlines()
            if any(marker in line for marker in STOP_MARKERS)
        ]
    else:
        # Log shrank/rotated -- don't try to diff, just resync from the end.
        new_log_text = ""

    report = {
        "has_news": bool(new_items) or bool(new_stop_lines),
        "new_pending": [i for i in new_items if i["status"] == "pending"],
        "new_auto_resolved": [i for i in new_items if i["status"] == "auto_resolved"],
        "stop_events": new_stop_lines,
    }

    cursor["seen_item_ids"] = [i["id"] for i in all_items]
    cursor["log_byte_offset"] = log_size
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(cursor, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check")
    p_check.set_defaults(func=cmd_check)
    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
