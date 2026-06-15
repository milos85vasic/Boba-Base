package api

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
)

// §11.4.135 regression guard for S4: ThemeStore.load() silently ignored the
// error from json.Unmarshal, so a corrupt/partial theme file overwrote the
// constructor's sensible default with a zero-value ThemeState (PaletteID="",
// Mode=""). The end user would then get a broken/blank theme served by
// GetThemeHandler. RED on the pre-fix code (state becomes zero-value); GREEN
// after load() checks the error and preserves the default.
func TestThemeStore_CorruptFile_KeepsDefault_S4(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "theme.json")
	// Partially-decodable corrupt JSON: json.Unmarshal sets palette_id to ""
	// (overwriting the "default" the constructor seeded) and THEN errors on the
	// number-into-string mode field. Pre-fix code ignored the error, so the
	// served state had a blank palette — a broken theme for the end user.
	if err := os.WriteFile(file, []byte(`{"palette_id":"","mode":123}`), 0o600); err != nil {
		t.Fatalf("setup write failed: %v", err)
	}

	store := NewThemeStore(file)
	got := store.Get()

	// User-observable contract: the served theme MUST remain a valid default,
	// never the zero-value that corrupt data would have produced.
	assert.NotEmpty(t, got.PaletteID, "corrupt file must not blank the palette")
	assert.NotEmpty(t, got.Mode, "corrupt file must not blank the mode")
	assert.Equal(t, "default", got.PaletteID)
	assert.Equal(t, "dark", got.Mode)
}

// Valid file must still load normally (guards against an over-broad fix that
// rejects all on-disk state).
func TestThemeStore_ValidFile_Loads_S4(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "theme.json")
	if err := os.WriteFile(file, []byte(`{"palette_id":"ocean","mode":"light"}`), 0o600); err != nil {
		t.Fatalf("setup write failed: %v", err)
	}

	store := NewThemeStore(file)
	got := store.Get()

	assert.Equal(t, "ocean", got.PaletteID)
	assert.Equal(t, "light", got.Mode)
}
