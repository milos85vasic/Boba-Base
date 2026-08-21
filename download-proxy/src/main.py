#!/usr/bin/env python3
"""
Main entry point for the Боба Search Service.

Starts both:
1. The original download proxy (HTTP server)
2. The FastAPI merge service (REST API)
"""

import asyncio
import faulthandler
import logging
import os
import signal
import sys
import threading
import time
import traceback

from config.log_filter import CredentialScrubber

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().addFilter(CredentialScrubber())
logger = logging.getLogger(__name__)

_shutdown_event = threading.Event()


# ---------------------------------------------------------------------------
# BOB-137 stall observatory  --  OBSERVE-ONLY INSTRUMENT, NOT A FIX.
#
# The merge service (7187) has been observed to stop answering for a bounded
# period while the download proxy (7186), served by the SAME process on a
# different thread, keeps answering normally (docs/qa/BOB-137/forensics.md).
# Identifying WHICH frame is responsible requires a stack dump taken WHILE the
# stall is happening. `py-spy` cannot attach on this host
# (kernel.yama.ptrace_scope=1), so the process must dump its OWN stacks.
#
# This block adds NO timeout, NO retry, NO restart and NO change to request
# handling (§11.4.102 Iron Law: no fixes before root cause). It only observes:
#
#   * an asyncio heartbeat task stamps a monotonic clock once a second;
#   * a plain (non-asyncio) watchdog thread notices when that stamp stops
#     advancing -- i.e. the merge-service event loop is not running callbacks;
#   * on stall it writes an all-thread traceback plus a per-thread CPU delta.
#
# The CPU delta is the discriminator the forensics could not settle: a thread
# BUSY-LOOPING shows rising utime, a thread BLOCKED in a syscall shows flat
# utime. Repeated dumps during one stall show whether the frame is stationary
# (blocked) or moving (spinning).
#
# BOB-157 -- WHY THIS NO LONGER USES faulthandler FOR THE AUTOMATIC DUMP.
#
# An earlier revision dumped stacks with
# `faulthandler.dump_traceback(all_threads=True)`, justified by "it is C and
# does not need the GIL, unlike sys._current_frames()".  That justification
# was WRONG for this call site, and the call was a live crash vector:
#
#   * CRASH.  On 2026-08-20 17:56:26 CEST it killed the service:
#     `python3[314359]: segfault at 70 ... in libpython3.12.so.1.0`, with the
#     container log ending mid-`"  File "`.  In CPython <3.13,
#     Python/traceback.c dump_frame() reads the frame's code pointer with NO
#     null check -- `PyCodeObject *code = frame->f_code;` -- then emits the
#     7-byte literal `"  File "` and dereferences `code->co_filename` at
#     offset 0x70.  A NULL code pointer therefore faults at address 0x70,
#     which is exactly what the kernel reported.  `_Py_DumpTracebackThreads()`
#     walks EVERY thread state without taking `interp->threads.head_mutex`
#     (it must stay async-signal-safe), so a thread exiting concurrently
#     leaves a freed/torn frame behind for the dumper to read.
#     Upstream: python/cpython gh-116008 and gh-128400.  Fixed on 3.13/3.14
#     (`_PyFrame_SafeGetCode()` + an explicit NULL return); the 3.12 branch
#     never received the backport -- 3.12 is security-fix-only -- and this
#     container runs CPython 3.12.13.  Verified against the branch sources on
#     2026-08-21 (see tests/unit/test_bob157_watchdog_dump_safety.py).
#
#   * AND THE GIL ARGUMENT DID NOT HOLD HERE.  faulthandler is GIL-free only
#     on its SIGNAL-HANDLER entry points (faulthandler_user /
#     faulthandler_fatal_error).  The Python-callable entry point
#     faulthandler_dump_traceback_py() contains no Py_BEGIN_ALLOW_THREADS at
#     all -- the watchdog thread must already hold the GIL to make the call.
#     `sys._current_frames()` needs exactly the same thing, so switching to
#     it costs nothing on this path.
#
# The perverse shape this closes: the worse the wedge got, the likelier the
# instrument was to kill the process and destroy the evidence it exists to
# capture.  The automatic dump is now pure Python (`sys._current_frames()` +
# `traceback.format_stack()`), which cannot enter dump_frame().  It takes
# `threading`'s brief bookkeeping lock, so its worst case is a WAIT -- and a
# waiting process still holds its evidence, unlike a faulted one.
#
# Manual dump at any time, no ptrace required:
#     podman exec qbittorrent-proxy kill -USR1 1     # -> safe dump, both sinks
#     podman exec qbittorrent-proxy kill -QUIT 1     # -> safe dump, both sinks
# Both are serviced by the watchdog thread (<=2 s latency), NOT inside the
# signal handler.  Set BOBA_STALL_C_DUMP=1 to arm the GIL-free C dump on
# SIGQUIT instead: it is the only tool that still works if a thread holds the
# GIL inside a C call, and on CPython <3.13 it can segfault the process.
# (PID 1 is this process INSIDE the container namespace. Never run a bare
# kill/pkill on the host, and never signal pgid <= 1 -- §11.4.263.)
# ---------------------------------------------------------------------------

_DIAG_ON = os.environ.get("BOBA_STALL_WATCHDOG", "1").strip().lower() not in ("0", "false", "no", "off")
_DIAG_STALL_S = float(os.environ.get("BOBA_STALL_SECONDS", "20"))
_DIAG_REDUMP_S = float(os.environ.get("BOBA_STALL_REDUMP_SECONDS", "60"))
_DIAG_DIR = os.environ.get("BOBA_STALL_DUMP_DIR", "/config/download-proxy/diagnostics")
_DIAG_MAX_DUMPS = int(os.environ.get("BOBA_STALL_MAX_DUMPS", "200"))
# Window over which per-thread CPU tick deltas are sampled (0 disables the wait).
_DIAG_CPU_SAMPLE_S = 1.0
# Innermost frames kept per thread, so one runaway recursion cannot flood the log.
_DIAG_MAX_FRAMES = 200

# BOB-157: first CPython release carrying the gh-116008 / gh-128400 fix for the
# NULL code-pointer dereference in dump_frame().  Bumping the runtime to >=3.13
# re-enables the C dump by design; anything below it must not arm it silently.
_C_DUMP_FIX_VERSION = (3, 13)
_C_DUMP_SAFE = sys.version_info[:2] >= _C_DUMP_FIX_VERSION

# Monotonic stamp written by the asyncio heartbeat task. If it stops advancing
# the merge-service event loop is not running callbacks. 0.0 == not started.
_loop_beat = 0.0
_loop_tid = 0
_diag_dumps = 0
_diag_fh = None
_diag_errors: list[str] = []
# Set by the SIGUSR1/SIGQUIT handlers; drained by the watchdog thread so the
# dump never runs in signal context (no buffered-I/O reentrancy).
_diag_request = threading.Event()


def _diag_c_dump_enabled() -> bool:
    """Whether the GIL-free C (faulthandler) all-thread dump may be armed.

    ``BOBA_STALL_C_DUMP``: ``1``/``on`` forces it on (operator accepts the
    CPython <3.13 segfault risk -- gh-116008 / gh-128400), ``0``/``off``
    forces it off, anything else (default ``auto``) arms it only on a runtime
    that carries the upstream fix.
    """
    raw = os.environ.get("BOBA_STALL_C_DUMP", "auto").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return _C_DUMP_SAFE


def _diag_all_thread_stacks() -> str:
    """Render every live thread's Python stack without entering faulthandler.

    ``sys._current_frames()`` plus ``traceback.format_stack()`` stay entirely
    on the Python side, so the CPython <3.13 ``dump_frame()`` NULL-dereference
    (gh-116008 / gh-128400) is unreachable from here.  Threads are keyed by
    the same native tid the per-thread CPU table uses, so the two blocks join.
    """
    meta: dict[int, tuple[str, int | None]] = {}
    try:
        for th in threading.enumerate():
            if th.ident is not None:
                meta[th.ident] = (th.name, th.native_id)
    except Exception as exc:  # never lose the stacks over missing labels
        _diag_errors.append(f"thread_meta: {exc!r}")

    rows = ["--- all-thread Python stacks (sys._current_frames, BOB-157-safe) ---"]
    frames = sys._current_frames()
    try:
        for ident in sorted(frames):
            name, native = meta.get(ident, ("<unknown>", None))
            mark = "  <-- ASYNCIO LOOP" if native is not None and native == _loop_tid else ""
            rows.append(f"Thread tid={native} ident={ident} name={name}{mark}")
            try:
                rows.extend(
                    line.rstrip("\n")
                    for line in traceback.format_stack(frames[ident], limit=_DIAG_MAX_FRAMES)
                )
            except Exception as exc:
                rows.append(f"  <stack unavailable: {exc!r}>")
    finally:
        # Frame objects keep their locals alive; drop them promptly.
        del frames
    return "\n".join(rows) + "\n"


def _diag_signal_dump(signum: int, frame: object) -> None:
    """SIGUSR1/SIGQUIT handler: only flag the request, never dump in-handler."""
    _diag_request.set()


def _diag_open_dump_file():
    """Pre-open the dump file at startup so a stall dump needs no new fd."""
    global _diag_fh
    try:
        os.makedirs(_DIAG_DIR, exist_ok=True)
        path = os.path.join(_DIAG_DIR, "stall_dumps.log")
        _diag_fh = open(path, "a", buffering=1)  # noqa: SIM115 - lifetime = process
        logger.info(f"BOB-137 stall watchdog: dumps -> {path}")
    except OSError as e:
        # An instrument that fails silently is a blind instrument (§11.4.201).
        logger.error(f"BOB-137 stall watchdog: cannot open dump file: {e}")
        _diag_fh = None


def _diag_threads():
    """{tid: (state, utime_ticks, stime_ticks, wchan)} from /proc/self/task."""
    out = {}
    try:
        tids = os.listdir("/proc/self/task")
    except OSError:
        return out
    for tid in tids:
        try:
            with open(f"/proc/self/task/{tid}/stat") as fh:
                raw = fh.read()
            # comm is parenthesised and may contain spaces -> split after ')'
            tail = raw[raw.rindex(")") + 2 :].split()
            state, utime, stime = tail[0], int(tail[11]), int(tail[12])
            try:
                with open(f"/proc/self/task/{tid}/wchan") as fh:
                    wchan = fh.read().strip() or "0"
            except OSError:
                wchan = "?"
            out[int(tid)] = (state, utime, stime, wchan)
        except (OSError, ValueError, IndexError):
            continue
    return out


def _diag_dump(stalled_for: float, episode: int, *, reason: str = "stall", force: bool = False) -> None:
    """Write an all-thread traceback + per-thread CPU delta for one stall."""
    global _diag_dumps
    if _diag_dumps >= _DIAG_MAX_DUMPS and not force:
        return
    _diag_dumps += 1

    # BOB-157: render the stacks ONCE, in pure Python, then write the same text
    # to both sinks. The previous revision called faulthandler once per sink,
    # which is the call that segfaulted the service on 2026-08-20 (see the
    # block comment above). Rendering first also means a failure here costs the
    # header, not the process.
    try:
        stacks = _diag_all_thread_stacks()
    except Exception as exc:
        # Must not raise and must not re-enter logging while the loop is
        # wedged; recorded instead so the failure is observable, never
        # swallowed (§11.4.201 - a silent instrument is a blind one).
        _diag_errors.append(f"all_thread_stacks: {exc!r}")
        stacks = "--- all-thread Python stacks UNAVAILABLE ---\n"

    header = (
        f"\n===== BOB-137 STALL DUMP #{_diag_dumps} episode={episode} reason={reason} "
        f"utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
        f"loop_silent_for={stalled_for:.1f}s loop_tid={_loop_tid} =====\n"
    )
    for sink in (_diag_fh, sys.stderr):
        if sink is None:
            continue
        try:
            sink.write(header)
            sink.write(stacks)
        except Exception as exc:
            _diag_errors.append(f"dump_write: {exc!r}")

    # Per-thread CPU delta: rising utime == spinning, flat utime == blocked.
    try:
        before = _diag_threads()
        if _DIAG_CPU_SAMPLE_S > 0:
            time.sleep(_DIAG_CPU_SAMPLE_S)
        after = _diag_threads()
        rows = [
            f"--- per-thread CPU over {_DIAG_CPU_SAMPLE_S:.1f}s "
            f"(ticks: rising=SPINNING, flat=BLOCKED) ---"
        ]
        for tid in sorted(after):
            st, ut, stm, wch = after[tid]
            put, pst = (before[tid][1], before[tid][2]) if tid in before else (ut, stm)
            mark = "  <-- ASYNCIO LOOP" if tid == _loop_tid else ""
            rows.append(
                f"tid={tid} state={st} d_utime={ut - put} d_stime={stm - pst} wchan={wch}{mark}"
            )
        text = "\n".join(rows) + "\n"
        for sink in (_diag_fh, sys.stderr):
            if sink is not None:
                sink.write(text)
    except Exception as exc:
        _diag_errors.append(f"cpu_delta: {exc!r}")


def _diag_watchdog() -> None:
    """Notice when the merge-service event loop stops running callbacks."""
    episode = 0
    stalling = False
    next_dump = 0.0
    while not _shutdown_event.is_set():
        _shutdown_event.wait(2.0)
        if _diag_request.is_set():
            # Operator asked for a dump (kill -USR1 / -QUIT). Serviced HERE,
            # out of signal context, so no buffered write is re-entered.
            _diag_request.clear()
            logger.info("BOB-137: on-demand stack dump requested")
            _diag_dump(0.0, 0, reason="on-demand", force=True)
            while _diag_errors:
                logger.error(f"BOB-137 watchdog internal error: {_diag_errors.pop(0)}")
        beat = _loop_beat
        if beat <= 0.0:
            continue  # event loop has not started yet
        silent = time.monotonic() - beat
        if silent < _DIAG_STALL_S:
            if stalling:
                logger.warning(
                    f"BOB-137: merge-service event loop RECOVERED after ~{silent:.0f}s "
                    f"(episode {episode})"
                )
                stalling = False
            continue
        now = time.monotonic()
        if not stalling:
            stalling = True
            episode += 1
            next_dump = 0.0
            logger.error(
                f"BOB-137: merge-service event loop SILENT for {silent:.0f}s "
                f"(episode {episode}) -- dumping all thread stacks"
            )
        if now >= next_dump:
            _diag_dump(silent, episode)
            while _diag_errors:
                logger.error(f"BOB-137 watchdog internal error: {_diag_errors.pop(0)}")
            next_dump = now + _DIAG_REDUMP_S


async def _diag_heartbeat() -> None:
    """Stamp the monotonic clock from inside the merge-service event loop."""
    global _loop_beat, _loop_tid
    _loop_tid = threading.get_native_id()
    while True:
        _loop_beat = time.monotonic()
        await asyncio.sleep(1.0)


def _diag_install() -> None:
    """Install the stall observatory. Never blocks or breaks startup."""
    if not _DIAG_ON:
        logger.info("BOB-137 stall watchdog: disabled (BOBA_STALL_WATCHDOG=0)")
        return
    try:
        _diag_open_dump_file()
        # KEPT at all_threads=True on purpose (BOB-157): this handler runs only
        # after SIGSEGV/SIGBUS/SIGFPE/SIGABRT/SIGILL, i.e. once the process is
        # already dying. It cannot crash a healthy service; the worst case is a
        # truncated last-gasp dump, which still beats no dump at all.
        faulthandler.enable(file=sys.stderr, all_threads=True)

        # On-demand dumps without ptrace. Default path is the pure-Python dump
        # serviced by the watchdog thread -- it cannot reach the CPython <3.13
        # dump_frame() fault (gh-116008 / gh-128400).
        c_dump = _diag_c_dump_enabled()
        try:
            # Own try/except: on-demand dumps are a convenience, and failing to
            # arm them (e.g. installed off the main thread) must never cost us
            # the automatic watchdog started below.
            signal.signal(signal.SIGUSR1, _diag_signal_dump)
            if c_dump and _diag_fh is not None:
                # chain=False -> the default action (core dump / terminate for
                # SIGQUIT) is NOT taken afterwards.
                faulthandler.register(signal.SIGQUIT, file=_diag_fh, all_threads=True, chain=False)
            else:
                signal.signal(signal.SIGQUIT, _diag_signal_dump)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"BOB-137 stall watchdog: on-demand signal dumps NOT armed: {e}")

        threading.Thread(target=_diag_watchdog, name="bob137-watchdog", daemon=True).start()
        logger.info(
            f"BOB-137 stall watchdog armed: stall>{_DIAG_STALL_S}s, redump every "
            f"{_DIAG_REDUMP_S}s, SIGUSR1/SIGQUIT=safe-dump-to-log+file; "
            f"BOB-157 C dump {'ARMED (may segfault on CPython<3.13)' if c_dump else 'disarmed'} "
            f"(python {sys.version_info[0]}.{sys.version_info[1]}, "
            f"upstream fix in {_C_DUMP_FIX_VERSION[0]}.{_C_DUMP_FIX_VERSION[1]}+)"
        )
    except Exception as e:
        logger.error(f"BOB-137 stall watchdog: install FAILED: {e}")


def _signal_handler(signum: int, frame: object) -> None:
    _shutdown_event.set()


def start_original_proxy() -> None:
    """Start the original download_proxy.py."""
    logger.info("Starting original download proxy...")
    try:
        engines_dir = os.environ.get("ENGINES_DIR", "/config/qBittorrent/nova3/engines")
        if engines_dir not in sys.path:
            sys.path.insert(0, engines_dir)
        from download_proxy import run_server  # type: ignore[import-not-found]

        run_server()
    except Exception as e:
        logger.error(f"Original proxy failed: {e}")


def start_fastapi_server() -> None:
    """Start the FastAPI merge service."""
    logger.info("Starting FastAPI merge service...")
    try:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        import uvicorn

        from api import app

        # Configure uvicorn. MERGE_SERVICE_HOST defaults to 0.0.0.0 because
        # the container uses network_mode: host and external requests arrive
        # on 7187 from any interface (the host port is firewalled per the
        # constitution Security Requirements). Override with
        # MERGE_SERVICE_HOST=127.0.0.1 in deployments where the merge
        # service should be localhost-only.
        merge_port = int(os.environ.get("MERGE_SERVICE_PORT", "7187"))
        merge_host = os.environ.get("MERGE_SERVICE_HOST", "0.0.0.0")  # nosec B104  # noqa: S104
        config = uvicorn.Config(
            app,
            host=merge_host,
            port=merge_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # Run in async mode. The heartbeat task is the BOB-137 stall
        # observatory's liveness probe; it stamps a monotonic clock from
        # inside this event loop so the watchdog thread can tell "loop is
        # idle" apart from "loop is not running callbacks at all". It adds
        # no behaviour to request handling and is cancelled with the server.
        async def _serve_with_heartbeat() -> None:
            beat = asyncio.ensure_future(_diag_heartbeat()) if _DIAG_ON else None
            try:
                await server.serve()
            finally:
                if beat is not None:
                    beat.cancel()

        asyncio.run(_serve_with_heartbeat())
    except Exception as e:
        logger.error(f"FastAPI server failed: {e}")


def main() -> None:
    """Main entry point."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # BOB-137: observe-only stall observatory (no timeouts/retries/restarts).
    _diag_install()

    logger.info("=" * 60)
    logger.info("Боба Search Service Starting")
    logger.info("=" * 60)

    # Map BOBA_UPSTREAM_PROXY → HTTP(S)_PROXY/NO_PROXY before any worker thread
    # starts, so tracker-bound urllib + aiohttp egress honors the configured
    # outbound proxy with the loopback/sidecar bypass. No-op when unset.
    try:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from config.proxy import apply_proxy_env, upstream_proxy

        apply_proxy_env()
        if upstream_proxy():
            logger.info("Tracker-bound egress routed through upstream proxy (BOBA_UPSTREAM_PROXY/*_PROXY)")
    except Exception as e:  # pragma: no cover - never block startup on proxy setup
        logger.warning(f"Upstream proxy setup skipped: {e}")

    proxy_thread = threading.Thread(target=start_original_proxy, daemon=True)
    fastapi_thread = threading.Thread(target=start_fastapi_server, daemon=True)

    proxy_thread.start()
    logger.info("Original proxy thread started")

    fastapi_thread.start()
    logger.info("FastAPI thread started")

    while not _shutdown_event.is_set():
        _shutdown_event.wait(60)

    logger.info("Shutting down...")
    proxy_thread.join(timeout=5)
    fastapi_thread.join(timeout=5)
    logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
