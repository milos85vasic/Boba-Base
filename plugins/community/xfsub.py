# VERSION: 1.0
# AUTHORS: qBittorrent Community

import re
import time
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class xfsub:
    """Xfsub anime subtitle search engine plugin."""

    url = "https://www.xfsub.com"
    name = "Xfsub"
    supported_categories = {"all": "0", "anime": "1"}

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)

        # Build search URL
        search_term = quote(what)
        url = f"{self.url}/search/?keyword={search_term}"

        try:
            html = retrieve_url(url)
            self._parse_results(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _parse_results(self, html):
        """Parse search results from HTML."""
        # Xfsub uses a table format for results
        pattern = re.compile(
            r"<tr[^>]*>.*?"
            r'<td[^>]*>.*?<a[^>]*href="(/torrent/[^"]+)"[^>]*>([^<]+)</a>.*?</td>.*?'
            r"<td[^>]*>([^<]+)</td>.*?"
            r"<td[^>]*>([^<]+)</td>.*?"
            r"<td[^>]*>([^<]+)</td>.*?"
            r"<td[^>]*>([^<]+)</td>.*?"
            r"</tr>",
            re.S | re.I,
        )

        matches = pattern.findall(html)
        for match in matches:
            try:
                desc_link = self.url + match[0]
                name = match[1].strip()
                size = match[2].strip()
                seeds = match[3].strip()
                leech = match[4].strip()
                date_str = match[5].strip()

                # Convert size to bytes
                size_bytes = self._parse_size(size)

                result = {
                    "link": desc_link,
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

            # Look for .torrent download
            torrent_match = re.search(r'href="(/download/[^"]+)"', html)
            if torrent_match:
                torrent_url = self.url + torrent_match.group(1)
                print(torrent_url + " " + url)
                sys.stdout.flush()
                return

        except Exception as e:
            print(f"Download error: {e}", file=sys.stderr)
            sys.exit(1)


# Module reference
xfsub = xfsub

if __name__ == "__main__":
    a = xfsub()
    a.search("naruto", "anime")
