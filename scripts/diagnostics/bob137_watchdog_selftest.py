#!/usr/bin/env python3
"""BOB-137 stall-watchdog self-test (§11.4.107(10) self-validated analyzer).

An instrument is only evidence once it has been observed to FIRE on a known
bad case AND to stay quiet on a known good one. A watchdog that never dumps
proves nothing about the service: it may equally mean "no stall happened" or
"the watchdog is blind" -- the §11.4.201(6) false-null. This runs both poles.

  GOLDEN-GOOD : event loop healthy for the whole window  -> MUST NOT dump.
  GOLDEN-BAD  : event loop blocked by a synchronous call -> MUST dump, and the
                dump MUST name the blocking frame by function name.

Usage (inside the container, where the service's own Python runs):
    podman exec qbittorrent-proxy python3 \
        /config/download-proxy/scripts/diagnostics/bob137_watchdog_selftest.py

Exit 0 = both poles behaved. Non-zero = the watchdog is NOT trustworthy and
its silence during a soak must NOT be read as "no stall occurred".
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import threading
import time

SRC = os.environ.get("BOBA_SRC_DIR", "/config/download-proxy/src")


def _load_main(dump_dir: str, stall_s: float):
    """Import the service's real main.py with the watchdog pointed at a temp dir."""
    os.environ["BOBA_STALL_WATCHDOG"] = "1"
    os.environ["BOBA_STALL_DUMP_DIR"] = dump_dir
    os.environ["BOBA_STALL_SECONDS"] = str(stall_s)
    os.environ["BOBA_STALL_REDUMP_SECONDS"] = "5"
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    for stale in ("main",):
        sys.modules.pop(stale, None)
    import main

    return main


def _dump_text(dump_dir: str) -> str:
    path = os.path.join(dump_dir, "stall_dumps.log")
    if not os.path.exists(path):
        return ""
    with open(path) as fh:
        return fh.read()


def _run_pole(block_seconds: float, observe_seconds: float, stall_s: float) -> str:
    """Run one pole in a fresh temp dir; return the dump-file contents."""
    dump_dir = tempfile.mkdtemp(prefix="bob137-selftest-")
    try:
        main = _load_main(dump_dir, stall_s)
        main._diag_install()

        def _loop_thread() -> None:
            async def _drive() -> None:
                beat = asyncio.ensure_future(main._diag_heartbeat())
                await asyncio.sleep(stall_s / 2.0)  # prove the loop is alive first
                if block_seconds > 0:
                    # The defect shape under test: a SYNCHRONOUS blocking call
                    # made from inside a coroutine. The loop cannot run any
                    # other callback -- including its own heartbeat -- until
                    # this returns. Named distinctively so the dump can be
                    # asserted to point at THIS frame.
                    _bob137_synthetic_blocking_frame(block_seconds)
                await asyncio.sleep(observe_seconds)
                beat.cancel()

            asyncio.run(_drive())

        t = threading.Thread(target=_loop_thread, daemon=True)
        t.start()
        t.join(timeout=stall_s / 2.0 + block_seconds + observe_seconds + 15.0)
        time.sleep(1.0)
        return _dump_text(dump_dir)
    finally:
        main = sys.modules.get("main")
        if main is not None:
            main._shutdown_event.set()
        time.sleep(0.2)
        if main is not None:
            main._shutdown_event.clear()
        sys.modules.pop("main", None)
        shutil.rmtree(dump_dir, ignore_errors=True)


def _bob137_synthetic_blocking_frame(seconds: float) -> None:
    """Stand-in for the real blocking call. Blocks the calling thread."""
    time.sleep(seconds)


def main() -> int:
    stall_s = 4.0
    failures: list[str] = []

    print("== GOLDEN-BAD: event loop blocked -> watchdog MUST dump ==")
    bad = _run_pole(block_seconds=stall_s * 2.5, observe_seconds=2.0, stall_s=stall_s)
    if "BOB-137 STALL DUMP" not in bad:
        failures.append("GOLDEN-BAD produced no stall dump - watchdog is BLIND")
    elif "_bob137_synthetic_blocking_frame" not in bad:
        failures.append("GOLDEN-BAD dumped but did NOT name the blocking frame")
    else:
        print("   PASS: dumped and named the blocking frame")
    if "d_utime=" not in bad:
        failures.append("GOLDEN-BAD dump carries no per-thread CPU delta")
    else:
        print("   PASS: per-thread CPU delta present (spin-vs-block discriminator)")

    print("== GOLDEN-GOOD: event loop healthy -> watchdog MUST stay quiet ==")
    good = _run_pole(block_seconds=0.0, observe_seconds=stall_s * 2.5, stall_s=stall_s)
    if "BOB-137 STALL DUMP" in good:
        failures.append("GOLDEN-GOOD dumped on a healthy loop - false positive (§11.4.201(1))")
    else:
        print("   PASS: stayed quiet on a healthy loop")

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("SELFTEST PASS - watchdog fires on a real stall and not otherwise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
