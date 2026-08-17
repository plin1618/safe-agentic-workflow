#!/usr/bin/env bash
# Loop Engineering — Component 6 auto-trigger, wired via a project's
# settings.local.json Stop hook (filename is a holdover from when this sat
# behind SessionEnd -- left as-is, only the hook key needed to change).
#
# record-cost's own docstring says to call it "once the fixing session's
# transcript is complete (e.g. at session end)" -- but nothing calls it
# there by default, which leaves every fix-history.json entry sitting at
# tokens_used=0 unless something wires this up. SessionEnd only fires
# when a session's process actually terminates -- not when someone just
# opens a new chat and leaves the old one running, which is a common
# habit. Stop fires after every assistant turn instead, so it doesn't
# depend on an explicit close that may never come.
#
# A RUNNING total, not a one-time snapshot: re-records on every matching
# turn rather than stopping once tokens_used is first non-zero. A one-shot
# ("only while still 0") version freezes the number at whatever the
# transcript's total happened to be on the FIRST post-fix turn -- wrong
# the moment any more work happens on the same ticket afterward.
# record-cost's own entry = matches[-1] + overwrite behavior already
# makes repeat calls idempotent-safe (see recurrence_detect.py
# cmd_record_cost) -- it always replaces tokens_used/turns_used with the
# transcript's current cumulative totals, never adds to them, so calling
# it every turn is exactly "keep this number current," not
# "double-count."
#
# The [ -z "$TICKET_PREFIX" ] check keeps the common case (not on a
# ticket branch at all) to two cheap git calls. But re-recording on
# EVERY turn while on a ticket branch, unconditionally, would also
# re-render the dashboard every turn (build_dashboard.py's render-html
# shells out to gh + the Linear API) -- real network cost paid on every
# single response, not something to accept turn after turn. So:
# fix-history.json itself (local, no network) updates every matching
# turn for a true running total, but the dashboard re-render only fires
# on the FIRST recording per ticket (0 -> non-zero) -- later turns keep
# the underlying number fresh without hitting gh/Linear again each time.
#
# Infers the ticket ID PREFIX from the current branch name (this
# template's standing convention: {{TICKET_PREFIX}}-{number}-{description},
# one branch per ticket -- see CLAUDE.md, and post-commit-linear-update.sh
# for the same {{TICKET_PREFIX}} substitution pattern). That prefix is
# then matched against fix-history.json's OWN ticket_id strings -- exact
# match, or prefix match for suffixed IDs like "{{TICKET_PREFIX}}-132-followup"
# (a plain `== $TICKET` exact-match would silently never match those,
# since branch parsing only ever recovers the bare prefix + number).
# Updates every match for the current branch, keyed by its real
# ticket_id, not the truncated branch prefix. Once you switch off that
# branch, the number simply stops updating (frozen at its last real
# total) -- correct, since this hook only ever runs in the context of
# whichever branch is currently checked out.
#
# record-cost itself resolves the transcript across every plausible
# project folder for this repo (main root + nested worktree folders),
# not just escaped(cwd) -- see _default_transcript in
# recurrence_detect.py for why cwd alone isn't reliable when the work
# happened in a worktree.
#
# Deliberately fails soft everywhere -- never intended to block a turn
# or print anything alarming for the (very common) case of a turn that
# didn't touch a ticket at all (doc reading, exploration, chores).
#
# NOTE: {{TICKET_PREFIX}} below must be substituted for your project's
# real ticket prefix (setup-template.sh does this automatically along
# with the rest of the harness's template placeholders).
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "")
TICKET_PREFIX=$(echo "$BRANCH" | grep -oE '^{{TICKET_PREFIX}}-[0-9]+' || true)

[ -z "$TICKET_PREFIX" ] && exit 0

FIX_HISTORY=".claude/state/fix-history.json"
[ -f "$FIX_HISTORY" ] || exit 0

# Two lists out of one read: every tracked ticket_id for this branch
# (always re-recorded), and the subset still at 0 right now (the only ones
# whose recording should trigger a dashboard re-render, since that's the
# "went from nothing to something" moment worth pushing live).
TRACKED_AND_FIRST=$(python -c "
import json
try:
    d = json.load(open('$FIX_HISTORY', encoding='utf-8'))
except Exception:
    raise SystemExit
prefix = '$TICKET_PREFIX'
matched = [f for f in d.get('fixes', [])
           if f.get('ticket_id') == prefix or f.get('ticket_id', '').startswith(prefix + '-')]
tracked = sorted({f['ticket_id'] for f in matched})
first = sorted({f['ticket_id'] for f in matched if f.get('tokens_used', 0) == 0})
print('TRACKED\t' + ','.join(tracked))
print('FIRST\t' + ','.join(first))
" 2>/dev/null)

TRACKED_IDS=$(echo "$TRACKED_AND_FIRST" | awk -F'\t' '$1=="TRACKED"{print $2}')
FIRST_IDS=$(echo "$TRACKED_AND_FIRST" | awk -F'\t' '$1=="FIRST"{print $2}')

[ -z "$TRACKED_IDS" ] && exit 0

NEEDS_RENDER=0
IFS=',' read -ra IDS <<< "$TRACKED_IDS"
for TICKET_ID in "${IDS[@]}"; do
    [ -z "$TICKET_ID" ] && continue
    if python .claude/loop-engineering/recurrence_detect.py record-cost --ticket-id "$TICKET_ID"; then
        case ",$FIRST_IDS," in
            *",$TICKET_ID,"*)
                echo "💰 Stop hook: first cost recorded for $TICKET_ID."
                NEEDS_RENDER=1
                ;;
        esac
    else
        echo "   (record-cost failed or found no transcript for $TICKET_ID -- leaving fix-history.json as-is, not blocking)"
    fi
done

if [ "$NEEDS_RENDER" = "1" ]; then
    python .claude/loop-engineering/build_dashboard.py render >/dev/null 2>&1 || true
    python .claude/loop-engineering/build_dashboard.py render-html >/dev/null 2>&1 || true
    echo "   Dashboard re-rendered."
fi
exit 0
