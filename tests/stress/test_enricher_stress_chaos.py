"""§11.4.85 STRESS + CHAOS automation tests for the Boba enricher /
quality-detection path (``MetadataEnricher.detect_quality`` in
``download-proxy/src/merge_service/enricher.py``).

``detect_quality(name)`` parses an **UNTRUSTED**, tracker-supplied torrent
title and applies a fixed battery of ``re.search`` patterns
(``2160p|4k|uhd`` … ``480p|sd|camrip``) plus a handful of substring checks,
returning one of a CLOSED set of quality-tier strings
(``4K | 1080p | 720p | SD | BluRay | WEB-DL | HDTV | DVD``) or ``None``.
Because the title is attacker-controlled, this is a real ReDoS + crash
surface: a single catastrophic-backtracking regex or an unhandled type
would let a hostile tracker hang or crash the merge pipeline.

This is a DIFFERENT code path from every other stress test in this tree
(dedup, search-orchestration, routes, bridge, auth). It exercises ONLY the
pure, in-process ``detect_quality`` classifier: no network, no running
service, no sleeps beyond the hard timeout guards, host-safe (N capped at
600; ReDoS payloads bounded; thread-pool capped).

Anti-bluff (§11.4 / §11.4.5 / §11.4.69 / §11.4.107): every test asserts a
USER-OBSERVABLE outcome — the returned quality-tier value, per-call
latency under a hard wall-clock cap, determinism-hash equality, evidence
-file existence — NEVER merely "no exception raised". Each PASS writes an
inspectable JSON artefact under ``qa-results/enricher_stress/local/`` (a
STATIC run-id so assertions never depend on wall-clock).

§11.4.85 category -> test map (asserted by ``test_section_114_85_category_map``):

STRESS:
  sustained-load        -> test_stress_sustained_load_500_titles
  concurrent-contention -> test_stress_concurrent_determinism
  boundary-empty        -> test_boundary_empty_title
  boundary-single-char  -> test_boundary_single_char_title
  boundary-only-token   -> test_boundary_only_resolution_token
  boundary-conflicting  -> test_boundary_conflicting_resolution_tokens
  boundary-no-token     -> test_boundary_no_quality_token
CHAOS:
  redos-resistance      -> test_chaos_redos_pathological_inputs   (CRITICAL)
  malformed-type        -> test_chaos_malformed_non_string_titles
  malformed-huge        -> test_chaos_malformed_huge_unicode_control
  adversarial-storm     -> test_chaos_adversarial_token_storm
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Import the production enricher module directly from source. ``detect_quality``
# depends only on the stdlib (re/os/logging/dataclasses), so it loads cleanly
# under the venv 3.13 interpreter even though the tree targets 3.12.
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]

_enricher_spec = importlib.util.spec_from_file_location(
    "merge_service.enricher", _MS_PATH / "enricher.py"
)
_enricher_mod = importlib.util.module_from_spec(_enricher_spec)
sys.modules["merge_service.enricher"] = _enricher_mod
_enricher_spec.loader.exec_module(_enricher_mod)

MetadataEnricher = _enricher_mod.MetadataEnricher

# Closed set of values ``detect_quality`` is contractually allowed to return.
_VALID_TIERS = frozenset({"4K", "1080p", "720p", "SD", "BluRay", "WEB-DL", "HDTV", "DVD"})

# Hard wall-clock cap per single ReDoS-payload classification (seconds). A
# correct linear-time regex battery classifies even a 100k-char hostile title
# in low single-digit milliseconds; 2s is a generous ReDoS tripwire.
_REDOS_CAP_SECONDS = 2.0

_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "enricher_stress" / "local"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _write_evidence(name: str, payload: dict) -> Path:
    """Persist captured evidence; return the path (asserted to exist by callers)."""
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return path


def _assert_valid_classification(result) -> None:
    """A well-formed classification is either None or one of the closed tier set."""
    assert result is None or result in _VALID_TIERS, f"non-contract classification: {result!r}"


def _classify_with_timeout(enricher, title, cap_seconds):
    """Run ``detect_quality(title)`` in a worker thread with a hard wall-clock cap.

    Returns ``(result, elapsed_seconds)``. Raises ``concurrent.futures.TimeoutError``
    if the call did not complete within ``cap_seconds`` — that is the ReDoS signal.
    NOTE: a Python-level regex runs without releasing the GIL, so a true
    catastrophic backtrack would still wall-clock past the cap and the future
    ``.result(timeout=...)`` raises, which is exactly the defect we want to
    surface (never mask).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        start = time.perf_counter()
        fut = ex.submit(enricher.detect_quality, title)
        result = fut.result(timeout=cap_seconds)
        elapsed = time.perf_counter() - start
    return result, elapsed


# Real-world + adversarial title corpus for the sustained-load pass.
def _build_title_corpus(n: int) -> list[str]:
    base = [
        "Movie.2023.2160p.UHD.BluRay.x265.HDR",
        "Show S01E01 1080p WEB-DL DDP5.1",
        "Some.Film.2019.720p.HDRip.x264",
        "Old.Movie.1998.DVDRip.XviD",
        "Documentary.2021.HDTV.x264",
        "Concert.4K.UHD.2160p.Remux",
        "Series S03E10 480p SDTV",
        "Фильм.2022.1080p.BluRay.x264.русская.озвучка",
        "Аниме [1080p] [HEVC] [RusSub]",
        "Album (2020) [FLAC] [Lossless]",
        "Book.Title.EPUB.retail",
        "Game.Release.v1.0.REPACK",
        "Mixed.Case.WebRip.FullHD.AC3",
        "Plain Title With No Quality Tokens At All",
        "Movie 8K experimental cut 2160p",
        "Cam.Release.CAMRIP.2024",
        "Show.S02.COMPLETE.WEBDL.1080p.DDP5.1.Atmos",
        "Classic.BD-Remux.2160p.DV.HDR10",
    ]
    corpus = []
    i = 0
    while len(corpus) < n:
        corpus.append(base[i % len(base)] + f" .copy{i}")
        i += 1
    return corpus


# --------------------------------------------------------------------------- #
# STRESS — sustained load
# --------------------------------------------------------------------------- #
def test_stress_sustained_load_500_titles():
    """Enrich 600 varied real-world titles; record p50/p95 latency; assert every
    result is a well-formed (closed-set or None) quality classification."""
    enricher = MetadataEnricher()
    titles = _build_title_corpus(600)

    latencies_ms: list[float] = []
    classifications: dict[str, int] = {}
    for title in titles:
        start = time.perf_counter()
        result = enricher.detect_quality(title)
        latencies_ms.append((time.perf_counter() - start) * 1000.0)
        _assert_valid_classification(result)
        classifications[str(result)] = classifications.get(str(result), 0) + 1

    latencies_ms.sort()
    n = len(latencies_ms)
    p50 = latencies_ms[n // 2]
    p95 = latencies_ms[min(n - 1, int(n * 0.95))]

    # User-observable proof: the real-world fixtures classify into known tiers,
    # not all-None (which would mean the parser is silently dead).
    assert classifications.get("None", 0) < n, "every title classified None — parser dead?"
    assert classifications.get("4K", 0) > 0, "expected ≥1 4K from the 2160p/UHD fixtures"
    assert classifications.get("1080p", 0) > 0, "expected ≥1 1080p fixture"

    evidence = _write_evidence(
        "sustained_load_latency.json",
        {
            "feature": "audio_output? no — quality_detection",
            "count": n,
            "p50_ms": round(p50, 4),
            "p95_ms": round(p95, 4),
            "max_ms": round(latencies_ms[-1], 4),
            "classification_histogram": classifications,
            "valid_tier_set": sorted(_VALID_TIERS),
        },
    )
    assert evidence.exists() and evidence.stat().st_size > 0


# --------------------------------------------------------------------------- #
# STRESS — concurrent contention + determinism (§11.4.50)
# --------------------------------------------------------------------------- #
def test_stress_concurrent_determinism():
    """≥10 concurrent enrich calls complete with no exception, and every title
    classifies IDENTICALLY across the concurrent run AND a serial baseline
    (deterministic — §11.4.50 hash equality)."""
    enricher = MetadataEnricher()
    titles = _build_title_corpus(240)

    # Serial baseline classification map.
    baseline = {t: enricher.detect_quality(t) for t in titles}
    baseline_hash = hashlib.sha256(
        json.dumps([(t, baseline[t]) for t in titles], ensure_ascii=False).encode()
    ).hexdigest()

    # Concurrent run: 16 workers hammer the same enricher instance.
    def work(t):
        return t, enricher.detect_quality(t)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        concurrent_pairs = list(ex.map(work, titles * 3))

    # Every concurrent result matches the serial baseline for its title.
    mismatches = [(t, r, baseline[t]) for t, r in concurrent_pairs if r != baseline[t]]
    assert not mismatches, f"non-deterministic under concurrency: {mismatches[:5]}"
    for _t, r in concurrent_pairs:
        _assert_valid_classification(r)

    # Re-run the serial baseline a second time → identical hash (determinism).
    rerun = {t: enricher.detect_quality(t) for t in titles}
    rerun_hash = hashlib.sha256(
        json.dumps([(t, rerun[t]) for t in titles], ensure_ascii=False).encode()
    ).hexdigest()
    assert rerun_hash == baseline_hash, "classification not deterministic across runs"

    evidence = _write_evidence(
        "concurrent_determinism.json",
        {
            "titles": len(titles),
            "concurrent_calls": len(concurrent_pairs),
            "workers": 16,
            "baseline_hash": baseline_hash,
            "rerun_hash": rerun_hash,
            "hash_equal": rerun_hash == baseline_hash,
            "mismatches": mismatches,
        },
    )
    assert evidence.exists() and evidence.stat().st_size > 0


# --------------------------------------------------------------------------- #
# STRESS — boundary conditions
# --------------------------------------------------------------------------- #
def test_boundary_empty_title():
    """Empty string → None (no quality token), no crash."""
    enricher = MetadataEnricher()
    result = enricher.detect_quality("")
    assert result is None
    _assert_valid_classification(result)
    ev = _write_evidence("boundary_empty.json", {"input": "", "result": result})
    assert ev.exists()


def test_boundary_single_char_title():
    """Single non-token char → None."""
    enricher = MetadataEnricher()
    for ch in ("a", "1", " ", "."):
        result = enricher.detect_quality(ch)
        _assert_valid_classification(result)
        assert result is None, f"unexpected tier for single char {ch!r}: {result!r}"
    ev = _write_evidence("boundary_single_char.json", {"chars": ["a", "1", " ", "."], "result": None})
    assert ev.exists()


def test_boundary_only_resolution_token():
    """A title that is ONLY a resolution token classifies to exactly that tier."""
    enricher = MetadataEnricher()
    cases = {
        "2160p": "4K",
        "4k": "4K",
        "uhd": "4K",
        "1080p": "1080p",
        "fullhd": "1080p",
        "720p": "720p",
        "480p": "SD",
        "bluray": "BluRay",
        "web-dl": "WEB-DL",
        "hdtv": "HDTV",
        "dvd": "DVD",
    }
    observed = {}
    for token, expected in cases.items():
        result = enricher.detect_quality(token)
        observed[token] = result
        _assert_valid_classification(result)
        assert result == expected, f"{token!r} → {result!r}, expected {expected!r}"
    ev = _write_evidence("boundary_only_token.json", {"cases": cases, "observed": observed})
    assert ev.exists()


def test_boundary_conflicting_resolution_tokens():
    """Title with 720p AND 1080p AND 2160p → resolution precedence is honoured
    deterministically (4K wins; it is checked first), never a crash, never an
    out-of-set value."""
    enricher = MetadataEnricher()
    title = "Movie 720p 1080p 2160p mixed BluRay WEB-DL HDTV DVD"
    result = enricher.detect_quality(title)
    _assert_valid_classification(result)
    # 2160p is checked first in the regex battery → 4K must win.
    assert result == "4K", f"conflicting-token precedence broke: got {result!r}"
    # Determinism: same answer every time.
    assert all(enricher.detect_quality(title) == "4K" for _ in range(20))
    ev = _write_evidence(
        "boundary_conflicting.json",
        {"input": title, "result": result, "precedence_expected": "4K"},
    )
    assert ev.exists()


def test_boundary_no_quality_token():
    """Plausible title with zero quality tokens → None (not a false-positive tier)."""
    enricher = MetadataEnricher()
    for title in (
        "Just A Plain Movie Name 2021",
        "Author - Some Book Title",
        "Band Name - Album Name",
        "A" * 200,
    ):
        result = enricher.detect_quality(title)
        _assert_valid_classification(result)
        assert result is None, f"false-positive tier for {title[:30]!r}: {result!r}"
    ev = _write_evidence("boundary_no_token.json", {"sampled": "plain titles", "result": None})
    assert ev.exists()


# --------------------------------------------------------------------------- #
# CHAOS — ReDoS resistance (CRITICAL)
# --------------------------------------------------------------------------- #
def test_chaos_redos_pathological_inputs():
    """CRITICAL: feed pathological catastrophic-backtracking payloads against
    the title regex battery. Each call is wrapped in a hard 2s wall-clock cap;
    every payload MUST complete under the cap. The MAX time across all payloads
    vs the cap is the key ReDoS-resistance finding.

    If ANY payload exceeds the cap, that is a REAL ReDoS defect: this test FAILS
    and the evidence file records exactly which payload + its measured time, so
    the source can be fixed — the failure is NEVER masked.
    """
    enricher = MetadataEnricher()

    # Payloads designed to stress alternation / repetition in the patterns:
    # 2160p|4k|uhd, 1080p|fullhd|fhd, 720p|hdrip, 480p|sd|camrip, plus the
    # bluray/web-dl/hdtv/dvd substring scans.
    payloads = {
        "50k_ones": "1" * 50000,
        "5k_zero_p": "0p" * 5000,
        "100k_x": "x" * 100000,
        "50k_dots": "." * 50000,
        "10k_1080p": "1080p" * 10000,
        "10k_2160p": "2160p" * 10000,
        "50k_p_runs": "p" * 50000,
        "alt_res_storm": ("720p1080p2160p" * 5000),
        "long_then_token": ("z" * 80000) + "2160p",
        "token_then_long": "uhd" + ("z" * 80000),
        "interleaved_digits_p": ("1" * 100 + "p") * 500,
        "webdl_prefix_storm": ("web" * 20000) + "-dl",
        "bluray_storm": ("blu" * 20000) + "ray",
        "huge_4k_suffix": ("9" * 90000) + "4k",
    }

    results = {}
    max_elapsed = 0.0
    max_payload = None
    redos_failures = []

    for name, payload in payloads.items():
        try:
            result, elapsed = _classify_with_timeout(enricher, payload, _REDOS_CAP_SECONDS)
        except concurrent.futures.TimeoutError:
            # REAL ReDoS defect — record it precisely, do not mask.
            redos_failures.append(
                {
                    "payload": name,
                    "payload_len": len(payload),
                    "exceeded_cap_seconds": _REDOS_CAP_SECONDS,
                    "regex_battery": "detect_quality resolution/source alternations",
                }
            )
            results[name] = {"timed_out": True, "elapsed_s": None}
            continue

        _assert_valid_classification(result)
        results[name] = {
            "timed_out": False,
            "elapsed_s": round(elapsed, 6),
            "elapsed_ms": round(elapsed * 1000, 4),
            "result": result,
            "payload_len": len(payload),
        }
        if elapsed > max_elapsed:
            max_elapsed = elapsed
            max_payload = name

    evidence = _write_evidence(
        "redos_resistance.json",
        {
            "cap_seconds": _REDOS_CAP_SECONDS,
            "max_elapsed_seconds": round(max_elapsed, 6),
            "max_elapsed_ms": round(max_elapsed * 1000, 4),
            "slowest_payload": max_payload,
            "redos_failures": redos_failures,
            "per_payload": results,
            "verdict": "REDOS_DEFECT" if redos_failures else "REDOS_RESISTANT",
        },
    )
    assert evidence.exists() and evidence.stat().st_size > 0

    # The load-bearing ReDoS assertion: NO payload may exceed the cap.
    assert not redos_failures, (
        f"REAL ReDoS defect — {len(redos_failures)} payload(s) exceeded the "
        f"{_REDOS_CAP_SECONDS}s cap: {redos_failures}"
    )
    # Belt-and-braces: the worst observed time is comfortably under the cap.
    assert max_elapsed < _REDOS_CAP_SECONDS, (
        f"slowest payload {max_payload!r} took {max_elapsed:.4f}s ≥ cap {_REDOS_CAP_SECONDS}s"
    )


# --------------------------------------------------------------------------- #
# CHAOS — malformed / hostile non-string + huge + unicode input
# --------------------------------------------------------------------------- #
def test_chaos_malformed_non_string_titles():
    """None and non-string titles must not crash with an *unhandled* exception.

    ``detect_quality`` guards ``None`` (``name_lower = name.lower() if name else ""``)
    so ``None`` returns a contract value. For genuinely non-string types (int,
    bytes, list) the function does not type-guard, so a ``TypeError`` /
    ``AttributeError`` is the DEFINED, contained outcome — we assert it is one of
    those (a contained, predictable failure), never a hang and never a wrong
    quality tier. This pins the current contract so a regression that silently
    returns a bogus tier for non-string input is caught.
    """
    enricher = MetadataEnricher()

    # None is explicitly guarded → must return None.
    assert enricher.detect_quality(None) is None

    contained = {}
    for label, value in (("int", 1080), ("bytes", b"1080p"), ("list", ["1080p"]), ("float", 2160.0)):
        try:
            result = enricher.detect_quality(value)
            # If it DID return, it must still be a contract value (never a bogus tier).
            _assert_valid_classification(result)
            contained[label] = {"returned": result}
        except (TypeError, AttributeError) as exc:
            contained[label] = {"raised": type(exc).__name__}
    ev = _write_evidence(
        "malformed_non_string.json",
        {"none_result": None, "non_string_outcomes": contained},
    )
    assert ev.exists() and ev.stat().st_size > 0


def test_chaos_malformed_huge_unicode_control():
    """100k-char, unicode/emoji/RTL/zero-width, and control-char titles → no
    crash, returns a defined classification (closed-set or None), fast."""
    enricher = MetadataEnricher()
    cases = {
        "100k_chars": "Movie " + ("ä" * 100000) + " 1080p",
        "emoji": "🎬🍿 Movie 2160p UHD 🔥💯",
        "rtl": "فيلم 1080p مترجم ‮RTL‬",
        "zero_width": "Mo​vie‌ 720p‍ HDRip",
        "control_chars": "Movie\x00\x01\x07\x1b[31m 1080p BluRay",
        "mixed_scripts": "电影 Фильм Movie 2160p フィルム",
        "only_combining": "́̂̃" * 1000,
    }
    observed = {}
    for label, title in cases.items():
        result, elapsed = _classify_with_timeout(enricher, title, _REDOS_CAP_SECONDS)
        _assert_valid_classification(result)
        observed[label] = {"result": result, "elapsed_ms": round(elapsed * 1000, 4)}

    # Sanity: the cases that DO contain a clear token classify as expected
    # (proves the parser still works through the unicode noise, not just "no crash").
    assert observed["100k_chars"]["result"] == "1080p"
    assert observed["emoji"]["result"] == "4K"
    assert observed["control_chars"]["result"] in ("1080p", "BluRay")  # 1080p wins (checked first)

    ev = _write_evidence("malformed_huge_unicode.json", {"cases": list(cases), "observed": observed})
    assert ev.exists() and ev.stat().st_size > 0


# --------------------------------------------------------------------------- #
# CHAOS — adversarial token storm
# --------------------------------------------------------------------------- #
def test_chaos_adversarial_token_storm():
    """Titles stuffed with hundreds of conflicting quality tokens → no crash,
    deterministic, returns a contract value (resolution precedence honoured)."""
    enricher = MetadataEnricher()
    tokens = ["2160p", "4k", "uhd", "1080p", "fullhd", "720p", "hdrip", "480p", "sd",
              "camrip", "bluray", "web-dl", "webrip", "hdtv", "dvd", "x264", "x265", "hevc"]

    # 500 tokens shuffled deterministically (no RNG seeding needed; fixed order).
    storm = " ".join((tokens * 30)[:500])
    result, elapsed = _classify_with_timeout(enricher, storm, _REDOS_CAP_SECONDS)
    _assert_valid_classification(result)
    # Contains 2160p → resolution battery picks 4K first; deterministic.
    assert result == "4K", f"token-storm classification broke: {result!r}"
    assert all(enricher.detect_quality(storm) == "4K" for _ in range(25))

    # A storm with NO resolution tokens but many source tokens → first source wins.
    src_storm = " ".join((["bluray", "web-dl", "hdtv", "dvd"] * 100)[:300])
    src_result = enricher.detect_quality(src_storm)
    _assert_valid_classification(src_result)
    assert src_result == "BluRay", f"source-storm precedence broke: {src_result!r}"

    ev = _write_evidence(
        "adversarial_token_storm.json",
        {
            "res_storm_tokens": 500,
            "res_storm_result": result,
            "res_storm_elapsed_ms": round(elapsed * 1000, 4),
            "src_storm_tokens": 300,
            "src_storm_result": src_result,
        },
    )
    assert ev.exists() and ev.stat().st_size > 0


# --------------------------------------------------------------------------- #
# Meta: assert the §11.4.85 category map in the module docstring is realised
# by the actually-collected test functions (anti-bluff on the coverage claim).
# --------------------------------------------------------------------------- #
def test_section_114_85_category_map():
    expected_tests = {
        "test_stress_sustained_load_500_titles",
        "test_stress_concurrent_determinism",
        "test_boundary_empty_title",
        "test_boundary_single_char_title",
        "test_boundary_only_resolution_token",
        "test_boundary_conflicting_resolution_tokens",
        "test_boundary_no_quality_token",
        "test_chaos_redos_pathological_inputs",
        "test_chaos_malformed_non_string_titles",
        "test_chaos_malformed_huge_unicode_control",
        "test_chaos_adversarial_token_storm",
    }
    module_globals = globals()
    missing = {name for name in expected_tests if name not in module_globals}
    assert not missing, f"docstring map references undefined tests: {missing}"
    ev = _write_evidence(
        "category_map.json",
        {"section": "11.4.85", "stress_and_chaos_tests": sorted(expected_tests)},
    )
    assert ev.exists()
