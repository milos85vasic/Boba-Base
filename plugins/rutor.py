#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rutor.org search engine plugin for qBittorrent with environment variable support."""
# VERSION: 1.18-fixed
# AUTHORS: imDMG [imdmgg@gmail.com]
# MODIFIED: Added environment variable support and fixed download functionality

import os
import sys


def _load_env_file():
    try:
        from env_loader import load_env_files

        load_env_files(
            os.path.join(os.path.dirname(__file__), ".env"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            os.path.expanduser("~/.config/qbittorrent/.env"),
        )
    except ImportError:
        pass


_load_env_file()


def _get_env(key, default=""):
    """Get environment variable with fallback."""
    return os.environ.get(key, default)


def _get_proxy_from_env():
    """Parse proxy from environment variable."""
    http_proxy = _get_env("RUTOR_PROXY_HTTP", _get_env("HTTP_PROXY", ""))
    https_proxy = _get_env("RUTOR_PROXY_HTTPS", _get_env("HTTPS_PROXY", ""))

    if http_proxy or https_proxy:
        return {"http": http_proxy, "https": https_proxy}
    return {"http": "", "https": ""}


class Config:
    use_magnet = _get_env("RUTOR_USE_MAGNET", "true").lower() == "true"
    proxy_enabled = _get_env("RUTOR_PROXY_ENABLED", "false").lower() == "true"
    proxies = _get_proxy_from_env()
    user_agent = _get_env(
        "RUTOR_USER_AGENT",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )


CONFIG = Config()

import base64
import logging
import re
import socket
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import ProxyHandler, build_opener

try:
    import novaprinter
except ImportError:
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location("novaprinter", "nova2.py")
        novaprinter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(novaprinter)
    except FileNotFoundError:
        spec = importlib.util.spec_from_file_location("novaprinter", "../nova2.py")
        novaprinter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(novaprinter)


# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

RE_TORRENTS = re.compile(
    r'(?:gai|tum)"><td>(?P<pub_date>.+?)</td.+?href="(?P<mag_link>magnet:'
    r'.+?)".+?href="/(?P<desc_link>torrent/(?P<tor_id>\d+).+?)">(?P<name>.+?)'
    r'</a.+?right">(?P<size>[.\d]+?&nbsp;\w+?)</td.+?<span.+?(?P<seeds>\d+?)'
    r"</span>.+?<span.+?(?P<leech>\d+?)</span>",
    re.S,
)
RE_RESULTS = re.compile(r"</b>\sРезультатов\sпоиска\s(\d{1,4})\s", re.S)
PATTERNS = ("%ssearch/%i/%i/000/0/%s",)
PAGES = 100


def rng(t: int) -> range:
    return range(1, -(-t // PAGES))


def date_normalize(date_str: str) -> int:
    months = (
        "Янв",
        "Фев",
        "Мар",
        "Апр",
        "Май",
        "Июн",
        "Июл",
        "Авг",
        "Сен",
        "Окт",
        "Ноя",
        "Дек",
    )
    try:
        date_str = [date_str.replace(m, f"{i:02d}") for i, m in enumerate(months, 1) if m in date_str][0]
        return int(time.mktime(time.strptime(date_str, "%d %m %y")))
    except (IndexError, ValueError, OverflowError, OSError):
        # §11.4.252: narrowed from a bare `except:`. The "now" fallback is the
        # intended behaviour for an unparseable tracker date, but the bare form
        # also caught KeyboardInterrupt/SystemExit. IndexError = no month matched,
        # ValueError = strptime mismatch, OverflowError/OSError = mktime range.
        return int(time.time())


class EngineError(Exception):
    pass


class Rutor:
    """Rutor.org search engine plugin for qBittorrent."""

    name = "Rutor"
    url = "https://rutor.info/"
    url_dl = url.replace("//", "//d.") + "download/"
    supported_categories = {
        "all": 0,
        "movies": 1,
        "tv": 6,
        "music": 2,
        "games": 8,
        "anime": 10,
        "software": 9,
        "pictures": 3,
        "books": 11,
    }

    def __init__(self):
        self._init()

    def search(self, what: str, cat: str = "all") -> None:
        """Search for torrents."""
        self._catch_errors(self._search, what, cat)

    def download_torrent(self, url: str) -> None:
        """Download torrent file using authenticated session.

        This method is called by nova2dl.py when downloading torrents.

        Args:
            url: The torrent download URL or magnet link

        Output format (required by qBittorrent):
            <filepath> <url>
        """
        self._catch_errors(self._download_torrent, url)

    def searching(self, query: str, first: bool = False) -> int:
        """Execute search query on single page."""
        try:
            page = self._request(query).decode()
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return 0

        torrents_found = -1

        if first:
            match = RE_RESULTS.search(page)
            if match is None:
                logger.debug(f"Unexpected page content:\n {page}")
                raise EngineError("Unexpected page content")
            torrents_found = int(match[1])
            if torrents_found <= 0:
                return 0

        self.draw(page)
        return torrents_found

    def draw(self, html: str) -> None:
        """Parse and output torrent results."""
        for tor in RE_TORRENTS.finditer(html):
            mag_link = tor.group("mag_link")
            tor_id = tor.group("tor_id")

            # Use magnet link if configured, otherwise use .torrent URL
            if CONFIG.use_magnet:
                link = mag_link
            else:
                link = self.url_dl + tor_id

            novaprinter.prettyPrinter(
                {
                    "link": link,
                    "name": unescape(tor.group("name")),
                    "size": tor.group("size").replace("&nbsp;", " "),
                    "seeds": int(tor.group("seeds")),
                    "leech": int(tor.group("leech")),
                    "engine_url": self.url,
                    "desc_link": self.url + tor.group("desc_link"),
                    "pub_date": date_normalize(unescape(tor.group("pub_date"))),
                }
            )

    def _catch_errors(self, handler, *args):
        """Error handler wrapper."""
        try:
            handler(*args)
        except EngineError as ex:
            logger.exception(ex)
            self.pretty_error(args[0], str(ex))
        except Exception as ex:
            self.pretty_error(args[0], "Unexpected error, please check logs")
            logger.exception(ex)

    def _init(self) -> None:
        """Initialize session with proxy if configured."""
        self.session = build_opener()

        if CONFIG.proxy_enabled:
            if not any(CONFIG.proxies.values()):
                raise EngineError("Proxy enabled, but not set!")

            for proxy_str in CONFIG.proxies.values():
                if not proxy_str.lower().startswith("socks"):
                    continue
                try:
                    import socks

                    url = urlparse(proxy_str)
                    socks.set_default_proxy(
                        socks.PROXY_TYPE_SOCKS5,
                        url.hostname,
                        url.port,
                        True,
                        url.username,
                        url.password,
                    )
                    socket.socket = socks.socksocket
                    break
                except ImportError:
                    pass
            else:
                self.session.add_handler(ProxyHandler(CONFIG.proxies))
            logger.debug("Proxy is set!")

        self.session.addheaders = [("User-Agent", CONFIG.user_agent)]

    def _search(self, what: str, cat: str = "all") -> None:
        """Internal search implementation."""
        query = PATTERNS[0] % (
            self.url,
            0,
            self.supported_categories[cat],
            quote(unquote(what)),
        )

        t0 = time.time()
        total = self.searching(query, True)

        if total > PAGES:
            query = query.replace("h/0", "h/{}")
            qrs = [query.format(x) for x in rng(total)]
            with ThreadPoolExecutor(len(qrs)) as executor:
                executor.map(self.searching, qrs, timeout=30)

        logger.debug(f"--- {time.time() - t0} seconds ---")
        logger.info(f"Found torrents: {total}")

    def _download_torrent(self, url: str) -> None:
        """Download torrent file from URL."""
        logger.info(f"Downloading from: {url}")

        # Handle magnet links
        if url.startswith("magnet:"):
            # For magnet links, we just output the magnet URL directly
            # qBittorrent will handle the magnet link
            print(url + " " + url)
            sys.stdout.flush()
            return

        # Download .torrent file
        response = self._request(url)

        if not response:
            raise ValueError("No data received from URL")

        # Verify this looks like a torrent file
        if not response.startswith(b"d"):
            # §11.4.252(3): the refusal must NAME the unresolved precondition.
            # The former bare `except:` here caught the ValueError raised two
            # lines above, destroying the operator-actionable "you are being
            # served a login page" signal and reporting the generic message
            # instead. decode(errors="ignore") with a valid codec cannot raise,
            # so the guard was both harmful and unnecessary.
            decoded = response.decode("utf-8", errors="ignore")
            if "<html" in decoded.lower():
                raise ValueError("Received HTML page instead of torrent file")
            raise ValueError("Downloaded data is not a valid torrent file")

        file_handle, temp_path = tempfile.mkstemp(suffix=".torrent", prefix="rutor_")

        try:
            with os.fdopen(file_handle, "wb") as f:
                f.write(response)
                f.flush()
                os.fsync(f.fileno())

            os.chmod(temp_path, 0o644)

            logger.info(f"Torrent saved to: {temp_path}")
            print(temp_path + " " + url)
            sys.stdout.flush()

        except Exception as e:
            # §11.4.252 (bucket B after triage): narrowed from a bare `except:`, which
            # also caught KeyboardInterrupt/SystemExit -- a Ctrl-C during cleanup of a
            # credentialed download was silently discarded. The swallow itself is
            # correct here: best-effort cleanup, and the real error re-raises below.
            # Kept ABOVE the handler so the §11.4.252 gate can still SEE this site
            # (a comment between `except` and `pass` blinds its detector).
            try:  # noqa: SIM105
                os.unlink(temp_path)
            except OSError:
                pass
            raise e

    def _request(self, url: str, data=None, repeated: bool = False) -> bytes:
        """Make HTTP request with retry logic."""
        try:
            with self.session.open(url, data, 5) as r:
                if r.geturl().startswith((self.url, self.url_dl)):
                    return r.read()
                raise EngineError(f"{url} is blocked. Try another proxy.")
        except (URLError, HTTPError) as err:
            error = str(err.reason)
            reason = f"{url} is not responding! Maybe it is blocked."
            if "timed out" in error and not repeated:
                logger.debug("Request timed out. Retrying...")
                return self._request(url, data, True)
            if "no host given" in error:
                reason = "Proxy is bad, try another!"
            elif isinstance(err, HTTPError):
                reason = f"Request to {url} failed with status: {err.code}"
            raise EngineError(reason)

    def pretty_error(self, what: str, error: str) -> None:
        """Output error in pretty format."""
        novaprinter.prettyPrinter(
            {
                "engine_url": self.url,
                "desc_link": self.url,
                "name": f"[{unquote(what)}][Error]: {error}",
                "link": self.url + "error",
                "size": "1 TB",
                "seeds": 100,
                "leech": 100,
                "pub_date": int(time.time()),
            }
        )


# Create the engine class reference
rutor = Rutor

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    try:
        logging.info("Testing Rutor plugin...")
        engine = Rutor()

        # Test search
        logging.info("\n[Test] Search for 'ubuntu':")
        engine.search("ubuntu")

        logging.info("\nTest completed successfully!")

    except Exception as e:
        logging.error(f"Test failed: {e}")
        import traceback

        traceback.print_exc()
