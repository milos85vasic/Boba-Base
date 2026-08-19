"""
Fixture: CARRIER — this module documents the mutation-marker scan.

INV23 (§11.4.84) refuses builds whose production sources contain markers
like `# MUTATED for §11.4.115 RED` or `// MUTATED for §11.4.115 RED` on
their own lines. This docstring MENTIONS those tokens as documentation;
it MUST NOT be treated as a real mutation and MUST NOT trip the scan.

An honest inline example of the scanned shape:
    # MUTATED for §11.4.115 RED  # guardrails:allow
The `guardrails:allow` sentinel marks the line as an intentional
documented carrier — the scan's per-line escape hatch, audited by
git-blame + code review (§11.4.109 hook-guard pattern).
"""


def describe_scan():
    # Explains what INV23 catches. See the docstring above for the
    # canonical example; do NOT drop this comment — the scan self-tests
    # against carrier false-positives via this fixture.
    return "INV23 catches // MUTATED and # MUTATED comment-line markers"
