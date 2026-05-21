"""Fetch + parse a static web page. No paid service, no extra deps.

Uses ONLY Python stdlib (urllib + html.parser). Respects robots.txt.

Usage:
    python fetch.py "<url>"
    python fetch.py "<url>" --raw  # skip robots.txt check
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
_TIMEOUT = 15.0
_MAX_CONTENT = 8000


class _TextExtractor(HTMLParser):
    _SKIP_TAGS = {
        "script", "style", "nav", "footer", "header", "aside",
        "form", "noscript", "svg", "iframe", "button",
    }
    _BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_stack: list[str] = []
        self.title: str = ""
        self._in_title = False
        self.meta_description: str = ""

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self.skip_stack.append(tag)
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            attrs_d = dict(attrs)
            name = (attrs_d.get("name") or attrs_d.get("property") or "").lower()
            if name in {"description", "og:description"}:
                content = attrs_d.get("content", "")
                if content and not self.meta_description:
                    self.meta_description = content.strip()
            return
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_stack:
            return
        if self._in_title:
            self.title += data
            return
        text = data.strip()
        if text:
            self.parts.append(text + " ")

    def get_text(self) -> str:
        return "".join(self.parts)


def _http_get(url: str, timeout: float = _TIMEOUT) -> tuple[int, str, dict, str]:
    """GET via stdlib urllib. Returns (status, body, headers, final_url)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA}, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read()
            body = raw.decode(charset, errors="replace")
            return resp.status, body, dict(resp.headers), resp.geturl()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body, dict(getattr(e, "headers", {}) or {}), url


def _robots_allowed(url: str, ua: str) -> tuple[bool, str]:
    try:
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        status, body, _, _ = _http_get(robots_url, timeout=8.0)
        if status >= 400:
            return True, "no robots.txt (allowed by default)"
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        allowed = rp.can_fetch(ua, url)
        return allowed, "robots.txt allowed" if allowed else "robots.txt disallowed"
    except Exception as e:
        return True, f"robots check failed ({type(e).__name__}) — proceeding"


def fetch(url: str, respect_robots: bool = True) -> dict:
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "URL должен начинаться с http:// или https://", "url": url}

    if respect_robots:
        ok_robots, reason = _robots_allowed(url, _UA)
        if not ok_robots:
            return {"ok": False, "reason": f"robots.txt запрещает: {reason}", "url": url}

    try:
        status, body, headers, final_url = _http_get(url)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "reason": f"network error: {type(e).__name__}: {e}", "url": url}

    if status != 200:
        return {"ok": False, "reason": f"HTTP {status}", "url": url, "final_url": final_url}

    ctype = headers.get("Content-Type", headers.get("content-type", "")).lower()
    if "text/html" not in ctype and "application/xhtml" not in ctype:
        truncated = len(body) > _MAX_CONTENT
        return {
            "ok": True,
            "url": url,
            "final_url": final_url,
            "content_type": ctype,
            "title": "",
            "meta_description": "",
            "content": body[:_MAX_CONTENT],
            "truncated": truncated,
            "byte_length": len(body.encode("utf-8")),
        }

    parser = _TextExtractor()
    try:
        parser.feed(body)
    except Exception as e:
        return {"ok": False, "reason": f"HTML parse error: {type(e).__name__}: {e}", "url": url}

    text = parser.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()

    truncated = len(text) > _MAX_CONTENT
    if truncated:
        text = text[:_MAX_CONTENT].rsplit(" ", 1)[0] + " [truncated]"

    return {
        "ok": True,
        "url": url,
        "final_url": final_url,
        "content_type": ctype,
        "title": parser.title.strip()[:200],
        "meta_description": parser.meta_description[:500],
        "content": text,
        "truncated": truncated,
        "byte_length": len(body.encode("utf-8")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--raw", action="store_true", help="Skip robots.txt check")
    args = parser.parse_args()

    result = fetch(args.url.strip(), respect_robots=not args.raw)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
