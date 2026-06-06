"""§11.4.85 chaos / fault-injection tests for the offline search pipeline.

OFFLINE + DETERMINISTIC: these inject malformed / empty / corrupt inputs at
the in-process boundaries of the pipeline and assert graceful, *categorised*
handling — no unhandled exception, well-formed structured output. They
complement the live-service chaos test in ``tests/chaos/test_tracker_failure.py``.

Fault classes (per §11.4.85, applied where appropriate to this fix-class):
- input-corruption injection into ``_classify_plugin_stderr`` (the only signal
  we get about why a public-tracker subprocess returned zero rows) — malformed,
  empty, truncated, binary-garbage, and every known error-class stderr;
- state/input-corruption injection into the deduplicator + enricher — corrupt
  SearchResult field values (empty, oversized, unicode, malformed magnets,
  numeric size sentinels) must not crash the fan-out.

Anti-bluff (§11.4.5 / §11.4.69): each PASS writes a categorised-evidence JSON
artefact under ``qa-results/pipeline_chaos/<run-id>/`` recording exactly which
fault was injected and how it was categorised — a real observable outcome, not
"no error".
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"merge_service.{modname}", str(_MS_PATH / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"merge_service.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


_search_mod = _load("search", "search.py")
_dedup_mod = _load("deduplicator", "deduplicator.py")
_enricher_mod = _load("enricher", "enricher.py")

SearchResult = _search_mod.SearchResult
Deduplicator = _dedup_mod.Deduplicator
MetadataEnricher = _enricher_mod.MetadataEnricher
classify_stderr = _search_mod._classify_plugin_stderr


_RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "pipeline_chaos" / _RUN_ID


def _write_evidence(name: str, payload) -> Path:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    assert path.exists() and path.stat().st_size > 0
    return path


# --------------------------------------------------------------------------- #
# stderr classification fault injection
# --------------------------------------------------------------------------- #
@pytest.mark.chaos
def test_classify_stderr_malformed_inputs_always_well_formed() -> None:
    """Every malformed / garbage stderr yields a well-formed diagnostic dict.

    The classifier is the only place that turns a crashed-or-blocked plugin
    subprocess into something the dashboard can show. If ANY input makes it
    raise (or return a malformed dict), the whole tracker stat goes missing.
    """
    fault_inputs = [
        ("empty", ""),
        ("whitespace", "   \n\t  "),
        ("none_like", None),
        ("binary_garbage", "\x00\x01\x02\xff\xfe not utf safe"),
        ("truncated_traceback", "Traceback (most recent call l"),
        ("http_403", "urllib.error.HTTPError: HTTP Error 403: Forbidden"),
        ("http_404", "ConnectionError: Not Found"),
        ("dns", "socket.gaierror: [Errno -2] Name does not resolve"),
        ("tls", "ssl: TLSV1_ALERT_INTERNAL_ERROR"),
        ("indexerror", "IndexError: list index out of range"),
        ("typeerror", "TypeError: 'NoneType' object is not iterable"),
        ("jsondecode", "json.decoder.JSONDecodeError: Expecting value"),
        ("incompleteread", "http.client.IncompleteRead(0 bytes read)"),
        ("benign_noise", '{"__done__": 0}'),
        ("huge", "x" * 100_000),
    ]

    categorised: dict[str, dict] = {}
    for label, stderr in fault_inputs:
        for killed in (True, False):
            for had in (True, False):
                diag = classify_stderr(stderr, killed_by_deadline=killed, had_results=had)
                # Structural contract — must always be a dict with these keys.
                assert isinstance(diag, dict)
                assert set(diag.keys()) == {"error_type", "error", "stderr_tail"}
                assert diag["error_type"] is None or isinstance(diag["error_type"], str)
                assert diag["error"] is None or isinstance(diag["error"], str)
                assert isinstance(diag["stderr_tail"], str)
        # Record the canonical (not-killed, no-results) categorisation.
        categorised[label] = classify_stderr(stderr, killed_by_deadline=False, had_results=False)

    # Real observable outcomes: the known crash classes ARE categorised.
    assert categorised["http_403"]["error_type"] == "upstream_http_403"
    assert categorised["indexerror"]["error_type"] == "plugin_parse_failure"
    assert categorised["typeerror"]["error_type"] == "plugin_crashed"
    assert categorised["jsondecode"]["error_type"] == "plugin_parse_failure"
    assert categorised["dns"]["error_type"] == "dns_failure"
    # Empty stderr with no deadline kill stays uncategorised (benign).
    assert categorised["empty"]["error_type"] is None
    # The huge tail is truncated, never echoed whole.
    assert len(categorised["huge"]["stderr_tail"]) <= 400

    _write_evidence("classify_stderr_faults", categorised)


@pytest.mark.chaos
def test_classify_stderr_deadline_timeout_path() -> None:
    """Killed-by-deadline + empty stderr + no results -> deadline_timeout."""
    diag = classify_stderr("", killed_by_deadline=True, had_results=False)
    assert diag["error_type"] == "deadline_timeout"
    assert "deadline" in diag["error"].lower()
    # If it DID have results, an empty stderr is benign, not a timeout.
    diag2 = classify_stderr("", killed_by_deadline=True, had_results=True)
    assert diag2["error_type"] is None
    _write_evidence("classify_stderr_deadline", {"timeout": diag, "had_results": diag2})


# --------------------------------------------------------------------------- #
# deduplicator corrupt-input fault injection
# --------------------------------------------------------------------------- #
def _corrupt_results() -> list:
    """A batch of SearchResults with hostile-but-type-correct field values."""
    return [
        SearchResult(name="", link="", size="", seeds=0, leechers=0, engine_url=""),
        SearchResult(
            name="x" * 5000,  # absurdly long name
            link="not-a-magnet-or-url",
            size="-1",  # negative-size sentinel some plugins emit
            seeds=-5,
            leechers=-3,
            engine_url="ftp://weird.example",
        ),
        SearchResult(
            name="Ünïcödé 日本語 🎬 Title 2023",
            link="magnet:?xt=urn:btih:short",  # too-short infohash
            size="9999999 PB",  # unknown unit
            seeds=10**9,
            leechers=0,
            engine_url="https://t.example",
        ),
        SearchResult(
            name="Valid Movie 2023 1080p BluRay",
            link="magnet:?xt=urn:btih:" + ("C" * 40),
            size="2.0 GB",
            seeds=50,
            leechers=2,
            engine_url="https://t2.example",
            tracker="t2",
        ),
        SearchResult(
            name="Valid Movie 2023 1080p BluRay",  # duplicate by name+size
            link="magnet:?xt=urn:btih:" + ("C" * 40),
            size="2.0 GB",
            seeds=80,
            leechers=1,
            engine_url="https://t3.example",
            tracker="t3",
        ),
    ]


@pytest.mark.chaos
def test_deduplicator_handles_corrupt_results_without_crashing() -> None:
    """Corrupt / hostile SearchResults must dedup gracefully (no exception)."""
    dedup = Deduplicator()
    merged = dedup.merge_results(_corrupt_results())

    # Observable outcome: pipeline produced groups, did not crash, and the two
    # identical-infohash "Valid Movie" rows collapsed into ONE group.
    assert isinstance(merged, list)
    assert 1 <= len(merged) <= 5
    total_sources = sum(len(g.original_results) for g in merged)
    assert total_sources == 5, "every input must be accounted for in some group"

    # The duplicate pair (same 40-char infohash) must be one group of 2.
    dup_groups = [g for g in merged if len(g.original_results) == 2]
    assert len(dup_groups) == 1, "the same-infohash duplicate pair must collapse"

    _write_evidence(
        "dedup_corrupt_inputs",
        {
            "input_count": 5,
            "group_count": len(merged),
            "total_sources_accounted": total_sources,
            "duplicate_group_sizes": [len(g.original_results) for g in merged],
        },
    )


@pytest.mark.chaos
def test_dedup_parse_size_chaos_values() -> None:
    """_parse_size must tolerate every corrupt size value (None/int/garbage)."""
    dedup = Deduplicator()
    cases = {
        "none": None,
        "empty": "",
        "negative_int": -1,
        "zero": 0,
        "float": 1234.5,
        "garbage": "not a size",
        "unknown_unit": "5 PB",
        "valid_gb": "2.0 GB",
        "no_space": "700MB",
    }
    out = {}
    for label, value in cases.items():
        parsed = dedup._parse_size(value)  # must never raise
        assert parsed is None or isinstance(parsed, float)
        out[label] = parsed
    # A genuinely valid size still parses to a positive number.
    assert out["valid_gb"] == 2.0 * 1024**3
    assert out["none"] is None and out["garbage"] is None and out["negative_int"] is None
    _write_evidence("parse_size_chaos", out)


# --------------------------------------------------------------------------- #
# enricher corrupt-input fault injection
# --------------------------------------------------------------------------- #
@pytest.mark.chaos
def test_enricher_detect_quality_handles_garbage_names() -> None:
    """detect_quality must categorise or safely return None for any input."""
    enricher = MetadataEnricher()
    cases = {
        "empty": "",
        "unicode": "日本語 🎬 garbage",
        "huge": "z" * 20000,
        "control_chars": "\x00\x01\x02 title 1080p",
        "valid_4k": "Movie 2023 2160p UHD BluRay",
        "valid_1080": "Movie 2023 1080p WEB-DL",
        "no_quality": "Some Random Title Without Quality",
    }
    out = {}
    for label, name in cases.items():
        q = enricher.detect_quality(name)  # must never raise
        assert q is None or isinstance(q, str)
        out[label] = q
    # Real observable outcomes: quality IS detected when present.
    assert out["valid_4k"] == "4K"
    assert out["valid_1080"] == "1080p"
    assert out["no_quality"] is None
    _write_evidence("detect_quality_chaos", out)
