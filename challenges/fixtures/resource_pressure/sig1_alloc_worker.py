#!/usr/bin/env python3
"""sig1_alloc_worker.py — bounded, self-terminating real-RSS allocator.

Helper for sig1_real_rss_fixture.sh (the SIG-1 §11.4.115(F) RED fixture for
challenges/scripts/resource_pressure_signature_challenge.sh).

Allocates ${SIG1_FIXTURE_GB:-5.5} GB of REAL, page-resident memory. The
`bytearray(size)` constructor already forces every page via its internal
memset(0), but every page is ALSO explicitly re-written here (belt-and-
suspenders) so the kernel cannot serve any part of the allocation from the
shared zero-page under any allocator implementation detail — the measured
RSS genuinely reflects the requested size, not merely virtual address space.

Prints a "SIG1_FIXTURE_READY" marker (with its own PID + byte count) once
the allocation is fully resident, then sleeps for a BOUNDED window so the
driver script has time to verify via `ps` and run the challenge. The bounded
sleep is a second line of defense: even if the driver's cleanup trap never
fires (crash, SIGKILL of the driver itself), this process self-terminates
on its own instead of leaking a multi-GB allocation indefinitely.

Host-safety (§12.6/§12.11): the default 5.5 GB is well under 10% of a
typical 32-64 GB development host and far under the §12.6 60%-of-total
ceiling; the caller (sig1_real_rss_fixture.sh) is responsible for checking
available memory before invoking this worker.
"""
import os
import sys
import time

GB = 1024 ** 3
PAGE = 4096


def main() -> int:
    size_gb = float(os.environ.get("SIG1_FIXTURE_GB", "5.5"))
    sleep_sec = float(os.environ.get("SIG1_FIXTURE_SLEEP_SEC", "25"))
    size = int(size_gb * GB)

    buf = bytearray(size)
    # Explicitly touch every page so the kernel cannot serve any of it from
    # the shared zero-page under any allocator/CPython-version implementation
    # detail. This is a real write, not a no-op re-zero.
    for i in range(0, size, PAGE):
        buf[i] = 1

    print(f"SIG1_FIXTURE_READY pid={os.getpid()} bytes={size}", flush=True)
    sys.stdout.flush()
    time.sleep(sleep_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
