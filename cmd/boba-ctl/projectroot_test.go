package main

import (
	"os"
	"path/filepath"
	"testing"
)

// TestFindRootWithComposeFile is the §11.4.135 regression guard for the
// hardcoded-capital-path bug: boba-ctl returned "/Volumes/T7/Projects/Boba"
// which does not exist on the case-sensitive T7 volume (real repo is lowercase
// "boba"), so compose chdir failed and the stack never started. The fix
// resolves the project root dynamically by locating docker-compose.yml.
func TestFindRootWithComposeFile(t *testing.T) {
	tmp := t.TempDir()
	root := filepath.Join(tmp, "boba")
	sub := filepath.Join(root, "cmd", "boba-ctl")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "docker-compose.yml"), []byte("services: {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	orig, _ := os.Getwd()
	defer os.Chdir(orig)
	if err := os.Chdir(sub); err != nil {
		t.Fatal(err)
	}

	got := findRootWithComposeFile()
	// EvalSymlinks because macOS /var -> /private/var.
	gotResolved, _ := filepath.EvalSymlinks(got)
	wantResolved, _ := filepath.EvalSymlinks(root)
	if gotResolved != wantResolved {
		t.Fatalf("findRootWithComposeFile() = %q, want %q", gotResolved, wantResolved)
	}
}

// TestProjectRootHonorsEnv verifies the PROJECT_ROOT override path.
func TestProjectRootHonorsEnv(t *testing.T) {
	t.Setenv("PROJECT_ROOT", "/some/explicit/path")
	if got := projectRoot(); got != "/some/explicit/path" {
		t.Fatalf("projectRoot() = %q, want /some/explicit/path", got)
	}
}

// TestProjectRootResolvesToExistingDir guards against any future regression to
// a hardcoded non-existent path: with PROJECT_ROOT unset, projectRoot() must
// return a directory that actually exists on disk.
func TestProjectRootResolvesToExistingDir(t *testing.T) {
	t.Setenv("PROJECT_ROOT", "")
	os.Unsetenv("PROJECT_ROOT")
	got := projectRoot()
	if fi, err := os.Stat(got); err != nil || !fi.IsDir() {
		t.Fatalf("projectRoot() = %q which is not an existing directory (err=%v)", got, err)
	}
}
