# LOOP.md — Continuous Build Loop

## Intent
Runs the build → audit → tiered fixes → doc sync → repeat cycle
continuously from a single kickoff, escalating to the human only for
blockers, design decisions, and final production-ready review. See
`.claude/loop-constraints.md` for the hard constraints every supervised
session must follow.

## Budget
See `loop-budget.md` for the full budget declaration. Enforcement is
turns/iterations-based (see `.claude/state/run-ledger.json`'s circuit
breaker), not dollar-based, unless this project is confirmed to run on
metered API billing — see `.claude/loop-constraints.md`'s "Budget
discipline" section.

## Human gates
The following always require human approval — never auto-proceed, no
exceptions:
- Any change touching a path in `.github/gate.yaml`'s denylist
- Any blocker (routed to `.claude/state/attention-queue.json`)
- Any design decision, **unless** it clears every bullet in
  `.claude/loop-constraints.md`'s "Risk tiers" section — those narrow,
  no-product-impact cases may be decided and logged in the same call
  (`attention_queue.py add --risk low --decision "..."`) instead of
  parking. Still fully visible afterward, just not blocking. When in
  doubt it's high-risk and parks like before.
- Final production-ready sign-off — reaching `production_ready: true` in
  `.claude/state/audit-tally.json` means the loop stops asking for fixes,
  not that the human's final review is skipped
- Any unresolved recurring pattern (Component 6, Types A-E) — these are
  surfaced as hypotheses for human judgment, never auto-resolved

## Getting notified
`supervisor.sh` itself only logs to `.claude/state/supervisor.log` and the
state JSON files — it does not push anywhere. Don't rely on remembering
to check it. Instead, ask your interactive Claude Code session (the one
you're talking to, not the headless loop) to poll and report: it can
schedule its own periodic wakeups, diff `attention-queue.json` and
`supervisor.log` against what it last saw, and message you in chat the
moment a new pending item lands or the loop stops for any reason
(production-ready, parked, or circuit-breaker tripped). Ask for this
explicitly — "watch the loop and tell me in chat when something needs
me" — it isn't automatic just because `supervisor.sh` is running.

**Exception:** the tier-approval gate specifically (a batch ready to
build but waiting on your explicit sign-off before `worktree_manager.sh
create`) no longer depends on this poll-and-report workaround — it
self-announces via a Linear comment on every ticket in the batch the
moment it stalls, per `.claude/loop-constraints.md`'s "Tier-approval
gate" section. Every other stall reason (a genuine blocker, a design
decision, circuit-breaker trip) still relies on the poll-and-report ask
above.

## Stop conditions
- `production_ready: true` (2 consecutive clean build-fidelity-audit runs)
- The cumulative circuit breaker trips (`.claude/state/run-ledger.json`)
- Every cluster is parked awaiting human input (nothing left to do
  without a human)

## Components
1. `audit-tally` state tracking — `.claude/loop-engineering/audit_tally.py`
2. Conditional auto-merge gate — `.github/workflows/auto-merge-gate.yml`
   + `.github/scripts/auto_merge_gate.py` (project must add its own
   `.github/gate.yaml` — see `.github/gate.yaml.example`)
3. Worktree clustering / parallel execution —
   `.claude/loop-engineering/cluster_tickets.py` +
   `.claude/loop-engineering/worktree_manager.sh`
4. Continuous loop supervisor — `supervisor.sh`
5. Status dashboard — `.claude/loop-engineering/build_dashboard.py`
   (writes `docs/BUILD-STATUS.md`)
6. Recurrence detection (self-learning, Types A-E) —
   `.claude/loop-engineering/recurrence_detect.py`

## Verification status
This is the artifact set a `loop-audit`-style tool would check for.
Creating these files is not the same as having been scored against them —
run an independent audit (e.g. `cobusgreyling/loop-engineering`'s
`loop-audit` tool) once, for a sanity check, before trusting a numeric
"Loop Ready" score.

## Setup in a new project
These files sync via `sync-claude-harness.sh` only for what's inside
`.claude/` (`audit_tally.py`, `cluster_tickets.py`,
`worktree_manager.sh`, `build_dashboard.py`, `recurrence_detect.py`,
`loop-constraints.md`). `LOOP.md`, `loop-budget.md`, `supervisor.sh`, and
everything under `.github/` are **not** in the harness's current
`sync_scope` (`docs/`, `scripts/`, `.github/` are listed in
`.harness-manifest.yml` as deferred) — copy those manually into each new
project until sync support for those domains ships.
