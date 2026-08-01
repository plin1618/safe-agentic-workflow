# loop-budget.md — Budget Declaration

## Basis
This build enforces budget via **turns/iterations, not dollars** — see
`.claude/loop-constraints.md`'s "Budget discipline" section for why
(default assumption: `claude -p` is authenticated via a subscription
login, where usage counts against rate-limit windows, not per-token
billing). If a project confirms it's running on metered API billing
instead, set the cumulative dollar cap below for real and treat it as an
enforced condition, not just an estimate.

## Per-invocation caps (supervisor.sh, per `claude -p` call)
- Max turns: `SUPERVISOR_MAX_TURNS`, default 50
- Max budget: `SUPERVISOR_MAX_BUDGET_USD`, default unset (informational
  only under subscription auth — see Basis above)

## Cumulative caps (`.claude/state/run-ledger.json`, across the whole
supervised run — see Component 4.3 in `loop-engineering-build-spec-v1.md`)
- Trip after 5 consecutive failed invocations
- Trip after the same error signature repeats 5 times in a row
- Trip after 100 total iterations in one run
- Cumulative dollar cap per run: **not enforced by default** (turns/
  iterations are the real breaker). Set `RUN_LEDGER_MAX_COST_USD` only if
  this project is confirmed to run on metered API billing.

## Review cadence
See `docs/BUILD-STATUS.md`'s Comprehension Review section for read/unread
tracking of auto-merged changes. No fixed cadence is enforced — read
unreviewed sensitive-path merges before treating `production_ready` as
meaningful; a rough guide is weekly, not per-merge, so it doesn't become
constant interruption, but also doesn't silently pile up for a month.

## Pre-run cost projection
See `docs/BUILD-STATUS.md`'s Pre-run Cost Projection table — queued
ticket count × tier's historical median tokens/turns, checked before
launching the next tier batch. Under subscription auth this is a
token-usage estimate for planning purposes, not a real dollar figure.
