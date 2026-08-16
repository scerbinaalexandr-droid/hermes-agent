"""Public edge for the CEO OS: HTML reports + the web UI behind them.

Two jobs:
1. GET /reports/<uuid>.html — unguessable report links (see below).
   Plus GET /edge-health — liveness of this edge itself. NOT /health: that one
   belongs to the web UI, whose JSON the Hermex app probes when adding a server.
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

# Everything that is not /edge-health or /reports/<uuid>.html is forwarded to the
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
    """True when this IP already spent its FAILED-login budget for the window.

    Only failures are recorded (see _record_login_failure): counting successes
    too let anyone lock the owner out of his own assistant with a dozen requests.
    """
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_hits.get(client_ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
        _login_hits[client_ip] = hits
        return len(hits) >= _LOGIN_MAX_ATTEMPTS


def _record_login_failure(client_ip: str) -> None:
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_hits.get(client_ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
        hits.append(now)
        _login_hits[client_ip] = hits
        if len(_login_hits) > 1000:  # bound memory against spoofed sources
            for ip in [k for k, v in _login_hits.items()
                       if not v or now - v[-1] > _LOGIN_WINDOW_SECONDS]:
                _login_hits.pop(ip, None)

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

    def _client_ip(self) -> str:
        """Real caller address.

        self.client_address is Railway's edge, identical for every visitor —
        keying the login limiter on it would both fail to stop an attacker and
        let one lock the owner out. The edge puts the caller first in
        X-Forwarded-For.
        """
        xff = self.headers.get("X-Forwarded-For", "")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def _proxy_to_webui(self) -> None:
        """Forward the request to the local web UI, streaming the response back."""
        path = urllib.parse.urlparse(self.path).path
        client_ip = self._client_ip()
        if path in _LOGIN_PATHS and _login_rate_limited(client_ip):
            _append_log(f"RATELIMIT {client_ip} {path}")
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

        # Host is forwarded UNCHANGED on purpose: the web UI's CSRF gate compares
        # the browser's Origin against Host, so rewriting it to 127.0.0.1 makes
        # every request look cross-origin ("Cross-origin mismatch - check reverse
        # proxy headers").
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("connection", "content-length", "transfer-encoding")
        }
        if payload is not None:
            headers["Content-Length"] = str(len(payload))
        # Provenance headers are OVERWRITTEN, never merged: the web UI trusts
        # X-Forwarded-Proto (HERMES_WEBUI_TRUST_FORWARDED_PROTO=1), so letting a
        # client-supplied value survive would hand it a downgrade lever. The only
        # way in from outside is the HTTPS domain.
        headers["X-Forwarded-Proto"] = "https"
        headers["X-Forwarded-Host"] = self.headers.get("Host", "")
        headers["X-Forwarded-For"] = f"{client_ip}, {self.client_address[0]}"

        conn = None
        try:
            conn = http.client.HTTPConnection(_WEBUI_HOST, _WEBUI_PORT, timeout=_PROXY_TIMEOUT)
            conn.request(self.command, self.path, body=payload, headers=headers)
            upstream = conn.getresponse()

            # Framing decides whether the client can tell where the body ends.
            # A fixed-size body MUST keep its Content-Length: iOS URLSession
            # waits for the declared length and, without it, spins forever on a
            # response curl would have accepted — that is what left Kanban,
            # Tasks and session bodies stuck on "loading" in the app.
            body_len = upstream.getheader("Content-Length")
            try:
                body_len = int(body_len) if body_len is not None else None
            except ValueError:
                body_len = None

            self.send_response(upstream.status)
            for key, value in upstream.getheaders():
                # Hop-by-hop headers and framing are ours to decide. Server/Date
                # are emitted by send_response already — forwarding the upstream
                # copies too produced duplicate headers in every response.
                if key.lower() in ("transfer-encoding", "connection", "content-length",
                                   "keep-alive", "server", "date"):
                    continue
                self.send_header(key, value)
            if body_len is not None:
                self.send_header("Content-Length", str(body_len))
            else:
                # Streamed / unknown length (SSE, chunked) — close marks the end.
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()

            remaining = body_len
            while True:
                chunk = upstream.read(8192 if remaining is None else min(8192, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break

            if path in _LOGIN_PATHS and upstream.status >= 400:
                _record_login_failure(client_ip)
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

        # /health belongs to the web UI: the Hermex app probes it when adding a
        # server and expects Hermes' JSON. Answering it here with plain text made
        # the app fail with "Не удалось прочитать ответ сервера". Our own edge
        # liveness check lives on /edge-health instead.
        if path == "/edge-health":
            body = b"Hermes edge OK\n"
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
        if path == "/edge-health":
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
