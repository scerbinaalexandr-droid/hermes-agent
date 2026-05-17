# Risks — Active Tracking

> 8 категорий по блюпринту §04. Updated as observed.
> SOP: `SOP/memory_management.md`.
> Updated: 2026-05-17 (init).

---

## Шаблон риска

```markdown
### <Risk title>

Category: <one of 8 below>
Severity: critical | high | medium | low
Probability: high | medium | low
Status: monitoring | active | escalated | mitigated | closed
Trigger: <what would make this real>
Mitigation: <what we are doing about it>
Owner: <CEO / delegate>
Last Reviewed: YYYY-MM-DD
Linked Projects: <projects.md links>
```

---

## 1. Cashflow Risks

<например:>
### <Specific cashflow risk>

Category: cashflow
Severity: high
Probability: medium
Status: monitoring
Trigger: <specific event>
Mitigation: weekly cashflow review + reserve fund
Owner: CEO + CFO
Last Reviewed: 2026-05-17
Linked Projects: Tandem Casa 360°, Pharma RO

---

## 2. Overload Risks

<CEO overload — слишком много встреч, слишком много открытых проектов>

### CEO calendar overload

Category: overload
Severity: high
Probability: high
Status: active
Trigger: >10 встреч/день sustained, no recovery blocks
Mitigation: Hermes daily briefing + evening review, weekly calendar audit
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: Tandem Group CEO System (Hermes V1)

---

## 3. Burnout Risks

### Sustained high-stress + low recovery

Category: burnout
Severity: critical
Probability: medium
Status: monitoring
Trigger: <specific markers — sleep <6hr 5+ дней, missed sport sessions 2+ weeks, irritability>
Mitigation: weekly recovery blocks, sport non-negotiable, evening review tracking Energy/Stress levels
Owner: CEO + Супруга (support)
Last Reviewed: 2026-05-17
Linked Projects: Health / Longevity

---

## 4. Health Risks

<серьёзные риски здоровью — отдельный domain через HEALTH_VAULT>

### <Specific health risk if applicable>

Category: health
Severity: <>
Probability: <>
Status: <>
Trigger: <>
Mitigation: HEALTH_VAULT protocols, regular bloodwork, doctor follow-ups
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: Health / Longevity

---

## 5. Family Neglect Risks

### Недостаточно времени с Супругой / родителями

Category: family neglect
Severity: high
Probability: medium
Status: monitoring
Trigger: <2 quality touchpoints / week с Супругой, missed weekly parent call
Mitigation: daily Family Touchpoint в briefing, weekly date night non-negotiable, Sunday parent call
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: areas.md::Супруга, areas.md::Parents

---

## 6. Strategic Risks

<риски про неправильное направление, конкуренцию, market shifts>

### <Specific strategic risk>

Category: strategic
Severity: <>
Probability: <>
Status: <>
Trigger: <>
Mitigation: quarterly strategy review, blue ocean preference, competitor scan (Phase 4)
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: TANDEM Group, Tandem Casa 360°, Pharma RO

---

## 7. Project Delays

<накопление delayed milestones — структурный risk>

### Brasov Apartment renovation delays

Category: project delays
Severity: medium
Probability: high (по статистике renovations)
Status: active
Trigger: missed weekly milestone 2 weeks in a row
Mitigation: weekly contractor sync, monthly site visit, buffer в deadline
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: Brasov Apartment Renovation

---

## 8. Key People Dependency

<если business depends on 1-2 человек и они уходят>

### <Specific key dependency>

Category: key people dependency
Severity: critical
Probability: low
Status: monitoring
Trigger: <key person leaves or unavailable>
Mitigation: documentation, succession planning, cross-training
Owner: CEO
Last Reviewed: 2026-05-17
Linked Projects: <relevant projects>

---

## Risk Review Cadence

- **Weekly** — top 3 risks (см. memory.md::Active Risks) reviewed в weekly CEO review
- **Monthly** — full risks.md scan, status update
- **Quarterly** — risk landscape review, new risks identification

---

## Notes

- Risks ≠ problems. Risk = что может пойти не так. Problem = что уже идёт не так (тогда → memory.md::Current Business Issues).
- Risks linkbacks to projects через Linked Projects поле.
- При закрытии risk → status: closed + дата + что произошло (учиться на closed risks).
