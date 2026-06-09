# VERSION: 2.0
# AUTHORS: Unknown (converted from various sources)
# CONTRIBUTORS: qBittorrent Community

import re
import urllib.request
from urllib.parse import quote, unquote
from novaprinter import prettyPrinter
from helpers import retrieve_url


class one337x:
    """1337x torrent search engine plugin."""

    url = "https://1337x.to"
    name = "1337x"
    supported_categories = {
        "all": "All",
        "movies": "Movies",
        "tv": "TV",
        "music": "Music",
        "games": "Games",
        "anime": "Anime",
        "software": "Apps",
        "books": "Documentaries",
    }

    class HTMLParser:
        def __init__(self, url):
            self.url = url
            self.results = []
            self.current = {}
            self.in_table = False
            self.in_row = False
            self.cell_count = 0
            self.in_name = False
            self.in_seeds = False
            self.in_leech = False
            self.in_size = False

        def feed(self, html):
            # Simple regex-based parsing for reliability
            # Find all table rows with torrent data
            row_pattern = re.compile(
                r'<tr[^>]*>.*?<a[^>]*href="(/torrent/[^"]+)"[^>]*>([^<]+)</a>.*?'
                r'<td[^>]*class="coll-2[^"]*"[^>]*>(\d+)</td>.*?'
                r'<td[^>]*class="coll-3[^"]*"[^>]*>(\d+)</td>.*?'
                r'<td[^>]*class="coll-4[^"]*"[^>]*>([^<]+)<.*?'
                r'<td[^>]*class="coll-date[^"]*"[^>]*>([^<]+)<.*?'
                r"</tr>",
                re.S | re.I,
            )

            matches = row_pattern.findall(html)
            for match in matches:
                try:
                    desc_link = self.url + match[0]
                    name = match[1].strip()
                    seeds = match[2]
                    leech = match[3]
                    size = match[4].strip()
                    date = match[5].strip()

                    # Convert size to bytes
                    size_bytes = self._parse_size(size)

                    # Get magnet link from detail page
                    # For performance, we'll construct a magnet hash lookup
                    # In a real implementation, you'd parse the detail page

                    result = {
                        "link": desc_link,  # Will be resolved to magnet on download
                        "name": name,
                        "size": str(size_bytes),
                        "seeds": seeds,
                        "leech": leech,
                        "engine_url": self.url,
                        "desc_link": desc_link,
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

    def search(self, what, cat="all"):
        """Search for torrents."""
        what = unquote(what)
        category = self.supported_categories.get(cat, "All")

        # Build search URL
        search_term = quote(what.replace(" ", "-").lower())
        if category == "All":
            url = f"{self.url}/search/{search_term}/1/"
        else:
            url = f"{self.url}/category-search/{search_term}/{category}/1/"

        try:
            html = retrieve_url(url)
            parser = self.HTMLParser(self.url)
            parser.feed(html)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def download_torrent(self, url):
        """Download torrent file or magnet link."""
        import sys

        try:
            # Fetch the detail page to get magnet link
            html = retrieve_url(url)

            # Look for magnet link
            magnet_match = re.search(r'href="(magnet:\?xt=[^"]+)"', html)
            if magnet_match:
                magnet = magnet_match.group(1)
                print(magnet + " " + url)
                sys.stdout.flush()
                return

            # Look for .torrent download link
            torrent_match = re.search(r'href="(/download/[^"]+)"', html)
            if torrent_match:
                torrent_url = self.url + torrent_match.group(1)
                # Return the URL for qBittorrent to handle
                print(torrent_url + " " + url)
                sys.stdout.flush()
                return

        except Exception as e:
            print(f"Download error: {e}", file=sys.stderr)
            sys.exit(1)


# Module reference
one337x = one337x

if __name__ == "__main__":
    a = one337x()
    a.search("ubuntu", "all")
