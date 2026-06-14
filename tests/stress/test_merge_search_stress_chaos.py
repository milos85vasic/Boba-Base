"""§11.4.85 STRESS + CHAOS automation tests for the Boba merge-search
de-duplication path (``Deduplicator.merge_results`` — the tiered match engine
that powers the progressive merged-results streaming).

This is a DIFFERENT code path from the button / route endpoints. It exercises
ONLY the pure, in-process dedup/merge logic: no network, no running merge
service, no sleeps, host-safe (N capped at 5000).

Anti-bluff (§11.4 / §11.4.5 / §11.4.69): every test asserts a USER-OBSERVABLE
outcome — merged-row count, sources-per-merged-group, the
no-cross-group-duplicate-infohash invariant, deterministic serialized-output
hash equality, latency-evidence-file existence — NEVER merely "no error". Each
PASS writes an inspectable JSON artefact under
``qa-results/search_stress/local/`` (a STATIC run-id so assertions never
depend on wall-clock).

§11.4.85 category -> test map (see ``test_section_114_85_category_map`` which
asserts this docstring map is itself realised by the collected test set):

STRESS:
  sustained-load        -> test_stress_sustained_load_large_dedup
  concurrent-contention -> test_stress_concurrent_determinism
  boundary-empty        -> test_boundary_empty_input
  boundary-single       -> test_boundary_single_result
  boundary-all-identical-> test_boundary_all_identical_one_row
  boundary-all-unique   -> test_boundary_all_unique_n_rows
  boundary-fuzzy-edge   -> test_boundary_fuzzy_threshold_edges
CHAOS:
  input-fault-malformed -> test_chaos_malformed_partial_results
  adversarial-storm     -> test_chaos_adversarial_near_duplicate_storm
  state-corruption      -> test_chaos_conflicting_infohash_metadata
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
# Import the production dedup/search modules directly from source (3.12 code;
# loaded under the venv 3.13 interpreter via importlib so the relative
# ``from .search import ...`` inside deduplicator.py resolves).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"merge_service.{modname}", str(_MS_PATH / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"merge_service.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


_search_mod = _load("search", "search.py")
_dedup_mod = _load("deduplicator", "deduplicator.py")

SearchResult = _search_mod.SearchResult
Deduplicator = _dedup_mod.Deduplicator

# --------------------------------------------------------------------------- #
# Captured-evidence helper. STATIC run-id "local" per the task — never a
# wall-clock subdir, so assertions are stable and re-runnable.
# --------------------------------------------------------------------------- #
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "search_stress" / "local"


def _write_evidence(name: str, payload: dict) -> Path:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    assert path.exists() and path.stat().st_size > 0, "evidence artefact must exist and be non-empty"
    return path


# --------------------------------------------------------------------------- #
# Serialization / invariant helpers — these define the USER-OBSERVABLE outcomes
# every assertion inspects.
# --------------------------------------------------------------------------- #
def _serialize(merged_list: list) -> str:
    """Deterministically serialize the merged output to a stable string.

    We sort merged rows by canonical title + the sorted source links so that
    two runs that produce the same *set* of merged groups serialize
    byte-identically regardless of internal ordering. This is the observable
    the §11.4.50 determinism check hashes.
    """
    rows = []
    for m in merged_list:
        rows.append(
            {
                "title": m.canonical_identity.title,
                "n_sources": len(m.original_results),
                "total_seeds": m.total_seeds,
                "best_quality": m.best_quality.value if m.best_quality else None,
                "source_links": sorted(r.link or "" for r in m.original_results),
                "source_names": sorted(r.name or "" for r in m.original_results),
            }
        )
    rows.sort(key=lambda r: (r["title"] or "", tuple(r["source_links"])))
    return json.dumps(rows, sort_keys=True, default=str)


def _hash_output(merged_list: list) -> str:
    return hashlib.sha256(_serialize(merged_list).encode("utf-8")).hexdigest()


def _infohash(link: str):
    return Deduplicator()._extract_infohash(link or "")


def _assert_no_cross_group_dup_infohash(merged_list: list) -> dict:
    """USER-OBSERVABLE invariant: a given infohash must never appear in two
    different merged rows. If it did, the user would see the same torrent
    listed as two "distinct" results — the exact failure dedup exists to stop.

    Returns a small census dict for evidence.
    """
    hash_to_row = {}
    duplicates = []
    for idx, m in enumerate(merged_list):
        seen_in_row = set()
        for r in m.original_results:
            ih = _infohash(r.link)
            if not ih:
                continue
            ih = ih.lower()
            if ih in hash_to_row and hash_to_row[ih] != idx and ih not in seen_in_row:
                duplicates.append({"infohash": ih, "rows": [hash_to_row[ih], idx]})
            hash_to_row[ih] = idx
            seen_in_row.add(ih)
    assert not duplicates, f"infohash leaked across merged rows: {duplicates[:5]}"
    return {"distinct_infohashes": len(hash_to_row), "cross_group_dups": len(duplicates)}


# --------------------------------------------------------------------------- #
# Synthetic input builders (pure, no network).
# --------------------------------------------------------------------------- #
_TRACKERS = ["rutracker", "kinozal", "nnmclub", "rutor"]


def _btih(seed: int) -> str:
    """Deterministic 40-hex-char btih from an int seed."""
    return hashlib.sha1(f"boba-{seed}".encode()).hexdigest()


def _result(name, link, size="2.0 GB", seeds=10, tracker="rutracker", leechers=1, freeleech=False):
    return SearchResult(
        name=name,
        link=link,
        size=size,
        seeds=seeds,
        leechers=leechers,
        engine_url=f"https://{tracker}.example",
        tracker=tracker,
        freeleech=freeleech,
    )


def _unique_title(g: int) -> str:
    """A pairwise-DISSIMILAR title per group.

    Important: the engine's Tier-1 identity match groups results whose
    *normalized* titles are >=0.80 Levenshtein-similar (BEFORE infohash is even
    compared). Templated names like "Distinct Movie {g} ..." normalize to
    near-identical strings and ALL collapse together. A unique 40-hex token per
    group guarantees the normalized titles stay far below 0.80 similarity
    (empirically <0.52 max), so distinct groups remain distinct rows and the
    only thing collapsing a group is its shared infohash (Tier 2).
    """
    return "Title" + hashlib.sha1(f"grp-{g}".encode()).hexdigest()


def _make_large_corpus(n_groups: int, copies_per_group: int) -> tuple[list, int]:
    """Build n_groups duplicate-groups, each with `copies_per_group` identical
    torrents that share ONE infohash across trackers.

    Returns (results, expected_merged_rows). Each group shares ONE infohash AND
    a unique dissimilar title, so the group collapses to exactly one merged row
    and distinct groups never accidentally merge.
    """
    results = []
    for g in range(n_groups):
        link = f"magnet:?xt=urn:btih:{_btih(g)}"
        title = _unique_title(g)
        for c in range(copies_per_group):
            tracker = _TRACKERS[c % len(_TRACKERS)]
            results.append(_result(name=title, link=link, seeds=5 + c, tracker=tracker))
    return results, n_groups


# --------------------------------------------------------------------------- #
# STRESS — sustained load
# --------------------------------------------------------------------------- #
def test_stress_sustained_load_large_dedup():
    """Dedup a LARGE input (groups + their duplicate copies) and assert the
    merge is both FAST and CORRECT.

    USER-OBSERVABLE assertions:
      - every duplicate-group collapses to exactly ONE merged row
        (expected_rows == produced rows);
      - no infohash leaks across two merged rows;
      - completes within a sane wall-clock bound.
    """
    # 300 distinct duplicate-groups x 7 copies = 2100 input results, 300 rows.
    # The engine's grouping cost is O(distinct-seeds^2) (each unmatched seed
    # re-scans the remaining list), so "large" here is sized on DISTINCT groups
    # (the expensive axis), not raw count — 2100 results in the 2000-5000 range
    # while staying host-safe.
    n_groups, copies = 300, 7
    results, expected_rows = _make_large_corpus(n_groups, copies)
    assert len(results) == n_groups * copies == 2100

    dedup = Deduplicator()
    t0 = time.perf_counter()
    merged = dedup.merge_results(results)
    elapsed = time.perf_counter() - t0

    # Correctness: every group collapsed to exactly one row.
    assert len(merged) == expected_rows, f"expected {expected_rows} merged rows, got {len(merged)}"
    # Each merged row carries all `copies` sources.
    sources_per_row = sorted({len(m.original_results) for m in merged})
    assert sources_per_row == [copies], f"each group should have {copies} sources, got {sources_per_row}"
    invariant = _assert_no_cross_group_dup_infohash(merged)
    assert invariant["cross_group_dups"] == 0

    # Performance bound (host-safe, generous to avoid flake on a busy host;
    # observed ~20s for this corpus).
    bound_s = 90.0
    assert elapsed < bound_s, f"dedup of {len(results)} results took {elapsed:.2f}s (> {bound_s}s)"

    ev = _write_evidence(
        "dedup_latency",
        {
            "section": "11.4.85",
            "category": "stress/sustained-load",
            "input_results": len(results),
            "n_groups": n_groups,
            "copies_per_group": copies,
            "merged_rows": len(merged),
            "expected_rows": expected_rows,
            "sources_per_row_distinct": sources_per_row,
            "wall_clock_s": round(elapsed, 4),
            "bound_s": bound_s,
            "results_per_second": round(len(results) / elapsed, 1) if elapsed > 0 else None,
            "invariant_no_cross_group_dup_infohash": invariant,
            "output_hash": _hash_output(merged),
        },
    )
    assert ev.stat().st_size > 0


# --------------------------------------------------------------------------- #
# STRESS — concurrent contention + determinism (§11.4.50)
# --------------------------------------------------------------------------- #
def test_stress_concurrent_determinism():
    """Run many deduplicate calls concurrently on the SAME input and assert
    byte-identical merged output every time (§11.4.50 deterministic
    consistency). Each call uses its own Deduplicator instance (the production
    streaming path creates a fresh one per search) and a fresh shuffled copy of
    the input to prove order-invariance under contention.

    USER-OBSERVABLE assertion: the set of distinct output hashes across all
    concurrent runs has size exactly 1.
    """
    base, expected_rows = _make_large_corpus(100, 3)  # 300 results (~1.4s/run)

    # Add a handful of standalone uniques so the path exercises all tiers.
    for i in range(40):
        ih = _btih(10_000 + i)
        base.append(_result(_unique_title(10_000 + i), f"magnet:?xt=urn:btih:{ih}", seeds=3))
    expected_rows += 40

    def _run(shift: int):
        # deterministic rotation (not RNG) so the perturbation is reproducible
        rotated = base[shift:] + base[:shift]
        merged = Deduplicator().merge_results(rotated)
        return _hash_output(merged), len(merged)

    iterations = 8
    hashes = []
    row_counts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_run, (k * 37) % len(base)) for k in range(iterations)]
        for f in concurrent.futures.as_completed(futures):
            h, rc = f.result()
            hashes.append(h)
            row_counts.append(rc)

    distinct = sorted(set(hashes))
    assert len(distinct) == 1, f"non-deterministic merged output across {iterations} concurrent runs: {distinct}"
    assert set(row_counts) == {expected_rows}, f"row-count drift: {sorted(set(row_counts))} != {expected_rows}"

    ev = _write_evidence(
        "concurrent_determinism",
        {
            "section": "11.4.85",
            "category": "stress/concurrent-contention + 11.4.50 determinism",
            "iterations": iterations,
            "max_workers": 4,
            "input_results": len(base),
            "merged_rows": expected_rows,
            "distinct_output_hashes": distinct,
            "determinism_ok": len(distinct) == 1,
        },
    )
    assert ev.stat().st_size > 0


# --------------------------------------------------------------------------- #
# STRESS — boundary conditions
# --------------------------------------------------------------------------- #
def test_boundary_empty_input():
    """Empty input -> empty output (no crash, no phantom rows)."""
    merged = Deduplicator().merge_results([])
    assert merged == []
    _write_evidence("boundary_empty", {"section": "11.4.85", "category": "boundary-empty", "merged_rows": 0})


def test_boundary_single_result():
    """Single result -> exactly one merged row with one source."""
    r = _result("Solo Movie 2021 1080p", f"magnet:?xt=urn:btih:{_btih(1)}", seeds=7)
    merged = Deduplicator().merge_results([r])
    assert len(merged) == 1
    assert len(merged[0].original_results) == 1
    assert merged[0].total_seeds == 7
    _write_evidence(
        "boundary_single",
        {"section": "11.4.85", "category": "boundary-single", "merged_rows": 1, "total_seeds": 7},
    )


def test_boundary_all_identical_one_row():
    """N identical copies (one shared infohash) -> exactly ONE merged row with
    N sources and total_seeds == sum of all copies' seeds."""
    n = 50
    ih = _btih(2)
    link = f"magnet:?xt=urn:btih:{ih}"
    results = [_result("Same Movie 2020 1080p BluRay x264-GRP", link, seeds=2, tracker=_TRACKERS[i % 4]) for i in range(n)]
    merged = Deduplicator().merge_results(results)
    assert len(merged) == 1, f"all-identical must collapse to ONE row, got {len(merged)}"
    assert len(merged[0].original_results) == n
    assert merged[0].total_seeds == 2 * n
    _write_evidence(
        "boundary_all_identical",
        {
            "section": "11.4.85",
            "category": "boundary-all-identical",
            "input": n,
            "merged_rows": 1,
            "sources_in_row": n,
            "total_seeds": 2 * n,
        },
    )


def test_boundary_all_unique_n_rows():
    """N genuinely-distinct torrents -> N merged rows (nothing wrongly merged).
    Each has a distinct infohash AND a distinct, non-fuzzy-similar name."""
    n = 60
    results = []
    # Unique 40-hex-token titles => pairwise normalized-title similarity <0.52,
    # well below BOTH the Tier-1 identity threshold (0.80) and the Tier-4 fuzzy
    # threshold (0.85), AND distinct infohashes => nothing should merge.
    for i in range(n):
        results.append(_result(_unique_title(3000 + i), f"magnet:?xt=urn:btih:{_btih(3000 + i)}", seeds=1))
    merged = Deduplicator().merge_results(results)
    assert len(merged) == n, f"all-unique must stay {n} rows, got {len(merged)}"
    invariant = _assert_no_cross_group_dup_infohash(merged)
    _write_evidence(
        "boundary_all_unique",
        {
            "section": "11.4.85",
            "category": "boundary-all-unique",
            "input": n,
            "merged_rows": len(merged),
            "invariant": invariant,
        },
    )


def test_boundary_fuzzy_threshold_edges():
    """Fuzzy-threshold edge: two names just ABOVE 0.85 Levenshtein similarity
    must group; two names just BELOW must NOT.

    To isolate the fuzzy tier (Tier 4) from the Tier-1 identity match (which
    also uses a 0.80 normalized-title similarity), we use names with NO
    year/resolution/codec tokens (so normalization is a no-op) and DIFFERENT
    infohashes (so Tier 2 cannot fire). We assert on the engine's own
    similarity score so the test is grounded in the real threshold, then
    confirm the grouping outcome the user sees.
    """
    dedup = Deduplicator()

    # ABOVE threshold: small edit distance on a long ASCII string (last word
    # swapped Film -> Movie => ratio ~0.94, comfortably >= 0.85).
    a_above = "The Quick Brown Fox Jumps Over The Lazy Dog Documentary Film"
    b_above = "The Quick Brown Fox Jumps Over The Lazy Dog Documentary Movie"
    sim_above = dedup._calculate_similarity(a_above, b_above)

    # BELOW threshold: same length-ish but very different words.
    a_below = "The Quick Brown Fox Jumps Over The Lazy Dog"
    b_below = "An Entirely Separate Unrelated Subject Matter Here"
    sim_below = dedup._calculate_similarity(a_below, b_below)

    assert sim_above >= Deduplicator.SIMILARITY_THRESHOLD, f"sim_above={sim_above} should be >= 0.85"
    assert sim_below < Deduplicator.SIMILARITY_THRESHOLD, f"sim_below={sim_below} should be < 0.85"

    above_pair = [
        _result(a_above, f"magnet:?xt=urn:btih:{_btih(4001)}", seeds=5),
        _result(b_above, f"magnet:?xt=urn:btih:{_btih(4002)}", seeds=4),
    ]
    below_pair = [
        _result(a_below, f"magnet:?xt=urn:btih:{_btih(4003)}", seeds=5),
        _result(b_below, f"magnet:?xt=urn:btih:{_btih(4004)}", seeds=4),
    ]

    merged_above = dedup.merge_results(above_pair)
    merged_below = Deduplicator().merge_results(below_pair)

    assert len(merged_above) == 1, f"above-threshold names must MERGE (got {len(merged_above)} rows)"
    assert len(merged_below) == 2, f"below-threshold names must NOT merge (got {len(merged_below)} rows)"

    _write_evidence(
        "boundary_fuzzy_edge",
        {
            "section": "11.4.85",
            "category": "boundary-fuzzy-edge",
            "threshold": Deduplicator.SIMILARITY_THRESHOLD,
            "sim_above": round(sim_above, 4),
            "sim_below": round(sim_below, 4),
            "merged_rows_above": len(merged_above),
            "merged_rows_below": len(merged_below),
        },
    )


# --------------------------------------------------------------------------- #
# CHAOS — malformed / partial input fault injection
# --------------------------------------------------------------------------- #
def test_chaos_malformed_partial_results():
    """Inject malformed/partial results (missing infohash, None/empty fields,
    unicode/emoji, 10k-char titles, negative-sentinel size). The dedup MUST
    NOT raise and MUST produce a well-formed list of merged rows.

    USER-OBSERVABLE assertions: returns a list; every input survives into some
    merged row (no silent loss); the cross-group-infohash invariant holds.

    None-seeds robustness (§11.4.4 / §11.4.115): a ``None`` *seeds* value (a
    tracker that reports no seed count) used to crash ``merge_results`` at the
    ``-r.seeds`` sort AND at ``total_seeds += result.seeds`` (TypeError). This
    test now injects ``None`` seeds/leechers — RED on the pre-fix engine,
    GREEN after coercing to 0 in deduplicator.py + search.py. ``None``/``-1``
    *size* is also handled (``_parse_size`` returns None for negatives).
    """
    results = [
        # no infohash (non-magnet link)
        _result("No Infohash Release 1080p", "https://tracker.example/x.torrent", seeds=3),
        # empty name + empty link
        _result("", "", size="", seeds=0),
        # -1 byte-count sentinel emitted by some plugins (handled by _parse_size)
        _result("Negative Size Sentinel 720p", f"magnet:?xt=urn:btih:{_btih(5001)}", size=-1, seeds=2),
        # None size (handled by _parse_size -> None)
        _result("None Size Release 480p", f"magnet:?xt=urn:btih:{_btih(5005)}", size=None, seeds=2),
        # unicode + emoji title
        _result("Фильм 2023 🎬🍿 Кино 1080p", f"magnet:?xt=urn:btih:{_btih(5002)}", seeds=4),  # noqa: RUF001
        # extremely long title (10k chars)
        _result("L" * 10_000 + " 2024 2160p", f"magnet:?xt=urn:btih:{_btih(5003)}", seeds=1),
        # None seeds — a tracker that does not report a seed count. Crashed the
        # `-r.seeds` sort + `total_seeds += result.seeds` pre-fix (TypeError);
        # now coerced to 0. Distinct infohash so it survives as its own row.
        _result("No Seed Count Reported 1080p", f"magnet:?xt=urn:btih:{_btih(5006)}", seeds=None, leechers=None),
        # None seeds on a DUPLICATE infohash (merges into another group via the
        # total_seeds += path).
        _result("Negative Size Sentinel 720p alt", f"magnet:?xt=urn:btih:{_btih(5001)}", seeds=None),
    ]

    merged = None
    error = None
    try:
        merged = Deduplicator().merge_results(results)
    except Exception as e:  # noqa: BLE001 — chaos: ANY raise is the failure
        error = repr(e)

    assert error is None, f"dedup raised on malformed input: {error}"
    assert isinstance(merged, list) and len(merged) >= 1
    # None seeds/leechers must coerce to int (0) — total_seeds stays a number,
    # never None or a crash.
    assert all(isinstance(m.total_seeds, int) for m in merged), "total_seeds must be int after None-seed input"
    assert all(isinstance(m.total_leechers, int) for m in merged), "total_leechers must be int after None-leecher input"
    # No input silently lost: every source object appears in exactly one row.
    total_sources = sum(len(m.original_results) for m in merged)
    assert total_sources == len(results), f"input loss: {total_sources} sources for {len(results)} inputs"
    invariant = _assert_no_cross_group_dup_infohash(merged)

    _write_evidence(
        "chaos_malformed",
        {
            "section": "11.4.85",
            "category": "chaos/input-fault-malformed",
            "input_results": len(results),
            "merged_rows": len(merged),
            "total_sources_preserved": total_sources,
            "raised": error,
            "invariant": invariant,
        },
    )


# --------------------------------------------------------------------------- #
# CHAOS — adversarial near-duplicate storm
# --------------------------------------------------------------------------- #
def test_chaos_adversarial_near_duplicate_storm():
    """Many titles engineered to sit right at the fuzzy boundary. Assert:
    - no crash, completes within bound (no O(n^2) blowup past the bound);
    - deterministic grouping (same input -> identical output hash on repeat).

    The 'storm' is N families of near-identical names with DISTINCT infohashes,
    so Tier-2 cannot collapse them — the fuzzy/identity tiers must do the work,
    which is the expensive O(n^2) path we stress.
    """
    families, per_family = 60, 6  # 360 results, heavy intra-family similarity
    results = []
    for fam in range(families):
        base_name = f"Adversarial Storm Title Number {fam} Edition Complete Collection"
        for k in range(per_family):
            # tiny per-copy perturbation -> high similarity within a family
            name = base_name + ("." * k)
            results.append(_result(name, f"magnet:?xt=urn:btih:{_btih(6000 + fam * 100 + k)}", seeds=2))

    dedup = Deduplicator()
    t0 = time.perf_counter()
    merged1 = dedup.merge_results(list(results))
    elapsed = time.perf_counter() - t0
    merged2 = Deduplicator().merge_results(list(reversed(results)))

    bound_s = 30.0
    assert elapsed < bound_s, f"adversarial storm took {elapsed:.2f}s (> {bound_s}s) — possible blowup"
    # Determinism under reordering.
    h1, h2 = _hash_output(merged1), _hash_output(merged2)
    assert h1 == h2, "adversarial storm produced non-deterministic grouping under input reversal"
    # Each family collapses (fuzzy/identity) to a small number of rows, far
    # fewer than the raw input — observable consolidation.
    assert len(merged1) < len(results), "storm should consolidate at least some near-dups"
    invariant = _assert_no_cross_group_dup_infohash(merged1)

    _write_evidence(
        "chaos_adversarial_storm",
        {
            "section": "11.4.85",
            "category": "chaos/adversarial-storm",
            "input_results": len(results),
            "families": families,
            "per_family": per_family,
            "merged_rows": len(merged1),
            "wall_clock_s": round(elapsed, 4),
            "bound_s": bound_s,
            "deterministic_under_reversal": h1 == h2,
            "invariant": invariant,
        },
    )


# --------------------------------------------------------------------------- #
# CHAOS — state corruption: conflicting metadata for same infohash
# --------------------------------------------------------------------------- #
def test_chaos_conflicting_infohash_metadata():
    """Same btih, but conflicting size/name/seeds across sources (corrupted /
    adversarial tracker metadata). The defined, documented outcome: Tier-2
    infohash match wins -> they MERGE into ONE row regardless of the
    conflicting size/name. Assert that defined outcome (not a crash).
    """
    ih = _btih(7001)
    link = f"magnet:?xt=urn:btih:{ih}"
    results = [
        _result("Conflict Movie 1080p BluRay", link, size="8.0 GB", seeds=100, tracker="rutracker"),
        _result("totally different name 720p WEBRip", link, size="700 MB", seeds=3, tracker="kinozal"),
        _result("ANOTHER 2160p REMUX", link, size=-1, seeds=50, tracker="nnmclub"),
    ]
    merged = Deduplicator().merge_results(results)

    # Defined outcome: infohash identity collapses all three into one row.
    assert len(merged) == 1, f"conflicting-metadata-but-same-infohash must merge to ONE row, got {len(merged)}"
    row = merged[0]
    assert len(row.original_results) == 3
    assert row.total_seeds == 153  # 100 + 3 + 50 — all sources accounted for
    invariant = _assert_no_cross_group_dup_infohash(merged)

    _write_evidence(
        "chaos_conflicting_infohash",
        {
            "section": "11.4.85",
            "category": "chaos/state-corruption",
            "shared_infohash": ih,
            "input_results": len(results),
            "merged_rows": 1,
            "sources_in_row": len(row.original_results),
            "total_seeds": row.total_seeds,
            "documented_outcome": "Tier-2 infohash match wins; conflicting size/name ignored for grouping",
            "invariant": invariant,
        },
    )


# --------------------------------------------------------------------------- #
# Meta: assert the §11.4.85 closed-set category map in the module docstring is
# actually realised by the collected test functions (anti-bluff: the coverage
# claim is mechanically checked, not just asserted in prose).
# --------------------------------------------------------------------------- #
def test_section_114_85_category_map():
    expected_tests = {
        # stress
        "test_stress_sustained_load_large_dedup",
        "test_stress_concurrent_determinism",
        "test_boundary_empty_input",
        "test_boundary_single_result",
        "test_boundary_all_identical_one_row",
        "test_boundary_all_unique_n_rows",
        "test_boundary_fuzzy_threshold_edges",
        # chaos
        "test_chaos_malformed_partial_results",
        "test_chaos_adversarial_near_duplicate_storm",
        "test_chaos_conflicting_infohash_metadata",
    }
    module = sys.modules[__name__]
    present = {name for name in dir(module) if name.startswith("test_")}
    missing = expected_tests - present
    assert not missing, f"§11.4.85 category map missing tests: {missing}"

    _write_evidence(
        "category_map",
        {
            "section": "11.4.85",
            "category": "meta/category-map",
            "stress_categories": [
                "sustained-load",
                "concurrent-contention",
                "boundary-empty",
                "boundary-single",
                "boundary-all-identical",
                "boundary-all-unique",
                "boundary-fuzzy-edge",
            ],
            "chaos_categories": [
                "input-fault-malformed",
                "adversarial-storm",
                "state-corruption",
            ],
            "tests_present": sorted(expected_tests & present),
        },
    )
