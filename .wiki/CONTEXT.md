---
title: hermes-agent — Context
type: reference
updated: 2026-05-17
tags: [wiki, hermes-agent, ceo-os, tandem]
---

# hermes-agent — Context
**Updated:** 2026-05-17
**Phase:** V1 Executive OS — MVP-вертикаль (Stage 0-4) для CEO Tandem Group

## Что это за проект

Fork Nous Research Hermes Agent, переоснащённый для использования как **Executive Operating System** для Alexandr Scerbina (CEO TANDEM Group, MD+RO). Бренды: TANDEM Group, Tandem Casa 360°, Kitchen by Tandem, Arlengo, Lean Kitchen.

Источник архитектуры V1: `~/Downloads/hermes_claude_code_sequential_files_blueprint.md`.
Плановый файл: `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md`.

## Текущая задача

Построить MVP-вертикаль V1: рабочая команда `/brief` в Telegram (@Hermes_Alex21_bot) → daily briefing из `/memory/*.md`.

Этапы:
- ✅ Stage 0 — ALEX21 Compliance (.wiki + CLAUDE.md)
- ✅ Stage 1 — Audit report сохранён (`.wiki/AUDIT_2026-05-17.md`)
- ✅ Stage 2 — Folder structure (/memory, /SOP, /logs, /backups + .gitignore patches)
- ✅ Stage 3 — Memory content + loader (10 markdown файлов + `skills/ceo/_lib/memory.py`)
- ✅ Stage 4 — `/brief` skill working end-to-end
- ✅ Stage 4b — Skill loader routing (rename, placeholder skills, COMMAND_REGISTRY rollback)
- ✅ Stage 4c — `~/.hermes/config.yaml` с external_dirs
- ✅ Stage 5 — `/evening` (blueprint §08) + `/week` (blueprint §09) real implementations
- ✅ Stage 5b — `/capture` (4 routing types для voice memo / text)
- ✅ Stage 5c — `/projects`, `/risks` listings (priority/severity sorted)
- ✅ Stage 5d — Extended memory loader (all_projects, all_risks, route_capture, update_project_field, ...)
- ⏳ Stage 6 — Cron seeding (5 jobs) — operational, VPS access
- ⏳ Stage 7 — GitHub private backup — operational, GITHUB_TOKEN + repo setup

**6 из 7 CEO команд real-implemented**, 1 placeholder (/backup для Stage 7).

## Принятые решения

См. `decisions.md`. Главные:
- `/memory`, `/SOP`, `/logs`, `/backups` — в КОРНЕ репо (по блюпринту)
- Skills формат — Hermes-native `skills/ceo/<name>/SKILL.md`
- `docker/SOUL.md` — база для `memory/soul.md` (расширение, не дубль)
- Scope первой итерации — MVP-вертикаль до `/brief` end-to-end

## Следующие шаги

1. **End-to-end тест** `/brief` через Telegram @Hermes_Alex21_bot (запустить gateway, отправить /brief, проверить ответ + лог в `logs/daily/`)
2. **Дозаполнить** user.md (Leadership Style, Communication Style разделы) и memory.md (Active Priorities этой недели)
3. **Commit** серией: feat(ceo-os): stage 0, ..., stage 4
4. Stage 5 (next iteration): evening_review, weekly_ceo_review skills + `/evening`, `/week`
5. Stage 6: cron seeding (07:30 brief, 21:30 evening, Sun 17:00 cleanup, Sun 18:00 weekly, 00:30 backup)
6. Stage 7: GitHub private backup automation

## Открытые блокеры

- `memory/user.md` — нужны personal data из `docker/SOUL.md` + дополнение (handled inline в Stage 3)
- Telegram end-to-end тест возможен только когда user готов запустить бот / контейнер

## Continuation Notes

Если сессия прервётся — продолжать со следующего pending task в TaskList. План в `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md`.
