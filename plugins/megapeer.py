# VERSION: 1.1
# AUTHORS: qBittorrent Community

import re
import time
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class megapeer:
    """MegaPeer Russian torrent tracker plugin."""

    url = "https://megapeer.vip"
    name = "MegaPeer"
    supported_categories = {
        "all": "0",
        "movies": "1",
        "tv": "4",
        "music": "2",
        "games": "7",
        "software": "8",
        "books": "11",
    }

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)

        # Build search URL
        search_term = quote(what)
        url = f"{self.url}/browse.php?search={search_term}"

        try:
            html = retrieve_url(url)
            self._parse_results(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _parse_results(self, html):
        """Parse search results from HTML."""
        pattern = re.compile(
            r'<tr[^>]*class="table_fon"[^>]*>.*?'
            r'<td[^>]*>([^<]+)</td>.*?'
            r'<a[^>]*href="(/download/\d+)"[^>]*>.*?</a>.*?'
            r'<a[^>]*href="(/torrent/[^"]+)"[^>]*class="url"[^>]*>([^<]+)</a>.*?'
            r'<td[^>]*align="right"[^>]*>([^<]+)</td>.*?'
            r'<font[^>]*color="#[0-9a-fA-F]+"[^>]*>(\d+)</font>.*?'
            r'<font[^>]*color="#[0-9a-fA-F]+"[^>]*>(\d+)</font>.*?'
            r'</tr>',
            re.S | re.I,
        )

        matches = pattern.findall(html)
        for match in matches:
            try:
                date_str = match[0].strip()
                download_link = self.url + match[1]
                desc_link = self.url + match[2]
                name = match[3].strip()
                size = match[4].strip()
                seeds = match[5].strip()
                leech = match[6].strip()

                size_bytes = self._parse_size(size)

                result = {
                    "link": download_link,
                    "name": name,
                    "size": str(size_bytes),
                    "seeds": seeds,
                    "leech": leech,
                    "engine_url": self.url,
                    "desc_link": desc_link,
                    "pub_date": str(int(time.time())),
                }
                prettyPrinter(result)
            except Exception:
                continue

    def _parse_size(self, size_str):
        """Convert size string to bytes."""
        size_str = size_str.upper().strip()
        multipliers = {"TB": 1024**4, "GB": 1024**3, "MB": 1024**2, "KB": 1024, "B": 1}

        for unit, mult in multipliers.items():
            if unit in size_str:
                try:
                    num = float(size_str.replace(unit, "").replace(",", "").strip())
                    return int(num * mult)
                except Exception:
                    return 0
        return 0

    def download_torrent(self, url):
        """Download torrent file or magnet link."""
        import sys

        try:
            print(url + " " + url)
            sys.stdout.flush()
        except Exception as e:
            print(f"Download error: {e}", file=sys.stderr)


megapeer = megapeer

if __name__ == "__main__":
    a = megapeer()
    a.search("ubuntu", "all")
