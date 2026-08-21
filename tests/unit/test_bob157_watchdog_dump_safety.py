"""BOB-157 — the BOB-137 stall watchdog must not be able to segfault the service.

Forensics (docs: BOB-157, BOB-131): on 2026-08-20 17:56:26 CEST the merge
service died with ``python3[314359]: segfault at 70 ... in
libpython3.12.so.1.0`` while the watchdog was writing stall dump #17.  The
faulting instruction pair decodes to ``mov r14,[r12]`` (the frame's code
pointer, read as NULL) followed by ``mov rax,[r14+0x70]`` (``co_filename``)
— i.e. ``NULL + 0x70`` — inside ``dump_frame()``.

Source-level confirmation (fetched 2026-08-21, see the module docstring of
``download-proxy/src/main.py``):

* cpython ``3.12`` branch, ``Python/traceback.c`` ``dump_frame()``::

      PyCodeObject *code = frame->f_code;      /* no NULL check */
      PUTS(fd, "  File ");                     /* 7 bytes — matches edx=7 */
      if (code->co_filename != NULL ...        /* faults here */

* cpython ``3.13``/``3.14`` branches carry the fix::

      PyCodeObject *code = _PyFrame_SafeGetCode(frame);
      if (code == NULL) { return -1; }

The container runs CPython 3.12.13, where the fix is absent.

WHAT THESE TESTS ASSERT — stated plainly per the anti-bluff covenant
(§11.4/§11.4.1): they do **not** reproduce a segfault.  A memory-safety
fault inside CPython cannot be triggered on demand from Python.  They are
structural + behavioural guards:

* structural — the automatic (unattended) dump path no longer reaches
  ``faulthandler.dump_traceback()``, and the on-demand signal handlers do
  not arm the C all-thread dump on a runtime that lacks the upstream fix;
* behavioural — the replacement capture really produces per-thread Python
  stacks that name the threads and the frames they are parked in, so the
  diagnostic value the watchdog exists for is genuinely preserved.
"""

from __future__ import annotations

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

import main  # noqa: E402


class _ExplodingFaulthandler:
    """Stand-in that fails loudly if the crash-prone C dump is invoked."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def dump_traceback(self, *args, **kwargs):
        self.calls.append("dump_traceback")
        raise AssertionError(
            "BOB-157: the automatic stall dump called faulthandler.dump_traceback(); "
            "this is the CPython <3.13 segfault vector (gh-116008 / gh-128400)."
        )

    def enable(self, *args, **kwargs):
        self.calls.append(f"enable{kwargs}")

    def register(self, signum, *args, **kwargs):
        self.calls.append(f"register:{signum}:{kwargs}")


@pytest.fixture
def fast_dump(monkeypatch):
    """Make _diag_dump cheap: no /proc walk, no 1 s CPU-delta sleep."""
    monkeypatch.setattr(main, "_diag_threads", lambda: {}, raising=True)
    monkeypatch.setattr(main, "_DIAG_CPU_SAMPLE_S", 0.0, raising=False)
    monkeypatch.setattr(main, "_diag_dumps", 0, raising=True)


class TestAutomaticDumpIsNotACrashVector:
    """The unattended path — the one that fired 17x in 16 min and crashed."""

    def test_stall_dump_never_calls_faulthandler(self, monkeypatch, fast_dump, tmp_path):
        """_diag_dump() must not reach faulthandler.dump_traceback()."""
        fh = _ExplodingFaulthandler()
        monkeypatch.setattr(main, "faulthandler", fh, raising=True)
        sink = (tmp_path / "dump.log").open("a", buffering=1)
        monkeypatch.setattr(main, "_diag_fh", sink, raising=True)
        try:
            main._diag_dump(21.0, 1)
        finally:
            sink.close()
        assert fh.calls == [], f"automatic dump touched faulthandler: {fh.calls}"

    def test_stall_dump_still_writes_thread_stacks(self, monkeypatch, fast_dump, tmp_path):
        """Removing the crash vector must not remove the diagnostic itself."""
        monkeypatch.setattr(main, "faulthandler", _ExplodingFaulthandler(), raising=True)
        path = tmp_path / "dump.log"
        sink = path.open("a", buffering=1)
        monkeypatch.setattr(main, "_diag_fh", sink, raising=True)
        try:
            main._diag_dump(21.0, 7)
        finally:
            sink.close()
        text = path.read_text()
        assert "BOB-137 STALL DUMP #1 episode=7" in text
        # The stack of *this* thread must be in there, named and with a frame.
        assert "test_stall_dump_still_writes_thread_stacks" in text, text[:2000]


class TestAllThreadStackCapture:
    """The replacement capture must deliver the multi-thread view."""

    def test_captures_every_live_thread_by_name_and_native_id(self):
        started, release = threading.Event(), threading.Event()

        def parked_in_a_known_function() -> None:
            started.set()
            release.wait(10)

        t = threading.Thread(target=parked_in_a_known_function, name="bob157-probe", daemon=True)
        t.start()
        try:
            assert started.wait(5), "probe thread never started"
            text = main._diag_all_thread_stacks()
        finally:
            release.set()
            t.join(5)

        assert "bob157-probe" in text, text[:2000]
        assert str(t.native_id) in text, text[:2000]
        assert "parked_in_a_known_function" in text, text[:2000]

    def test_marks_the_event_loop_thread_so_stacks_join_the_cpu_table(self, monkeypatch):
        """The CPU-delta table keys on native tid; the stacks must too."""
        monkeypatch.setattr(main, "_loop_tid", threading.get_native_id(), raising=True)
        text = main._diag_all_thread_stacks()
        loop_lines = [ln for ln in text.splitlines() if "ASYNCIO LOOP" in ln]
        assert loop_lines, f"no loop marker in stacks:\n{text[:2000]}"
        assert str(threading.get_native_id()) in loop_lines[0]

    def test_capture_is_pure_python_and_never_touches_faulthandler(self, monkeypatch):
        fh = _ExplodingFaulthandler()
        monkeypatch.setattr(main, "faulthandler", fh, raising=True)
        main._diag_all_thread_stacks()
        assert fh.calls == []


class TestUpstreamFixBoundaryIsRecorded:
    """§ BOB-157 acceptance: a later runtime bump must not silently re-arm it."""

    def test_fix_version_constant_is_313(self):
        assert main._C_DUMP_FIX_VERSION == (3, 13)

    def test_source_cites_the_upstream_issues(self):
        src = os.path.join(os.path.dirname(main.__file__), "main.py")
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        assert "gh-116008" in text
        assert "gh-128400" in text

    @pytest.mark.parametrize(
        ("env", "safe_runtime", "expected"),
        [
            (None, False, False),  # 3.12 container -> C dump NOT armed
            (None, True, True),  # 3.13+ -> upstream fix present -> armed
            ("1", False, True),  # explicit operator opt-in overrides
            ("0", True, False),  # explicit operator opt-out overrides
        ],
    )
    def test_c_dump_decision(self, monkeypatch, env, safe_runtime, expected):
        if env is None:
            monkeypatch.delenv("BOBA_STALL_C_DUMP", raising=False)
        else:
            monkeypatch.setenv("BOBA_STALL_C_DUMP", env)
        monkeypatch.setattr(main, "_C_DUMP_SAFE", safe_runtime, raising=True)
        assert main._diag_c_dump_enabled() is expected


class TestOnDemandSignalsAreSafeByDefault:
    """kill -USR1 / -QUIT must not be able to kill a healthy 3.12 service."""

    def _install(self, monkeypatch, fh, signals):
        monkeypatch.setattr(main, "faulthandler", fh, raising=True)
        monkeypatch.setattr(main, "signal", signals, raising=True)
        monkeypatch.setattr(main, "_diag_open_dump_file", lambda: None, raising=True)
        monkeypatch.setattr(main, "_DIAG_ON", True, raising=True)
        monkeypatch.setattr(threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda s: None})())
        main._diag_install()

    def test_no_c_all_thread_handler_registered_on_312(self, monkeypatch):
        import signal as real_signal

        fh = _ExplodingFaulthandler()
        installed: dict[int, object] = {}

        class _Signals:
            SIGUSR1 = real_signal.SIGUSR1
            SIGQUIT = real_signal.SIGQUIT

            @staticmethod
            def signal(signum, handler):
                installed[signum] = handler

        monkeypatch.setattr(main, "_C_DUMP_SAFE", False, raising=True)
        monkeypatch.delenv("BOBA_STALL_C_DUMP", raising=False)
        self._install(monkeypatch, fh, _Signals)

        assert not [c for c in fh.calls if c.startswith("register:")], fh.calls
        # ... and the operator still gets a dump: both signals are handled.
        assert real_signal.SIGUSR1 in installed
        assert real_signal.SIGQUIT in installed

    def test_fatal_handler_keeps_all_threads(self, monkeypatch):
        """faulthandler.enable() runs only on an already-fatal signal — keep it."""
        import signal as real_signal

        fh = _ExplodingFaulthandler()

        class _Signals:
            SIGUSR1 = real_signal.SIGUSR1
            SIGQUIT = real_signal.SIGQUIT

            @staticmethod
            def signal(signum, handler):
                pass

        monkeypatch.setattr(main, "_C_DUMP_SAFE", False, raising=True)
        self._install(monkeypatch, fh, _Signals)
        assert any(c.startswith("enable") and "'all_threads': True" in c for c in fh.calls), fh.calls
