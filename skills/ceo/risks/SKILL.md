---
name: risks
description: |
  Compact Telegram listing of active risks from memory/risks.md for the CEO
  of TANDEM Group, sorted by severity × probability. Auto-invoked when the
  user types /risks in Telegram (variants: "show risks", "риски", "что
  угрожает"). Optionally filter by minimum severity (`/risks high`).
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/risks.md
metadata:
  hermes:
    tags: [CEO, Risks, Listing, Telegram]
    commands: [/risks]
    triggers:
      - "/risks"
      - "show risks"
      - "риски"
      - "что угрожает"
---

# Risks Listing

**Purpose.** Top risks at a glance. Per blueprint §04, 8 categories.

**Trigger.** `/risks` or `/risks <min_severity>` (critical|high|medium|low).

---

## Persona

Load `memory/soul.md`.

---

## Step 1 — Gather

```bash
python skills/ceo/risks/scripts/list_risks.py
# or:
python skills/ceo/risks/scripts/list_risks.py --min-severity high
```

Returns JSON `{risks: [...], filter: ..., total: N}`. Each risk dict has:
title, category, severity, probability, status, mitigation_short, owner.

Risks sorted by severity × probability rank (highest first).

---

## Step 2 — Format for Telegram (**на русском**)

```
⚠ Активные риски — всего {N}, фильтр={filter or 'все'}

🔥 critical (критический):
• *<title>* (<category>)
  Вероятность: <high|medium|low> · Статус: <status>
  Mitigation: <mitigation_short>

🟥 high (высокий):
• ...

🟧 medium (средний):
• ...

🟨 low (низкий):
• ...
```

Group by severity desc.

If total = 0:
```
⚠ Активных рисков не зафиксировано.
Открой memory/risks.md и добавь (8 категорий: cashflow, overload, burnout,
health, family neglect, strategic, project delays, key people dependency).
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| Placeholder risks (title starts with `<...>`) | Excluded by parser already |
| Risk with empty severity | Display "—", sort as 0 (last) |
| Risk status=closed | Exclude from listing |
| Длинный list >4096 char | Split: critical+high in `(1/2)`, medium+low in `(2/2)` |

---

## What NOT to do

- ❌ НЕ предлагай "что делать с risk X" — это для weekly review (`/week`).
- ❌ НЕ показывай Trigger / Linked Projects / Last Reviewed в основном listing (overflow). Доступно через manual open of risks.md.
- ❌ НЕ создавай новые risks через `/risks` — manual edit memory/risks.md или future `/capture --type risk` (not in V1).
