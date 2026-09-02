# -*- coding: utf-8 -*-
# VERSION: 1.1
# AUTHORS: Joost Bremmer (toost.b@gmail.com)
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.


try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser
import re
from urllib.parse import quote_plus, unquote_plus

# import qBT modules
try:
    from novaprinter import prettyPrinter
    from helpers import retrieve_url
except ImportError:
    # §11.4.252: narrowed from a bare `except:`, which also caught
    # KeyboardInterrupt and SystemExit — so a Ctrl-C during module import was
    # silently turned into "loaded fine" instead of terminating. These modules
    # are supplied by the qBittorrent nova3 host; ImportError is the ONLY real
    # failure here, and it is the EXPECTED out-of-container condition
    # (§11.4.3 topology-absent), not a swallowed error — so no diagnostic is
    # emitted: it would fire on every unit-test import and be noise, not signal.
    pass


class linuxtracker(object):
    """Class used by qBittorrent to search for torrents"""

    url = "http://linuxtracker.org"
    name = "Linux Tracker"
    # defines which search categories are supported by this search engine
    # and their corresponding id. Possible categories are:
    # 'all', 'movies', 'tv', 'music', 'games', 'anime', 'software', 'pictures',
    # 'books'
    supported_categories = {"all": 0, "software": 0}

    class LinuxSearchParser(HTMLParser):
        """Parses BakaBT browse page for search results and prints them"""

        def __init__(self, res, url):
            try:
                super().__init__()
            except TypeError:
                # See: http://stackoverflow.com/questions/9698614/
                # §11.4.252: narrowed from a bare `except:`. The zero-argument
                # `super()` form is a Python-3 construct; on the Python-2
                # old-style HTMLParser it raises TypeError, which is the ONLY
                # real failure here. No diagnostic: the fallback SUCCEEDS, so
                # nothing is lost or hidden — this is a supported code path,
                # not a swallowed error.
                HTMLParser.__init__(self)
            self.results = res
            self.engine_url = url
            self.curr = None
            self.strong_count = 0
            self.wait_for_data = True

        def handle_starttag(self, tag, attr):
            if tag == "a":
                self.start_a(attr)

        def handle_endtag(self, tag):
            if tag == "strong":
                self.end_strong()

        def start_a(self, attr):
            params = dict(attr)
            if "href" in params and "title" in params and "torrent-details" in params["href"]:
                hit = {"desc_link": self.engine_url + "/" + params["href"]}
                self.curr = hit
                self.wait_for_data = True
            elif "href" in params and "magnet:?" in params["href"]:
                self.curr["link"] = params["href"]
                self.curr["engine_url"] = self.engine_url
                self.results.append(self.curr)
                self.curr = None
            elif "href" in params and "peers" in params["href"]:
                self.wait_for_data = True

        def end_strong(self):
            self.strong_count += 1
            self.wait_for_data = True

        def handle_data(self, data):
            if self.wait_for_data is True:
                # We process the data in order of name, size, seeds, leechers
                if self.strong_count == 0 and self.curr:
                    # Get title
                    self.curr["name"] = data.strip()
                elif self.strong_count == 3 and self.curr:
                    # Get size
                    # Strip all comma's since it screws with
                    # prettyPrinter
                    if "," in data:
                        data = re.sub(",", "", data)
                    self.curr["size"] = data.strip()
                elif self.strong_count == 4 and self.curr:
                    # Get seeds
                    try:
                        self.curr["seeds"] = int(data.strip())
                    except ValueError as e:
                        # §11.4.252: narrowed from a bare `except:`, which also
                        # caught KeyboardInterrupt and SystemExit — so Ctrl-C
                        # mid-parse was silently dropped instead of terminating.
                        # int() on a non-numeric seeds cell is the ONLY real
                        # failure here, and it raises ValueError.
                        # Not silent either: `pass` leaves "seeds" unset, so the
                        # row renders with a wrong/absent count and the previous
                        # bare handler left no trace of why.
                        # stderr, NOT stdout: nova3 parses plugin STDOUT
                        # (novaprinter writes the result stream to raw fd 1), so
                        # a diagnostic printed there would corrupt the results.
                        print(
                            f"Seeds parse error ({data.strip()!r}): {e}",
                            file=__import__("sys").stderr,
                        )
                elif self.strong_count == 5 and self.curr:
                    # Get leechers
                    try:
                        self.curr["leech"] = int(data.strip())
                    except ValueError as e:
                        # §11.4.252: narrowed from a bare `except:`, which also
                        # caught KeyboardInterrupt and SystemExit — so Ctrl-C
                        # mid-parse was silently dropped instead of terminating.
                        # int() on a non-numeric leech cell is the ONLY real
                        # failure here, and it raises ValueError.
                        # Not silent either: `pass` leaves "leech" unset, so the
                        # row renders with a wrong/absent count and the previous
                        # bare handler left no trace of why.
                        # stderr, NOT stdout: nova3 parses plugin STDOUT
                        # (novaprinter writes the result stream to raw fd 1), so
                        # a diagnostic printed there would corrupt the results.
                        print(
                            f"Leech parse error ({data.strip()!r}): {e}",
                            file=__import__("sys").stderr,
                        )
                elif self.strong_count == 6:
                    # Reset strong counter
                    self.strong_count = 0
                self.wait_for_data = False

    def __init__(self):
        """class initialization"""

    def download_torrent(self, info):
        """Retrieve and save url as a temporary file."""

    # DO NOT CHANGE the name and parameters of this function
    # This function will be the one called by nova2.py
    def search(self, what, cat="all"):
        """
        Retreive and parse engine search results by category and query.

        Parameters:
        :param what: a string with the search tokens, already escaped
                     (e.g. "Ubuntu+Linux")
        :param cat:  the name of a search category, see supported_categories.
        """

        # ?search= query param: percent-encode (space -> +, UTF-8 percent-encoded).
        # unquote_plus first decodes the nova2 (%20-encoded) caller so a Cyrillic
        # query is encoded exactly once (no double-encoding); quote_plus then
        # makes the value ASCII-safe so a non-ASCII char never reaches urllib.
        what = quote_plus(unquote_plus(what))
        url = ("{0}/index.php?page=torrents&active=1&order=5&by=2&search={1}").format(self.url, what)

        hits = []
        page = 1
        parser = self.LinuxSearchParser(hits, self.url)
        while True:
            res = retrieve_url(url + "&pages={}".format(page))
            parser.feed(res)
            for each in hits:
                prettyPrinter(each)

            if len(hits) < 15:
                break
            del hits[:]
            page += 1

        parser.close()
