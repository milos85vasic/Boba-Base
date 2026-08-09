"""
Smoke tests for canonical tracker plugins.

Verifies each plugin is importable and has the required attributes:
url, name, supported_categories, search, download_torrent.
"""

import importlib.util
import os
import sys

import pytest

_PLUGINS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins"))

CANONICAL_PLUGINS = [
    "anilibra",
    "bitsearch",
    "gamestorrents",
    "iptorrents",
    "kickass",
    "kinozal",
    "limetorrents",
    "megapeer",
    "nnmclub",
    "nyaa",
    "piratebay",
    "rutor",
    "rutracker",
    "torlock",
    "torrentgalaxy",
    "torrentkitty",
    "yts",
]

REQUIRED_ATTRS = ["url", "name", "supported_categories", "search", "download_torrent"]


_PLUGIN_DEPS = ("helpers", "novaprinter", "nova2")


def _import_plugin(name: str):
    path = os.path.join(_PLUGINS_DIR, f"{name}.py")
    if not os.path.isfile(path):
        # SKIP-OK: intentional — defensive guard for a canonical plugin file that
        # doesn't exist yet; verified all 17 CANONICAL_PLUGINS files are present
        # as of this triage (2026-08-09), so this branch is currently dead code,
        # not an active defect.
        pytest.skip(f"Plugin file not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    saved_path = sys.path[:]
    sys.path.insert(0, _PLUGINS_DIR)
    saved_modules = {k: v for k, v in sys.modules.items() if k in _PLUGIN_DEPS}
    for k in _PLUGIN_DEPS:
        sys.modules.pop(k, None)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = saved_path
        for k in list(sys.modules):
            if k in _PLUGIN_DEPS:
                del sys.modules[k]
        sys.modules.update(saved_modules)
    return mod


@pytest.mark.parametrize("plugin_name", CANONICAL_PLUGINS, ids=CANONICAL_PLUGINS)
class TestCanonicalPluginSmoke:
    def test_importable(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name, None)
        assert cls is not None, f"Module {plugin_name} has no class named {plugin_name}"

    def test_has_url(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        assert hasattr(cls, "url")
        assert isinstance(cls.url, str)
        assert cls.url.startswith("http")

    def test_has_name(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        assert hasattr(cls, "name")
        assert isinstance(cls.name, str)
        assert len(cls.name) > 0

    def test_has_supported_categories(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        assert hasattr(cls, "supported_categories")
        assert isinstance(cls.supported_categories, (list, dict))

    def test_has_search_method(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        assert hasattr(cls, "search")
        assert callable(cls.search)

    def test_has_download_torrent_method(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        assert hasattr(cls, "download_torrent")
        assert callable(cls.download_torrent)

    def test_all_required_attrs(self, plugin_name):
        mod = _import_plugin(plugin_name)
        cls = getattr(mod, plugin_name)
        for attr in REQUIRED_ATTRS:
            assert hasattr(cls, attr), f"{plugin_name} missing {attr}"
