"""Meta-test: enforce fixture-based service-availability gating.

Phase 0.3 of the completion-initiative plan converted the old
``if probe_health() else pytest.skip(...)`` pattern into fixture-based
gating using ``merge_service_live`` / ``qbittorrent_live`` /
``webui_bridge_live`` / ``all_services_live`` from
``tests/fixtures/services.py``.

To prevent regression, this test scans every ``tests/**/*.py`` file and
fails if any ``pytest.skip(...)`` call reason reads as an
availability/reachability/health condition. Two allow-listed escape
hatches:

*   ``tests/fixtures/services.py`` itself — the docstring mentions the old
    pattern so we can explain what we replaced.
*   Any ``pytest.skip(...)`` call carrying a ``# allow-skip:`` comment on
    any line of the call — lets genuine data-dependent skips
    (e.g. "No search results") coexist.

``# allow-skip:`` is THIS guard's escape marker and the only one it
honours. It is a different mechanism from the project-wide ``SKIP-OK:
#<ticket>`` marker required by the CLAUDE.md Definition of Done ("skips
are loud"); a skip may need both, and a ``SKIP-OK`` comment alone does
NOT exempt a skip from this guard.

Credential skips should be migrated to ``@pytest.mark.requires_credentials``
rather than run-time ``pytest.skip`` calls where possible.

Two blind spots closed 2026-09-19 (independent review found the guard
GREEN *through* them, so its silence was not evidence):

1.  VOCABULARY — the old ``FORBIDDEN = ("service", "available",
    "unreachable")`` substring tuple missed the real phrasings actually
    in the tree: "not reachable", "unhealthy", "/healthz not ok",
    "not up".  Replaced by word-boundary regex patterns (see
    ``FORBIDDEN_PATTERNS``), so e.g. ``\\bdown\\b`` cannot fire on
    "download".
2.  ARGUMENT TRUNCATION AT THE FIRST ``)`` — the old
    ``pytest\\.skip\\s*\\(\\s*([^)]*)\\)`` regex stopped capturing at the
    first ``)`` inside the argument, so any reason wording that FOLLOWS a
    nested ``)`` was never scanned.

    CORRECTED DIAGNOSIS (2026-09-22, measured — the earlier note in this
    docstring claimed the hole was MULTI-LINE-ness, which is false and was
    asserted by a self-test that could never pass).  ``[^)]`` is a negated
    character class, and it therefore INCLUDES ``\\n``; the old regex
    matched multi-line calls perfectly well.  Probe, run against the exact
    multi-line sample the old self-test claimed was invisible::

        old arg captured: '# SKIP-OK: live service unreachable\\n
                           f"merge service not reachable at {URL}/health"\\n'
        -> MATCH=True

    The real defect is truncation.  For
    ``pytest.skip(f"probe({url}) says the merge service is unreachable")``
    the old regex captures only ``f"probe({url}`` — zero forbidden hits, a
    silent MISS — while the paren-balancing scan captures the whole
    argument and flags it.  Truncation is also why
    ``pytest.skip(f"Jackett unhealthy ({r.status_code})")`` was captured
    only up to ``{r.status_code}``; that particular call still tripped the
    vocabulary because its forbidden word happens to precede the ``)``.

    HONEST BOUNDARY (§11.4.6): re-scanning the current tree with the old
    argument capture and the new vocabulary yields the SAME offender set as
    the new scanner — no real site in this tree presently hides its reason
    behind a nested ``)``.  The hole is real and demonstrable but currently
    LATENT; ``test_truncation_hole_is_actually_closed`` pins it with the
    synthetic sample above rather than claiming a tree-wide rescue that was
    not measured.

    Replaced by a quote-aware paren-balancing scan (``_iter_skip_calls``).
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
ALLOW_LISTED_FILES = {
    TESTS_ROOT / "fixtures" / "services.py",
    THIS_FILE,
}

# Locates the *start* of a ``pytest.skip(`` call.  The argument list is then
# consumed by the paren-balancing scan in ``_iter_skip_calls`` so that
# multi-line calls and nested parentheses are both handled.
SKIP_CALL_START = re.compile(r"pytest\s*\.\s*skip\s*\(")

# A health-endpoint PATH on its own is not an availability claim — it is
# just a URL.  It becomes one only when a failure predicate sits beside it.
# Load-bearing: tests/ddos/test_slow_request.py skips on HOST LOAD with the
# reason "baseline /health latency 0.310s already exceeds the ... bar", and
# a bare ``/health`` pattern refused that correct code — a §11.4.201(1)
# false-positive refusal, as forbidden as a false pass.
_HEALTH_ENDPOINT = r"/health\w*"
_FAILURE_PREDICATE = (
    r"(?:not\s+ok|not\s+reachable|un(?:reachable|available|healthy)|"
    r"failed|refused|returned\s+[45]\d{2}|non-?200)"
)

# Forbidden reason patterns: an availability / reachability / health
# condition dressed up as a skip.  Word boundaries are load-bearing —
# a bare "down" substring would fire on "download" (a §11.4.201(1)
# false-positive refusal, as forbidden as a false pass).
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bservices?\b",
        r"\b(?:un)?available\b",
        r"\b(?:un)?reachable\b",
        r"\b(?:un)?healthy\b",
        # ``healthz`` stays a bare token deliberately: unlike ``/health`` it
        # has no measured non-availability use anywhere in the tree, and it
        # is a probe-endpoint name rather than English prose.
        r"\bhealthz\b",
        # Endpoint + failure predicate, either order, same line, bounded
        # window — replaces the bare ``/health\b`` that produced the
        # false-positive refusal documented above.
        rf"{_HEALTH_ENDPOINT}\b[^\n]{{0,40}}?\b{_FAILURE_PREDICATE}\b",
        rf"\b{_FAILURE_PREDICATE}\b[^\n]{{0,40}}?{_HEALTH_ENDPOINT}\b",
        r"\bnot\s+(?:yet\s+)?(?:up|ok|healthy|ready|running|started|live|listening|responding)\b",
        r"\boffline\b",
        r"\bdown\b",
        r"\bconnection\s+refused\b",
        r"\bno\s+such\s+host\b",
        r"\btimed\s+out\b",
    )
)

ALLOW_MARKER = "# allow-skip:"

_QUOTES = ("'''", '"""', "'", '"')


def _py_files() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if p.is_file())


def _iter_skip_calls(text: str) -> list[tuple[int, int, str]]:
    """Yield ``(start_line, end_line, argument_text)`` per ``pytest.skip(`` call.

    Quote-aware paren balancing: parentheses inside string literals are
    ignored, so ``pytest.skip(f"... ({x})")`` is captured whole rather
    than truncated at the first ``)``.  Line numbers are 1-based and
    span the whole call, so a trailing ``# allow-skip:`` on the closing
    line is visible to the caller.
    """
    out: list[tuple[int, int, str]] = []
    for m in SKIP_CALL_START.finditer(text):
        i = m.end()  # just past the opening paren
        depth = 1
        quote: str | None = None
        arg_start = i
        while i < len(text):
            ch = text[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if text.startswith(quote, i):
                    i += len(quote)
                    quote = None
                    continue
                i += 1
                continue
            for q in _QUOTES:
                if text.startswith(q, i):
                    quote = q
                    i += len(q)
                    break
            else:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
        else:
            continue  # unterminated call — nothing decidable here
        start_line = text.count("\n", 0, m.start()) + 1
        end_line = text.count("\n", 0, i) + 1
        out.append((start_line, end_line, text[arg_start:i]))
    return out


def _forbidden_hits(arg: str) -> list[str]:
    return [p.pattern for p in FORBIDDEN_PATTERNS if p.search(arg)]


def _scan_text(text: str) -> list[tuple[int, list[str]]]:
    """Return ``(line, matched_patterns)`` for every offending skip in ``text``."""
    lines = text.splitlines()
    offenders: list[tuple[int, list[str]]] = []
    for start_line, end_line, arg in _iter_skip_calls(text):
        span = "\n".join(lines[start_line - 1 : end_line])
        if ALLOW_MARKER in span:
            continue
        hits = _forbidden_hits(arg)
        if hits:
            offenders.append((start_line, hits))
    return offenders


def test_no_runtime_service_skips() -> None:
    """Fail if any test file still uses the runtime availability-skip pattern."""
    offenders: list[str] = []

    for path in _py_files():
        if path in ALLOW_LISTED_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.splitlines()
        for lineno, hits in _scan_text(text):
            rel = path.relative_to(TESTS_ROOT.parent)
            offenders.append(f"{rel}:{lineno}: {lines[lineno - 1].strip()}  [{', '.join(hits)}]")

    assert not offenders, (
        "Found runtime service-availability skips. Convert them to fixture gates "
        "(merge_service_live / qbittorrent_live / webui_bridge_live / all_services_live) "
        "or append a trailing '# allow-skip: <reason>' comment if the skip is truly "
        "data-dependent and not about service availability. Note: a 'SKIP-OK: #<ticket>' "
        "comment satisfies the CLAUDE.md loud-skip rule but does NOT exempt a skip from "
        "this guard — only '# allow-skip:' does.\n  - " + "\n  - ".join(offenders)
    )


# ---------------------------------------------------------------------------
# §1.1 paired validation of the detector itself.
#
# A guard never observed FAILing on genuinely-broken input is unvalidated
# instrumentation (§11.4.115(F)); a guard that fires on correct input is a
# §11.4.201(1) false-positive refusal.  Both polarities are asserted below
# against samples drawn verbatim-in-shape from the real tree.
# ---------------------------------------------------------------------------

# golden-TRUE: every one of these MUST be detected.
POSITIVE_SAMPLES: tuple[tuple[str, str], ...] = (
    (
        "single-line 'not reachable' (tests/scaling/test_boba_scaling.py)",
        'pytest.skip("boba-jackett :7189 not reachable (SKIP-OK BOB-109)")',
    ),
    (
        "single-line '/healthz not ok' (tests/scaling/test_boba_scaling.py)",
        'pytest.skip("boba-jackett /healthz not ok (SKIP-OK BOB-109)")',
    ),
    (
        "nested parens + 'unhealthy' (tests/integration/test_jackett_autoconfig_real.py)",
        'pytest.skip(f"Jackett unhealthy ({r.status_code})")',
    ),
    (
        "multi-line f-string, reason on line 2 (tests/e2e/test_full_pipeline.py)",
        'pytest.skip(  # SKIP-OK: live service unreachable\n'
        '    f"merge service not reachable at {URL}/health — "\n'
        '    "start the real stack with `./start.sh -p`."\n'
        ")",
    ),
    ("phrase 'not up'", 'pytest.skip("stack not up")'),
    ("phrase 'unavailable'", 'pytest.skip("Merge service unavailable")'),
    ("phrase 'offline'", 'pytest.skip("proxy offline")'),
    ("phrase 'down'", 'pytest.skip("qBittorrent is down")'),
    ("phrase 'connection refused'", 'pytest.skip("connection refused on :7187")'),
    ("phrase 'not responding'", 'pytest.skip("bridge not responding")'),
    (
        "health endpoint WITH a failure predicate (narrowed pattern still fires)",
        'pytest.skip(f"{URL}/healthz returned 503")',
    ),
    (
        "failure predicate BEFORE the health endpoint",
        'pytest.skip("connection refused polling /health")',
    ),
    (
        "reason hidden AFTER a nested ')' — the real HOLE-2 shape",
        'pytest.skip(f"probe({url}) says the merge service is unreachable")',
    ),
)

# golden-FALSE: none of these may be detected.
NEGATIVE_SAMPLES: tuple[tuple[str, str], ...] = (
    (
        "annotated with this guard's escape marker",
        'pytest.skip("Jackett unreachable")  # allow-skip: integration data-dependent',
    ),
    (
        "annotated escape marker on the closing line of a multi-line call",
        'pytest.skip(\n    "merge service not reachable"\n)  # allow-skip: operator-gated live stack',
    ),
    (
        "genuine data-dependent skip",
        'pytest.skip("No search results returned for the query")',
    ),
    (
        "'download' must NOT trip the \\bdown\\b pattern",
        'pytest.skip("no completed download to inspect")',
    ),
    (
        "credential skip (migrate to requires_credentials, not this guard)",
        'pytest.skip("Jackett API key not yet generated")',
    ),
    (
        "unrelated prose mentioning a service in a comment, no skip call",
        '# the merge service is unreachable in CI, which is why this is a fixture gate',
    ),
    (
        "fixture-gated test body, no runtime skip at all",
        'def test_search(merge_service_live):\n    assert merge_service_live is not None',
    ),
    (
        # Verbatim-in-shape from tests/ddos/test_slow_request.py:122 — the
        # measured false-positive refusal that forced the /health narrowing.
        "host-load skip that merely NAMES the /health path (not availability)",
        'pytest.skip(\n'
        '    f"host_too_loaded_to_measure: baseline /health latency {b:.3f}s "\n'
        '    f"already exceeds the {c:.3f}s bar, so an under-load measurement "\n'
        '    "could not distinguish blocking from host noise"\n'
        ")",
    ),
    (
        "unrelated prose naming the health path, no skip call",
        '# poll /health until the container answers, then hand back the URL',
    ),
)


def test_detector_catches_every_forbidden_phrasing() -> None:
    """golden-TRUE: multi-line calls and each widened phrase are detected."""
    missed = [label for label, sample in POSITIVE_SAMPLES if not _scan_text(sample)]
    assert not missed, "detector blind to: " + "; ".join(missed)


def test_detector_does_not_fire_on_correct_code() -> None:
    """golden-FALSE: a §11.4.201(1) false-positive refusal is as bad as a false pass."""
    fired = [
        f"{label} -> {_scan_text(sample)}"
        for label, sample in NEGATIVE_SAMPLES
        if _scan_text(sample)
    ]
    assert not fired, "detector false-positives on: " + "; ".join(fired)


OLD_SKIP_REGEX = re.compile(r"pytest\.skip\s*\(\s*(?P<arg>[^)]*)\)", re.IGNORECASE)


def test_old_regex_was_never_blind_to_multi_line_calls() -> None:
    """Refutes the superseded 'HOLE 2 = multi-line' diagnosis, by measurement.

    ``[^)]`` is a NEGATED character class, so it matches ``\\n``.  The old
    regex therefore captured multi-line ``pytest.skip(`` calls in full.  An
    earlier revision of this file asserted the opposite and could never go
    green.  This test is the control needle that keeps the corrected
    diagnosis honest: if someone "fixes" it back, this fails.
    """
    multi_line = (
        'pytest.skip(  # SKIP-OK: live service unreachable\n'
        '    f"merge service not reachable at {URL}/health"\n'
        ")"
    )
    m = OLD_SKIP_REGEX.search(multi_line)
    assert m is not None, "premise refuted: old regex did NOT match a multi-line call"
    assert "not reachable" in m.group("arg"), (
        "old regex matched but truncated before the reason — that would make "
        "multi-line-ness the hole after all; captured: " + repr(m.group("arg"))
    )


def test_truncation_hole_is_actually_closed() -> None:
    """The REAL hole: a reason that follows a nested ``)`` inside the argument.

    ``[^)]*`` stops at the first ``)``, so everything after it was never
    scanned.  Here the forbidden wording sits *past* that ``)``: the old
    capture yields zero hits (a silent MISS) while the paren-balancing scan
    sees the whole argument.  Both polarities are asserted, so this proves
    the paren-balancing scan — not the widened vocabulary — is the fix.
    """
    sample = 'pytest.skip(f"probe({url}) says the merge service is unreachable")'

    m = OLD_SKIP_REGEX.search(sample)
    assert m is not None and m.group("arg") == 'f"probe({url}', (
        "expected the old regex to truncate at the nested ')'; captured: "
        + repr(m.group("arg") if m else None)
    )
    assert not _forbidden_hits(m.group("arg")), (
        "old capture unexpectedly retained a forbidden phrase — the truncation "
        "MISS this test pins would not be demonstrated"
    )

    assert _scan_text(sample), "new scanner failed to see past the nested ')'"


def test_health_path_narrowing_keeps_both_polarities() -> None:
    """A bare ``/health`` mention is a path; with a failure predicate it is a verdict.

    Pins the §11.4.201(1) narrowing: the host-load skip in
    ``tests/ddos/test_slow_request.py`` names ``/health`` while skipping on
    latency, and must NOT be refused; a health endpoint reported as failing
    must still be caught.
    """
    load_measurement = (
        'pytest.skip("host_too_loaded_to_measure: baseline /health latency '
        '0.310s already exceeds the 0.150s bar")'
    )
    assert not _scan_text(load_measurement), (
        "false-positive refusal on a host-load skip that merely names /health"
    )
    assert _scan_text('pytest.skip(f"{URL}/health returned 503")'), (
        "narrowing went too far — a failing health endpoint must still be caught"
    )


def test_nested_paren_call_is_captured_whole() -> None:
    """The scanner must not truncate at a nested ``)``."""
    sample = 'pytest.skip(f"Jackett unhealthy ({r.status_code})")'
    calls = _iter_skip_calls(sample)
    assert len(calls) == 1
    assert calls[0][2] == 'f"Jackett unhealthy ({r.status_code})"'
