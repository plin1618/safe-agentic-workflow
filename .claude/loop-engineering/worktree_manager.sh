#!/usr/bin/env bash
# Loop Engineering — Component 3.2/3.5: worktree assignment + cleanup.
#
# Reads/writes .claude/state/cluster-status.json. Does not touch tickets
# or run SAW commands itself -- that happens inside each worktree, driven
# by supervisor.sh. This script only manages the worktrees.
set -euo pipefail

STATE_FILE=".claude/state/cluster-status.json"
PROJECT_NAME="$(basename "$(git rev-parse --show-toplevel)")"

usage() {
  cat <<EOF
Usage:
  worktree_manager.sh create <cluster-key>     # e.g. tier1-cluster-3
  worktree_manager.sh park <cluster-key> <blocker|design_decision> "<description>"
  worktree_manager.sh complete <cluster-key>   # removes worktree after merge confirms
  worktree_manager.sh sweep                    # reap stale/orphaned worktrees
EOF
  exit 1
}

[ $# -ge 1 ] || usage
cmd="$1"; shift

read_status() {
  python -c "
import json
state = json.load(open('$STATE_FILE'))
print(state['clusters'].get('$1', {}).get('status', ''))
" 2>/dev/null || echo ""
}

set_status() {
  local key="$1" status="$2" worktree_path="${3:-}"
  python - "$key" "$status" "$worktree_path" <<'PYEOF'
import json, sys
from pathlib import Path
key, status, worktree_path = sys.argv[1], sys.argv[2], sys.argv[3]
p = Path(".claude/state/cluster-status.json")
state = json.loads(p.read_text()) if p.exists() else {"clusters": {}}
state.setdefault("clusters", {}).setdefault(key, {})
state["clusters"][key]["status"] = status
if worktree_path:
    state["clusters"][key]["worktree_path"] = worktree_path
p.write_text(json.dumps(state, indent=2) + "\n")
PYEOF
}

case "$cmd" in
  create)
    key="${1:?cluster key required, e.g. tier1-cluster-3}"
    wt_path="../${PROJECT_NAME}-${key}"
    branch="${key}"
    git worktree add "$wt_path" -b "$branch"
    set_status "$key" "in_progress" "$wt_path"
    echo "Worktree created at $wt_path on branch $branch."
    echo "Run /start-work -> implement -> /pre-pr per ticket inside that worktree, per .claude/loop-constraints.md."
    ;;

  park)
    key="${1:?cluster key required}"
    type="${2:?blocker or design_decision required}"
    desc="${3:?description required}"
    set_status "$key" "parked_${type}"
    python .claude/loop-engineering/attention_queue.py add \
      --type "$type" --cluster-id "$key" --description "$desc"
    echo "Parked $key as parked_${type}. Continue with the next unstarted cluster."
    ;;

  complete)
    key="${1:?cluster key required}"
    status="$(read_status "$key")"
    if [ "$status" != "in_progress" ] && [ "$status" != "ready_for_qas" ]; then
      echo "Refusing to remove worktree for $key: status is '$status', not in_progress/ready_for_qas." >&2
      exit 1
    fi
    wt_path="$(python -c "
import json
state = json.load(open('$STATE_FILE'))
print(state['clusters'].get('$key', {}).get('worktree_path', ''))
")"
    if [ -n "$wt_path" ] && [ -d "$wt_path" ]; then
      git worktree remove "$wt_path"
    fi
    set_status "$key" "complete"
    echo "$key marked complete, worktree removed."
    ;;

  sweep)
    # Reap worktrees whose cluster is complete but the dir still exists,
    # or parked_* for >24h with no open attention-queue item (resolved but
    # never cleaned up). Never touch an actively-parked cluster with an
    # open attention-queue item.
    python - <<'PYEOF'
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

cluster_state = json.loads(Path(".claude/state/cluster-status.json").read_text()) if Path(".claude/state/cluster-status.json").exists() else {"clusters": {}}
aq_state = json.loads(Path(".claude/state/attention-queue.json").read_text()) if Path(".claude/state/attention-queue.json").exists() else {"items": []}

open_cluster_ids = {i["cluster_id"] for i in aq_state["items"] if i["status"] == "pending" and i.get("cluster_id")}

for key, c in cluster_state.get("clusters", {}).items():
    wt = c.get("worktree_path")
    if not wt or not Path(wt).exists():
        continue
    status = c.get("status", "")
    if status == "complete":
        print(f"Reaping completed worktree: {key} ({wt})")
        subprocess.run(["git", "worktree", "remove", wt], check=False)
    elif status.startswith("parked_") and key not in open_cluster_ids:
        print(f"Reaping orphaned parked worktree (resolved, never cleaned up): {key} ({wt})")
        subprocess.run(["git", "worktree", "remove", wt], check=False)
    # else: leave it -- actively parked with an open attention-queue item,
    # or in_progress/ready_for_qas. When in doubt, don't guess.
PYEOF
    git worktree prune
    echo "Sweep complete."
    ;;

  *)
    usage
    ;;
esac
