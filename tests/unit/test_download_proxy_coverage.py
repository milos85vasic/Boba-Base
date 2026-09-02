import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PATH = REPO_ROOT / "plugins" / "download_proxy.py"


def _load_download_proxy():
    stubs = {}
    for mod_name in ("novaprinter", "helpers"):
        if mod_name not in sys.modules:
            stub = type(sys)("_stub_" + mod_name)
            stub.print = lambda *a, **kw: None
            sys.modules[mod_name] = stub
            stubs[mod_name] = stub
    spec = importlib.util.spec_from_file_location("download_proxy_cov", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_proxy_cov"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dp():
    return _load_download_proxy()


class TestIdentifyPlugin:
    def test_rutracker_org(self, dp):
        assert dp.identify_plugin("https://rutracker.org/forum/t123.html") == "rutracker"

    def test_rutracker_net(self, dp):
        assert dp.identify_plugin("https://rutracker.net/forum/t123.html") == "rutracker"

    def test_rutracker_nl(self, dp):
        assert dp.identify_plugin("https://rutracker.nl/forum/t123.html") == "rutracker"

    def test_kinozal_tv(self, dp):
        assert dp.identify_plugin("https://kinozal.tv/details.php?id=123") == "kinozal"

    def test_kinozal_me(self, dp):
        assert dp.identify_plugin("https://kinozal.me/details.php?id=123") == "kinozal"

    def test_nnmclub_to(self, dp):
        assert dp.identify_plugin("https://nnmclub.to/forum/viewtopic.php?t=1") == "nnmclub"

    def test_nnmclub_me(self, dp):
        assert dp.identify_plugin("https://nnmclub.to/forum/viewtopic.php?t=1") == "nnmclub"

    def test_iptorrents_com(self, dp):
        assert dp.identify_plugin("https://iptorrents.com/torrents/12345") == "iptorrents"

    def test_iptorrents_me(self, dp):
        assert dp.identify_plugin("https://iptorrents.me/torrents/12345") == "iptorrents"

    def test_iptorrents_org(self, dp):
        assert dp.identify_plugin("https://iptorrents.org/torrents/12345") == "iptorrents"

    def test_unknown_url(self, dp):
        assert dp.identify_plugin("https://example.com/torrent/123") is None

    def test_empty_string(self, dp):
        assert dp.identify_plugin("") is None

    def test_case_insensitive(self, dp):
        assert dp.identify_plugin("https://RUTRACKER.ORG/forum/1") == "rutracker"

    def test_partial_match_not_enough(self, dp):
        assert dp.identify_plugin("https://example.com/nottracker") is None

    def test_in_url_path(self, dp):
        assert dp.identify_plugin("https://proxy.example.com/redirect?to=rutracker.org") == "rutracker"


class TestPluginPatternsStructure:
    """RECONCILED 2026-09-01 (§11.4.120).

    ``PLUGIN_PATTERNS`` / ``COMPILED_PATTERNS`` were this module's private copy
    of the private-tracker roster, and it had drifted from the three other
    copies (it uniquely carried ``kinozal.me`` / ``iptorrents.org`` and
    uniquely lacked ``kinozal.guru`` / ``nnmclub.ro``). The roster now lives
    once, in ``merge_service.trackers``, so these gates would fail-by-absence
    on a mechanism that is deliberately gone. They are rewritten to assert the
    replacement mechanism rather than fake-passed or deleted: the module
    resolves the SHARED roster, and every tracker in it is matchable through
    this module's own entry point.
    """

    def test_module_resolves_the_shared_roster(self, dp):
        names = dp._supported_tracker_names()
        assert sorted(names) == ["iptorrents", "kinozal", "nnmclub", "rutracker"]

    def test_every_roster_domain_matches_through_this_module(self, dp):
        from merge_service.trackers import PRIVATE_TRACKER_DOMAINS

        assert dp._resolve_tracker_matcher() is not None
        for plugin, domains in PRIVATE_TRACKER_DOMAINS.items():
            assert len(domains) >= 1
            for domain in domains:
                assert isinstance(domain, str)
                assert dp.identify_plugin(f"https://{domain}/download.php?id=1") == plugin, domain
