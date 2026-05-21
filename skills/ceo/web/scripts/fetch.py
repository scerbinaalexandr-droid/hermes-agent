"""Fetch + parse a static web page. No paid service.

httpx + stdlib html.parser. Extracts: title, main text (cleaned),
optional og:description. Respects robots.txt for the configured UA.

Usage:
    python fetch.py "<url>"
    python fetch.py "<url>" --raw  # skip robots.txt check (use with caution)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.robotparser
from html.parser import HTMLParser

import httpx


_UA = "Hermes-CEO-Research-Bot/0.1 (alexandr.scerbina@gmail.com)"
_TIMEOUT = 15.0
_MAX_CONTENT = 8000


class _TextExtractor(HTMLParser):
    """Walk HTML, skip script/style/nav/footer/header tags, accumulate visible text."""

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


def _robots_allowed(url: str, ua: str) -> tuple[bool, str]:
    """Check robots.txt. Returns (allowed, reason)."""
    try:
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        with httpx.Client(timeout=8.0, headers={"User-Agent": ua}) as client:
            r = client.get(robots_url)
            if r.status_code >= 400:
                # No robots.txt = allowed by default per RFC
                return True, "no robots.txt"
            rp.parse(r.text.splitlines())
        allowed = rp.can_fetch(ua, url)
        return allowed, "robots.txt allowed" if allowed else "robots.txt disallowed"
    except Exception as e:
        # Conservative: allow if check itself failed
        return True, f"robots check failed ({type(e).__name__}) — proceeding"


def fetch(url: str, respect_robots: bool = True) -> dict:
    """Fetch and parse a URL. Returns dict with ok/title/content/etc."""
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "URL должен начинаться с http:// или https://", "url": url}

    if respect_robots:
        ok_robots, reason = _robots_allowed(url, _UA)
        if not ok_robots:
            return {"ok": False, "reason": f"robots.txt запрещает: {reason}", "url": url}

    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True) as client:
            resp = client.get(url)
    except httpx.HTTPError as e:
        return {"ok": False, "reason": f"network error: {type(e).__name__}: {e}", "url": url}

    if resp.status_code != 200:
        return {"ok": False, "reason": f"HTTP {resp.status_code}", "url": url, "final_url": str(resp.url)}

    ctype = resp.headers.get("content-type", "").lower()
    if "text/html" not in ctype and "application/xhtml" not in ctype:
        # Plain text or RSS — return as-is
        body = resp.text[:_MAX_CONTENT]
        truncated = len(resp.text) > _MAX_CONTENT
        return {
            "ok": True,
            "url": url,
            "final_url": str(resp.url),
            "content_type": ctype,
            "title": "",
            "meta_description": "",
            "content": body,
            "truncated": truncated,
            "byte_length": len(resp.content),
        }

    parser = _TextExtractor()
    try:
        parser.feed(resp.text)
    except Exception as e:
        return {"ok": False, "reason": f"HTML parse error: {type(e).__name__}: {e}", "url": url}

    text = parser.get_text()
    # Cleanup excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    truncated = len(text) > _MAX_CONTENT
    if truncated:
        text = text[:_MAX_CONTENT].rsplit(" ", 1)[0] + " [truncated]"

    return {
        "ok": True,
        "url": url,
        "final_url": str(resp.url),
        "content_type": ctype,
        "title": parser.title.strip()[:200],
        "meta_description": parser.meta_description[:500],
        "content": text,
        "truncated": truncated,
        "byte_length": len(resp.content),
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
