# Fixture: CARRIER — mutation-marker text held inside string literals.
# A codebase legitimately holding the marker token as data (a scanner's
# own pattern registry, a test-fixture generator, a doc-generator that
# emits example markers) MUST NOT trip INV23 on its string-literal use.

MUTATION_TOKEN_EXAMPLES = [
    "# MUTATED for §11.4.115 RED",
    "// MUTATED for §11.4.115 RED",
    "# always pass",
    "// always pass",
]

SHORT_CIRCUIT_SWALLOW_EXAMPLE = "if false && err != nil // MUTATED"


def marker_help():
    return "The scanner refuses lines like: '# MUTATED for §11.4.115 RED'"
