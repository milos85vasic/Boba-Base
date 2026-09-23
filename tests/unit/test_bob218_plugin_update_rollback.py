"""BOB-218 -- three defects in tools/plugin_update_automation.py and its
README, filed in the same session as BOB-217 (already landed; this file
tests the CURRENT, post-BOB-217 state of the tool).

Docs/Issues.md verbatim (BOB-218):

  1. `tools/README.md` claims "the backup is restored" on validation
     failure. `shutil.copy2` in `tools/plugin_update_automation.py`
     copies FORWARD only (making a `.bak` backup before writing) --
     there is no reverse-direction restore. The plugin write opened
     in mode "w", which truncates immediately. A failure part-way
     through the write left a TRUNCATED, NON-IMPORTABLE plugin on
     disk while the operator was told (falsely) that the backup was
     restored.

  2. `tools/README.md` claims the tool's JSON report goes to stdout.
     The code writes it to a file via `open(args.output, "w")` +
     `json.dump()`.

  3. `_extract_version()` used a bare `except:`, silently swallowing
     `KeyboardInterrupt` (Ctrl-C) during the 14-URL upstream sweep --
     a signal-handling defect, since `except:` (and `except
     BaseException:`) catch `KeyboardInterrupt`/`SystemExit`, which
     `except Exception:` deliberately does NOT (both inherit from
     `BaseException`, not `Exception`).

This module proves, with real code execution against the CURRENT
working-tree file (never a pinned historical commit -- unlike
BOB-217, all three of these defects are still live in the tree this
test file is authored against), that:

  (1) A write failure mid-way through updating a plugin leaves the
      PREVIOUS plugin content genuinely INTACT (byte-identical to its
      pre-attempt state) post-fix, and was genuinely TRUNCATED/
      corrupted pre-fix -- the single test
      `test_write_failure_leaves_previous_plugin_content_intact`
      is RED against the pre-fix code (the assertion fails because
      the file is empty/truncated) and GREEN against the post-fix
      code (the assertion passes because the file was never opened
      for writing at all -- only a temp file was, then renamed onto
      the target atomically).

  (2) `tools/README.md` no longer claims the JSON report is written
      to stdout, and the CURRENT code's real behaviour (file, not
      stdout) is directly observed and asserted.

  (3) `KeyboardInterrupt` raised during `_extract_version()` (i.e.
      during the file-read/version-parse it wraps) now propagates
      instead of being silently swallowed.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_PATH = REPO_ROOT / "tools" / "plugin_update_automation.py"
README_PATH = REPO_ROOT / "tools" / "README.md"


def _load_current_module() -> types.ModuleType:
    """Load the CURRENT (working-tree) tools/plugin_update_automation.py
    fresh, mirroring the loader in
    tests/unit/test_bob217_plugin_update_pinned_hash_verification.py so
    each test gets an independent module object with no import-cache
    interference between tests."""
    spec = importlib.util.spec_from_file_location("plugin_update_automation_bob218", TARGET_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    d = tmp_path / "plugins"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Defect 1: no rollback on write failure -> a truncated, non-importable
# plugin file is left on disk, contradicting README's "the backup is
# restored" claim.
# ---------------------------------------------------------------------------


def test_write_failure_leaves_previous_plugin_content_intact(plugins_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-existing plugin content MUST survive a write failure mid-way
    through an update, byte-for-byte, with no data loss.

    RED (pre-fix): `update_plugin()` opens the real target file
    directly in `"w"` mode, which truncates it immediately on open --
    so by the time the injected write failure is raised, the file on
    disk is already corrupted (empty), regardless of any `.bak` that
    was separately created (the README's false claim: the tool never
    reads that `.bak` back).

    GREEN (post-fix): `update_plugin()` writes to a temp file and
    renames it onto the target atomically, so the target is NEVER
    opened for writing in the failure path -- it stays exactly as it
    was.

    The injected failure targets ANY write-mode (`"w"`, exact-match,
    never `"wb"` -- so the binary backup copy via `shutil.copy2` is
    left completely alone) `open()` call whose path lives inside
    `plugins_dir`. This is implementation-agnostic by construction: it
    catches both the pre-fix direct-truncate call and the post-fix
    temp-file call without needing to know which path either one
    uses.
    """
    current = _load_current_module()

    local_path = plugins_dir / "eztv.py"
    original_content = "# VERSION: 1.0.0\nORIGINAL_MARKER_MUST_SURVIVE = True\n"
    local_path.write_text(original_content, encoding="utf-8")

    new_content = '# VERSION: 2.0.0\n"""content that would have replaced the original, if the write had succeeded."""\n'
    pin = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
    manager = current.PluginUpdateManager(str(plugins_dir), pinned_hashes={"eztv": pin})

    real_open = builtins.open
    plugins_dir_str = str(plugins_dir)

    class _FailAfterOpen:
        """Wraps a REAL, already-opened write-mode file. Opening it for
        real is what makes this an honest reproduction of "opens in
        mode w, which truncates immediately" for the pre-fix code path
        -- the truncation genuinely happens on disk via the real
        open() call before `write()` is ever invoked."""

        def __init__(self, real_file) -> None:
            self._real_file = real_file

        def __enter__(self) -> "_FailAfterOpen":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            self._real_file.close()
            return False

        def write(self, _data: str) -> None:
            raise OSError("BOB-218 RED/GREEN test: simulated write failure mid-write")

    def failing_open(path, mode="r", *args, **kwargs):
        if mode == "w" and str(path).startswith(plugins_dir_str):
            real_file = real_open(path, mode, *args, **kwargs)
            return _FailAfterOpen(real_file)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing_open)

    result = manager.update_plugin("eztv", new_content, dry_run=False)

    assert result["status"] == "failed", f"a write failure mid-way must be reported as failed, got {result!r}"
    assert local_path.exists(), "the target plugin file must still exist after a failed write"
    assert local_path.read_text(encoding="utf-8") == original_content, (
        "BOB-218 defect 1: after a write failure mid-way, the pre-existing plugin content "
        "must be left byte-identical to its pre-attempt state. Pre-fix, open(path, 'w') "
        "truncates the target immediately so it is corrupted the instant the write starts, "
        "with no rollback of any kind despite README's claim that 'the backup is restored'."
    )


def test_readme_no_longer_claims_a_rollback_that_does_not_match_reality() -> None:
    """The README's rollback claim and the code's actual behaviour must
    agree (constitution SS11.4.6). Either the README no longer claims a
    restore happens on failure that the code doesn't perform, or (if
    real rollback is implemented) the claim is accurate. This asserts
    the doc no longer describes a truncate-then-silently-fail-with-no-
    recovery flow as "the backup is restored"."""
    readme_text = README_PATH.read_text(encoding="utf-8")
    assert "the backup is restored" not in readme_text.lower(), (
        "BOB-218 defect 1: README still claims 'the backup is restored' on validation "
        "failure. The pre-fix code never reads a .bak back under any circumstances -- "
        "this claim must be corrected to match either an atomic-write implementation "
        "(no rollback needed because the target is never truncated) or removed."
    )


# ---------------------------------------------------------------------------
# Defect 2: README claims JSON report goes to stdout; code writes a file.
# ---------------------------------------------------------------------------


def test_report_is_written_to_file_not_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Directly observe the CURRENT behaviour: the JSON report body is
    written to `args.output` via `open(..., "w")` + `json.dump()`, and
    does NOT appear on stdout. No network calls: `check_for_updates`
    is replaced with a canned, deterministic result so this test never
    touches a real upstream URL."""
    current = _load_current_module()

    monkeypatch.setattr(current.PluginUpdateManager, "check_for_updates", lambda self: [])

    output_path = tmp_path / "bob218_report.json"
    monkeypatch.setattr(current.sys, "argv", ["plugin_update_automation.py", "--check", "--output", str(output_path)])
    monkeypatch.chdir(tmp_path)

    exit_code = current.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert output_path.is_file(), "the JSON report must be written to the --output file"

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert "total_checked" in report

    # The distinguishing JSON key from the report body must not appear
    # verbatim in stdout -- only a short confirmation line ("Report
    # saved to: ...") is printed there.
    assert '"total_checked"' not in captured.out, (
        "BOB-218 defect 2: the JSON report body must not be printed to stdout -- "
        "it is written to a file, and the README's claim that it goes to stdout "
        "does not match this observed behaviour"
    )
    assert str(output_path) in captured.out, "stdout should still confirm where the report was saved"


def test_readme_does_not_claim_json_report_goes_to_stdout() -> None:
    """The README's claim must match the directly-observed behaviour in
    `test_report_is_written_to_file_not_stdout` above: the code writes
    JSON reports to a file, never to stdout."""
    readme_text = README_PATH.read_text(encoding="utf-8")
    assert "written to stdout" not in readme_text.lower(), (
        "BOB-218 defect 2: README claims 'Reports are written to stdout in JSON', "
        "but the code writes them to args.output via open(args.output, 'w') + "
        "json.dump() -- the claim must be corrected to match reality"
    )
    assert "reports to stdout" not in readme_text.lower(), (
        "BOB-218 defect 2: README's Conventions section still claims 'reports to "
        "stdout', contradicting the code's actual file-based output"
    )


# ---------------------------------------------------------------------------
# Defect 3: bare `except:` in `_extract_version` swallows KeyboardInterrupt.
# ---------------------------------------------------------------------------


def test_extract_version_propagates_keyboard_interrupt(plugins_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `KeyboardInterrupt` (Ctrl-C) raised while extracting a plugin's
    version MUST propagate, not be silently swallowed and converted
    into an "unknown" version string.

    RED (pre-fix): the bare `except:` in `_extract_version` catches
    EVERYTHING, including `KeyboardInterrupt` (which inherits from
    `BaseException`, not `Exception`) -- so no exception escapes and
    `pytest.raises(KeyboardInterrupt)` fails because nothing was
    raised.

    GREEN (post-fix): the narrowed except clause does not match
    `KeyboardInterrupt`, so it propagates normally and
    `pytest.raises(KeyboardInterrupt)` observes it.
    """
    current = _load_current_module()
    manager = current.PluginUpdateManager(str(plugins_dir))

    plugin_path = plugins_dir / "eztv.py"
    plugin_path.write_text("# VERSION: 1.0.0\n", encoding="utf-8")

    def raise_keyboard_interrupt(self, content: str) -> str:
        raise KeyboardInterrupt()

    monkeypatch.setattr(current.PluginUpdateManager, "_extract_version_from_content", raise_keyboard_interrupt)

    with pytest.raises(KeyboardInterrupt):
        manager._extract_version(str(plugin_path))


def test_extract_version_still_returns_unknown_on_genuine_io_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """golden-FALSE (SS11.4.201(1) false-positive guard): narrowing the
    except clause must not turn `_extract_version` into something that
    raises on every genuine, ordinary failure it is meant to guard
    against (a missing/unreadable local plugin file) -- it must still
    return "unknown" for that case, exactly as before."""
    current = _load_current_module()
    manager = current.PluginUpdateManager(str(Path("/nonexistent-bob218-dir")))

    result = manager._extract_version("/nonexistent-bob218-dir/does-not-exist.py")
    assert result == "unknown", (
        f"a missing plugin file must still yield 'unknown' (not raise), got {result!r}"
    )


def test_extract_version_does_not_use_bare_except() -> None:
    """Static confirmation that `_extract_version`'s own guard clause
    no longer uses a bare `except:` (nor `except BaseException:`) --
    both catch `KeyboardInterrupt`/`SystemExit`, which this function
    must never swallow.

    Scoped to `_extract_version`'s own source only (via
    `inspect.getsource`), not the whole file: `_atomic_write`'s
    cleanup-then-re-raise clause legitimately uses
    `except BaseException:` (it re-raises unconditionally, so it
    never swallows anything) to guarantee the temp file is removed
    on literally any failure, including a Ctrl-C mid-write -- that is
    correct, unrelated usage this assertion must not flag.
    """
    import inspect

    current = _load_current_module()
    fn_source = inspect.getsource(current.PluginUpdateManager._extract_version)

    assert "except:\n" not in fn_source, "a bare `except:` must not appear in _extract_version"
    assert "except BaseException:" not in fn_source, (
        "`except BaseException:` is equally forbidden in _extract_version -- it also "
        "catches KeyboardInterrupt/SystemExit"
    )
