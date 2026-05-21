"""DuckDuckGo HTML search — no API key, no paid service.

Scrapes https://html.duckduckgo.com/html/ which is the no-JS endpoint.
Returns top N results as structured JSON.

Usage:
    python search.py "<query>" [--num 10]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse

import httpx


# Browser-class UA — DDG html/ endpoint returns HTTP 202 for non-browser UAs.
# Use the lite/ endpoint with a normal Safari UA for clean text results.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
_DDG_LITE = "https://lite.duckduckgo.com/lite/"
_TIMEOUT = 12.0


def _strip_html(s: str) -> str:
    """Remove HTML tags, collapse whitespace, unescape entities."""
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _decode_ddg_redirect(href: str) -> str:
    """DDG wraps results in //duckduckgo.com/l/?uddg=<encoded>. Unwrap."""
    if "/l/?uddg=" in href:
        try:
            parsed = urllib.parse.urlparse(href if href.startswith("http") else f"https:{href}")
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                return urllib.parse.unquote(qs["uddg"][0])
        except Exception:
            pass
    return href


def search(query: str, num: int = 10) -> dict:
    """Run a DDG lite search. Returns dict with ok/results/error."""
    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}) as client:
            resp = client.get(_DDG_LITE, params={"q": query}, follow_redirects=True)
    except httpx.HTTPError as e:
        return {"ok": False, "reason": f"network error: {type(e).__name__}: {e}", "query": query}

    if resp.status_code != 200:
        return {"ok": False, "reason": f"HTTP {resp.status_code}", "query": query}

    body = resp.text
    if "Unfortunately, bots use DuckDuckGo too" in body or "anomaly" in body.lower():
        return {"ok": False, "reason": "DuckDuckGo блокирует — rate limit / captcha. Подожди 60s.", "query": query}

    # DDG lite format: <a rel="nofollow" href="<url>" ...>Title</a>
    # Each result follows a numbered table cell; snippet is in the next <td class="result-snippet">
    # We parse rel="nofollow" anchors and their following <td class="result-snippet"> if available.
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
        url = _decode_ddg_redirect(m.group(1))
        title = _strip_html(m.group(2))
        if not url.startswith("http") or len(title) < 3:
            continue
        snippet = snippets[i][:250] if i < len(snippets) else ""
        results.append({
            "rank": len(results) + 1,
            "title": title[:160],
            "url": url,
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
    parser.add_argument("--num", type=int, default=10, help="Max results (default 10)")
    args = parser.parse_args()

    if not args.query.strip():
        json.dump({"ok": False, "reason": "Пустой запрос"}, sys.stdout, ensure_ascii=False)
        return 1

    time.sleep(0.3)  # politeness
    result = search(args.query.strip(), num=min(max(args.num, 1), 25))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
