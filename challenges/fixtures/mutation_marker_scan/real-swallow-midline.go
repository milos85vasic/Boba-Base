// Fixture: REAL residue — short-circuit-swallow NOT at statement start.
// The previous line-anchored pattern only saw `if fals`+`e &&` when it
// began the line; a swallow reached through an earlier operand was invisible.
package fixture

func Drop(err error) bool {
	if err == nil || false && err != nil {
		return true
	}
	return false
}
