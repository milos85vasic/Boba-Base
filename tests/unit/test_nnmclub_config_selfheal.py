"""
Regression: the NNMClub plugin must import even when its config JSON is stale
(missing a newly-added field) — the self-heal path must not crash.

Root cause (reproduced 2026-06-06): BOB-006 added a `password` field to the
plugin's Config dataclass. `_validate_json` iterates ALL Config fields, so any
existing nnmclub.json lacking "Password" now fails validation → __post_init__'s
`except` self-heal runs → it calls `base64.b64decode(ICON)`, but ICON is invalid
base64 (1533 chars) → binascii.Error crashes the import. Every nnmclub import
against a stale/lagging JSON (test fixtures, the runtime engines/ copy) then
breaks.

§11.4.43 RED-first: against the pre-fix plugin, importing with a stale JSON
raises binascii.Error. After guarding the self-heal it imports cleanly (the
JSON self-heals; the cosmetic icon write is skipped on failure).
"""

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NNMCLUB_SRC = _REPO_ROOT / "plugins" / "nnmclub.py"


def _stub_framework(monkeypatch):
    np = types.ModuleType("novaprinter")
    np.prettyPrinter = lambda d: None
    hp = types.ModuleType("helpers")
    hp.retrieve_url = lambda *a, **k: ""
    hp.download_file = lambda *a, **k: ""
    monkeypatch.setitem(sys.modules, "novaprinter", np)
    monkeypatch.setitem(sys.modules, "helpers", hp)


def _load_with_json(tmp_path, monkeypatch, config_json: dict):
    _stub_framework(monkeypatch)
    d = Path(tempfile.mkdtemp(dir=tmp_path))
    (d / "nnmclub.py").write_text(_NNMCLUB_SRC.read_text())
    (d / "nnmclub.json").write_text(json.dumps(config_json))
    monkeypatch.syspath_prepend(str(d))
    spec = importlib.util.spec_from_file_location(f"nnmclub_{d.name}", d / "nnmclub.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, d


_STALE_JSON = {  # legacy schema — no "Password"
    "username": "U",
    "cookies": "C",
    "proxy": False,
    "proxies": {"http": "", "https": ""},
    "ua": "x",
}


def test_nnmclub_imports_with_stale_json(tmp_path, monkeypatch):
    mod, _ = _load_with_json(tmp_path, monkeypatch, dict(_STALE_JSON))
    # Constructing Config triggers __post_init__'s validate→self-heal path.
    cfg = mod.Config()
    assert cfg is not None  # did not crash on the invalid ICON


def test_nnmclub_selfheal_rewrites_config(tmp_path, monkeypatch):
    mod, d = _load_with_json(tmp_path, monkeypatch, dict(_STALE_JSON))
    mod.Config()
    # JSON self-healed: rewritten with the full current schema (incl. password).
    healed = json.loads((d / "nnmclub.json").read_text())
    assert "password" in healed
