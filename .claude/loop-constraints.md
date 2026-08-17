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

## Tier-approval gate
Before running `worktree_manager.sh create <cluster-key>` for a new tier
batch, the repo owner's explicit sign-off is required on each ticket in
that batch (e.g. a Linear comment along the lines of "tier approval
confirmed ... cleared for worktree_manager.sh create") — this is never
optional. This section closes a **visibility** gap, not the gate itself:
without it, a stall here relies entirely on LOOP.md's "ask your
interactive session to poll" workaround, which only works if someone
remembers to ask — a pattern that has caused real, unnoticed stalls on
projects running this harness.

**Stall must self-announce.** The moment a session determines a batch is
ready to build but is blocked on tier-approval (i.e. it would otherwise
write a `blocker_category: "tier-approval-gate"` entry to
`attention-queue.json`), it must **also** post a Linear comment on every
ticket in that batch, in the same call, asking for tier approval —
don't just write to the attention queue and wait for someone to check
the dashboard. Use the Linear connector's comment tool (`save_comment` /
equivalent) with a message identifying the cluster, the tickets, and
literally what unblocks it (e.g. "Ready to build as tier2-cluster-1 —
ABC-131, ABC-133. Reply with tier approval to proceed, or flag
concerns."). This is in addition to, not instead of, the
`attention-queue.json` entry — the queue stays the system of record; the
comment is what makes the stall visible without anyone having to go
looking.

**Pre-authorized low-risk tier for this gate specifically.** A batch may
skip the ask and proceed straight to `worktree_manager.sh create` without
waiting for a Linear reply — logged via `attention_queue.py add --risk
low --decision "..."` exactly like any other low-risk item — only when
**every** one of these holds:
- Every ticket in the batch is itself already tagged low-risk under the
  general "Risk tiers" section above (small/mechanical, zero product/
  calc/tax-math/spec impact, fully reversible, not a denylisted path).
- No ticket in the batch touches a file any other in-flight worktree is
  also touching (no shared-file collision risk from parallelizing).
- The batch is not, and does not contain, a blocker or a recurring-
  pattern (Type A-E) finding — **this carve-out does not touch the
  general Risk tiers section's own exclusion of blockers and recurring
  patterns from `--risk low`; both exclusions independently apply.**

This is a narrower, separate exception from the general "Risk tiers"
section above — it exists only to let a tier-approval *stall specifically*
self-clear for genuinely mechanical batches; it does not change what
counts as low-risk for any other `attention_queue.py add` call, and the
general section's own blocker/recurring-pattern exclusion stays intact
exactly as written. When in doubt whether a batch clears this bar, it
doesn't — post the Linear comment and park, same as before.

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
