# VERSION: 1.0
# AUTHORS: qBittorrent Community

import re
import time
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class btsow:
    """BTSOW search engine plugin - Magnet link aggregator."""

    url = "https://btsow.motorcycles"
    name = "BTSOW"
    supported_categories = {"all": "0"}

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)

        # Build search URL
        search_term = quote(what)
        url = f"{self.url}/search/{search_term}"

        try:
            html = retrieve_url(url)
            self._parse_results(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _parse_results(self, html):
        """Parse search results from HTML."""
        # BTSOW uses a grid layout with magnet links
        pattern = re.compile(
            r'<div[^>]*class="[^"]*data-list[^"]*"[^>]*>.*?'
            r'<a[^>]*href="(/magnet/[^"]+)"[^>]*>.*?'
            r'<div[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)</div>.*?'
            r'<div[^>]*class="[^"]*size[^"]*"[^>]*>([^<]+)</div>.*?'
            r'<div[^>]*class="[^"]*date[^"]*"[^>]*>([^<]+)</div>.*?'
            r"</div>",
            re.S | re.I,
        )

        matches = pattern.findall(html)
        for match in matches:
            try:
                magnet_path = match[0]
                name = match[1].strip()
                size = match[2].strip()
                date_str = match[3].strip()

                # Convert size to bytes
                size_bytes = self._parse_size(size)

                # Build magnet link from path
                # BTSOW stores hash in the URL path
                hash_match = re.search(r"/magnet/([a-f0-9]{40})", magnet_path, re.I)
                if hash_match:
                    info_hash = hash_match.group(1).upper()
                    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name)}"
                else:
                    magnet = self.url + magnet_path

                result = {
                    "link": magnet,
                    "name": name,
                    "size": str(size_bytes),
                    "seeds": "0",
                    "leech": "0",
                    "engine_url": self.url,
                    "desc_link": self.url + magnet_path,
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
                    continue
        return 0

    def download_torrent(self, url):
        """BTSOW returns magnet links directly."""
        import sys

        # BTSOW already provides magnet links in search results
        print(url + " " + url)
        sys.stdout.flush()


# Module reference
btsow = btsow

if __name__ == "__main__":
    a = btsow()
    a.search("ubuntu", "all")
