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
- Any blocker or design decision (routed to `.claude/state/attention-queue.json`)
- Final production-ready sign-off — reaching `production_ready: true` in
  `.claude/state/audit-tally.json` means the loop stops asking for fixes,
  not that the human's final review is skipped
- Any unresolved recurring pattern (Component 6, Types A-E) — these are
  surfaced as hypotheses for human judgment, never auto-resolved

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
