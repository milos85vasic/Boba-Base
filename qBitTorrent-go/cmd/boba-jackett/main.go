// boba-jackett — HTTP service exposing the spec §8 Jackett management
// API on the configured port (default 7189). See
// docs/superpowers/specs/2026-04-27-jackett-management-ui-and-system-db-design.md
// for the full endpoint catalog.
//
// Boot sequence (see Task 21 in the plan):
//
//  1. Read env: BOBA_DB_PATH, BOBA_ENV_PATH, JACKETT_URL, JACKETT_API_KEY,
//     PORT (defaulted via the env() helper).
//  2. bootstrap.EnsureMasterKey — generates BOBA_MASTER_KEY in .env on
//     first boot; otherwise re-uses the persisted key.
//  3. db.Open + db.Migrate.
//  4. Construct repos, Jackett client, and the secret redactor (installed
//     as the global stdlib log writer; preloaded with every credential
//     plaintext so accidental leaks never reach stderr).
//  5. Run a synchronous first-pass autoconfig (errors are non-fatal — the
//     service can serve management endpoints with Jackett offline; the
//     /healthz "degraded" status reflects that).
//  6. Start http.Server with graceful shutdown on SIGINT/SIGTERM.
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/bootstrap"
	"github.com/milos85vasic/qBitTorrent-go/internal/db"
	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackettapi"
	"github.com/milos85vasic/qBitTorrent-go/internal/logging"
)

const (
	defaultPort    = "7189"
	defaultDBPath  = "config/boba.db"
	defaultEnvPath = ".env"
	// serviceVersion is the build-time version stamp surfaced through
	// /healthz. Bumped manually on releases — keeping it in source avoids
	// pulling a build-info dependency for a single string.
	serviceVersion = "0.1.0"
)

// env returns os.Getenv(name) trimmed of surrounding whitespace, or
// fallback when the variable is unset / empty.
func env(name, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return fallback
}

func main() {
	if err := run(); err != nil {
		// log.Fatal would skip deferred cleanups (notably the *sql.DB
		// Close). Print + os.Exit(1) preserves them.
		fmt.Fprintln(os.Stderr, "boba-jackett:", err)
		os.Exit(1)
	}
}

func run() error {
	startTime := time.Now().UTC()
	dbPath := env("BOBA_DB_PATH", defaultDBPath)
	envPath := env("BOBA_ENV_PATH", defaultEnvPath)
	jackettURL := env("JACKETT_URL", "http://localhost:9117")
	jackettAPIKey := env("JACKETT_API_KEY", "")
	// §6.R: the dashboard admin password is injected at runtime, never a
	// literal. Default empty = the out-of-the-box Jackett install. Used only
	// for the cookie-session login the MANAGEMENT API requires when the
	// dashboard is password protected (the Torznab feeds use the apikey).
	jackettAdminPassword := env("JACKETT_ADMIN_PASSWORD", "")
	port := env("PORT", defaultPort)

	// 1) Master-key bootstrap. EnsureMasterKey requires .env to exist;
	// create an empty one when absent so this is a one-step boot for
	// fresh deployments.
	if _, err := os.Stat(envPath); errors.Is(err, os.ErrNotExist) {
		if err := os.WriteFile(envPath, []byte(""), 0o600); err != nil {
			return fmt.Errorf("create .env: %w", err)
		}
	}
	key, generated, err := bootstrap.EnsureMasterKey(envPath)
	if err != nil {
		return fmt.Errorf("ensure master key: %w", err)
	}

	// 2) Open DB + run migrations. Fatal: nothing else works without DB.
	conn, err := db.Open(dbPath)
	if err != nil {
		return fmt.Errorf("db.Open(%q): %w", dbPath, err)
	}
	defer conn.Close()
	if err := db.Migrate(conn); err != nil {
		return fmt.Errorf("db.Migrate: %w", err)
	}

	// 3) Repos + Jackett client.
	credsRepo := repos.NewCredentials(conn, key)
	indexersRepo := repos.NewIndexers(conn)
	catalogRepo := repos.NewCatalog(conn)
	runsRepo := repos.NewRuns(conn)
	overridesRepo := repos.NewOverrides(conn)
	jClient := jackett.NewClientWithPassword(jackettURL, jackettAPIKey, jackettAdminPassword)

	// 4) Redactor — wrap stderr, then preload with current credential
	// plaintexts so any accidental log of those values is masked. Set
	// log.SetOutput BEFORE the first log.Printf so the master-key-generated
	// notice (and everything after) flows through the redactor.
	redactor := logging.NewRedactor(os.Stderr)
	log.SetOutput(redactor)
	log.SetFlags(log.LstdFlags | log.LUTC)

	if generated {
		log.Printf("boba-jackett: BOBA_MASTER_KEY generated and persisted to %s", envPath)
	}

	rows, err := credsRepo.List()
	if err != nil {
		log.Printf("boba-jackett: list credentials for redactor seed failed: %v", err)
	} else {
		for _, c := range rows {
			decrypted, derr := credsRepo.Get(c.Name)
			if derr != nil {
				log.Printf("boba-jackett: decrypt %s failed: %v", c.Name, derr)
				continue
			}
			redactor.AddSecret(decrypted.Username)
			redactor.AddSecret(decrypted.Password)
			redactor.AddSecret(decrypted.Cookies)
		}
		log.Printf("boba-jackett: redactor preloaded with %d credential bundle(s)", len(rows))
	}
	// Always redact the API key from log output. The raw master key bytes
	// contain nulls and are never serialized to text, so we deliberately
	// do NOT register them as a secret (would be a no-op anyway).
	redactor.AddSecret(jackettAPIKey)
	// §6.H: the dashboard admin password is a secret — register it so an
	// accidental log never surfaces it. AddSecret no-ops on the empty default.
	redactor.AddSecret(jackettAdminPassword)

	// 5) First-pass autoconfig (synchronous, errors non-fatal). The
	// orchestrator is idempotent so a re-trigger after a creds upsert
	// is safe; here we run once at boot to converge persisted state with
	// what's actually configured at Jackett.
	autoconfigDeps := jackett.AutoconfigDeps{
		Creds:     credsRepo,
		Overrides: overridesRepo,
		Indexers:  indexersRepo,
		Runs:      runsRepo,
		Client:    jClient,
	}
	envOverrides := jackett.ParseIndexerMapCSV(os.Getenv("JACKETT_INDEXER_MAP"))
	bootResult := jackett.Autoconfigure(autoconfigDeps, envOverrides)
	log.Printf("boba-jackett: boot autoconfig — discovered=%d configured_now=%d errors=%d",
		len(bootResult.DiscoveredCredentials),
		len(bootResult.ConfiguredNow),
		len(bootResult.Errors))

	// 6) HTTP wiring. The post-credential-upsert AutoconfigTrigger runs
	// in a goroutine so the HTTP request thread isn't blocked on Jackett
	// round-trips; the manual /autoconfig/run trigger is synchronous so
	// the caller sees the full result.
	deps := &jackettapi.Deps{
		Credentials: &jackettapi.CredentialsDeps{
			Repo:     credsRepo,
			Indexers: indexersRepo,
			Jackett:  jClient,
			EnvPath:  envPath,
			AutoconfigTrigger: func() {
				go func() {
					res := jackett.Autoconfigure(autoconfigDeps, envOverrides)
					log.Printf("boba-jackett: post-cred autoconfig — configured_now=%d errors=%d",
						len(res.ConfiguredNow), len(res.Errors))
				}()
			},
		},
		Indexers: &jackettapi.IndexersDeps{
			Indexers: indexersRepo, Creds: credsRepo, Catalog: catalogRepo, Jackett: jClient,
		},
		Catalog: &jackettapi.CatalogDeps{
			Catalog: catalogRepo, Jackett: jClient,
		},
		Runs: &jackettapi.RunsDeps{
			Repo: runsRepo,
			AutoconfigOnce: func() jackett.AutoconfigResult {
				return jackett.Autoconfigure(autoconfigDeps, envOverrides)
			},
		},
		Overrides: &jackettapi.OverridesDeps{Repo: overridesRepo},
		Health: &jackettapi.HealthDeps{
			DB: conn, Jackett: jClient, Version: serviceVersion, StartTime: startTime,
		},
	}

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           jackettapi.NewMux(deps),
		ReadHeaderTimeout: 5 * time.Second,
		// Catalog refresh fans out one HTTP call per indexer template
		// (~600 in production); 60s is the operator-visible upper bound.
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown on SIGINT/SIGTERM. ListenAndServe in a goroutine,
	// signal handler in main; whichever fires first wins. Shutdown gives
	// in-flight requests up to 10s to drain.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	errCh := make(chan error, 1)
	go func() {
		log.Printf("boba-jackett: listening on %s", srv.Addr)
		errCh <- srv.ListenAndServe()
	}()
	select {
	case err := <-errCh:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return fmt.Errorf("listen: %w", err)
	case sig := <-sigCh:
		log.Printf("boba-jackett: %s received, shutting down", sig)
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			return fmt.Errorf("shutdown: %w", err)
		}
		return nil
	}
}
