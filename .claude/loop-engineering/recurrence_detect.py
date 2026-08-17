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
      --tier 1

  # Once the fixing session's transcript is complete (e.g. at session end),
  # record its REAL cost -- reads actual per-turn token usage off the
  # transcript instead of a hand-typed --tokens/--turns guess:
  python recurrence_detect.py record-cost --ticket-id ABC-104
  python recurrence_detect.py record-cost --ticket-id ABC-104 --transcript /path/to/session.jsonl

  python recurrence_detect.py log-feature --feature "MACRS mid-quarter convention" \
      --classification MATCH

  python recurrence_detect.py detect
"""
import argparse
import json
import subprocess
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


# --- transcript-derived cost -----------------------------------------------
#
# log-fix's --tokens/--turns args have existed since this file was written,
# but nothing ever called it with real numbers -- every fix-history.json
# entry sat at tokens_used=0/turns_used=0 because "figure out how many
# tokens this fix cost" had no actual mechanism behind it, just an argparse
# flag waiting for a human to type a number nobody was computing. A Claude
# Code session's own transcript (.jsonl under ~/.claude/projects/<escaped
# cwd>/) already records real per-turn `usage` (input/output/cache tokens)
# on every assistant message -- that's a genuine, non-fabricated signal,
# not an estimate. record-cost reads it and patches it onto an existing
# fix-history.json entry after the fact, so log-fix (called at fix time,
# when the transcript isn't finished yet) and record-cost (called once it
# is, e.g. at session end) stay two separate steps.


def _escape_project_path(path_str):
    """Mirrors Claude Code's own project-folder naming: every character
    that isn't alphanumeric becomes a literal '-', no collapsing of
    consecutive separators."""
    return "".join(c if c.isalnum() else "-" for c in path_str)


def _main_repo_root():
    """Resolves to the MAIN worktree's root, not whichever worktree cwd
    happens to be in -- `git rev-parse --git-common-dir` returns the shared
    .git dir regardless of which worktree you're standing in, so its parent
    is stable across every worktree of this repo. Returns None outside a
    git repo / if git isn't on PATH."""
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                              capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except Exception:
        return None
    common_dir = Path(out)
    if not common_dir.is_absolute():
        common_dir = Path.cwd() / common_dir
    return common_dir.resolve().parent


def _default_transcript():
    """Best-effort: the most recently modified .jsonl across every
    transcript folder plausibly holding this session's history.

    Looking ONLY at escaped(cwd)'s own project folder is correct in the
    common non-worktree case, but wrong for ticket work done in a
    worktree: a session that `cd`s into (or is started at) a worktree
    directory doesn't necessarily get its OWN transcript folder keyed to
    that worktree path. What DOES reliably exist is the main repo's own
    project folder, plus nested per-worktree folders keyed off the main
    repo's escaped path. So: search escaped(cwd)'s own folder (still
    checked first -- correct and cheapest when it exists), escaped(main
    repo root)'s own folder, and every folder whose name starts with
    escaped(main repo root) (catches the nested-worktree convention) --
    then take the single most recently modified .jsonl across all of them.
    Still best-effort, not a guarantee (a completely unrelated concurrent
    session in the same project folder could win) -- always prints which
    file it picked so a caller can sanity-check, and --transcript
    overrides this entirely."""
    projects_dir = Path.home() / ".claude" / "projects"
    search_dirs = set()

    cwd_folder = projects_dir / _escape_project_path(str(Path.cwd().resolve()))
    if cwd_folder.exists():
        search_dirs.add(cwd_folder)

    main_root = _main_repo_root()
    if main_root:
        main_escaped = _escape_project_path(str(main_root))
        main_folder = projects_dir / main_escaped
        if main_folder.exists():
            search_dirs.add(main_folder)
        if projects_dir.exists():
            for child in projects_dir.iterdir():
                if child.is_dir() and child.name.startswith(main_escaped):
                    search_dirs.add(child)

    candidates = [p for d in search_dirs for p in d.glob("*.jsonl")]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _compute_transcript_usage(transcript_path):
    """Sums real usage off every assistant-role message's `usage` field
    (input + output + cache_creation + cache_read tokens) and counts
    assistant turns. Malformed/non-JSON lines are skipped rather than
    failing the whole read -- transcripts can contain non-message event
    types (queue-operation, attachment, mode, etc.), not every line is a
    message."""
    tokens = 0
    turns = 0
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message")
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            turns += 1
            usage = msg.get("usage") or {}
            tokens += (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0)
                       + usage.get("cache_read_input_tokens", 0))
    return tokens, turns


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


# --- record-cost -----------------------------------------------------------
def cmd_record_cost(args):
    if args.transcript:
        transcript = Path(args.transcript)
        if not transcript.exists():
            print(f"Transcript not found: {transcript}", file=sys.stderr)
            return 1
    else:
        transcript = _default_transcript()
        if not transcript:
            print("Couldn't auto-detect a transcript for this project -- pass --transcript explicitly.", file=sys.stderr)
            return 1
        print(f"Auto-detected transcript: {transcript}")

    tokens, turns = _compute_transcript_usage(transcript)
    if tokens == 0 and turns == 0:
        print(f"WARNING: {transcript} yielded 0 tokens/0 turns -- likely the wrong file "
              f"(no assistant messages with a usage field found). Not writing anything.", file=sys.stderr)
        return 1

    history = _load(FIX_HISTORY, {"fixes": []})
    matches = [f for f in history["fixes"] if f["ticket_id"] == args.ticket_id]
    if not matches:
        print(f"No fix-history.json entry for {args.ticket_id} -- log the fix first via 'log-fix', "
              f"then record-cost.", file=sys.stderr)
        return 1
    entry = matches[-1]  # most recent, in case the same ticket was fixed more than once
    entry["tokens_used"] = tokens
    entry["turns_used"] = turns
    entry["cost_source"] = f"transcript:{transcript.name}"
    _save(FIX_HISTORY, history)
    print(f"Recorded {args.ticket_id}: {tokens:,} tokens, {turns} assistant turns (from {transcript.name}).")
    return 0


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

    p_cost = sub.add_parser("record-cost")
    p_cost.add_argument("--ticket-id", required=True)
    p_cost.add_argument("--transcript", default=None,
                         help="Path to a Claude Code session .jsonl. Omit to auto-detect the most "
                              "recently modified transcript in this project's own transcript folder.")
    p_cost.set_defaults(func=cmd_record_cost)

    p_detect = sub.add_parser("detect")
    p_detect.set_defaults(func=cmd_detect)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
