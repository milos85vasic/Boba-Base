package main

import (
	"path/filepath"
	"strings"
	"testing"

	"digital.vasic.containers/pkg/remote"
)

// TestParseDeployHosts_Nezha is the RED-first guard for the `boba-ctl deploy`
// hosts.yaml parser (§11.4.115 polarity: this test fails against a no-op /
// absent parser and passes only when parseDeployHosts + findDeployHost read
// the real deploy/hosts.yaml correctly). It asserts the nezha block's
// load-bearing fields (the address/user/remote_path the SSH-driven boot uses).
func TestParseDeployHosts_Nezha(t *testing.T) {
	// deploy/hosts.yaml lives at the project root, two levels up from cmd/boba-ctl.
	hostsPath := filepath.Join("..", "..", deployHostsFile)

	cfg, err := parseDeployHosts(hostsPath)
	if err != nil {
		t.Fatalf("parseDeployHosts(%s): %v", hostsPath, err)
	}
	if cfg.SchemaVersion != 1 {
		t.Errorf("schema_version = %d, want 1", cfg.SchemaVersion)
	}

	nezha, err := findDeployHost(cfg, "nezha")
	if err != nil {
		t.Fatalf("findDeployHost(nezha): %v", err)
	}

	checks := []struct {
		field, got, want string
	}{
		{"address", nezha.Address, "nezha.local"},
		{"user", nezha.User, "milosvasic"},
		{"remote_path", nezha.RemotePath, "/home/milosvasic/boba"},
		{"auth", nezha.Auth, "key"},
		{"runtime", nezha.Runtime, "podman"},
		{"compose_file", nezha.ComposeFile, "docker-compose.yml"},
	}
	for _, c := range checks {
		if c.got != c.want {
			t.Errorf("nezha.%s = %q, want %q", c.field, c.got, c.want)
		}
	}
	if nezha.Port != 22 {
		t.Errorf("nezha.Port = %d, want 22", nezha.Port)
	}
}

// TestFindDeployHost_NotFound asserts a missing host yields an error naming the
// available hosts (no silent empty return that would later fail obscurely).
func TestFindDeployHost_NotFound(t *testing.T) {
	cfg := &deployHostsConfig{Hosts: []deployHost{{Name: "nezha"}}}
	if _, err := findDeployHost(cfg, "ghost"); err == nil {
		t.Fatal("findDeployHost(ghost) returned nil error, want not-found error")
	}
}

// TestDeployHost_ToRemoteHost asserts the deployHost → remote.RemoteHost
// conversion (§11.4.76) maps the "key" auth shorthand onto the submodule's
// remote.AuthSSHKey const and carries the SSH-driving fields.
func TestDeployHost_ToRemoteHost(t *testing.T) {
	dh := deployHost{
		Name: "nezha", Address: "nezha.local", Port: 22, User: "milosvasic",
		Auth: "key", KeyPath: "/tmp/id_ed25519", Runtime: "podman",
	}
	rh, err := dh.toRemoteHost()
	if err != nil {
		t.Fatalf("toRemoteHost() unexpected error: %v", err)
	}
	if rh.Auth != remote.AuthSSHKey {
		t.Errorf("Auth = %q, want %q (remote.AuthSSHKey)", rh.Auth, remote.AuthSSHKey)
	}
	if rh.Name != "nezha" || rh.Address != "nezha.local" || rh.User != "milosvasic" {
		t.Errorf("identity fields not carried: %+v", rh)
	}
	if rh.SSHPort() != 22 {
		t.Errorf("SSHPort() = %d, want 22", rh.SSHPort())
	}
}

// TestDeployHost_ToRemoteHost_InvalidAuthRefuses is the host-level (caller)
// half of the BOB-215 fix: a deployHost whose "auth:" value is typo'd MUST
// propagate a refusal from toRemoteHost(), never silently produce a
// RemoteHost carrying a default credential mechanism the operator never
// chose.
func TestDeployHost_ToRemoteHost_InvalidAuthRefuses(t *testing.T) {
	dh := deployHost{Name: "nezha", Auth: "ssh-keyy"}
	rh, err := dh.toRemoteHost()
	if err == nil {
		t.Fatalf("toRemoteHost() with typo'd auth returned nil error, want refusal; got RemoteHost=%+v", rh)
	}
	if !strings.Contains(err.Error(), "nezha") {
		t.Errorf("toRemoteHost() error = %q, want it to name the host %q", err, "nezha")
	}
	if !strings.Contains(err.Error(), "ssh-keyy") {
		t.Errorf("toRemoteHost() error = %q, want it to name the bad value %q", err, "ssh-keyy")
	}
}

// TestAuthMethod_LegitimateValuesResolve is the golden-FALSE guard for the
// BOB-215 fix (§11.4.201(1) — a fix that closes the silent-default hole must
// never introduce a false refusal on real deploys): every value the
// deploy/hosts.yaml schema actually recognises (the full case set read out
// of authMethod()'s switch statement) MUST still resolve to its intended
// remote.AuthMethod with no error.
func TestAuthMethod_LegitimateValuesResolve(t *testing.T) {
	cases := map[string]remote.AuthMethod{
		"key":       remote.AuthSSHKey,
		"ssh_key":   remote.AuthSSHKey,
		"ssh-key":   remote.AuthSSHKey,
		"agent":     remote.AuthSSHAgent,
		"ssh_agent": remote.AuthSSHAgent,
		"ssh-agent": remote.AuthSSHAgent,
		"password":  remote.AuthPassword,
		// authMethod() lowercases + trims before matching (§11.4.6 explicit,
		// not guessed): mixed case and surrounding whitespace are legitimate
		// spellings of the same value and must not be refused either.
		"KEY":      remote.AuthSSHKey,
		" agent ":  remote.AuthSSHAgent,
		"Password": remote.AuthPassword,
	}
	for in, want := range cases {
		got, err := authMethod(in)
		if err != nil {
			t.Errorf("authMethod(%q) returned unexpected refusal: %v (false-refusal on a legitimate value would break real deploys — §11.4.201(1))", in, err)
			continue
		}
		if got != want {
			t.Errorf("authMethod(%q) = %q, want %q", in, got, want)
		}
	}
}

// TestAuthMethod_UnrecognisedValueRefuses is the BOB-215 fix's GREEN
// assertion (flipped from the pre-fix RED evidence captured against
// unfixed code, where authMethod("totally-not-a-real-auth-method") and
// authMethod("") both silently returned remote.AuthSSHKey, nil — see
// docs/Issues.md BOB-215). An unrecognised, typo'd, or empty "auth:" value
// MUST now refuse with an error naming BOTH the offending config key
// ("auth") and its declared (bad) value — never silently default to any
// auth method.
func TestAuthMethod_UnrecognisedValueRefuses(t *testing.T) {
	badValues := []string{
		"totally-not-a-real-auth-method",
		"",
		"ssh-keyy", // typo of "ssh-key"
		"pasword",  // typo of "password"
		"AGENT!!!",
	}
	for _, in := range badValues {
		got, err := authMethod(in)
		if err == nil {
			t.Errorf("authMethod(%q) = (%q, nil), want a refusal error (BOB-215: silent default is the bug)", in, got)
			continue
		}
		if got != "" {
			t.Errorf("authMethod(%q) returned non-empty AuthMethod %q alongside an error — a refusal must not also hand back a usable value", in, got)
		}
		if !strings.Contains(err.Error(), "auth") {
			t.Errorf("authMethod(%q) error = %q, want it to name the offending config key %q", in, err, "auth")
		}
		if !strings.Contains(err.Error(), in) && in != "" {
			t.Errorf("authMethod(%q) error = %q, want it to name the declared bad value %q", in, err, in)
		}
	}
}
