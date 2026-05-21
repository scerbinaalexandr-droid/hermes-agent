"""Render a JS-heavy page via headless Chromium. No paid service.

Re-uses the same Chromium binary as /report PDF generation. Calls Chromium
CLI with --dump-dom flag to get post-JS DOM, then strips HTML to text.

Usage:
    python render.py "<url>"
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import shutil
import subprocess
import sys

# Re-use text extractor from fetch.py
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch import _TextExtractor, _MAX_CONTENT  # noqa: E402


_TIMEOUT = 30


def find_chromium_binary() -> str | None:
    """Locate Chromium — same logic as /report skill."""
    playwright_root = "/opt/hermes/.playwright"
    patterns = [
        f"{playwright_root}/chromium_headless_shell-*/chrome-linux/headless_shell",
        f"{playwright_root}/chromium-*/chrome-linux/chrome",
        f"{playwright_root}/chromium-*/chrome-linux/headless_shell",
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat))
        if matches:
            return matches[-1]
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    return None


def render(url: str) -> dict:
    """Render via Chromium --dump-dom, return post-JS text."""
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "URL должен начинаться с http:// или https://", "url": url}

    chromium = find_chromium_binary()
    if not chromium:
        return {
            "ok": False,
            "reason": "Chromium не найден в /opt/hermes/.playwright/ — render unavailable. "
                      "Используй /web fetch для статических страниц.",
            "url": url,
        }

    cmd = [
        chromium,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--virtual-time-budget=8000",
        "--user-agent=Hermes-CEO-Research-Bot/0.1",
        "--dump-dom",
        url,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"render timeout {_TIMEOUT}s", "url": url}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "url": url}

    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": f"chromium exit {proc.returncode}: {proc.stderr.strip()[:300]}",
            "url": url,
        }

    dom = proc.stdout
    if not dom or len(dom) < 100:
        return {"ok": False, "reason": "Chromium вернул пустой DOM", "url": url}

    parser = _TextExtractor()
    try:
        parser.feed(dom)
    except Exception as e:
        return {"ok": False, "reason": f"DOM parse error: {type(e).__name__}: {e}", "url": url}

    text = parser.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    truncated = len(text) > _MAX_CONTENT
    if truncated:
        text = text[:_MAX_CONTENT].rsplit(" ", 1)[0] + " [truncated]"

    return {
        "ok": True,
        "url": url,
        "title": parser.title.strip()[:200],
        "meta_description": parser.meta_description[:500],
        "content": text,
        "truncated": truncated,
        "dom_bytes": len(dom),
        "binary": chromium,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL to render")
    args = parser.parse_args()

    result = render(args.url.strip())
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
