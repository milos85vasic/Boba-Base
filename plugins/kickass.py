# VERSION: 1.2
# AUTHORS: LightDestory (https://github.com/LightDestory) and Snake

import re
from time import sleep
from helpers import retrieve_url
from novaprinter import prettyPrinter


class kickass(object):
    url = "https://kickasstorrents.to/"
    name = "Kickasstorrents"

    # Hard cap on search-result pagination. A misbehaving / interstitial /
    # index-ignoring upstream that re-serves matching rows for every page
    # index would make the search loop run forever (compounded by the
    # per-row sleep). Real result sets are far under this bound.
    MAX_PAGES: int = 50

    supported_categories = {
        "all": "",
        "movies": "movies",
        "tv": "tv",
        "music": "music",
        "games": "games",
        "anime": "anime",
        "software": "apps",
    }

    class HTMLParser:
        def __init__(self, url):
            self.url = url
            self.noTorrents = False

        def feed(self, html):
            self.noTorrents = False
            torrents = self.__findTorrents(html)
            if len(torrents) == 0:
                self.noTorrents = True
                return

        def __findTorrents(self, html):
            # Find all TR nodes with class odd or even
            trs = re.findall(r"<tr class=\"(?:odd|even)\"\s*>.*?</tr>", html, re.DOTALL)
            for tr in trs:
                url_titles = re.search(
                    r'<div class="torrentname">.*?<a href="([^"]+)"\s+class="cellMainLink">\s*(.*?)\s*</a>.*?<td[^>]*>\s*([\d,\.]+\s*(?:TB|GB|MB|KB))\s*</td>.*?<td class="green center">\s*(\d+)\s*</td>.*?<td class="red lasttd center">\s*(\d+)\s*</td>',
                    tr,
                    re.DOTALL,
                )
                if url_titles:
                    detail_link = "{0}{1}".format(self.url, url_titles.group(1))
                    download_link = self.__retrieve_download_link(detail_link)
                    data = {
                        "link": download_link,
                        "name": url_titles.group(2),
                        "size": url_titles.group(3).replace(",", ""),
                        "seeds": url_titles.group(4).replace(",", ""),
                        "leech": url_titles.group(5).replace(",", ""),
                        "engine_url": self.url,
                        "desc_link": detail_link,
                    }
                    prettyPrinter(data)
                    sleep(1)
            return trs

        def __retrieve_download_link(self, detail_link):
            try:
                torrent_page = retrieve_url(detail_link)
            except Exception:
                return "NotFound"
            if not torrent_page:
                return "NotFound"
            magnet_match = re.search(r"\"(magnet:.*?)\"", torrent_page)
            if magnet_match and magnet_match.groups():
                return str(magnet_match.groups()[0])
            else:
                return "NotFound"

    def download_torrent(self, url):
        if not url or not isinstance(url, str):
            # Degenerate input (None / empty / non-string): there is no
            # usable URL to resolve. Emit the qBittorrent-expected
            # "<url> <engine_url>" fallback shape instead of crashing.
            print("{0} {1}".format(url or "", self.url))
            return
        if url.startswith("magnet:"):
            print(url + " " + self.url)
            return
        try:
            data = retrieve_url(url)
        except Exception:
            print(url + " " + self.url)
            return
        if not data:
            print(url + " " + self.url)
            return
        magnet_match = re.search(r'(magnet:\?[^"<\s]+)', data)
        if magnet_match:
            print(magnet_match.group(1) + " " + self.url)
        else:
            print(url + " " + self.url)

    def search(self, what, cat="all"):
        # The query goes into the URL path. The merge service passes a raw
        # query with literal spaces; nova2 passes a %20-encoded one. Encode
        # a raw space to %20 so it never reaches urllib (which rejects it).
        what = what.replace(" ", "%20")
        parser = self.HTMLParser(self.url)
        category = "" if cat == "all" else "category/{0}/".format(self.supported_categories[cat])
        counter: int = 0
        while counter < self.MAX_PAGES:
            url = "{0}search/{1}/{2}{3}/".format(self.url, what, category, counter)
            try:
                html = retrieve_url(url)
            except Exception:
                break
            if not html:
                break
            html = re.sub("<strong[^>]*>|</strong>", "", html)
            parser.feed(html)
            if parser.noTorrents:
                break
            counter += 1
