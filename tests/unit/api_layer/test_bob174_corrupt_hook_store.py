"""§11.4.135 regression guard for BOB-174 — a CORRUPT hook store must never read as ZERO hooks.

THE CHAIN (three defects, one data-loss path; see docs/qa/BOB-174/DESIGN_DECISION.md):

    A5  ``_save_hooks`` wrote with a plain ``open(path, "w")``. A crash, ENOSPC or a
        kill mid-write truncates the file IN PLACE — it MANUFACTURES the corruption.
    A1  ``_load_hooks`` wrapped its read in ``except Exception: return []``. That
        truncated file is then reported to every caller as an empty, healthy list.
    A2  ``create_hook`` loads, appends, saves. Given a corrupt file that load turned
        into ``[]``, the save writes a ONE-element list over the top. Every
        previously-configured hook is DESTROYED, HTTP 200 throughout.

Measured on the pre-fix tree (BOB-173 already landed, so this survives that fix):

    BEFORE  on disk : ['prod-hook-0', 'prod-hook-1', 'prod-hook-2']
    GET     reports : 200 {'hooks': [], 'count': 0}     <- claims ZERO configured
    DELETE  reports : 404 {'detail': 'Hook not found'}  <- for a hook that IS in the file
    POST    reports : 200 hook_id=...
    AFTER   on disk : ['<the new id>']

THE ROOT, and the decision this guard pins: a MISSING hooks file legitimately means
"no hooks configured"; a CORRUPT one does not. The pre-fix code could not tell them
apart and collapsed both to ``[]``. Every test below exists to keep those two states
distinguishable at the API surface.

ASSERTION LAYER (§11.4.226 / §11.4.262): every assertion is on a USER-OBSERVABLE
outcome — the HTTP status, the response body, or the BYTES ON DISK afterwards.
Nothing asserts on a log line; a log-only assertion would re-certify the exact bluff
the defect consists of. The on-disk assertions are the load-bearing ones: A2 is a
DATA-LOSS defect, and the only honest oracle for data loss is the surviving data.

NEGATIVE CONTROLS (§11.4.201(1)) — ``TestMissingFileIsNotCorruption`` and
``TestValidFileBehavesExactlyAsBefore``. A fix that makes every load fail closed by
failing ALWAYS is not a fix, it is a FAIL-bluff that refuses the healthy case. The
missing-file control is the sharp one: it is the state the pre-fix ``return []``
was actually CORRECT for, and it must keep working unchanged.

BOB-135 TRAP: ``monkeypatch.setattr`` is called with the MODULE OBJECT
(``api.hooks``), never the dotted string ``"api.hooks.HOOKS_FILE"``. The string form
resolves through the parent package ATTRIBUTE while ``api.app``'s router came from
the ``sys.modules`` entry; when those two diverge the patch lands on a module the app
does not use. ``_assert_single_hooks_module`` — the same guard BOB-173 established —
asserts they have not diverged, so this file can never silently patch the wrong
object.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


# --------------------------------------------------------------------------- #
# The operator's real data. Named so the destruction is legible in a diff.
# --------------------------------------------------------------------------- #
_PROD_HOOK_NAMES = ["prod-hook-0", "prod-hook-1", "prod-hook-2"]


def _prod_hooks(script_path: str) -> list[dict]:
    return [
        {
            "hook_id": f"seeded-{i}",
            "name": name,
            "event": "search_start",
            "script_path": script_path,
            "enabled": True,
            "timeout": 30,
            "environment": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        for i, name in enumerate(_PROD_HOOK_NAMES)
    ]


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _assert_single_hooks_module(hooks_mod) -> None:
    """Guard the BOB-135 two-live-modules split before trusting any patch."""
    assert sys.modules["api.hooks"] is hooks_mod
    assert sys.modules["api"].hooks is hooks_mod


class _HooksHarness:
    def __init__(self, client: TestClient, store_dir: Path, hooks_file: Path, scripts_dir: Path, mod):
        self.client = client
        self.store_dir = store_dir
        self.hooks_file = hooks_file
        self.scripts_dir = scripts_dir
        self.mod = mod

    # ---------------------------------------------------------------- seeding
    def make_script(self, name: str = "hook.sh") -> Path:
        script = self.scripts_dir / name
        script.write_text("#!/bin/sh\necho ok\n")
        script.chmod(0o755)
        return script

    def seed_valid_prod_hooks(self) -> str:
        """Three real hooks, written intact."""
        payload = _prod_hooks(str(self.make_script()))
        self.hooks_file.write_text(json.dumps(payload, indent=2))
        return self.hooks_file.read_text()

    def seed_truncated(self) -> str:
        """A file cut off mid-write — exactly what a crash/ENOSPC/kill leaves (A5).

        The operator's hook NAMES are still in the bytes, so the file is
        hand-recoverable. That recoverability is what A2 destroys, and what the
        on-disk assertions below protect.
        """
        full = json.dumps(_prod_hooks(str(self.make_script())), indent=2)
        truncated = full[: int(len(full) * 0.7)]
        assert "prod-hook-0" in truncated, "the seed must retain recoverable operator data"
        with pytest.raises(json.JSONDecodeError):
            json.loads(truncated)
        self.hooks_file.write_text(truncated)
        return truncated

    def seed_wrong_shape(self) -> str:
        """Valid JSON, wrong shape — a dict where the module contracts for a list.

        A DIFFERENT failure mode from truncation on purpose: it parses cleanly, so a
        fix that only hardened ``json.load`` would still collapse this to ``[]``.
        """
        body = json.dumps({"hooks": _prod_hooks(str(self.make_script()))}, indent=2)
        json.loads(body)  # proves it is valid JSON; only the SHAPE is wrong
        self.hooks_file.write_text(body)
        return body

    def seed_list_of_non_dicts(self) -> str:
        """A list, but not of hook objects. Every consumer here does ``h["..."]``."""
        body = json.dumps(["prod-hook-0", "prod-hook-1", "prod-hook-2"])
        self.hooks_file.write_text(body)
        return body

    # ------------------------------------------------------------- observation
    def create_payload(self, name: str = "bob174-new-hook") -> dict:
        return {"name": name, "event": "search_start", "script_path": str(self.make_script())}

    def on_disk_text(self) -> str:
        return self.hooks_file.read_text()

    def stray_temp_files(self) -> list[str]:
        return sorted(p.name for p in self.store_dir.iterdir() if p.name != self.hooks_file.name)


def _build_harness(store_dir: Path, scripts_dir: Path, monkeypatch) -> _HooksHarness:
    """Wire a fresh app against a store directory of the caller's choosing.

    Shared by both fixtures so the cross-device variant cannot drift from the
    ordinary one in how it patches — the patch discipline (module object, never
    the dotted string) is the BOB-135 trap this file's header documents.
    """
    monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
    hooks_file = store_dir / "hooks.json"
    monkeypatch.setenv("BOBA_HOOKS_DIR", str(scripts_dir))

    _purge_api_module()
    import api
    import api.hooks

    _assert_single_hooks_module(api.hooks)
    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(hooks_file))

    return _HooksHarness(TestClient(api.app), store_dir, hooks_file, scripts_dir, api.hooks)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    store_dir = tmp_path / "hooks-store"
    store_dir.mkdir()
    scripts_dir = tmp_path / "hooks"
    scripts_dir.mkdir()
    return _build_harness(store_dir, scripts_dir, monkeypatch)


def _a_directory_on_another_filesystem() -> str | None:
    """A writable dir whose st_dev differs from ``tempfile.gettempdir()``'s, or None.

    Probed rather than assumed: which mounts exist and which are separate
    filesystems is host-specific, so the candidates are TESTED, and a host where
    none qualifies gets an honest SKIP rather than a fabricated one.
    """
    try:
        base = os.stat(tempfile.gettempdir()).st_dev
    except OSError:
        return None
    for cand in ("/dev/shm", "/var/tmp", os.path.expanduser("~")):
        try:
            if os.path.isdir(cand) and os.access(cand, os.W_OK) and os.stat(cand).st_dev != base:
                return cand
        except OSError:
            continue
    return None


@pytest.fixture
def cross_device_harness(tmp_path, monkeypatch):
    """A harness whose STORE sits on a different filesystem from mkstemp's default.

    This is the only configuration in which a missing ``dir=`` kwarg produces its
    real production symptom, so it is staged for real rather than simulated: no
    ``os.replace`` is patched, no EXDEV is injected. The kernel raises it or it
    does not.
    """
    other = _a_directory_on_another_filesystem()
    if other is None:
        pytest.skip(
            "no second writable filesystem on this host, so a cross-device "
            "os.replace cannot be staged. The device-INDEPENDENT kwarg pin in "
            "TestAtomicWriteMechanicsArePinned is the guard that still runs here."
        )

    store_dir = Path(tempfile.mkdtemp(prefix="bob174-xdev-store-", dir=other))
    scripts_dir = tmp_path / "hooks"
    scripts_dir.mkdir()
    try:
        assert os.stat(store_dir).st_dev != os.stat(tempfile.gettempdir()).st_dev, (
            "the cross-device store landed on the SAME device as mkstemp's default; "
            "this fixture would then prove nothing (§11.4.201(6))"
        )
        yield _build_harness(store_dir, scripts_dir, monkeypatch)
    finally:
        shutil.rmtree(store_dir, ignore_errors=True)


# =========================================================================== #
# A1 — a corrupt store must not be reported as an empty, healthy one.
# =========================================================================== #
class TestCorruptStoreIsNotReportedAsZeroHooks:
    """GET must never answer a corrupt file with a confident 'nothing configured'."""

    @pytest.mark.parametrize("seed", ["seed_truncated", "seed_wrong_shape", "seed_list_of_non_dicts"])
    def test_get_does_not_claim_zero_hooks(self, harness, seed):
        getattr(harness, seed)()

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code >= 500, (
            "GET returned %d for an UNPARSEABLE hook store (%s). The operator's hooks "
            "may still be configured and firing; answering 'here is your hook list' "
            "about a file the server could not read is a false report, not a null "
            "result (BOB-174 / §11.4.201(6))." % (resp.status_code, seed)
        )
        body = resp.json()
        assert body.get("count") != 0, "a corrupt store must never be summarised as count=0"
        assert "hooks" not in body, (
            "an error response must not carry a 'hooks' key — a consumer reading the "
            "body without checking the status would see an empty list and believe it"
        )

    def test_a_directory_at_the_store_path_is_not_reported_as_zero_hooks(self, harness):
        """The rarer flavour of the same conflation: exists, but unusable.

        ``os.path.isfile`` is False for a directory, so the original guard —
        and a fix that kept ``isfile`` — reports a directory at the store path as
        "no hooks configured", which is the identical false report the item is
        about. Found by self-review rather than by the reported chain.
        """
        harness.hooks_file.mkdir()

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code >= 500, (
            "GET returned %d for a store path that exists but is not a readable file "
            "— 'exists but unusable' is not 'nothing configured'" % resp.status_code
        )

    def test_error_detail_names_the_problem_so_the_operator_can_fix_it(self, harness):
        """A 500 that says nothing is only marginally better than a lying 200."""
        harness.seed_truncated()

        detail = harness.client.get("/api/v1/hooks").json().get("detail", "")

        assert isinstance(detail, str) and detail, "the failure must carry a detail"
        assert "hook store" in detail.lower(), (
            "the detail must name WHAT is broken so the operator knows which file to "
            "repair; got %r" % detail
        )


# =========================================================================== #
# A2 — the data loss. The reason this item is High.
# =========================================================================== #
class TestCreateRefusesRatherThanDestroying:
    """§11.4.252 — mutation + external side effect on unverifiable input FAILS CLOSED."""

    @pytest.mark.parametrize("seed", ["seed_truncated", "seed_wrong_shape", "seed_list_of_non_dicts"])
    def test_create_is_refused_on_a_corrupt_store(self, harness, seed):
        getattr(harness, seed)()

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code >= 500, (
            "create returned %d against a store it could not parse. It is about to "
            "write a list it derived from a MISREAD of that file (BOB-174 A2)." % resp.status_code
        )
        assert "hook_id" not in resp.json(), "no id may be handed back for a refused create"

    @pytest.mark.parametrize("seed", ["seed_truncated", "seed_wrong_shape", "seed_list_of_non_dicts"])
    def test_the_operators_hooks_survive_the_refused_create(self, harness, seed):
        """THE data-loss assertion. Bytes on disk, before vs after.

        Pre-fix this file was overwritten with a one-element list and the operator's
        three hook definitions ceased to exist — not corrupted, GONE, with an HTTP
        200 saying it went fine.
        """
        before = getattr(harness, seed)()

        harness.client.post("/api/v1/hooks", json=harness.create_payload())

        after = harness.on_disk_text()
        assert after == before, (
            "the hook store was REWRITTEN by a create that could not read it. "
            "Content lost:\n  before: %r\n  after:  %r" % (before[:160], after[:160])
        )

    def test_recoverable_operator_data_is_still_recoverable(self, harness):
        """The human-repair path must survive: the names must still be in the bytes.

        Asserts on the names the truncated seed ACTUALLY still contains — a
        truncation by definition cut some of them off, and demanding those back
        would be the test asserting something no fix could deliver (§11.4.1).
        """
        seed = harness.seed_truncated()
        surviving = [name for name in _PROD_HOOK_NAMES if name in seed]
        assert surviving, "the seed must retain at least one recoverable hook name"

        harness.client.post("/api/v1/hooks", json=harness.create_payload())

        after = harness.on_disk_text()
        for name in surviving:
            assert name in after, (
                "%r was in the corrupt file and is no longer in the hook store. A "
                "truncated file is hand-repairable; an overwritten one is not. The "
                "create turned a recoverable state into an unrecoverable one." % name
            )


class TestDeleteRefusesRatherThanDestroying:
    """DELETE must not answer 404 about a file it never read, nor clobber it."""

    def test_delete_does_not_report_not_found_for_an_unreadable_store(self, harness):
        harness.seed_truncated()

        resp = harness.client.delete("/api/v1/hooks/seeded-1")

        assert resp.status_code != 404, (
            "delete returned 404 'Hook not found' for a hook that IS in the file — the "
            "server did not look, it failed to read and then reported absence (BOB-174)"
        )
        assert resp.status_code >= 500

    def test_the_store_survives_a_refused_delete(self, harness):
        before = harness.seed_truncated()

        harness.client.delete("/api/v1/hooks/seeded-1")

        assert harness.on_disk_text() == before, "a delete that could not parse the store rewrote it"


# =========================================================================== #
# A5 — the atomic write. Proving ATOMICITY, not merely that a write still happens.
# =========================================================================== #
class TestWriteIsAtomic:
    """A failure mid-write must leave the ORIGINAL file intact.

    This is the defect that MANUFACTURES the corrupt file A1 misreads and A2
    destroys — so it is proven here at its own layer, not assumed from the fact
    that healthy writes still land.

    The reproduction is faithful rather than synthetic: ``json.dump`` writes a
    partial fragment and THEN raises ENOSPC, which is precisely what a full disk or
    a kill mid-serialisation does. With a plain ``open(path, "w")`` the original is
    already truncated at OPEN time, so the fragment is all that survives. With
    tmp-file + ``os.replace`` the fragment lands in the temp file and the original
    is never touched.
    """

    @staticmethod
    def _arm_one_shot_enospc(monkeypatch) -> None:
        """Make the NEXT ``json.dump`` write a fragment and then fail with ENOSPC.

        ONE-SHOT, and deliberately so: an earlier draft restored the real
        ``json.dump`` with ``monkeypatch.undo()`` mid-test, which silently reverted
        EVERY patch the shared ``monkeypatch`` fixture instance had made —
        including the harness's ``HOOKS_FILE``. The app was thereby re-pointed at
        the real ``/config/download-proxy/hooks.json``, a GET read that
        (non-existent) path and returned an empty list, and the assertion failed
        for a reason that had nothing to do with the code under test. A §11.4.201
        instrument defect: had the expectation been ``== []`` it would have passed
        vacuously against production state. Self-restoring, so no undo is needed.
        """
        real_dump = json.dump
        state = {"fired": False}

        def _dump(obj, fp, **kwargs):
            if not state["fired"]:
                state["fired"] = True
                fp.write('[{"hook_id": "half-writ')
                raise OSError(28, "No space left on device")
            return real_dump(obj, fp, **kwargs)

        monkeypatch.setattr(json, "dump", _dump)

    def test_a_crash_mid_write_leaves_the_previous_store_intact(self, harness, monkeypatch):
        before = harness.seed_valid_prod_hooks()
        self._arm_one_shot_enospc(monkeypatch)

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code >= 500, "a failed write must still be reported (BOB-173)"
        assert harness.on_disk_text() == before, (
            "a write that FAILED PART-WAY left the store truncated. The previous "
            "contents are gone and what remains is the exact corrupt input that "
            "BOB-174's A1/A2 chain then reads as 'no hooks' and overwrites."
        )

    def test_the_surviving_store_is_still_parseable_after_a_failed_write(self, harness, monkeypatch):
        """The end-to-end consequence: the API still works afterwards."""
        harness.seed_valid_prod_hooks()
        self._arm_one_shot_enospc(monkeypatch)
        harness.client.post("/api/v1/hooks", json=harness.create_payload())

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code == 200, "the store should never have become unreadable"
        assert [h["name"] for h in resp.json()["hooks"]] == _PROD_HOOK_NAMES

    def test_no_partial_or_temp_file_is_left_observable_after_a_failed_write(self, harness, monkeypatch):
        harness.seed_valid_prod_hooks()
        self._arm_one_shot_enospc(monkeypatch)
        harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert harness.stray_temp_files() == [], (
            "a failed write left debris in the store directory: %s" % harness.stray_temp_files()
        )

    def test_no_temp_file_is_left_after_a_successful_write(self, harness):
        harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert harness.stray_temp_files() == [], (
            "a successful write left debris in the store directory: %s" % harness.stray_temp_files()
        )


class TestAtomicWriteMechanicsArePinned:
    """The two properties the atomic write DEPENDS on that no other assertion can see.

    Both are properties of HOW the write is performed rather than of what it leaves
    behind, so every other test in this file — all four of ``TestWriteIsAtomic``
    included — stays GREEN when either is removed. That is not a hypothesis: the
    independent review mutated each one away and the whole suite passed.

    (a) THE TEMP FILE MUST BE CREATED IN THE DESTINATION DIRECTORY, and this suite
        is STRUCTURALLY BLIND to it. ``os.replace`` is atomic only WITHIN a
        filesystem; across one it does not silently degrade, it RAISES. Measured
        on this host 2026-08-23:

            os.replace(<file under tempfile.gettempdir()>, <file under the repo>)
            -> OSError errno 18 (EXDEV) Invalid cross-device link

        The rest of this suite can never observe that, because pytest's
        ``tmp_path`` lives UNDER ``tempfile.gettempdir()`` — SAME st_dev, whatever
        that number happens to be on the day (it is a mount-local identifier, not a
        stable value, so it is deliberately not quoted here) — which makes
        ``mkstemp``'s default directory and the store directory the same filesystem
        in every ordinary test.
        In the container they are not — the store is the bind-mounted ``/config``
        while ``/tmp`` is the overlay — so dropping the kwarg is a latent
        PRODUCTION defect that would fail EVERY hook write while every test on
        every developer machine kept passing. The pin is therefore deliberately
        device-INDEPENDENT: it asserts the CALL, not the outcome, because the
        outcome is unobservable where the tests run (§11.4.201(7)(b) — a null from
        a blind instrument is not evidence). ``TestTheCrossDeviceFailureIsCaughtForReal``
        below is the complement: it stages the real two-filesystem condition and
        catches the actual EXDEV symptom where the host permits it.

    (b) THE TEMP FILE MUST BE FSYNCED BEFORE THE REPLACE. Durability is not
        in-process observable at all: after ``os.replace`` the new bytes are
        visible to every reader whether or not they ever reached the platter, so
        no assertion on the file, on the API or on the response can tell a synced
        write from an unsynced one. Only a real power-cut could, and that is not
        something a unit test can stage. Pinned on the CALL rather than merely
        recorded as an honest gap, because the call IS cheaply observable and the
        alternative is an unguarded line that the next "this fsync looks
        unnecessary" edit removes in silence.
    """

    @staticmethod
    def _record_write_mechanics(monkeypatch) -> list[tuple]:
        """Record the ordered mkstemp / fsync / replace calls of one write.

        Patched on the ``os`` and ``tempfile`` MODULE OBJECTS because ``hooks.py``
        resolves both through those modules at call time; the real functions are
        still invoked, so this observes the write without altering it.
        """
        calls: list[tuple] = []
        real_mkstemp, real_fsync, real_replace = tempfile.mkstemp, os.fsync, os.replace

        def _mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            calls.append(("mkstemp", {"kwargs": kwargs, "fd": fd, "path": path}))
            return fd, path

        def _fsync(fd):
            calls.append(("fsync", {"fd": fd}))
            return real_fsync(fd)

        def _replace(src, dst):
            calls.append(("replace", {"src": src, "dst": dst}))
            return real_replace(src, dst)

        monkeypatch.setattr(tempfile, "mkstemp", _mkstemp)
        monkeypatch.setattr(os, "fsync", _fsync)
        monkeypatch.setattr(os, "replace", _replace)
        return calls

    def test_the_temp_file_is_created_in_the_destination_directory(self, harness, monkeypatch):
        calls = self._record_write_mechanics(monkeypatch)

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code == 200, resp.text
        mkstemps = [d for name, d in calls if name == "mkstemp"]
        assert mkstemps, "no temp file was created at all — the write was not atomic"

        # THE load-bearing assertion: where the temp file ACTUALLY landed. Asserted
        # on the produced path rather than on the kwarg, because ``mkstemp`` accepts
        # ``dir`` POSITIONALLY too — keying the guard on the kwarg alone would refuse
        # a behaviourally-correct positional call, a §11.4.201(1) false-positive
        # refusal of exactly the kind this file's other guards exist to avoid.
        tmp_dir = os.path.realpath(os.path.dirname(mkstemps[-1]["path"]))
        assert tmp_dir == os.path.realpath(str(harness.store_dir)), (
            "the temp file was created in %r, NOT in the store directory %r. "
            "os.replace is atomic only WITHIN a filesystem, and across one it does "
            "not degrade — it RAISES EXDEV (errno 18, measured on this host). In the "
            "container the store is the bind-mounted /config while /tmp is the image "
            "overlay, so this fails on EVERY hook write. A same-device test host "
            "cannot see that, which is why this asserts placement directly."
            % (tmp_dir, str(harness.store_dir))
        )
        # NOTE: no second assertion on the ``dir`` KWARG. It would be a tautology —
        # unreachable once the placement assertion above has passed — and a test that
        # cannot fail is decoration (§11.4.224(C)). The kwarg is named in the message
        # above instead, where it belongs: as the likely cause, not as a gate.
        # The kwarg is only meaningful if the file it produced is the file that got
        # renamed; a correct 'dir' on a temp file nobody replaces in proves nothing.
        replaces = [d for name, d in calls if name == "replace"]
        assert replaces, "no os.replace — the write was not atomic"
        assert replaces[-1]["src"] == mkstemps[-1]["path"], (
            "the file renamed into place (%r) is not the temp file that was written "
            "(%r)" % (replaces[-1]["src"], mkstemps[-1]["path"])
        )
        assert os.path.realpath(replaces[-1]["dst"]) == os.path.realpath(str(harness.hooks_file))

    def test_the_temp_file_is_fsynced_before_the_replace(self, harness, monkeypatch):
        calls = self._record_write_mechanics(monkeypatch)

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code == 200, resp.text
        names = [name for name, _ in calls]
        assert "fsync" in names, (
            "the temp file was never fsynced. os.replace makes the SWAP atomic "
            "against a concurrent reader, but without the fsync the new bytes may "
            "still be only in the page cache when the rename lands — a power loss "
            "can then leave the store empty or short, which is precisely the "
            "corrupt file this item exists to stop manufacturing. Durability is not "
            "in-process observable, so the call is the only thing assertable."
        )
        assert "replace" in names, "no os.replace — the write was not atomic"
        assert names.index("fsync") < names.index("replace"), (
            "os.fsync ran AFTER os.replace (%r). Syncing the temp file once it is no "
            "longer the temp file does not make the replaced contents durable." % names
        )
        fsynced = [d["fd"] for name, d in calls if name == "fsync"]
        tmp_fd = [d["fd"] for name, d in calls if name == "mkstemp"][-1]
        assert tmp_fd in fsynced, (
            "fsync was called on fd(s) %r, none of which is the temp file's fd %d — "
            "the bytes synced are not the bytes being renamed into place"
            % (fsynced, tmp_fd)
        )


class TestTheCrossDeviceFailureIsCaughtForReal:
    """Stage the two-filesystem condition and let the kernel decide.

    ``TestAtomicWriteMechanicsArePinned`` asserts the ``dir=`` kwarg, which runs
    on every host but is a proxy for the property that actually matters. This
    class asserts the PROPERTY: put the hook store on a genuinely different
    filesystem from ``tempfile.gettempdir()``, drive a real create through the
    real API, and require it to work. Nothing is simulated — no ``os.replace``
    is patched and no EXDEV is injected. If the temp file is created in the
    wrong place, the kernel raises ``OSError errno 18 (EXDEV) Invalid
    cross-device link`` by itself and the create 500s.

    THIS IS THE CONTAINER'S GEOMETRY, not an exotic one: the store lives under
    the bind-mounted ``/config`` while ``/tmp`` is the image's overlay, so the
    two are different filesystems in every deployed instance. A hooks write is
    therefore cross-device in production and same-device in every ordinary test,
    which is exactly why this defect class can ship green.

    HONEST BOUNDARY (§11.4.3 / §11.4.201(6)): on a host that offers no second
    writable filesystem the fixture SKIPs with that reason rather than passing
    vacuously — a test that never reached its precondition has proven nothing,
    and saying so is the difference between a gap and a lie. The kwarg pin above
    is device-independent and still runs there.
    """

    def test_a_create_succeeds_when_the_store_is_on_another_filesystem(self, cross_device_harness):
        h = cross_device_harness
        assert os.stat(h.store_dir).st_dev != os.stat(tempfile.gettempdir()).st_dev

        resp = h.client.post("/api/v1/hooks", json=h.create_payload())

        assert resp.status_code == 200, (
            "creating a hook FAILED (%d) with the store on a different filesystem "
            "from tempfile.gettempdir(). If the detail mentions a cross-device link "
            "(EXDEV, errno 18), the temp file is being created outside the "
            "destination directory and os.replace cannot rename across the "
            "boundary — which is every hook write in the container, where the "
            "store is the bind-mounted /config and /tmp is the overlay. "
            "Response: %s" % (resp.status_code, resp.text)
        )
        assert [x["name"] for x in json.loads(h.on_disk_text())] == ["bob174-new-hook"], (
            "the create reported success but the hook is not in the store on disk"
        )

    def test_the_existing_hooks_survive_a_cross_filesystem_write(self, cross_device_harness):
        """The append path, not just the create-from-nothing path.

        A cross-device failure at this point is worse than a refused create: the
        operator already HAS hooks, and a write that cannot complete is the A5
        link that manufactures the corrupt store the rest of this file guards.
        """
        h = cross_device_harness
        h.seed_valid_prod_hooks()

        resp = h.client.post("/api/v1/hooks", json=h.create_payload())

        assert resp.status_code == 200, resp.text
        assert [x["name"] for x in json.loads(h.on_disk_text())] == [
            *_PROD_HOOK_NAMES,
            "bob174-new-hook",
        ]
        assert h.stray_temp_files() == [], (
            "debris left in a store directory on another filesystem: %s" % h.stray_temp_files()
        )


class TestNonOSErrorWriteFailureIsPinned:
    """BOB-173 review finding: the non-OSError arm of ``_save_hooks`` was unpinned.

    Mutating its ``except Exception`` to ``except OSError`` passed the entire existing
    suite. It is not reachable through the API today — every persisted field is
    parsed-JSON body content, a uuid4 string, an isoformat string, a bool or a bounded
    int — but it becomes reachable the moment anything richer is persisted, and the
    consequence of an unhandled serialisation error mid-write is a truncated fragment,
    which IS this item's chain. Pinned at the unit layer because the API cannot
    currently produce the input.
    """

    def test_a_serialisation_failure_raises_hook_persistence_error(self, harness):
        with pytest.raises(harness.mod.HookPersistenceError):
            harness.mod._save_hooks([{"x": object()}])

    def test_a_serialisation_failure_does_not_destroy_the_existing_store(self, harness):
        before = harness.seed_valid_prod_hooks()

        with pytest.raises(harness.mod.HookPersistenceError):
            harness.mod._save_hooks([{"x": object()}])

        assert harness.on_disk_text() == before


class TestDispatchFailsClosedWithoutBreakingUnrelatedRequests:
    """The one place a corrupt store is deliberately NOT propagated.

    ``dispatch_event`` is awaited INLINE from ``api/routes.py`` at EIGHT call sites
    (lines 488, 507, 598, 760, 1190, 1309, 1373, 1419 — counted by AST walk
    2026-08-23, not by grep; a bare grep also matches the five ``from .hooks import
    dispatch_event`` lines and reports 13). SEVEN of the eight have NO enclosing
    ``try``/``except`` — only line 507, inside ``_background()``, does — so an
    exception raised out of this coroutine reaches the request handler and becomes
    a 500. Driven end-to-end by the independent review: with the corrupt-store arm
    removed, a real corrupt store returned HTTP 500 from ``/api/v1/search``
    (routes.py:488) and ``/api/v1/download`` (routes.py:1190). That is a
    §11.4.201(1) false-positive refusal of unrelated capabilities, worse than the
    gap it would close. So it dispatches nothing (failing closed on the side
    effect) and returns.

    Both halves are asserted because each alone is satisfiable by a wrong
    implementation: "does not raise" alone is satisfied by dispatching hooks read
    from a misparse, and "dispatches nothing" alone is satisfied by raising.
    Reasoning: docs/qa/BOB-174/DESIGN_DECISION.md §3.
    """

    async def test_dispatch_does_not_raise_on_a_corrupt_store(self, harness):
        harness.seed_truncated()

        await harness.mod.dispatch_event("search_start", {"query": "x"})

    async def test_dispatch_runs_no_hooks_on_a_corrupt_store(self, harness):
        """Fail closed: an unknown hook set means none run, never a guessed subset."""
        harness.seed_truncated()
        from merge_service.hooks import get_dispatcher

        await harness.mod.dispatch_event("search_start", {"query": "x"})

        assert get_dispatcher().get_execution_log() == [], (
            "a hook was executed off a store the server could not parse"
        )


# =========================================================================== #
# NEGATIVE CONTROLS (§11.4.201(1)) — the fix must not refuse the healthy cases.
# =========================================================================== #
class TestMissingFileIsNotCorruption:
    """The sharp control: MISSING legitimately means 'no hooks configured'.

    This is the state the pre-fix ``return []`` was CORRECT for. Collapsing it into
    the corrupt case would be a false-positive refusal — a fresh install would 500 on
    its hooks tab and refuse every create, which is worse than the defect being fixed.
    """

    def test_get_returns_an_empty_list_when_no_store_exists(self, harness):
        assert not harness.hooks_file.exists()

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"hooks": [], "count": 0}

    def test_create_works_on_a_fresh_install(self, harness):
        assert not harness.hooks_file.exists()

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code == 200, resp.text
        hook_id = resp.json()["hook_id"]
        assert [h["hook_id"] for h in json.loads(harness.on_disk_text())] == [hook_id]

    def test_an_empty_json_list_is_a_healthy_store_not_a_corrupt_one(self, harness):
        """``[]`` is what a delete-the-last-hook leaves behind. It must stay healthy."""
        harness.hooks_file.write_text("[]")

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"hooks": [], "count": 0}


class TestValidFileBehavesExactlyAsBefore:
    """A valid store must behave exactly as it did — read, append, delete."""

    def test_get_lists_the_configured_hooks(self, harness):
        harness.seed_valid_prod_hooks()

        resp = harness.client.get("/api/v1/hooks")

        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 3
        assert [h["name"] for h in resp.json()["hooks"]] == _PROD_HOOK_NAMES

    def test_create_appends_and_preserves_the_existing_hooks(self, harness):
        harness.seed_valid_prod_hooks()

        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code == 200, resp.text
        names = [h["name"] for h in json.loads(harness.on_disk_text())]
        assert names == [*_PROD_HOOK_NAMES, "bob174-new-hook"]

    def test_delete_removes_only_the_named_hook(self, harness):
        harness.seed_valid_prod_hooks()

        resp = harness.client.delete("/api/v1/hooks/seeded-1")

        assert resp.status_code == 200, resp.text
        names = [h["name"] for h in json.loads(harness.on_disk_text())]
        assert names == ["prod-hook-0", "prod-hook-2"]

    def test_delete_of_an_absent_hook_still_404s_on_a_valid_store(self, harness):
        harness.seed_valid_prod_hooks()

        resp = harness.client.delete("/api/v1/hooks/no-such-hook")

        assert resp.status_code == 404, (
            "the corrupt-store guard must not swallow the ordinary not-found path"
        )


# =========================================================================== #
# A3 — the two-sources-of-truth pin (recorded separately in the item).
# =========================================================================== #
class TestEventVocabularyCannotDrift:
    """``VALID_EVENTS`` is DERIVED from ``HookEventType``; these guard the derivation.

    THE CONSEQUENCE, if the two ever diverge: a hook whose event is in
    ``VALID_EVENTS`` but not in ``HookEventType`` registers with HTTP 200 and then
    NEVER FIRES — ``dispatch_event`` resolves the enum first and returns early on
    ``ValueError``, logging a warning nobody reads. Silent, permanent, and reported
    as success: the same false-null shape as the chain above, one layer over.

    WHAT THESE ASSERTIONS NOW TARGET (changed, and the change is the point). They
    were written when ``VALID_EVENTS`` was a hand-maintained literal, to DETECT two
    sources of truth drifting apart. ``VALID_EVENTS`` is now
    ``[event.value for event in HookEventType]``, so that drift is no longer
    representable and against the source as it stands these assertions cannot fail
    — §11.4.241 rung 2 replaced rung 4. They are NOT dead, and were not deleted:
    what they guard now is the DERIVATION ITSELF being reverted to a literal that
    diverges. Measured 2026-08-23 rather than argued — replacing the comprehension
    with a hardcoded list carrying one extra event fails BOTH of them (2 failed,
    31 passed), so the mutation that matters is caught and the guard is
    load-bearing at its new target.

    The earlier rationale for pinning instead of deriving ("unifying them means
    editing ``merge_service/hooks.py``, outside this item's scope and live under a
    sibling stream") was measured FALSE on all three counts by the independent
    review and is corrected here rather than quietly dropped (§11.4.194(2)):
    ``merge_service/hooks.py`` is untouched, the change was one line in
    ``api/hooks.py``, and ``merge_service.hooks`` imports only stdlib so there is
    no import cycle.
    """

    def test_the_two_event_vocabularies_are_identical(self, harness):
        from merge_service.hooks import HookEventType

        assert set(harness.mod.VALID_EVENTS) == {e.value for e in HookEventType}, (
            "VALID_EVENTS and HookEventType have drifted. An event accepted by the "
            "create endpoint but absent from the enum registers successfully and then "
            "never fires."
        )

    def test_every_accepted_event_is_dispatchable(self, harness):
        """The consequence stated directly, in the direction that loses events."""
        from merge_service.hooks import HookEventType

        for event in harness.mod.VALID_EVENTS:
            HookEventType(event)  # raises ValueError if the create endpoint accepts a dead event
