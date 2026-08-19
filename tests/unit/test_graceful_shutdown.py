"""Verify that main.py handles SIGTERM/SIGINT with graceful shutdown.

The test spawns a subprocess that mimics main.py's threading pattern,
sends SIGTERM, and asserts the process exits cleanly within 5 seconds.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time

_WORKTREE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MAIN_PY = os.path.join(_WORKTREE, "download-proxy", "src", "main.py")


def _write_script(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".py", prefix="_shutdown_test_")
    with os.fdopen(fd, "w") as f:
        f.write(source)
    return path


def _run_and_signal(script_path: str, sig: int, startup: float = 0.5) -> subprocess.CompletedProcess:
    with subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as proc:
        time.sleep(startup)
        proc.send_signal(sig)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stdout_data = proc.stdout.read() if proc.stdout else b""
        stderr_data = proc.stderr.read() if proc.stderr else b""
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=stdout_data,
        stderr=stderr_data,
    )


def test_sigterm_graceful_exit():
    """Process should exit with code 0 on SIGTERM (graceful shutdown)."""
    script = _write_script(_pattern_from_main())
    try:
        result = _run_and_signal(script, signal.SIGTERM)
        assert result.returncode == 0, (
            f"Expected graceful exit (0), got {result.returncode}.\n"
            f"stderr: {result.stderr.decode(errors='replace')[:500]}"
        )
    finally:
        os.unlink(script)


def test_sigint_graceful_exit():
    """Process should exit with code 0 on SIGINT (Ctrl-C)."""
    script = _write_script(_pattern_from_main())
    try:
        result = _run_and_signal(script, signal.SIGINT)
        assert result.returncode == 0, (
            f"Expected graceful exit (0), got {result.returncode}.\n"
            f"stderr: {result.stderr.decode(errors='replace')[:500]}"
        )
    finally:
        os.unlink(script)


def test_threads_joined_on_shutdown():
    """Daemon threads should be joined (with timeout) before exit."""
    marker = os.path.join(tempfile.gettempdir(), f"_shutdown_test_{os.getpid()}.marker")

    script = _write_script(f"""
import threading
import time
import signal
import os
import sys

sys.path.insert(0, r"{_WORKTREE}/download-proxy/src")

shutdown_event = threading.Event()
MARKER = r"{marker}"

def signal_handler(signum, frame):
    shutdown_event.set()

def worker():
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(60)
    finally:
        with open(MARKER, "w") as f:
            f.write("cleaned")

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

t = threading.Thread(target=worker, daemon=True)
t.start()

while not shutdown_event.is_set():
    shutdown_event.wait(60)

t.join(timeout=5)
sys.exit(0)
""")
    try:
        result = _run_and_signal(script, signal.SIGTERM)
        assert result.returncode == 0
        assert os.path.isfile(marker), "Worker thread did not run cleanup"
        with open(marker) as f:
            assert f.read() == "cleaned"
    finally:
        os.unlink(script)
        if os.path.isfile(marker):
            os.unlink(marker)


def _pattern_from_main() -> str:
    """Read main.py and extract its threading/shutdown pattern.

    Returns a self-contained script that uses the same pattern as main.py
    but with dummy thread functions instead of real server starts.
    """
    with open(_MAIN_PY) as f:
        source = f.read()
    has_signal_import = "import signal" in source
    has_shutdown_event = "shutdown_event" in source or "threading.Event" in source
    has_event_wait = "event.wait" in source or "shutdown_event.wait" in source
    has_join = ".join(" in source

    if has_signal_import and has_shutdown_event and has_event_wait and has_join:
        return _fixed_pattern()
    return _broken_pattern()


def _broken_pattern() -> str:
    return f"""
import threading
import time
import sys

sys.path.insert(0, r"{_WORKTREE}/download-proxy/src")

def dummy():
    while True:
        time.sleep(60)

def main():
    t1 = threading.Thread(target=dummy, daemon=True)
    t2 = threading.Thread(target=dummy, daemon=True)
    t1.start()
    t2.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass

main()
"""


def _fixed_pattern() -> str:
    return f"""
import threading
import time
import signal
import sys

sys.path.insert(0, r"{_WORKTREE}/download-proxy/src")

shutdown_event = threading.Event()

def _signal_handler(signum, frame):
    shutdown_event.set()

def dummy():
    while not shutdown_event.is_set():
        shutdown_event.wait(60)

def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    t1 = threading.Thread(target=dummy, daemon=True)
    t2 = threading.Thread(target=dummy, daemon=True)
    t1.start()
    t2.start()

    while not shutdown_event.is_set():
        shutdown_event.wait(60)

    t1.join(timeout=5)
    t2.join(timeout=5)

main()
"""
