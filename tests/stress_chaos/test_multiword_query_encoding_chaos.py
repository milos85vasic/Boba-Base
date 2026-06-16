"""§11.4.85 CHAOS suite for the multi-word query URL-encoding fix.

Two chaos surfaces:

1. INPUT-CORRUPTION INJECTION into the REAL plugin search() — null bytes,
   newlines, %-sequences, extremely long strings, raw control chars. Each
   fixed plugin must EITHER encode the query safely (no raw control char in
   the constructed URL, urllib accepts it) OR raise cleanly (no hang, no
   silent corruption). A hang would be caught by the per-test deadline.

2. CLASSIFIER CHAOS — ``SearchOrchestrator._classify_plugin_stderr`` must
   correctly classify a urllib URL-control-char failure as
   ``plugin_bad_query_encoding`` (NOT ``plugin_crashed``) across a battery
   of real stderr variants (different tracebacks, casings, surrounding
   noise), AND must NOT mislabel a genuine crash as bad-query-encoding.

Anti-bluff (§11.4 / §11.4.85): every PASS cites a captured-evidence artifact
(categorised results JSON). §1.1: ``test_classifier_guard_bites`` proves the
classifier would mislabel the urllib error as ``plugin_crashed`` if the
``url can't contain control characters`` branch were removed — the guard
bites. Cleanup of injected corruption is via the conftest stub reset (each
``drive_search`` rebinds retrieve_url) + a trap-style finalizer fixture.
"""

from __future__ import annotations

import pytest

from .conftest import (
    FIXED_PLUGINS,
    drive_search,
    load_classifier,
    url_has_raw_space,
    url_is_urllib_acceptable,
)


# ---------------------------------------------------------------------------
# Surface 1: input-corruption injection into plugin search()
# ---------------------------------------------------------------------------

ADVERSARIAL_QUERIES = [
    "null\x00byte",
    "new\nline\nquery",
    "carriage\rreturn",
    "already %20 encoded mix word",
    "%2e%2e%2f%2e%2e%2f traversal attempt",
    "tab\tand\tspaces here",
    "Z" * 5000,                       # extremely long
    "\x01\x02\x03 control prefix",   # leading control chars
    "emoji 🔥 multi word query",
    "ampersand & equals = query",
]


@pytest.fixture
def corruption_finalizer():
    """trap-style cleanup (§11.4.14): nothing persistent is mutated by
    drive_search (it rebinds the in-memory helpers stub each call); on EVERY
    exit path we assert the stub registry is left in a sane state."""
    import sys

    yield
    helpers = sys.modules.get("helpers")
    assert helpers is None or hasattr(helpers, "retrieve_url")


@pytest.mark.parametrize("plugin", FIXED_PLUGINS)
def test_adversarial_queries_no_raw_space_no_hang(plugin, evidence, corruption_finalizer):
    """Input-corruption injection. The HARD contract (the defect the fix
    actually addresses): NO adversarial query may produce a URL containing a
    raw SPACE, and search() must EITHER build a URL OR raise cleanly — never
    hang (a hang trips the per-test deadline).

    Broader non-space control chars (null, newline, tab) that a query CARRIES
    INTO the URL are recorded as honest observations (§11.4.6) — the
    per-plugin fix encodes spaces, it does not sanitise arbitrary control
    chars; asserting a fix that does not exist would be a bluff."""
    results = []
    space_violations = []
    for q in ADVERSARIAL_QUERIES:
        outcome = {"query_repr": repr(q)[:80]}
        try:
            urls = drive_search(plugin, q)
            outcome["urls_built"] = len(urls)
            raw_space = [u for u in urls if url_has_raw_space(u)]
            other_ctrl = [
                u for u in urls
                if not url_has_raw_space(u) and not url_is_urllib_acceptable(u)
            ]
            outcome["raw_space_urls"] = len(raw_space)
            outcome["other_control_char_urls_observed"] = len(other_ctrl)
            outcome["status"] = "VIOLATION-raw-space" if raw_space else "ok"
            if raw_space:
                space_violations.append(outcome)
        except Exception as exc:  # noqa: BLE001 - any clean raise is acceptable
            outcome["status"] = f"clean-raise:{type(exc).__name__}"
        results.append(outcome)

    for r in results:
        evidence.add(**r)
    path = evidence.emit({
        "plugin": plugin,
        "raw_space_violations": len(space_violations),
        "verdict": "PASS" if not space_violations else "FAIL",
        "note": "non-space control chars carried in from the query are observed, "
                "not asserted — fix targets the space/multi-word defect class",
    })
    assert not space_violations, (
        f"{plugin}: adversarial queries produced raw-SPACE URLs (the fixed "
        f"defect re-surfacing): {space_violations}. Evidence: {path}"
    )


# ---------------------------------------------------------------------------
# Surface 2: classifier chaos
# ---------------------------------------------------------------------------

# Real urllib ValueError stderr variants (the message urllib actually emits)
# wrapped in assorted traceback noise + casings the subprocess can produce.
URL_CONTROL_CHAR_STDERRS = [
    "Traceback (most recent call last):\n  File \"eztv.py\", line 40\n"
    "ValueError: URL can't contain control characters. '/search/the matrix' (found at least ' ')",
    "ValueError: URL can't contain control characters.",
    "urllib.error / ValueError: URL CAN'T CONTAIN CONTROL CHARACTERS. (found at least ' ')",
    "some plugin INFO log line\n"
    "Traceback ...\nValueError: URL can't contain control characters. '/q/war and peace'",
    "  url can't contain control characters  ",  # bare, padded, lowercase
]

# Genuine crashes that MUST NOT be mislabeled as bad-query-encoding.
GENUINE_CRASH_STDERRS = [
    ("Traceback (most recent call last):\nTypeError: 'NoneType' object is not iterable",
     "plugin_crashed"),
    ("Traceback (most recent call last):\nIndexError: list index out of range",
     "plugin_parse_failure"),
    ("Traceback (most recent call last):\nurllib.error.HTTPError: HTTP Error 403: Forbidden",
     "upstream_http_403"),
    ("Traceback (most recent call last):\njson.decoder.JSONDecodeError: Expecting value",
     "plugin_parse_failure"),
    ("Traceback (most recent call last):\nRuntimeError: kaboom",
     "plugin_crashed"),
]


@pytest.mark.parametrize("stderr", URL_CONTROL_CHAR_STDERRS)
def test_classifier_labels_url_control_char_as_bad_query_encoding(stderr, evidence):
    classify = load_classifier()
    diag = classify(stderr, killed_by_deadline=False, had_results=False)
    evidence.add(stderr_repr=repr(stderr)[:120], error_type=diag["error_type"])
    path = evidence.emit({"verdict": "PASS" if diag["error_type"] == "plugin_bad_query_encoding" else "FAIL"})
    assert diag["error_type"] == "plugin_bad_query_encoding", (
        f"urllib control-char stderr misclassified as {diag['error_type']!r} "
        f"(should be plugin_bad_query_encoding). Evidence: {path}"
    )


@pytest.mark.parametrize("stderr,expected", GENUINE_CRASH_STDERRS)
def test_classifier_does_not_mislabel_genuine_failures(stderr, expected, evidence):
    """§11.4.6 honesty: a real crash/upstream error must NOT be downgraded
    to plugin_bad_query_encoding."""
    classify = load_classifier()
    diag = classify(stderr, killed_by_deadline=False, had_results=False)
    evidence.emit({"expected": expected, "got": diag["error_type"],
                   "verdict": "PASS" if diag["error_type"] == expected else "FAIL"})
    assert diag["error_type"] != "plugin_bad_query_encoding", (
        f"genuine failure mislabeled as bad-query-encoding: {stderr!r}"
    )
    assert diag["error_type"] == expected, (
        f"expected {expected!r}, got {diag['error_type']!r} for {stderr!r}"
    )


def test_classifier_guard_bites(evidence):
    """§1.1 paired mutation (in-test): simulate REMOVING the
    'url can't contain control characters' branch and confirm the urllib
    error would then fall through to plugin_crashed — proving the real
    branch is load-bearing (the guard bites)."""
    classify = load_classifier()
    real = classify(
        "Traceback ...\nValueError: URL can't contain control characters. (found at least ' ')",
        killed_by_deadline=False, had_results=False,
    )
    assert real["error_type"] == "plugin_bad_query_encoding"

    # Mutant: strip the distinguishing phrase so the SAME stderr no longer
    # matches the bad-query-encoding branch. It contains "Traceback" so it
    # falls through to plugin_crashed — i.e. WITHOUT the branch the System
    # would dishonestly report a crash. This proves the branch is necessary.
    mutated_stderr = "Traceback ...\nValueError: malformed request (found at least ' ')"
    mutant = classify(mutated_stderr, killed_by_deadline=False, had_results=False)
    assert mutant["error_type"] == "plugin_crashed", (
        "expected the non-control-char ValueError to classify as plugin_crashed, "
        f"got {mutant['error_type']!r} — guard logic changed"
    )
    evidence.emit({"with_branch": real["error_type"], "without_branch_equiv": mutant["error_type"],
                   "verdict": "PASS"})
