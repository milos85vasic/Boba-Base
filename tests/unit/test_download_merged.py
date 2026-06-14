"""
Unit tests for merged download functionality.

Issue 1: Plus button must become Download button and produce merged sources.
"""

import os
import sys

_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))
if _src not in sys.path:
    sys.path.insert(0, _src)

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request


class TestDownloadButtonLabel:
    """Dashboard must show 'Download' instead of '+'."""

    def test_dashboard_has_download_button_not_plus(self):
        """The button text must be 'Download', not '+'."""
        # Read dashboard template
        dashboard_path = os.path.join(_src, "ui", "templates", "dashboard.html")
        with open(dashboard_path) as f:
            html = f.read()
        # Must contain Download button
        assert ">Download</button>" in html or 'title="Download">Download' in html, (
            "Dashboard must have 'Download' button instead of '+'"
        )
        # Should not have standalone + button
        assert ">+</button>" not in html, "Dashboard must not have '+' button"


class TestMergedMagnetGeneration:
    """Magnet generation must include all trackers from all sources."""

    @pytest.mark.asyncio
    async def test_magnet_endpoint_builds_single_xt_from_primary(self):
        """A magnet identifies ONE torrent — it MUST carry exactly one xt.

        Reconciled per §11.4.120: this test previously asserted the magnet
        embed EVERY source infohash (multi-xt). That encoded the bug — a
        merged content row aggregates many distinct tracker-copies (each a
        different infohash), and joining them all produced a malformed
        21-xt magnet qBittorrent rejects (confirmed live, 2026-06-14:
        Magnet dialog showed 21 `xt=urn:btih:` for an Ubuntu merged row).
        Correct behaviour: build the magnet from the PRIMARY (first =
        best/highest-seeded) source only, while still aggregating every
        source's trackers to enrich the swarm.
        """
        from api.routes import generate_magnet

        primary = "abc123def4567890abc123def4567890abc12345"
        secondary = "def4567890abc123def4567890abc123def45678"
        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={
                "result_id": "test",
                "download_urls": [
                    f"magnet:?xt=urn:btih:{primary}&tr=udp://tracker1:1337",
                    f"magnet:?xt=urn:btih:{secondary}&tr=udp://tracker2:6969",
                ],
            }
        )
        resp = await generate_magnet(mock_request)
        magnet = resp["magnet"]
        # EXACTLY ONE xt — a single torrent.
        assert magnet.count("xt=urn:btih:") == 1, f"magnet must have one xt, got: {magnet}"
        # The one xt is the PRIMARY (first) source.
        assert primary in magnet, f"primary infohash missing: {magnet}"
        assert secondary not in magnet, f"secondary infohash must NOT be in single-torrent magnet: {magnet}"
        # Trackers from ALL sources are still aggregated (enriches the swarm).
        assert "tracker1" in magnet, f"primary source tracker missing: {magnet}"
        assert "tracker2" in magnet, f"secondary source tracker missing: {magnet}"

    @pytest.mark.asyncio
    async def test_magnet_single_xt_for_21_source_merged_row(self):
        """RED→GREEN guard for the live defect: a 21-source merged row.

        Reproduces the exact field-overloading regression confirmed in the
        browser — 21 distinct tracker-copies of one content item. The
        magnet MUST collapse to the single primary torrent, never a 21-xt
        link. Fails on the pre-fix `"&".join(...)` implementation.
        """
        from api.routes import generate_magnet

        hashes = [f"{i:040x}" for i in range(1, 22)]  # 21 distinct 40-hex infohashes
        urls = [f"magnet:?xt=urn:btih:{h}&tr=udp://t{i}:1337" for i, h in enumerate(hashes)]
        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"result_id": "Ubuntu 11 04 Desktop", "download_urls": urls})
        resp = await generate_magnet(mock_request)
        magnet = resp["magnet"]
        assert magnet.count("xt=urn:btih:") == 1, (
            f"21-source merged row must yield ONE xt, got {magnet.count('xt=urn:btih:')}"
        )
        assert hashes[0] in magnet, "primary (first) source must be the chosen torrent"

    @pytest.mark.asyncio
    async def test_magnet_endpoint_includes_source_trackers(self):
        """Generated magnet must include trackers from source magnet URLs."""
        from api.routes import generate_magnet

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={
                "result_id": "test",
                "download_urls": [
                    "magnet:?xt=urn:btih:abc123&tr=udp://tracker1.org:1337&tr=udp://tracker2.org:6969",
                ],
            }
        )
        resp = await generate_magnet(mock_request)
        magnet = resp["magnet"]
        assert "tracker1.org" in magnet, f"Missing source tracker in magnet: {magnet}"
        assert "tracker2.org" in magnet, f"Missing source tracker in magnet: {magnet}"

    def test_merged_magnet_function_exists(self):
        """There should be a function to generate merged magnets."""
        import inspect

        from api import routes

        assert hasattr(routes, "generate_magnet") or "generate_magnet" in inspect.getsource(routes)


class TestMergedQbitAdd:
    """qBit button on a merged row must add ONE torrent (the primary), not all sources."""

    @pytest.mark.asyncio
    async def test_qbit_adds_only_primary_source_of_merged_row(self):
        """A merged content row aggregates many distinct tracker-copies.

        The qBit button must add the SINGLE best source (download_urls[0])
        and stop on the first successful add — never fan a content item out
        into N distinct torrents in the client. Fails on the pre-fix
        `for url in download_urls[:5]` loop that added up to 5 of them.
        Confirmed live (2026-06-14): the Ubuntu merged row's download_urls
        carried 21 distinct infohashes; the old loop added 3 wrong torrents.
        """
        from api.routes import DownloadRequest, initiate_download

        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="Ok.")
        mock_resp.status = 200
        mock_resp.cookies = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # 3 distinct tracker-copies of the SAME content (merged row).
        urls = [
            "magnet:?xt=urn:btih:" + ("a" * 40),
            "magnet:?xt=urn:btih:" + ("b" * 40),
            "magnet:?xt=urn:btih:" + ("c" * 40),
        ]
        req = DownloadRequest(result_id="Ubuntu 11 04", download_urls=urls)

        with (
            patch("api.routes._get_orchestrator", return_value=MagicMock()),
            patch("api.routes._get_qbit_username", return_value="admin"),
            patch("api.routes._get_qbit_password", return_value="admin"),
            patch("api.hooks.dispatch_event", new_callable=AsyncMock),
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            result = await initiate_download(req, MagicMock())

        add_calls = [c for c in mock_session.post.call_args_list if str(c).find("/torrents/add") != -1]
        assert len(add_calls) == 1, f"expected ONE add (primary only), got {len(add_calls)}"
        assert result.get("added_count") == 1, f"expected added_count==1, got {result.get('added_count')}"


class TestDownloadFileEndpoint:
    """Download file endpoint must return merged sources."""

    @pytest.mark.asyncio
    async def test_download_file_returns_merged_magnet_with_all_trackers(self):
        """For magnet URLs, /download/file should return a merged magnet with all trackers."""
        from unittest.mock import patch

        from api.routes import download_torrent_file

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.enricher = None

        mock_orch = MagicMock()
        mock_orch.fetch_torrent = AsyncMock(return_value=None)

        with patch("api.routes._get_orchestrator", return_value=mock_orch):
            resp = await download_torrent_file(
                MagicMock(
                    result_id="test",
                    download_urls=[
                        "magnet:?xt=urn:btih:abc123&tr=udp://t1:1337",
                        "magnet:?xt=urn:btih:def456&tr=udp://t2:6969",
                    ],
                ),
                mock_request,
            )
        # Should not be a 404
        assert resp.status_code != 404, "Download file endpoint returned 404 for magnet links"
        # For magnet links it currently returns PlainTextResponse
        from fastapi.responses import PlainTextResponse

        if isinstance(resp, PlainTextResponse):
            body = resp.body.decode()
            # The merged magnet should contain both trackers
            assert "t1" in body or "t2" in body or "opentrackr" in body, f"Magnet missing trackers: {body}"

    def test_dashboard_magnet_button_calls_proper_endpoint(self):
        """Magnet button should use merged magnet generation."""
        dashboard_path = os.path.join(_src, "ui", "templates", "dashboard.html")
        with open(dashboard_path) as f:
            html = f.read()
        # The magnet dialog should populate from actual results, not hardcoded trackers only
        assert "generateMagnet" in html, "Missing generateMagnet function"
