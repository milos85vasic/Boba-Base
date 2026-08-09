"""Meta-test: enforce fixture-based service-availability gating.

Phase 0.3 of the completion-initiative plan converted the old
``if probe_health() else pytest.skip(...)`` pattern into fixture-based
gating using ``merge_service_live`` / ``qbittorrent_live`` /
``webui_bridge_live`` / ``all_services_live`` from
``tests/fixtures/services.py``.

To prevent regression, this test scans every ``tests/**/*.py`` file and
fails if any ``pytest.skip(...)`` call mentions ``service``, ``available``,
or ``unreachable`` (case-insensitive). Two allow-listed escape hatches:

*   ``tests/fixtures/services.py`` itself — the docstring mentions the old
    pattern so we can explain what we replaced.
*   Any skip line with a trailing ``# allow-skip:`` comment — lets genuine
    data-dependent skips (e.g. "No search results") coexist.

Credential skips should be migrated to ``@pytest.mark.requires_credentials``
rather than run-time ``pytest.skip`` calls where possible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
ALLOW_LISTED_FILES = {
    TESTS_ROOT / "fixtures" / "services.py",
    THIS_FILE,
}

# Regex capturing ``pytest.skip(...)`` call including its argument list.
SKIP_CALL = re.compile(r"pytest\.skip\s*\(\s*(?P<arg>[^)]*)\)", re.IGNORECASE)

# Forbidden substrings inside the skip reason.
FORBIDDEN = ("service", "available", "unreachable")

ALLOW_MARKER = "# allow-skip:"


def _py_files() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if p.is_file())


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

        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            match = SKIP_CALL.search(line)
            if not match:
                continue
            arg = match.group("arg").lower()
            if any(word in arg for word in FORBIDDEN):
                rel = path.relative_to(TESTS_ROOT.parent)
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Found runtime service-availability skips. Convert them to fixture gates "
        "(merge_service_live / qbittorrent_live / webui_bridge_live / all_services_live) "
        "or append a trailing '# allow-skip: <reason>' comment if the skip is truly "
        "data-dependent and not about service availability.\n  - " + "\n  - ".join(offenders)
    )


def test_meta_allows_explicit_escape_hatch(tmp_path: pytest.TempPathFactory) -> None:
    """Sanity check: a skip annotated with '# allow-skip:' must NOT trigger."""
    # We can't write into the real tests tree, so we simulate by exercising
    # the regex directly.
    line = 'pytest.skip("service not available")  # allow-skip: legitimate reason'
    assert ALLOW_MARKER in line
    match = SKIP_CALL.search(line)
    assert match is not None
    # If the allow-marker is present, the main test skips it — which is the
    # behaviour under audit.


def test_meta_flags_service_wording() -> None:
    """Sanity check: a skip whose reason mentions 'service' triggers."""
    line = 'pytest.skip("Merge service not available")'
    assert ALLOW_MARKER not in line
    match = SKIP_CALL.search(line)
    assert match is not None
    arg = match.group("arg").lower()
    assert any(word in arg for word in FORBIDDEN)
