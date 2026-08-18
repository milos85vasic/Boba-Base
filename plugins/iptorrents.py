# VERSION: 2.00
# AUTHORS: txtsd (thexerothermicsclerodermoid@gmail.com), enhanced for qBitTorrent fork
# Changelog: env var credentials, freeleech detection, [free] tag in results

import gzip
import io
import logging
import os
import re
import tempfile
import urllib.request as request
from http.cookiejar import CookieJar
from urllib.error import URLError
from urllib.parse import urlencode, quote

from helpers import htmlentitydecode
from novaprinter import prettyPrinter

logger = logging.getLogger(__name__)


class iptorrents(object):
    url = "https://iptorrents.com"
    name = "IPTorrents"
    supported_categories = {
        "all": "",
        "movies": "72",
        "tv": "73",
        "music": "75",
        "games": "74",
        "anime": "60",
        "software": "1",
        "pictures": "36",
        "books": "35",
    }

    def __init__(self):
        self.ua = "Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0"
        self.session = None
        self._load_credentials()
        self._login()

    def _load_credentials(self):
        self.username = os.environ.get("IPTORRENTS_USERNAME", "") or os.environ.get("IPTORRENTS_USER", "")
        self.password = os.environ.get("IPTORRENTS_PASSWORD", "") or os.environ.get("IPTORRENTS_PASS", "")
        self._load_env_file()

    def _load_env_file(self):
        if self.username and self.password:
            return
        try:
            from env_loader import load_env_files

            load_env_files()
            self.username = os.environ.get("IPTORRENTS_USERNAME", "") or os.environ.get("IPTORRENTS_USER", "")
            self.password = os.environ.get("IPTORRENTS_PASSWORD", "") or os.environ.get("IPTORRENTS_PASS", "")
        except ImportError:
            for env_path in [
                os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
                os.path.expanduser("~/.qbit.env"),
            ]:
                env_path = os.path.normpath(env_path)
                if not os.path.isfile(env_path):
                    continue
                try:
                    with open(env_path) as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k == "IPTORRENTS_USERNAME" and not self.username:
                                self.username = v
                            elif k == "IPTORRENTS_PASSWORD" and not self.password:
                                self.password = v
                except Exception:
                    pass

    def _login(self):
        if not self.username or not self.password:
            logger.warning("IPTorrents: No credentials configured")
            return
        cj = CookieJar()
        params = {"username": self.username, "password": self.password}
        session = request.build_opener(request.HTTPCookieProcessor(cj))
        session.addheaders.pop()
        session.addheaders.append(("User-Agent", self.ua))
        session.addheaders.append(("Referrer", self.url + "/login.php"))
        try:
            session.open(self.url + "/do-login.php", urlencode(params).encode("utf-8"))
            self.session = session
        except URLError as e:
            logger.error(f"IPTorrents login failed: {e}")

    def _get_link(self, link):
        if not self.session:
            return ""
        try:
            res = self.session.open(link)
        except URLError as e:
            logger.error(f"IPTorrents fetch error: {e}")
            return ""
        charset = "utf-8"
        info = res.info()
        ct = info.get("Content-Type", "")
        if "charset=" in ct:
            _, charset = ct.split("charset=")
        raw = res.read()
        # IPTorrents always sends gzip-encoded bodies (content-encoding: gzip)
        # regardless of whether a matching Accept-Encoding was requested.
        # Without this, the "decoded" text is still compressed binary and
        # every downstream regex (table/row/seed/leech) silently fails to
        # match, producing zero or garbage results (BOB-083).
        if raw[:2] == b"\x1f\x8b":
            with (
                io.BytesIO(raw) as compressed_stream,
                gzip.GzipFile(fileobj=compressed_stream) as gzipper,
            ):
                raw = gzipper.read()
        data = raw.decode(charset, "replace")
        data = htmlentitydecode(data)
        return data

    def search_parse(self, link, page=1):
        data = self._get_link(link + "&p=" + str(page))
        if not data:
            return
        # IPTorrents now renders the results table as `<table id="torrents" ...>`
        # (quoted attribute) directly inside `<form>...`. The previous regex
        # required the unquoted `<table id=torrents` form and never matched
        # current markup, so search_parse() silently returned zero results.
        _tor_table = re.search(r'<form>(<table id="torrents".+?)</form>', data, re.S)
        if not _tor_table:
            return
        tor_table = _tor_table.groups()[0]

        # Current row markup no longer carries a `/details/...` desc-link
        # prefix, nor `t_seeders`/`t_leechers` CSS classes on the seed/leech
        # cells -- those classes were removed entirely. The trailing three
        # bare `<td>N` cells before `</tr>` are, in column order per the
        # table's own <thead>, Snatches, Seeders, Leechers -- captured here
        # by position rather than by (now-absent) class name (BOB-083).
        row_pattern = re.compile(
            r'<a class=" hv" href="(?P<desc_link>/t/\d+)">(?P<name>.+?)</a>'
            r'.*?<td><a href="(?P<link>/download\.php/[^"]+)"'
            r'.*?<td>(?P<size>[^<]+)<td>'
            r'.*?<td>\d+<td>(?P<seeds>\d+)<td>(?P<leech>\d+)</tr>',
            re.S,
        )

        for result in row_pattern.finditer(tor_table):
            is_freeleech = bool(re.search(r'<span\s+class="free"[^>]*>.*?</span>', result.group(0), re.I))

            name = result.group("name")
            tracker_tag = "IPTorrents"
            if is_freeleech:
                tracker_tag = "IPTorrents [free]"

            entry = {
                "link": self.url + quote(result.group("link")),
                "name": name,
                "size": result.group("size"),
                "seeds": result.group("seeds"),
                "leech": result.group("leech"),
                "engine_url": self.url,
                "desc_link": self.url + result.group("desc_link"),
            }
            prettyPrinter(entry)

        _num_pages = re.search(r"<a>Page <b>(\d+)</b> of <b>(\d+)</b>", data)
        if _num_pages:
            cur, total = _num_pages.groups()
            if int(cur) < int(total):
                self.search_parse(link, int(cur) + 1)

    def search_freeleech(self, what, cat="all"):
        # `what` MUST be URL-encoded: a literal space (or other reserved
        # character) in the raw query string trips Python 3.14's stricter
        # http.client path validation ("URL can't contain control
        # characters") and the search request never leaves this process.
        what = quote(what)
        if cat == "all":
            url = f"{self.url}/t?q={what}&o=seeders&free=on"
        else:
            url = f"{self.url}/t?{self.supported_categories[cat]}=&q={what}&o=seeders&free=on"
        self.search_parse(url)

    def download_torrent(self, info):
        if not self.session:
            return
        file, path = tempfile.mkstemp(".torrent")
        try:
            res = self.session.open(info)
        except URLError as e:
            logger.error(f"IPTorrents download error: {e}")
            return
        data = res.read()
        if data[:2] == b"\x1f\x8b":
            compressedstream = io.BytesIO(data)
            gzipper = gzip.GzipFile(fileobj=compressedstream)
            data = gzipper.read()
        with open(file, "wb") as f:
            f.write(data)
        print(path + " " + info)

    def search(self, what, cat="all"):
        what = quote(what)
        if cat == "all":
            url = f"{self.url}/t?q={what}&o=seeders"
        else:
            url = f"{self.url}/t?{self.supported_categories[cat]}=&q={what}&o=seeders"
        self.search_parse(url)


if __name__ == "__main__":
    engine = iptorrents()
    engine.search("ubuntu")
