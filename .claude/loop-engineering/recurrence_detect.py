#!/usr/bin/env python3
"""
Loop Engineering — Component 6: recurrence detection (self-learning, Types A-E).

Logs fixes and feature classifications over time, then flags five distinct
recurrence patterns so they get routed to human judgment as a
"recurring_pattern" attention-queue entry instead of being silently
re-patched as just another one-off ticket. This module SUGGESTS a
hypothesis; it never diagnoses or auto-resolves anything.

  Type A — same-target recurrence: same feature/file, 2+ fixes in the
           last 3 audit cycles.
  Type B — cross-target pattern recurrence: matching/related issue_type,
           2+ DIFFERENT features/files. Stronger signal than A — points
           at a missing/unclear convention, not one fragile feature.
  Type C — efficiency outliers: tokens/turns > ~2-3x the tier median on
           an otherwise-clean (not already A/B-flagged) outcome.
  Type D — oscillation: a feature's classification history shows
           MATCH -> REGRESSION -> MATCH -> REGRESSION, at least two full
           cycles. Stronger and more specific than Type A's plain
           fix-count — the fix has to have actually worked before
           breaking again.
  Type E — recurring blocker categories: the same blocker_category
           appears 3+ times in attention-queue.json, including resolved
           entries (history isn't deleted).

Usage:
  python recurrence_detect.py log-fix --ticket-id ABC-104 \
      --files src/calc/depreciation.py --classification REGRESSION \
      --feature "MACRS mid-quarter convention" \
      --issue-type "missing edge-case handling: partial-year disposition" \
      --tier 1 --tokens 84852 --turns 22

  python recurrence_detect.py log-feature --feature "MACRS mid-quarter convention" \
      --classification MATCH

  python recurrence_detect.py detect
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FIX_HISTORY = Path(".claude/state/fix-history.json")
FEATURE_HISTORY = Path(".claude/state/feature-history.json")
AUDIT_TALLY = Path(".claude/state/audit-tally.json")
ATTENTION_QUEUE = Path(".claude/state/attention-queue.json")


def _load(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _current_cycle():
    tally = _load(AUDIT_TALLY, {"audit_history": []})
    return max(len(tally.get("audit_history", [])), 1)


def _add_attention(item_type, description, extra=None):
    state = _load(ATTENTION_QUEUE, {"items": []})
    n = len(state["items"]) + 1
    while any(i["id"] == f"aq-{n:03d}" for i in state["items"]):
        n += 1
    item = {
        "id": f"aq-{n:03d}",
        "type": item_type,
        "cluster_id": None,
        "ticket_ids": [],
        "description": description,
        "created_at": _now(),
        "status": "pending",
        "resolution": None,
    }
    if extra:
        item.update(extra)
    state["items"].append(item)
    _save(ATTENTION_QUEUE, state)
    print(f"Flagged {item['id']}: {description}")


# --- log-fix -----------------------------------------------------------
def cmd_log_fix(args):
    history = _load(FIX_HISTORY, {"fixes": []})
    cycle = args.audit_cycle or _current_cycle()
    history["fixes"].append({
        "ticket_id": args.ticket_id,
        "timestamp": _now(),
        "audit_cycle": cycle,
        "files_touched": args.files,
        "audit_classification": args.classification,
        "feature": args.feature,
        "issue_type": args.issue_type,
        "tier": args.tier,
        "tokens_used": args.tokens,
        "turns_used": args.turns,
    })
    _save(FIX_HISTORY, history)
    print(f"Logged fix for {args.ticket_id} (cycle {cycle}).")


# --- log-feature ---------------------------------------------------------
def cmd_log_feature(args):
    history = _load(FEATURE_HISTORY, {"features": {}})
    cycle = args.audit_cycle or _current_cycle()
    entry = history["features"].setdefault(args.feature, {"classification_history": []})
    entry["classification_history"].append({
        "audit_cycle": cycle,
        "classification": args.classification,
        "date": _now(),
    })
    _save(FEATURE_HISTORY, history)
    print(f"Logged {args.feature} classification={args.classification} (cycle {cycle}).")


# --- detect ---------------------------------------------------------------
def detect_type_a(fixes, current_cycle):
    """Same feature/file, 2+ fixes in the last 3 audit cycles."""
    hits = []
    recent = [f for f in fixes if f["audit_cycle"] >= current_cycle - 2]
    by_feature = {}
    for f in recent:
        by_feature.setdefault(f["feature"], []).append(f)
    for feature, entries in by_feature.items():
        if len(entries) >= 2:
            hits.append({
                "feature": feature,
                "tickets": [e["ticket_id"] for e in entries],
                "cycles": sorted({e["audit_cycle"] for e in entries}),
            })
    return hits


def detect_type_b(fixes, current_cycle):
    """Matching/related issue_type across 2+ DIFFERENT features/files."""
    hits = []
    recent = [f for f in fixes if f["audit_cycle"] >= current_cycle - 2]
    by_issue = {}
    for f in recent:
        by_issue.setdefault(f["issue_type"], []).append(f)
    for issue_type, entries in by_issue.items():
        distinct_features = {e["feature"] for e in entries}
        if len(distinct_features) >= 2:
            hits.append({
                "issue_type": issue_type,
                "features": sorted(distinct_features),
                "tickets": [e["ticket_id"] for e in entries],
            })
    return hits


def detect_type_c(fixes, flagged_tickets):
    """tokens/turns > ~2-3x the tier median, on an otherwise-clean outcome."""
    hits = []
    by_tier = {}
    for f in fixes:
        by_tier.setdefault(f["tier"], []).append(f)
    for tier, entries in by_tier.items():
        tokens = sorted(e["tokens_used"] for e in entries if e["tokens_used"])
        if len(tokens) < 3:
            continue  # not enough data for a meaningful median yet
        median = tokens[len(tokens) // 2]
        for e in entries:
            if e["ticket_id"] in flagged_tickets:
                continue
            if e["tokens_used"] and median and e["tokens_used"] >= 2.5 * median:
                hits.append({
                    "ticket_id": e["ticket_id"],
                    "tier": tier,
                    "tokens_used": e["tokens_used"],
                    "tier_median": median,
                })
    return hits


def detect_type_d(feature_history):
    """MATCH -> REGRESSION -> MATCH -> REGRESSION, at least two full cycles."""
    hits = []
    for feature, data in feature_history.get("features", {}).items():
        seq = [c["classification"] for c in data["classification_history"]]
        # Look for the alternating pattern anywhere in the sequence.
        oscillations = 0
        for i in range(len(seq) - 1):
            if {seq[i], seq[i + 1]} == {"MATCH", "REGRESSION"}:
                oscillations += 1
        if oscillations >= 3:  # MATCH-REGRESSION-MATCH-REGRESSION = 3 transitions
            hits.append({"feature": feature, "sequence": seq})
    return hits


def detect_type_e(attention_queue):
    """Same blocker_category appears 3+ times, including resolved entries."""
    hits = []
    counts = {}
    for item in attention_queue.get("items", []):
        cat = item.get("blocker_category")
        if cat:
            counts.setdefault(cat, []).append(item["id"])
    for cat, ids in counts.items():
        if len(ids) >= 3:
            hits.append({"blocker_category": cat, "occurrences": ids})
    return hits


def cmd_detect(args):
    fixes = _load(FIX_HISTORY, {"fixes": []})["fixes"]
    feature_history = _load(FEATURE_HISTORY, {"features": {}})
    attention_queue = _load(ATTENTION_QUEUE, {"items": []})
    current_cycle = _current_cycle()

    type_a = detect_type_a(fixes, current_cycle)
    type_b = detect_type_b(fixes, current_cycle)
    flagged_tickets = {t for h in type_a for t in h["tickets"]} | {t for h in type_b for t in h["tickets"]}
    type_c = detect_type_c(fixes, flagged_tickets)
    type_d = detect_type_d(feature_history)
    type_e = detect_type_e(attention_queue)

    # De-dupe against already-flagged recurring_pattern entries so re-running
    # detect() doesn't spam duplicate attention-queue items every audit.
    already_flagged = {
        item["description"] for item in attention_queue.get("items", [])
        if item["type"] == "recurring_pattern"
    }

    for h in type_a:
        desc = f"Type A (same-target recurrence): '{h['feature']}' fixed {len(h['tickets'])}x in cycles {h['cycles']} ({', '.join(h['tickets'])}). Hypothesis: the fix isn't addressing root cause, or this feature is genuinely fragile."
        if desc not in already_flagged:
            _add_attention("recurring_pattern", desc, {"pattern_type": "A"})

    for h in type_b:
        desc = f"Type B (cross-target pattern): issue_type '{h['issue_type']}' recurred across {len(h['features'])} different features ({', '.join(h['features'])}) — tickets {', '.join(h['tickets'])}. Hypothesis: a missing or unclear convention, not a single fragile feature."
        if desc not in already_flagged:
            _add_attention("recurring_pattern", desc, {"pattern_type": "B"})

    for h in type_c:
        desc = f"Type C (efficiency outlier): {h['ticket_id']} (tier {h['tier']}) used {h['tokens_used']} tokens vs. tier median {h['tier_median']}. Hypothesis: missing reference material or unclear pattern docs causing context rediscovery."
        if desc not in already_flagged:
            _add_attention("recurring_pattern", desc, {"pattern_type": "C"})

    for h in type_d:
        desc = f"Type D (oscillation): '{h['feature']}' classification sequence {h['sequence']} shows repeated MATCH/REGRESSION flips. Hypothesis: a clustering/merge conflict or doc-sync drift, not a skill gap."
        if desc not in already_flagged:
            _add_attention("recurring_pattern", desc, {"pattern_type": "D"})

    for h in type_e:
        desc = f"Type E (recurring blocker): blocker_category '{h['blocker_category']}' occurred {len(h['occurrences'])}x ({', '.join(h['occurrences'])}). Hypothesis: a one-time structural fix to the blocker itself (e.g. persistent test-auth session, pre-answered decision in the DDD)."
        if desc not in already_flagged:
            _add_attention("recurring_pattern", desc, {"pattern_type": "E"})

    total = len(type_a) + len(type_b) + len(type_c) + len(type_d) + len(type_e)
    print(f"Detection complete: A={len(type_a)} B={len(type_b)} C={len(type_c)} D={len(type_d)} E={len(type_e)} (total {total})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_fix = sub.add_parser("log-fix")
    p_fix.add_argument("--ticket-id", required=True)
    p_fix.add_argument("--files", nargs="+", required=True, dest="files")
    p_fix.add_argument("--classification", required=True, help="e.g. REGRESSION, GAP, MATCH")
    p_fix.add_argument("--feature", required=True)
    p_fix.add_argument("--issue-type", required=True)
    p_fix.add_argument("--tier", required=True)
    p_fix.add_argument("--tokens", type=int, default=0)
    p_fix.add_argument("--turns", type=int, default=0)
    p_fix.add_argument("--audit-cycle", type=int, default=None)
    p_fix.set_defaults(func=cmd_log_fix)

    p_feat = sub.add_parser("log-feature")
    p_feat.add_argument("--feature", required=True)
    p_feat.add_argument("--classification", required=True)
    p_feat.add_argument("--audit-cycle", type=int, default=None)
    p_feat.set_defaults(func=cmd_log_feature)

    p_detect = sub.add_parser("detect")
    p_detect.set_defaults(func=cmd_detect)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
