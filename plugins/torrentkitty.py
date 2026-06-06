# VERSION: 1.0
# AUTHORS: qBittorrent Community

import re
import time
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class torrentkitty:
    """TorrentKitty search engine plugin."""

    url = "https://www.torrentkitty.tv"
    name = "TorrentKitty"
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
        # TorrentKitty uses a table format
        pattern = re.compile(
            r"<tr[^>]*>.*?"
            r'<td[^>]*class="name"[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*class="size"[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*class="date"[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*class="action"[^>]*>.*?<a[^>]*href="(magnet:\?xt=[^"]+)"[^>]*>.*?</td>.*?'
            r"</tr>",
            re.S | re.I,
        )

        matches = pattern.findall(html)
        for match in matches:
            try:
                name = match[0].strip()
                size = match[1].strip()
                date_str = match[2].strip()
                magnet = match[3]

                # Convert size to bytes
                size_bytes = self._parse_size(size)

                result = {
                    "link": magnet,
                    "name": name,
                    "size": str(size_bytes),
                    "seeds": "0",
                    "leech": "0",
                    "engine_url": self.url,
                    "desc_link": magnet,
                    "pub_date": str(int(time.time())),
                }
                prettyPrinter(result)
            except Exception as e:
                continue

    def _parse_size(self, size_str):
        """Convert size string to bytes."""
        size_str = size_str.upper().strip()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}

        # Check longest units first and match on the SUFFIX: "B" is a substring
        # of KB/MB/GB/TB, so the old `if unit in size_str` (dict order, "B"
        # first) treated every "X GB" as plain bytes and fell through to 0 —
        # i.e. every realistically-sized result reported size 0.
        for unit, mult in sorted(multipliers.items(), key=lambda kv: -len(kv[0])):
            if size_str.endswith(unit):
                try:
                    num = float(size_str[: -len(unit)].replace(",", "").strip())
                    return int(num * mult)
                except (ValueError, TypeError):
                    return 0
        return 0

    def download_torrent(self, url):
        """TorrentKitty returns magnet links directly."""
        import sys

        print(url + " " + url)
        sys.stdout.flush()


# Module reference
torrentkitty = torrentkitty

if __name__ == "__main__":
    a = torrentkitty()
    a.search("ubuntu", "all")
