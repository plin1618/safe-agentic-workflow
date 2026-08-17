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
- **Default to `--risk high`** (the flag's default) on every
  `attention_queue.py add` call. Only pass `--risk low` when the item
  clears every bullet in "Risk tiers" below. When genuinely unsure which
  tier applies, that uncertainty itself means high — escalate.

## Risk tiers
Not every `attention_queue.py add` needs to park and wait. A **low-risk**
item can be decided and logged in the same call (`--risk low --decision
"..."`) instead of blocking a human. This is a narrow carve-out, not a
default — most design decisions and all blockers stay high-risk.

**Low-risk (may auto-resolve with `--risk low`) — ALL of these must hold:**
- Zero product, calculation, tax-math, or spec impact — purely
  supervisor/tooling/process mechanics (e.g. a logging duplication in
  `supervisor.sh`, a script's internal retry count, a lint config choice).
- Fully reversible by a normal follow-up commit — nothing that ships to
  users or touches data.
- Does not touch any path in `.github/gate.yaml`'s denylist.
- Not a recurring-pattern (Type A-E) finding — those are always surfaced
  for human judgment per LOOP.md, never auto-resolved.
- You can state the decision and reasoning in one or two sentences — if
  it takes a design discussion to justify, it isn't low-risk.

**Always high-risk (never use `--risk low`), regardless of how small the
diff looks:**
- Anything a project's own CLAUDE.md flags for explicit escalation (e.g.
  calculation/tax-math behavior changes, UI/IA shape changes, spec
  deviations — see this repo's CLAUDE.md for its specific list).
- Any edit to a Blueprint, DDD, or other spec document Claude Code isn't
  authorized to edit directly.
- Anything touching `.github/gate.yaml`'s denylist.
- All blockers (by definition: work cannot continue without a decision —
  see the `--type blocker` guard in `attention_queue.py`, which rejects
  `--risk low` outright).
- All recurring-pattern findings (Type A-E).

When in doubt, treat it as high-risk. A low-risk item is still fully
visible afterward (`status: auto_resolved` in `attention-queue.json`,
included in `docs/BUILD-STATUS.md`) — the only thing that changes is it
doesn't block the loop while waiting for a human to look at it.

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
