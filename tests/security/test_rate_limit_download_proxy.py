"""BOB-111 — per-IP rate limiting on the :7186 download proxy (stdlib server).

WHY THIS FILE EXISTS, AND WHY IT IS NOT A DUPLICATE OF
`tests/security/test_rate_limit_public_endpoints.py`.

Measured 2026-08-21 against the operator's live stack:

    $ curl -sD- -o/dev/null http://localhost:7186/ | head -2
    HTTP/1.1 200 OK
    Server: BaseHTTP/0.6 Python/3.12.13     <-- stdlib, NOT uvicorn

    150 sequential GET http://localhost:7186/  ->  200:150  429:0

:7186 is served by `plugins/download_proxy.py::run_server()` — a stdlib
`ThreadingHTTPServer` running on its OWN THREAD inside the same process as the
FastAPI merge service (`download-proxy/src/main.py`). It is NOT an ASGI app, so
`SlowAPIMiddleware` — which is what protects :7187 — structurally cannot reach
it. The claim in `download-proxy/src/api/rate_limit.py`'s module docstring that
`install()` covers "the proxy service on :7186 (same FastAPI app object today)"
was measured FALSE and is corrected in that file by this change.

EVIDENCE CLASS (§11.4.226): RUNTIME-OVER-A-REAL-SOCKET. This file binds the
REAL `DownloadHandler` to a real ephemeral TCP port with a real
`ThreadingHTTPServer` and drives it with real `urllib` requests, exactly as the
container does. It is a strictly stronger class than the ASGI-TestClient tier
used for :7187, and it is what a stdlib server admits: there is no in-process
TestClient for `BaseHTTPRequestHandler`.

The one thing that is NOT real is the qBittorrent backend: a local stub HTTP
server stands in for :7185 so the test never needs the operator's container and
never proxies to a real torrent client (§11.4.27(A) — the stub is downstream of
the limiter and is not what is under test).

BOTH DIRECTIONS ARE ASSERTED (§11.4.201(1)): every case that proves a burst is
REFUSED is paired with a control proving under-threshold traffic SUCCEEDS. A
limiter that refuses everything is exactly as broken as one that refuses
nothing — and on :7186 that failure mode would take down the operator's
qBittorrent WebUI, which is proxied through this very port.

§11.4.263: no subprocess or proc object is mocked in this file, so no
`mock.pid` is involved anywhere.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import socket
import sys
import threading
from pathlib import Path
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DP_PATH = os.path.join(_REPO_ROOT, "plugins", "download_proxy.py")

# Deliberately tiny limits so a case costs milliseconds, injected through the
# SAME public env knobs an operator uses in production — so the test also
# proves those knobs are wired, not merely that a hardcoded default exists.
PROXY_LIMIT = 5
DOWNLOAD_LIMIT = 2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _StubQbtHandler(BaseHTTPRequestHandler):
    """Stands in for qBittorrent on :7185. Always 200, never a real client."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        pass

    def _ok(self):
        payload = b"stub-qbittorrent"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 - stdlib signature
        self._ok()

    def do_POST(self):  # noqa: N802 - stdlib signature
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        self._ok()


def _load_download_proxy(env: dict[str, str], qbt_port: int):
    """Import a FRESH `download_proxy` module under the given env.

    A fresh module object per case is required: the limit strings and the
    limiter instance are resolved at import time from the environment, exactly
    as they are in the container.
    """
    # M4: EVERY var this helper writes must be in the save/restore set, or it
    # leaks into the pytest process and silently reconfigures later modules.
    env = dict(env)
    env["QBITTORRENT_HOST"] = "127.0.0.1"
    env["QBITTORRENT_PORT"] = str(qbt_port)
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("download_proxy_rl_case", _DP_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["download_proxy_rl_case"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Stack:
    """A live stub-qBittorrent + a live download-proxy, both on real sockets."""

    def __init__(self, env: dict[str, str]):
        self.qbt_port = _free_port()
        self.qbt = ThreadingHTTPServer(("127.0.0.1", self.qbt_port), _StubQbtHandler)
        self.qbt.daemon_threads = True
        threading.Thread(target=self.qbt.serve_forever, daemon=True).start()

        self.mod = _load_download_proxy(env, self.qbt_port)
        self.proxy_port = _free_port()
        self.proxy = ThreadingHTTPServer(("127.0.0.1", self.proxy_port), self.mod.DownloadHandler)
        self.proxy.daemon_threads = True
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()

    def get(self, path: str = "/", headers: dict[str, str] | None = None) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.proxy_port}{path}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 - fixed loopback URL
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            # MINOR-a: an HTTPError IS an open response object. Letting it fall
            # out of scope unclosed emits a ResourceWarning per refused request
            # (12 per suite run, measured), and §11.4.134's bar is ZERO warnings.
            with contextlib.closing(e):
                return e.code, dict(e.headers), e.read()

    def post_tracker_add(self, headers: dict[str, str] | None = None) -> tuple[int, dict, bytes]:
        """POST the EXPENSIVE path: a tracker URL that triggers the nova2dl fan-out."""
        body = b"urls=https://rutracker.org/forum/viewtopic.php?t=1"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.proxy_port}/api/v2/torrents/add",
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed loopback URL
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            with contextlib.closing(e):
                return e.code, dict(e.headers), e.read()

    def close(self):
        for srv in (self.proxy, self.qbt):
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:  # noqa: BLE001 - teardown is best-effort (§11.4.14)
                pass
        sys.modules.pop("download_proxy_rl_case", None)


@pytest.fixture
def limited_stack():
    stacks: list[_Stack] = []

    def _make(**extra_env):
        env = {
            "RATE_LIMIT_PROXY": f"{PROXY_LIMIT}/minute",
            "RATE_LIMIT_PROXY_DOWNLOAD": f"{DOWNLOAD_LIMIT}/minute",
            "RATE_LIMIT_DISABLED": "",
            "TRUST_FORWARDED_FOR": "",
        }
        env.update(extra_env)
        s = _Stack(env)
        stacks.append(s)
        return s

    yield _make
    for s in stacks:
        s.close()


# ---------------------------------------------------------------------------
# The passthrough class: the qBittorrent WebUI proxy surface.
# ---------------------------------------------------------------------------


def test_red_passthrough_burst_is_refused_with_429(limited_stack):
    """A burst past the passthrough budget is REFUSED — the BOB-111 gap."""
    stack = limited_stack()
    codes = [stack.get("/")[0] for _ in range(PROXY_LIMIT + 4)]
    assert 429 in codes, (
        f"no 429 in {codes} — :7186 accepted an unbounded burst "
        f"(limit was {PROXY_LIMIT}/minute)"
    )
    # The refusal must arrive AFTER the allowance, not instead of it.
    assert codes[0] == 200, f"first request refused: {codes}"
    assert codes.index(429) >= PROXY_LIMIT, (
        f"refused at #{codes.index(429) + 1}, before the {PROXY_LIMIT}-request budget: {codes}"
    )


def test_control_under_threshold_passthrough_succeeds(limited_stack):
    """§11.4.201(1): a limiter that refuses everything is equally broken."""
    stack = limited_stack()
    codes = [stack.get("/")[0] for _ in range(PROXY_LIMIT)]
    assert codes == [200] * PROXY_LIMIT, f"under-threshold traffic was refused: {codes}"


def test_429_body_and_headers_are_leak_free(limited_stack):
    """§11.4.10: the 429 carries an opaque token + Retry-After, never internals."""
    stack = limited_stack()
    status, headers, body = 200, {}, b""
    for _ in range(PROXY_LIMIT + 4):
        status, headers, body = stack.get("/")
        if status == 429:
            break
    assert status == 429, "never reached the limit"
    assert json.loads(body.decode()) == {"error": "rate_limited"}, body
    lowered = {k.lower(): v for k, v in headers.items()}
    assert "retry-after" in lowered, lowered
    assert int(lowered["retry-after"]) > 0
    assert lowered.get("x-ratelimit-limit") == str(PROXY_LIMIT), lowered
    # No client IP, no bucket key, no limit-class name anywhere in the body.
    assert b"127.0.0.1" not in body
    assert b"proxy" not in body.lower()


# ---------------------------------------------------------------------------
# The expensive class: tracker-URL interception (subprocess + tracker fetch).
# ---------------------------------------------------------------------------


def test_red_tracker_download_path_has_its_own_tighter_budget(limited_stack):
    """The nova2dl fan-out path is budgeted separately and more tightly.

    This is the :7186 analogue of :7187's `search` class: one request here
    spawns a subprocess AND makes an outbound tracker request, so it is the
    amplification vector — it must not share the WebUI's generous allowance.
    """
    stack = limited_stack()
    codes = [stack.post_tracker_add()[0] for _ in range(DOWNLOAD_LIMIT + 3)]
    assert 429 in codes, f"tracker-download path accepted an unbounded burst: {codes}"
    assert codes.index(429) >= DOWNLOAD_LIMIT, (
        f"refused at #{codes.index(429) + 1}, before the {DOWNLOAD_LIMIT}-request budget: {codes}"
    )
    # And it must be TIGHTER than the passthrough class, or it is not a
    # separate class at all.
    assert DOWNLOAD_LIMIT < PROXY_LIMIT


def test_expensive_path_does_not_drain_the_webui_budget(limited_stack):
    """Buckets are per-class: exhausting downloads must not lock out the WebUI.

    Measured 2026-08-21: the WebUI page proxied through :7186 references 76
    unique local sub-resources, so one cold page load is ~77 requests. If the
    expensive class shared that bucket, a couple of torrent adds would blank
    the operator's WebUI.
    """
    stack = limited_stack()
    for _ in range(DOWNLOAD_LIMIT + 3):
        stack.post_tracker_add()
    assert stack.get("/")[0] == 200, "WebUI passthrough was collateral-damaged"


# ---------------------------------------------------------------------------
# Per-IP isolation + the paired §1.1 mutation.
# ---------------------------------------------------------------------------


def test_per_ip_isolation_under_explicit_forwarded_for_optin(limited_stack):
    """Caller A being throttled must not throttle caller B."""
    stack = limited_stack(TRUST_FORWARDED_FOR="1")
    a = {"X-Forwarded-For": "203.0.113.7"}
    b = {"X-Forwarded-For": "198.51.100.9"}
    codes_a = [stack.get("/", a)[0] for _ in range(PROXY_LIMIT + 3)]
    assert 429 in codes_a, codes_a
    assert stack.get("/", b)[0] == 200, "a second caller inherited A's exhausted bucket"


def test_forwarded_for_is_ignored_without_the_optin(limited_stack):
    """Default OFF: a forged XFF must NOT mint a fresh budget."""
    stack = limited_stack()  # TRUST_FORWARDED_FOR unset
    for i in range(PROXY_LIMIT + 3):
        code = stack.get("/", {"X-Forwarded-For": f"203.0.113.{i}"})[0]
        if code == 429:
            break
    else:
        pytest.fail("rotating X-Forwarded-For bypassed the per-IP budget")


def test_mutation_disabling_the_limiter_reopens_the_surface(limited_stack):
    """Paired §1.1 mutation: RATE_LIMIT_DISABLED=1 is the pre-fix RED baseline.

    If this case ever shows 429s the assertions above prove nothing — they
    would be passing on something other than the limiter.
    """
    stack = limited_stack(RATE_LIMIT_DISABLED="1")
    codes = [stack.get("/")[0] for _ in range(PROXY_LIMIT + 6)]
    assert 429 not in codes, f"429 appeared with the limiter disabled: {codes}"
    assert codes == [200] * len(codes), codes


# ---------------------------------------------------------------------------
# The mitigation must not become its own resource-exhaustion vector.
# ---------------------------------------------------------------------------


def test_refusal_logging_is_not_amplified_by_the_flood(limited_stack, caplog):
    """One WARNING per client per window, not one per refused request.

    MEASURED 2026-08-21 before the fix: a 604-request flood past a 600/minute
    budget produced 200 refusals AND 200 identical WARNING lines. A limiter
    that turns a refused flood into a log flood has moved the exhaustion from
    the request path to the disk (the `resource-exhaustion-under-attack`
    coverage BOB-074 records as missing), so this is a real defect, not tidiness.
    """
    import logging

    stack = limited_stack()
    with caplog.at_level(logging.WARNING, logger="download_proxy_rl_case"):
        for _ in range(PROXY_LIMIT + 25):
            stack.get("/")

    refusal_lines = [r for r in caplog.records if "Rate limited" in r.getMessage()]
    assert refusal_lines, "no refusal was logged at all — the event is now invisible"
    assert len(refusal_lines) == 1, (
        f"{len(refusal_lines)} WARNING lines for one client in one window — "
        "the refusal log is amplified by the flood it refuses"
    )


# ---------------------------------------------------------------------------
# IMPORTANT-1 — a malformed knob must not take the whole surface down.
# ---------------------------------------------------------------------------


def test_malformed_idle_reap_env_does_not_take_down_the_proxy(limited_stack):
    """A typo in RATE_LIMIT_IDLE_REAP_SECONDS must degrade loudly, not fatally.

    REPRODUCED 2026-08-21 before the fix: `RATE_LIMIT_IDLE_REAP_SECONDS=abc`
    raised ValueError at MODULE IMPORT. `main.py::start_original_proxy` catches
    it, logs "Original proxy failed", and :7186 never binds — a total WebUI
    outage caused by a typo in a knob this change introduced. That is the
    §11.4.201(1) false-refusal failure mode in its most extreme form: the guard
    does not refuse some requests, it refuses ALL of them by not existing.

    `_rl_parse_limit` already implements the loud-fallback shape; this knob
    must follow it.
    """
    stack = limited_stack(RATE_LIMIT_IDLE_REAP_SECONDS="abc")
    assert stack.get("/")[0] == 200, "the proxy did not serve under a malformed knob"
    assert stack.mod.RATE_LIMIT_IDLE_REAP_SECONDS == 900, (
        f"fell back to {stack.mod.RATE_LIMIT_IDLE_REAP_SECONDS}, not the documented default"
    )


def test_nonpositive_idle_reap_is_clamped_not_honoured(limited_stack):
    """A non-positive reap window would mass-evict live buckets on every call.

    `_reap` treats `now - last_seen > idle_reap` as "idle". With a negative or
    zero window that is true for EVERY bucket including the one just written,
    so once the map passes its half-cap the registry is wiped continuously and
    every attacker gets a fresh budget on demand — a silent disabling of the
    limiter dressed as a tuning knob.
    """
    stack = limited_stack(RATE_LIMIT_IDLE_REAP_SECONDS="-5")
    assert stack.mod.RATE_LIMIT_IDLE_REAP_SECONDS >= 1, (
        f"non-positive reap window {stack.mod.RATE_LIMIT_IDLE_REAP_SECONDS} was honoured"
    )
    codes = [stack.get("/")[0] for _ in range(PROXY_LIMIT + 4)]
    assert 429 in codes, f"limiter stopped enforcing under a negative reap window: {codes}"


# ---------------------------------------------------------------------------
# M1 — period grammar must match :7187's, including what it REJECTS.
# ---------------------------------------------------------------------------


def test_abbreviated_period_is_refused_loudly_not_silently_reinterpreted(limited_stack):
    """`100/s` must NOT quietly become `100/minute`.

    MEASURED 2026-08-21 against the `limits` library that backs :7187:

        limits.parse("10/second") -> 10 per 1 second
        limits.parse("10/s")      -> REJECTED ValueError
        limits.parse("10/m")      -> REJECTED ValueError

    :7187 refuses abbreviations. An earlier revision here used
    `.rstrip("s")`, which mapped the bare `"s"` to the empty string and then to
    the `"minute"` default — so an operator writing `100/s` got a window 60x
    LONGER than they asked for, with no error anywhere. Silent reinterpretation
    of an operator's configuration is a §11.4.6 violation; the documented
    behaviour is a loud fallback to the class default.
    """
    stack = limited_stack(RATE_LIMIT_PROXY="100/s")
    count, window = stack.mod._RATE_LIMITER.limit_for("proxy")
    assert (count, window) != (100, 60), (
        "'100/s' was silently reinterpreted as '100/minute' — a 60x divergence "
        "from the operator's stated intent"
    )
    assert (count, window) == (600, 60), (
        f"expected the loud fallback to the 600/minute default, got {count}/{window}s"
    )
    # Full period names, which :7187 DOES accept, must still work.
    assert limited_stack(RATE_LIMIT_PROXY="7/second").mod._RATE_LIMITER.limit_for("proxy") == (7, 1)
    assert limited_stack(RATE_LIMIT_PROXY="7/hour").mod._RATE_LIMITER.limit_for("proxy") == (7, 3600)


# ---------------------------------------------------------------------------
# IMPORTANT-3 — the mutual exclusion is load-bearing and must be OBSERVED.
# ---------------------------------------------------------------------------


def test_check_is_mutually_exclusive_under_concurrency(limited_stack):
    """Two threads must never be inside `check()`'s critical section at once.

    §11.4.115(F): an invariant never observed failing is unvalidated
    instrumentation. Every OTHER case in this file is sequential, so neutering
    `FixedWindowRateLimiter._lock` leaves them all GREEN while the limiter's
    counter loses updates and the effective budget inflates. :7186 is served by
    a THREADING server, so every concurrent request enters `check()` on its own
    thread and `used += 1` is a read-modify-write.

    THIS TEST ASSERTS THE MECHANISM (mutual exclusion). Its sibling
    `test_concurrent_check_does_not_lose_updates` asserts the CONSEQUENCE
    (counter consistency). BOTH are required and neither subsumes the other:
    this one dies if the lock is removed; only the sibling dies if the lock
    survives but the counter write is moved OUT of the region it protects.

    CORRECTION — an earlier revision of this docstring claimed a
    count-the-lost-updates test "CANNOT FAIL here no matter what the lock
    does". That was MEASURED-FALSE and is retracted (§11.4.6). The needle
    behind it was WRONG-SHAPED: a bare `v = d[k]; d[k] = v + 1` carries no
    interpreter checkpoint between read and write on this build, so it is
    switch-atomic BY CONSTRUCTION at any switch interval and could never have
    detected the defect. It did not share the certified path's load-bearing
    feature — the FUNCTION-CALL BOUNDARIES inside `check()`'s critical region,
    where a thread switch can land mid-window (§11.4.201(7)(b): a needle
    certifies only the query class it actually exercises). Re-measured on this
    host with the REAL `check()`, 8 threads x 30_000 calls:

        python 3.14.6, Py_GIL_DISABLED=False        interval 0.005   interval 1e-6
        bare subscript RMW, no lock                 lost=0           lost=0
        REAL check(), no lock                       lost=132,712     lost=129,048
        REAL check(), real lock                     lost=0           lost=0

    The real critical section loses >50% of its counter updates at the DEFAULT
    switch interval once the lock is gone.
    """
    stack = limited_stack()
    limiter = stack.mod.FixedWindowRateLimiter({"proxy": (10_000, 60)})

    parked = threading.Event()     # set once the first thread is INSIDE
    release = threading.Event()    # main thread lets the parked thread finish
    entered_second = threading.Event()
    state = {"occupancy": 0, "first": True}
    breaches = []

    original_reap = limiter._reap

    def instrumented_reap(now):
        # `_reap` is called by `check()` from INSIDE the lock, so occupancy > 1
        # here means two threads hold the critical section simultaneously.
        state["occupancy"] += 1
        if state["occupancy"] > 1:
            breaches.append(state["occupancy"])
            entered_second.set()
        if state["first"]:
            state["first"] = False
            parked.set()
            release.wait(5.0)      # hold the section open, bounded
        state["occupancy"] -= 1
        return original_reap(now)

    limiter._reap = instrumented_reap

    def call():
        limiter.check("10.0.0.1", "proxy")

    a = threading.Thread(target=call)
    a.start()
    assert parked.wait(5.0), "first thread never reached the critical section"

    b = threading.Thread(target=call)
    b.start()
    # With a real lock, b blocks on acquire and never reaches _reap. Without
    # one, it walks straight in. 1.5s is ~300x the 5ms switch interval.
    second_got_in = entered_second.wait(1.5)

    release.set()
    a.join(10)
    b.join(10)

    assert not second_got_in and not breaches, (
        f"MUTUAL EXCLUSION BREACHED: a second thread entered check()'s critical "
        f"section while another was inside it (occupancy={breaches}). "
        f"`used += 1` is a read-modify-write, so concurrent entrants read the "
        f"same counter and admissions are lost from it — the budget under-counts "
        f"and the effective limit inflates."
    )

    # The counter must also be exactly right after the forced overlap attempt:
    # two calls in, two recorded.
    assert limiter._buckets[("10.0.0.1", "proxy")][1] == 2, (
        f"counter = {limiter._buckets[('10.0.0.1', 'proxy')][1]}, expected 2 "
        f"admissions to be recorded"
    )


def test_concurrent_check_does_not_lose_updates(limited_stack):
    """The counter must record EVERY admission the limiter granted.

    THE CONSEQUENCE TEST, and the reason its sibling is not sufficient.
    `test_check_is_mutually_exclusive_under_concurrency` proves the lock
    EXCLUDES WHERE IT IS HELD. It cannot prove the whole read-modify-write sits
    INSIDE that region. A reviewer mutation (RM-2) kept the real
    `threading.Lock` and merely moved `self._buckets[key] = ...` and the return
    just outside the `with` block — a plausible "shorten the lock hold"
    refactor — and the entire suite, mutual-exclusion test included, stayed
    GREEN while the limiter lost tens of thousands of updates.

    THE ORACLE IS COUNTER CONSISTENCY, not admissions-at-the-refusal-boundary.
    Under an always-admit budget every call increments, so the race window is
    open for the whole run and `sum(admitted)` must equal the recorded `used`.
    A boundary oracle is weak by comparison: the reviewer's own first driver
    read an exact 1000 admissions off a lossy mutant, because the admission
    phase closes almost immediately once the budget is small.

    NOT FLAKY (§11.4.248 — flaky means differing verdicts on the SAME code).
    The lock makes this exactly consistent: measured 0 lost in every locked run
    at both switch intervals. A tightened switch interval only widens the
    margin against the mutants; correctness of the real code does not depend
    on it.
    """
    stack = limited_stack()
    # Always-admit budget: every one of the 240k calls takes the increment
    # path, so the counter race is exposed for the entire run.
    limiter = stack.mod.FixedWindowRateLimiter({"proxy": (10**9, 60)})
    key = ("10.0.0.1", "proxy")

    threads, per_thread = 8, 30_000
    admitted = [0] * threads
    barrier = threading.Barrier(threads)

    def worker(idx: int) -> None:
        barrier.wait()  # maximise real overlap inside check()
        n = 0
        for _ in range(per_thread):
            if limiter.check(*key)[0]:
                n += 1
        admitted[idx] = n

    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # margin only; not required for the verdict
    try:
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        sys.setswitchinterval(previous_interval)

    total_admitted = sum(admitted)
    recorded_used = limiter._buckets[key][1]

    assert total_admitted == threads * per_thread, (
        f"an always-admit budget refused {threads * per_thread - total_admitted} calls"
    )
    assert total_admitted == recorded_used, (
        f"LOST UPDATES: the limiter admitted {total_admitted} requests but "
        f"recorded only {recorded_used} — {total_admitted - recorded_used} "
        f"increments ({100 * (total_admitted - recorded_used) / total_admitted:.1f}%) "
        f"were lost. The read-modify-write of the bucket counter is not fully "
        f"inside the region the lock protects, so the budget under-counts and "
        f"the effective rate limit inflates."
    )


# ---------------------------------------------------------------------------
# The DEPLOYMENT path for this limiter (§11.4.224(A) / §11.4.196(F)).
#
# This lives beside the limiter's own tests because it guards the ONLY route by
# which the limiter reaches the running :7186. `download-proxy/src/main.py`
# imports `download_proxy` from ENGINES_DIR, not from plugins/ and not from the
# bind-mounted src tree, so if install-plugin.sh stops staging that module the
# limiter silently stops shipping — CM-PLUGIN-COUNT would not notice (it guards
# the roster COUNT, not this staging) and every test above would stay GREEN
# against source the container never loads.
# ---------------------------------------------------------------------------


def test_install_plugin_stages_the_infrastructure_modules(tmp_path):
    """`install-plugin.sh --local` must stage download_proxy.py + env_loader.py.

    Drives the REAL script through its REAL invocation path with HOME
    redirected into a temp tree, so it touches nothing the operator owns.
    """
    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    shutil.copy2(os.path.join(_REPO_ROOT, "install-plugin.sh"), sandbox / "install-plugin.sh")
    shutil.copytree(os.path.join(_REPO_ROOT, "plugins"), sandbox / "plugins")
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = dict(os.environ, HOME=str(fake_home))
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["bash", "install-plugin.sh", "--local", "rutracker"],
        cwd=sandbox, env=env, capture_output=True, text=True, timeout=300,
    )
    engines = fake_home / ".local/share/qBittorrent/nova3/engines"

    # The exit code is deliberately NOT asserted, and that is not an oversight.
    # `--local <one-plugin>` ends in verify_installation, which checks all 43
    # CURATED engines and therefore reports the other 42 missing and exits 1.
    # That is pre-existing behaviour of the one-plugin invocation, identical on
    # pristine and mutated code (measured: rc=1 in both), so it discriminates
    # nothing. What IS asserted is the staging step's own success marker plus
    # the bytes on disk — the real condition (§11.4.201).
    for module in ("download_proxy.py", "env_loader.py"):
        assert f"{module} staged (infrastructure module)" in proc.stdout, (
            f"install-plugin.sh never ran its INFRA_MODULES step for {module} "
            f"(rc={proc.returncode}).\nstdout tail:\n{proc.stdout[-1500:]}"
        )

    def md5(path):
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - file identity, not security

    for module in ("download_proxy.py", "env_loader.py"):
        staged = engines / module
        assert staged.is_file(), (
            f"{module} was NOT staged by install-plugin.sh (rc={proc.returncode}).\n"
            f"The :7186 limiter cannot reach the container through the documented "
            f"workflow.\nstdout tail:\n{proc.stdout[-1500:]}"
        )
        assert md5(staged) == md5(Path(_REPO_ROOT) / "plugins" / module), (
            f"{module} staged with different bytes than plugins/{module}"
        )

    # The staging step must never write into the repo's own config/ tree.
    assert not (sandbox / "config").exists(), (
        "--local mode wrote into the repo config/ tree"
    )
