"""Generate professional HTML dashboard report from REAL memory data.

Hard rules (enforced by code, not relying on LLM):
  - Only reads memory/*.md, logs/daily/*.md, logs/weekly/*.md — no external sources
  - No hardcoded competitor / market / news strings
  - Empty sections render explicit "(нет данных за период)" — never fabricated
  - HTML self-contained (Chart.js via CDN <script> tag, no other deps)
  - Optional PDF rendering via headless Chromium CLI (no Python playwright
    binding required; uses /opt/hermes/.playwright/* binary baked in image)

Usage:
  python generate_report.py --period week --output /opt/data/reports
  python generate_report.py --period month
  python generate_report.py --period quarter
  python generate_report.py --period all
  python generate_report.py --period week --pdf   # also writes .pdf

Returns JSON to stdout:
  {"html_path": "...", "pdf_path": "..." | null, ...}
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import glob
import html
import json
import mimetypes
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid as _uuid

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
# Production fallback: skills/ceo/_lib/ lives only in /opt/hermes (built
# into image). Hermes skill-sync to /opt/data copies only skill dirs with
# SKILL.md; _lib/ has no SKILL.md so it stays in image path.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    _normalize_rank_token,
    all_projects,
    all_risks,
    iso_week,
    last_entries,
    load_memory,
    today_iso,
)


PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90, "all": 36500}


# ── Chromium discovery + PDF generation ──────────────────────────────────────


def find_chromium_binary() -> str | None:
    """Locate a usable headless Chromium binary.

    Tries Playwright-bundled binaries (from `npx playwright install chromium
    --only-shell` in Hermes Dockerfile line 53), then system chromium / chrome
    if available. Returns absolute path or None.
    """
    # 1. Playwright bundled paths (most reliable in Hermes container)
    playwright_root = "/opt/hermes/.playwright"
    patterns = [
        f"{playwright_root}/chromium_headless_shell-*/chrome-linux/headless_shell",
        f"{playwright_root}/chromium-*/chrome-linux/chrome",
        f"{playwright_root}/chromium-*/chrome-linux/headless_shell",
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat))
        if matches:
            return matches[-1]  # latest version

    # 2. System chromium / chrome
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path

    return None


def html_to_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path, timeout: int = 60) -> dict:
    """Render HTML to PDF via headless Chromium CLI. Returns status dict."""
    chromium = find_chromium_binary()
    if not chromium:
        return {
            "ok": False,
            "reason": "Chromium binary not found. Install via "
                      "`npx playwright install chromium --only-shell` or add to image.",
        }

    cmd = [
        chromium,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--virtual-time-budget=8000",   # wait up to 8s for Chart.js to render
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        f"file://{html_path.resolve()}",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 or not pdf_path.exists():
            return {
                "ok": False,
                "reason": f"chromium exit {proc.returncode}: {proc.stderr.strip()[:300]}",
                "binary": chromium,
            }
        return {
            "ok": True,
            "binary": chromium,
            "size_kb": round(pdf_path.stat().st_size / 1024, 1),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"chromium timeout after {timeout}s", "binary": chromium}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "binary": chromium}


# ── Public URL upload (catbox.moe — free, no auth, no expiration) ───────────


_CATBOX_URL = "https://catbox.moe/user/api.php"
_UPLOAD_UA = "Hermes-Report-Uploader/0.1 (alexandr.scerbina@gmail.com)"


def upload_to_catbox(file_path: pathlib.Path, timeout: int = 30) -> dict:
    """Upload a file to catbox.moe. Returns dict with ok/url/error.

    catbox.moe is a free public file host. URLs have random 6-char hashes,
    not guessable. No registration, no expiration. Max 200MB per file.

    Returns:
      {ok: True, url: "https://files.catbox.moe/xxxxxx.html"}
      {ok: False, reason: "..."}
    """
    if not file_path.exists():
        return {"ok": False, "reason": f"File not found: {file_path}"}

    try:
        # Build multipart/form-data manually (stdlib only)
        boundary = f"----HermesBoundary{_uuid.uuid4().hex}"
        ctype, _ = mimetypes.guess_type(str(file_path))
        ctype = ctype or "application/octet-stream"

        file_bytes = file_path.read_bytes()

        body_parts = []
        # Field: reqtype=fileupload
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="reqtype"\r\n\r\n')
        body_parts.append(b"fileupload\r\n")
        # Field: fileToUpload=@file
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="fileToUpload"; filename="{file_path.name}"\r\n'.encode()
        )
        body_parts.append(f"Content-Type: {ctype}\r\n\r\n".encode())
        body_parts.append(file_bytes)
        body_parts.append(b"\r\n")
        body_parts.append(f"--{boundary}--\r\n".encode())

        body = b"".join(body_parts)
        headers = {
            "User-Agent": _UPLOAD_UA,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }

        req = urllib.request.Request(_CATBOX_URL, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_text = resp.read().decode("utf-8", errors="replace").strip()

        if response_text.startswith("https://") and "catbox.moe" in response_text:
            return {"ok": True, "url": response_text, "size_kb": round(len(file_bytes) / 1024, 1)}
        return {"ok": False, "reason": f"Unexpected response: {response_text[:200]}"}

    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "reason": f"upload error: {type(e).__name__}: {e}"}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _today() -> _dt.date:
    return _dt.date.today()


def _parse_date_header(line: str) -> _dt.date | None:
    """Parse 'YYYY-MM-DD' or 'YYYY-MM-DD — slug' from an entry header."""
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


# ── Section collectors ───────────────────────────────────────────────────────


_DECISION_FIELD_ALIASES = {
    "decision": "decision",
    "содержание": "decision",
    "[содержание]": "decision",
    "reason": "reason",
    "контекст": "reason",
    "[контекст]": "reason",
    "expected_result": "expected_result",
    "review_date": "review_date",
    "status": "status",
    "тип": "kind",
    "[тип]": "kind",
    "date": "date_field",
}


def _flatten_inline_brackets(text: str) -> str:
    """Convert single-line `[ключ]: value [ключ2]: value` into multi-line key:value."""
    return re.sub(r"\s+(\[[а-яa-z_]+\]:)", r"\n\1", text, flags=re.IGNORECASE)


def collect_decisions(cutoff: _dt.date) -> list[dict]:
    """Pull decisions.md entries with date >= cutoff.

    Tolerates two formats:
      1. Formal blueprint shape: 'Decision: ...', 'Reason: ...', 'Status: ...'
      2. Capture template shape: '[тип]: decision', '[контекст]: ...', '[содержание]: ...'
    """
    text = load_memory(["decisions"])["decisions"]
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    out = []
    for b in blocks[1:]:
        lines = b.splitlines()
        if not lines:
            continue
        header = lines[0]
        date = _parse_date_header(header)
        if not _within_window(date, cutoff):
            continue
        body_raw = "\n".join(lines[1:]).strip()
        body = _flatten_inline_brackets(body_raw)
        fields: dict[str, str] = {}
        current_key: str | None = None
        for line in body.splitlines():
            s = line.rstrip()
            if not s.strip():
                current_key = None
                continue
            m = re.match(r"^\s*\[?([A-Za-zА-Яа-я_]+)\]?\s*:\s*(.*)$", s)
            if m and m.group(1).strip().lower() in _DECISION_FIELD_ALIASES:
                canonical = _DECISION_FIELD_ALIASES[m.group(1).strip().lower()]
                fields[canonical] = m.group(2).strip()
                current_key = canonical
            elif current_key and s.startswith((" ", "\t")) or (current_key and not re.match(r"^\s*\[?[A-Za-zА-Яа-я_]+\]?\s*:", s)):
                # continuation of previous field (multi-line content)
                fields[current_key] = (fields.get(current_key, "") + "\n" + s.strip()).strip()
            else:
                current_key = None
        decision_text = fields.get("decision", "").strip()
        if not decision_text:
            # Last-ditch fallback: take first non-empty body line that isn't a `[label]:` token
            for ln in body.splitlines():
                ln_s = ln.strip()
                if ln_s and not re.match(r"^\[?[A-Za-zА-Яа-я_]+\]?\s*:", ln_s):
                    decision_text = ln_s
                    break
            if not decision_text:
                decision_text = body_raw[:200] or "(пусто)"
        out.append({
            "header": header.strip(),
            "date": date.isoformat() if date else "",
            "decision": decision_text[:400],
            "reason": fields.get("reason", "")[:300],
            "status": fields.get("status", "—") or "—",
            "review_date": fields.get("review_date", "—") or "—",
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def collect_captures_by_type(cutoff: _dt.date) -> dict:
    """daily_log.md entries grouped by ### Capture (...) type."""
    text = load_memory(["daily_log"])["daily_log"]
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    type_counts = collections.Counter()
    items_by_type = collections.defaultdict(list)
    for b in blocks[1:]:
        lines = b.splitlines()
        if not lines:
            continue
        date = _parse_date_header(lines[0])
        if not _within_window(date, cutoff):
            continue
        # Look for ### Capture (HH:MM) — <type>
        for sub in re.split(r"^###\s+", b, flags=re.MULTILINE)[1:]:
            m = re.match(r"Capture\s*\([\d:]+\)\s*[—-]\s*(\w+)", sub)
            if not m:
                continue
            t = m.group(1).lower()
            type_counts[t] += 1
            snippet = sub.split("\n", 2)
            snippet_text = "\n".join(snippet[1:3]).strip()[:240]
            items_by_type[t].append({
                "date": date.isoformat(),
                "snippet": snippet_text,
            })
    return {
        "counts": dict(type_counts),
        "total": sum(type_counts.values()),
        "items": {k: v[:10] for k, v in items_by_type.items()},
    }


def collect_weekly_reviews(cutoff: _dt.date) -> list[dict]:
    text = load_memory(["weekly_review"])["weekly_review"]
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    out = []
    for b in blocks[1:]:
        lines = b.splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        # Skip the init placeholder explicitly
        if "init" in header.lower() or header.startswith("(") or header.startswith("Format"):
            continue
        # ISO week format: 2026-W20
        m = re.match(r"(\d{4})-W(\d{1,2})", header)
        if not m:
            continue
        try:
            entry_year = int(m.group(1))
            entry_week = int(m.group(2))
            # Convert iso week to date (Mon)
            entry_date = _dt.date.fromisocalendar(entry_year, entry_week, 1)
        except (ValueError, AttributeError):
            continue
        if not _within_window(entry_date, cutoff):
            continue
        body = "\n".join(lines[1:]).strip()
        out.append({
            "iso_week": header,
            "date": entry_date.isoformat(),
            "body": body[:600],
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def collect_evening_trend(cutoff: _dt.date) -> dict:
    """Parse logs/daily/*.md::Evening (HH:MM) sections, extract Energy/Stress numeric."""
    logs_dir = _REPO / "logs" / "daily"
    # Also check /opt/data/logs/daily (production)
    prod_logs_dir = pathlib.Path("/opt/data/logs/daily")
    dirs_to_check = []
    if logs_dir.exists():
        dirs_to_check.append(logs_dir)
    if prod_logs_dir.exists() and prod_logs_dir != logs_dir:
        dirs_to_check.append(prod_logs_dir)

    dates, energy, stress = [], [], []
    for d in dirs_to_check:
        for f in sorted(d.glob("*.md")):
            stem = f.stem
            entry_date = _parse_date_header(stem)
            if not _within_window(entry_date, cutoff):
                continue
            content = f.read_text(encoding="utf-8", errors="ignore")
            # Find Evening section
            ev_match = re.search(r"##\s+Evening\s*\([\d:]+\)\s*\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL)
            if not ev_match:
                continue
            ev_body = ev_match.group(1)
            e_match = re.search(r"Energy[^:]*:\s*\*?\*?(\d+)", ev_body, re.IGNORECASE)
            s_match = re.search(r"Stress[^:]*:\s*\*?\*?(\d+)", ev_body, re.IGNORECASE)
            if e_match or s_match:
                dates.append(entry_date.isoformat())
                energy.append(int(e_match.group(1)) if e_match else None)
                stress.append(int(s_match.group(1)) if s_match else None)
    return {"dates": dates, "energy": energy, "stress": stress, "count": len(dates)}


def collect_top_risks(top_n: int = 5) -> list[dict]:
    """Return top N risks by severity × probability.

    Fallback: if no risk has severity filled, return all risks (so user sees
    them on dashboard and remembers to fill fields).
    """
    from skills.ceo._lib.memory import risks_by_severity
    rs = risks_by_severity("low")[:top_n]
    if not rs:
        # No severities filled — show what we have so user knows what's missing
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


def collect_active_projects() -> list[dict]:
    """All non-done active projects."""
    out = []
    for p in all_projects():
        status = _normalize_rank_token(p.get("status", ""))
        if status == "done":
            continue
        out.append({
            "name": p["name"],
            "status": status or "—",
            "priority": _normalize_rank_token(p.get("priority", "")) or "—",
            "deadline": p.get("deadline", "—"),
            "last_update": p.get("last_update", "—"),
            "next_review": p.get("next_review", "—"),
            "next_action_first": (p.get("next_actions_list", "") or "").split("\n", 1)[0],
        })
    # Sort: priority desc, then deadline
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "—": 0}
    out.sort(key=lambda x: (-rank.get(x["priority"], 0), x["deadline"], x["name"]))
    return out


# ── HTML rendering ───────────────────────────────────────────────────────────


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def render_html(data: dict) -> str:
    """Compose dark-theme TANDEM dashboard. Self-contained except Chart.js CDN."""
    period_label = data["period_label"]
    generated_at = data["generated_at"]
    cutoff = data["cutoff"]
    decisions = data["decisions"]
    captures = data["captures"]
    weekly = data["weekly_reviews"]
    projects = data["active_projects"]
    risks = data["top_risks"]
    trend = data["evening_trend"]

    empty_sections = data["empty_sections"]
    filled_sections = data["filled_sections"]

    # ---- Captures section ----
    if captures["total"] > 0:
        rows = []
        for t, items in captures["items"].items():
            rows.append(f'<h3>{_esc(t)} ({len(items)})</h3><ul>')
            for it in items[:5]:
                rows.append(
                    f'<li><span class="date">{_esc(it["date"])}</span> — '
                    f'<span class="snippet">{_esc(it["snippet"])}</span></li>'
                )
            rows.append("</ul>")
        captures_html = "\n".join(rows)
        captures_chart_data = json.dumps(captures["counts"])
    else:
        captures_html = '<p class="empty">Нет captures за период. Запиши через <code>/capture &lt;текст&gt;</code> голосом или текстом.</p>'
        captures_chart_data = "{}"

    # ---- Decisions ----
    MUTED_DASH_DEC = '<span class="muted">—</span>'
    if decisions:
        rows = ['<table class="data"><thead><tr><th>Дата</th><th>Решение</th><th>Статус</th><th>Review</th></tr></thead><tbody>']
        for d in decisions:
            status = (d["status"] or "").strip()
            review = (d["review_date"] or "").strip()
            status_cell = (
                f'<span class="status status-{_esc(status.lower())}">{_esc(status)}</span>'
                if status and status != "—" else MUTED_DASH_DEC
            )
            review_cell = _esc(review) if review and review != "—" else MUTED_DASH_DEC
            reason_html = f'<br><small class="reason">{_esc(d["reason"])}</small>' if d["reason"] else ""
            rows.append(
                f'<tr><td>{_esc(d["date"])}</td>'
                f'<td><strong>{_esc(d["decision"])}</strong>{reason_html}</td>'
                f'<td>{status_cell}</td>'
                f'<td>{review_cell}</td></tr>'
            )
        rows.append("</tbody></table>")
        decisions_html = "\n".join(rows)
    else:
        decisions_html = '<p class="empty">Нет decisions за период. Зафиксируй важное через <code>/capture decision: &lt;что и почему&gt;</code>.</p>'

    # ---- Weekly reviews ----
    if weekly:
        rows = []
        for w in weekly:
            rows.append(
                f'<div class="weekly-entry">'
                f'<h3>{_esc(w["iso_week"])} <small>(week of {_esc(w["date"])})</small></h3>'
                f'<pre>{_esc(w["body"])}</pre></div>'
            )
        weekly_html = "\n".join(rows)
    else:
        weekly_html = '<p class="empty">Нет weekly reviews за период. Запускай <code>/week</code> в воскресенье 18:00 — bot сам напомнит (cron).</p>'

    # ---- Projects ----
    def _badge_or_dash(value: str, css_class: str) -> str:
        v = (value or "").strip()
        if not v or v == "—":
            return '<span class="muted">—</span>'
        return f'<span class="{css_class} {css_class}-{_esc(v)}">{_esc(v)}</span>'

    MUTED_DASH = '<span class="muted">—</span>'
    if projects:
        rows = ['<table class="data"><thead><tr><th>Проект</th><th>Приоритет</th><th>Статус</th><th>Дедлайн</th><th>Next Action</th></tr></thead><tbody>']
        for p in projects:
            next_act = p["next_action_first"][:80] if p["next_action_first"] else ""
            deadline_cell = _esc(p["deadline"]) if p["deadline"] and p["deadline"] != "—" else MUTED_DASH
            next_cell = _esc(next_act) if next_act else MUTED_DASH
            rows.append(
                f'<tr><td><strong>{_esc(p["name"])}</strong></td>'
                f'<td>{_badge_or_dash(p["priority"], "priority")}</td>'
                f'<td>{_badge_or_dash(p["status"], "status")}</td>'
                f'<td>{deadline_cell}</td>'
                f'<td><small>{next_cell}</small></td></tr>'
            )
        rows.append("</tbody></table>")
        empty_count = sum(
            1 for p in projects
            if p["priority"] == "—" and p["status"] == "—" and p["deadline"] in ("", "—")
        )
        if empty_count:
            rows.append(
                f'<p class="hint">⚠ {empty_count} проект(а/ов) без полей. '
                f'Заполни priority/status/deadline через прямое редактирование '
                f'<code>memory/projects.md</code> или скажи боту в чате '
                f'«обнови проект &lt;name&gt;: priority=high, deadline=2026-07-01».</p>'
            )
        projects_html = "\n".join(rows)
    else:
        projects_html = '<p class="empty">Нет active проектов в memory/projects.md.</p>'

    # ---- Risks ----
    if risks:
        rows = ['<table class="data"><thead><tr><th>Категория</th><th>Title</th><th>Severity</th><th>Probability</th><th>Mitigation</th></tr></thead><tbody>']
        for r in risks:
            cat = (r["category"] or "").strip()
            prob = (r["probability"] or "").strip()
            mit = (r["mitigation"] or "").strip()
            cat_cell = _esc(cat) if cat and cat != "—" else MUTED_DASH
            prob_cell = _esc(prob) if prob and prob != "—" else MUTED_DASH
            mit_cell = _esc(mit) if mit else MUTED_DASH
            rows.append(
                f'<tr><td>{cat_cell}</td>'
                f'<td><strong>{_esc(r["title"])}</strong></td>'
                f'<td>{_badge_or_dash(r["severity"], "sev")}</td>'
                f'<td>{prob_cell}</td>'
                f'<td><small>{mit_cell}</small></td></tr>'
            )
        rows.append("</tbody></table>")
        empty_count = sum(
            1 for r in risks
            if r["severity"] == "—" and (r["probability"] or "—") == "—" and not (r["mitigation"] or "").strip()
        )
        if empty_count:
            rows.append(
                f'<p class="hint">⚠ {empty_count} риск(а/ов) без полей. '
                f'Заполни severity/probability/mitigation через прямое редактирование '
                f'<code>memory/risks.md</code>.</p>'
            )
        risks_html = "\n".join(rows)
    else:
        risks_html = '<p class="empty">Нет рисков в memory/risks.md.</p>'

    # ---- Energy/Stress trend ----
    if trend["count"] >= 2:
        trend_dates = json.dumps(trend["dates"])
        trend_energy = json.dumps(trend["energy"])
        trend_stress = json.dumps(trend["stress"])
        trend_html = f"""
<canvas id="trendChart" width="800" height="320"></canvas>
<script>
  const tctx = document.getElementById('trendChart').getContext('2d');
  new Chart(tctx, {{
    type: 'line',
    data: {{
      labels: {trend_dates},
      datasets: [
        {{ label: 'Энергия (1-10)', data: {trend_energy}, borderColor: '#5eead4', backgroundColor: 'rgba(94,234,212,0.15)', tension: 0.3, fill: true }},
        {{ label: 'Стресс (1-10)', data: {trend_stress}, borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.15)', tension: 0.3, fill: true }}
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
        trend_html = f'<p class="empty">Недостаточно данных evening reviews ({trend["count"]} из 2+ нужно). Запускай <code>/evening</code> ежедневно — bot напомнит в 21:30 (cron).</p>'

    # ---- Captures chart ----
    if captures["total"] > 0:
        captures_chart_html = f"""
<canvas id="capturesChart" width="500" height="320"></canvas>
<script>
  const ccData = {captures_chart_data};
  const ccLabels = Object.keys(ccData);
  const ccValues = Object.values(ccData);
  new Chart(document.getElementById('capturesChart').getContext('2d'), {{
    type: 'doughnut',
    data: {{
      labels: ccLabels,
      datasets: [{{
        data: ccValues,
        backgroundColor: ['#fbbf24', '#5eead4', '#a78bfa', '#fb7185', '#60a5fa', '#34d399']
      }}]
    }},
    options: {{ plugins: {{ legend: {{ position: 'right', labels: {{ color: '#d4d4d8' }} }} }} }}
  }});
</script>
"""
    else:
        captures_chart_html = ""

    # ---- Executive summary ----
    summary_bits = []
    if decisions:
        summary_bits.append(f"<li><strong>{len(decisions)} decision(s)</strong> зафиксировано</li>")
    if captures["total"] > 0:
        summary_bits.append(f"<li><strong>{captures['total']} capture(s)</strong> в memory ({', '.join(captures['counts'].keys())})</li>")
    if weekly:
        summary_bits.append(f"<li><strong>{len(weekly)} weekly review(s)</strong></li>")
    if projects:
        high_p = [p for p in projects if p["priority"] == "high"]
        summary_bits.append(f"<li><strong>{len(projects)} active projects</strong> ({len(high_p)} high priority)</li>")
    if risks:
        crit_h = [r for r in risks if r["severity"] in ("critical", "high")]
        summary_bits.append(f"<li><strong>{len(risks)} active risks</strong> ({len(crit_h)} critical/high)</li>")
    if trend["count"] > 0:
        e_vals = [v for v in trend["energy"] if v is not None]
        s_vals = [v for v in trend["stress"] if v is not None]
        if e_vals:
            summary_bits.append(f"<li>Энергия avg <strong>{sum(e_vals)/len(e_vals):.1f}/10</strong> ({len(e_vals)} замеров)</li>")
        if s_vals:
            summary_bits.append(f"<li>Стресс avg <strong>{sum(s_vals)/len(s_vals):.1f}/10</strong> ({len(s_vals)} замеров)</li>")

    if summary_bits:
        summary_html = "<ul>" + "".join(summary_bits) + "</ul>"
    else:
        summary_html = '<p class="empty">Памяти за период мало. Запускай <code>/capture</code>, <code>/evening</code>, <code>/week</code> регулярно — потом отчёт будет содержательным.</p>'

    # ---- Assemble HTML ----
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>TANDEM Group — Executive Report — {_esc(period_label)} — {_esc(generated_at)}</title>
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
  table.data small.reason {{ color: #71717a; }}
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
  pre {{ background: #27272a; padding: 14px; border-radius: 4px; overflow-x: auto; font-size: 13px; color: #d4d4d8; white-space: pre-wrap; }}
  ul {{ padding-left: 22px; }}
  ul li {{ margin: 6px 0; }}
  h3 {{ color: #d4d4d8; font-size: 16px; margin: 18px 0 6px; }}
  .date {{ color: #71717a; font-size: 12px; margin-right: 6px; }}
  .snippet {{ color: #e4e4e7; }}
  .footer {{ text-align: center; color: #52525b; font-size: 12px; margin-top: 60px; padding-top: 30px; border-top: 1px solid #27272a; }}
  .footer a {{ color: #a1a1aa; }}
  .filled-summary {{ background: #052e16; border-left: 4px solid #16a34a; padding: 14px 18px; margin: 16px 0; border-radius: 4px; font-size: 14px; }}
  .empty-summary {{ background: #1e1b06; border-left: 4px solid #ca8a04; padding: 14px 18px; margin: 16px 0; border-radius: 4px; font-size: 14px; }}
  .muted {{ color: #52525b; font-style: italic; }}
  .hint {{ color: #a1a1aa; font-size: 12px; padding: 12px 14px; margin-top: 14px; background: #18181b; border: 1px solid #27272a; border-radius: 4px; }}
  .hint code {{ background: #27272a; padding: 1px 6px; border-radius: 3px; color: #fbbf24; }}
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 24px; }}
  @media (max-width: 768px) {{ .charts-row {{ grid-template-columns: 1fr; }} .container {{ padding: 20px 16px 60px; }} header h1 {{ font-size: 28px; }} }}
  @media print {{ body {{ background: #fff; color: #111; }} section {{ background: #fafafa; border-color: #c4a747; }} table.data th {{ background: #f4f4f5; color: #111; }} }}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>TANDEM GROUP</h1>
  <div class="subtitle">Executive Report — {_esc(period_label)}</div>
  <div class="meta">Generated: {_esc(generated_at)} · Period from {_esc(cutoff)} · CEO: Alexandr Scerbina</div>
</header>

<section>
  <h2>📋 Executive Summary</h2>
  <div class="desc">Что произошло за период — только реальные данные из памяти.</div>
  {summary_html}
  {f'<div class="filled-summary"><strong>Заполнено секций:</strong> {", ".join(filled_sections)}</div>' if filled_sections else ''}
  {f'<div class="empty-summary"><strong>Пустые секции (как заполнить — внутри):</strong> {", ".join(empty_sections)}</div>' if empty_sections else ''}
</section>

<section>
  <h2>📝 Decisions Made</h2>
  <div class="desc">Из memory/decisions.md за период. NO fake decisions.</div>
  {decisions_html}
</section>

<section>
  <h2>🎤 Captures by Type</h2>
  <div class="desc">Что user поймал через /capture за период.</div>
  <div class="charts-row">
    <div>{captures_chart_html if captures["total"] > 0 else "<p class='empty'>—</p>"}</div>
    <div>{captures_html}</div>
  </div>
</section>

<section>
  <h2>📅 Weekly Reviews</h2>
  <div class="desc">Из memory/weekly_review.md.</div>
  {weekly_html}
</section>

<section>
  <h2>📂 Active Projects</h2>
  <div class="desc">Из memory/projects.md, отсортировано по priority.</div>
  {projects_html}
</section>

<section>
  <h2>⚠ Top Risks</h2>
  <div class="desc">Из memory/risks.md, sorted by severity × probability. NO fake threat levels.</div>
  {risks_html}
</section>

<section>
  <h2>💗 Energy & Stress Trend</h2>
  <div class="desc">Из ежедневных /evening reviews за период. Min 2 точки для chart.</div>
  {trend_html}
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=list(PERIOD_DAYS.keys()), default="week")
    parser.add_argument("--output", default=None,
                        help="Output directory. Defaults to /opt/data/reports/ or repo/reports/")
    parser.add_argument("--pdf", action="store_true",
                        help="Also render PDF via headless Chromium (best with JS charts).")
    parser.add_argument("--no-pdf", action="store_true",
                        help="Force-disable PDF generation even if chromium is available.")
    parser.add_argument("--no-upload", action="store_true",
                        help="Skip catbox.moe upload (no public URL in result).")
    args = parser.parse_args()

    days = PERIOD_DAYS[args.period]
    cutoff = _today() - _dt.timedelta(days=days)
    period_label = {"week": "Неделя", "month": "Месяц", "quarter": "Квартал", "all": "Всё время"}[args.period]

    decisions = collect_decisions(cutoff)
    captures = collect_captures_by_type(cutoff)
    weekly = collect_weekly_reviews(cutoff)
    projects = collect_active_projects()
    risks = collect_top_risks(top_n=8)
    trend = collect_evening_trend(cutoff)

    filled, empty = [], []
    if decisions: filled.append("decisions")
    else: empty.append("decisions")
    if captures["total"] > 0: filled.append("captures")
    else: empty.append("captures")
    if weekly: filled.append("weekly")
    else: empty.append("weekly")
    if projects: filled.append("projects")
    else: empty.append("projects")
    if risks: filled.append("risks")
    else: empty.append("risks")
    if trend["count"] >= 2: filled.append("trend")
    else: empty.append("trend")

    html_content = render_html({
        "period_label": period_label,
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cutoff": cutoff.isoformat(),
        "decisions": decisions,
        "captures": captures,
        "weekly_reviews": weekly,
        "active_projects": projects,
        "top_risks": risks,
        "evening_trend": trend,
        "filled_sections": filled,
        "empty_sections": empty,
    })

    # Resolve output path
    if args.output:
        out_dir = pathlib.Path(args.output)
    elif pathlib.Path("/opt/data").exists():
        out_dir = pathlib.Path("/opt/data/reports")
    else:
        out_dir = _REPO / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"tandem-report-{args.period}-{today_iso()}"
    file_path = out_dir / f"{stem}.html"
    file_path.write_text(html_content, encoding="utf-8")

    # ---- Optional PDF rendering ----
    pdf_path = None
    pdf_status: dict = {"requested": False}
    want_pdf = args.pdf and not args.no_pdf
    if want_pdf:
        pdf_path_candidate = out_dir / f"{stem}.pdf"
        pdf_status = {"requested": True, **html_to_pdf(file_path, pdf_path_candidate)}
        if pdf_status.get("ok"):
            pdf_path = pdf_path_candidate

    # ---- Public URL upload (catbox.moe — free, persistent) ----
    public_url = None
    upload_status: dict = {"requested": False}
    if not args.no_upload:
        upload_status = {"requested": True, **upload_to_catbox(file_path)}
        if upload_status.get("ok"):
            public_url = upload_status["url"]
            # Re-write HTML with public URL embedded in footer (so anyone who opens
            # the catbox URL also sees the share link at the bottom).
            html_with_url = html_content.replace(
                "Открой в Chrome → File → Print → Save as PDF для PDF-версии.",
                f'Открой в Chrome → File → Print → Save as PDF для PDF-версии.</p>'
                f'<p>🔗 <a href="{public_url}" style="color:#5eead4">Публичная ссылка на этот отчёт</a></p>'
                f'<p style="color:#52525b;font-size:11px">Ссылка работает на любом устройстве. URL содержит '
                f'random hash — не угадаешь без знания.',
            )
            file_path.write_text(html_with_url, encoding="utf-8")

    result = {
        "html_path": str(file_path),
        "html_size_kb": round(file_path.stat().st_size / 1024, 1),
        "public_url": public_url,
        "upload_status": upload_status,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "pdf_status": pdf_status,
        "period": args.period,
        "period_label": period_label,
        "cutoff": cutoff.isoformat(),
        "filled": filled,
        "empty": empty,
        "stats": {
            "decisions": len(decisions),
            "captures_total": captures["total"],
            "captures_types": captures["counts"],
            "weekly_reviews": len(weekly),
            "active_projects": len(projects),
            "risks": len(risks),
            "evening_datapoints": trend["count"],
        },
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
