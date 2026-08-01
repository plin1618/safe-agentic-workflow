#!/usr/bin/env python3
"""
Loop Engineering — Component 4.1: attention-queue.json helper.

Shared by worktree_manager.sh (parking clusters) and supervisor.sh
(circuit-breaker trips). Only ever appends or marks resolved -- nothing
in this build auto-resolves an entry. That's a human action only.

Usage:
    python attention_queue.py add --type blocker --cluster-id tier1-cluster-3 \
        --ticket-ids ABC-104 --description "Needs login to test the frontend UI change."

    python attention_queue.py list [--status pending]

    python attention_queue.py resolve --id aq-001 --resolution "Logged in and tested; unblocked."
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(".claude/state/attention-queue.json")


def load():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"items": []}


def save(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def next_id(state):
    n = len(state["items"]) + 1
    while any(i["id"] == f"aq-{n:03d}" for i in state["items"]):
        n += 1
    return f"aq-{n:03d}"


def cmd_add(args):
    state = load()
    item_id = next_id(state)
    state["items"].append({
        "id": item_id,
        "type": args.type,
        "cluster_id": args.cluster_id,
        "ticket_ids": args.ticket_ids or [],
        "description": args.description,
        "blocker_category": args.blocker_category,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "pending",
        "resolution": None,
    })
    save(state)
    print(f"Added {item_id} ({args.type}) for {args.cluster_id or 'n/a'}: {args.description}")


def cmd_list(args):
    state = load()
    items = state["items"]
    if args.status:
        items = [i for i in items if i["status"] == args.status]
    print(json.dumps(items, indent=2))


def cmd_resolve(args):
    state = load()
    for item in state["items"]:
        if item["id"] == args.id:
            item["status"] = "resolved"
            item["resolution"] = args.resolution
            save(state)
            print(f"Resolved {args.id}. Resume its cluster's worktree using this resolution as context.")
            return 0
    print(f"No attention-queue item with id {args.id}", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--type", required=True, choices=["blocker", "design_decision", "recurring_pattern"])
    p_add.add_argument("--cluster-id")
    p_add.add_argument("--ticket-ids", nargs="*")
    p_add.add_argument("--description", required=True)
    p_add.add_argument("--blocker-category", help="Short category tag for Type E recurrence detection")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", choices=["pending", "resolved"])
    p_list.set_defaults(func=cmd_list)

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--id", required=True)
    p_resolve.add_argument("--resolution", required=True)
    p_resolve.set_defaults(func=cmd_resolve)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
