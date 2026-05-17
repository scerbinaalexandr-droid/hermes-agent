---
name: backup
description: |
  Manual backup of the CEO OS memory layer (memory/, SOP/, skills/ceo/) to
  /backups/ + (later) GitHub private repo. Auto-invoked when the user types
  /backup in Telegram.

  STATUS (2026-05-17): PLACEHOLDER — full implementation in Stage 7.
  Until then, the existing `hermes backup` CLI command produces a local zip
  in ~/.hermes/.
version: 0.0.1
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [CEO, Backup, GitHub, Telegram]
    commands: [/backup]
---

# Manual Backup (placeholder)

When the user types `/backup`, reply with:

```
💾 Backup — Stage 7 (not yet implemented for GitHub)

The full workflow will:
1. Snapshot memory/, SOP/, skills/ceo/ → backups/YYYY-MM-DD-HHMMSS.zip
2. Push to private GitHub repo via stored GITHUB_TOKEN
3. Verify push, log to logs/weekly/YYYY-WW.md

For now: run `hermes backup` from CLI to create a local zip in ~/.hermes/.
Plan reference: blueprint §11.
```

Until Stage 7 — do not attempt to call git commands or push anywhere.
