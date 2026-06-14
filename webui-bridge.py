#!/usr/bin/env python3
"""
WebUI Bridge for Боба Private Tracker Support

This module solves the WebUI download issue by creating a bridge between
WebUI and nova2dl.py. It intercepts download requests and handles them
with proper authentication.

Author: Milos Vasic
Version: 2.0.0
License: Apache 2.0
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Share the theme-bridge helpers with the sibling download-proxy so
# the qBittorrent WebUI picks up our Darcula (or whatever is active)
# palette regardless of which proxy served the page.
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PLUGINS_DIR = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_DIR not in sys.path:
    sys.path.insert(0, _PLUGINS_DIR)
try:
    import theme_injector  # type: ignore[import-untyped]
except Exception as _exc:  # pragma: no cover — defensive
    theme_injector = None  # type: ignore[assignment]
    print(f"[WebUI-Bridge] theme_injector unavailable: {_exc}")

# Configuration
QBITTORRENT_HOST = os.environ.get("QBITTORRENT_HOST", "localhost")
QBITTORRENT_PORT = int(os.environ.get("QBITTORRENT_PORT", "7185"))
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "7188"))

# Private tracker URL patterns
PRIVATE_TRACKERS = {
    "rutracker": ["rutracker.org", "rutracker.net", "rutracker.nl"],
    "kinozal": ["kinozal.tv"],
    "nnmclub": ["nnmclub.to", "nnmclub.ro", "nnm-club.me"],
    "iptorrents": ["iptorrents.com", "iptorrents.me"],
}


class WebUIBridgeHandler(BaseHTTPRequestHandler):
    """Handle WebUI requests with private tracker support."""

    def log_message(self, format, *args):
        """Custom logging."""
        print(f"[WebUI-Bridge] {self.address_string()} - {format % args}")

    def do_POST(self):
        """Handle POST requests."""
        self.handle_request()

    def do_GET(self):
        """Handle GET requests."""
        self.handle_request()

    def handle_request(self):
        """Main request handler."""
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            # Liveness probe — the services-fixture preflight hits
            # /health at the bridge endpoint to make sure the bridge is
            # reachable before any test that depends on it runs. Return
            # a deeper signal: also probe the qBittorrent backend on
            # :7185 so `healthy` doesn't just mean "the python server is
            # up" but "the passthrough works." The probe timeout is
            # short so a slow qBittorrent doesn't hang the liveness
            # check — we degrade to `status:degraded` instead.
            if path == "/health":
                import http.client as _http
                import json as _json

                backend_status = "unknown"
                try:
                    conn = _http.HTTPConnection("localhost", 7185, timeout=2)
                    conn.request("GET", "/")
                    resp = conn.getresponse()
                    backend_status = "ok" if resp.status < 500 else f"http_{resp.status}"
                    conn.close()
                except Exception as exc:
                    backend_status = f"unreachable:{type(exc).__name__}"
                overall = "healthy" if backend_status == "ok" else "degraded"
                payload = _json.dumps(
                    {
                        "status": overall,
                        "service": "webui-bridge",
                        "backend": backend_status,
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            # Serve the theme-bridge assets locally (skin.css + bootstrap.js)
            # so the user-visible theme is identical to what the
            # download-proxy at :7186 serves. Must come BEFORE the
            # qBittorrent passthrough — these paths do not exist on the
            # qBittorrent WebUI side.
            # Serve the Boba logo locally so it replaces qBittorrent's
            # default SVG/PNG logos on both :7186 and :7188.
            if theme_injector is not None and theme_injector.is_boba_logo_request(path):
                status, headers, payload = theme_injector.serve_boba_logo()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)
                return

            if path.startswith("/__qbit_theme__/") and theme_injector is not None:
                status, headers, payload = theme_injector.serve_theme_asset(path)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)
                return

            # Check if this is a torrent download
            if "urls" in query:
                urls = query.get("urls", [""])[0]
                if urls:
                    self.handle_torrent_download(urls)
                    return

            # Proxy to qBittorrent
            self.proxy_to_qbittorrent()

        except Exception as e:
            self.send_error(500, str(e))

    def handle_torrent_download(self, url):
        """Handle torrent download with private tracker support."""
        url = urllib.parse.unquote(url)

        # Identify if this is a private tracker
        plugin = self.identify_plugin(url)

        if plugin:
            print(f"[WebUI-Bridge] Private tracker detected: {plugin}")
            print(f"[WebUI-Bridge] URL: {url[:80]}...")

            # Use nova2dl.py for private trackers
            torrent_file = self.download_via_nova2dl(plugin, url)

            if torrent_file:
                # Upload to qBittorrent
                success = self.upload_to_qbittorrent(torrent_file)

                if success:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK")

                    # Cleanup
                    try:
                        os.unlink(torrent_file)
                    except OSError as e:
                        print(f"[WebUI-Bridge] Cleanup error: {e}")
                    return

        # Not a private tracker or download failed, proxy to qBittorrent
        self.proxy_to_qbittorrent()

    def identify_plugin(self, url):
        """Identify which plugin to use."""
        url_lower = url.lower()
        for plugin, patterns in PRIVATE_TRACKERS.items():
            for pattern in patterns:
                if pattern in url_lower:
                    return plugin
        return None

    def download_via_nova2dl(self, plugin, url):
        """Download using nova2dl.py."""
        try:
            cmd = ["python3", "/config/qBittorrent/nova3/nova2dl.py", plugin, url]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                output = result.stdout.strip()
                if " " in output:
                    return output.split(" ")[0]

            print(f"[WebUI-Bridge] nova2dl failed: {result.stderr}")
            return None

        except Exception as e:
            print(f"[WebUI-Bridge] Error: {e}")
            return None

    def upload_to_qbittorrent(self, filepath):
        """Upload torrent file to qBittorrent."""
        try:
            url = f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}/api/v2/torrents/add"

            # Create multipart request
            boundary = "----WebKitFormBoundary" + str(int(time.time()))

            with open(filepath, "rb") as f:
                file_data = f.read()

            body = []
            body.append(f"------{boundary}".encode())
            body.append(b'Content-Disposition: form-data; name="torrents"; filename="torrent.torrent"')
            body.append(b"Content-Type: application/x-bittorrent")
            body.append(b"")
            body.append(file_data)
            body.append(f"------{boundary}--".encode())

            body = b"\r\n".join(body)

            req = urllib.request.Request(  # noqa: S310
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary=----{boundary}",
                    "Content-Length": len(body),
                },
            )

            with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
                return response.status == 200

        except Exception as e:
            print(f"[WebUI-Bridge] Upload error: {e}")
            return False

    def _is_root_liveness_probe(self):
        """True for a bare ``GET /`` with no torrent download in flight.

        The dashboard's bridge-health probe
        (``download-proxy/src/api/__init__.py:bridge_health``) GETs the
        bridge root and treats ``status < 500`` as "the bridge is alive".
        That probe must report on the *bridge process* liveness, which is
        independent of whether the qBittorrent backend on :7185 is
        reachable. When the passthrough to qBittorrent fails for such a
        bare-root probe we answer with a 200 liveness payload instead of
        leaking qBittorrent's connection error as a misleading 500 — a
        listening bridge with a down upstream is NOT "down".
        """
        try:
            parsed = urllib.parse.urlparse(self.path)
        except Exception:
            return False
        if parsed.path != "/":
            return False
        if urllib.parse.parse_qs(parsed.query):
            return False
        return self.command == "GET"

    def _send_root_liveness(self, backend_error):
        """Answer a bare-root liveness probe when qBittorrent is unreachable.

        Returns HTTP 200 with ``backend: unreachable`` so the dashboard
        renders the bridge as UP (it is — it answered) while still
        signalling that the qBittorrent passthrough is currently down.
        """
        payload = json.dumps(
            {
                "status": "alive",
                "service": "webui-bridge",
                "backend": "unreachable",
                "backend_error": str(backend_error),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def proxy_to_qbittorrent(self):
        """Proxy request to qBittorrent.

        Header hygiene:

        * ``Host`` and ``Content-Length`` are recomputed by urllib.
        * ``Referer`` and ``Origin`` are rewritten to
          ``http://localhost:$QBITTORRENT_PORT``. qBittorrent's WebUI
          enforces same-origin by default on state-changing endpoints
          (``/api/v2/auth/login`` returns 401 if the Referer does not
          match its host), and without this rewrite every login
          attempt through the bridge would fail.

        Upstream-down handling: if qBittorrent is unreachable
        (``URLError`` — connection refused / network unreachable / DNS),
        a bare-root liveness probe is answered 200 (the bridge is alive,
        only its upstream is down); any other path returns 502 Bad
        Gateway with correct gateway semantics instead of a generic 500.
        """
        try:
            target = f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}{self.path}"

            # Read body if POST
            body = None
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", 0))
                if length > 0:
                    body = self.rfile.read(length)

            req = urllib.request.Request(target, data=body, method=self.command)  # noqa: S310

            qbit_origin = f"http://localhost:{QBITTORRENT_PORT}"
            for header, value in self.headers.items():
                header_lower = header.lower()
                if header_lower in ("host", "content-length"):
                    continue
                if header_lower == "referer" or header_lower == "origin":
                    value = qbit_origin
                req.add_header(header, value)

            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw_body = resp.read()
                # Collect upstream headers so we can rewrite them before
                # echoing. We need to strip transfer-encoding and rewrite
                # content-length after any mutation.
                upstream_headers = list(resp.headers.items())
                content_type = resp.headers.get("Content-Type") or ""
                content_encoding = resp.headers.get("Content-Encoding") or ""

                # Theme bridge: on text/html, decompress (if gzipped),
                # inject the two bridge tags, rebrand qBittorrent → Боба,
                # drop the encoding header, rewrite CSP so bootstrap.js
                # can reach the merge service, and update Content-Length.
                body = raw_body
                mutated = False
                stripped_encoding = False
                if theme_injector is not None and content_type.lower().startswith("text/html"):
                    decoded, ok = theme_injector.maybe_decode_body(raw_body, content_encoding)
                    if ok:
                        new_body = theme_injector.inject_theme_assets(decoded, content_type)
                        new_body = theme_injector.rebrand_html(new_body, content_type)
                        if new_body is not decoded and new_body != decoded:
                            body = new_body
                            mutated = True
                        elif content_encoding:
                            body = decoded
                            mutated = True
                        if content_encoding:
                            stripped_encoding = True

                self.send_response(resp.status)
                for header, value in upstream_headers:
                    header_lower = header.lower()
                    if header_lower == "transfer-encoding":
                        continue
                    if header_lower == "content-encoding" and stripped_encoding:
                        continue
                    if header_lower == "content-length" and mutated:
                        # Recomputed below.
                        continue
                    if header_lower == "content-security-policy" and theme_injector is not None:
                        value = theme_injector.rewrite_csp(value)
                    self.send_header(header, value)
                if mutated:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        except urllib.error.HTTPError as e:
            # Forward qBittorrent's status/headers/body so auth failures
            # surface as 401 with ``Fails.`` body instead of being
            # rewritten to BaseHTTPRequestHandler's generic 401 HTML.
            try:
                self.send_response(e.code)
                for header, value in (e.headers or {}).items():
                    if header.lower() == "transfer-encoding":
                        continue
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(e.read() or e.reason.encode("utf-8"))
            except Exception:
                self.send_error(e.code, e.reason)

        except urllib.error.URLError as e:
            # qBittorrent upstream unreachable (connection refused /
            # network unreachable / DNS failure). HTTPError is a URLError
            # subclass and is handled above, so this branch is the
            # genuine transport-level failure. A bare-root liveness probe
            # must still see the bridge as alive — answer 200; everything
            # else gets a correct 502 Bad Gateway rather than a generic
            # 500 that the dashboard would misread as "bridge down".
            if self._is_root_liveness_probe():
                self._send_root_liveness(e.reason)
            else:
                self.send_error(502, f"qBittorrent upstream unreachable: {e.reason}")


def run_bridge():
    """Start the WebUI bridge server."""
    # ThreadingHTTPServer so one slow request (e.g. a long poll to qBit)
    # does not block the liveness probe from /api/v1/bridge/health.
    # Without this, the dashboard chip flipped to "down" any time a
    # real client happened to be mid-request.
    server = ThreadingHTTPServer(("", BRIDGE_PORT), WebUIBridgeHandler)

    print("=" * 70)
    print("Боба WebUI Bridge Server")
    print("=" * 70)
    print(f"Bridge Port: {BRIDGE_PORT}")
    print(f"qBittorrent backend: http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}")
    print("=" * 70)
    print("This bridge enables private tracker downloads in WebUI")
    print("=" * 70)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    run_bridge()
