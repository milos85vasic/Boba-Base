# VERSION: 2.0
# AUTHORS: qBittorrent Community

import json
import time
from urllib.parse import quote

from helpers import retrieve_url
from novaprinter import prettyPrinter


class anilibra:
    """AniLibria anime torrent search engine plugin."""

    url = "https://anilibria.top"
    name = "AniLibria"
    supported_categories = {"all": "0", "anime": "1"}

    def search(self, what, cat="all"):
        """Search for torrents."""
        search_term = quote(what)
        search_url = f"{self.url}/api/v1/app/search/releases?query={search_term}&limit=20"

        try:
            html = retrieve_url(search_url)
            releases = json.loads(html)
            if not isinstance(releases, list):
                return

            for release in releases:
                self._process_release(release)
        except Exception as e:
            print(f"Search error: {e}", file=__import__("sys").stderr)

    def _process_release(self, release):
        """Fetch torrents for a release and print results."""
        release_id = release.get("id")
        if not release_id:
            return

        name_ru = release.get("name", {}).get("main", "Unknown")
        name_en = release.get("name", {}).get("english", "")
        display_name = name_en if name_en else name_ru

        torrents_url = f"{self.url}/api/v1/anime/torrents/release/{release_id}"
        try:
            html = retrieve_url(torrents_url)
            torrents = json.loads(html)
            if not isinstance(torrents, list):
                return

            for torrent in torrents:
                magnet = torrent.get("magnet", "")
                if not magnet:
                    continue

                size = torrent.get("size", 0)
                seeders = torrent.get("seeders", 0)
                leechers = torrent.get("leechers", 0)
                label = torrent.get("label", display_name)
                torrent_id = torrent.get("id", "")
                desc_link = f"{self.url}/anime/releases/{release_id}"

                result = {
                    "link": magnet,
                    "name": label,
                    "size": str(size),
                    "seeds": str(seeders),
                    "leech": str(leechers),
                    "engine_url": self.url,
                    "desc_link": desc_link,
                    "pub_date": str(int(time.time())),
                }
                prettyPrinter(result)
        except Exception as e:
            # §11.4.252(3): search() already reports its own failures on stderr
            # (see above); this handler used to swallow every per-release
            # network/JSON failure, so a fully-broken torrents endpoint rendered
            # as a silent empty result set with no reason. Same stderr idiom as
            # search(); non-fatal so one bad release cannot abort the whole run.
            print(f"Release {release_id} error: {e}", file=__import__("sys").stderr)

    def download_torrent(self, url):
        """AniLibria returns magnet links directly."""
        import sys

        print(url + " " + url)
        sys.stdout.flush()


anilibra = anilibra

if __name__ == "__main__":
    a = anilibra()
    a.search("naruto", "all")
