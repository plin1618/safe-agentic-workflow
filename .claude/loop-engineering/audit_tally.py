#!/usr/bin/env python3
"""
Loop Engineering — Component 1: audit-tally state tracking.

Call this once, at the end of a build-fidelity-audit run, with that run's
findings counts. It appends to .claude/state/audit-tally.json, tracks the
consecutive-clean streak, and flips production_ready once two audits in a
row come back with zero High/Critical findings.

Usage:
    python .claude/loop-engineering/audit_tally.py \
        --sprint 17 \
        --high 0 --critical 0 \
        --ticket-refs PEN-104 PEN-106

Exits 0 always (state tracking should never fail the audit run itself);
prints the resulting production_ready status to stdout so callers can
surface it without re-reading the file.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(".claude/state/audit-tally.json")


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "audit_history": [],
        "consecutive_clean": 0,
        "production_ready": False,
        "last_updated": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprint", required=True, help="Sprint number/label this audit belongs to")
    parser.add_argument("--high", type=int, required=True, help="High-severity finding count")
    parser.add_argument("--critical", type=int, required=True, help="Critical-severity finding count")
    parser.add_argument("--ticket-refs", nargs="*", default=[], help="Linear ticket IDs opened from this run")
    args = parser.parse_args()

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = load_state()

    clean = args.high == 0 and args.critical == 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    state["audit_history"].append({
        "timestamp": now,
        "sprint": str(args.sprint),
        "high_count": args.high,
        "critical_count": args.critical,
        "clean": clean,
        "ticket_refs": args.ticket_refs,
    })

    state["consecutive_clean"] = state.get("consecutive_clean", 0) + 1 if clean else 0
    state["production_ready"] = state["consecutive_clean"] >= 2
    state["last_updated"] = now

    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print(f"audit-tally updated: clean={clean}, consecutive_clean={state['consecutive_clean']}, "
          f"production_ready={state['production_ready']}")
    if state["production_ready"]:
        print("PRODUCTION_READY: two consecutive clean audits — see LOOP.md stop conditions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
