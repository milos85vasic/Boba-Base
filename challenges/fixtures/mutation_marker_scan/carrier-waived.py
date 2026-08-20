# Fixture: CARRIER — an own-line documentation mention, properly waived.
# The sentinel carries a REASON and sits on a comment-only line, so the
# §11.4.224(E) fence is satisfied. The gate reports it as an AUDITED
# waiver (printed + counted), never silently.
#
# MUTATED for §11.4.115 RED  # guardrails:allow documents the exact residue shape INV23 hunts
def documented():
    return "see the waived example above"
