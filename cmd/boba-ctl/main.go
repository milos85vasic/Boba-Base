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

		allOK := true
		var details []string

		if s.Health != "" && s.Health != "healthy" && s.Health != "none" {
			allOK = false
			details = append(details, "compose-health: "+s.Health)
		}

		for _, portStr := range s.Ports {
			hostPort := extractHostPort(portStr)
			if hostPort == "" {
				continue
			}
			addr := "127.0.0.1:" + hostPort
			conn, dialErr := dialer.DialContext(ctx, "tcp", addr)
			if dialErr != nil {
				allOK = false
				details = append(details, fmt.Sprintf("%s: %v", addr, dialErr))
			} else {
				conn.Close()
				details = append(details, fmt.Sprintf("%s: reachable", addr))
			}
		}

		statusLabel := "OK"
		if !allOK {
			statusLabel = "FAIL"
		}
		detail := strings.Join(details, "; ")
		if detail == "" {
			detail = "no ports exposed"
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
