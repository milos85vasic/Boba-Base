"""BOB-065 — RED-first / TDD tests for ``scripts/egress-via-vpn.sh``.

Ports Lava PLAYBOOK §0/§4 (egress diagnosis + VPN-host SOCKS routing) per
``docs/PORTING-FROM-LAVA.md`` P2. The Go backend (``submodules/containers``
``pkg/egress`` — ``TunnelUp``/``Verify``/``DirectEgressIP``) and the shell
glue (``scripts/egress-via-vpn.sh``) both already existed before this file
was authored: they landed in commit ``be5062d`` (2026-07-01), citing the
containers submodule's own ``cde354f`` (feat) + ``e273fd2``/``3a52825``
(Wave-20 hardening). What this file adds is the MISSING test coverage the
shell wrapper never had (its only prior verification was a bare
``bash -n`` syntax check, cited in ``be5062d``'s own commit message) — never
a re-implementation of the wrapper or the Go package.

Investigation note (§11.4.102 systematic-debugging, captured 2026-09-25):
this test file's own filename was originally going to be authored under
``constitution/submodules/containers/pkg/egress`` — that path does NOT
exist and is NOT what the containers submodule referenced by
``docs/PORTING-FROM-LAVA.md`` (and by BOB-065's own item text) means. The
"containers submodule" the porting playbook and this project's stack
actually consume is the project-ROOT ``submodules/containers``
(``.gitmodules`` → ``git@github.com:vasic-digital/Containers.git``), which
already has a fully implemented, hardened, and unit-tested ``pkg/egress``
(``go test ./pkg/egress/...`` → 12/12 PASS, captured
``docs/qa/BOB-065/investigation_20260925.md``). ``constitution/submodules/
containers`` is a DIFFERENT, unrelated nested submodule (constitution's own
dependency tree) with no ``pkg/`` directory at all. Creating a duplicate
egress implementation there would be a §11.4.251 byte-identical-fork /
§11.4.124 dead-code violation against a component that already works.

What THIS environment genuinely has and lacks (§11.4.3 SKIP-with-reason,
never a fabricated PASS):

* HAS: real outbound network access — the "direct" (unproxied) half of the
  diagnosis is exercised for real against the live host, below.
* LACKS: any VPN host reachable over SSH (no ``BOBA_VPN_HOST`` configured,
  no host provisioned or provisionable in this sandbox). Every test that
  needs a LIVE SOCKS tunnel is environment-gated on ``BOBA_VPN_HOST`` and
  SKIPs honestly when it is unset — it is NOT a failure of this suite, it
  is the correct, documented outcome until an operator configures a real
  VPN host (see the item's own acceptance criterion: "assert the via-proxy
  egress IP != direct host IP AND a known-blocked tracker returns 200 via
  proxy").
"""

from __future__ import annotations

import ipaddress
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "egress-via-vpn.sh"

VPN_HOST = os.environ.get("BOBA_VPN_HOST", "")
IP_ECHO = os.environ.get("BOBA_EGRESS_IP_ECHO", "https://api.ipify.org")
# A tracker this project already treats as tracker-domain traffic (see
# CLAUDE.md's tracker list). Any target works for the direct-probe half;
# for the live via-proxy assertion an operator overrides via
# BOBA_EGRESS_LIVE_TARGET with a domain KNOWN blocked from the host under
# test, per the item's own diagnosis method.
DEFAULT_TARGET = os.environ.get("BOBA_EGRESS_LIVE_TARGET", "https://rutracker.org/")

requires_vpn_host = pytest.mark.skipif(
    not VPN_HOST,
    reason=(
        "SKIP: no VPN host configured (§11.4.3) — set BOBA_VPN_HOST to a "
        "reachable ssh destination (e.g. user@vpnhost) to exercise the live "
        "SOCKS-tunnel-and-routing acceptance criterion (BOB-065)"
    ),
)


def _run(*args: str, env: dict | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), f"{SCRIPT} must exist (containers-pkg/egress shell glue)"
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} must be executable"


def test_bash_syntax_clean() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


def test_usage_with_no_subcommand_exits_2_and_lists_all_four_verbs() -> None:
    """No subcommand -> honest usage message, never a silent no-op."""
    result = _run()
    assert result.returncode == 2, result.stderr
    for verb in ("up", "verify", "diagnose", "down"):
        assert verb in result.stdout + result.stderr, (
            f"usage message must mention '{verb}': {result.stdout!r} {result.stderr!r}"
        )


def test_up_without_host_configured_fails_loud_never_silent() -> None:
    """BOB-065 anti-bluff requirement: a missing VPN host MUST fail loud
    (§11.4.201 — never a false-positive 'tunnel is up' with no real ssh
    child), never silently report readiness. Runs with BOBA_VPN_HOST
    explicitly cleared regardless of the ambient environment."""
    env = dict(os.environ)
    env.pop("BOBA_VPN_HOST", None)
    result = subprocess.run(
        [str(SCRIPT), "up"],
        cwd=REPO_ROOT,
        env={k: v for k, v in env.items() if k != "BOBA_VPN_HOST"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2, (
        f"expected exit 2 with no VPN host configured, got {result.returncode}: "
        f"{result.stdout!r} {result.stderr!r}"
    )
    assert "BOBA_VPN_HOST" in (result.stdout + result.stderr)


def test_verify_without_a_live_tunnel_fails_honest_never_fakes_success() -> None:
    """Calling `verify` against a port with nothing listening MUST fail
    (exit 1) rather than report a fabricated egress IP — a dead tunnel is
    never a green verify (§11.4/§11.4.1 anti-bluff)."""
    # Use a port astronomically unlikely to have a real SOCKS listener.
    result = _run("verify", "--port", "1", env={"BOBA_VPN_HOST": ""})
    assert result.returncode == 1, (
        f"expected exit 1 against a dead SOCKS port, got {result.returncode}: "
        f"{result.stdout!r} {result.stderr!r}"
    )
    assert "FAIL" in (result.stdout + result.stderr)


def test_diagnose_direct_probe_returns_the_real_current_host_egress_ip() -> None:
    """The 'direct' half of `diagnose` needs NO VPN host — it is real,
    genuinely-testable-now evidence of this host's CURRENT (unproxied)
    egress IP and its CURRENT reachability of a tracker target. This is
    the diagnosis half of BOB-065's acceptance criterion this environment
    can actually prove; the via-proxy half is exercised only when
    BOBA_VPN_HOST is configured (see the requires_vpn_host-marked test
    below)."""
    result = _run("diagnose", DEFAULT_TARGET, "--port", "1")
    combined = result.stdout + result.stderr
    assert "direct_egress_ip=" in combined, combined
    ip_line = next(
        line for line in combined.splitlines() if line.startswith("direct_egress_ip=")
    )
    ip_value = ip_line.split("=", 1)[1].strip()
    # Real assertion, not a bare presence check: the reported value MUST be
    # a syntactically valid IP address (proves the script actually parsed a
    # real curl response, never an empty/garbage string masquerading as one).
    ipaddress.ip_address(ip_value)
    assert f"direct  {DEFAULT_TARGET} -> " in combined, combined
    # The via-proxy half MUST be attempted and MUST fail honestly (no
    # tunnel is up in this call) — proving `diagnose` never silently skips
    # the via-proxy comparison it's supposed to make.
    assert "via proxy" in combined
    assert "FAIL" in combined or "tunnel dead" in combined


@requires_vpn_host
def test_live_via_proxy_egress_ip_differs_and_blocked_tracker_returns_200() -> None:
    """THE canonical BOB-065 acceptance test, verbatim from the item text:
    'assert the via-proxy egress IP != direct host IP AND a known-blocked
    tracker returns 200 via proxy'. Runs for real ONLY when an operator
    has configured BOBA_VPN_HOST to a reachable VPN-connected host; SKIPs
    honestly otherwise (see module docstring)."""
    port = os.environ.get("BOBA_EGRESS_SOCKS_PORT", "12080")
    try:
        up = _run("up", "--port", port, timeout=30)
        assert up.returncode == 0, f"tunnel up failed: {up.stdout} {up.stderr}"

        direct = subprocess.run(
            ["curl", "-fsS", "--max-time", "20", IP_ECHO],
            capture_output=True,
            text=True,
            timeout=25,
        )
        assert direct.returncode == 0, "direct egress IP fetch failed"
        direct_ip = direct.stdout.strip()
        ipaddress.ip_address(direct_ip)

        verify = _run("verify", "--port", port, DEFAULT_TARGET, timeout=40)
        assert verify.returncode == 0, f"verify failed: {verify.stdout} {verify.stderr}"
        out = verify.stdout
        proxy_ip_line = next(
            line for line in out.splitlines() if line.startswith("egress_ip_via_proxy=")
        )
        proxy_ip = proxy_ip_line.split("=", 1)[1].strip()
        ipaddress.ip_address(proxy_ip)

        # THE acceptance assertion.
        assert proxy_ip != direct_ip, (
            f"via-proxy egress IP ({proxy_ip}) must differ from the direct "
            f"host IP ({direct_ip}) — routing did not actually change egress"
        )
        target_line = next(
            line for line in out.splitlines() if line.startswith(f"target {DEFAULT_TARGET}")
        )
        assert target_line.strip().endswith("200"), (
            f"expected 200 via proxy for {DEFAULT_TARGET}, got: {target_line}"
        )
    finally:
        _run("down", "--port", port)
