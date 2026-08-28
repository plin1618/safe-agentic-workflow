#!/usr/bin/env python3
"""
Loop Engineering — Component 4.1: attention-queue.json helper.

Shared by worktree_manager.sh (parking clusters) and supervisor.sh
(circuit-breaker trips). Human-only items (--risk high, the default) only
ever get appended or marked resolved -- nothing auto-resolves those.

--risk low is the one carve-out: see loop-constraints.md's "Risk tiers"
section for what qualifies (tooling/process choices with no product,
calc, or spec impact). A low-risk item passed with --decision is written
already resolved (status "auto_resolved") instead of parking -- it still
shows up in list/dashboard output for visibility, it just doesn't block.
Never use --risk low for anything loop-constraints.md's high-risk list
covers (calc/tax-math, DDD/Blueprint edits, denylisted paths, blockers).

`add` refuses by default if any `--ticket-ids` value overlaps a ticket ID
on an existing item already `resolved`/`auto_resolved` -- this is the
dedup check that stops a closed decision from re-surfacing as a "new"
item on the next backlog sweep (see loop-constraints.md's backlog-sweep
guidance). It prints the prior resolution and exits non-zero instead of
silently appending a duplicate. Pass --force only when you've confirmed
this is a genuinely distinct issue that happens to share a ticket ID.

Usage:
    python attention_queue.py add --type blocker --cluster-id tier1-cluster-3 \
        --ticket-ids ABC-104 --description "Needs login to test the frontend UI change."

    python attention_queue.py add --type design_decision --risk low \
        --description "supervisor.sh log() double-writes under nohup." \
        --decision "Picked option (b): keep tee, launchers redirect stdout to /dev/null."

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


def find_resolved_match(state, ticket_ids):
    """Return the most recent resolved/auto_resolved item that shares a
    ticket ID with the incoming one, or None. This is the dedup check that
    stops closed decisions from re-surfacing as new attention-queue items --
    see loop-constraints.md's backlog-sweep guidance."""
    if not ticket_ids:
        return None
    incoming = set(ticket_ids)
    matches = [
        i for i in state["items"]
        if i.get("status") in ("resolved", "auto_resolved")
        and incoming & set(i.get("ticket_ids") or [])
    ]
    return matches[-1] if matches else None


def cmd_add(args):
    if args.risk == "low" and not args.decision:
        print("--risk low requires --decision (what was picked and why) -- "
              "a low-risk item still needs its decision on the record, it just "
              "doesn't wait for a human to make it.", file=sys.stderr)
        return 1
    if args.risk == "low" and args.type == "blocker":
        print("--risk low is not valid with --type blocker -- a blocker means "
              "work can't continue without a call; that's never low-risk by "
              "definition. Use design_decision or drop --risk.", file=sys.stderr)
        return 1

    state = load()

    dup = None if args.force else find_resolved_match(state, args.ticket_ids)
    if dup:
        print(
            f"Refusing to add: ticket(s) {', '.join(args.ticket_ids)} already "
            f"covered by {dup['id']} (status: {dup['status']}), resolved "
            f"{dup.get('created_at', '?')}.\n"
            f"Existing resolution: {dup.get('resolution') or '(no resolution text recorded)'}\n"
            "If this is genuinely a new, distinct issue that happens to share "
            "a ticket ID, rerun with --force. Otherwise this is the duplicate "
            "the escalation-discipline dedup check exists to catch -- close "
            "out the underlying ticket/status instead of re-flagging it.",
            file=sys.stderr,
        )
        return 1

    item_id = next_id(state)
    auto = args.risk == "low"
    state["items"].append({
        "id": item_id,
        "type": args.type,
        "cluster_id": args.cluster_id,
        "ticket_ids": args.ticket_ids or [],
        "description": args.description,
        "blocker_category": args.blocker_category,
        "risk": args.risk,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "auto_resolved" if auto else "pending",
        "resolution": args.decision if auto else None,
    })
    save(state)
    if auto:
        print(f"Auto-resolved {item_id} ({args.type}, low-risk) for {args.cluster_id or 'n/a'}: {args.decision}")
    else:
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
    p_add.add_argument("--risk", choices=["low", "high"], default="high",
                        help="high (default): parks and waits for a human. low: requires "
                             "--decision, writes the item already resolved. See "
                             "loop-constraints.md's Risk tiers section before ever passing low.")
    p_add.add_argument("--decision", help="Required with --risk low: what was decided and why.")
    p_add.add_argument("--force", action="store_true",
                        help="Skip the dedup check against existing resolved/auto_resolved "
                             "items sharing a ticket ID. Default is to refuse and print the "
                             "existing resolution instead of silently duplicating it -- only "
                             "use --force when this is genuinely a new, distinct issue.")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", choices=["pending", "resolved", "auto_resolved"])
    p_list.set_defaults(func=cmd_list)

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--id", required=True)
    p_resolve.add_argument("--resolution", required=True)
    p_resolve.set_defaults(func=cmd_resolve)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
