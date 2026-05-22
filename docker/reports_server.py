"""Minimal stdlib HTTP server for serving CEO HTML reports.

Single endpoint: GET /reports/<uuid>.html
- Filename MUST match a uuid4 pattern (e.g. `a4b1...html`) — random hash
  in URL makes the report unguessable without prior knowledge.
- Read-only, no listing endpoint, no write endpoint, no auth (security
  is the uuid in URL).
- Reads files only from /opt/data/reports/, never escapes that dir.
- Logs every access to /opt/data/logs/reports_access.log.

Designed to run in background from ceo-os-entrypoint.sh. No external
deps. Listens on $PORT (Railway default) or $REPORTS_PORT.
"""

from __future__ import annotations

import datetime as _dt
import http.server
import os
import pathlib
import re
import sys
import urllib.parse


_REPORTS_DIR = pathlib.Path(os.environ.get("HERMES_REPORTS_DIR", "/opt/data/reports"))
_LOG_PATH = pathlib.Path(os.environ.get("HERMES_REPORTS_LOG", "/opt/data/logs/reports_access.log"))

# Strict pattern: <uuid4>.html where uuid4 is 8-4-4-4-12 hex
_UUID_FILE_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.html$")
_PATH_RE = re.compile(r"^/reports/([a-f0-9-]+\.html)$")


def _safe_resolve(filename: str) -> pathlib.Path | None:
    """Resolve filename inside _REPORTS_DIR. Returns None on escape attempt."""
    candidate = _REPORTS_DIR / filename
    try:
        resolved = candidate.resolve(strict=True)
        # Must be inside reports dir
        resolved.relative_to(_REPORTS_DIR.resolve())
        return resolved
    except (FileNotFoundError, ValueError, OSError):
        return None


def _append_log(line: str) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now().isoformat()} {line}\n")
    except Exception:
        pass


class ReportsHandler(http.server.BaseHTTPRequestHandler):

    server_version = "HermesReports/0.1"

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Hermes Reports OK\n")
            return

        match = _PATH_RE.match(path)
        if not match:
            self._send_404("not a reports path")
            return

        filename = match.group(1)
        if not _UUID_FILE_RE.match(filename):
            self._send_404("filename must be uuid4.html")
            return

        file_path = _safe_resolve(filename)
        if not file_path or not file_path.is_file():
            self._send_404("file not found")
            return

        try:
            body = file_path.read_bytes()
        except OSError as e:
            self._send_500(f"read error: {type(e).__name__}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy",
                         "default-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                         "img-src 'self' data:; "
                         "script-src 'unsafe-inline' https://cdn.jsdelivr.net;")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):  # noqa: N802
        # Same checks as GET but no body
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
            return
        match = _PATH_RE.match(path)
        if not match or not _UUID_FILE_RE.match(match.group(1)):
            self.send_error(404)
            return
        file_path = _safe_resolve(match.group(1))
        if not file_path or not file_path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()

    def _send_404(self, reason: str) -> None:
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not Found\n")

    def _send_500(self, reason: str) -> None:
        self.send_response(500)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Internal Error\n")

    def log_message(self, format: str, *args):  # noqa: A002
        # Override default stderr log; write to our file instead
        _append_log(f"{self.address_string()} {format % args}")


def main() -> int:
    port_str = os.environ.get("REPORTS_PORT") or os.environ.get("PORT") or "8090"
    try:
        port = int(port_str)
    except ValueError:
        sys.stderr.write(f"[reports-server] Invalid PORT={port_str}, using 8090\n")
        port = 8090

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    msg = f"[reports-server] Listening on 0.0.0.0:{port}, serving {_REPORTS_DIR}"
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
    _append_log(f"START {msg}")

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), ReportsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _append_log("STOP server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
