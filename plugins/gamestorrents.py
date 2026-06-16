# VERSION: 1.0
# AUTHORS: qBittorrent Community

import re
import time
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class gamestorrents:
    """GamesTorrents search engine plugin for games."""

    url = "https://www.gamestorrents.app"
    name = "GamesTorrents"
    supported_categories = {"all": "0", "games": "juegos"}

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)
        category = self.supported_categories.get(cat, "0")

        # Build search URL
        search_term = quote(what)
        if category == "0":
            url = f"{self.url}/?s={search_term}"
        else:
            url = f"{self.url}/category/{category}/?s={search_term}"

        try:
            html = retrieve_url(url)
            self._parse_results(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _parse_results(self, html):
        """Parse search results from HTML.

        The live site (verified 2026-06-16 against
        https://www.gamestorrents.app/?s=<query>) renders results in a
        ``<table class="table metalion">`` rather than the old
        ``<article>`` cards. Body row layout (column order from the live
        ``<thead>``): Nombre (``<td><a href=DETAIL>NAME</a></td>``), Fecha
        (DD-MM-YYYY), Tamaño (e.g. ``59.03 GBs``), Version, Genero, Idioma.
        The header row uses ``<th>`` and carries no detail ``<a>``, so it
        is skipped naturally by the per-row anchor match.
        """
        # Iterate every metalion table on the page, then each row inside it.
        for table in re.findall(
            r'<table[^>]*class="[^"]*metalion[^"]*"[^>]*>(.*?)</table>',
            html,
            re.S | re.I,
        ):
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
                # First <td> = Nombre: a detail-page link wrapping the name.
                # The header row has only <th> cells and no such <a>, so it
                # is skipped here. We deliberately key on the FIRST <a> whose
                # href points at a detail page (not the rel="category tag"
                # genre links in a later column).
                name_match = re.search(
                    r"<td[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
                    row,
                    re.S | re.I,
                )
                if not name_match:
                    continue

                desc_link = name_match.group(1).strip()
                name = self._clean_text(name_match.group(2))
                if not name:
                    continue

                # Size is the Tamaño <td>: the first cell whose text matches a
                # size token (e.g. "59.03 GBs" / "0.16 GB" / "512 MB").
                size_match = re.search(
                    r"<td[^>]*>\s*([\d.,]+\s*(?:TB|GB|MB|KB|B)s?)\s*</td>",
                    row,
                    re.I,
                )
                size = size_match.group(1) if size_match else ""
                size_bytes = self._parse_size(size)

                result = {
                    "link": desc_link,
                    "name": name,
                    "size": str(size_bytes),
                    "seeds": "-1",
                    "leech": "-1",
                    "engine_url": self.url,
                    "desc_link": desc_link,
                    "pub_date": str(int(time.time())),
                }
                prettyPrinter(result)

    @staticmethod
    def _clean_text(raw):
        """Strip tags, decode the few HTML entities the site emits, and
        collapse whitespace."""
        text = re.sub(r"<[^>]+>", "", raw)
        text = (
            text.replace("&#8211;", "-")
            .replace("&#8217;", "'")
            .replace("&amp;", "&")
        )
        return re.sub(r"\s+", " ", text).strip()

    def _parse_size(self, size_str):
        """Convert size string to bytes.

        The live site uses both ``GB`` and a plural ``GBs`` (e.g.
        ``59.03 GBs``); extract the numeric part by regex so a trailing
        ``s`` or stray text never corrupts the float() (TB/GB/MB/KB ordered
        before the bare ``B`` so the longer suffixes win).
        """
        size_str = size_str.upper().strip()
        multipliers = (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024), ("B", 1))

        for unit, mult in multipliers:
            if unit in size_str:
                num_match = re.search(r"([\d.,]+)", size_str)
                if not num_match:
                    return 0
                try:
                    num = float(num_match.group(1).replace(",", ""))
                    return int(num * mult)
                except ValueError:
                    return 0
        return 0

    def download_torrent(self, url):
        """Download torrent file or magnet link."""
        import sys

        try:
            html = retrieve_url(url)

            # Look for magnet link
            magnet_match = re.search(r'href="(magnet:\?xt=[^"]+)"', html)
            if magnet_match:
                magnet = magnet_match.group(1)
                print(magnet + " " + url)
                sys.stdout.flush()
                return

            # Look for a .torrent download link. The live detail page (verified
            # 2026-06-16) serves the file from /wp-content/uploads/files/...,
            # NOT /download/...; match any .torrent href and resolve it against
            # the site root. The href may contain literal [ ] ( ) from the
            # title, so percent-quote the path (leaving the URL structure
            # intact) before handing it back.
            torrent_match = re.search(r'href="([^"]+\.torrent)"', html)
            if torrent_match:
                href = torrent_match.group(1)
                if href.startswith("//"):
                    torrent_url = "https:" + href
                elif href.startswith("http"):
                    torrent_url = href
                else:
                    torrent_url = self.url + ("" if href.startswith("/") else "/") + href
                torrent_url = quote(torrent_url, safe=":/?&=%")
                print(torrent_url + " " + url)
                sys.stdout.flush()
                return

        except Exception as e:
            print(f"Download error: {e}", file=sys.stderr)
            sys.exit(1)


# Module reference
gamestorrents = gamestorrents

if __name__ == "__main__":
    a = gamestorrents()
    a.search("witcher", "games")
