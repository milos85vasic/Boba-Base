"""The single release-quality detector (§11.4.251 duplicate-logic paydown).

WHY THIS MODULE EXISTS
----------------------
Until 2026-09-22 the same quality ladder was implemented TWICE, in two files,
with two output vocabularies:

* ``merge_service/enricher.py::MetadataEnricher.detect_quality`` — DISPLAY
  labels (``4K`` / ``1080p`` / ``720p`` / ``SD`` / ``BluRay`` / ``WEB-DL`` /
  ``HDTV`` / ``DVD``).
* ``merge_service/search.py::_detect_result_metadata`` — INTERNAL codes
  (``uhd_4k`` / ``full_hd`` / ``hd`` / ``sd``), plus a size-based fallback.

The duplication was not theoretical: the ``\\bsd\\b`` word-boundary fix was
applied to the enricher copy only. The search copy kept a bare ``sd``
substring and mislabelled ``Sdorica.Anime.2019``, ``Wasdd.Movie``, a
``?sdid=`` query parameter and a ``/sdcard/`` path as standard-definition in
the search results a user actually sees, for a full review round, until the
second copy was found and fixed in place.

Two copies mean a fix lands on one and the defect stays live on the other.
There is now ONE ladder — :func:`detect_quality_signal` — and each consumer
maps its result into its own vocabulary through a table below. A fix to the
ladder reaches every consumer by construction; it is no longer possible to
fix one and miss the other.

THE CANONICAL VOCABULARY IS THE FINER OF THE TWO
------------------------------------------------
:class:`QualitySignal` is deliberately modelled at the enricher's granularity,
not the search service's. The enricher distinguishes ``BluRay`` from
``1080p``; the search service collapses both to ``full_hd``. Collapsing is
lossy, so the shared signal keeps the distinction and each consumer discards
what it does not need. Modelling the canonical tier at the COARSER vocabulary
would have made the enricher's output unrecoverable — a silent narrowing of a
public output, which this refactor is explicitly forbidden from doing.

Equivalence of the two ladders was MEASURED, not assumed, before they were
collapsed: across the shared corpus in
``tests/unit/merge_service/test_quality_shared_detector_golden.py`` the
enricher's label mapped through :data:`SIGNAL_TO_INTERNAL_CODE`'s predecessor
equalled the search service's code on every row — ZERO disagreements, with a
control needle proving the comparison could see one (§11.4.201(7)(b)).

SCOPE (§11.4.6 — stated, not implied)
-------------------------------------
This module owns the NAME ladder only. The size-based fallback stays with
:mod:`merge_service.search`, because it is that consumer's own behaviour: the
enricher has never had one and must keep returning ``None`` for a name that
carries no quality token. Folding the fallback in here would have changed the
enricher's output for every untokenised name — a behaviour change disguised
as a refactor.
"""

from __future__ import annotations

import re
from enum import Enum

__all__ = [
    "SIGNAL_TO_DISPLAY_LABEL",
    "SIGNAL_TO_INTERNAL_CODE",
    "QualitySignal",
    "detect_quality_signal",
]


class QualitySignal(Enum):
    """Canonical quality signal read out of a release name.

    NOT a public output vocabulary. Consumers map it to their own via
    :data:`SIGNAL_TO_DISPLAY_LABEL` or :data:`SIGNAL_TO_INTERNAL_CODE`; the
    member names are internal and carry no wire or UI meaning.
    """

    UHD_4K = "uhd_4k"
    FULL_HD = "full_hd"
    HD_720 = "hd_720"
    SD = "sd"
    BLURAY = "bluray"
    WEB_DL = "web_dl"
    HDTV = "hdtv"
    DVD = "dvd"


# ``sd`` is WORD-BOUNDED. As a bare substring it matched any name merely
# containing those two letters — measured false positives: "Sdorica",
# "Wasdd", a "?sdid=" query parameter, a "/sdcard/" path. Every one was
# labelled standard-definition in results the user sees.
#
# ``sdrip`` / ``sdtv`` are kept EXPLICITLY: they ARE standard-definition and
# the bare-substring version caught them by accident. Word-bounding without
# re-admitting them would fix the false positive by breaking a true one — the
# both-factors trap (§11.4.194(1)) this exact pattern already fell into once.
#
# FORENSIC HISTORY, carried over from the two copies this pattern replaces so
# it is not lost with them (both lessons are about THIS one line):
#   * M-c (2026-09-01) — the ORIGINAL defect: ``sd`` matched as a bare
#     substring, so any name or URL containing those two letters anywhere
#     (``?sdid=``, ``/sdcard/``, ``xsd``) was tagged standard-definition. That
#     is an invented value (§11.4.6), reachable the moment tagging began
#     falling back to the download URL when no title was supplied.
#   * F6 — the FIRST FIX OVERCORRECTED: a plain ``\bsd\b`` removed the false
#     positives but also killed the legitimate ``sdrip`` / ``sdtv`` tokens,
#     i.e. only one side of the change had been verified. A pre-existing
#     RED-capable test (``test_enricher_resolve.py``) caught it exactly as
#     designed — it simply had not been run. Hence the explicit
#     ``(?:rip|tv)?`` alternation rather than a bare word boundary.
_SD_PATTERN = r"480p|\bsd(?:rip|tv)?\b|camrip"

# Ordered ladder: FIRST match wins, so resolution outranks source. Both
# original implementations had this precedence and the golden master pins it
# ("Movie 720p 1080p 2160p mixed BluRay WEB-DL HDTV DVD" -> UHD_4K).
_RESOLUTION_LADDER: tuple[tuple[re.Pattern[str], QualitySignal], ...] = (
    (re.compile(r"2160p|4k|uhd"), QualitySignal.UHD_4K),
    (re.compile(r"1080p|fullhd|fhd"), QualitySignal.FULL_HD),
    (re.compile(r"720p|hdrip"), QualitySignal.HD_720),
    (re.compile(_SD_PATTERN), QualitySignal.SD),
)

# Source ladder, consulted only when no resolution token matched. These are
# plain substring checks in BOTH original implementations — kept as substring
# checks so the golden master's ``bd-remux`` / ``web.dl`` / ``webdl`` rows
# keep matching exactly as before.
_SOURCE_LADDER: tuple[tuple[tuple[str, ...], QualitySignal], ...] = (
    (("bluray", "blu-ray", "bdrip", "bd-remux"), QualitySignal.BLURAY),
    (("web-dl", "webrip", "web.dl", "webdl"), QualitySignal.WEB_DL),
    (("hdtv",), QualitySignal.HDTV),
    (("dvd",), QualitySignal.DVD),
)


def detect_quality_signal(name: str | None) -> QualitySignal | None:
    """Read the quality signal from a release name, or ``None`` if absent.

    ``name`` is UNTRUSTED tracker-supplied text and may be ``None`` or empty;
    both yield ``None`` rather than raising.
    """
    lowered = name.lower() if name else ""

    for pattern, signal in _RESOLUTION_LADDER:
        if pattern.search(lowered):
            return signal

    for tokens, signal in _SOURCE_LADDER:
        if any(token in lowered for token in tokens):
            return signal

    return None


#: :mod:`merge_service.enricher`'s public DISPLAY vocabulary. UNCHANGED by the
#: extraction — every value here was emitted by ``detect_quality`` before it.
SIGNAL_TO_DISPLAY_LABEL: dict[QualitySignal, str] = {
    QualitySignal.UHD_4K: "4K",
    QualitySignal.FULL_HD: "1080p",
    QualitySignal.HD_720: "720p",
    QualitySignal.SD: "SD",
    QualitySignal.BLURAY: "BluRay",
    QualitySignal.WEB_DL: "WEB-DL",
    QualitySignal.HDTV: "HDTV",
    QualitySignal.DVD: "DVD",
}

#: :mod:`merge_service.search`'s public INTERNAL vocabulary. UNCHANGED by the
#: extraction. Note the deliberate collapse: BluRay joins FULL_HD, and
#: WEB-DL/HDTV join HD — exactly as the search ladder did inline, and exactly
#: as the display-label-to-code table in the downstream consumers already did.
SIGNAL_TO_INTERNAL_CODE: dict[QualitySignal, str] = {
    QualitySignal.UHD_4K: "uhd_4k",
    QualitySignal.FULL_HD: "full_hd",
    QualitySignal.HD_720: "hd",
    QualitySignal.SD: "sd",
    QualitySignal.BLURAY: "full_hd",
    QualitySignal.WEB_DL: "hd",
    QualitySignal.HDTV: "hd",
    QualitySignal.DVD: "sd",
}
