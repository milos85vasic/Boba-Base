"""Enforces the .trivyignore.yaml waiver-expiry policy.

Every accepted-risk vulnerability suppression in ``.trivyignore.yaml``
represents a live security risk the project has chosen not to fix. The
waiver policy documented in ``docs/SECURITY.md`` ("Waiver policy") and in
the header comment of ``.trivyignore`` requires every such entry to carry
an ``expires: YYYY-MM-DD`` field, and forbids that date from being in the
past — an expired waiver is a stale risk-acceptance decision that must be
re-reviewed, not silently ignored forever.

This is the ``tests/unit/test_scan_config.py`` referenced by
``.trivyignore`` and (as ``test_scan_waivers_have_expiry.py``, corrected
to this filename) by ``docs/SECURITY.md`` — RD2-38 / RD2-06
(``docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md``).
"""

import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
TRIVYIGNORE_YAML = ROOT / ".trivyignore.yaml"


def _load_ignores() -> list[dict]:
    data = yaml.safe_load(TRIVYIGNORE_YAML.read_text()) or {}
    ignores = data.get("ignores") or []
    assert isinstance(ignores, list), ".trivyignore.yaml 'ignores' must be a list"
    return ignores


class TestTrivyIgnoreWaiverExpiry:
    def test_every_ignore_entry_has_an_expiry_date(self):
        """Every waiver must declare when it is due for re-review."""
        missing = [entry.get("id", "<no id>") for entry in _load_ignores() if not entry.get("expires")]
        assert not missing, f".trivyignore.yaml entries missing 'expires: YYYY-MM-DD': {missing}"

    def test_every_ignore_entry_expiry_is_a_valid_iso_date(self):
        """A malformed date must fail loudly, not be silently un-enforced."""
        bad = []
        for entry in _load_ignores():
            raw = entry.get("expires")
            if raw is None:
                continue
            try:
                datetime.date.fromisoformat(str(raw))
            except ValueError:
                bad.append((entry.get("id", "<no id>"), raw))
        assert not bad, f".trivyignore.yaml entries with non-ISO 'expires' date (id, expires): {bad}"

    def test_no_ignore_entry_is_expired(self):
        """An expired waiver blocks — the risk-acceptance must be renewed or the entry dropped."""
        today = datetime.date.today()
        expired = []
        for entry in _load_ignores():
            raw = entry.get("expires")
            if raw is None:
                continue
            expiry = datetime.date.fromisoformat(str(raw))
            if expiry < today:
                expired.append((entry.get("id", "<no id>"), raw))
        assert not expired, f".trivyignore.yaml has expired waiver(s) (id, expires): {expired}"

    def test_every_ignore_entry_has_a_real_looking_cve_id(self):
        """Reject template placeholders (e.g. CVE-2025-XXXX-0001) — RD2-06.

        A real CVE id is ``CVE-<4-digit year>-<4+ digit sequence number>``.
        A literal ``X`` anywhere in the id is template boilerplate that was
        never filled in with a real vulnerability identifier.
        """
        import re

        cve_re = re.compile(r"^CVE-\d{4}-\d{4,}$")
        placeholders = [
            entry.get("id", "<no id>") for entry in _load_ignores() if not cve_re.match(str(entry.get("id", "")))
        ]
        assert not placeholders, f".trivyignore.yaml has non-real-looking CVE id(s): {placeholders}"
