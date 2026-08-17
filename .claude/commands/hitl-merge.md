---
description: Manual HITL override merge -- bypasses the normal merge path on the repo owner's direct instruction
argument-hint: <PR-number> [merge-method]
allowed-tools: [Bash]
---

> **📋 TEMPLATE**: This command is a template. See "Customization Guide" below to adapt for your infrastructure.

Run `.claude/scripts/hitl-merge.sh $ARGUMENTS`.

**Only run this when the repo owner has just, in this session, explicitly asked you to merge this specific PR number.** Do not reach for this because a PR looks trivial, is docs-only, or has been open a while -- those are exactly the cases a mechanical merge gate (if this project has one) should already handle on its own, without a human needing to say anything in chat. If a PR should merge automatically and isn't, that's a gate bug to fix, not a reason to invoke this command yourself.

The script posts an audit comment on the PR recording that this was a manual override, so don't skip calling it in favor of a raw `gh pr merge`.

If this project has additional sensitivity rules (e.g. a file-based denylist for critical code, ticket/evidence requirements), CLAUDE.md's "Manual Merge Override" section should say explicitly whether this override applies uniformly or carves those out -- follow whatever that section says. If the change touches something this project's escalation rules call out (security, data migrations, calculation/business logic, etc.), flag that explicitly in your response -- this command does not do that for you.

## Customization Guide

This command is infrastructure-agnostic as written. Optional per-project adaptations:

| Adaptation                          | When to make it                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| Set `GH_REPO` in the script's env    | If Claude may run this from a working directory whose git remote isn't the target repo |
| Add a scope note in CLAUDE.md        | If this project has a sensitivity denylist and needs to state whether the override carves it out |
