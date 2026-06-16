# VERSION: 1.92
# AUTHORS: mauricci
# MODIFIED: Returns magnet links in search results for WebUI compatibility

import re
import logging
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Mapping, Tuple, Union
from urllib.parse import unquote

from helpers import retrieve_url
from novaprinter import prettyPrinter

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class torrentproject:
    url = "https://torrentproject.com.se"
    name = "TorrentProject"
    supported_categories = {"all": "0"}

    class MyHTMLParser(HTMLParser):
        def __init__(self, url: str, parent: "torrentproject") -> None:
            HTMLParser.__init__(self)
            self.url = url
            self.parent = parent
            self.insideResults = False
            self.insideDataDiv = False
            self.pageComplete = False
            self.spanCount = -1
            self.infoMap = {
                "name": 0,
                "torrLink": 0,
                "seeds": 2,
                "leech": 3,
                "pub_date": 4,
                "size": 5,
            }
            self.fullResData: List[object] = []
            self.pageRes: List[object] = []
            self.singleResData = self.get_single_data()

        def get_single_data(self) -> Dict[str, Any]:
            return {
                "name": "-1",
                "seeds": "-1",
                "leech": "-1",
                "size": "-1",
                "link": "-1",
                "desc_link": "-1",
                "engine_url": self.url,
                "pub_date": "-1",
            }

        def handle_starttag(self, tag: str, attrs: List[Tuple[str, Union[str, None]]]) -> None:
            def getStr(d: Mapping[str, Union[str, None]], key: str) -> str:
                value = d.get(key, "")
                return value if value is not None else ""

            attributes = dict(attrs)
            if tag == "div" and "nav" in getStr(attributes, "id"):
                self.pageComplete = True
            if tag == "div" and attributes.get("id", "") == "similarfiles":
                self.insideResults = True
            if tag == "div" and self.insideResults and "gac_bb" not in getStr(attributes, "class"):
                self.insideDataDiv = True
            elif tag == "span" and self.insideDataDiv and "verified" != attributes.get("title", ""):
                self.spanCount += 1
            if self.insideDataDiv and tag == "a" and len(attrs) > 0:
                if self.infoMap["torrLink"] == self.spanCount and "href" in attributes:
                    self.singleResData["_info_link"] = self.url + getStr(attributes, "href")
                if self.infoMap["name"] == self.spanCount and "href" in attributes:
                    self.singleResData["desc_link"] = self.url + getStr(attributes, "href")

        def handle_endtag(self, tag: str) -> None:
            if not self.pageComplete:
                if tag == "div":
                    self.insideDataDiv = False
                    self.spanCount = -1
                    if len(self.singleResData) > 0:
                        if (
                            self.singleResData["name"] != "-1"
                            and self.singleResData["size"] != "-1"
                            and self.singleResData["name"].lower() != "nome"
                        ):
                            if self.singleResData["desc_link"] != "-1" or "_info_link" in self.singleResData:
                                try:
                                    date_string = self.singleResData["pub_date"]
                                    date = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
                                    self.singleResData["pub_date"] = int(date.timestamp())
                                except Exception:
                                    pass

                                info_link = self.singleResData.pop("_info_link", "")
                                magnet_link = ""
                                if info_link:
                                    magnet_link = self.parent._fetch_magnet_from_page(info_link)

                                if magnet_link:
                                    self.singleResData["link"] = magnet_link
                                else:
                                    self.singleResData["link"] = info_link

                                try:
                                    prettyPrinter(self.singleResData)
                                except Exception:
                                    print(self.singleResData)
                                self.pageRes.append(self.singleResData)
                                self.fullResData.append(self.singleResData)
                        self.singleResData = self.get_single_data()

        def handle_data(self, data: str) -> None:
            if self.insideDataDiv:
                for key, val in self.infoMap.items():
                    if self.spanCount == val:
                        curr_key = key
                        if curr_key in self.singleResData and data.strip() != "":
                            if self.singleResData[curr_key] == "-1":
                                self.singleResData[curr_key] = data.strip()
                            elif curr_key != "name":
                                self.singleResData[curr_key] += data.strip()

    def _fetch_magnet_from_page(self, info_url: str) -> str:
        """Fetch magnet link from torrent info page."""
        try:
            html = retrieve_url(info_url)
            m = re.search(r"href=[\'\"].*?(magnet:\?[^\'\"]+)[\'\"]", html)
            if m and m.groups():
                magnet = unquote(m.group(1))
                return magnet
        except Exception as e:
            logger.debug(f"Failed to fetch magnet from {info_url}: {e}")
        return ""

    def search(self, what: str, cat: str = "all") -> None:
        # ?t= query param: '+' encodes a space. Handle BOTH the %20-encoded (nova2)
        # and raw-space (merge service) caller conventions so a literal space
        # never reaches urllib.
        what = what.replace("%20", "+").replace(" ", "+")
        for currPage in range(0, 5):
            url = f"{self.url}/browse?t={what}&p={currPage}"
            html = retrieve_url(url)
            parser = self.MyHTMLParser(self.url, self)
            parser.feed(html)
            parser.close()
            if len(parser.pageRes) < 20:
                break

    def download_torrent(self, info: str) -> None:
        """Handle magnet links and info page downloads."""
        import sys

        if info.startswith("magnet:"):
            print(info + " " + info)
            sys.stdout.flush()
            return

        html = retrieve_url(info)
        m = re.search(r"href=[\'\"].*?(magnet:\?[^\'\"]+)[\'\"]", html)
        if m and m.groups():
            magnet = unquote(m.group(1))
            print(magnet + " " + info)
            sys.stdout.flush()
        else:
            print(f"Error: Could not find magnet link", file=sys.stderr)
