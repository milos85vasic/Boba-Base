"""BOB-217 — plugin_update_automation.py gated a network-fetched,
executable-code write by SYNTAX ONLY.

Docs/Issues.md verbatim:

    "plugin_update_automation downloads executable plugin code from
    third-party personal GitHub repos and gates it with a SYNTAX
    check only -- no signature, no pinned commit, no hash allowlist"

`update_plugin()` combines three dangerous capabilities that
constitution SS11.4.252 (fail-closed-on-dangerous-combination) requires
be gated: UNTRUSTED INPUT (14 URLs, 3 of the 4 repos are third-party
personal GitHub accounts) + MUTATION (writes plugins/<name>.py) +
DEFERRED CODE EXECUTION (qBittorrent executes the written .py as its
search engine). The only pre-fix gate was `compile(content, ...,
"exec")` -- a SYNTAX check. A syntactically valid file is exactly
what a hostile payload is.

This module proves, with real code execution (no mocks -- the
"hostile" file below is executed through `compile()` exactly as the
tool's own validator does, and through a real filesystem write/no-write
assertion), that:

  1. RED (historical proof): the exact pre-fix commit (eb5cfce, the
     tip of `main` at the time this defect was filed and still HEAD
     as this test is authored) accepts a syntactically-valid-but-
     unpinned "hostile" payload and WRITES it to disk. This snapshot
     is pinned to an immutable commit hash, not to "the code on disk
     right now" -- so it keeps proving the historical gap existed
     even after the fix below lands and HEAD moves forward.

  2. GREEN: the current (fixed) `tools/plugin_update_automation.py`
     REFUSES the same hostile payload for the same plugin name,
     names the specific check that failed ("hash mismatch"), and
     does NOT write it to disk.

  3. golden-FALSE (SS11.4.201(1) false-positive guard): a legitimate,
     correctly-pinned update for a DIFFERENT plugin name still
     succeeds -- proving the new gate does not just refuse everything.

  4. A plugin name with genuinely no pin configured is refused with
     an honest "no pin configured" reason, not silently accepted and
     not conflated with "hash mismatch".
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_PATH = REPO_ROOT / "tools" / "plugin_update_automation.py"

# Immutable historical reference: the last commit before this fix, and
# the exact commit whose Issues.md entry (BOB-217) this test file closes.
# Pinning to a commit hash (not "current working tree") means this proof
# of the historical gap survives forever, even after the fix below is
# committed and HEAD moves past it.
PRE_FIX_COMMIT = "eb5cfce"

HOSTILE_PAYLOAD = '''# VERSION: 9.9.9
"""Not a real exploit -- deliberately NOT matching any pinned hash.

Syntactically perfectly valid Python (so compile()-only gating
accepts it). Anything that fails a hash-pin check is sufficient
per the BOB-217 acceptance criteria; this does not need to be a
literal RCE payload to prove the gap.
"""
import novaprinter


class hostile_totally_not_evil(object):
    url = "http://example.invalid"
    name = "hostile"
    supported_categories = {"all": "0"}

    def search(self, what, cat="all"):
        novaprinter.prettyPrinter(
            {
                "link": "http://example.invalid/mal.torrent",
                "name": "definitely not malicious",
                "size": "0",
                "seeds": 0,
                "leech": 0,
                "engine_url": self.url,
                "desc_link": self.url,
            }
        )
'''


def _load_module_from_source(module_name: str, source: str) -> types.ModuleType:
    """Load `source` as a standalone module without touching disk state
    for `tools/plugin_update_automation.py` itself (mirrors the
    importlib.util.spec_from_file_location pattern this repo's own
    tests/unit/_download_proxy_harness.py and
    tests/unit/test_download_proxy_coverage.py already use for
    loading non-package standalone scripts).

    `__file__` is seeded to the real target path (not a synthetic
    string) because the module's own top-level code computes
    `SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))` --
    without a real, existing path here that line raises.
    """
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    module.__dict__["__file__"] = str(TARGET_PATH)
    sys.modules[module_name] = module
    try:
        exec(compile(source, f"<{module_name}>", "exec"), module.__dict__)  # noqa: S102 -- test-only dynamic load of a pinned historical git blob, not untrusted input
    finally:
        sys.modules.pop(module_name, None)
    return module


def _load_current_module() -> types.ModuleType:
    """Load the CURRENT (working-tree) tools/plugin_update_automation.py
    -- this is the file this fix edits. Pre-fix it is vulnerable;
    post-fix it is not."""
    spec = importlib.util.spec_from_file_location("plugin_update_automation_current", TARGET_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_pre_fix_module() -> types.ModuleType:
    """Load the tool exactly as it existed at the immutable pre-fix
    commit `PRE_FIX_COMMIT`, regardless of what the working tree now
    contains. This is the RED/historical-proof fixture."""
    source = subprocess.run(
        ["git", "show", f"{PRE_FIX_COMMIT}:tools/plugin_update_automation.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return _load_module_from_source("plugin_update_automation_pre_fix", source)


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    d = tmp_path / "plugins"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# 1. RED / historical proof: the pre-fix commit is genuinely vulnerable.
# ---------------------------------------------------------------------------


def test_prefix_commit_accepts_hostile_payload_via_syntax_check_alone(plugins_dir: Path) -> None:
    """Historical proof the reported gap was real: at the immutable
    pre-fix commit, `_validate_plugin()` is a bare `compile()` syntax
    check, so a syntactically-valid hostile payload is accepted and
    WRITTEN to disk as `plugins/eztv.py` -- the exact file qBittorrent
    would subsequently import and execute as a search engine."""
    pre_fix = _load_pre_fix_module()

    # Confirm the syntax-only gate itself: the hostile payload compiles.
    manager = pre_fix.PluginUpdateManager(str(plugins_dir))
    assert manager._validate_plugin(HOSTILE_PAYLOAD) is True, (
        "sanity check: the hostile payload must be syntactically valid "
        "Python for this test to demonstrate the syntax-only gap"
    )

    # And with NOTHING else standing in the way, the pre-fix tool
    # actually installs it.
    result = manager.update_plugin("eztv", HOSTILE_PAYLOAD, dry_run=False)

    assert result["status"] == "success", (
        "pre-fix update_plugin() was expected to accept the hostile "
        f"payload on syntax-check alone; got {result!r}"
    )
    written_path = plugins_dir / "eztv.py"
    assert written_path.is_file(), "pre-fix code must have written the hostile payload to disk"
    assert written_path.read_text(encoding="utf-8") == HOSTILE_PAYLOAD


# ---------------------------------------------------------------------------
# 2. GREEN: the fixed tool refuses the same payload.
# ---------------------------------------------------------------------------


def test_current_code_refuses_hostile_unpinned_payload(plugins_dir: Path) -> None:
    """The fixed tool MUST refuse a syntactically-valid but
    hash-mismatched payload for a plugin that DOES have a pin
    configured, and MUST name the failing check (hash mismatch) --
    not merely "Validation failed" (which would conflate it with a
    syntax error and hide the real reason from an operator)."""
    current = _load_current_module()

    manager = current.PluginUpdateManager(str(plugins_dir))
    assert "eztv" in manager.pinned_hashes, "eztv must have a real pin configured for this test to be meaningful"

    result = manager.update_plugin("eztv", HOSTILE_PAYLOAD, dry_run=False)

    assert result["status"] == "failed", f"expected refusal for hash-mismatched content, got {result!r}"
    assert "hash mismatch" in result.get("error", "").lower(), (
        f"refusal must name the failing check as a hash mismatch, got: {result.get('error')!r}"
    )
    assert not (plugins_dir / "eztv.py").exists(), "a refused update MUST NOT write anything to disk"


def test_current_code_refuses_plugin_with_no_pin_configured(plugins_dir: Path) -> None:
    """A plugin name that genuinely has no pinned hash at all must be
    refused honestly as "no pin configured" -- never silently
    accepted, and never mis-reported as a hash mismatch (SS11.4.6
    no-guessing: the two failure reasons are observably different
    facts and must not be conflated)."""
    current = _load_current_module()

    manager = current.PluginUpdateManager(str(plugins_dir), pinned_hashes={})

    # Content is syntactically valid AND would even match nothing
    # (there is nothing to match against) -- the absence of a pin is
    # itself the refusal reason, independent of content.
    legitimate_looking = '# VERSION: 1.0.0\nprint("hello")\n'
    result = manager.update_plugin("eztv", legitimate_looking, dry_run=False)

    assert result["status"] == "failed"
    assert "no pin configured" in result.get("error", "").lower(), (
        f"expected an honest 'no pin configured' refusal, got: {result.get('error')!r}"
    )
    assert not (plugins_dir / "eztv.py").exists()


# ---------------------------------------------------------------------------
# 3. golden-FALSE: a legitimate, correctly-pinned update still works.
# ---------------------------------------------------------------------------


def test_current_code_accepts_legitimate_correctly_pinned_content(plugins_dir: Path) -> None:
    """SS11.4.201(1) false-positive guard: the new pinned-hash gate must
    not simply refuse everything. A plugin whose fetched content's
    SHA-256 matches its configured pin MUST be written successfully --
    otherwise the tool can no longer perform its actual job of
    installing reviewed, deliberately-repinned upstream updates."""
    current = _load_current_module()

    legitimate_content = '# VERSION: 2.0.0\n"""A perfectly ordinary, reviewed plugin body."""\n'
    pin = hashlib.sha256(legitimate_content.encode("utf-8")).hexdigest()

    manager = current.PluginUpdateManager(str(plugins_dir), pinned_hashes={"eztv": pin})
    result = manager.update_plugin("eztv", legitimate_content, dry_run=False)

    assert result["status"] == "success", f"a correctly-pinned legitimate update must succeed, got {result!r}"
    written_path = plugins_dir / "eztv.py"
    assert written_path.is_file()
    assert written_path.read_text(encoding="utf-8") == legitimate_content


def test_current_code_dry_run_still_verifies_pin_before_reporting_success(plugins_dir: Path) -> None:
    """A --dry-run must still run the pinned-hash gate (it must not
    report a hostile payload as a dry-run success just because
    nothing gets written) -- an operator previewing updates with
    --dry-run needs an honest signal of what WOULD have happened."""
    current = _load_current_module()

    manager = current.PluginUpdateManager(str(plugins_dir))
    result = manager.update_plugin("eztv", HOSTILE_PAYLOAD, dry_run=True)

    assert result["status"] == "failed", f"dry-run must still refuse a hash-mismatched payload, got {result!r}"
    assert not (plugins_dir / "eztv.py").exists()


# ---------------------------------------------------------------------------
# 4. In-source documentation of the syntax-check-is-not-a-safety-gate note.
# ---------------------------------------------------------------------------


def test_validate_plugin_docstring_documents_it_is_not_a_safety_gate() -> None:
    """Acceptance criterion (3): the `compile()` call in
    `_validate_plugin` must be documented in-source as a SYNTAX check
    that is NOT a safety gate, so nobody reading it in isolation
    mistakes it for the security boundary."""
    current = _load_current_module()

    doc = (current.PluginUpdateManager._validate_plugin.__doc__ or "").lower()
    assert "syntax" in doc, "docstring must call out that this is a syntax-only check"
    assert "not" in doc and ("safety" in doc or "security" in doc), (
        "docstring must explicitly disclaim this as a safety/security gate"
    )


def test_pinned_hashes_registry_covers_every_upstream_source() -> None:
    """Every known upstream URL (constitution SS11.4.270-adjacent:
    dependency-existence verified before adoption) must have a
    corresponding pinned hash -- an upstream source with no pin is
    exactly the silent gap BOB-217 reports. This also guards against
    a future contributor adding a 15th upstream URL and forgetting to
    pin it."""
    current = _load_current_module()

    missing = sorted(set(current.UPSTREAM_SOURCES) - set(current.PLUGIN_PINNED_HASHES))
    assert not missing, f"the following upstream plugins have NO pinned hash configured: {missing}"

    for name, digest in current.PLUGIN_PINNED_HASHES.items():
        assert name in current.UPSTREAM_SOURCES, f"pinned hash for unknown plugin {name!r} (typo?)"
        assert isinstance(digest, str) and len(digest) == 64, (
            f"pinned hash for {name!r} does not look like a sha256 hex digest: {digest!r}"
        )
        int(digest, 16)  # raises ValueError if not valid hex
