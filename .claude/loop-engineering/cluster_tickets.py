#!/usr/bin/env python3
"""
Loop Engineering — Component 3.1: ticket clustering by file overlap.

Given a batch of Tier-N tickets and the files each one touches (per the
build-fidelity-audit's Feature Scope mapping), groups tickets into
clusters via connected components on a file-overlap graph -- the
automated version of manual file-overlap batching.

Input: a JSON file (or stdin) shaped like:
    [
      {"ticket_id": "ABC-104", "files": ["src/calc/depreciation.py"]},
      {"ticket_id": "ABC-106", "files": ["src/calc/depreciation.py", "src/api/routes.py"]},
      {"ticket_id": "ABC-110", "files": ["src/ui/DashboardCard.tsx"]}
    ]

Output: prints clusters (ticket IDs + the shared file(s) that caused the
grouping) to stdout as JSON, and writes the same to
.claude/state/cluster-status.json with every cluster's status set to
"pending_review" -- per Q2's sanity-check requirement, do NOT create
worktrees from this output until a human has glanced at it. That's a
separate step (worktree_manager.sh create), not automatic here.

Usage:
    python .claude/loop-engineering/cluster_tickets.py tickets.json --tier 1
    cat tickets.json | python .claude/loop-engineering/cluster_tickets.py --tier 1
"""
import argparse
import json
import sys
from pathlib import Path

STATE_PATH = Path(".claude/state/cluster-status.json")


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster(tickets):
    uf = UnionFind(t["ticket_id"] for t in tickets)
    file_owner = {}  # file -> first ticket_id seen touching it
    shared_files = {}  # (ticket_id pair set as frozenset via cluster root) -> set of files

    for t in tickets:
        for f in t["files"]:
            if f in file_owner:
                uf.union(t["ticket_id"], file_owner[f])
            else:
                file_owner[f] = t["ticket_id"]

    groups = {}
    for t in tickets:
        root = uf.find(t["ticket_id"])
        groups.setdefault(root, []).append(t)

    clusters = []
    for idx, (root, members) in enumerate(sorted(groups.items()), start=1):
        member_files = set()
        for m in members:
            member_files.update(m["files"])
        # shared = files touched by 2+ members of this cluster
        touch_count = {}
        for m in members:
            for f in m["files"]:
                touch_count[f] = touch_count.get(f, 0) + 1
        shared = sorted(f for f, c in touch_count.items() if c > 1)
        clusters.append({
            "cluster_id": idx,
            "ticket_ids": sorted(m["ticket_id"] for m in members),
            "shared_files": shared,
            "all_files": sorted(member_files),
        })
    return clusters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Path to tickets JSON; reads stdin if omitted")
    parser.add_argument("--tier", required=True, help="Tier number/label this batch belongs to")
    args = parser.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    tickets = json.loads(raw)
    if not tickets:
        print("No tickets to cluster.")
        return 0

    clusters = cluster(tickets)

    print(f"Tier {args.tier}: {len(clusters)} cluster(s) from {len(tickets)} ticket(s)")
    print(json.dumps(clusters, indent=2))

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("clusters", {})
    for c in clusters:
        key = f"tier{args.tier}-cluster-{c['cluster_id']}"
        state["clusters"][key] = {
            "tier": args.tier,
            "ticket_ids": c["ticket_ids"],
            "shared_files": c["shared_files"],
            "status": "pending_review",
            "worktree_path": None,
        }
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print("\nWritten to .claude/state/cluster-status.json as 'pending_review'.")
    print("Review the clusters above before running worktree_manager.sh create -- "
          "a bad boundary can produce a semantic conflict that git won't catch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
