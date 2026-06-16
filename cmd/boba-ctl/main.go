package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"digital.vasic.containers/pkg/compose"
	"digital.vasic.containers/pkg/logging"
	"digital.vasic.containers/pkg/remote"
	"digital.vasic.containers/pkg/runtime"
	"gopkg.in/yaml.v3"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: boba-ctl <command> [options]\n\n")
		fmt.Fprintf(os.Stderr, "Commands:\n")
		fmt.Fprintf(os.Stderr, "  up       Start all services\n")
		fmt.Fprintf(os.Stderr, "  down     Stop all services\n")
		fmt.Fprintf(os.Stderr, "  status   Show service status\n")
		fmt.Fprintf(os.Stderr, "  health   Check service health endpoints\n")
		fmt.Fprintf(os.Stderr, "  list     List services and profiles\n")
		fmt.Fprintf(os.Stderr, "  deploy   Deploy + boot the System on a remote host\n")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "up":
		cmdUp()
	case "down":
		cmdDown()
	case "status":
		cmdStatus()
	case "health":
		cmdHealth()
	case "list":
		cmdList()
	case "deploy":
		cmdDeploy()
	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", os.Args[1])
		os.Exit(1)
	}
}

func projectRoot() string {
	if root := os.Getenv("PROJECT_ROOT"); root != "" {
		return root
	}
	// Resolve dynamically — never hardcode an absolute, case-specific path
	// (§11.4.111 resolve-by-stable-name, §11.4.29 case-correct). A hardcoded
	// "/Volumes/T7/Projects/Boba" failed chdir on the case-sensitive T7 volume
	// because the real repo is lowercase "boba".
	if root := findRootWithComposeFile(); root != "" {
		return root
	}
	if exe, err := os.Executable(); err == nil {
		return filepath.Dir(exe)
	}
	return "."
}

// findRootWithComposeFile walks up from the working directory (then the
// executable's directory) looking for docker-compose.yml, returning the first
// directory that contains it. Returns "" when none is found.
func findRootWithComposeFile() string {
	var starts []string
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	for _, start := range starts {
		for dir := start; ; {
			if _, err := os.Stat(filepath.Join(dir, "docker-compose.yml")); err == nil {
				return dir
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}

func createOrchestrator() (*compose.DefaultOrchestrator, error) {
	return compose.NewDefaultOrchestrator(projectRoot(), logging.NewStdLogger("boba-ctl"))
}

func createProject() compose.ComposeProject {
	return compose.ComposeProject{
		Name: "boba",
		File: filepath.Join(projectRoot(), "docker-compose.yml"),
	}
}

func cmdUp() {
	fs := flag.NewFlagSet("up", flag.ExitOnError)
	profile := fs.String("profile", "", "compose profile to use")
	wait := fs.Bool("wait", false, "wait for services to become healthy")
	fs.Parse(os.Args[2:])

	orch, err := createOrchestrator()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	project := createProject()
	project.Profile = *profile

	opts := []compose.UpOption{compose.WithUpDetach(true)}
	if *wait {
		opts = append(opts, compose.WithWait(true))
	}

	ctx := context.Background()
	if err := orch.Up(ctx, project, opts...); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	rt, _ := runtime.AutoDetect(ctx)
	rtName := "unknown"
	if rt != nil {
		rtName = rt.Name()
	}

	fmt.Printf("Services started [runtime: %s]\n", rtName)
}

func cmdDown() {
	fs := flag.NewFlagSet("down", flag.ExitOnError)
	volumes := fs.Bool("volumes", false, "also remove named volumes")
	fs.Parse(os.Args[2:])

	orch, err := createOrchestrator()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	ctx := context.Background()
	project := createProject()

	var opts []compose.DownOption
	if *volumes {
		opts = append(opts, compose.WithDownRemoveVolumes(true))
	}

	if err := orch.Down(ctx, project, opts...); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Services stopped")
}

func cmdStatus() {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	fs.Parse(os.Args[2:])

	orch, err := createOrchestrator()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	ctx := context.Background()
	statuses, err := orch.Status(ctx, createProject())
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if len(statuses) == 0 {
		fmt.Println("No services found")
		return
	}

	fmt.Printf("%-25s %-12s %-14s %s\n", "NAME", "STATE", "HEALTH", "PORTS")
	fmt.Println(strings.Repeat("-", 85))
	for _, s := range statuses {
		health := s.Health
		if health == "" {
			health = "-"
		}
		ports := strings.Join(s.Ports, ", ")
		fmt.Printf("%-25s %-12s %-14s %s\n", s.Name, s.State, health, ports)
	}
}

// serviceStatusLite is the minimal projection of compose.ServiceStatus that the
// health-detail logic needs. Decoupling it keeps healthDetail unit-testable
// without a live runtime (the containers submodule provides ServiceStatus; the
// probing logic is owned here per §11.4.28 — the submodule's pkg/health probes
// published ports only and is read-only/decoupled, so the host-net fix lives in
// boba-ctl's own cmdHealth).
type serviceStatusLite struct {
	Name   string
	State  string
	Health string
	Ports  []string
}

// hostNetServicePorts maps each network_mode: host Boba service to the TCP port
// it actually listens on, derived from docker-compose.yml (the per-service
// healthcheck `curl localhost:PORT` lines + the PORT env vars are authoritative).
// host-net services publish NO host->container port mappings, so ServiceStatus.
// Ports is empty for them and the published-port probe loop never runs; without
// this map health would emit the misleading "no ports exposed" for a service
// that IS serving. The podman VM forwards host-net container ports to the host
// loopback, so probing 127.0.0.1:PORT from the macOS host is a real endpoint
// probe (same path that makes http://localhost:7186 etc. reachable per the
// project Port Map).
var hostNetServicePorts = map[string]string{
	"qbittorrent":          "7185",
	"jackett":              "9117",
	"qbittorrent-proxy-go": "7187",
	"download-proxy":       "7186",
	"boba-jackett":         "7189",
}

// healthDetail computes the (ok, detail) verdict for a single running service.
// Probe priority: (1) any published host->container port mappings (preserves
// the prior behaviour for non-host-net services); (2) failing that, the known
// host-net listening port from knownPorts (the §network_mode: host fix); (3)
// failing both, an HONEST "running (host-net, endpoint not probed)" — never the
// misleading "no ports exposed" (§11.4.6: report what is true, do not overclaim).
func healthDetail(ctx context.Context, dialer net.Dialer, s serviceStatusLite, knownPorts map[string]string) (bool, string) {
	allOK := true
	var details []string

	if s.Health != "" && s.Health != "healthy" && s.Health != "none" {
		allOK = false
		details = append(details, "compose-health: "+s.Health)
	}

	probed := false
	// authoritative=true: a published host->container port; unreachable means the
	// service is genuinely down → FAIL. authoritative=false: a host-net port probed
	// over the host loopback — on a remote-VM runtime (macOS podman) the host can
	// only reach host-net ports that happen to be tunnel-forwarded, so an
	// unreachable result does NOT confirm the service is down (could be the VM/
	// tunnel boundary). Reporting FAIL there would be a §11.4.1 false-FAIL, so we
	// record an honest "not a confirmed failure" detail WITHOUT failing the verdict.
	probe := func(hostPort string, authoritative bool) {
		if hostPort == "" {
			return
		}
		probed = true
		addr := "127.0.0.1:" + hostPort
		conn, dialErr := dialer.DialContext(ctx, "tcp", addr)
		if dialErr != nil {
			if authoritative {
				allOK = false
				details = append(details, fmt.Sprintf("%s: %v", addr, dialErr))
			} else {
				details = append(details, fmt.Sprintf("%s: not reachable from host (host-net via VM — not a confirmed failure)", addr))
			}
		} else {
			conn.Close()
			details = append(details, fmt.Sprintf("%s: reachable", addr))
		}
	}

	// (1) Published port mappings (non-host-net services) — failure is authoritative.
	for _, portStr := range s.Ports {
		probe(extractHostPort(portStr), true)
	}

	// (2) Known host-net listening port (host-net services publish nothing) —
	// failure is NOT authoritative over the host loopback (VM boundary).
	if !probed {
		if hostPort, ok := knownPorts[s.Name]; ok {
			probe(hostPort, false)
		}
	}

	detail := strings.Join(details, "; ")
	if detail == "" {
		// (3) Nothing probeable — honest, non-misleading detail. The service is
		// running; we simply have no endpoint to probe. NOT "no ports exposed",
		// which falsely implied a broken/missing service.
		detail = "running (host-net, endpoint not probed)"
	}
	return allOK, detail
}

func cmdHealth() {
	fs := flag.NewFlagSet("health", flag.ExitOnError)
	timeout := fs.Int("timeout", 5, "connection timeout in seconds")
	fs.Parse(os.Args[2:])

	orch, err := createOrchestrator()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	ctx := context.Background()
	project := createProject()
	statuses, err := orch.Status(ctx, project)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if len(statuses) == 0 {
		fmt.Println("No services running")
		return
	}

	dialer := net.Dialer{Timeout: time.Duration(*timeout) * time.Second}

	fmt.Printf("%-25s %-10s  %s\n", "SERVICE", "STATUS", "DETAIL")
	fmt.Println(strings.Repeat("-", 70))
	for _, s := range statuses {
		if s.State != "running" {
			fmt.Printf("%-25s %-10s  %s\n", s.Name, "STOPPED", "Not running")
			continue
		}

		ok, detail := healthDetail(ctx, dialer, serviceStatusLite{
			Name:   s.Name,
			State:  s.State,
			Health: s.Health,
			Ports:  s.Ports,
		}, hostNetServicePorts)

		statusLabel := "OK"
		if !ok {
			statusLabel = "FAIL"
		}
		fmt.Printf("%-25s %-10s  %s\n", s.Name, statusLabel, detail)
	}
}

func cmdList() {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	fs.Parse(os.Args[2:])

	composeFile := filepath.Join(projectRoot(), "docker-compose.yml")
	data, err := os.ReadFile(composeFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading compose file: %v\n", err)
		os.Exit(1)
	}

	var cfg struct {
		Services map[string]struct {
			Profiles  []string `yaml:"profiles"`
			DependsOn map[string]struct {
				Condition string `yaml:"condition"`
			} `yaml:"depends_on"`
		} `yaml:"services"`
	}

	if err := yaml.Unmarshal(data, &cfg); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing compose file: %v\n", err)
		os.Exit(1)
	}

	defaultSvcs := make([]string, 0)
	profileSvcs := make(map[string][]string)

	for name, svc := range cfg.Services {
		if len(svc.Profiles) == 0 {
			defaultSvcs = append(defaultSvcs, name)
		}
		for _, p := range svc.Profiles {
			profileSvcs[p] = append(profileSvcs[p], name)
		}
	}

	fmt.Println("Default services:")
	fmt.Println(strings.Repeat("-", 40))
	for _, s := range defaultSvcs {
		fmt.Printf("  %s\n", s)
	}

	fmt.Println("\nProfiles:")
	fmt.Println(strings.Repeat("-", 40))
	if len(profileSvcs) == 0 {
		fmt.Println("  (none)")
	} else {
		for name, svcs := range profileSvcs {
			fmt.Printf("  %s:\n", name)
			for _, s := range svcs {
				fmt.Printf("    - %s\n", s)
			}
		}
	}

	ctx := context.Background()
	rt, err := runtime.AutoDetect(ctx)
	if err != nil {
		fmt.Printf("\nRuntime: not detected (%v)\n", err)
	} else {
		fmt.Printf("\nRuntime: %s\n", rt.Name())
	}
}

func extractHostPort(portStr string) string {
	parts := strings.SplitN(portStr, "->", 2)
	if len(parts) != 2 {
		return ""
	}
	hostPart := parts[0]
	if idx := strings.LastIndex(hostPart, ":"); idx >= 0 {
		return hostPart[idx+1:]
	}
	return hostPart
}

// deployHostsFile is the relative path (from project root) of the remote
// deploy host registry consumed by `boba-ctl deploy`.
const deployHostsFile = "deploy/hosts.yaml"

// deployHost is the per-host shape parsed from deploy/hosts.yaml. It mirrors
// the containers submodule's remote.RemoteHost field set plus the deploy-only
// fields (remote_path / compose_file / profile) that the SSH-driven boot needs.
// §11.4.10: no credential VALUES live here — only KeyPath points at a local
// private key; the per-host .env is transferred out-of-band by the operator.
type deployHost struct {
	Name        string `yaml:"name"`
	Address     string `yaml:"address"`
	Port        int    `yaml:"port"`
	User        string `yaml:"user"`
	Auth        string `yaml:"auth"`
	KeyPath     string `yaml:"key_path"`
	Runtime     string `yaml:"runtime"`
	RemotePath  string `yaml:"remote_path"`
	ComposeFile string `yaml:"compose_file"`
	Profile     string `yaml:"profile"`
}

// deployHostsConfig is the top-level deploy/hosts.yaml document.
type deployHostsConfig struct {
	SchemaVersion int          `yaml:"schema_version"`
	Hosts         []deployHost `yaml:"hosts"`
}

// parseDeployHosts reads + unmarshals the deploy host registry from path.
func parseDeployHosts(path string) (*deployHostsConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var cfg deployHostsConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return &cfg, nil
}

// findDeployHost returns the named host block, or an error naming the
// available hosts when not found.
func findDeployHost(cfg *deployHostsConfig, name string) (*deployHost, error) {
	for i := range cfg.Hosts {
		if cfg.Hosts[i].Name == name {
			return &cfg.Hosts[i], nil
		}
	}
	names := make([]string, 0, len(cfg.Hosts))
	for i := range cfg.Hosts {
		names = append(names, cfg.Hosts[i].Name)
	}
	return nil, fmt.Errorf("host %q not found in registry (available: %s)", name, strings.Join(names, ", "))
}

// expandHome resolves a leading "~/" to the caller's home directory so a
// key_path like "~/.ssh/id_ed25519" works when handed to ssh -i.
func expandHome(p string) string {
	if p == "~" || strings.HasPrefix(p, "~/") {
		if home, err := os.UserHomeDir(); err == nil {
			if p == "~" {
				return home
			}
			return filepath.Join(home, p[2:])
		}
	}
	return p
}

// authMethod maps the hosts.yaml `auth` field onto the containers submodule's
// remote.AuthMethod closed set. "key" is the deploy registry's shorthand for
// SSH-key auth (the submodule const is "ssh_key").
func authMethod(s string) remote.AuthMethod {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "key", "ssh_key", "ssh-key":
		return remote.AuthSSHKey
	case "agent", "ssh_agent", "ssh-agent":
		return remote.AuthSSHAgent
	case "password":
		return remote.AuthPassword
	default:
		return remote.AuthSSHKey
	}
}

// toRemoteHost converts a parsed deployHost into the containers submodule's
// remote.RemoteHost (§11.4.76 — the SSH executor + remote compose orchestrator
// consume this type; we do NOT shell out to ssh ourselves).
func (h *deployHost) toRemoteHost() remote.RemoteHost {
	return remote.RemoteHost{
		Name:    h.Name,
		Address: h.Address,
		Port:    h.Port,
		User:    h.User,
		KeyPath: expandHome(h.KeyPath),
		Auth:    authMethod(h.Auth),
		Runtime: h.Runtime,
	}
}

func cmdDeploy() {
	fs := flag.NewFlagSet("deploy", flag.ExitOnError)
	profile := fs.String("profile", "", "compose profile to use on the remote host (e.g. go)")
	fs.Parse(os.Args[2:])

	if fs.NArg() < 1 {
		fmt.Fprintf(os.Stderr, "Usage: boba-ctl deploy <host-name> [--profile go]\n")
		os.Exit(1)
	}
	hostName := fs.Arg(0)

	hostsPath := filepath.Join(projectRoot(), deployHostsFile)
	cfg, err := parseDeployHosts(hostsPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	dh, err := findDeployHost(cfg, hostName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Profile precedence: --profile flag overrides the host's registry default.
	profileToUse := dh.Profile
	if *profile != "" {
		profileToUse = *profile
	}
	composeFile := dh.ComposeFile
	if composeFile == "" {
		composeFile = "docker-compose.yml"
	}

	host := dh.toRemoteHost()
	logger := logging.NewStdLogger("boba-ctl-deploy")

	// §11.4.76: drive the remote boot through the containers submodule's
	// SSH executor + remote compose orchestrator — never a hand-rolled ssh.
	executor, err := remote.NewSSHExecutor(logger,
		remote.WithConnectTimeout(10*time.Second),
		remote.WithCommandTimeout(30*time.Minute),
		remote.WithKeepAlive(30*time.Second),
		remote.WithKeepAliveCountMax(10),
	)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: create SSH executor: %v\n", err)
		os.Exit(1)
	}
	defer executor.Close()

	ctx := context.Background()
	fmt.Printf("Deploying to %s (%s@%s:%s) profile=%q\n",
		host.Name, host.User, host.Address, dh.RemotePath, profileToUse)

	if !executor.IsReachable(ctx, host) {
		fmt.Fprintf(os.Stderr, "Error: host %s is not reachable over SSH (%s@%s)\n",
			host.Name, host.User, host.Address)
		os.Exit(1)
	}
	fmt.Printf("  [1/3] SSH reachable\n")

	orch := remote.NewRemoteComposeOrchestrator(host, executor, logger)
	project := compose.ComposeProject{
		Name:    "boba",
		File:    filepath.Join(dh.RemotePath, composeFile),
		Profile: profileToUse,
	}

	// remote.RemoteComposeOrchestrator.Up runs the compose `up -d` on the
	// remote host via the SSH executor, auto-detecting podman-compose first
	// (matches the host's preinstalled podman-compose 1.5.0).
	if err := orch.Up(ctx, project); err != nil {
		fmt.Fprintf(os.Stderr, "Error: remote compose up on %s: %v\n", host.Name, err)
		os.Exit(1)
	}
	fmt.Printf("  [2/3] compose up -d (project=boba) issued on %s\n", host.Name)

	// Health: query remote service status through the same orchestrator.
	statuses, err := orch.Status(ctx, project)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: remote status on %s: %v\n", host.Name, err)
		os.Exit(1)
	}
	fmt.Printf("  [3/3] remote service status:\n")
	if len(statuses) == 0 {
		fmt.Println("        (no services reported)")
	}
	for _, s := range statuses {
		health := s.Health
		if health == "" {
			health = "-"
		}
		fmt.Printf("        %-25s %-12s %s\n", s.Name, s.State, health)
	}
	fmt.Printf("Deploy to %s complete.\n", host.Name)
}
