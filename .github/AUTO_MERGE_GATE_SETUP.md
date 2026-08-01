# Setting up the conditional auto-merge gate in a new project

`auto-merge-gate.yml` + `auto_merge_gate.py` are **not** synced by
`sync-claude-harness.sh` — `.github/` is outside the harness's current
`sync_scope`. Copy these files manually into each project:

1. Copy `.github/workflows/auto-merge-gate.yml` and
   `.github/scripts/auto_merge_gate.py` into the target repo.
2. Copy `.github/gate.yaml.example` to `.github/gate.yaml` in the target
   repo and add that project's actual highest-stakes paths beyond the
   generic security defaults (e.g. for a tax-precision codebase: the
   calculation/rounding modules, migration files).
3. Add repo secret `LINEAR_API_KEY` (Settings → Secrets and variables →
   Actions → Secrets).
4. Add repo variable `LINEAR_TICKET_PREFIX` (same location → Variables
   tab), matching that project's Linear team prefix.
5. Optionally add repo variable `MERGE_METHOD` (`squash` / `merge` /
   `rebase`) — defaults to `squash`.
6. Leave the `DRY_RUN` repo variable unset (defaults to `true`) until
   you've run it against a batch of real PRs and compared its verdicts
   to your own judgment. Then set `DRY_RUN` = `false` to go live.
7. One unverified assumption, flagged in `auto_merge_gate.py`'s
   `check_qas_approved`: Linear's GraphQL `issue(id:)` field is assumed
   to accept the human-readable ticket identifier (e.g. "ABC-123")
   directly. Believed current, not yet exercised against a real
   workspace — verify once per install, not per project.
8. Condition (c) of the gate (independent QAS pass) requires the SAW
   harness's `/start-work` → `/pre-pr` sequence to actually be running
   and posting "Approved for RTE" evidence to Linear — see
   `.claude/loop-constraints.md`'s process-discipline section. If that
   isn't confirmed working yet, the gate will simply find no evidence
   and fail closed (never auto-merge) until it is — which is the safe
   default, not a bug.
