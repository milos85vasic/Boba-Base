// Fixture: CARRIER — Go block comment + string literals holding markers.
package fixture

/*
This block comment documents the residue shapes INV23 refuses:

    // MUTATED for §11.4.115 RED
    // always pass
    if false && err != nil

Prose in a block comment is documentation, never residue.
*/

var MarkerExamples = []string{
	"// MUTATED for §11.4.115 RED",
	"# MUTATED for §11.4.115 RED",
	"// always pass",
	"if false && err != nil",
}
