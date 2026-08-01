#!/usr/bin/env python3
"""
Loop Engineering — Component 5: status dashboard.

Reads .claude/state/{audit-tally,cluster-status,attention-queue,
fix-history,sprint-history,review-ledger}.json and renders
docs/BUILD-STATUS.md. Auto-generated -- don't hand-edit the output, it's
overwritten on every regeneration.

Call this at the end of every build-fidelity-audit run and after every
cluster-status.json write (worktree_manager.sh already calls the pieces
that change cluster state -- wire a call to this script after those
points in your project's own hook/skill).

Usage:
    python build_dashboard.py render [--feature-scope path/to/ddd-or-blueprint.md]
    python build_dashboard.py update-review-ledger   # requires `gh` CLI on PATH
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".claude/state")
OUT_PATH = Path("docs/BUILD-STATUS.md")


def _load(name, default):
    p = STATE_DIR / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def _median(values):
    values = sorted(v for v in values if v)
    if not values:
        return 0
    return values[len(values) // 2]


def cmd_render(args):
    audit_tally = _load("audit-tally.json", {"audit_history": [], "consecutive_clean": 0, "production_ready": False})
    cluster_status = _load("cluster-status.json", {"clusters": {}})
    attention_queue = _load("attention-queue.json", {"items": []})
    fix_history = _load("fix-history.json", {"fixes": []})
    sprint_history = _load("sprint-history.json", {"sprints": []})
    review_ledger = _load("review-ledger.json", {"merges": [], "last_review_session": None})

    clusters = cluster_status.get("clusters", {})
    by_tier = {}
    for key, c in clusters.items():
        by_tier.setdefault(c.get("tier"), []).append(c)

    tiers_incomplete = sorted(
        (t for t, cs in by_tier.items() if any(c["status"] != "complete" for c in cs)),
        key=lambda t: (str(t))
    )
    current_tier = tiers_incomplete[0] if tiers_incomplete else (sorted(by_tier.keys())[-1] if by_tier else "n/a")

    current_sprint = sprint_history["sprints"][-1] if sprint_history["sprints"] else None
    current_ddd_rev = current_sprint["ddd_revisions"][-1] if current_sprint and current_sprint["ddd_revisions"] else "n/a"

    pending_items = [i for i in attention_queue["items"] if i["status"] == "pending"]
    blockers = [i for i in pending_items if i["type"] == "blocker"]
    design_decisions = [i for i in pending_items if i["type"] == "design_decision"]
    recurring = [i for i in pending_items if i["type"] == "recurring_pattern"]

    unreviewed = [m for m in review_ledger["merges"] if not m.get("reviewed")]
    unreviewed_sensitive = [m for m in unreviewed if m.get("touches_sensitive_path")]

    last_audit = audit_tally["audit_history"][-1] if audit_tally["audit_history"] else None

    # Token/turn usage
    tokens_by_tier = {}
    for f in fix_history["fixes"]:
        tokens_by_tier.setdefault(f["tier"], []).append(f["tokens_used"])
    total_tokens = sum(f["tokens_used"] for f in fix_history["fixes"])
    total_turns = sum(f["turns_used"] for f in fix_history["fixes"])

    lines = []
    lines.append("# Build Status — auto-generated, do not hand-edit")
    lines.append("")
    lines.append(f"Last updated: {_now_placeholder()}")
    lines.append("")
    lines.append("## Current position")
    lines.append(f"**Sprint {current_sprint['sprint_number'] if current_sprint else 'n/a'}, "
                  f"DDD rev {current_ddd_rev}, Tier {current_tier}** — "
                  f"{sum(1 for c in clusters.values() if c['status'] == 'complete')} complete, "
                  f"{sum(1 for c in clusters.values() if c['status'] == 'in_progress')} in progress, "
                  f"{sum(1 for c in clusters.values() if str(c['status']).startswith('parked_'))} parked")
    lines.append("")
    lines.append("## Comprehension review")
    lines.append(f"- Auto-merged since your last review: {len(review_ledger['merges'])} PRs, {len(unreviewed)} unread")
    if unreviewed_sensitive:
        lines.append(f"- **{len(unreviewed_sensitive)} unread auto-merges touch sensitive paths** — read these before treating anything downstream as trustworthy")
    lines.append(f"- Last review session: {review_ledger.get('last_review_session') or 'never'}")
    lines.append("")
    lines.append("## Production readiness")
    lines.append(f"- Consecutive clean audits: {audit_tally.get('consecutive_clean', 0)} of 2 needed")
    if last_audit:
        lines.append(f"- Last audit: {last_audit['timestamp']} — {last_audit['high_count']} High, {last_audit['critical_count']} Critical")
    lines.append(f"- production_ready: **{audit_tally.get('production_ready', False)}**")
    lines.append("")
    lines.append("## Sprint history")
    lines.append("| Sprint | Status | Started | Completed | Audit result | Tickets resolved |")
    lines.append("|---|---|---|---|---|---|")
    for s in sprint_history["sprints"]:
        lines.append(f"| {s['sprint_number']} | {s['status']} | {s['started_at']} | {s['completed_at'] or '-'} | "
                      f"H:{s['audit_result'].get('high')} C:{s['audit_result'].get('critical')} | {s['tickets_resolved']} |")
    lines.append("")
    lines.append("## Token/turn usage")
    lines.append(f"- Total this cycle: {total_tokens} tokens, {total_turns} turns, across {len(fix_history['fixes'])} tickets")
    for tier, toks in sorted(tokens_by_tier.items(), key=lambda kv: str(kv[0])):
        lines.append(f"- Tier {tier} median tokens/ticket: {_median(toks)}")
    lines.append("")
    lines.append("## Pre-run cost projection")
    lines.append("Projected next-tier cost = queued tickets × that tier's historical median tokens/ticket "
                  "(informational token-usage estimate, not a real dollar figure under subscription auth "
                  "-- see loop-budget.md).")
    lines.append("")
    lines.append("| Tier | Tickets pending_review | Historical median tokens/ticket | Projected total |")
    lines.append("|---|---|---|---|")
    pending_by_tier = {}
    for c in clusters.values():
        if c["status"] == "pending_review":
            pending_by_tier[c["tier"]] = pending_by_tier.get(c["tier"], 0) + len(c["ticket_ids"])
    for tier, count in sorted(pending_by_tier.items(), key=lambda kv: str(kv[0])):
        median = _median(tokens_by_tier.get(tier, []))
        lines.append(f"| {tier} | {count} | {median} | {median * count} |")
    lines.append("")
    lines.append("## Needs your attention")
    lines.append(f"- Blockers: {len(blockers)}")
    lines.append(f"- Design decisions: {len(design_decisions)}")
    lines.append(f"- Recurring patterns flagged: {len(recurring)}")
    lines.append("")
    lines.append("| Type | Description |")
    lines.append("|---|---|")
    for item in pending_items:
        lines.append(f"| {item['type']} | {item['description']} |")
    lines.append("")
    lines.append("(full detail in `.claude/state/attention-queue.json`)")
    lines.append("")

    if args.feature_scope:
        lines.append("## By feature")
        lines.append(f"See `{args.feature_scope}`'s Feature Scope table directly -- this dashboard "
                      "doesn't parse project-specific DDD/blueprint formats generically.")
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


def _now_placeholder():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def cmd_update_review_ledger(args):
    """Queries GitHub for PRs merged since the last run carrying the
    auto-merge-gate's success comment, cross-references gate.yaml's
    denylist, and appends new review-ledger.json entries. Requires the
    `gh` CLI authenticated on PATH. Never marks an entry reviewed --
    that's a manual action only.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", "50",
             "--json", "number,mergedAt,headRefName,files"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Skipping review-ledger update -- `gh` CLI unavailable or failed: {e}", file=sys.stderr)
        return 0

    prs = json.loads(result.stdout)
    review_ledger = _load("review-ledger.json", {"merges": [], "last_review_session": None})
    known_prs = {m["pr_number"] for m in review_ledger["merges"]}

    gate_path = Path(".github/gate.yaml")
    denylist = []
    if gate_path.exists():
        import yaml
        denylist = (yaml.safe_load(gate_path.read_text()) or {}).get("denylist", [])

    import fnmatch
    added = 0
    for pr in prs:
        if pr["number"] in known_prs:
            continue
        comments = subprocess.run(
            ["gh", "pr", "view", str(pr["number"]), "--json", "comments"],
            capture_output=True, text=True,
        )
        if comments.returncode != 0:
            continue
        body = comments.stdout
        if "Auto-merge gate" not in body:
            continue  # not an auto-merged PR, skip
        touches_sensitive = any(
            fnmatch.fnmatch(f["path"], pattern)
            for f in pr.get("files", [])
            for pattern in denylist
        )
        review_ledger["merges"].append({
            "pr_number": pr["number"],
            "ticket_id": None,
            "merged_at": pr["mergedAt"],
            "touches_sensitive_path": touches_sensitive,
            "reviewed": False,
            "reviewed_at": None,
        })
        added += 1

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "review-ledger.json").write_text(json.dumps(review_ledger, indent=2) + "\n", encoding="utf-8")
    print(f"review-ledger.json updated: {added} new merge(s) recorded.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render")
    p_render.add_argument("--feature-scope", help="Path to the DDD/blueprint file with the Feature Scope table (referenced, not parsed)")
    p_render.set_defaults(func=cmd_render)

    p_review = sub.add_parser("update-review-ledger")
    p_review.set_defaults(func=cmd_update_review_ledger)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
