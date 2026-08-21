"""Container writes MUST be owned by the operator who started the system.

Feature 002-user-owned-downloads · T004 (the RED) + T005 (honest skip).

THIS TEST IS EXPECTED TO FAIL until the ownership routes land in Phase 3. That
failure is the point: it reproduces the reported defect, and §11.4.115 requires
the RED to be OBSERVED against the genuinely-broken artifact before any fix.

WHY IT WRITES VIA ``s6-setuidgid abc`` AND NOT A BARE ``sh -c touch``
--------------------------------------------------------------------
The linuxserver images boot as root and drop the *application* to ``PUID`` via
s6. A bare ``sh -c 'touch ...'`` therefore runs as the container's ROOT
ENTRYPOINT, which the rootless mapping resolves to host uid 1000 — so it lands
on the operator either way and the test passes against a broken system.

This is not hypothetical. That exact mistake was made while researching this
feature: the first repro and its control both reported uid 1000 and
distinguished nothing, and reporting it would have concluded no defect existed
(research.md R1). Writing as the s6 application user is what reproduces the
real failing path.

WHAT "CORRECT" MEANS HERE
-------------------------
The file's owner uid, read from the HOST after the container exits, equals the
uid of the account running the test. Not "the container reported success", not
"no error occurred", not "the directory is owned by us" — those are proxies,
and §11.4.201 forbids asserting a proxy in place of the real condition.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

import pytest

# The image whose ownership behaviour this feature must fix. It is the service
# that writes downloads, so it is the one that matters.
IMAGE = "lscr.io/linuxserver/qbittorrent:latest"

# Generous: this may pull the image on a cold host. Still bounded, because an
# unbounded container run in a test suite is a §12 host-safety problem.
RUN_TIMEOUT_S = 300


def _runtime() -> str | None:
    """Return an available rootless container runtime, or None.

    Probed, never assumed — §11.4.6. A host without a runtime is a legitimate
    state, not a failure of this feature.
    """
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    return None


def _configured_puid_pgid() -> tuple[str, str]:
    """Read PUID/PGID for the qbittorrent service FROM docker-compose.yml.

    THIS IS THE LOAD-BEARING PART OF THIS TEST, and it is why the values are
    not written here as literals.

    A test that hardcodes ``PUID=1000`` asserts a permanent property of the
    IMAGE — "the linuxserver image, told to run its app as uid 1000, produces
    files at host uid 100999 under a rootless mapping". That is a true fact,
    and it is unfixable: no change to this project can make it false. A test
    that can never go green is not a RED, it is a restatement of how user
    namespaces work, and it would keep failing after the defect was fixed
    (§11.4.201(1) — a refusal that fires on a healthy system).

    What this feature actually changes is the CONFIGURATION. So the test reads
    the configuration and asks the question that matters: *does the system, as
    it is configured right now, write files this operator owns?* Reverting the
    fix in docker-compose.yml therefore turns this test red again, which is
    what makes it a regression guard rather than decoration (§1.1).
    """
    compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    doc = yaml.safe_load(compose.read_text())
    env = doc["services"]["qbittorrent"]["environment"]
    # `environment` may be a list of KEY=VALUE or a mapping; handle both rather
    # than assuming, because either is valid compose and a wrong assumption
    # here would silently test the wrong value.
    if isinstance(env, dict):
        found = {k: str(v) for k, v in env.items()}
    else:
        found = dict(
            item.split("=", 1) for item in env if isinstance(item, str) and "=" in item
        )
    try:
        return found["PUID"], found["PGID"]
    except KeyError as exc:  # pragma: no cover - a malformed compose file
        raise AssertionError(
            f"docker-compose.yml qbittorrent service declares no {exc.args[0]}. "
            f"This test cannot report on a configuration it cannot read; that "
            f"is a blind instrument, not a pass (§11.4.201(6))."
        ) from exc


def _container_cleanup(runtime: str, path: str) -> None:
    """Remove *path*'s contents from inside the user namespace.

    The application writes as a uid the operator does not own, so the operator
    CANNOT delete what it created — that is the defect under test. Python's
    TemporaryDirectory therefore raises PermissionError during teardown, and a
    test that dies in teardown is not a clean RED: the failure must come from
    the assertion, not the cleanup.

    ``podman unshare`` re-enters the same user namespace the container used, so
    those files appear owned by root and are removable. Verified on this host:
    three leftover trees that the operator could not delete were removed by
    ``podman unshare rm -rf``.

    Deliberately NOT ``ignore_cleanup_errors=True``: that would leave
    operator-undeletable directories behind on every run, and this host has
    already had /tmp reach 100%.

    Cleanup failure is never allowed to mask a test result — the caller runs
    this in a ``finally`` and this function swallows its own errors.
    """
    if runtime != "podman":
        return  # docker's rootless namespace entry differs; nothing safe to do
    try:
        subprocess.run(
            [runtime, "unshare", "rm", "-rf", path],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except Exception:
        pass


# T005: honest SKIP, not a failure, when the runtime is absent (§11.4.3).
# This test asserts a property of a CONTAINER; on a host with no container
# runtime the property is not false, it is unobservable. Failing here would be
# a §11.4.201(1) false-positive refusal — it would report a defect in the
# product when the only thing missing is the instrument.
pytestmark = pytest.mark.skipif(
    _runtime() is None,
    reason="no container runtime available (podman/docker) — "
    "container-write ownership is unobservable on this host",
)


@pytest.mark.requires_runtime
def test_container_written_file_is_owned_by_the_operator() -> None:
    """A file the containerised application writes must belong to the operator.

    RED (pre-fix):  owner uid is 100999 — an identity with no host account,
                    which is why it renders as UNKNOWN and why the operator
                    must chown after every download.
    GREEN (post-fix): owner uid equals the operator's.
    """
    runtime = _runtime()
    assert runtime is not None  # guarded by pytestmark

    operator_uid = os.getuid()

    # A directory the operator owns, bind-mounted into the container. Mode 777
    # so the in-container user can write regardless of which uid it maps to —
    # otherwise a permission error would mask the ownership question we are
    # actually asking.
    with tempfile.TemporaryDirectory(prefix="ownership-red-") as tmp:
      try:
        os.chmod(tmp, 0o777)
        target = Path(tmp) / "written_by_the_app"

        puid, pgid = _configured_puid_pgid()
        result = subprocess.run(
            [
                runtime, "run", "--rm",
                "-e", f"PUID={puid}",
                "-e", f"PGID={pgid}",
                "-v", f"{tmp}:/downloads:Z",
                IMAGE,
                "sh", "-c",
                # s6-setuidgid drops to the application user, reproducing the
                # real write path. See the module docstring for why a bare
                # touch would silently pass against a broken system.
                "s6-setuidgid abc touch /downloads/written_by_the_app",
            ],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
            check=False,
        )

        assert target.exists(), (
            "the container did not create the file at all, so this run says "
            "nothing about ownership — fix the harness before reading the "
            f"result.\nrc={result.returncode}\nstderr={result.stderr[-800:]}"
        )

        owner_uid = target.stat().st_uid

        assert owner_uid == operator_uid, (
            f"file written by the containerised application is owned by uid "
            f"{owner_uid}, but the operator is uid {operator_uid}.\n"
            f"The operator cannot rename, move, or delete it without first "
            f"reassigning ownership — the reported defect (FR-001).\n"
            f"uid {owner_uid} is the rootless user-namespace mapping of the "
            f"container's PUID; it has no host account, which is why it "
            f"renders as UNKNOWN."
        )
      finally:
        _container_cleanup(runtime, tmp)


@pytest.mark.requires_runtime
def test_container_written_directory_is_owned_by_the_operator() -> None:
    """FR-002: every level of a created tree, not only the leaf file.

    A fix that corrects files but leaves their containing directories wrongly
    owned still blocks the operator from moving or deleting the download.
    """
    runtime = _runtime()
    assert runtime is not None

    operator_uid = os.getuid()

    with tempfile.TemporaryDirectory(prefix="ownership-red-dir-") as tmp:
      try:
        os.chmod(tmp, 0o777)
        nested = Path(tmp) / "outer" / "inner"
        puid, pgid = _configured_puid_pgid()

        subprocess.run(
            [
                runtime, "run", "--rm",
                "-e", f"PUID={puid}",
                "-e", f"PGID={pgid}",
                "-v", f"{tmp}:/downloads:Z",
                IMAGE,
                "sh", "-c",
                "s6-setuidgid abc mkdir -p /downloads/outer/inner",
            ],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
            check=False,
        )

        assert nested.exists(), "the container did not create the tree at all"

        wrong = [
            (str(p), p.stat().st_uid)
            for p in (nested.parent, nested)
            if p.stat().st_uid != operator_uid
        ]
        assert not wrong, (
            f"directories created by the containerised application are not "
            f"owned by the operator (uid {operator_uid}): {wrong}\n"
            f"Every level of a created tree must be operator-owned (FR-002) — "
            f"a correct leaf inside a wrongly-owned parent still cannot be "
            f"moved or deleted."
        )
      finally:
        _container_cleanup(runtime, tmp)
