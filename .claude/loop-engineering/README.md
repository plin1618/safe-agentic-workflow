# Loop Engineering components

Generic, project-agnostic scripts implementing Components 1, 3, 4, 5, 6 of
the continuous build loop (Component 2, the auto-merge gate, lives under
`.github/` since it's a GitHub Action — see `.github/AUTO_MERGE_GATE_SETUP.md`).
See `LOOP.md` (repo root) for the overall intent and `loop-budget.md` for
budget declarations.

**Sync note:** everything in this directory is under `.claude/`, which
IS in `sync-claude-harness.sh`'s `sync_scope` — these files propagate to
downstream projects on sync. `LOOP.md`, `loop-budget.md`, `supervisor.sh`
(repo root) and everything under `.github/` are **not** in scope and need
manual copying into each project.

## Hook points

**After every `build-fidelity-audit` run** (the skill itself lives in the
separate `Claude-skills` repo, not here — see that skill's own docs for
where to add this call):

```bash
python .claude/loop-engineering/audit_tally.py \
    --sprint <N> --high <count> --critical <count> --ticket-refs <IDs...>

python .claude/loop-engineering/sprint_history.py record \
    --high <count> --critical <count> --tickets-resolved <N>

# For each ticket fixed since the last audit:
python .claude/loop-engineering/recurrence_detect.py log-fix \
    --ticket-id <ID> --files <paths...> --classification <MATCH|GAP|REGRESSION|...> \
    --feature "<feature name>" --issue-type "<short description of the kind of mistake>" \
    --tier <N> --tokens <N> --turns <N>

# For each feature scored this audit:
python .claude/loop-engineering/recurrence_detect.py log-feature \
    --feature "<feature name>" --classification <MATCH|GAP|REGRESSION|...>

python .claude/loop-engineering/recurrence_detect.py detect

python .claude/loop-engineering/build_dashboard.py update-review-ledger
python .claude/loop-engineering/build_dashboard.py render
```

**Before creating worktrees for a new tier batch:**

```bash
python .claude/loop-engineering/cluster_tickets.py tickets.json --tier <N>
# -- review the printed clusters by eye first, per Q2's sanity-check rule --
.claude/loop-engineering/worktree_manager.sh create tier<N>-cluster-<id>
```

**When a cluster hits a blocker or design decision:**

```bash
.claude/loop-engineering/worktree_manager.sh park tier<N>-cluster-<id> blocker "description"
```

**On cluster completion / periodic cleanup:**

```bash
.claude/loop-engineering/worktree_manager.sh complete tier<N>-cluster-<id>
.claude/loop-engineering/worktree_manager.sh sweep
```

## One-time setup in a new project

1. `sync-claude-harness.sh` brings in everything under `.claude/`
   (including this directory and `loop-constraints.md`).
2. Manually copy `LOOP.md`, `loop-budget.md`, and `supervisor.sh` from
   this fork's repo root into the new project's repo root.
3. Follow `.github/AUTO_MERGE_GATE_SETUP.md` for Component 2.
4. Seed `sprint-history.json` with the project's real current sprint
   number before the first supervised run:
   `python .claude/loop-engineering/sprint_history.py seed --sprint <N>`
5. Wire the hook-point calls above into wherever the project's
   `build-fidelity-audit` skill runs (see that skill's own repo).
6. Run the auth-mode pre-flight check described in
   `loop-constraints.md`'s "Budget discipline" section before any
   unattended `supervisor.sh` run.
7. Test `supervisor.sh`'s rate-limit reset-time parsing against real
   captured output before trusting an unattended multi-hour run — this
   is the single biggest untested risk in the whole build.

## State files (all under `.claude/state/`, gitignore is a judgment call —
recommend tracking, small and gives you history in version control)

- `audit-tally.json` — Component 1
- `cluster-status.json` — Component 3
- `attention-queue.json` — Component 4 (also written by Component 3 parks
  and Component 6 recurring-pattern flags)
- `run-ledger.json` — Component 4's cumulative circuit breaker
- `sprint-history.json`, `review-ledger.json` — Component 5
- `fix-history.json`, `feature-history.json` — Component 6
