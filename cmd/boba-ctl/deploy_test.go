package main

import (
	"path/filepath"
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
	rh := dh.toRemoteHost()
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

// TestAuthMethod_Mapping covers the closed-set auth-string mapping including
// the default-to-key fallback for an unrecognised value (§11.4.6 — explicit,
// not guessed: documented as the safe SSH-key default).
func TestAuthMethod_Mapping(t *testing.T) {
	cases := map[string]remote.AuthMethod{
		"key":       remote.AuthSSHKey,
		"ssh_key":   remote.AuthSSHKey,
		"agent":     remote.AuthSSHAgent,
		"ssh_agent": remote.AuthSSHAgent,
		"password":  remote.AuthPassword,
		"":          remote.AuthSSHKey,
		"weird":     remote.AuthSSHKey,
	}
	for in, want := range cases {
		if got := authMethod(in); got != want {
			t.Errorf("authMethod(%q) = %q, want %q", in, got, want)
		}
	}
}
