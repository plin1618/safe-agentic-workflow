# Loop Constraints — read this at the start of every supervised session

These are hard constraints, not suggestions. Read this file before doing any
work in a session started by `supervisor.sh` or any other unattended/loop
invocation.

## Scope discipline
- Prefer the smallest possible diff that correctly resolves the ticket.
- Never touch a file outside the ticket's identified scope unless the fix
  genuinely requires it — if it does, note why in the PR description.

## Path restrictions
- Never edit anything matching `.github/gate.yaml`'s denylist without
  explicit human approval first. This applies even if the edit seems safe
  or trivial — the denylist exists specifically because "safe or trivial"
  is a judgment call that shouldn't be made unilaterally on these paths.
- If a ticket's fix appears to require touching a denylisted path, park
  the cluster and write an `attention-queue.json` entry rather than
  proceeding.

## Process discipline
- Always work through `/start-work {ticket-id}` → implement → `/pre-pr`
  for every ticket. Never skip this sequence, even for a fix that looks
  obvious — this is what makes QAS actually run as an independent
  reviewer instead of the implementer self-declaring done.
- Never self-report QAS approval. If `/pre-pr` doesn't produce genuine,
  independent QAS evidence (e.g. a Linear comment posted by the QAS
  subagent), treat the ticket as not ready to merge.

## Escalation discipline
- When uncertain whether something needs human input, escalate (write to
  `attention-queue.json`) rather than guess. A false escalation costs a
  few minutes of human review; false confidence costs correctness.

## Budget discipline
- Budget enforcement in this build is **turns/iterations-based, not
  dollar-based** — `run-ledger.json`'s circuit breaker trips on
  consecutive failures, a repeating error signature, or a total-iteration
  cap (see `loop-budget.md`). Any dollar figures surfaced in
  `docs/BUILD-STATUS.md` are informational token-usage estimates only,
  not an enforced cap, unless the project has confirmed it's running on
  metered API billing rather than a flat-rate subscription.
- **Auth-mode pre-flight check, before any unattended run:** confirm
  whether the `claude` CLI is authenticated via a subscription login or
  an API key (`ANTHROPIC_API_KEY`). Under a subscription, usage counts
  against rate-limit windows (with a reset time), not per-token billing —
  `supervisor.sh`'s rate-limit-reset parsing is written for exactly that
  case. Under an API key, real per-token cost accrues and the dollar
  fields in `loop-budget.md` become meaningful and should be set for
  real, not left as an estimate.
