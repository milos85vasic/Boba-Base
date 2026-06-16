# VERSION: 4.16
# AUTHORS: Lima66
# CONTRIBUTORS: Diego de las Heras (ngosang@hotmail.es)
# MODIFIED: Returns magnet links in search results for WebUI compatibility

import re
import logging
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Callable, Dict, List, Mapping, Match, Tuple, Union
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from helpers import retrieve_url
from novaprinter import prettyPrinter

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class limetorrents:
    url = "https://www.limetorrents.lol"
    name = "LimeTorrents"
    supported_categories = {
        "all": "all",
        "anime": "anime",
        "software": "applications",
        "games": "games",
        "movies": "movies",
        "music": "music",
        "tv": "tv",
    }

    class MyHtmlParser(HTMLParser):
        """Sub-class for parsing results"""

        def error(self, message: str) -> None:
            pass

        A, TD, TR, HREF = ("a", "td", "tr", "href")

        def __init__(self, url: str) -> None:
            HTMLParser.__init__(self)
            self.url = url
            self.current_item: Dict[str, object] = {}
            self.page_items = 0
            self.inside_table = False
            self.inside_tr = False
            self.column_index = -1
            self.column_name: Union[str, None] = None
            self.columns = ["name", "pub_date", "size", "seeds", "leech"]
            self.results: List[Dict] = []

            now = datetime.now()
            self.date_parsers: Mapping[str, Callable[[Match[str]], datetime]] = {
                r"yesterday": lambda m: now - timedelta(days=1),
                r"last\s+month": lambda m: now - timedelta(days=30),
                r"(\d+)\s+years?": lambda m: now - timedelta(days=int(m[1]) * 365),
                r"(\d+)\s+months?": lambda m: now - timedelta(days=int(m[1]) * 30),
                r"(\d+)\s+days?": lambda m: now - timedelta(days=int(m[1])),
                r"(\d+)\s+hours?": lambda m: now - timedelta(hours=int(m[1])),
                r"(\d+)\s+minutes?": lambda m: now - timedelta(minutes=int(m[1])),
            }

        def handle_starttag(self, tag: str, attrs: List[Tuple[str, Union[str, None]]]) -> None:
            params = dict(attrs)

            if params.get("class") == "table2":
                self.inside_table = True
            elif not self.inside_table:
                return

            if tag == self.TR and (params.get("bgcolor") == "#F4F4F4" or params.get("bgcolor") == "#FFFFFF"):
                self.inside_tr = True
                self.column_index = -1
                self.current_item = {"engine_url": self.url}
            elif not self.inside_tr:
                return

            if tag == self.TD:
                self.column_index += 1
                if self.column_index < len(self.columns):
                    self.column_name = self.columns[self.column_index]
                else:
                    self.column_name = None

            if self.column_name == "name" and tag == self.A and self.HREF in params:
                link = params["href"]
                if link is not None and link.endswith(".html"):
                    desc_link = self.url + link
                    self.current_item["desc_link"] = desc_link
                    self.current_item["_info_link"] = desc_link

        def handle_data(self, data: str) -> None:
            if self.column_name:
                if self.column_name in ["size", "seeds", "leech"]:
                    data = data.replace(",", "")
                elif self.column_name == "pub_date":
                    timestamp = -1
                    for pattern, calc in self.date_parsers.items():
                        m = re.match(pattern, data, re.IGNORECASE)
                        if m:
                            timestamp = int(calc(m).timestamp())
                            break
                    data = str(timestamp)
                self.current_item[self.column_name] = data.strip()
                self.column_name = None

        def handle_endtag(self, tag: str) -> None:
            if tag == "table":
                self.inside_table = False

            if self.inside_tr and tag == self.TR:
                self.inside_tr = False
                self.column_name = None
                if "desc_link" in self.current_item:
                    self.results.append(self.current_item.copy())
                    self.page_items += 1

    def _fetch_url_with_retry(self, url: str, max_retries: int = 3) -> str:
        """Fetch URL with retry logic and proper URL encoding."""
        from urllib.parse import quote

        # Fix URL encoding - spaces and special characters need to be encoded
        # Split URL into parts to encode only the path
        if " " in url or "%20" in url:
            # URL contains spaces, need to fix encoding
            url = url.replace("%20", " ")
            url = quote(url, safe="/:=?&()[]")  # Keep URL structure characters safe

        for attempt in range(max_retries):
            try:
                req = Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
                )
                with urlopen(req, timeout=15) as response:
                    html = response.read().decode("utf-8", errors="ignore")
                    return html
            except (URLError, HTTPError) as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
                if attempt == max_retries - 1:
                    raise
        return ""

    def _fetch_magnet_from_page(self, info_url: str) -> str:
        """Fetch magnet link from info page with multiple extraction methods."""
        try:
            logger.info(f"Fetching magnet from: {info_url}")
            info_page = self._fetch_url_with_retry(info_url)

            # Method 1: Standard magnet link in href
            magnet_patterns = [
                r'href\s*=\s*"(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"]*)"',
                r"href\s*=\s*\'(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^\']*)\'",
                r'"(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"]*)"',
            ]

            for pattern in magnet_patterns:
                magnet_match = re.search(pattern, info_page)
                if magnet_match and magnet_match.groups():
                    magnet = magnet_match.groups()[0]
                    logger.info(f"✅ Found magnet link: {magnet[:80]}...")
                    return magnet

            logger.warning(f"No magnet link found in page: {info_url}")

        except Exception as e:
            logger.error(f"Failed to fetch magnet from {info_url}: {e}")

        return ""

    def search(self, query: str, cat: str = "all") -> None:
        """Performs search and returns magnet links only."""
        # limetorrents uses '-' for spaces in its search PATH. Handle BOTH the
        # %20-encoded (nova2) and raw-space (merge service) caller conventions —
        # the raw-space case was unhandled and crashed urllib on multi-word
        # queries (observed on nezha as plugin_bad_query_encoding).
        query = query.replace("%20", "-").replace(" ", "-")
        category = self.supported_categories[cat]

        for page in range(1, 3):  # Reduced from 5 to 3 pages for speed
            page_url = f"{self.url}/search/{category}/{query}/seeds/{page}/"

            try:
                html = retrieve_url(page_url)
            except Exception as e:
                logger.error(f"Failed to fetch search page {page}: {e}")
                continue

            parser = self.MyHtmlParser(self.url)
            parser.feed(html)
            parser.close()

            logger.info(f"Page {page}: Found {len(parser.results)} results")

            for result in parser.results:
                info_url = result.get("_info_link", "")

                if not info_url:
                    logger.warning("Skipping result: no info link")
                    continue

                # Fetch magnet link
                magnet_link = self._fetch_magnet_from_page(info_url)

                if magnet_link:
                    result["link"] = magnet_link
                    result.pop("_info_link", None)
                    logger.info(f"✅ Returning result with magnet: {result.get('name', 'Unknown')[:50]}")
                    prettyPrinter(result)
                else:
                    # Skip results without magnet links
                    logger.warning(f"Skipping result without magnet: {result.get('name', 'Unknown')[:50]}")
                    continue

            if parser.page_items < 20:
                break

    def download_torrent(self, info: str) -> None:
        """Handle magnet links and .torrent downloads."""
        import sys

        if info.startswith("magnet:"):
            print(info + " " + info)
            sys.stdout.flush()
            return

        # Fallback for HTTP URLs - try to get magnet
        try:
            magnet = self._fetch_magnet_from_page(info)
            if magnet:
                print(magnet + " " + info)
                sys.stdout.flush()
                return
        except Exception as e:
            logger.error(f"Download failed: {e}")

        raise ValueError("Error: Could not find magnet link")
