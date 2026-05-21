"""DuckDuckGo lite search — no API key, no paid service, no extra deps.

Uses ONLY Python stdlib (urllib). Works on any container with python3.

Usage:
    python search.py "<query>" [--num 10]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


# Browser-class UA — DDG /html/ endpoint returns HTTP 202 for non-browser UAs.
# Use the /lite/ endpoint with a Safari UA for clean text results.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
_DDG_LITE = "https://lite.duckduckgo.com/lite/"
_TIMEOUT = 12.0


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _decode_ddg_redirect(href: str) -> str:
    if "/l/?uddg=" in href:
        try:
            parsed = urllib.parse.urlparse(href if href.startswith("http") else f"https:{href}")
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                return urllib.parse.unquote(qs["uddg"][0])
        except Exception:
            pass
    return href


def _http_get(url: str, headers: dict, timeout: float) -> tuple[int, str]:
    """GET via stdlib urllib. Returns (status_code, body_text)."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body


def search(query: str, num: int = 10) -> dict:
    url = f"{_DDG_LITE}?{urllib.parse.urlencode({'q': query})}"
    try:
        status, body = _http_get(url, {"User-Agent": _UA}, _TIMEOUT)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "reason": f"network error: {type(e).__name__}: {e}", "query": query}

    if status != 200:
        return {"ok": False, "reason": f"HTTP {status}", "query": query}

    if "Unfortunately, bots use DuckDuckGo too" in body or "anomaly" in body.lower():
        return {"ok": False, "reason": "DuckDuckGo блокирует — rate limit / captcha. Подожди 60s.", "query": query}

    link_pattern = re.compile(
        r'<a\s+rel="nofollow"\s+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL,
    )
    snippets = [_strip_html(m.group(1)) for m in snippet_pattern.finditer(body)]
    results = []
    for i, m in enumerate(link_pattern.finditer(body)):
        result_url = _decode_ddg_redirect(m.group(1))
        title = _strip_html(m.group(2))
        if not result_url.startswith("http") or len(title) < 3:
            continue
        snippet = snippets[i][:250] if i < len(snippets) else ""
        results.append({
            "rank": len(results) + 1,
            "title": title[:160],
            "url": result_url,
            "snippet": snippet,
        })
        if len(results) >= num:
            break

    return {
        "ok": bool(results),
        "query": query,
        "engine": "duckduckgo-lite",
        "count": len(results),
        "results": results,
        "reason": "" if results else "Не удалось распарсить выдачу (возможно изменился HTML формат DDG)",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Search query")
    parser.add_argument("--num", type=int, default=10)
    args = parser.parse_args()

    if not args.query.strip():
        json.dump({"ok": False, "reason": "Пустой запрос"}, sys.stdout, ensure_ascii=False)
        return 1

    time.sleep(0.3)
    result = search(args.query.strip(), num=min(max(args.num, 1), 25))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
