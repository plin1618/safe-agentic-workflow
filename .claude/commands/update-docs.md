---
description: Check and update relevant documentation for current work
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

Review current work and identify documentation that needs updating. If this repo has a CONTRIBUTING.md with a docs-update requirement, follow it; otherwise apply the general rule: always update docs related to the work in this PR.

## Documentation Assessment

### 1. Identify Changes

Analyze git diff to understand scope:

```bash
git diff origin/{{MAIN_BRANCH}} --name-only
```

Categorize changes:

- Architecture/workflow changes
- New features or APIs
- Process modifications
- Configuration changes
- Database schema changes

### 2. Required Documentation Updates

Based on changes, check if these need updates:

#### High-Level Docs (ALWAYS update in same PR)

- **CLAUDE.md**: Architecture, commands, setup
  - Check if: New commands, workflow changes, tech stack updates
- **CONTRIBUTING.md**: Development process, workflows
  - Check if: Process changes, new requirements, workflow modifications

#### Specialized Docs

- **Database**: `docs/database/` (schema, RLS, migrations)
  - Check if: Schema changes, new tables, RLS patterns
- **API Docs**: `docs/api/` (endpoints, webhooks)
  - Check if: New routes, API changes, webhook modifications
- **Feature Docs**: `docs/` (feature-specific)
  - Check if: New features, major functionality changes

#### Code Documentation

- **Inline comments**: Complex logic
- **README**: Feature directories
- **ADRs**: `docs/adr/` (architectural decisions)
  - Check if: Significant architecture decisions made

### 3. Documentation Checklist

For each doc identified:

- [ ] Content accuracy verified
- [ ] Examples updated
- [ ] Commands/code samples tested
- [ ] Links validated
- [ ] Markdown linting passed

### 4. Execute Updates

For each doc needing updates:

1. Read current version
2. Identify outdated sections
3. Update with current information
4. Run `{{LINT_MD_FIX_COMMAND}}` (skip if this project doesn't lint markdown)
5. Add to current commit

## Workflow

1. Assess changes made in current branch
2. Identify all affected documentation
3. Present list to user for confirmation
4. Execute updates for confirmed docs
5. Verify markdown linting passes
6. Report completion status

## Success Criteria

- ✅ All relevant docs identified
- ✅ Updates made in same PR
- ✅ Markdown linting passes
- ✅ Documentation stays current

This ensures agentic team has accurate, up-to-date information to work effectively.

## Customization Guide

| Placeholder | Description | Example |
| --- | --- | --- |
| `{{MAIN_BRANCH}}` | Your integration/trunk branch | `main`, `dev` |
| `{{LINT_MD_FIX_COMMAND}}` | Your markdown auto-fix command (omit step 4 if none) | `npm run lint:md:fix` |
