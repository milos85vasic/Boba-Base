package logging

import (
	"bytes"
	"errors"
	"strings"
	"testing"
)

func TestRedactorReplacesSecrets(t *testing.T) {
	var buf bytes.Buffer
	r := NewRedactor(&buf)
	r.AddSecret("supersecret123")
	r.Write([]byte("user logged in with password=supersecret123 ok"))
	if strings.Contains(buf.String(), "supersecret123") {
		t.Fatalf("secret leaked: %s", buf.String())
	}
	if !strings.Contains(buf.String(), "***") {
		t.Fatalf("no redaction marker: %s", buf.String())
	}
}

func TestRedactorMultipleSecrets(t *testing.T) {
	var buf bytes.Buffer
	r := NewRedactor(&buf)
	r.AddSecret("aaa")
	r.AddSecret("bbb")
	r.Write([]byte("aaa bbb ccc"))
	if strings.Contains(buf.String(), "aaa") || strings.Contains(buf.String(), "bbb") {
		t.Fatalf("secret leaked: %s", buf.String())
	}
}

// TestRedactorRemoveSecretStopsMasking covers RemoveSecret's found-branch.
// After a registered secret is removed, the next Write MUST emit it
// verbatim again. RED-on-regression: if RemoveSecret no-ops (e.g. the
// slice-splice is dropped), the post-remove Write would still mask
// "rotateme" and this assertion fails.
func TestRedactorRemoveSecretStopsMasking(t *testing.T) {
	var buf bytes.Buffer
	r := NewRedactor(&buf)
	r.AddSecret("keepme")
	r.AddSecret("rotateme")

	r.Write([]byte("keepme rotateme"))
	if strings.Contains(buf.String(), "rotateme") || strings.Contains(buf.String(), "keepme") {
		t.Fatalf("pre-remove leak: %s", buf.String())
	}

	r.RemoveSecret("rotateme")
	buf.Reset()
	r.Write([]byte("keepme rotateme"))
	got := buf.String()
	if !strings.Contains(got, "rotateme") {
		t.Fatalf("removed secret still masked (RemoveSecret did not unregister): %q", got)
	}
	if strings.Contains(got, "keepme") {
		t.Fatalf("RemoveSecret wrongly unregistered an unrelated secret: %q", got)
	}
}

// TestRedactorRemoveSecretUnknownAndEmpty covers the not-found + empty
// branches of RemoveSecret (both must be no-ops that preserve the list).
// RED-on-regression: if RemoveSecret("") spliced index 0, "real" would leak.
func TestRedactorRemoveSecretUnknownAndEmpty(t *testing.T) {
	var buf bytes.Buffer
	r := NewRedactor(&buf)
	r.AddSecret("real")

	r.RemoveSecret("")            // empty: no-op
	r.RemoveSecret("never-added") // unknown: no-op

	r.Write([]byte("real value"))
	if strings.Contains(buf.String(), "real ") {
		t.Fatalf("no-op RemoveSecret corrupted the secret list, secret leaked: %q", buf.String())
	}
	if !strings.Contains(buf.String(), "***") {
		t.Fatalf("expected redaction still active: %q", buf.String())
	}
}

// TestRedactorAddSecretEmptyIgnored covers the empty-needle guard in
// AddSecret. RED-on-regression: an empty needle in bytes.ReplaceAll
// inserts the mask between every byte; without the guard the output is
// peppered with *** and the equality check fails.
func TestRedactorAddSecretEmptyIgnored(t *testing.T) {
	var buf bytes.Buffer
	r := NewRedactor(&buf)
	r.AddSecret("") // must be ignored
	in := "plain text no secrets"
	r.Write([]byte(in))
	if buf.String() != in {
		t.Fatalf("empty secret poisoned the redactor: %q", buf.String())
	}
}

// errWriter forces dest.Write to fail so we exercise Write's error path.
type errWriter struct{ err error }

func (e errWriter) Write(p []byte) (int, error) { return 0, e.err }

// TestRedactorWriteErrorReturnsFullLen verifies the io.Writer contract:
// on a downstream error Write still returns len(p) so log libraries do
// not re-emit (and re-leak) the same bytes. RED-on-regression: returning
// the dest's n (0) breaks the invariant and this assertion fails.
func TestRedactorWriteErrorReturnsFullLen(t *testing.T) {
	wantErr := errors.New("sink down")
	r := NewRedactor(errWriter{err: wantErr})
	r.AddSecret("x")
	in := []byte("xyz")
	n, err := r.Write(in)
	if n != len(in) {
		t.Fatalf("Write n=%d, want %d (contract: always len(p))", n, len(in))
	}
	if !errors.Is(err, wantErr) {
		t.Fatalf("Write err=%v, want %v propagated", err, wantErr)
	}
}
