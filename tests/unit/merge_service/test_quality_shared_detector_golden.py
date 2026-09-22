"""Golden-master characterization of the two quality detectors (§11.4.243).

Two detectors existed independently and BOTH had to be edited for one fix:

* ``MetadataEnricher.detect_quality`` (``merge_service/enricher.py``) emits
  DISPLAY labels — ``4K`` / ``1080p`` / ``720p`` / ``SD`` / ``BluRay`` /
  ``WEB-DL`` / ``HDTV`` / ``DVD`` / ``None``.
* ``_detect_result_metadata`` (``merge_service/search.py``) emits INTERNAL
  codes — ``uhd_4k`` / ``full_hd`` / ``hd`` / ``sd`` / ``None`` — and owns a
  SIZE-BASED fallback the enricher has never had.

The ``\\bsd\\b`` word-boundary fix was applied to the enricher only; the search
copy kept a bare ``sd`` substring and mislabelled ``Sdorica.Anime.2019`` and
``Wasdd.Movie`` as standard-definition in live search results for a full
review round. That is the §11.4.251 debt this file pins before it is paid.

THIS FILE IS A GOLDEN MASTER, NOT A SPEC. Every expectation below was MEASURED
against the pre-refactor implementations, not derived from what the detectors
*ought* to do. It is DESCRIPTIVE (§11.4.243): its job is to make any behaviour
change during the extraction visible, including a change that would be an
improvement. Changing a value here without a stated, evidenced reason defeats
the entire point of the file.

Anti-bluff: the corpus deliberately includes the five false-positive strings
the ``sd`` fix targets, every branch BOTH detectors carry, the branches only
the search copy carries (``bluray``/``web-dl``/``hdtv``/``dvd``), and the
size-fallback boundary values — so a regression at any one of them fails here.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_MS_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src", "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _load(mod_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(_MS_PATH, file_name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_enricher_mod = _load("merge_service.enricher", "enricher.py")
_search_mod = _load("merge_service.search", "search.py")

detect_display_quality = _enricher_mod.MetadataEnricher().detect_quality
detect_result_metadata = _search_mod._detect_result_metadata


# ---------------------------------------------------------------------------
# The canonical DISPLAY-label -> INTERNAL-code map, copied verbatim from the
# two consumers that already performed this translation before the extraction
# (``api/routes.py::_detect_quality`` and
# ``merge_service/deduplicator.py::_fallback_quality``). It is reproduced here
# as DATA so the A/B equivalence check below is independent of whichever
# module currently owns the mapping.
# ---------------------------------------------------------------------------
_DISPLAY_TO_CODE = {
    "4K": "uhd_4k",
    "1080p": "full_hd",
    "720p": "hd",
    "SD": "sd",
    "BluRay": "full_hd",
    "BDRip": "full_hd",
    "BDRemux": "uhd_4k",
    "WEB-DL": "hd",
    "WEBRip": "hd",
    "HDRip": "hd",
    "HDTV": "hd",
    "DVD": "sd",
    "DVDRip": "sd",
}


# ---------------------------------------------------------------------------
# GOLDEN BASELINE — (name, size, display_label, internal_code)
#
# ``size`` is consumed ONLY by the search detector's fallback; the enricher
# never sees it. Rows are grouped by the branch they exercise.
# ---------------------------------------------------------------------------
_GOLDEN: list[tuple[str, str | None, str | None, str | None]] = [
    # --- resolution ladder: shared by both detectors -----------------------
    ("Movie.2023.2160p.BluRay", "5 GB", "4K", "uhd_4k"),
    ("Movie 4K Remux", "5 GB", "4K", "uhd_4k"),
    ("Movie UHD Bluray", "5 GB", "4K", "uhd_4k"),
    ("Movie.2023.1080p.WEB-DL", "5 GB", "1080p", "full_hd"),
    ("Movie FullHD", "5 GB", "1080p", "full_hd"),
    ("Movie FHD x264", "5 GB", "1080p", "full_hd"),
    ("Movie.720p.HDTV", "5 GB", "720p", "hd"),
    ("Movie HDRip XviD", "5 GB", "720p", "hd"),
    ("Movie.480p.XviD", "5 GB", "SD", "sd"),
    # ``sdrip`` / ``sdtv`` are TRUE positives the word-boundary must KEEP.
    ("Movie sdrip", "5 GB", "SD", "sd"),
    ("Movie SDTV cap", "5 GB", "SD", "sd"),
    ("Cam.Release.CAMRIP.2024", "5 GB", "SD", "sd"),
    # --- source ladder: the search detector collapses, the enricher does not
    ("Movie BluRay x264", "5 GB", "BluRay", "full_hd"),
    ("Movie BDRip", "5 GB", "BluRay", "full_hd"),
    ("Movie BD-Remux DV", "5 GB", "BluRay", "full_hd"),
    ("Movie blu-ray", "5 GB", "BluRay", "full_hd"),
    ("Movie web-dl DDP", "5 GB", "WEB-DL", "hd"),
    ("Movie WEBRip", "5 GB", "WEB-DL", "hd"),
    ("Movie WEB.DL", "5 GB", "WEB-DL", "hd"),
    ("Movie WEBDL", "5 GB", "WEB-DL", "hd"),
    ("Show S01E01 HDTV", "5 GB", "HDTV", "hd"),
    ("Movie DVD 1999", "5 GB", "DVD", "sd"),
    ("Movie DVDRip", "5 GB", "DVD", "sd"),
    # --- resolution OUTRANKS source when a name carries both --------------
    ("Movie 720p 1080p 2160p mixed BluRay WEB-DL HDTV DVD", "5 GB", "4K", "uhd_4k"),
    # --- the FALSE POSITIVES the `\bsd\b` fix targets ----------------------
    # Neither detector may read a quality token out of these. The search
    # detector still returns a code here because 5 GB lands in its SIZE
    # fallback — that is the fallback firing, NOT an ``sd`` match. The
    # zero-size rows below are the control that separates the two causes.
    ("Sdorica.Anime.2019", "5 GB", None, "hd"),
    ("Wasdd.Movie", "5 GB", None, "hd"),
    ("http://t/x?sdid=99", "5 GB", None, "hd"),
    ("/mnt/sdcard/f", "5 GB", None, "hd"),
    ("file.xsd", "5 GB", None, "hd"),
    # Same five strings with a size below every fallback threshold: proves
    # the NAME ladder itself matches nothing. If a bare-``sd`` regression is
    # ever reintroduced, these five rows flip to "sd" and fail.
    ("Sdorica.Anime.2019", "0 B", None, None),
    ("Wasdd.Movie", "0 B", None, None),
    ("http://t/x?sdid=99", "0 B", None, None),
    ("/mnt/sdcard/f", "0 B", None, None),
    ("file.xsd", "0 B", None, None),
    # --- size fallback: search detector only, enricher always None ---------
    ("Plain Release Name", "50 GB", None, "uhd_4k"),
    ("Plain Release Name", "10 GB", None, "full_hd"),
    ("Plain Release Name", "3 GB", None, "hd"),
    ("Plain Release Name", "400 MB", None, "sd"),
    ("Plain Release Name", "10 MB", None, None),
    ("Plain Release Name", "0 B", None, None),
    ("Plain Release Name", "2 TB", None, "uhd_4k"),
    # exact threshold boundaries, as raw byte strings
    ("Plain Release Name", str(40 * 1024**3), None, "uhd_4k"),
    ("Plain Release Name", str(8 * 1024**3), None, "full_hd"),
    ("Plain Release Name", str(2 * 1024**3), None, "hd"),
    ("Plain Release Name", str(300 * 1024**2), None, "sd"),
    # --- unparseable / degenerate inputs -----------------------------------
    ("Plain Release Name", "abc", None, None),
    ("Plain Release Name", None, None, None),
    ("", "", None, None),
]


@pytest.mark.parametrize(("name", "size", "expected_display", "expected_code"), _GOLDEN)
def test_golden_display_label(name, size, expected_display, expected_code):
    """The enricher's DISPLAY vocabulary is unchanged for every corpus row."""
    assert detect_display_quality(name) == expected_display, (
        f"display label drifted for {name!r}"
    )


@pytest.mark.parametrize(("name", "size", "expected_display", "expected_code"), _GOLDEN)
def test_golden_internal_code(name, size, expected_display, expected_code):
    """The search detector's INTERNAL vocabulary is unchanged for every row."""
    _content_type, code = detect_result_metadata(name, size)
    assert code == expected_code, f"internal code drifted for {name!r} @ size={size!r}"


@pytest.mark.parametrize(("name", "size", "expected_display", "expected_code"), _GOLDEN)
def test_detectors_agree_on_the_name_ladder(name, size, expected_display, expected_code):
    """A and B agree once the enricher's finer labels are mapped to codes.

    Evaluated with size ``"0 B"`` so the search detector's size fallback --
    which the enricher has no counterpart for -- cannot mask a genuine
    name-ladder disagreement. Measured 2026-09-22 across this corpus: ZERO
    disagreements. This is the precondition that makes collapsing the two
    detectors onto one shared implementation safe rather than a silent
    behaviour change.
    """
    display = detect_display_quality(name)
    mapped = _DISPLAY_TO_CODE.get(display) if display else None
    _content_type, code = detect_result_metadata(name, "0 B")
    assert mapped == code, (
        f"detectors disagree for {name!r}: enricher={display!r} -> {mapped!r} "
        f"but search={code!r}"
    )


def test_agreement_check_is_not_blind():
    """Control needle (§11.4.201(7)(b)) for the agreement assertion above.

    A zero-disagreement result is only evidence if the comparison can see a
    disagreement at all. This feeds the comparison a name the search detector
    reads as ``sd`` while pretending the enricher read nothing, and requires
    the mismatch to be detected. Without this, a comparison that silently
    compared ``None`` to ``None`` for every row would also report zero.
    """
    _content_type, code = detect_result_metadata("Movie 480p", "0 B")
    assert code == "sd", "needle precondition failed: search detector no longer reads 480p"
    assert _DISPLAY_TO_CODE.get(None) != code, "comparison is blind — it cannot see a mismatch"
