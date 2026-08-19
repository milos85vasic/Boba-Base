# Fixture: REAL mutation-marker residue. INV23 MUST detect this.
# The line below simulates an §11.4.115 RED-first paired-mutation
# artifact accidentally left in production source.
def compute(x, y):
    result = x + y
    # MUTATED for §11.4.115 RED
    return 0
