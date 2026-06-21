#!/usr/bin/env python3
"""Generate a Hermes CEO OS capability map as an .excalidraw file.

Produces docs/hermes-map.excalidraw — a hand-laid system map the CEO can open on
excalidraw.com or drag into Obsidian Excalidraw. Three zones: what it can do
(commands), what's configured (infra), what can be added (Phase 2) + legend.

Stdlib only. Deterministic (fixed seeds) so re-runs are diff-stable.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "hermes-map.excalidraw"

# Palette
GREEN_BG, GREEN_ST = "#ebfbee", "#2f9e44"      # ✅ have
ADDED_BG, ADDED_ST = "#d3f9d8", "#099268"      # 🟢 just added this session
ADD_BG, ADD_ST = "#fff9db", "#e8590c"          # ⏳ can add (Phase 2)
HUB_BG, HUB_ST = "#e7f5ff", "#1971c2"          # core hub
TITLE_C, SUB_C = "#212529", "#495057"

_elements = []
_seed = 1000


def _nid():
    global _seed
    _seed += 7
    return f"el{_seed}"


def box(x, y, w, h, bg, st, radius=True):
    eid = _nid()
    _elements.append({
        "id": eid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": st, "backgroundColor": bg, "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": {"type": 3} if radius else None,
        "seed": _seed * 3, "version": 1, "versionNonce": _seed * 5, "isDeleted": False,
        "boundElements": [], "updatedAt": 1, "link": None, "locked": False,
    })
    return eid


def text(x, y, content, size=16, color=TITLE_C, w=None, align="left", bold=False):
    eid = _nid()
    lines = content.split("\n")
    width = w if w else max((len(l) for l in lines), default=1) * size * 0.6
    height = len(lines) * size * 1.25
    _elements.append({
        "id": eid, "type": "text", "x": x, "y": y, "width": width, "height": height,
        "angle": 0, "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid", "roughness": 1,
        "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
        "seed": _seed * 3, "version": 1, "versionNonce": _seed * 5, "isDeleted": False,
        "boundElements": [], "updatedAt": 1, "link": None, "locked": False,
        "text": content, "fontSize": size, "fontFamily": 2 if bold else 1,
        "textAlign": align, "verticalAlign": "top", "containerId": None,
        "originalText": content, "lineHeight": 1.25, "baseline": int(size * 0.8),
    })
    return eid


def arrow(x1, y1, x2, y2, color=SUB_C):
    eid = _nid()
    _elements.append({
        "id": eid, "type": "arrow", "x": x1, "y": y1,
        "width": abs(x2 - x1), "height": abs(y2 - y1), "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": {"type": 2},
        "seed": _seed * 3, "version": 1, "versionNonce": _seed * 5, "isDeleted": False,
        "boundElements": [], "updatedAt": 1, "link": None, "locked": False,
        "points": [[0, 0], [x2 - x1, y2 - y1]], "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    })
    return eid


def card(x, y, w, title, body, bg, st, title_size=17, body_size=13):
    """A titled card with body text inside."""
    lines = body.count("\n") + 1
    h = 34 + lines * body_size * 1.35 + 14
    box(x, y, w, h, bg, st)
    text(x + 14, y + 12, title, title_size, st, bold=True)
    text(x + 14, y + 40, body, body_size, TITLE_C, w=w - 24)
    return h


# ── Canvas ──────────────────────────────────────────────────────────────────
text(60, 20, "HERMES — Executive OS Александра  ·  карта возможностей", 30, TITLE_C, bold=True)
text(60, 62, "@Hermes_Alex21_bot  ·  Telegram + Railway (always-on)  ·  обновлено 2026-06-21", 15, SUB_C)

# Legend
lx, ly = 60, 96
box(lx, ly, 760, 38, "#f8f9fa", "#adb5bd")
text(lx + 14, ly + 11, "✅ есть и работает      🟢 добавил в этой сессии      ⏳ можно прикрутить (Phase 2)", 15, TITLE_C, bold=True)

# ── CENTER HUB ──────────────────────────────────────────────────────────────
hx, hy, hw = 600, 170, 360
box(hx, hy, hw, 96, HUB_BG, HUB_ST)
text(hx + 18, hy + 16, "🤖  HERMES CEO OS", 22, HUB_ST, bold=True)
text(hx + 18, hy + 50, "Вход: голос (49%) / текст (41%)\nМодель: Claude Sonnet 4.5 · provider anthropic", 13, TITLE_C, w=hw - 30)

# arrows hub -> zones
arrow(hx + hw / 2, hy + 96, hx + hw / 2 - 250, hy + 230, HUB_ST)   # to commands
arrow(hx + hw / 2, hy + 96, hx + hw / 2, hy + 230, HUB_ST)         # to infra
arrow(hx + hw / 2, hy + 96, hx + hw / 2 + 250, hy + 230, HUB_ST)   # to add

# ── LEFT: COMMANDS (what it can do) ─────────────────────────────────────────
cx, cy, cw = 60, 410, 470
text(cx, cy - 34, "ЧТО УМЕЕТ  ·  22 команды", 19, GREEN_ST, bold=True)
cmd_body = (
    "Каждый день:  /brief  /evening  /capture  /diary\n"
    "Неделя:       /week\n"
    "Просмотр:     /projects  /risks  /find  /notes\n"
    "              /dashboard (кокпит вперёд)\n"
    "Коуч:         /coach (ICF/GROW/Колесо)\n"
    "Внешнее:      /web (поиск)  /report (HTML)\n"
    "Контроль:     /cost  /telemetry  /backup  /cleanup\n"
    "Доступ:       /handoff (Chief of Staff)  /whoami\n"
    "Утилиты:      /menu  /start  /remind"
)
card(cx, cy, cw, "✅ Команды (голосом или текстом)", cmd_body, GREEN_BG, GREEN_ST, body_size=14)

# ── CENTER: INFRA (what's configured) ───────────────────────────────────────
ix, iy, iw = 580, 410, 400
text(ix, iy - 34, "ЧТО НАСТРОЕНО  ·  инфраструктура", 19, GREEN_ST, bold=True)
infra_body = (
    "Память: 10 файлов + guard-защита от перезаписи\n"
    "Cron: brief 07:30 · week вс 18:00 · RO-инфляция пн\n"
    "Бэкап: GitHub daily + Mac DR-зеркало (6ч)\n"
    "Голос вход: Whisper STT (ru)\n"
    "Always-on: Railway + tini, health 200\n"
    "Privacy: семья→роли, без банка/медицины\n"
    "Доступ: только 2 твоих Telegram-аккаунта"
)
hh = card(ix, iy, iw, "✅ База", infra_body, GREEN_BG, GREEN_ST, body_size=14)

# just-added cards under infra
ay = iy + hh + 16
added_body = (
    "Fallback-цепочка: Anthropic → Sonnet/OpenRouter\n"
    "→ Gemini 2.5 Pro (brief придёт даже при сбое)\n"
    "Голос ОТВЕТА: Edge TTS, ru-RU-Dmitry\n"
    "(«ответь голосом» → голосовой баббл)"
)
card(ix, ay, iw, "🟢 Добавил сейчас", added_body, ADDED_BG, ADDED_ST, body_size=14)

# ── RIGHT: CAN ADD (Phase 2) ────────────────────────────────────────────────
rx, ry, rw = 1030, 410, 430
text(rx, ry - 34, "ЧТО МОЖНО ПРИКРУТИТЬ", 19, ADD_ST, bold=True)
add_body = (
    "📊 Google Sheets + Календарь — нужен 1 OAuth-клик\n"
    "    (CRM, партнёрка, расписание, новые лиды)\n"
    "📇 CRM-монитор лидов — silent-cron, только новое\n"
    "🧠 Субагент-делегация — готова, снять Phase-1 рамку\n"
    "    (ресёрч ∥ задача параллельно)\n"
    "📔 Obsidian «на сегодня» — нужен Mac-мост\n"
    "🔔 Webhook-приём (CRM пуши) — нужен порт\n"
    "🔌 MCP к Claude Code — нужна HTTP-обёртка"
)
card(rx, ry, rw, "⏳ Phase 2 (по твоему слову)", add_body, ADD_BG, ADD_ST, body_size=14)

# pruned / skip note
sy = ry + 250
box(rx, sy, rw, 92, "#f8f9fa", "#adb5bd")
text(rx + 14, sy + 10, "⚪ Сознательно НЕ делаем", 16, SUB_C, bold=True)
text(rx + 14, sy + 36,
     "• Экономия токенов — у тебя $0.44/день, нечего экономить\n"
     "• Brave Search — твой /web уже работает\n"
     "• Kanban «цифровые сотрудники» — это dev-фича, не CEO",
     12.5, TITLE_C, w=rw - 24)

# ── write ───────────────────────────────────────────────────────────────────
doc = {
    "type": "excalidraw", "version": 2, "source": "hermes-agent/gen_hermes_map.py",
    "elements": _elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT}  ({len(_elements)} elements)")
