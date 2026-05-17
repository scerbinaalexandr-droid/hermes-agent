# SOP: Telegram Commands

**Назначение:** реестр всех CEO команд, что делает каждая, какие memory-файлы читает/обновляет, какой skill отрабатывает.

**Bot:** @Hermes_Alex21_bot
**Канал:** Telegram DM (личные команды), Topic mode для групповых чатов (см. `telegram_dm_topic_mode` в `hermes_state.py`).

---

## Реестр команд (V1)

| Команда | Skill | Reads | Writes | Status |
|---|---|---|---|---|
| `/start` | core | — | — | Hermes default |
| `/help` | core | — | — | Hermes default |
| `/brief` | `ceo/daily_briefing` | user, soul, memory, areas, projects (priority=high), daily_log (last 3) | logs/daily/YYYY-MM-DD.md | **V1 MVP** |
| `/evening` | `ceo/evening_review` | memory, daily_log (today), projects, risks | logs/daily/YYYY-MM-DD.md, daily_log.md, memory.md | Stage 5 |
| `/week` | `ceo/weekly_ceo_review` | memory, projects, risks, daily_log (week), weekly_review (last) | logs/weekly/YYYY-WW.md, weekly_review.md, projects.md, risks.md | Stage 5 |
| `/capture <text>` | `ceo/voice_to_task` | — | memory.md (active context) или projects.md (Next Actions) | Stage 5b |
| `/projects` | `ceo/project_listing` | projects.md | — | Stage 5c |
| `/area <name>` | `ceo/area_view` | areas.md | — | Stage 5c |
| `/risks` | `ceo/risk_listing` | risks.md | — | Stage 5c |
| `/decision <text>` | `ceo/decision_capture` | — | decisions.md | Stage 5c |
| `/cleanup` | `ceo/memory_cleanup` | memory.md, daily_log.md, weekly_review.md | proposal output (manual approval) | Stage 5c |
| `/backup` | `ceo/manual_backup` | — | backups/ + GitHub push (Stage 7) | Stage 7 |

---

## Принципы

Из блюпринта §06:

1. **Команды короткие.** `/brief` лучше чем `/morning-briefing-please`.
2. **Команды работают надёжно.** Если skill упал — graceful fallback с stub-ответом, не silent fail.
3. **Команды возвращают сжатые ответы.** Telegram limit 4096 char. Briefing должен влезть в одно сообщение.
4. **Memory updates безопасны.** Append-only там где `daily_log`, `weekly_review`, `decisions`. Перезапись `memory.md` — только через `/cleanup` proposal с явным approval.
5. **НЕТ destructive auto-actions.** `/cleanup` не удаляет — показывает proposal. `/backup` не overwrites — создаёт timestamped snapshot.

---

## Регистрация команды

`gateway/platforms/telegram.py::_handle_command()` (≈line 2956) — расширить:

```python
# Pseudocode skeleton
if cmd == "/brief":
    skill = load_skill("ceo/daily_briefing")
    result = run_skill(skill, user_context=user_id)
    return send_telegram_message(chat_id, result, parse_mode="MarkdownV2")
```

Конкретный hook см. в `skills/ceo/daily_briefing/SKILL.md` execute блок.

---

## Edge cases

- **Пустая память** → команда возвращает structured stub с instruction "залейте контент в memory/<file>".
- **LLM timeout / rate-limit** → fallback с last `daily_log.md` entry + "previous brief" hint.
- **Длинный output > 4096 char** → разбивать на 2 сообщения с continuation pointer "(1/2)".
- **Команда вне допустимого канала (групповой чат без topic)** → reply "use DM with bot for CEO commands".
