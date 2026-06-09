"""
Additional coverage for merge_service/validator.py — bencode parsing,
HTTP/UDP scrape, caching, validate_multiple.
"""

import asyncio
import importlib.util
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_validator_spec = importlib.util.spec_from_file_location(
    "merge_service.validator", os.path.join(_MS_PATH, "validator.py")
)
_validator_mod = importlib.util.module_from_spec(_validator_spec)
sys.modules["merge_service.validator"] = _validator_mod
_validator_spec.loader.exec_module(_validator_mod)

TrackerValidator = _validator_mod.TrackerValidator
ScrapeResult = _validator_mod.ScrapeResult
TrackerStatus = _validator_mod.TrackerStatus


class TestBencodeParsing:
    def test_empty_dict(self):
        v = TrackerValidator()
        result = v._parse_bencoded(b"de")
        assert result == {}

    def test_simple_dict(self):
        v = TrackerValidator()
        data = b"d4:name5:alice3:agei25ee"
        result = v._parse_bencoded(data)
        assert result[b"name"] == b"alice"
        assert result[b"age"] == 25

    def test_nested_dict(self):
        v = TrackerValidator()
        data = b"d4:infod6:lengthi1024eee"
        result = v._parse_bencoded(data)
        assert result[b"info"][b"length"] == 1024

    def test_list(self):
        v = TrackerValidator()
        data = b"l5:hello5:worlde"
        result, pos = v._decode_benc(data, 0)
        assert result == [b"hello", b"world"]

    def test_integer(self):
        v = TrackerValidator()
        data = b"i42e"
        result, pos = v._decode_benc(data, 0)
        assert result == 42

    def test_string(self):
        v = TrackerValidator()
        data = b"5:hello"
        result, pos = v._decode_benc(data, 0)
        assert result == b"hello"

    def test_empty_list(self):
        v = TrackerValidator()
        data = b"le"
        result, pos = v._decode_benc(data, 0)
        assert result == []

    def test_invalid_bencode(self):
        v = TrackerValidator()
        result = v._parse_bencoded(b"xyz")
        assert result == {}

    def test_unexpected_end(self):
        v = TrackerValidator()
        with pytest.raises(ValueError, match="Unexpected end"):
            v._decode_benc(b"", 0)

    def test_invalid_char(self):
        v = TrackerValidator()
        with pytest.raises(ValueError, match="Invalid bencode"):
            v._decode_benc(b"x", 0)

    def test_dict_with_list_value(self):
        v = TrackerValidator()
        data = b"d4:listli1ei2eee"
        result = v._parse_bencoded(data)
        assert result[b"list"] == [1, 2]


class TestHttpScrape:
    @pytest.mark.asyncio
    async def test_invalid_scrape_url(self):
        v = TrackerValidator()
        result = await v._http_scrape("not-a-valid-url")
        assert result.status == TrackerStatus.OFFLINE
        assert "Invalid" in result.error

    @pytest.mark.asyncio
    async def test_successful_scrape(self):
        v = TrackerValidator()
        bencoded_response = b"d5:filesdee"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=bencoded_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(v, "_get_session", return_value=mock_session):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_successful_single_torrent_scrape(self):
        v = TrackerValidator()
        bencoded = b"d8:completei200e10:incompletei50e7:tracker6:ubuntue"
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=bencoded)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch.object(v, "_get_session", return_value=mock_session):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.HEALTHY
            assert result.seeds == 200
            assert result.leechers == 50

    @pytest.mark.asyncio
    async def test_http_error_status(self):
        v = TrackerValidator()
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(v, "_get_session", return_value=mock_session):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.OFFLINE
            assert "500" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self):
        v = TrackerValidator()
        with patch.object(v, "_get_session", side_effect=TimeoutError()):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.OFFLINE
            assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_connection_error(self):
        v = TrackerValidator()
        with patch.object(v, "_get_session", side_effect=Exception("conn refused")):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.OFFLINE
            assert "conn refused" in result.error

    @pytest.mark.asyncio
    async def test_session_creation_failure(self):
        v = TrackerValidator()
        with patch.object(v, "_get_session", return_value=None):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.UNKNOWN
            assert "session creation failed" in result.error

    @pytest.mark.asyncio
    async def test_validate_tracker_fallback_to_udp(self):
        v = TrackerValidator()
        http_result = ScrapeResult(
            tracker="udp://tracker.com:80/announce",
            status=TrackerStatus.OFFLINE,
            error="HTTP failed",
        )
        udp_result = ScrapeResult(
            tracker="udp://tracker.com:80/announce",
            status=TrackerStatus.OFFLINE,
            error="UDP timeout",
        )
        with patch.object(v, "_http_scrape", return_value=http_result):
            with patch.object(v, "_udp_scrape", return_value=udp_result):
                result = await v.validate_tracker("udp://tracker.com:80/announce")
                assert result.status == TrackerStatus.OFFLINE
                assert "UDP timeout" in result.error

    @pytest.mark.asyncio
    async def test_validate_tracker_http_success_no_fallback(self):
        v = TrackerValidator()
        http_result = ScrapeResult(
            tracker="https://tracker.com/announce",
            status=TrackerStatus.HEALTHY,
            seeds=50,
            leechers=10,
        )
        with patch.object(v, "_http_scrape", return_value=http_result):
            result = await v.validate_tracker("https://tracker.com/announce")
            assert result.status == TrackerStatus.HEALTHY
            assert result.seeds == 50

    @pytest.mark.asyncio
    async def test_http_scrape_with_valid_bencoded_files(self):
        v = TrackerValidator()
        bencoded = b"d5:filesd20:aaaaaaaaaaaaaaaaaaaa d8:completei5e10:incompletei3eeee"
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=bencoded)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch.object(v, "_get_session", return_value=mock_session):
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.HEALTHY


class TestValidateTracker:
    @pytest.mark.asyncio
    async def test_caches_result(self):
        v = TrackerValidator()
        mock_result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)

        with patch.object(v, "_http_scrape", return_value=mock_result):
            r1 = await v.validate_tracker("https://tracker.com/announce")
            assert r1.status == TrackerStatus.HEALTHY
            assert "https://tracker.com/announce" in v._cache


class TestGetCachedResult:
    def test_no_cache(self):
        v = TrackerValidator()
        assert v.get_cached_result("http://unknown") is None

    def test_expired_cache(self):
        import time

        v = TrackerValidator()
        mock_result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)
        v._cache["http://t"] = (time.time() - 600, mock_result)
        assert v.get_cached_result("http://t") is None

    def test_valid_cache(self):
        import time

        v = TrackerValidator()
        mock_result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)
        v._cache["http://t"] = (time.time(), mock_result)
        assert v.get_cached_result("http://t") is mock_result


class TestValidateMultiple:
    @pytest.mark.asyncio
    async def test_multiple_trackers(self):
        v = TrackerValidator()
        urls = ["https://a.com/announce", "https://b.com/announce"]
        mock_result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)

        with patch.object(v, "validate_tracker", return_value=mock_result):
            results = await v.validate_multiple(urls)
            assert len(results) == 2


class TestUdpScrape:
    @pytest.mark.asyncio
    async def test_invalid_url(self):
        v = TrackerValidator()
        result = await v._udp_scrape("not-valid")
        assert result.status == TrackerStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        v = TrackerValidator()
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.side_effect = Exception("no loop")
            result = await v._udp_scrape("udp://tracker.com:80/announce")
            assert result.status == TrackerStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_udp_timeout(self):
        v = TrackerValidator()
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.side_effect = TimeoutError("UDP timeout")
            result = await v._udp_scrape("udp://tracker.com:80/announce")
            assert result.status == TrackerStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_udp_connect_response_too_short(self):
        """Connect response shorter than 16 bytes (line 217-222)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        connect_future = loop.create_future()
        connect_future.set_result(b"tooshort")

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [connect_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.return_value = 42
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape("udp://tracker.com:80/announce")
            assert result.status == TrackerStatus.OFFLINE
            assert "too short" in result.error

    @pytest.mark.asyncio
    async def test_udp_handshake_failed(self):
        """Connect response with wrong action/transaction_id (line 224-231)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        conn_id = 12345
        bad_resp = struct.pack("!iiq", 999, 0, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(bad_resp)

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [connect_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.return_value = 0
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape("udp://tracker.com:80/announce")
            assert result.status == TrackerStatus.OFFLINE
            assert "handshake failed" in result.error

    @pytest.mark.asyncio
    async def test_udp_no_infohash_healthy(self):
        """Valid connect, no infohash → HEALTHY with seeds=0 (line 234-240)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        tid = 42
        conn_id = 12345
        connect_resp = struct.pack("!iiq", 0, tid, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(connect_resp)

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [connect_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.return_value = tid
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape("udp://tracker.com:80/announce")
            assert result.status == TrackerStatus.HEALTHY
            assert result.seeds == 0

    @pytest.mark.asyncio
    async def test_udp_scrape_response_too_short(self):
        """Scrape response shorter than 20 bytes (line 258-263)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        connect_tid = 10
        conn_id = 34567
        connect_resp = struct.pack("!iiq", 0, connect_tid, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(connect_resp)

        # connect_future is pre-set on mock_protocol for connect phase
        # create_future is only called once at line 253 → returns scrape_future
        scrape_future = loop.create_future()
        scrape_future.set_result(b"tooshort")

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [scrape_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.side_effect = [connect_tid, 99]
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape(
                "udp://tracker.com:80/announce?aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
            assert result.status == TrackerStatus.OFFLINE
            assert "too short" in result.error

    @pytest.mark.asyncio
    async def test_udp_scrape_error(self):
        """Scrape response with action=3 (error from tracker, line 266-271)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        connect_tid = 10
        conn_id = 34567
        connect_resp = struct.pack("!iiq", 0, connect_tid, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(connect_resp)

        scrape_tid = 99
        # Pad to 20 bytes to pass length check, then action=3 triggers error path
        scrape_resp = struct.pack("!ii", 3, scrape_tid) + b"\x00" * 12

        scrape_future = loop.create_future()
        scrape_future.set_result(scrape_resp)

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [scrape_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.side_effect = [connect_tid, scrape_tid]
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape(
                "udp://tracker.com:80/announce?aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
            assert result.status == TrackerStatus.OFFLINE
            assert "error from tracker" in result.error

    @pytest.mark.asyncio
    async def test_udp_invalid_hex_infohash(self):
        """Invalid hex infohash triggers except ValueError (line 247-248)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        connect_tid = 10
        conn_id = 34567
        connect_resp = struct.pack("!iiq", 0, connect_tid, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(connect_resp)

        scrape_tid = 99
        scrape_resp = struct.pack("!iiiii", 2, scrape_tid, 50, 20, 10)

        scrape_future = loop.create_future()
        scrape_future.set_result(scrape_resp)

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [scrape_future]

        # zz is invalid hex; bytes.fromhex raises ValueError, falls to .encode()[:20]
        invalid_hex_url = "udp://tracker.com:80/announce?zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.side_effect = [connect_tid, scrape_tid]
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape(invalid_hex_url)
            assert result.status == TrackerStatus.HEALTHY
            assert result.seeds == 50

    @pytest.mark.asyncio
    async def test_udp_successful_scrape(self):
        """Full successful UDP scrape with seeds/leechers (line 273-281)."""
        import struct
        v = TrackerValidator()
        loop = asyncio.get_running_loop()

        connect_tid = 10
        conn_id = 34567
        connect_resp = struct.pack("!iiq", 0, connect_tid, conn_id)

        connect_future = loop.create_future()
        connect_future.set_result(connect_resp)

        scrape_tid = 99
        seeders = 150
        completed = 75
        leechers = 25
        scrape_resp = struct.pack(
            "!iiiii", 2, scrape_tid, seeders, completed, leechers
        )

        scrape_future = loop.create_future()
        scrape_future.set_result(scrape_resp)

        mock_transport = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.response_future = connect_future

        future_queue = [scrape_future]

        with patch("random.randint") as mock_rand, \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_rand.side_effect = [connect_tid, scrape_tid]
            mock_loop = MagicMock()
            mock_loop.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            mock_loop.create_future = MagicMock(side_effect=lambda: future_queue.pop(0))
            mock_get_loop.return_value = mock_loop

            result = await v._udp_scrape(
                "udp://tracker.com:80/announce?aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
            assert result.status == TrackerStatus.HEALTHY
            assert result.seeds == 150
            assert result.leechers == 25
            assert result.complete == 75




class TestCloseSession:
    @pytest.mark.asyncio
    async def test_close_with_open_session(self):
        v = TrackerValidator()
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        v._session = mock_session
        await v.close()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_none_session(self):
        v = TrackerValidator()
        v._session = None
        await v.close()


class TestRealSession:
    """Session lifecycle tests with real aiohttp — no mocks."""

    @pytest.mark.asyncio
    async def test_get_session_creates_real_session(self):
        v = TrackerValidator()
        assert v._session is None
        session = await v._get_session()
        assert session is not None
        assert not session.closed
        assert session._timeout.total == v.HTTP_TIMEOUT
        await session.close()

    @pytest.mark.asyncio
    async def test_get_session_reuses_open_session(self):
        v = TrackerValidator()
        s1 = await v._get_session()
        s2 = await v._get_session()
        assert s1 is s2
        await s1.close()

    @pytest.mark.asyncio
    async def test_get_session_recreates_after_close(self):
        v = TrackerValidator()
        s1 = await v._get_session()
        await s1.close()
        s2 = await v._get_session()
        assert s2 is not None
        assert s1 is not s2
        await s2.close()

    @pytest.mark.asyncio
    async def test_close_with_real_session(self):
        v = TrackerValidator()
        session = await v._get_session()
        assert not session.closed
        await v.close()
        assert session.closed


class TestAioHttpNotAvailable:
    """Tests for aiohttp not available path (lines 103-108)."""

    @pytest.mark.asyncio
    async def test_http_scrape_returns_unknown_when_aiohttp_missing(self):
        with patch.object(_validator_mod, "AIOHTTP_AVAILABLE", False):
            v = TrackerValidator()
            result = await v._http_scrape("https://tracker.com/announce")
            assert result.status == TrackerStatus.UNKNOWN
            assert "aiohttp not available" in result.error


class TestBencodeRealisticScrape:
    """Bencode parsing with realistic BEP 48 scrape data — no mocks."""

    def test_multi_file_scrape(self):
        """Parse a multi-file BEP 48 scrape response with infohash-keyed dict."""
        infohash = b"\x01" * 20
        data = (
            b"d5:filesd20:" + infohash +
            b"d8:completei100e10:incompletei50e10:downloadedi200eeee"
        )
        v = TrackerValidator()
        result = v._parse_bencoded(data)
        files = result.get(b"files", {})
        assert isinstance(files, dict)
        stats = files.get(infohash)
        assert stats is not None
        assert stats[b"complete"] == 100
        assert stats[b"incomplete"] == 50
        assert stats[b"downloaded"] == 200

    def test_single_torrent_scrape(self):
        """Parse a single-torrent scrape response with tracker key as bytes."""
        data = (
            b"d8:completei200e10:incompletei50e"
            b"10:downloadedi100e7:tracker6:ubuntu"
            b"12:piece_lengthi524288ee"
        )
        v = TrackerValidator()
        result = v._parse_bencoded(data)
        assert result[b"complete"] == 200
        assert result[b"incomplete"] == 50
        assert result[b"downloaded"] == 100
        assert result[b"tracker"] == b"ubuntu"
        assert result[b"piece_length"] == 524288

    def test_empty_files_dict(self):
        """Parse a scrape with an empty files dict."""
        data = b"d5:filesdee"
        v = TrackerValidator()
        result = v._parse_bencoded(data)
        assert result.get(b"files") == {}


class TestAnnounceToScrapeEdgeCases:
    """Edge cases for announce-to-scrape URL conversion — no mocks."""

    def test_null_url(self):
        v = TrackerValidator()
        assert v._announce_to_scrape("") is None

    def test_no_match(self):
        v = TrackerValidator()
        assert v._announce_to_scrape("https://tracker.com/foo") is None

    def test_subdomain_announce(self):
        v = TrackerValidator()
        url = "https://tracker.example.com/announce"
        assert v._announce_to_scrape(url) == "https://tracker.example.com/scrape"

    def test_announce_with_path(self):
        v = TrackerValidator()
        url = "https://tracker.com/announce/123"
        result = v._announce_to_scrape(url)
        assert result == "https://tracker.com/scrape/123"

    def test_announce_php_to_scrape(self):
        v = TrackerValidator()
        result = v._announce_to_scrape("https://tracker.com/announce.php")
        assert result == "https://tracker.com/scrape.php"

    def test_announce_already_scrape_url(self):
        v = TrackerValidator()
        result = v._announce_to_scrape("https://tracker.com/scrape")
        assert result == "https://tracker.com/scrape"


class TestCacheRealTime:
    """Cache behavior with real timestamps — no mocks."""

    def test_cache_store_and_retrieve(self):
        import time

        v = TrackerValidator()
        result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)
        v._cache["http://t"] = (time.time(), result)
        cached = v.get_cached_result("http://t")
        assert cached is result

    def test_cache_expired_entry_removed(self):
        import time

        v = TrackerValidator()
        result = ScrapeResult(tracker="http://t", status=TrackerStatus.HEALTHY)
        v._cache["http://t"] = (time.time() - 600, result)
        cached = v.get_cached_result("http://t")
        assert cached is None
        assert "http://t" not in v._cache

    def test_cache_multiple_entries(self):
        import time

        v = TrackerValidator()
        r1 = ScrapeResult(tracker="http://a", status=TrackerStatus.HEALTHY)
        r2 = ScrapeResult(tracker="http://b", status=TrackerStatus.OFFLINE)
        now = time.time()
        v._cache["http://a"] = (now, r1)
        v._cache["http://b"] = (now - 600, r2)
        assert v.get_cached_result("http://a") is r1
        assert v.get_cached_result("http://b") is None
        assert "http://b" not in v._cache
