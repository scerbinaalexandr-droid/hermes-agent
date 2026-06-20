"""Generate the forward-looking CEO Executive Cockpit (/dashboard) as HTML.

Unlike /report (retrospective: what happened over a period), /dashboard is
forward-looking: what is on the CEO's plate RIGHT NOW and what is coming up.

Hard rules (enforced by code, not by the LLM):
  - Only reads memory/*.md + logs/daily/*.md — no external sources
  - No hardcoded competitor / market / news strings
  - Empty sections render an explicit "(нет данных)" notice — never fabricated
  - HTML self-contained except Chart.js via CDN <script> tag
  - uuid4 filename for unguessable public URL via HERMES_PUBLIC_HOST
  - telegram_caption: deterministic ready-to-send string in the JSON output

Sections (forward-looking cockpit):
  1. 🎯 Top-of-mind today      — memory.md::Active Priorities (open items)
  2. 🎤 Backlog надиктованного — /capture task: items (last 30d, daily_log.md)
  3. 📅 Weekly Plan            — latest weekly_review.md::Next Week Focus
  4. 📂 Active projects        — projects.md, with simple progress (done/total actions)
  5. ⚠ Risks watching         — risks.md, sorted by severity × probability
  6. 💗 Health trend           — logs/daily/*.md::Evening Energy/Stress (if data)
  7. 📝 Decisions log (recent) — decisions.md, last entries
  8. 🎤 Quick-capture reminder — static nudge to keep the cockpit fed

Usage:
  python generate_dashboard.py --output /opt/data/reports
  python generate_dashboard.py            # auto-resolve output dir

Returns JSON to stdout: {html_path, public_url, telegram_caption, stats, ...}
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os
import pathlib
import re
import sys
import uuid as _uuid

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
# Production fallback: skills/ceo/_lib/ lives only in /opt/hermes (built into
# the image). Hermes skill-sync to /opt/data copies only dirs with a SKILL.md;
# _lib/ has no SKILL.md so it stays at the image path.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    _normalize_rank_token,
    all_projects,
    extract_section,
    last_entries,
    load_memory,
    memory_root,
    risks_by_severity,
    all_risks,
    today_iso,
)

# Forward-looking backlog window (days) for dictated task captures.
BACKLOG_DAYS = 30
# Health trend lookback (days) for the energy/stress sparkline.
HEALTH_DAYS = 14


# ── Helpers ──────────────────────────────────────────────────────────────────


def _today() -> _dt.date:
    return _dt.date.today()


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _parse_date_header(line: str) -> _dt.date | None:
    """Parse 'YYYY-MM-DD' (optionally followed by ' — slug') from a header line."""
    line = line.strip().lstrip("#").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", line)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _within_window(entry_date: _dt.date | None, cutoff: _dt.date) -> bool:
    return entry_date is not None and entry_date >= cutoff


def public_dashboard_url(uuid_filename: str) -> str | None:
    """Build a public URL for the given uuid HTML filename.

    Reads HERMES_PUBLIC_HOST env var (set in Railway Variables after enabling
    Public Networking). Returns None if unset — caller shows a fallback note.
    """
    host = (os.environ.get("HERMES_PUBLIC_HOST") or "").strip()
    if not host:
        return None
    host = host.rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    return f"{host}/reports/{uuid_filename}"


def _daily_log_dirs() -> list[pathlib.Path]:
    """Return existing logs/daily directories (dev repo + prod /opt/data)."""
    dirs: list[pathlib.Path] = []
    home = pathlib.Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
    candidates = [
        home / "logs" / "daily",
        _REPO / "logs" / "daily",
        pathlib.Path("/opt/data/logs/daily"),
    ]
    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if c.exists() and key not in seen:
            dirs.append(c)
            seen.add(key)
    return dirs


# ── Section collectors (real data only) ──────────────────────────────────────


def collect_top_of_mind() -> dict:
    """Open items from memory.md::Active Priorities — the CEO's focus right now.

    Returns {items, raw_present}. Skips template placeholder lines (those with
    '<...>' angle-bracket stubs).
    """
    text = load_memory(["memory"])["memory"]
    section = extract_section(text, "Active Priorities (this week)") or ""
    items: list[dict] = []
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        # Drop the leading bullet / checkbox marker.
        body = re.sub(r"^-\s*(\[[ xX]\]\s*)?", "", s).strip()
        if not body:
            continue
        # Skip template placeholders like "<priority 1 — ...>".
        if body.startswith("<") and body.endswith(">"):
            continue
        checked = bool(re.match(r"^-\s*\[[xX]\]", s))
        items.append({"text": body[:300], "done": checked})
    # Forward-looking: surface OPEN items first; keep done ones for context tail.
    open_items = [i for i in items if not i["done"]]
    done_items = [i for i in items if i["done"]]
    return {
        "items": open_items + done_items,
        "open_count": len(open_items),
        "done_count": len(done_items),
    }


def collect_backlog(cutoff: _dt.date) -> dict:
    """Dictated task captures within the window.

    Source 1: logs/daily/*.md — '### Capture (HH:MM) — task' blocks (dated).
    Source 2: memory.md::Active Priorities open checkboxes (current backlog,
              already covered by top_of_mind; here we surface the dictated
              task stream specifically).

    Only daily_log captures carry a real date, so the 30d window applies to
    those. Returns {items, count}.
    """
    items: list[dict] = []
    text = load_memory(["daily_log"])["daily_log"]
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for b in blocks[1:]:
        lines = b.splitlines()
        if not lines:
            continue
        date = _parse_date_header(lines[0])
        if not _within_window(date, cutoff):
            continue
        for sub in re.split(r"^###\s+", b, flags=re.MULTILINE)[1:]:
            m = re.match(r"Capture\s*\([\d:]+\)\s*[—-]\s*task", sub, re.IGNORECASE)
            if not m:
                continue
            rest = sub.split("\n", 1)
            snippet = (rest[1].strip() if len(rest) > 1 else "")[:240]
            items.append({"date": date.isoformat(), "snippet": snippet or "(пусто)"})
    items.sort(key=lambda x: x["date"], reverse=True)
    return {"items": items[:20], "count": len(items)}


def collect_weekly_plan() -> dict:
    """Latest weekly_review.md entry's 'Next Week Focus' — the forward plan.

    Falls back to the full body of the latest non-template weekly entry if the
    'Next Week Focus' subsection is absent.
    """
    entries = last_entries("weekly_review", limit=6)
    for body in reversed(entries):  # most-recent first
        header_line = body.splitlines()[0].strip() if body.splitlines() else ""
        # Skip the init placeholder / format spec entries.
        if "init" in header_line.lower() or header_line.lower().startswith("format"):
            continue
        if not re.match(r"\d{4}-W\d", header_line):
            continue
        focus = extract_section(body, "Next Week Focus")
        if focus:
            # Strip template angle-bracket stubs.
            cleaned = "\n".join(
                ln for ln in focus.splitlines()
                if not (ln.strip().startswith("<") and ln.strip().endswith(">"))
            ).strip()
            if cleaned:
                return {"week": header_line, "focus": cleaned[:800], "present": True}
        # No usable focus subsection — surface the body tail instead.
        tail = "\n".join(body.splitlines()[1:]).strip()
        if tail and "<" not in tail[:40]:
            return {"week": header_line, "focus": tail[:800], "present": True}
    return {"week": "", "focus": "", "present": False}


def _project_progress(proj: dict) -> dict:
    """Compute done/total from a project's Next Actions checkboxes."""
    raw = proj.get("next_actions_list", "") or ""
    total = done = 0
    for ln in raw.splitlines():
        s = ln.strip()
        if re.match(r"^\[[ xX]\]", s):
            total += 1
            if re.match(r"^\[[xX]\]", s):
                done += 1
    pct = round(done / total * 100) if total else 0
    return {"done": done, "total": total, "pct": pct}


def collect_active_projects() -> list[dict]:
    """Non-done active projects with simple progress + next action."""
    out = []
    for p in all_projects():
        status = _normalize_rank_token(p.get("status", ""))
        if status == "done":
            continue
        prog = _project_progress(p)
        next_first = (p.get("next_actions_list", "") or "").split("\n", 1)[0]
        next_first = re.sub(r"^\[[ xX]\]\s*", "", next_first.strip())
        out.append({
            "name": p["name"],
            "status": status or "—",
            "priority": _normalize_rank_token(p.get("priority", "")) or "—",
            "deadline": p.get("deadline", "—"),
            "next_review": p.get("next_review", "—"),
            "next_action_first": next_first,
            "progress": prog,
        })
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "—": 0}
    out.sort(key=lambda x: (-rank.get(x["priority"], 0), x["deadline"], x["name"]))
    return out


def collect_risks_watching(top_n: int = 8) -> list[dict]:
    """Open risks sorted by severity × probability."""
    rs = risks_by_severity("low")[:top_n]
    if not rs:
        rs = [r for r in all_risks() if (r.get("status") or "").lower() != "closed"][:top_n]
    out = []
    for r in rs:
        if (r.get("status") or "").lower() == "closed":
            continue
        out.append({
            "title": r.get("title", ""),
            "category": r.get("category", "—"),
            "severity": _normalize_rank_token(r.get("severity", "")) or "—",
            "probability": _normalize_rank_token(r.get("probability", "")) or "—",
            "status": _normalize_rank_token(r.get("status", "")) or "—",
            "mitigation": (r.get("mitigation", "") or "")[:200],
        })
    return out


def collect_health_trend(cutoff: _dt.date) -> dict:
    """Energy/Stress from logs/daily/*.md::Evening blocks within the window."""
    dates, energy, stress = [], [], []
    seen_dates: set[str] = set()
    for d in _daily_log_dirs():
        for f in sorted(d.glob("*.md")):
            entry_date = _parse_date_header(f.stem)
            if not _within_window(entry_date, cutoff):
                continue
            iso = entry_date.isoformat()
            if iso in seen_dates:
                continue
            content = f.read_text(encoding="utf-8", errors="ignore")
            ev = re.search(r"##\s+Evening\s*\([\d:]+\)\s*\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL)
            if not ev:
                continue
            body = ev.group(1)
            e = re.search(r"Energy[^:]*:\s*\*?\*?(\d+)", body, re.IGNORECASE)
            s = re.search(r"Stress[^:]*:\s*\*?\*?(\d+)", body, re.IGNORECASE)
            if e or s:
                seen_dates.add(iso)
                dates.append(iso)
                energy.append(int(e.group(1)) if e else None)
                stress.append(int(s.group(1)) if s else None)
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return {
        "dates": [dates[i] for i in order],
        "energy": [energy[i] for i in order],
        "stress": [stress[i] for i in order],
        "count": len(dates),
    }


def collect_recent_decisions(limit: int = 6) -> list[dict]:
    """Last decisions from decisions.md (most-recent first), template-stripped."""
    text = load_memory(["decisions"])["decisions"]
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    out = []
    for b in blocks[1:]:
        lines = b.splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        date = _parse_date_header(header)
        body = "\n".join(lines[1:])
        # Skip format / template blocks.
        if "format" in header.lower() or (header.startswith("<") and header.endswith(">")):
            continue
        dec = ""
        status = "—"
        for ln in body.splitlines():
            ms = re.match(r"^\s*\[?(decision|содержание)\]?\s*:\s*(.*)$", ln.strip(), re.IGNORECASE)
            if ms and not dec:
                dec = ms.group(2).strip()
            mst = re.match(r"^\s*\[?status\]?\s*:\s*(.*)$", ln.strip(), re.IGNORECASE)
            if mst:
                status = mst.group(1).strip() or "—"
        if not dec:
            # First non-label body line.
            for ln in body.splitlines():
                t = ln.strip()
                if t and not re.match(r"^\[?[A-Za-zА-Яа-я_]+\]?\s*:", t):
                    dec = t
                    break
        if dec.startswith("<") and dec.endswith(">"):
            continue
        if not dec:
            continue
        out.append({
            "date": date.isoformat() if date else "",
            "decision": dec[:300],
            "status": status,
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:limit]


# ── HTML rendering ───────────────────────────────────────────────────────────


def render_html(data: dict) -> str:
    """Compose the dark-theme TANDEM cockpit. Self-contained except Chart.js CDN."""
    generated_at = data["generated_at"]
    top = data["top_of_mind"]
    backlog = data["backlog"]
    plan = data["weekly_plan"]
    projects = data["projects"]
    risks = data["risks"]
    health = data["health"]
    decisions = data["decisions"]
    filled = data["filled_sections"]
    empty = data["empty_sections"]

    MUTED = '<span class="muted">—</span>'

    def _badge(value: str, css: str) -> str:
        v = (value or "").strip()
        if not v or v == "—":
            return MUTED
        return f'<span class="{css} {css}-{_esc(v)}">{_esc(v)}</span>'

    # ---- Top of mind ----
    if top["items"]:
        rows = ['<ul class="checklist">']
        for it in top["items"]:
            mark = "✅" if it["done"] else "🔸"
            cls = "done" if it["done"] else "open"
            rows.append(f'<li class="{cls}">{mark} {_esc(it["text"])}</li>')
        rows.append("</ul>")
        top_html = "\n".join(rows)
    else:
        top_html = ('<p class="empty">Нет открытых приоритетов. Запиши через '
                    '<code>/capture task: &lt;что сделать&gt;</code> голосом или текстом.</p>')

    # ---- Backlog ----
    if backlog["items"]:
        rows = ['<ul class="capture-list">']
        for it in backlog["items"]:
            rows.append(
                f'<li><span class="date">{_esc(it["date"])}</span> '
                f'<span class="snippet">{_esc(it["snippet"])}</span></li>'
            )
        rows.append("</ul>")
        backlog_html = "\n".join(rows)
    else:
        backlog_html = ('<p class="empty">Нет надиктованных задач за последние '
                        f'{BACKLOG_DAYS} дней. Диктуй задачи через '
                        '<code>/capture task: &lt;...&gt;</code> — попадут сюда.</p>')

    # ---- Weekly plan ----
    if plan["present"]:
        weekly_html = (
            f'<h3>{_esc(plan["week"])}</h3>'
            f'<pre>{_esc(plan["focus"])}</pre>'
        )
    else:
        weekly_html = ('<p class="empty">Нет фокуса недели. Запусти <code>/week</code> '
                       'в воскресенье — bot напомнит (cron), там заполняется Next Week Focus.</p>')

    # ---- Projects ----
    if projects:
        rows = ['<table class="data"><thead><tr><th>Проект</th><th>Приоритет</th>'
                '<th>Статус</th><th>Прогресс</th><th>Дедлайн</th><th>Next Action</th>'
                '</tr></thead><tbody>']
        for p in projects:
            prog = p["progress"]
            if prog["total"]:
                bar = (f'<div class="bar"><div class="bar-fill" style="width:{prog["pct"]}%"></div></div>'
                       f'<small>{prog["done"]}/{prog["total"]} ({prog["pct"]}%)</small>')
            else:
                bar = MUTED
            deadline_cell = _esc(p["deadline"]) if p["deadline"] and p["deadline"] != "—" else MUTED
            next_act = p["next_action_first"][:80] if p["next_action_first"] else ""
            next_cell = _esc(next_act) if next_act else MUTED
            rows.append(
                f'<tr><td><strong>{_esc(p["name"])}</strong></td>'
                f'<td>{_badge(p["priority"], "priority")}</td>'
                f'<td>{_badge(p["status"], "status")}</td>'
                f'<td>{bar}</td>'
                f'<td>{deadline_cell}</td>'
                f'<td><small>{next_cell}</small></td></tr>'
            )
        rows.append("</tbody></table>")
        projects_html = "\n".join(rows)
    else:
        projects_html = '<p class="empty">Нет active проектов в memory/projects.md.</p>'

    # ---- Risks ----
    if risks:
        rows = ['<table class="data"><thead><tr><th>Категория</th><th>Title</th>'
                '<th>Severity</th><th>Probability</th><th>Mitigation</th>'
                '</tr></thead><tbody>']
        for r in risks:
            cat = (r["category"] or "").strip()
            prob = (r["probability"] or "").strip()
            mit = (r["mitigation"] or "").strip()
            cat_cell = _esc(cat) if cat and cat != "—" else MUTED
            prob_cell = _esc(prob) if prob and prob != "—" else MUTED
            mit_cell = _esc(mit) if mit else MUTED
            rows.append(
                f'<tr><td>{cat_cell}</td>'
                f'<td><strong>{_esc(r["title"])}</strong></td>'
                f'<td>{_badge(r["severity"], "sev")}</td>'
                f'<td>{prob_cell}</td>'
                f'<td><small>{mit_cell}</small></td></tr>'
            )
        rows.append("</tbody></table>")
        risks_html = "\n".join(rows)
    else:
        risks_html = '<p class="empty">Нет рисков в memory/risks.md.</p>'

    # ---- Health trend ----
    if health["count"] >= 2:
        h_dates = json.dumps(health["dates"])
        h_energy = json.dumps(health["energy"])
        h_stress = json.dumps(health["stress"])
        health_html = f"""
<canvas id="healthChart" width="800" height="300"></canvas>
<script>
  const hctx = document.getElementById('healthChart').getContext('2d');
  new Chart(hctx, {{
    type: 'line',
    data: {{
      labels: {h_dates},
      datasets: [
        {{ label: 'Энергия (1-10)', data: {h_energy}, borderColor: '#5eead4', backgroundColor: 'rgba(94,234,212,0.15)', tension: 0.3, fill: true }},
        {{ label: 'Стресс (1-10)', data: {h_stress}, borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.15)', tension: 0.3, fill: true }}
      ]
    }},
    options: {{
      scales: {{ y: {{ min: 0, max: 10, ticks: {{ color: '#d4d4d8' }} }}, x: {{ ticks: {{ color: '#d4d4d8' }} }} }},
      plugins: {{ legend: {{ labels: {{ color: '#d4d4d8' }} }} }}
    }}
  }});
</script>
"""
    else:
        health_html = (f'<p class="empty">Недостаточно данных evening reviews '
                       f'({health["count"]} из 2+ нужно за {HEALTH_DAYS} дней). '
                       'Запускай <code>/evening</code> ежедневно — bot напомнит в 21:30 (cron).</p>')

    # ---- Decisions ----
    if decisions:
        rows = ['<table class="data"><thead><tr><th>Дата</th><th>Решение</th><th>Статус</th></tr></thead><tbody>']
        for d in decisions:
            date_cell = _esc(d["date"]) if d["date"] else MUTED
            status = (d["status"] or "").strip()
            status_cell = (
                f'<span class="status status-{_esc(status.lower())}">{_esc(status)}</span>'
                if status and status != "—" else MUTED
            )
            rows.append(
                f'<tr><td>{date_cell}</td>'
                f'<td><strong>{_esc(d["decision"])}</strong></td>'
                f'<td>{status_cell}</td></tr>'
            )
        rows.append("</tbody></table>")
        decisions_html = "\n".join(rows)
    else:
        decisions_html = ('<p class="empty">Нет решений в memory/decisions.md. '
                          'Фиксируй через <code>/capture decision: &lt;что и почему&gt;</code>.</p>')

    filled_str = ", ".join(filled) if filled else "—"
    empty_str = ", ".join(empty) if empty else "—"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>TANDEM Group — Executive Cockpit — {_esc(generated_at)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: #09090b; color: #e4e4e7; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; line-height: 1.55; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 30px 80px; }}
  header {{ text-align: center; padding: 40px 0; border-bottom: 1px solid #c4a747; margin-bottom: 30px; }}
  header h1 {{ font-size: 38px; margin: 0; color: #c4a747; letter-spacing: 0.05em; }}
  header .subtitle {{ color: #a1a1aa; margin-top: 10px; font-size: 15px; }}
  header .meta {{ color: #71717a; margin-top: 8px; font-size: 13px; }}
  section {{ background: #18181b; border-left: 4px solid #c4a747; padding: 28px 30px; margin: 24px 0; border-radius: 6px; }}
  section h2 {{ color: #c4a747; margin-top: 0; font-size: 22px; letter-spacing: 0.03em; }}
  section .desc {{ color: #a1a1aa; font-size: 13px; margin-top: -8px; margin-bottom: 18px; }}
  .empty {{ color: #71717a; font-style: italic; padding: 16px; background: #27272a; border-radius: 4px; }}
  .empty code {{ background: #3f3f46; padding: 2px 6px; border-radius: 3px; color: #fbbf24; font-style: normal; }}
  table.data {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
  table.data th {{ text-align: left; background: #27272a; padding: 10px 14px; color: #d4d4d8; border-bottom: 2px solid #c4a747; }}
  table.data td {{ padding: 10px 14px; border-bottom: 1px solid #27272a; vertical-align: top; }}
  .status, .severity, .priority {{ display: inline-block; padding: 3px 10px; border-radius: 3px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
  .priority-high {{ background: #7c2d12; color: #fed7aa; }}
  .priority-medium {{ background: #713f12; color: #fed7aa; }}
  .priority-low {{ background: #14532d; color: #bbf7d0; }}
  .priority--, .priority-— {{ background: #3f3f46; color: #a1a1aa; }}
  .sev-critical {{ background: #7f1d1d; color: #fecaca; }}
  .sev-high {{ background: #7c2d12; color: #fed7aa; }}
  .sev-medium {{ background: #713f12; color: #fed7aa; }}
  .sev-low {{ background: #14532d; color: #bbf7d0; }}
  .status-active {{ background: #14532d; color: #bbf7d0; }}
  .status-pending {{ background: #713f12; color: #fed7aa; }}
  .status-monitoring {{ background: #1e3a8a; color: #bfdbfe; }}
  .status-applied {{ background: #14532d; color: #bbf7d0; }}
  .bar {{ background: #27272a; border-radius: 4px; height: 8px; width: 90px; overflow: hidden; margin-bottom: 3px; }}
  .bar-fill {{ background: #c4a747; height: 100%; }}
  pre {{ background: #27272a; padding: 14px; border-radius: 4px; overflow-x: auto; font-size: 13px; color: #d4d4d8; white-space: pre-wrap; }}
  ul {{ padding-left: 22px; }}
  ul li {{ margin: 6px 0; }}
  ul.checklist {{ list-style: none; padding-left: 4px; }}
  ul.checklist li.done {{ color: #71717a; text-decoration: line-through; }}
  ul.capture-list {{ list-style: none; padding-left: 4px; }}
  h3 {{ color: #d4d4d8; font-size: 16px; margin: 18px 0 6px; }}
  .date {{ color: #71717a; font-size: 12px; margin-right: 6px; }}
  .snippet {{ color: #e4e4e7; }}
  .footer {{ text-align: center; color: #52525b; font-size: 12px; margin-top: 60px; padding-top: 30px; border-top: 1px solid #27272a; }}
  .footer a {{ color: #a1a1aa; }}
  .muted {{ color: #52525b; font-style: italic; }}
  .filled-summary {{ background: #052e16; border-left: 4px solid #16a34a; padding: 14px 18px; margin: 16px 0; border-radius: 4px; font-size: 14px; }}
  .empty-summary {{ background: #1e1b06; border-left: 4px solid #ca8a04; padding: 14px 18px; margin: 16px 0; border-radius: 4px; font-size: 14px; }}
  .nudge {{ background: #1e1b06; border-left: 4px solid #c4a747; padding: 16px 20px; border-radius: 4px; font-size: 14px; color: #d4d4d8; }}
  .nudge code {{ background: #27272a; padding: 1px 6px; border-radius: 3px; color: #fbbf24; }}
  @media (max-width: 768px) {{ .container {{ padding: 20px 16px 60px; }} header h1 {{ font-size: 28px; }} }}
  @media print {{ body {{ background: #fff; color: #111; }} section {{ background: #fafafa; border-color: #c4a747; }} table.data th {{ background: #f4f4f5; color: #111; }} }}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>TANDEM GROUP</h1>
  <div class="subtitle">Executive Cockpit — взгляд вперёд</div>
  <div class="meta">Generated: {_esc(generated_at)} · CEO: Alexandr Scerbina</div>
</header>

<section>
  <h2>📊 Снимок</h2>
  <div class="desc">Только реальные данные из памяти. Forward-looking — что на столе сейчас и что впереди.</div>
  {f'<div class="filled-summary"><strong>Заполнено:</strong> {filled_str}</div>' if filled else ''}
  {f'<div class="empty-summary"><strong>Пусто (как заполнить — внутри секций):</strong> {empty_str}</div>' if empty else ''}
</section>

<section>
  <h2>🎯 Top-of-mind сегодня</h2>
  <div class="desc">Открытые приоритеты из memory/memory.md::Active Priorities.</div>
  {top_html}
</section>

<section>
  <h2>🎤 Backlog надиктованного</h2>
  <div class="desc">Задачи через /capture task: за последние {BACKLOG_DAYS} дней (из logs/daily).</div>
  {backlog_html}
</section>

<section>
  <h2>📅 Weekly Plan</h2>
  <div class="desc">Next Week Focus из последнего weekly review.</div>
  {weekly_html}
</section>

<section>
  <h2>📂 Активные проекты</h2>
  <div class="desc">Из memory/projects.md, отсортировано по priority. Прогресс — по чекбоксам Next Actions.</div>
  {projects_html}
</section>

<section>
  <h2>⚠ Риски под наблюдением</h2>
  <div class="desc">Из memory/risks.md, sorted by severity × probability. NO fake threat levels.</div>
  {risks_html}
</section>

<section>
  <h2>💗 Тренд энергии и стресса</h2>
  <div class="desc">Из ежедневных /evening reviews за {HEALTH_DAYS} дней. Min 2 точки для графика.</div>
  {health_html}
</section>

<section>
  <h2>📝 Журнал решений (недавние)</h2>
  <div class="desc">Из memory/decisions.md, последние записи. NO fake decisions.</div>
  {decisions_html}
</section>

<section>
  <h2>🎤 Quick-capture</h2>
  <div class="nudge">
    Держи кокпит живым — диктуй по ходу дня:<br>
    <code>/capture task: …</code> — задача · <code>/capture decision: …</code> — решение ·
    <code>/capture insight: …</code> — мысль<br>
    Вечером <code>/evening</code>, в воскресенье <code>/week</code> — тренд и план заполняются сами.
  </div>
</section>

<div class="footer">
  <p><strong>TANDEM Group</strong> · Executive Operating System (Hermes V1)</p>
  <p>Сгенерировано {_esc(generated_at)} из real CEO memory. NO fabricated stats, NO external market data.</p>
  <p>Открой в Chrome → File → Print → Save as PDF для PDF-версии.</p>
</div>

</div>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None,
                        help="Output directory. Defaults to /opt/data/reports/ or repo/reports/.")
    parser.add_argument("--no-upload", action="store_true",
                        help="Skip building public URL (no HERMES_PUBLIC_HOST lookup).")
    args = parser.parse_args()

    backlog_cutoff = _today() - _dt.timedelta(days=BACKLOG_DAYS)
    health_cutoff = _today() - _dt.timedelta(days=HEALTH_DAYS)

    top = collect_top_of_mind()
    backlog = collect_backlog(backlog_cutoff)
    plan = collect_weekly_plan()
    projects = collect_active_projects()
    risks = collect_risks_watching(top_n=8)
    health = collect_health_trend(health_cutoff)
    decisions = collect_recent_decisions(limit=6)

    filled, empty = [], []
    (filled if top["items"] else empty).append("top-of-mind")
    (filled if backlog["items"] else empty).append("backlog")
    (filled if plan["present"] else empty).append("weekly-plan")
    (filled if projects else empty).append("projects")
    (filled if risks else empty).append("risks")
    (filled if health["count"] >= 2 else empty).append("health")
    (filled if decisions else empty).append("decisions")

    generated_at = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    html_content = render_html({
        "generated_at": generated_at,
        "top_of_mind": top,
        "backlog": backlog,
        "weekly_plan": plan,
        "projects": projects,
        "risks": risks,
        "health": health,
        "decisions": decisions,
        "filled_sections": filled,
        "empty_sections": empty,
    })

    # Resolve output directory (prod /opt/data first, else repo/reports).
    if args.output:
        out_dir = pathlib.Path(args.output)
    elif pathlib.Path("/opt/data").exists():
        out_dir = pathlib.Path("/opt/data/reports")
    else:
        out_dir = _REPO / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    uuid_filename = f"{_uuid.uuid4()}.html"
    file_path = out_dir / uuid_filename
    friendly_name = f"tandem-dashboard-{today_iso()}.html"
    friendly_path = out_dir / friendly_name

    public_url = None if args.no_upload else public_dashboard_url(uuid_filename)

    if public_url:
        html_with_url = html_content.replace(
            "Открой в Chrome → File → Print → Save as PDF для PDF-версии.",
            'Открой в Chrome → File → Print → Save as PDF для PDF-версии.</p>'
            f'<p>🔗 <a href="{public_url}" style="color:#5eead4">Публичная ссылка на этот кокпит</a></p>'
            '<p style="color:#52525b;font-size:11px">Ссылка содержит random uuid — невозможно угадать. '
            'Хостится на твоём Railway endpoint.',
        )
    else:
        html_with_url = html_content

    file_path.write_text(html_with_url, encoding="utf-8")

    # Friendly symlink for local browsing; the URL always uses the uuid filename.
    try:
        if friendly_path.exists() or friendly_path.is_symlink():
            friendly_path.unlink()
        friendly_path.symlink_to(uuid_filename)
    except OSError:
        pass

    upload_status = {
        "requested": not args.no_upload,
        "ok": bool(public_url),
        "reason": "" if public_url else "HERMES_PUBLIC_HOST env var not set in Railway",
        "url": public_url,
    }

    # ---- Deterministic Telegram caption (ready-to-send, not LLM-built) ----
    html_size_kb = round(file_path.stat().st_size / 1024, 1)
    cap_lines = [
        "📊 **Executive Cockpit** — взгляд вперёд",
        "",
        f"🎯 Top-of-mind: {top['open_count']} откр. · 🎤 backlog: {backlog['count']} задач(и)",
        f"📂 Проектов: {len(projects)} · ⚠ рисков: {len(risks)} · 📝 решений: {len(decisions)}",
        f"📈 Секций с данными: {len(filled)}/7",
    ]
    if empty:
        cap_lines.append(f"⚠ Пусто: {', '.join(empty)} (как заполнить — внутри)")
    cap_lines.append("")
    if public_url:
        cap_lines.append("🔗 **Открыть (любое устройство):**")
        cap_lines.append(public_url)
        cap_lines.append("   Persistent URL на твоём Railway endpoint.")
    elif upload_status.get("requested"):
        cap_lines.append(f"⚠ Публичная ссылка отключена: {upload_status.get('reason', 'unknown')}")
        cap_lines.append("   Railway → hermes → Settings → Networking → Generate Domain")
        cap_lines.append("   Потом Variables → HERMES_PUBLIC_HOST = <domain>")
    cap_lines.append("")
    cap_lines.append(f"📎 HTML во вложении ({html_size_kb} KB) — interactive с charts.")
    telegram_caption = "\n".join(cap_lines)

    result = {
        "html_path": str(file_path),
        "html_size_kb": html_size_kb,
        "public_url": public_url,
        "upload_status": upload_status,
        "generated_at": generated_at,
        "filled": filled,
        "empty": empty,
        "stats": {
            "top_of_mind_open": top["open_count"],
            "top_of_mind_done": top["done_count"],
            "backlog_tasks": backlog["count"],
            "weekly_plan_present": plan["present"],
            "active_projects": len(projects),
            "risks": len(risks),
            "health_datapoints": health["count"],
            "decisions": len(decisions),
        },
        # CRITICAL: the agent must use this field verbatim as the Telegram
        # caption. Do NOT rewrite, shorten, translate, or remove the URL.
        "telegram_caption": telegram_caption,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
