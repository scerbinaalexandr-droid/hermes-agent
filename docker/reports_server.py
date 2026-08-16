"""Public edge for the CEO OS: HTML reports + the web UI behind them.

Two jobs:
1. GET /reports/<uuid>.html — unguessable report links (see below).
2. Everything else — reverse-proxied to the local web UI (:8787), so the
   iPhone app reaches it over Railway's HTTPS edge instead of a userspace
   Tailscale tunnel that kept dropping connections on a mobile network.
   Auth stays the web UI's own password; this layer adds a login rate limit.

Reports endpoint: GET /reports/<uuid>.html
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
import http.client
import http.server
import os
import pathlib
import re
import sys
import threading
import time
import urllib.parse


_REPORTS_DIR = pathlib.Path(os.environ.get("HERMES_REPORTS_DIR", "/opt/data/reports"))
_LOG_PATH = pathlib.Path(os.environ.get("HERMES_REPORTS_LOG", "/opt/data/logs/reports_access.log"))

# Everything that is not /health or /reports/<uuid>.html is forwarded to the
# web UI, so the iPhone app reaches it over Railway's HTTPS edge instead of the
# userspace Tailscale tunnel — that tunnel dropped connections 19 times in one
# hour on a phone switching between 5G and Wi-Fi.
_WEBUI_HOST = os.environ.get("HERMES_WEBUI_UPSTREAM_HOST", "127.0.0.1")
_WEBUI_PORT = int(os.environ.get("HERMES_WEBUI_PORT", "8787"))
# Long: chat answers stream for minutes over SSE.
_PROXY_TIMEOUT = float(os.environ.get("HERMES_PROXY_TIMEOUT", "600"))

# Brute-force guard on the login route — the web UI is now reachable from the
# public internet, where a single password is the only thing in front of the
# owner's mail, calendar and memory.
_LOGIN_PATHS = frozenset({"/api/auth/login", "/login"})
_LOGIN_MAX_ATTEMPTS = int(os.environ.get("HERMES_LOGIN_MAX_ATTEMPTS", "10"))
_LOGIN_WINDOW_SECONDS = float(os.environ.get("HERMES_LOGIN_WINDOW_SECONDS", "300"))
_login_hits: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _login_rate_limited(client_ip: str) -> bool:
    """True when this IP exceeded the login attempt budget for the window."""
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_hits.get(client_ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
        hits.append(now)
        _login_hits[client_ip] = hits
        if len(_login_hits) > 1000:  # bound memory against spoofed sources
            for ip in [k for k, v in _login_hits.items() if not v or now - v[-1] > _LOGIN_WINDOW_SECONDS]:
                _login_hits.pop(ip, None)
        return len(hits) > _LOGIN_MAX_ATTEMPTS

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

    # HTTP/1.1 so streamed answers (SSE) reach the app chunk by chunk instead of
    # arriving only when the connection closes.
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        self._proxy_to_webui()

    def do_PUT(self):  # noqa: N802
        self._proxy_to_webui()

    def do_PATCH(self):  # noqa: N802
        self._proxy_to_webui()

    def do_DELETE(self):  # noqa: N802
        self._proxy_to_webui()

    def do_OPTIONS(self):  # noqa: N802
        self._proxy_to_webui()

    def _proxy_to_webui(self) -> None:
        """Forward the request to the local web UI, streaming the response back."""
        path = urllib.parse.urlparse(self.path).path
        if path in _LOGIN_PATHS and _login_rate_limited(self.client_address[0]):
            _append_log(f"RATELIMIT {self.client_address[0]} {path}")
            body = b'{"error":"Too many attempts, try later"}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", str(int(_LOGIN_WINDOW_SECONDS)))
            self.end_headers()
            self.wfile.write(body)
            return

        payload = None
        length = self.headers.get("Content-Length")
        if length:
            try:
                payload = self.rfile.read(int(length))
            except (ValueError, OSError):
                self._send_500("bad request body")
                return

        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length", "transfer-encoding")
        }
        if payload is not None:
            headers["Content-Length"] = str(len(payload))

        conn = None
        try:
            conn = http.client.HTTPConnection(_WEBUI_HOST, _WEBUI_PORT, timeout=_PROXY_TIMEOUT)
            conn.request(self.command, self.path, body=payload, headers=headers)
            upstream = conn.getresponse()

            self.send_response(upstream.status)
            for key, value in upstream.getheaders():
                # Hop-by-hop headers and framing are ours to decide.
                if key.lower() in ("transfer-encoding", "connection", "content-length", "keep-alive"):
                    continue
                self.send_header(key, value)
            # Close-delimited: works for both fixed-size bodies and open-ended
            # SSE streams without having to re-chunk them.
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()

            while True:
                chunk = upstream.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True  # client hung up mid-stream — normal
        except Exception as e:  # upstream down or unreachable
            _append_log(f"PROXY-ERROR {self.command} {self.path} {type(e).__name__}")
            try:
                self._send_502(f"web UI unreachable: {type(e).__name__}")
            except Exception:
                pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health":
            body = b"Hermes Reports OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        match = _PATH_RE.match(path)
        if not match:
            # Not a report URL → it belongs to the web UI (app + browser).
            self._proxy_to_webui()
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
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        match = _PATH_RE.match(path)
        if not match or not _UUID_FILE_RE.match(match.group(1)):
            self._proxy_to_webui()
            return
        file_path = _safe_resolve(match.group(1))
        if not file_path or not file_path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()

    def _send_simple(self, status: int, text: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text)

    def _send_404(self, reason: str) -> None:
        self._send_simple(404, b"Not Found\n")

    def _send_500(self, reason: str) -> None:
        self._send_simple(500, b"Internal Error\n")

    def _send_502(self, reason: str) -> None:
        self._send_simple(502, b"Service starting, retry shortly\n")

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
