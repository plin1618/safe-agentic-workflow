---
description: Run complete validation workflow before creating PR
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

> **📋 TEMPLATE**: This command is a template. See "Customization Guide" below to adapt for your infrastructure. Once you've filled in real values below, add `.claude/commands/pre-pr.md` to your manifest's `protected` (or `replaced`) list — the same way `CLAUDE.md` is protected — so a future harness sync doesn't overwrite your customization with generic template text again.

You are preparing to create a Pull Request. Execute the validation workflow below. If this repo has a `CONTRIBUTING.md`, treat it as the source of truth where it's more specific than this command; if it doesn't, this command is the workflow.

## Validation Checklist

### 1. Code Quality Validation

Run this project's full validation suite (typecheck + lint + tests + format check):

```bash
{{CI_VALIDATE_COMMAND}}
```

If this project has no single combined script, run the equivalent checks individually (typecheck, lint, unit tests) for whatever changed.

**BLOCKER**: Must pass before proceeding. Fix any failures.

### 2. Documentation Linting

Only if this project lints markdown (check `package.json`/`Makefile` for a `lint:md` script — many projects don't have one, in which case skip this step):

```bash
{{LINT_MD_FIX_COMMAND}}
```

Verify no errors remain:

```bash
{{LINT_MD_COMMAND}}
```

### 3. Git Status Check

Verify all changes committed:

```bash
git status
```

**BLOCKER**: No uncommitted changes allowed in PR.

### 4. Rebase onto the Main Branch

Fetch and rebase:

```bash
git fetch origin
git rebase origin/{{MAIN_BRANCH}}
```

**BLOCKER**: Must be up-to-date with `{{MAIN_BRANCH}}`.

### 5. Commit Message Validation

Check all commits follow this repo's format (see `CONTRIBUTING.md` if one exists; otherwise use the format below):

```bash
git log origin/{{MAIN_BRANCH}}..HEAD --oneline
```

**Required format**: `type(scope): description [{{TICKET_PREFIX}}-XXX]`

**BLOCKER**: All commits must reference a ticket, or be identifiable as ticketless housekeeping (doc sync, harness/tooling fixes with no product behavior change).

### 6. Documentation Updates

Verify related docs updated:

- [ ] CLAUDE.md (if architecture/workflow changed)
- [ ] CONTRIBUTING.md (if process changed, and one exists)
- [ ] Specialized docs (feature-specific)

### 7. PR Template Ready

If `.github/pull_request_template.md` exists in this repo, confirm you can fill out all of its sections before opening the PR. If it doesn't exist yet, skip this step (it's a one-time project-setup artifact, not something the harness sync manages — copy one in from `safe-agentic-workflow/.github/pull_request_template.md` if you want one).

## Workflow

Execute steps 1-6 in order (skip 2 if this project doesn't lint markdown).

Report results for each step:

- ✅ PASS: Step completed successfully
- ⚠️ WARNING: Non-blocking issue found
- ❌ BLOCKER: Must fix before PR

## Success Criteria

All validation steps pass. Ready to create PR with:

```bash
git push --force-with-lease origin {branch-name}
gh pr create --title "..." --body "..."
```

Report final status and any remaining blockers.

## Customization Guide

To adapt this command for your infrastructure, fill in these values — either by adding them to your `.harness-manifest.yml`'s `identity` block (for `TICKET_PREFIX`/`MAIN_BRANCH`) or `substitutions` block (for the custom command tokens below) so they're auto-substituted on your next harness sync, or by hand-editing this file directly:

| Placeholder | Description | Example |
| --- | --- | --- |
| `{{TICKET_PREFIX}}` | Your Linear ticket prefix | `WOR`, `PROJ`, `TASK` |
| `{{MAIN_BRANCH}}` | Your integration/trunk branch name | `main`, `dev` |
| `{{CI_VALIDATE_COMMAND}}` | Your combined validation command | `npm run ci:validate`, `yarn ci:validate`, `pnpm check` |
| `{{LINT_MD_FIX_COMMAND}}` | Your markdown auto-fix command (omit step 2 if none) | `npm run lint:md:fix` |
| `{{LINT_MD_COMMAND}}` | Your markdown check command (omit step 2 if none) | `npm run lint:md` |

`{{TICKET_PREFIX}}` and `{{MAIN_BRANCH}}` are required manifest identity fields and already flow through on any harness sync. `{{CI_VALIDATE_COMMAND}}`, `{{LINT_MD_FIX_COMMAND}}`, and `{{LINT_MD_COMMAND}}` are custom tokens — put them in your manifest's `substitutions` block (the designated place for tokens outside the standard identity fields; see `docs/HARNESS_MANIFEST_SCHEMA.md`) and the sync script will fill them in the same way.
