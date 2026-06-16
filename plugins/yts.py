#!/usr/bin/env python3
# VERSION: 4.3
# AUTHORS: Khen Solomon Lethil
import json
import re
import math

try:
    from urllib.parse import urlencode, unquote, quote_plus, quote
    # from html.parser import HTMLParser
except ImportError:
    from urllib import urlencode, unquote, quote_plus, quote
    # from HTMLParser import HTMLParser

# local
from novaprinter import prettyPrinter
from helpers import retrieve_url


class yts(object):
    url = "https://yts.lt"
    name = "YTS"
    supported_categories = {"all": "All", "movies": "Movie"}

    def download_torrent(self, url):
        """Download torrent - returns magnet link directly."""
        import sys

        print(url + " " + url)
        sys.stdout.flush()

    def search(self, keyword, cat="all"):
        job = score()
        params = job.paramBuilder(unquote(keyword))
        url = job.urlBuilder(self.url, ["api", "v2", "list_movies.json"], params)
        data = retrieve_url(url)
        try:
            j = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(j, dict):
            return
        j_data = j.get("data")
        if not isinstance(j_data, dict):
            j_data = {}
        if j_data.get("movie_count") and "movies" in j_data:
            page_of = "{}of{}".format(
                j["data"]["page_number"], int(math.ceil(int(j["data"]["movie_count"]) / int(j["data"]["limit"])))
            )
            for movies in j["data"]["movies"]:
                for torrent in movies["torrents"]:
                    res = {
                        "link": job.magnetBuilder(torrent["hash"], movies["title"]),
                        "name": "{n} ({y}) [{q}]-[{p}]-[{i}]".format(
                            n=movies["title"], y=movies["year"], q=torrent["quality"], p=page_of, i=self.name
                        ),
                        "size": torrent["size"],
                        "seeds": torrent["seeds"],
                        "leech": torrent["peers"],
                        "engine_url": "IMDB:{rating}, [{genres}]".format(
                            rating=movies["rating"], genres=", ".join(movies["genres"])
                        ),
                        "desc_link": movies["url"],
                    }
                    job.done(res)
        elif job.supported_browse_params:
            url_params = job.supported_browse_params
            # §11.4.146: the query_term lands in a URL PATH segment here (the
            # browse-movies route), NOT the urlencode'd list_movies.json query
            # param above — so percent-encode each segment (quote, safe="" =>
            # %20 for space + UTF-8 %XX for non-ASCII; '+' is wrong in a path).
            # paramBuilder already unquote'd the query, so this never double-encodes.
            url_path = list(
                map(lambda i: quote(str(i in params and params[i] or url_params[i]), safe=""), url_params)
            )
            url = job.urlBuilder(self.url, url_path, "page" in params and {"page": params["page"]})
            data = retrieve_url(url)
            data = re.sub(r"\s\s+", "", data).replace("\n", "").replace("\r", "")
            data_container = re.findall(
                r'<div class="browse-content"><div class="container">.*?<section><div class="row">(.*?)</div></section>.*?</div></div>',
                data,
            )
            if data_container and data_container[0]:
                page_of = re.findall(r'<li class="pagination-bordered">(.*?)</li>', data)[0]  # 1 of 5
                page_of = page_of and re.sub(r" +", "", page_of).strip() or "?"
                data_movie = re.findall('<div class=".?browse-movie-wrap.*?">.*?</div></div></div>', data_container[0])
                for hM in data_movie:
                    movie_link = re.findall(r'<a href="(.*?)" class="browse-movie-link">.*?</a>', hM)[0]
                    response_detail = retrieve_url(movie_link)
                    response_detail = re.sub(r"\s\s+", "", response_detail).replace("\n", "").replace("\r", "")
                    movie_id = re.findall(r'data-movie-id="(\d+)"', response_detail)[0]
                    if movie_id:
                        url = job.urlBuilder(self.url, ["api", "v2", "movie_details.json"], {"movie_id": movie_id})
                        data_detail = retrieve_url(url)
                        try:
                            j = json.loads(data_detail)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        movies = j.get("data", {}).get("movie", {})
                        if not movies:
                            continue
                        for torrent in movies["torrents"]:
                            res = {
                                "link": job.magnetBuilder(torrent["hash"], movies["title"]),
                                "name": "{n} ({y}) [{q}]-[{p}]-[{i}]".format(
                                    n=movies["title"],
                                    y=movies["year"],
                                    q=torrent["quality"],
                                    p=page_of,
                                    i=self.name[:-1],
                                ),
                                "size": torrent["size"],
                                "seeds": torrent["seeds"],
                                "leech": torrent["peers"],
                                "engine_url": "IMDB:{rating}, [{genres}]".format(
                                    rating=movies["rating"], genres=", ".join(movies["genres"])
                                ),
                                "desc_link": movies["url"],
                            }
                            job.done(res)
                        else:
                            # Fallback: Extract movie details from browse page HTML when API doesn't return results
                            # This handles cases where the movie exists in browse but not in direct API
                            movie_title = re.findall('<a.*?class="browse-movie-title".*?>(.*?)</a>', hM)[0]
                            movie_year = re.findall('<div.?class="browse-movie-year".*?>(.*?)</div>', hM)[0]
                            movie_rate = re.findall('<h4.?class="rating".*?>(.*?)</h4>', hM)[0]
                            movie_rate = movie_rate.split("/")[0]
                            movie_genre = re.findall('<figcaption class=".*?">.*?(<h4>.*</h4>).*?</figcaption>', hM)[0]
                            movie_genre = re.findall("<h4>(.*?)</h4>", movie_genre)
                            # print(movie_title,movie_link,movie_year,movie_rate,movie_genre)
                            job.done()
            else:
                # NOTE: No match found
                job.done()
        else:
            # NOTE: not supported browsing
            job.done()


class score(object):
    supported_browse_params = {
        "browse": "browse-movies",
        "query_term": "0",
        "quality": "all",
        "genre": "all",
        "minimum_rating": "0",
        "sort_by": "latest",
    }
    default_params = {
        "genre": {"x": r"(term=\w+[\s+|$]?)"},
        "quality": {"x": r"(term=\w+[\s+|$]?)"},
        "minimum_rating": {"x": r"(term=?[0-9]*[.]?[0-9]+[\s+|$]?)"},
        "sort_by": {"x": r"(term=\w+[\s+|$]?)"},
        "order_by": {"x": r"(term=\w+[\s+|$]?)"},
        "with_rt_ratings": {"x": r"(term=\w+[\s+|$]?)"},
        "page": {"x": r"(term=\w+[\s+|$]?)", "value": "1"},
        "limit": {"x": r"(term=.*[\s+|$]?)", "value": "1"},
        "query_term": {"x": r"(term=.*[\s+|$]?)", "value": "%%"},
    }

    tracker = [
        "udp://open.demonii.com:1337/announce",
        "udp://tracker.openbittorrent.com:80",
        "udp://tracker.coppersurfer.tk:6969",
        "udp://glotorrents.pw:6969/announce",
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://torrent.gresille.org:80/announce",
        "udp://p4p.arenabg.com:1337",
        "udp://tracker.leechers-paradise.org:6969",
    ]

    def magnetBuilder(self, hash, name):
        return "magnet:?xt=urn:btih:{}&{}&{}".format(
            hash, urlencode({"dn": name}), "&".join(map(lambda x: "tr=" + quote_plus(x.strip()), self.tracker))
        )

    def urlBuilder(self, url, uri=[], param={}):
        for r in uri:
            url = "{}/{}".format(url, r)
        if param:
            url = "{}?{}".format(url, urlencode(param))
        return url

    def paramBuilder(self, query_term):
        params = {}
        for name in self.default_params:
            o = self.default_params[name]
            regex = o["x"].replace("term", name)
            val = re.findall(regex, query_term)
            if len(val):
                query_term = re.sub(regex, "", query_term)
                val = re.findall("=(.*)", val[0])[0].strip()
                if "value" in o and val != o["value"]:
                    """ limit > 1, page > 1, query_term != '%%' """
                    params[name] = val
                else:
                    params[name] = val
            else:
                """ default value, if required """
        query_term = re.sub(" +", " ", query_term).strip()
        if query_term:
            if query_term != self.default_params["query_term"]["value"]:
                params["query_term"] = query_term  # quote_plus(query_term)
        return params

    def done(self, res={}):
        if res:
            # print(res['name'])
            prettyPrinter(res)
        else:
            """ None """


if __name__ == "__main__":
    """ debug """
    y = yts()
    y.search("ubuntu")
