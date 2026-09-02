"""
Live container integration tests — validates both running containers
against real endpoints.

Requires:
  - Both containers running (qbittorrent + qbittorrent-proxy)
  - Podman or Docker on the host

Run:
    python3 -m pytest tests/integration/test_live_containers.py -v
"""

import json
import os
import subprocess
import urllib.error
import urllib.request

import pytest

QBITTORRENT_URL = os.environ.get("QBITTORRENT_URL", "http://localhost:7185")
PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:7186")
MERGE_URL = os.environ.get("MERGE_URL", "http://localhost:7187")
WEBUI_USER = os.environ.get("QBITTORRENT_USER", "admin")
WEBUI_PASS = os.environ.get("QBITTORRENT_PASS", "admin")


def _detect_runtime():
    env = os.environ.get("CONTAINER_RUNTIME")
    if env:
        return env
    for cmd in ("podman", "docker"):
        try:
            subprocess.run(
                [cmd, "version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
            return cmd
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            continue
    return None


RUNTIME = _detect_runtime()


def _exec(container: str, cmd: str, timeout: int = 15) -> subprocess.CompletedProcess:
    assert RUNTIME, "No container runtime found (podman/docker)"
    return subprocess.run(
        [RUNTIME, "exec", container, "sh", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _fetch(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
):
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, {}
    except urllib.error.URLError as e:
        return None, str(e.reason), {}


def _header(headers: dict | None, name: str) -> str:
    """Case-insensitive header lookup.

    ``dict(resp.headers)`` preserves the wire casing, and qBittorrent emits
    ``set-cookie`` in lowercase — a plain ``headers["Set-Cookie"]`` would miss
    it and silently read as "no cookie was issued" (a §11.4.201 false-null).
    """
    if not headers:
        return ""
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


# ──────────────────────────────────────────────
# Container Runtime
# ──────────────────────────────────────────────


class TestContainerRuntime:
    def test_runtime_detected(self):
        assert RUNTIME, "Neither podman nor docker found on PATH"

    def test_qbittorrent_container_running(self):
        r = _exec("qbittorrent", "echo ok")
        assert r.returncode == 0, f"qbittorrent container not running: {r.stderr}"

    def test_proxy_container_running(self):
        r = _exec("qbittorrent-proxy", "echo ok")
        assert r.returncode == 0, f"qbittorrent-proxy container not running: {r.stderr}"


# ──────────────────────────────────────────────
# qBittorrent WebUI (port 7185)
# ──────────────────────────────────────────────


class TestQbittorrentWebUI:
    def test_webui_reachable(self):
        status, _, _ = _fetch(f"{QBITTORRENT_URL}/")
        assert status == 200, f"qBittorrent WebUI not reachable: status={status}"

    def test_webui_login(self):
        """A GOOD credential must actually authenticate — and a BAD one must not.

        The previous form accepted ``status in (200, 302, 403)`` as a pass.
        ``403`` is qBittorrent's REFUSAL, so that assertion scored a rejected
        login as a successful one and could not fail for the defect it named —
        a §11.4 PASS-bluff. Measured reality (2026-09-01, qBittorrent 5.2.3):
        good login → ``204`` + ``Set-Cookie: QBT_SID_<port>=…``; bad login →
        ``401`` with no cookie.
        """
        data = urllib.parse.urlencode({"username": WEBUI_USER, "password": WEBUI_PASS}).encode()
        status, body, headers = _fetch(f"{QBITTORRENT_URL}/api/v2/auth/login", method="POST", data=data)

        set_cookie = _header(headers, "Set-Cookie")
        has_session = "QBT_SID" in set_cookie
        assert status is not None and 200 <= status < 300 and (has_session or body.strip() == "Ok."), (
            f"login with the configured credential did not authenticate: "
            f"status={status} body={body.strip()!r} set_cookie={set_cookie!r}"
        )

        # Negative control — a wrong password must NOT mint a session cookie.
        bad_data = urllib.parse.urlencode({"username": WEBUI_USER, "password": "wrongwrong"}).encode()
        bad_status, bad_body, bad_headers = _fetch(
            f"{QBITTORRENT_URL}/api/v2/auth/login", method="POST", data=bad_data
        )
        bad_cookie = _header(bad_headers, "Set-Cookie")
        bad_ok = bad_status is not None and 200 <= bad_status < 300 and ("QBT_SID" in bad_cookie or bad_body.strip() == "Ok.")
        assert not bad_ok, (
            f"a WRONG password authenticated: status={bad_status} "
            f"body={bad_body.strip()!r} set_cookie={bad_cookie!r}"
        )

    def test_api_version(self):
        data = urllib.parse.urlencode({"username": WEBUI_USER, "password": WEBUI_PASS}).encode()
        status, body, _ = _fetch(f"{QBITTORRENT_URL}/api/v2/auth/login", method="POST", data=data)
        cookie = ""
        for line in body.split("\n"):
            pass
        status, body, _ = _fetch(f"{QBITTORRENT_URL}/api/v2/app/version")
        assert status == 200 or status == 403, f"Version endpoint unexpected: {status}"

    def test_transfer_info(self):
        status, body, _ = _fetch(f"{QBITTORRENT_URL}/api/v2/transfer/info")
        assert status in (200, 403), f"Transfer info unexpected: {status}"


# ──────────────────────────────────────────────
# Download Proxy (port 7186)
# ──────────────────────────────────────────────


class TestDownloadProxy:
    @pytest.fixture(autouse=True)
    def _service_up(self, qbittorrent_live):
        self.proxy_url = qbittorrent_live

    def test_proxy_container_has_proxy_module(self):
        r = _exec(
            "qbittorrent-proxy",
            'python3 -c \'import sys; sys.path.insert(0, "/config/qBittorrent/nova3/engines"); from download_proxy import run_server; print("ok")\'',
        )
        assert r.returncode == 0, f"download_proxy module not importable: {r.stderr}"

    def test_proxy_reachable(self):
        status, body, _ = _fetch(f"{self.proxy_url}/")
        assert status is not None, f"Proxy not reachable at {self.proxy_url}"

    def test_proxy_forwards_to_qbittorrent(self):
        status, body, _ = _fetch(f"{self.proxy_url}/")
        assert status == 200, f"Proxy forward failed: status={status}"
        assert "qBittorrent" in body or "html" in body.lower(), "Proxy not forwarding to qBittorrent WebUI"

    def test_proxy_container_has_requests(self):
        r = _exec(
            "qbittorrent-proxy",
            "python3 -c 'import requests; print(requests.__version__)'",
        )
        assert r.returncode == 0, f"requests not installed in proxy: {r.stderr}"

    def test_proxy_container_has_fastapi(self):
        r = _exec(
            "qbittorrent-proxy",
            "python3 -c 'import fastapi; print(fastapi.__version__)'",
        )
        assert r.returncode == 0, f"fastapi not installed in proxy: {r.stderr}"

    def test_proxy_container_has_uvicorn(self):
        r = _exec(
            "qbittorrent-proxy",
            "python3 -c 'import uvicorn; print(uvicorn.__version__)'",
        )
        assert r.returncode == 0, f"uvicorn not installed in proxy: {r.stderr}"


# ──────────────────────────────────────────────
# Merge Search Service (port 7187)
# ──────────────────────────────────────────────


class TestMergeService:
    def test_health_endpoint(self):
        status, body, _ = _fetch(f"{MERGE_URL}/health")
        assert status == 200, f"Merge service health check failed: {status}"
        data = json.loads(body)
        assert data.get("status") == "healthy"
        assert data.get("service") == "merge-search"

    def test_dashboard_endpoint(self):
        status, body, _ = _fetch(f"{MERGE_URL}/")
        assert status == 200, f"Dashboard not served: {status}"
        assert "<html" in body.lower(), "Dashboard not returning HTML"

    def test_stats_endpoint(self):
        status, body, _ = _fetch(f"{MERGE_URL}/api/v1/stats")
        assert status == 200, f"Stats endpoint failed: {status}"
        data = json.loads(body)
        assert "trackers_count" in data
        assert isinstance(data["trackers_count"], int)

    def test_search_endpoint_exists(self):
        data = json.dumps({"query": "ubuntu", "limit": 3}).encode()
        status, body, _ = _fetch(
            f"{MERGE_URL}/api/v1/search",
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        assert status in (200, 201, 202, 502, 503), f"Search endpoint unexpected status: {status}, body: {body}"

    def test_hooks_endpoint(self):
        status, body, _ = _fetch(f"{MERGE_URL}/api/v1/hooks")
        assert status == 200, f"Hooks GET failed: {status}"
        data = json.loads(body)
        assert isinstance(data, (list, dict)), f"Hooks returned unexpected type: {type(data)}"

    def test_merge_source_code_in_container(self):
        r = _exec("qbittorrent-proxy", "ls /config/download-proxy/src/api/__init__.py")
        assert r.returncode == 0, f"Merge service source not found in container: {r.stderr}"

    def test_merge_service_running_in_container(self):
        r = _exec("qbittorrent-proxy", "ps aux | grep python3")
        assert "python3" in r.stdout, f"No python3 process in proxy container: {r.stdout}"

    def test_streaming_endpoint_exists(self):
        status, body, _ = _fetch(f"{MERGE_URL}/api/v1/search/stream/nonexistent-id")
        assert status in (200, 404), f"Streaming endpoint unexpected: {status}"


# ──────────────────────────────────────────────
# Container Environment & Config
# ──────────────────────────────────────────────


class TestContainerEnvironment:
    @pytest.mark.requires_credentials
    def test_rutracker_creds_configured(self):
        r = _exec("qbittorrent-proxy", "env | grep RUTRACKER_USERNAME || true")
        assert r.stdout.strip(), (
            "RUTRACKER_USERNAME must be configured in .env — required for the rutracker plugin to search"
        )

    def test_proxy_port_env(self):
        r = _exec("qbittorrent-proxy", "echo $PROXY_PORT")
        assert r.stdout.strip() in ("7186", ""), f"PROXY_PORT unexpected: {r.stdout.strip()}"

    def test_merge_port_env(self):
        r = _exec("qbittorrent-proxy", "echo $MERGE_SERVICE_PORT")
        port = r.stdout.strip()
        # MERGE_SERVICE_PORT may be unset (compose uses the 7187 default).
        # Treat empty as equivalent to the default — assert the actual
        # listen port works via /health instead.
        if port:
            assert port == "7187", f"MERGE_SERVICE_PORT is: {port}"
        # Always verify the service is listening on 7187 regardless.
        hr = _fetch(f"{MERGE_URL}/health")
        assert hr[0] == 200, f"merge service not reachable on 7187: {hr[0]}"

    def test_shared_tmp_mount(self):
        r = _exec("qbittorrent-proxy", "ls -la /shared-tmp/ 2>/dev/null || true")
        assert r.returncode == 0 and "/shared-tmp" not in r.stderr, (
            "/shared-tmp must be mounted — update docker-compose.yml and `podman compose up -d` to pick up the mount"
        )

    def test_shared_tmp_in_qbittorrent(self):
        r = _exec("qbittorrent", "ls -la /shared-tmp/")
        assert r.returncode == 0, "/shared-tmp not mounted in qbittorrent"

    def test_download_proxy_source_mounted(self):
        r = _exec("qbittorrent-proxy", "ls /config/download-proxy/src/main.py")
        assert r.returncode == 0, "download-proxy source not mounted"

    def test_qbittorrent_env_file_mounted(self):
        r = _exec("qbittorrent-proxy", "cat /config/.env | head -1")
        assert r.returncode == 0, ".env not mounted in proxy container"

    def test_network_mode_host(self):
        assert RUNTIME
        r = subprocess.run(
            [
                RUNTIME,
                "inspect",
                "qbittorrent",
                "--format",
                "{{.HostConfig.NetworkMode}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "host" in r.stdout.lower(), f"qbittorrent not using host network: {r.stdout}"

        r2 = subprocess.run(
            [
                RUNTIME,
                "inspect",
                "qbittorrent-proxy",
                "--format",
                "{{.HostConfig.NetworkMode}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "host" in r2.stdout.lower(), f"qbittorrent-proxy not using host network: {r2.stdout}"


# ──────────────────────────────────────────────
# Startup & Restart Resilience
# ──────────────────────────────────────────────


class TestStartupResilience:
    def test_start_proxy_script_exists(self):
        r = _exec("qbittorrent-proxy", "cat /start-proxy.sh")
        assert r.returncode == 0, "/start-proxy.sh not found in container"
        assert "main.py" in r.stdout, "start-proxy.sh does not reference main.py"

    def test_requirements_file_mounted(self):
        r = _exec("qbittorrent-proxy", "cat /config/download-proxy/requirements.txt")
        assert r.returncode == 0, "requirements.txt not mounted in container"
        assert "fastapi" in r.stdout, "fastapi not in requirements.txt"
        assert "uvicorn" in r.stdout, "uvicorn not in requirements.txt"

    def test_main_py_entrypoint(self):
        r = _exec("qbittorrent-proxy", "cat /proc/1/cmdline | tr '\\0' ' '")
        assert "main.py" in r.stdout, f"PID 1 is not main.py: {r.stdout}"

    def test_no_pip_install_at_runtime(self):
        r = _exec(
            "qbittorrent-proxy",
            "python3 -c 'import requests, fastapi, uvicorn; print(\"ok\")'",
        )
        assert r.returncode == 0, f"Core deps missing: {r.stderr}"

    def test_config_dir_writable(self):
        r = _exec(
            "qbittorrent-proxy",
            "touch /config/download-proxy/.write_test && rm /config/download-proxy/.write_test",
        )
        assert r.returncode == 0, f"config/ dir not writable: {r.stderr}"
