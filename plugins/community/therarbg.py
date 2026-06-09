# VERSION: 1.0
# AUTHORS: qBittorrent Community

import re
import time
import json
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class therarbg:
    """TheRarBg - RARBG alternative torrent search engine plugin."""

    url = "https://therarbg.com"
    name = "TheRarBg"
    supported_categories = {
        "all": "0",
        "movies": "movies",
        "tv": "tv",
        "music": "music",
        "games": "games",
        "software": "software",
        "anime": "anime",
        "books": "books",
    }

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)
        category = self.supported_categories.get(cat, "0")

        # Build search URL
        search_term = quote(what)
        if category == "0":
            url = f"{self.url}/search/?search={search_term}&category=0"
        else:
            url = f"{self.url}/search/?search={search_term}&category={category}"

        try:
            html = retrieve_url(url)
            self._parse_results(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _parse_results(self, html):
        """Parse search results from HTML."""
        # TheRarBg uses a table format similar to original RARBG
        pattern = re.compile(
            r'<tr[^>]*class="[^"]*tlist[^"]*"[^>]*>.*?'
            r'<td[^>]*class="[^"]*tlistname[^"]*"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?</td>.*?'
            r'<td[^>]*class="[^"]*tlistdownload[^"]*"[^>]*>.*?<a[^>]*href="(magnet:\?xt=[^"]+)".*?</td>.*?'
            r'<td[^>]*class="[^"]*tlistsize[^"]*"[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*class="[^"]*tlistseeds[^"]*"[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*class="[^"]*tlistleeches[^"]*"[^>]*>([^<]+)</td>.*?'
            r"</tr>",
            re.S | re.I,
        )

        matches = pattern.findall(html)
        for match in matches:
            try:
                desc_link = self.url + match[0]
                name = match[1].strip()
                magnet = match[2]
                size = match[3].strip()
                seeds = match[4].strip()
                leech = match[5].strip()

                # Convert size to bytes
                size_bytes = self._parse_size(size)

                result = {
                    "link": magnet,
                    "name": name,
                    "size": str(size_bytes),
                    "seeds": seeds if seeds.isdigit() else "0",
                    "leech": leech if leech.isdigit() else "0",
                    "engine_url": self.url,
                    "desc_link": desc_link,
                    "pub_date": str(int(time.time())),
                }
                prettyPrinter(result)
            except Exception as e:
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
                except:
                    return 0
        return 0

    def download_torrent(self, url):
        """TheRarBg returns magnet links directly."""
        import sys

        print(url + " " + url)
        sys.stdout.flush()


# Module reference
therarbg = therarbg

if __name__ == "__main__":
    a = therarbg()
    a.search("ubuntu", "software")
