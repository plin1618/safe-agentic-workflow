#!/usr/bin/env bash
# HITL manual merge override.
#
# Bypasses this project's normal merge path (manual GitHub click, or whatever
# mechanical gate you've set up) on DIRECT, EXPLICIT instruction from the
# repo owner given in a live chat session.
#
# This is NOT something an agent should ever invoke on its own initiative,
# as a default, or because a PR "looks safe" or "is just docs." It exists
# for exactly one situation: the repo owner has said, in this session, to
# merge this specific PR number right now. If that didn't just happen,
# don't run this -- open/validate the PR normally and let the human or the
# mechanical gate handle it instead.
#
# If this project has its own sensitivity rules (e.g. a file-based denylist
# for critical code), decide explicitly whether this override applies
# uniformly or should carve those out, and document that decision in
# CLAUDE.md -- this script does not make that call for you.
#
# Every use posts an audit comment on the PR, so "who actually merged this
# and on what authority" stays reconstructable from GitHub history alone --
# doesn't depend on anyone remembering a chat happened.
#
# Usage: hitl-merge.sh <pr-number> [merge-method: squash|merge|rebase]
set -euo pipefail

PR="${1:?Usage: hitl-merge.sh <pr-number> [merge-method]}"
METHOD="${2:-squash}"
REPO_ARGS=()
if [[ -n "${GH_REPO:-}" ]]; then
  REPO_ARGS=(--repo "$GH_REPO")
fi

case "$METHOD" in
  squash|merge|rebase) ;;
  *)
    echo "Invalid merge method: $METHOD (expected squash, merge, or rebase)" >&2
    exit 1
    ;;
esac

gh pr merge "$PR" "${REPO_ARGS[@]}" --"$METHOD" --delete-branch

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh pr comment "$PR" "${REPO_ARGS[@]}" --body "**Manual HITL override merge.** Requested directly by the repo owner in a live chat session, executed by Claude at ${TIMESTAMP} UTC. See CLAUDE.md, 'Manual Merge Override' for the policy this falls under."

echo "Merged PR #${PR} (${METHOD}) and posted audit comment."
