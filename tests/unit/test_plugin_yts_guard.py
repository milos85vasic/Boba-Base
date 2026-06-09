import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PLUGINS_PATH = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_PATH not in sys.path:
    sys.path.insert(0, _PLUGINS_PATH)

import pytest


class TestYtsJsonGuard:
    def test_empty_response_returns_empty(self, monkeypatch):
        from yts import yts as YtsPlugin

        monkeypatch.setattr("yts.retrieve_url", lambda url: "")
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_invalid_json_returns_empty(self, monkeypatch):
        from yts import yts as YtsPlugin

        monkeypatch.setattr("yts.retrieve_url", lambda url: "not json at all {{{")
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_valid_json_no_movies_returns_empty(self, monkeypatch):
        from yts import yts as YtsPlugin

        response = json.dumps({"data": {"movie_count": 0, "movies": []}})
        monkeypatch.setattr("yts.retrieve_url", lambda url: response)
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_valid_json_with_movies_returns_results(self, monkeypatch):
        from yts import yts as YtsPlugin

        response = json.dumps({
            "data": {
                "movie_count": 1,
                "page_number": 1,
                "limit": 20,
                "movies": [
                    {
                        "title": "Test Movie",
                        "year": "2024",
                        "rating": "8.0",
                        "genres": ["Action"],
                        "url": "https://yts.lt/movie/test",
                        "torrents": [
                            {
                                "hash": "abc123def456",
                                "quality": "1080p",
                                "size": "1.5 GB",
                                "seeds": 100,
                                "peers": 50,
                            }
                        ],
                    }
                ],
            }
        })
        monkeypatch.setattr("yts.retrieve_url", lambda url: response)
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert len(results) == 1
        assert "Test Movie" in results[0]["name"]

    def test_html_response_returns_empty(self, monkeypatch):
        from yts import yts as YtsPlugin

        monkeypatch.setattr("yts.retrieve_url", lambda url: "<html><body>Error 502</body></html>")
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_partial_json_returns_empty(self, monkeypatch):
        from yts import yts as YtsPlugin

        monkeypatch.setattr("yts.retrieve_url", lambda url: '{"data":')
        plugin = YtsPlugin()
        results = []
        monkeypatch.setattr("yts.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []
