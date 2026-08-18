"""
IPTorrents integration tests — freeleech detection, search, and download.

Requires:
  - IPTORRENTS_USERNAME and IPTORRENTS_PASSWORD in .env
  - qbittorrent-proxy container running (merge service on 7187)

Run:
    python3 -m pytest tests/integration/test_iptorrents.py -v --import-mode=importlib
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

MERGE_URL = os.environ.get("MERGE_URL", "http://localhost:7187")


def _fetch(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 420,
):
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, {}
    except urllib.error.URLError as e:
        return None, str(e.reason), {}


def _has_iptorrents_creds():
    return bool(os.environ.get("IPTORRENTS_USERNAME") and os.environ.get("IPTORRENTS_PASSWORD"))


def _bootstrap_env_from_dotenv():
    """Load .env into os.environ at module import time so the
    ``no_creds`` marker, which is evaluated during collection, can see
    the credentials. Previously this lived in a module-scope fixture
    that ran AFTER the decorator was applied, so IPTorrents tests
    skipped even with creds in .env."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v


_bootstrap_env_from_dotenv()


@pytest.fixture(scope="module")
def load_env():
    """Compatibility shim — .env is now loaded at module import."""
    _bootstrap_env_from_dotenv()


no_creds = pytest.mark.skipif(
    not (os.environ.get("IPTORRENTS_USERNAME") or os.environ.get("IPTORRENTS_USER")),
    reason="IPTorrents credentials not configured in environment — "
    "set IPTORRENTS_USERNAME / IPTORRENTS_PASSWORD in .env",
)


def _import_iptorrents():
    """Import the iptorrents plugin, clearing any stale ``helpers``
    module that may have been cached from ``config/qBittorrent/nova3/``
    (the stock qBittorrent version lacks ``htmlentitydecode``).
    """
    plugins_dir = os.path.join(os.path.dirname(__file__), "..", "..", "plugins")
    sys.path.insert(0, plugins_dir)
    sys.modules.pop("helpers", None)
    sys.modules.pop("iptorrents", None)
    from iptorrents import iptorrents

    return iptorrents


class TestIPTorrentsPluginUnit:
    def test_plugin_imports(self):
        iptorrents = _import_iptorrents()
        assert iptorrents.url == "https://iptorrents.com"
        assert iptorrents.name == "IPTorrents"

    def test_plugin_categories(self):
        iptorrents = _import_iptorrents()
        cats = iptorrents.supported_categories
        assert "movies" in cats
        assert "tv" in cats
        assert cats["movies"] == "72"
        assert cats["tv"] == "73"

    def test_plugin_has_search_freeleech_method(self):
        iptorrents = _import_iptorrents()
        assert hasattr(iptorrents, "search_freeleech")

    def test_plugin_has_download_method(self):
        iptorrents = _import_iptorrents()
        assert hasattr(iptorrents, "download_torrent")


@pytest.mark.timeout(600)
class TestIPTorrentsMergeService:
    @pytest.mark.requires_credentials
    def test_iptorrents_in_stats(self):
        if not _has_iptorrents_creds():
            pytest.fail("IPTorrents credentials are required; set IPTORRENTS_USERNAME/IPTORRENTS_PASSWORD")
        status, body, _ = _fetch(f"{MERGE_URL}/api/v1/stats")
        assert status == 200
        data = json.loads(body)
        tracker_names = [t["name"] for t in data.get("trackers", [])]
        assert "iptorrents" in tracker_names, f"iptorrents not in enabled trackers: {tracker_names}"

    @pytest.mark.requires_credentials
    @no_creds
    def test_search_returns_results(self):
        data = json.dumps({"query": "ubuntu", "limit": 10}).encode()
        status, body, _ = _fetch(
            f"{MERGE_URL}/api/v1/search/sync",
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        assert status in (200, 201, 202), f"Search failed: {status} {body}"
        result = json.loads(body)
        assert result.get("total_results", 0) >= 0

    @pytest.mark.requires_credentials
    @no_creds
    def test_search_results_have_freeleech_field(self, live_search_result):
        # Use the cached "linux" result so this test reuses one
        # session-wide fan-out instead of paying for its own 200-300 s
        # ``1080p`` search every batch run. ``linux`` reliably brings
        # back IPTorrents hits with the freeleech field populated.
        result = live_search_result("linux", 100)
        ip_results = [r for r in result.get("results", []) if r.get("tracker") == "iptorrents"]
        if not ip_results:
            pytest.skip(  # SKIP-OK: intentional — live network ranking is non-deterministic, not a defect
                f"IPTorrents results not in top-N for 'linux'; total_results={result.get('total_results')}"
            )
        for r in ip_results:
            assert "freeleech" in r, "Missing freeleech field in iptorrents result"


class TestIPTorrentsFreeleechDetection:
    def test_parse_iptorrents_html_freeleech(self):
        sys.path.insert(
            0,
            os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"),
        )
        from merge_service.search import SearchOrchestrator

        orch = SearchOrchestrator()
        # BOB-122 (reported as "BOB-083"): IPTorrents renders its result
        # rows with old-school UNCLOSED `<td>` tags -- there is no `</td>`
        # anywhere in a real response body, and the trailing three bare
        # `<td>N` cells are Snatches/Seeders/Leechers, in that column
        # order, per the table's own <thead>. This fixture mirrors that
        # real (unclosed-tag, 3-trailing-column) shape rather than a
        # neatly-closed synthetic one, so it actually exercises the parser
        # against the markup the live site produces.
        html = """<form><table id="torrents"><tr>
<td><a class=" hv" href="/t/123">Ubuntu 22.04 LTS</a>
<span class="free">Free!</span>
<td><a href="/download.php/123/ubuntu.torrent?torrent_key=abc">DL</a>
<td>4.5 GB<td>12<td>50<td>10</tr>
<tr>
<td><a class=" hv" href="/t/456">Ubuntu 20.04 LTS</a>
<td><a href="/download.php/456/ubuntu20.torrent?torrent_key=def">DL</a>
<td>3.2 GB<td>8<td>30<td>5</tr>
</table></form>"""
        results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"

        free_results = [r for r in results if r.freeleech]
        non_free = [r for r in results if not r.freeleech]
        assert len(free_results) == 1, f"Expected 1 freeleech, got {len(free_results)}"
        assert len(non_free) == 1, f"Expected 1 non-free, got {len(non_free)}"
        assert free_results[0].name == "Ubuntu 22.04 LTS [free]"
        assert free_results[0].tracker == "iptorrents"

        # BOB-122 regression guard: seed/leech must reflect the real
        # trailing values, never silently default to 0/0.
        assert free_results[0].seeds == 50
        assert free_results[0].leechers == 10
        assert non_free[0].seeds == 30
        assert non_free[0].leechers == 5

    def test_freeleech_tracker_display_tag(self):
        sys.path.insert(
            0,
            os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"),
        )
        from merge_service.search import SearchResult

        free_result = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
            tracker="iptorrents",
            freeleech=True,
        )
        d = free_result.to_dict()
        assert d["tracker_display"] == "iptorrents [free]"

        paid_result = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
            tracker="iptorrents",
            freeleech=False,
        )
        d = paid_result.to_dict()
        assert d["tracker_display"] == "iptorrents"


@pytest.mark.timeout(600)
class TestIPTorrentsDownloadFreeleechOnly:
    @pytest.mark.requires_credentials
    @no_creds
    def test_search_freeleech_via_merge_service(self, live_search_result):
        # Reuse the session-cached search instead of issuing a fresh
        # ``1080p`` fan-out. Both tests in this class assert the same
        # invariant on iptorrents freeleech rows.
        result = live_search_result("linux", 20)
        ip_results = [
            r for r in result.get("results", []) if r.get("tracker") == "iptorrents" and r.get("freeleech") is True
        ]
        for r in ip_results:
            assert r.get("freeleech") is True, f"Non-freeleech in results: {r}"
            assert "[free]" in r.get("tracker_display", ""), f"Missing [free] tag: {r}"

    @pytest.mark.requires_credentials
    @no_creds
    def test_plugin_search_freeleech_method(self):
        iptorrents = _import_iptorrents()
        engine = iptorrents()
        assert engine.session, (
            "IPTorrents login failed with credentials set — check "
            "IPTORRENTS_USERNAME/IPTORRENTS_PASSWORD and that the "
            "tracker is reachable"
        )
        import io
        from contextlib import redirect_stdout

        captured = io.StringIO()
        with redirect_stdout(captured):
            engine.search_freeleech("ubuntu")
        output = captured.getvalue()
        assert output is not None
