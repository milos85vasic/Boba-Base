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
                # §11.4.252(3): a per-row parse failure must NOT abort the whole
                # search, but it must NOT be silent either — the previous
                # `continue` swallowed every row error, so a site-layout change
                # rendered as a quietly short result set with no reason anywhere.
                # stderr, NOT stdout: nova3 parses plugin STDOUT, so a diagnostic
                # printed there would corrupt the result stream it explains.
                print(f"Row parse error: {e}", file=__import__("sys").stderr)
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
                except ValueError as e:
                    # §11.4.252: narrowed from a bare `except:`, which also caught
                    # KeyboardInterrupt and SystemExit — so Ctrl-C or an interpreter
                    # shutdown inside this loop was silently converted into a bogus
                    # "size 0" result instead of terminating. float() on a non-numeric
                    # size token is the ONLY real failure here, and it raises ValueError.
                    # Not silent either: an unparseable size still renders as a 0-byte
                    # torrent in the WebUI, so its reason must be recoverable somewhere.
                    # stderr, NOT stdout: nova3 parses plugin STDOUT (novaprinter writes
                    # the result stream to raw fd 1), so a diagnostic printed there would
                    # corrupt the very results it explains.
                    print(f"Size parse error ({size_str!r}): {e}", file=__import__("sys").stderr)
                    return 0
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
