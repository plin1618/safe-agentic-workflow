---
description: View {{DEV_MACHINE}} dev container logs
argument-hint: [--follow] [--tail N]
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

> **📋 TEMPLATE — infra-dependent**: This command assumes you deploy to a remote server over SSH with Docker Compose. If your project doesn't have that infrastructure yet (e.g. it deploys via a platform like Vercel/Cloudflare, or hasn't set up deployment at all), this command doesn't apply — don't treat it as a pending TODO, delete it or leave it unfilled until you actually have matching infrastructure. See "Customization Guide" below if you do.

> **DEPRECATED**: This command is an alias to `/remote-logs`. Use `/remote-logs` directly.

This command calls `/remote-logs` which is the canonical command for viewing {{DEV_MACHINE}} container logs.

## Usage

```bash
/remote-logs
/remote-logs --follow
/remote-logs --tail 500
```

## Why Deprecated?

Per {{TICKET_PREFIX}}-445, we canonicalized around `/remote-*` and `/local-*` naming:

- `/remote-*` = {{DEV_MACHINE}} operations (staging-first, then dev)
- `/local-*` = Local machine operations

## Related Commands

- `/remote-logs` - **Canonical** - View {{DEV_MACHINE}} container logs
- `/remote-health` - Health dashboard for {{DEV_MACHINE}}
- `/remote-status` - Check if {{DEV_MACHINE}} needs update
- `/remote-deploy` - Deploy latest image to {{DEV_MACHINE}}

## Customization Guide

To adapt this command for your infrastructure, replace these placeholders:

| Placeholder       | Description                  | Example                           |
| ----------------- | ---------------------------- | --------------------------------- |
| `{{TICKET_PREFIX}}` | Your Linear ticket prefix    | `WOR`, `PROJ`, `TASK`             |
| `{{DEV_MACHINE}}`   | Your remote dev machine name | `Pop OS`, `staging`, `dev-server` |
