"""fail-open triage 2026-08-20 — §11.4.252 fail-open regression guards (RED-first per §11.4.43/§11.4.224).

Guards the eight bucket-(A) fail-open sites triaged in ``triage.md``:

    plugins/env_loader.py:30      except Exception: pass   (credential env mutation)
    plugins/iptorrents.py:77      except Exception: pass   (credential file read)
    plugins/rutor.py:303          bare except:             (eats its own ValueError)
    plugins/rutor.py:324          bare except:             (BaseException in cleanup)
    plugins/rutracker.py:349      bare except:             (eats its own ValueError)
    plugins/rutracker.py:370      bare except:             (BaseException in cleanup)
    plugins/helpers.py:220        except Exception: pass   (network failure == "no magnet")
    plugins/anilibra.py:75        except Exception: pass   (silent zero results)

ORACLE STRATEGY (§11.4.245): **INVARIANT**.  The oracle is the anchor's own
clause-(3) rule — "a dangerous-capability path that cannot complete MUST emit
captured evidence naming the unresolved precondition; it MUST NEVER silently
proceed" — asserted against *user-observable* output (stderr text, the raised
exception's message, the returned value), never against the implementation's
own agreement with itself.  Independent of the code under test: the expected
value comes from the constitution, not from re-running the function.

BOTH POLARITIES (§11.4.201(1)): every failure-path test that demands a refusal
is paired with a normal-path test proving the feature still works and that no
spurious diagnostic is emitted.  A fix that breaks plugin loading is worse than
the bug it fixes.

Self-contained: installs its own ``novaprinter`` / ``helpers`` stubs and
snapshots ``sys.modules`` + ``os.environ``, so it runs standalone
(``pytest docs/qa/fail-open-triage-20260820/``) without tests/conftest.py.
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import types
from contextlib import redirect_stderr, redirect_stdout, suppress

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")

_POLLUTES = ("env_loader", "helpers", "novaprinter", "socks", "anilibra", "rutor", "rutracker", "iptorrents")


@pytest.fixture(autouse=True)
def _isolate():
    """Snapshot/restore sys.modules + sys.path + os.environ around every test."""
    saved_mods = {k: sys.modules.get(k) for k in _POLLUTES}
    saved_path = list(sys.path)
    saved_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(saved_env)
    sys.path[:] = saved_path
    for k, v in saved_mods.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _load(name: str, *, retrieve_url=None, captured=None):
    """Load a plugin module by path with the nova3 sibling modules stubbed."""
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: (captured if captured is not None else []).append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = retrieve_url or (lambda url, *a, **k: "[]")
    helpers_mod.download_file = lambda *a, **k: ""
    helpers_mod.htmlentitydecode = lambda s: s
    sys.modules["helpers"] = helpers_mod

    if PLUGINS_DIR not in sys.path:
        sys.path.insert(0, PLUGINS_DIR)
    sys.modules.pop(name, None)
    path = os.path.join(PLUGINS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── A1 — plugins/env_loader.py:30 ────────────────────────────────────────────
# Capabilities combined: CREDENTIAL ACCESS (.env holds tracker creds) +
# MUTATION of shared process state (os.environ) + UNTRUSTED INPUT (parsed file).


def test_a1_env_loader_unreadable_file_emits_diagnostic():
    """FAILURE POLARITY: a .env that cannot be fully read must say so."""
    env_mod = _load("env_loader")
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".env", delete=False) as f:
        # Valid first line, then a byte sequence that is not valid UTF-8, so
        # iteration raises UnicodeDecodeError *after* line 1 was applied.
        f.write(b"BOB144_FIRST=applied\nBOB144_SECOND=\xff\xfe\xfd not-utf8\n")
        path = f.name
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            env_mod.load_env_files(path)
        err = buf.getvalue()
        # The fail-open is that the .env silently did not take effect: the
        # credential keys it carries are simply absent, and a downstream
        # "credentials not configured" warning then misnames a CORRUPT file as
        # an ABSENT one. (Python decodes a whole buffered chunk on the first
        # `for line in f`, so this particular failure aborts before any key is
        # applied -- all-or-nothing, not partial.) §11.4.252(3) demands the
        # reason be emitted either way.
        assert os.environ.get("BOB144_SECOND") is None, "corrupt line must not be applied"
        assert err.strip(), "env_loader swallowed the read failure with no diagnostic (§11.4.252)"
        assert path in err or "env" in err.lower()
    finally:
        os.unlink(path)


def test_a1_env_loader_normal_path_still_loads_and_is_quiet():
    """NORMAL POLARITY: a good .env still loads, and emits no diagnostic."""
    env_mod = _load("env_loader")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("BOB144_OK=yes\n# comment\nBOB144_TWO=two\n")
        path = f.name
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            env_mod.load_env_files(path)
        assert os.environ.get("BOB144_OK") == "yes"
        assert os.environ.get("BOB144_TWO") == "two"
        assert buf.getvalue().strip() == "", "spurious diagnostic on the healthy path (§11.4.201(1))"
    finally:
        os.unlink(path)


def test_a1_env_loader_missing_file_is_not_an_error():
    """NORMAL POLARITY: an absent optional .env is a designed condition, not a failure."""
    env_mod = _load("env_loader")
    buf = io.StringIO()
    with redirect_stderr(buf):
        env_mod.load_env_files(os.path.join(tempfile.gettempdir(), "bob144-does-not-exist.env"))
    assert buf.getvalue().strip() == "", "absent optional .env must not emit a diagnostic (§11.4.201(1))"


# ── A2 — plugins/iptorrents.py:77 ────────────────────────────────────────────
# Capabilities combined: CREDENTIAL ACCESS + UNTRUSTED INPUT (parsed file).


def _iptorrents_instance():
    mod = _load("iptorrents")
    cls = getattr(mod, "iptorrents", None) or mod.IPTorrents
    inst = cls.__new__(cls)
    inst.username = ""
    inst.password = ""
    inst.session = None
    return mod, inst


def test_a2_iptorrents_unreadable_credentials_file_emits_diagnostic(monkeypatch, caplog):
    """FAILURE POLARITY: an unreadable credentials file must name the reason."""
    mod, inst = _iptorrents_instance()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".env", delete=False) as f:
        f.write(b"IPTORRENTS_USERNAME=\xff\xfe not-utf8\n")
        path = f.name
    try:
        # Force the ImportError branch (no env_loader) and point it at our file.
        monkeypatch.setitem(sys.modules, "env_loader", None)
        buf = io.StringIO()
        with caplog.at_level("WARNING"), redirect_stderr(buf):
            _run_iptorrents_fallback(mod, inst, path)
        surfaced = buf.getvalue() + "\n".join(r.getMessage() for r in caplog.records)
        assert surfaced.strip(), "iptorrents swallowed the credential-file read failure (§11.4.252)"
    finally:
        os.unlink(path)


def test_a2_iptorrents_good_credentials_file_still_loads(monkeypatch, caplog):
    """NORMAL POLARITY: a valid credentials file still populates username/password."""
    mod, inst = _iptorrents_instance()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("IPTORRENTS_USERNAME=bob\nIPTORRENTS_PASSWORD=secret\n")
        path = f.name
    try:
        buf = io.StringIO()
        with caplog.at_level("WARNING"), redirect_stderr(buf):
            _run_iptorrents_fallback(mod, inst, path)
        assert inst.username == "bob"
        assert inst.password == "secret"  # noqa: S105 - fixture, not a real secret
        surfaced = buf.getvalue() + "\n".join(r.getMessage() for r in caplog.records)
        assert surfaced.strip() == "", "spurious diagnostic on the healthy path (§11.4.201(1))"
    finally:
        os.unlink(path)


def _run_iptorrents_fallback(mod, inst, env_path):
    """Drive iptorrents' real ImportError-fallback credential reader at env_path."""
    import unittest.mock as _m

    with _m.patch.object(os.path, "isfile", lambda p: p == env_path), _m.patch.object(
        os.path, "normpath", lambda p: env_path
    ), _m.patch.dict(sys.modules, {"env_loader": None}):
        inst._load_env_file()


def _read_guarded_block(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── A3/A5 — plugins/rutor.py:303, plugins/rutracker.py:349 ───────────────────
# The bare `except:` swallows the ValueError the code raises two lines above,
# destroying the operator-actionable "session expired / not logged in" signal.


@pytest.mark.parametrize(
    ("plugin", "payload"),
    [
        ("rutor", b"<html><body>Login required</body></html>"),
        ("rutracker", b"<!DOCTYPE html><html>Login required</html>"),
    ],
)
def test_a3_html_instead_of_torrent_surfaces_the_specific_reason(plugin, payload, monkeypatch):
    """FAILURE POLARITY: an HTML page must be reported AS an HTML page."""
    src = _read_guarded_block(os.path.join(PLUGINS_DIR, f"{plugin}.py"))
    # The specific message must reach the caller, not be replaced by the
    # generic one because a bare `except:` ate it.
    assert "Received HTML page instead of torrent file" in src
    reason = _raise_reason_for_html(plugin, payload)
    assert "HTML" in reason, (
        f"{plugin}: the specific 'Received HTML page' reason was swallowed by a bare "
        f"except: and replaced with {reason!r} (§11.4.252(3))"
    )


def _raise_reason_for_html(plugin: str, payload: bytes) -> str:
    """Drive the REAL download path with the network stubbed; return the message.

    No source slicing: the plugin's own method is invoked, so the assertion is
    on the user-observable failure the operator would actually receive
    (§11.4.199 — use the real sequence, not an approximation).
    """
    import unittest.mock as _m

    mod = _load(plugin)
    if plugin == "rutor":
        cls, method, stub = mod.Rutor, "_download_torrent", "_request"
    else:
        cls, method, stub = mod.RuTracker, "download_torrent", "_open_url"

    inst = cls.__new__(cls)
    made = []
    real_mkstemp = tempfile.mkstemp

    def _tracking_mkstemp(*a, **k):
        fd, path = real_mkstemp(*a, **k)
        made.append(path)
        return fd, path

    try:
        with _m.patch.object(cls, stub, lambda self, *a, **k: payload), _m.patch.object(
            tempfile, "mkstemp", _tracking_mkstemp
        ):
            getattr(inst, method)("https://example.test/dl.php?t=1")
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"<{type(exc).__name__}: {exc}>"
    finally:
        for pth in made:
            with suppress(OSError):
                os.unlink(pth)
    return "<no exception raised>"


@pytest.mark.parametrize("plugin", ["rutor", "rutracker"])
def test_a3_valid_bencode_payload_is_not_rejected(plugin):
    """NORMAL POLARITY: a real torrent payload must pass the branch untouched."""
    reason = _raise_reason_for_html(plugin, b"d8:announce30:http://tracker.example/announcee")
    assert reason == "<no exception raised>", f"{plugin}: valid bencode wrongly rejected: {reason}"


@pytest.mark.parametrize("plugin", ["rutor", "rutracker"])
def test_a3_non_html_garbage_still_reports_the_generic_reason(plugin):
    """NORMAL POLARITY: non-HTML garbage keeps the generic message (no over-fix)."""
    reason = _raise_reason_for_html(plugin, b"\x00\x01\x02 not a torrent")
    assert "not a valid torrent file" in reason


# ── A4/A6 — bare `except:` anywhere in the owned (A) files ───────────────────
# A bare except catches KeyboardInterrupt/SystemExit; in a credentialed
# download path that means Ctrl-C during cleanup is silently discarded.

_OWNED_A_FILES = ["rutor.py", "rutracker.py", "env_loader.py", "iptorrents.py", "helpers.py", "anilibra.py"]


@pytest.mark.parametrize("fname", _OWNED_A_FILES)
def test_a4_no_bare_except_in_owned_first_party_plugins(fname):
    """STRUCTURAL INVARIANT: no unnarrowed `except:` in boba-owned plugin code."""
    path = os.path.join(PLUGINS_DIR, fname)
    offenders = [
        (n, ln.rstrip())
        for n, ln in enumerate(_read_guarded_block(path).splitlines(), 1)
        if ln.strip() == "except:"
    ]
    assert not offenders, (
        f"{fname}: bare `except:` catches BaseException (KeyboardInterrupt/SystemExit) "
        f"at line(s) {[n for n, _ in offenders]} (§11.4.252)"
    )


# ── A7 — plugins/helpers.py:220 fetch_magnet_from_page ───────────────────────
# Capabilities combined: EXTERNAL SIDE EFFECT (network fetch) + UNTRUSTED INPUT.
# A network failure returns "" — indistinguishable from "the page has no magnet".


def test_a7_fetch_magnet_network_failure_emits_diagnostic():
    """FAILURE POLARITY: a fetch failure must be distinguishable from 'not found'."""

    def _boom(url, *a, **k):
        raise OSError("connection refused")

    helpers = _load_real_helpers(retrieve_url=_boom)
    buf = io.StringIO()
    with redirect_stderr(buf):
        got = helpers.fetch_magnet_from_page("https://example.invalid/x")
    assert got == "", "contract preserved: still returns empty string"
    assert buf.getvalue().strip(), (
        "fetch_magnet_from_page swallowed the fetch failure; a network error is "
        "reported identically to 'no magnet on the page' (§11.4.252(3))"
    )


def test_a7_fetch_magnet_success_returns_magnet_quietly():
    """NORMAL POLARITY: a page containing a magnet still yields it, silently."""
    magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=demo"
    helpers = _load_real_helpers(retrieve_url=lambda url, *a, **k: f"<a href='{magnet}'>dl</a>")
    buf = io.StringIO()
    with redirect_stderr(buf):
        got = helpers.fetch_magnet_from_page("https://example.test/x")
    assert got.startswith("magnet:?xt=urn:btih:")
    assert buf.getvalue().strip() == "", "spurious diagnostic on the healthy path (§11.4.201(1))"


def test_a7_fetch_magnet_page_without_magnet_is_quiet():
    """NORMAL POLARITY: a genuinely magnet-free page returns '' with no diagnostic."""
    helpers = _load_real_helpers(retrieve_url=lambda url, *a, **k: "<html>no links here</html>")
    buf = io.StringIO()
    with redirect_stderr(buf):
        got = helpers.fetch_magnet_from_page("https://example.test/x")
    assert got == ""
    assert buf.getvalue().strip() == "", "'not found' is not a failure and must stay quiet (§11.4.201(1))"


def _load_real_helpers(retrieve_url):
    """Load the REAL plugins/helpers.py, then swap its retrieve_url binding."""
    sys.modules.setdefault("socks", types.ModuleType("socks"))
    if PLUGINS_DIR not in sys.path:
        sys.path.insert(0, PLUGINS_DIR)
    sys.modules.pop("helpers", None)
    spec = importlib.util.spec_from_file_location("helpers", os.path.join(PLUGINS_DIR, "helpers.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["helpers"] = mod
    spec.loader.exec_module(mod)
    mod.retrieve_url = retrieve_url
    return mod


# ── A8 — plugins/anilibra.py:75 _process_release ─────────────────────────────
# Capabilities combined: EXTERNAL SIDE EFFECT (network) + UNTRUSTED INPUT (JSON).


def test_a8_anilibra_release_fetch_failure_emits_diagnostic():
    """FAILURE POLARITY: a per-release fetch failure must not be silent."""
    calls = {"n": 0}

    def _retrieve(url, *a, **k):
        calls["n"] += 1
        if "search/releases" in url:
            return '[{"id": 42, "name": {"main": "Demo", "english": "Demo"}}]'
        raise OSError("connection refused")

    captured: list = []
    mod = _load("anilibra", retrieve_url=_retrieve, captured=captured)
    inst = mod.anilibra()
    buf = io.StringIO()
    with redirect_stderr(buf):
        inst.search("demo")
    assert captured == [], "no results expected when the torrents endpoint fails"
    assert buf.getvalue().strip(), (
        "anilibra._process_release swallowed the fetch failure — the user sees "
        "zero results with no reason (§11.4.252(3))"
    )


def test_a8_anilibra_happy_path_still_prints_results_quietly():
    """NORMAL POLARITY: a healthy API still yields results, with no diagnostic."""
    magnet = "magnet:?xt=urn:btih:" + "b" * 40

    def _retrieve(url, *a, **k):
        if "search/releases" in url:
            return '[{"id": 7, "name": {"main": "Демо", "english": "Demo"}}]'
        return (
            '[{"magnet": "' + magnet + '", "size": 123, "seeders": 5, '
            '"leechers": 1, "label": "Demo 1080p", "id": "t1"}]'
        )

    captured: list = []
    mod = _load("anilibra", retrieve_url=_retrieve, captured=captured)
    inst = mod.anilibra()
    buf = io.StringIO()
    with redirect_stderr(buf):
        inst.search("demo")
    assert len(captured) == 1, f"expected one printed result, got {captured}"
    assert captured[0]["link"] == magnet
    assert buf.getvalue().strip() == "", "spurious diagnostic on the healthy path (§11.4.201(1))"


# ── Contract guard: the fixes must not break the nova3 plugin contract ───────


@pytest.mark.parametrize("name", ["rutor", "rutracker", "anilibra", "iptorrents"])
def test_nova3_contract_preserved(name):
    """A fix that breaks plugin loading is worse than the bug (CLAUDE.md plugin contract)."""
    mod = _load(name)
    cls = None
    for cand in (name, name.capitalize(), name.upper(), "RuTracker", "IPTorrents", "Rutor", "anilibra"):
        cls = getattr(mod, cand, None)
        if isinstance(cls, type):
            break
    assert isinstance(cls, type), f"{name}: nova3 engine class not exported"
    for attr in ("url", "name", "supported_categories"):
        assert hasattr(cls, attr), f"{name}: nova3 contract attribute '{attr}' missing"
    assert callable(getattr(cls, "search", None)), f"{name}: search() missing"
    assert callable(getattr(cls, "download_torrent", None)), f"{name}: download_torrent() missing"


# ── nova3 stream integrity: diagnostics MUST go to stderr, never stdout ──────
# nova3 parses plugin STDOUT to harvest search results. Every diagnostic this
# triage added is a new write; if any of them reached stdout it would corrupt
# the result stream for the end user — a worse defect than the swallow it
# replaced. This guard is the standing proof that they do not.


def test_diagnostics_never_reach_stdout_env_loader():
    """NORMAL+FAILURE: the env_loader diagnostic must not pollute the result stream."""
    env_mod = _load("env_loader")
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".env", delete=False) as f:
        f.write(b"BOB_X=\xff\xfe not-utf8\n")
        path = f.name
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            env_mod.load_env_files(path)
        assert err.getvalue().strip(), "precondition: the diagnostic must fire"
        assert out.getvalue() == "", (
            "env_loader diagnostic leaked to STDOUT — nova3 parses stdout for "
            "search results, so this would corrupt the result stream"
        )
    finally:
        os.unlink(path)


def test_diagnostics_never_reach_stdout_helpers():
    """NORMAL+FAILURE: the fetch_magnet_from_page diagnostic must stay on stderr."""

    def _boom(url, *a, **k):
        raise OSError("connection refused")

    helpers = _load_real_helpers(retrieve_url=_boom)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        got = helpers.fetch_magnet_from_page("https://example.invalid/x")
    assert err.getvalue().strip(), "precondition: the diagnostic must fire"
    assert got == ""
    assert out.getvalue() == "", "helpers diagnostic leaked to STDOUT"


def test_diagnostics_never_reach_stdout_anilibra():
    """NORMAL+FAILURE: the anilibra per-release diagnostic must stay on stderr."""

    def _retrieve(url, *a, **k):
        if "search/releases" in url:
            return '[{"id": 9, "name": {"main": "D", "english": "D"}}]'
        raise OSError("connection refused")

    captured: list = []
    mod = _load("anilibra", retrieve_url=_retrieve, captured=captured)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        mod.anilibra().search("d")
    assert err.getvalue().strip(), "precondition: the diagnostic must fire"
    assert out.getvalue() == "", "anilibra diagnostic leaked to STDOUT"
