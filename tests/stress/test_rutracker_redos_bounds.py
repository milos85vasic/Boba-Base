"""BOB-093 · rutracker ReDoS bounds — BEHAVIOURAL regression guard (§11.4.85).

The sibling structural guard in ``tests/unit/test_plugin_rutracker.py`` reads
the pattern SOURCE.  This one measures what the compiled regex actually COSTS,
because a source check is source-class evidence for a runtime-class claim
(§11.4.226) and a differently-spelled unbounded scan would slip past it.

Measured 2026-08-21 (min-of-3, host under normal agent load):

    attack           regex             pre-fix              post-fix
    -------------------------------------------------------------------
    tr_storm         re_threads        9.46s @ 64 KB (n^2)  0.79s (linear)
    gtlt_storm       re_torrent_data   25.80s @ 2 KB (n^3)  0.000004s (flat)
    ts_text_storm    re_torrent_data   2.92s @ 4 KB         0.089s (flat)

Host safety (§12.6/§12.12): single-threaded, no parallelism, every attack size
chosen so the pre-fix golden-bad measurement itself stays under ~10s.  Python
signal handlers CANNOT interrupt a running ``re.search`` (one uninterruptible C
call), so an in-test alarm is not a sound bound — sizes are bounded instead.
"""

import importlib.util
import json
import os
import re
import sys
import time
import types

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACT_DIR = os.path.join(REPO, "qa-results", "redos_bounds")

# The exact patterns that shipped before the BOB-093 fixes — the permanent
# golden-bad fixtures (§11.4.107(10)).  Every run re-proves the harness can
# still SEE the blow-up, so a broken timer cannot silently pass everything.
HIST_THREADS = re.compile(r'<tr id="trs-tr-\d+.*?</tr>', re.S)
HIST_TD = re.compile(
    r'a data-topic_id="(?P<id>\d+?)".*?>(?P<title>.+?)<'
    r".+?"
    r'data-ts_text="(?P<size>\d+?)"'
    r".+?"
    r'data-ts_text="(?P<seeds>[-\d]+?)"'
    r".+?"
    r"leechmed.+?>(?P<leech>\d+?)<"
    r".+?"
    r'data-ts_text="(?P<pub_date>\d+?)"',
    re.S,
)


def _rutracker_class():
    """Load the plugin's class WITHOUT instantiating it (no login, no HTTP)."""
    sys.modules.setdefault("novaprinter", types.ModuleType("novaprinter"))
    sys.modules["novaprinter"].prettyPrinter = lambda d: None
    env_mod = types.ModuleType("env_loader")
    env_mod.load_env_files = lambda *a, **kw: None
    sys.modules.setdefault("env_loader", env_mod)
    sys.modules.pop("rutracker", None)
    path = os.path.join(REPO, "plugins", "rutracker.py")
    spec = importlib.util.spec_from_file_location("rutracker", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rutracker"] = mod
    spec.loader.exec_module(mod)
    cls = getattr(mod, "rutracker", None)
    if not isinstance(cls, type):
        cls = mod.RuTracker
    return cls


# ─── adversarial inputs ───────────────────────────────────────────────────
def tr_storm(k):
    """Many row-starts, no ``</tr>`` anywhere: every start scans to EOF."""
    return '<tr id="trs-tr-1' * k


def gtlt_storm(k):
    """A ``><`` storm: every ``>`` and every ``<`` is a backtrack point."""
    return 'a data-topic_id="1"' + "><" * k


def ts_text_storm(k):
    """Many ``data-ts_text`` hits where the final group is never satisfied."""
    return 'a data-topic_id="1">t<' + 'data-ts_text="1"' * k


def _best(rx, s, op, reps=3):
    """Min-of-N — the robust estimator when other agents share the host."""
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        rx.findall(s) if op == "findall" else rx.search(s)
        out.append(time.perf_counter() - t0)
    return min(out)


# attack, builder, k, op, cap_s, live-regex attribute
# Two discriminator shapes, because the two failure modes differ:
#
#   "absolute" — for the flat cases.  The fix is ~5 orders of magnitude faster
#     than the pre-fix pattern (>=80x margin even against the cap), so host load
#     cannot close the gap and a fixed cap is the clearest signal.
#
#   "relative" — for tr_storm.  Here the fix is linear and the pre-fix is
#     quadratic, so the honest gap is ~15x, not ~80x, and BOTH halves inflate
#     together under load.  A fixed cap therefore FALSE-FAILS on correct code:
#     an independent review measured live_s = 4.13s against a 0.98s idle
#     baseline (4.2x inflation under 3-agent load) and the 3.5s cap failed with
#     zero code defect — a §11.4.201(1) FAIL-bluff and exactly the
#     re-run-until-green trainer (§11.4.248) the removed ratio test was.
#     Comparing the two halves measured in the SAME run cancels the shared
#     inflation.  Measured separations: idle 13.03/0.89 = 14.6x; under 3-agent
#     load 38.1/4.13 = 9.2x; a quadratic regression 11.2/10.3 = 1.09x.  A 4x
#     threshold sits with >2x margin on both sides.  The absolute arm is kept
#     only as a loose sanity ceiling, not as the discriminator.
CASES = [
    # attack, builder, k, op, mode, param, attr, historical
    ("tr_storm", tr_storm, 6000, "findall", "relative", 4.0, "re_threads", HIST_THREADS),
    ("gtlt_storm", gtlt_storm, 500, "search", "absolute", 0.5, "re_torrent_data", HIST_TD),
    ("ts_text_storm", ts_text_storm, 500, "search", "absolute", 1.0, "re_torrent_data", HIST_TD),
]

# Loose ceiling for the relative case: catches a regression so slow that even
# the ratio would be misleading. Deliberately far above any load-inflated
# healthy reading (review measured 4.13s under 3-agent load).
RELATIVE_SANITY_CEILING_S = 10.0

# Teeth-check thresholds. BOTH are RELATIVE or floor-shaped for the same
# reason the tr_storm discriminator is: an ABSOLUTE floor on `hist_s` alone is
# not clock-invariant. Second review measured the historical gtlt_storm at
# 0.4887s / 0.465 / 0.453 / 0.452s once host load fell to ~1.3 and cores
# boosted to 2.7GHz -- all UNDER the old 0.5s floor, so the teeth-check
# FALSE-FAILED on healthy code. Cause established, not guessed: the earlier
# 1.70s "idle" baseline was taken with cores at powersave clocks under
# contention, and the same measurement runs ~3.7x faster boosted. A 3.4x floor
# margin cannot survive 3.7x clock-state variance; ts_text was the next domino
# at 5.4x. Both halves share the clock, so a RATIO cancels the variance
# entirely -- the identical argument already used for tr_storm.
# Observed separations across FOUR distinct box states (powersave-under-
# contention, 2.7GHz boost, 3.4GHz boost, mixed): gtlt_storm 467986-846316x,
# ts_text_storm 566-1052x -> a 100x threshold sits 5.7x above the worst arm's
# worst-ever reading. Round-3 review confirmed the form against a 3.4GHz state
# it was NOT tuned for: historical gtlt measured 0.571s and 0.563s there, which
# the retired 0.5s absolute floor would have made a coin flip AGAIN, while the
# relative form read 831717x.
FLAT_TEETH_MIN_SEPARATION_X = 100.0
# Floor on the historical arm of the relative case. Observed hist range across
# every box state: 3.08-38.1s, so >=3.1x margin. This is the ONE absolute
# constant left in the harness, so its exposure is stated explicitly rather
# than assumed:
#   - The 3.08s low was measured AT MAX BOOST (load ~1.4-3): review recorded
#     four samples 3.29/3.82/4.11/4.18s, and a following 8-sample run in the
#     same state extended the low to 3.084s (3.08-3.89s, min-of-8). Unlike the
#     R2-1 floor, there is no faster state on THIS hardware waiting to cross
#     it -- that is the structural reason this is not R2-1 repeating.
#   - Residual intra-state noise is 1.26x against a 3.1x margin.
#   - The VALUE is not load-bearing for the detection role it exists for:
#     review weakened it 1000x to 0.001s and the dead-timer and broken-payload
#     classes were STILL caught, because they sit 5-6 orders below any sane
#     floor. It sits mid-way in a ~3-order-wide valid band.
#   - Known cost, accepted: a ~3.1x-faster single-thread host would false-FAIL
#     this floor LOUDLY (never silently), and the derivation above makes the
#     retune straightforward.
# It exists to kill the dead-timer path: with `_best` stubbed to 0.0 the ratio
# arm used to read `float("inf")` and PASS, because it had dropped the
# teeth-check the absolute arms kept (§11.4.107(10) self-validation).
RELATIVE_TEETH_MIN_HIST_S = 1.0


@pytest.mark.parametrize("attack,build,k,op,mode,param,attr,hist", CASES, ids=[c[0] for c in CASES])
def test_regex_stays_bounded_and_guard_sees_the_prefix_blowup(attack, build, k, op, mode, param, attr, hist):
    """Live regex bounded AND the same harness showing the pre-fix one is not.

    Both halves are required.  The first alone could pass because the timer is
    broken; the second (§1.1 / §11.4.115(F)) proves the timer really measures
    catastrophic backtracking on the genuinely-broken artifact.
    """
    rx = getattr(_rutracker_class(), attr)
    payload = build(k)

    live_s = _best(rx, payload, op)
    hist_s = _best(hist, payload, op, reps=1)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    if mode == "absolute":
        ok = live_s <= param and hist_s > FLAT_TEETH_MIN_SEPARATION_X * live_s
    else:
        ok = hist_s > RELATIVE_TEETH_MIN_HIST_S and hist_s > param * live_s and live_s <= RELATIVE_SANITY_CEILING_S
    with open(os.path.join(ARTIFACT_DIR, f"rutracker_{attack}.json"), "w") as fh:
        json.dump(
            {
                "item": "BOB-093",
                "attack": attack,
                "regex": attr,
                "k": k,
                "payload_bytes": len(payload),
                "mode": mode,
                "param": param,
                "live_s": round(live_s, 6),
                "historical_vulnerable_s": round(hist_s, 6),
                "separation_x": round(hist_s / live_s, 2) if live_s else None,
                "verdict": "PASS" if ok else "FAIL",
            },
            fh,
            indent=1,
        )

    separation = hist_s / live_s if live_s else 0.0

    if mode == "absolute":
        # Teeth-check, clock-invariant: both halves are measured in the same
        # run on the same cores, so their RATIO is immune to the clock-state
        # variance that broke the old absolute floor. `0 > 100*0` is False, so
        # a dead timer fails here too.
        assert hist_s > FLAT_TEETH_MIN_SEPARATION_X * live_s, (
            f"guard has no teeth: the historical vulnerable {attr} was only "
            f"{separation:.1f}x slower than the bounded one on {attack} (k={k}, "
            f"{len(payload)} bytes): historical {hist_s:.4f}s vs live "
            f"{live_s:.6f}s. Expected >={FLAT_TEETH_MIN_SEPARATION_X:.0f}x "
            f"(observed 566x-846316x across four box states). The harness "
            f"cannot see the blow-up it "
            f"exists to catch."
        )
        assert live_s <= param, (
            f"BOB-093 ReDoS regression: {attr} took {live_s:.4f}s on {attack} "
            f"(k={k}, {len(payload)} bytes), cap {param}s. The pre-fix pattern "
            f"took {hist_s:.4f}s on the same input."
        )
    else:
        # Teeth-check for the relative arm. Without it a zeroed timer reads as
        # infinite separation and PASSES (reviewer mutation M-D1).
        assert hist_s > RELATIVE_TEETH_MIN_HIST_S, (
            f"guard has no teeth: the historical vulnerable {attr} finished "
            f"{attack} (k={k}, {len(payload)} bytes) in {hist_s:.4f}s, under the "
            f"{RELATIVE_TEETH_MIN_HIST_S}s floor. Observed range is 3.08-38.1s "
            f"(the 3.08s low measured at max boost), "
            f"so this reads as a dead or stubbed timer, not a fast host."
        )
        assert live_s <= RELATIVE_SANITY_CEILING_S, (
            f"BOB-093: {attr} took {live_s:.4f}s on {attack} (k={k}), over the "
            f"{RELATIVE_SANITY_CEILING_S}s sanity ceiling. Even allowing for host "
            f"load this is too slow to be the bounded pattern."
        )
        assert separation > param, (
            f"BOB-093 ReDoS regression: {attr} is only {separation:.2f}x faster "
            f"than the pre-fix quadratic pattern on {attack} (k={k}, "
            f"{len(payload)} bytes): live {live_s:.4f}s vs historical "
            f"{hist_s:.4f}s. Bounded measures >=9x even under heavy load; a "
            f"quadratic regression measures ~1.1x. Threshold {param}x."
        )


# A growth-RATIO test (time(2n)/time(n) < threshold) was written here and then
# REMOVED, not weakened: it passed in isolation and failed when run after the
# three cap tests above, because a ratio of two noisy measurements amplifies the
# host-contention noise this box has by design (other agents share it).  A test
# that needs a re-run to go green trains everyone to re-run instead of read
# (§11.4.248), so it is gone.  Nothing is lost: the quadratic it was meant to
# catch overshoots the tr_storm cap above by ~2x, which the §1.1 mutation run
# demonstrated (reverted re_threads measured 6.70s against the 3.5s cap).
