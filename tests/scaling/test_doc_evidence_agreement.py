"""Mechanical doc-vs-evidence agreement check (BOB-109).

WHY THIS FILE EXISTS
--------------------
An earlier revision of ``docs/testing/scaling.md`` quoted dedup p50
66.1/232.8/955.9/3308.1 with span 1.882 while the artifact it cited
contained 33.1/112.1/452.7/2813.8 and a span of 2.1359 — a run that
VIOLATED that file's own 2.10 gate. The doc had been hand-transcribed
from runs whose artifacts were later overwritten (the evidence channel
was last-write-wins), so the tables cited figures their own evidence no
longer contained.

That was fixed by re-transcribing. Re-transcription is not a mechanism:
drift recurred twice more during the same authoring session, and the
scheduled BOB-170 quiescent run will require transcribing again. The
author then REPORTED that "a mechanical check confirms every figure is
backed" — while the checker lived in a scratch directory outside the
deliverable. Per §11.4.215 an un-tracked artifact is not binding: nobody
else could run it, inspect it, or ask whether it passes vacuously. And
per §11.4.262, reporting a mechanical result whose mechanism is not in
the deliverable is the wrong shape even when the result is true.

So the checker lives here, tracked, runnable by anyone, with its own
anti-vacuity assertions.

WHAT IT PROVES — and what it does not
-------------------------------------
PROVES: every decimal figure quoted in the doc's measured-baselines
section equals an actual NUMERIC VALUE in a committed artifact, that the
doc names the artifacts' ``run_id``, and that all artifacts come from
ONE run.

The word VALUE is load-bearing. This check first matched figures as
SUBSTRINGS of the concatenated artifact JSON, and a reviewer defeated it
with the likeliest hand-transcription error there is: rounding a table
cell while tidying it. ``26.131 ms`` retyped as ``26.1 ms`` PASSED,
because ``"26.1"`` is a prefix of ``"26.131"`` — a figure appearing in
NO artifact, waved through by the mechanism the doc leans on. Truncation
(``438.26`` -> ``438.2``) passed the same way, and prose could "back" a
figure: ``11.4`` was extracted from a ``§11.4.x`` citation and matched
the string ``"§11.4.119"`` inside an artifact's ``method`` field.
Comparing against parsed numeric values kills all three.

DOES NOT PROVE: that the numbers are *correct*, that the right figure
was quoted for the right axis, or that prose around them is accurate.
It is a containment check against transcription drift, not an oracle
(§11.4.6).

EXPECTED BEHAVIOUR AFTER A FRESH SUITE RUN
------------------------------------------
Running the whole ``tests/scaling/`` suite REGENERATES the artifacts
with a new ``run_id``. Until the doc's tables are re-transcribed from
them, this checker FAILS — by design, and it is not a broken suite. It
did exactly that on its first full run, within minutes of being
written. Re-transcribe the measured-baselines section from
``docs/qa/BOB-109/*.json`` and re-run; that is the drift it exists to
force someone to notice. Running this file ALONE never regenerates
anything and is safe at any time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "testing" / "scaling.md"
EVIDENCE_DIR = REPO_ROOT / "docs" / "qa" / "BOB-109"

SECTION_START = "## Measured baselines"
SECTION_END = "## Evidence contract"

# A figure may appear in the doc without appearing in an artifact ONLY
# for these audited reasons. Every entry names why. The test asserts
# each entry is STILL PRESENT in the doc — a stale allowlist would
# silently widen the exemption over time.
ALLOWED_UNBACKED: dict[str, str] = {
    # Explicitly retracted in the doc's own retraction paragraph.
    "66.1": "retracted figure, named as withdrawn",
    "232.8": "retracted figure, named as withdrawn",
    "955.9": "retracted figure, named as withdrawn",
    "3308.1": "retracted figure, named as withdrawn",
    "1.882": "retracted span exponent, named as withdrawn",
    "2.1359": "the gate-violating stale specimen, named as such",
    # Source constant, not a measurement.
    "2.10": "MAX_GROWTH_EXPONENT, a constant in the test source",
    # Labelled in the doc as context from a quiet-host run whose
    # artifact no longer exists, explicitly NOT offered as evidence.
    "3.65": "quiet-host context, doc says explicitly not evidence",
    "6.61": "quiet-host context, doc says explicitly not evidence",
    "11.99": "quiet-host context, doc says explicitly not evidence",
}

# Anti-vacuity floor, counted over LIVE (non-allowlisted) figures only.
# It used to count ALL figures against a floor of 12 while ten
# allowlisted figures sat in the section — an effective floor of TWO, so
# a doc stripped of every live table still passed. Today the section
# carries ~16 live figures.
MIN_LIVE_FIGURES = 10


def _load_artifacts() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(EVIDENCE_DIR.glob("*.json"))}


def _numeric_values(artifacts: dict[str, str]) -> set[str]:
    """Every NUMBER in every artifact, as the string Python renders it.

    Values, never raw text: a substring test over the JSON blob accepts
    any prefix of a longer number, which is exactly a rounded or
    truncated table cell.
    """
    out: set[str] = set()

    def walk(obj: object) -> None:
        if isinstance(obj, bool):
            return  # bools are ints in Python; they are not figures
        if isinstance(obj, (int, float)):
            out.add(str(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for text in artifacts.values():
        walk(json.loads(text))
    return out


def _doc_figures(section: str) -> set[str]:
    r"""Decimal figures quoted in the section, excluding §-anchor tokens.

    ``§11.4.201(8)`` must not yield the "figure" 11.4. Anchors are
    stripped first, then the lookarounds refuse any decimal that is part
    of a longer dotted token. This MUST stay paired with value-matching:
    under substring-matching 11.4 was silently "backed" by prose, so
    removing one without the other flips the checker red on a good doc.

    The trailing lookahead is ``(?!\.?\d)`` — refuse a dot only when a
    DIGIT follows it — not ``(?![\d.])``, which refused ANY following
    dot including a sentence period. A reviewer's twelfth mutation used
    exactly that: ``"the top-rung admission p50 was 99.87."`` was
    INVISIBLE to the scan and passed, while the control
    ``"...was 99.87 ms."`` correctly failed, proving the period rather
    than any backing was the escape. Backtracking could not rescue it
    (``99.8`` fails the digit lookahead, ``9.87`` fails the lookbehind),
    so the figure was simply never extracted — a gap against this
    module's own claim to check EVERY decimal figure in the section.
    Narrow in practice (table cells are never sentence-final) but real,
    and one character class closes it.
    """
    stripped = re.sub(r"§\s*\d+(?:\.\d+)*", " ", section)
    return set(re.findall(r"(?<![\d.])\d+\.\d+(?!\.?\d)", stripped))


def _section() -> str:
    text = DOC.read_text()
    assert SECTION_START in text, (
        f"doc section {SECTION_START!r} not found in {DOC} — the checker "
        f"cannot verify a section that does not exist (renamed? removed?)"
    )
    assert SECTION_END in text, f"doc section {SECTION_END!r} not found in {DOC}"
    start = text.index(SECTION_START)
    end = text.index(SECTION_END)
    assert end > start, "doc sections are out of order"
    return text[start:end]


def test_evidence_dir_is_populated():
    """Anti-vacuity: no artifacts means nothing to agree WITH."""
    artifacts = _load_artifacts()
    assert artifacts, (
        f"no evidence artifacts under {EVIDENCE_DIR} — a doc-vs-evidence "
        f"check against an empty corpus would pass vacuously"
    )


def test_every_quoted_figure_is_backed_by_an_artifact():
    """Every decimal in the measured-baselines section exists in some artifact."""
    section = _section()
    artifacts = _load_artifacts()
    assert artifacts, "no artifacts to check against"

    values = _numeric_values(artifacts)
    figures = _doc_figures(section)
    live = sorted(f for f in figures if f not in ALLOWED_UNBACKED)

    assert len(live) >= MIN_LIVE_FIGURES, (
        f"only {len(live)} LIVE (non-allowlisted) decimal figures found in "
        f"the measured-baselines section (floor {MIN_LIVE_FIGURES}); "
        f"{len(figures)} figures total. The section was likely renamed, "
        f"emptied, or its tables stripped — refusing to report agreement on "
        f"a near-empty sample."
    )

    unbacked = sorted(f for f in live if f not in values)
    assert not unbacked, (
        f"doc quotes {len(unbacked)} figure(s) that equal NO numeric value "
        f"in any committed artifact under {EVIDENCE_DIR}: {unbacked}. A "
        f"rounded or truncated table cell lands here. Either re-transcribe "
        f"the doc from the artifacts, or — if a figure is deliberately "
        f"historical — add it to ALLOWED_UNBACKED with the reason."
    )


def test_allowlist_has_no_stale_entries():
    """A retired exemption must be removed, not left widening the check."""
    figures = _doc_figures(_section())
    stale = sorted(f for f in ALLOWED_UNBACKED if f not in figures)
    assert not stale, (
        f"ALLOWED_UNBACKED lists {len(stale)} figure(s) no longer present in "
        f"the doc: {stale}. Remove them — a stale allowlist silently exempts "
        f"figures nobody is reading any more."
    )


def test_doc_cites_the_artifacts_run_id():
    """The doc must name the run its numbers came from."""
    artifacts = _load_artifacts()
    assert artifacts, "no artifacts to check against"
    run_ids = {json.loads(t).get("run_id") for t in artifacts.values()}
    assert None not in run_ids, "an artifact carries no run_id"
    assert len(run_ids) == 1, (
        f"artifacts come from {len(run_ids)} different runs {sorted(run_ids)} — "
        f"the corpus is mixed, so no single run_id can be cited honestly"
    )
    run_id = run_ids.pop()
    assert run_id in DOC.read_text(), (
        f"doc does not cite the artifacts' run_id {run_id!r}; without it a "
        f"reader cannot tell which run the tables were transcribed from"
    )


def test_every_artifact_declares_purpose_and_verdict():
    """A committed artifact must say what it is and how it came out."""
    problems: list[str] = []
    for name, text in _load_artifacts().items():
        obj = json.loads(text)
        if obj.get("purpose") != "baseline":
            problems.append(f"{name}: purpose={obj.get('purpose')!r} (expected 'baseline')")
        if obj.get("verdict") not in {"PASS", "FAIL"}:
            problems.append(f"{name}: verdict={obj.get('verdict')!r}")
    assert not problems, (
        "committed artifacts must declare purpose=baseline and a PASS/FAIL "
        f"verdict: {problems}"
    )


if __name__ == "__main__":  # pragma: no cover - convenience runner
    raise SystemExit(pytest.main([__file__, "-v"]))
