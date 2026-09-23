package main

import (
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/api"
	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/milos85vasic/qBitTorrent-go/internal/config"
	"github.com/milos85vasic/qBitTorrent-go/internal/corsorigins"
	"github.com/milos85vasic/qBitTorrent-go/internal/httpx"
	"github.com/milos85vasic/qBitTorrent-go/internal/middleware"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	cfg := config.Load()

	zerolog.SetGlobalLevel(parseLogLevel(cfg.LogLevel))
	log.Info().Str("port", fmt.Sprintf("%d", cfg.ServerPort)).Msg("starting merge search service")

	// BOB-198 boot-time guard (operator decision 2026-08-26, §11.4.66:
	// "REFUSE TO START LAN-BOUND"). This binary registers CORS, Logger and
	// rate-limit middleware but NO authentication — 22 routes including
	// download and hook deletion would be reachable from anything on the LAN
	// if this process ever bound a non-loopback address. Checked as early as
	// possible (before the qBittorrent connection attempt, the proxy config,
	// or any store is opened) so a misconfiguration fails fast and loud
	// rather than silently exposing the surface for however long it takes an
	// operator to notice. log.Fatal() exits the process non-zero; the server
	// never reaches r.Run(addr) below.
	if err := checkLoopbackBind(cfg.ServerBindHost); err != nil {
		log.Fatal().Err(err).Str("configured_bind_host", cfg.ServerBindHost).
			Msg("BOB-198: refusing to start — non-loopback bind address and this binary ships no auth middleware")
	}

	// Install the configurable outbound proxy for tracker-bound egress before
	// any tracker-bound client is constructed. Fail-fast on a malformed value
	// so a typo in BOBA_UPSTREAM_PROXY is loud, never silently ignored.
	if err := httpx.Configure(cfg.UpstreamProxy); err != nil {
		log.Fatal().Err(err).Msg("invalid BOBA_UPSTREAM_PROXY")
	}
	if cfg.UpstreamProxy != "" {
		log.Info().Str("proxy", cfg.UpstreamProxy).Msg("tracker-bound egress routed through upstream proxy")
	}

	var qbitClient *client.Client
	qc, err := client.NewClient(cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword)
	if err != nil {
		log.Warn().Err(err).Msg("failed to connect to qBittorrent on startup, will retry on requests")
	} else {
		qbitClient = qc
		log.Info().Msg("connected to qBittorrent")
	}

	searchSvc := service.NewMergeSearchService(qbitClient, cfg.MaxConcurrentSearches)
	hookStore := api.NewHookStore("/config/download-proxy/hooks.json")
	scheduleStore := api.NewScheduleStore("/config/merge-service/scheduling.json")
	themeStore := api.NewThemeStore("/config/merge-service/theme.json")

	if os.Getenv("GIN_MODE") == "debug" || os.Getenv("GIN_MODE") == "test" {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()
	// RW-04: pass an explicit allowlist (from ALLOWED_ORIGINS, default the
	// dashboard origins) instead of a wildcard. The middleware echoes the
	// matched Origin and never emits Allow-Origin:* together with credentials.
	// An operator may still set ALLOWED_ORIGINS="*" to opt into a wildcard
	// policy that echoes the specific Origin (no forbidden combination).
	r.Use(middleware.CORS(parseAllowedOrigins(cfg.AllowedOrigins)...))
	r.Use(middleware.Logger())
	// BOB-111: per-IP token-bucket rate limiter on the public HTTP surface.
	// Tuned via RATE_LIMIT_RPM / RATE_LIMIT_BURST / RATE_LIMIT_DISABLED env.
	// A 429 refusal carries the minimal `{"error":"rate_limited"}` body +
	// Retry-After: 60 header — no client IP echoed (§11.4.10).
	r.Use(middleware.GinRateLimit(middleware.NewRateLimiterFromEnv()))

	r.GET("/health", api.HealthHandler)

	bridgeHost := cfg.QBittorrentHost
	if h := os.Getenv("BRIDGE_HOST"); h != "" {
		bridgeHost = h
	}
	r.GET("/api/v1/bridge/health", api.BridgeHealthHandler(fmt.Sprintf("http://%s:%d", bridgeHost, cfg.BridgePort)))

	r.GET("/api/v1/config", api.ConfigHandler(map[string]interface{}{
		"qbittorrent_url":          fmt.Sprintf("http://%s:%d", cfg.QBittorrentHost, cfg.ProxyPort),
		"qbittorrent_internal_url": cfg.QBittorrentURL(),
		"qbittorrent_port":         cfg.QBittorrentPort,
		"qbittorrent_host":         cfg.QBittorrentHost,
		"proxy_port":               cfg.ProxyPort,
	}))

	r.GET("/api/v1/stats", func(c *gin.Context) {
		c.JSON(http.StatusOK, searchSvc.Stats())
	})

	v1 := r.Group("/api/v1")
	{
		// Left OPEN, deliberately, for parity with the Python merge
		// service's own choices (config/lan_route_auth_policy.yaml):
		// /search, /search/sync and /search/:id/abort are public-by-design
		// (query operations / cancelling the caller's own in-memory search
		// -- no persistent state); /auth/qbittorrent is a separately
		// tracked known-gap on BOTH builds (it accepts qBittorrent WebUI
		// credentials, a different credential entirely from BOBA_API_TOKEN,
		// and gating it is out of this item's scope).
		v1.POST("/search", api.SearchHandler(searchSvc))
		v1.POST("/search/sync", api.SearchSyncHandler(searchSvc))
		v1.GET("/search/stream/:id", api.SearchStreamHandler(searchSvc))
		v1.GET("/search/:id", api.GetSearchHandler(searchSvc))
		v1.POST("/search/:id/abort", api.AbortSearchHandler(searchSvc))
		v1.GET("/downloads/active", api.ActiveDownloadsHandler(cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword))
		v1.POST("/auth/qbittorrent", api.QBittorrentAuthHandler(cfg.QBittorrentURL()))
		v1.GET("/theme", api.GetThemeHandler(themeStore))
		v1.GET("/hooks", api.ListHooksHandler(hookStore))
	}

	// BOB-203: genuine auth-enforcing middleware, for parity with the
	// Python merge service's Depends(require_api_token) wiring on the SAME
	// routes (download, download/file, magnet, PUT theme, hooks create/
	// delete, schedules create/delete). middleware.APIToken() passes
	// GET/HEAD/OPTIONS through unconditionally, so sharing this group's
	// "/api/v1" prefix with the open group above registers no conflicting
	// route (each method+path pair is still declared exactly once).
	// Fail-open-when-BOBA_API_TOKEN-unset is preserved -- see APIToken's
	// doc comment.
	v1Protected := r.Group("/api/v1")
	v1Protected.Use(middleware.APIToken())
	{
		v1Protected.POST("/download", api.DownloadHandler(searchSvc, cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword))
		v1Protected.POST("/download/file", api.DownloadFileHandler(searchSvc))
		v1Protected.POST("/magnet", api.MagnetHandler(searchSvc))
		v1Protected.PUT("/theme", api.PutThemeHandler(themeStore))
		v1Protected.POST("/hooks", api.CreateHookHandler(hookStore))
		v1Protected.DELETE("/hooks/:id", api.DeleteHookHandler(hookStore))
	}

	// The Python schedules routes are ALL Depends(require_api_token)-gated
	// except the GET list, and middleware.APIToken() already passes GET
	// through unconditionally, so the whole group may safely share one
	// middleware-carrying group (unlike /api/v1 above, there is no
	// deliberately-open POST/DELETE route in this group to keep separate).
	schedules := r.Group("/api/v1/schedules")
	schedules.Use(middleware.APIToken())
	{
		schedules.GET("", api.ListSchedulesHandler(scheduleStore))
		schedules.POST("", api.CreateScheduleHandler(scheduleStore))
		schedules.DELETE("/:id", api.DeleteScheduleHandler(scheduleStore))
	}

	// cfg.ServerBindHost defaults to "127.0.0.1" (loopback-only). This is the
	// real fix, not merely the guard above: the listener itself now binds
	// loopback by default instead of the prior bare ":port" (all-interfaces)
	// form. checkLoopbackBind is defense-in-depth against a future
	// regression that reintroduces a non-loopback default or an operator
	// override — it has already run by this point, so addr below is
	// guaranteed loopback whenever this line is reached.
	addr := fmt.Sprintf("%s:%d", cfg.ServerBindHost, cfg.ServerPort)
	log.Info().Str("addr", addr).Msg("server listening")
	if err := r.Run(addr); err != nil {
		log.Fatal().Err(err).Msg("server failed")
		os.Exit(1)
	}
}

// parseAllowedOrigins splits the comma-separated ALLOWED_ORIGINS config value
// into a trimmed slice for middleware.CORS. A value that parses to nothing
// yields nil, so CORS falls back to its default allowlist. "*" passes through
// as an entry, enabling the wildcard-but-echoed policy (never the forbidden
// Allow-Origin:* + credentials combination).
//
// The splitting rule lives in internal/corsorigins so this call site, the merge
// middleware, and boba-jackett all parse the variable identically (§11.4.251).
func parseAllowedOrigins(raw string) []string {
	return corsorigins.Split(raw)
}

// checkLoopbackBind reports whether bindHost is a loopback address —
// "127.0.0.1", "localhost" (case-insensitive), "::1", or any other
// 127.0.0.0/8 literal — returning nil when it is, and a descriptive,
// actionable error when it is not.
//
// BOB-198: this binary (qbittorrent-proxy-go, the --profile go alternative
// to the Python merge service) registers CORS, Logger and rate-limit
// middleware but ships NO authentication middleware this cycle — that was an
// explicitly REJECTED alternative (operator decision 2026-08-26, §11.4.66).
// Its 22 routes, several mutating (POST /api/v1/download, POST
// /api/v1/magnet, DELETE /api/v1/hooks/:id, POST and DELETE
// /api/v1/schedules), are therefore reachable by anything that can reach the
// bind address with zero authentication. The decision was "REFUSE TO START
// LAN-BOUND": bind loopback only, or refuse to start — never silently serve
// a LAN-reachable, unauthenticated surface.
//
// The check is deliberately syntax-only (no DNS resolution): a hostname
// other than the literal "localhost" is refused even if it *might* resolve
// to a loopback address at runtime, because trusting an unresolved name here
// would make the guard's own correctness depend on network state that is
// unavailable, slow, or attacker-influenced at exactly the moment the guard
// needs to be trustworthy. Fail closed on an unresolvable signal — the
// conservative-safe default (§11.4.201) — rather than fail open.
//
//   - "" (Go's bare ":port" listen-all-interfaces shorthand) is explicitly
//     refused: it is the exact class of bind this bug report names.
func checkLoopbackBind(bindHost string) error {
	host := strings.TrimSpace(bindHost)

	if host == "" {
		return fmt.Errorf(
			"bind host is empty, which binds ALL interfaces (the \":port\" " +
				"listen-all-interfaces shorthand, equivalent to 0.0.0.0); " +
				"this binary ships no authentication middleware — set " +
				"SERVER_BIND_HOST to a loopback address (127.0.0.1, ::1, or " +
				"localhost) to start it",
		)
	}

	if strings.EqualFold(host, "localhost") {
		return nil
	}

	ip := net.ParseIP(host)
	if ip == nil {
		return fmt.Errorf(
			"configured bind host %q is not a loopback address (and is not "+
				"resolved via DNS by this check — see checkLoopbackBind); "+
				"this binary ships no authentication middleware and MUST NOT "+
				"be exposed to the LAN — set SERVER_BIND_HOST to 127.0.0.1, "+
				"::1, or localhost",
			host,
		)
	}
	if !ip.IsLoopback() {
		return fmt.Errorf(
			"configured bind address %q is not loopback; this binary ships "+
				"no authentication middleware and MUST NOT be exposed to the "+
				"LAN — set SERVER_BIND_HOST to 127.0.0.1, ::1, or localhost",
			host,
		)
	}

	return nil
}

func parseLogLevel(level string) zerolog.Level {
	switch level {
	case "debug":
		return zerolog.DebugLevel
	case "warn":
		return zerolog.WarnLevel
	case "error":
		return zerolog.ErrorLevel
	default:
		return zerolog.InfoLevel
	}
}
