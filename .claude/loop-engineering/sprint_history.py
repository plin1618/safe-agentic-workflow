#!/usr/bin/env python3
"""
Loop Engineering — Component 5: sprint tracking.

One audit run = one sprint. Call this at the exact same hook point as
audit_tally.py (after every build-fidelity-audit run), not on
supervisor.sh's fresh-kickoff branch — this applies uniformly whether
it's the first audit of a fresh kickoff or a repeat within an ongoing
"reach 2 clean audits" effort.

On every call: increments sprint_number, appends the new entry as
"active" with this run's audit_result, and marks the PREVIOUS sprint's
entry "complete" with a completed_at timestamp.

One-time seeding: if sprint-history.json doesn't exist yet, this script
will start counting from 1 unless you seed it first with the project's
real current sprint number:

    python sprint_history.py seed --sprint 17

Do this once, before the first supervised run, if the project already
has sprint history that predates this tracker -- otherwise the dashboard
will show the wrong sprint number.

Usage:
    python sprint_history.py record --high 0 --critical 0 [--tickets-resolved 3]
    python sprint_history.py seed --sprint 17
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(".claude/state/sprint-history.json")


def _load():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"sprints": []}


def _save(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def cmd_seed(args):
    if STATE_PATH.exists():
        print(f"{STATE_PATH} already exists -- refusing to overwrite. Delete it first if you really want to reseed.", file=sys.stderr)
        return 1
    state = {"sprints": [{
        "sprint_number": args.sprint,
        "started_at": _now(),
        "completed_at": None,
        "status": "active",
        "audit_result": {"high": None, "critical": None},
        "tickets_resolved": 0,
        "ddd_revisions": [],
    }]}
    _save(state)
    print(f"Seeded sprint-history.json starting at sprint {args.sprint}.")
    return 0


def cmd_record(args):
    state = _load()
    if not state["sprints"]:
        print("No seeded sprint-history.json found -- starting from sprint 1. "
              "If this project has prior sprint history, run 'seed --sprint N' "
              "first instead of letting this default silently.", file=sys.stderr)
        next_number = 1
    else:
        prev = state["sprints"][-1]
        prev["status"] = "complete"
        prev["completed_at"] = _now()
        next_number = prev["sprint_number"] + 1

    state["sprints"].append({
        "sprint_number": next_number,
        "started_at": _now(),
        "completed_at": None,
        "status": "active",
        "audit_result": {"high": args.high, "critical": args.critical},
        "tickets_resolved": args.tickets_resolved,
        "ddd_revisions": [],
    })
    _save(state)
    print(f"Sprint {next_number} recorded as active (high={args.high}, critical={args.critical}).")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed")
    p_seed.add_argument("--sprint", type=int, required=True)
    p_seed.set_defaults(func=cmd_seed)

    p_record = sub.add_parser("record")
    p_record.add_argument("--high", type=int, required=True)
    p_record.add_argument("--critical", type=int, required=True)
    p_record.add_argument("--tickets-resolved", type=int, default=0)
    p_record.set_defaults(func=cmd_record)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
