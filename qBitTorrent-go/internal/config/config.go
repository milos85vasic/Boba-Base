package config

import (
	"fmt"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

type Config struct {
	QBittorrentHost       string
	QBittorrentPort       int
	QBittorrentUsername  string
	QBittorrentPassword string
	ServerPort           int
	BridgePort           int
	ProxyPort            int
	LogLevel             string
	SSETimeout           int
	PluginTimeout        int
	MaxConcurrentSearches int

	RutrackerUsername   string
	RutrackerPassword   string
	KinozalUsername     string
	KinozalPassword     string
	NNMClubCookies     string
	RutrackerCookies   string
	IPTorrentsUsername string
	IPTorrentsPassword string

	OMDBAPIKey       string
	TMDBAPIKey       string
	AniListClientID string

	AllowedOrigins            string
	MergeServicePort          int
	QBittorrentDataDir      string
	DisableThemeInjection    bool

	// UpstreamProxy is the single configurable outbound proxy for
	// tracker-bound egress (BOBA_UPSTREAM_PROXY: socks5:// | http:// |
	// https://). Empty falls back to the standard HTTP_PROXY / HTTPS_PROXY /
	// ALL_PROXY / NO_PROXY env vars. Loopback + sidecar (qbittorrent, jackett)
	// hosts are always bypassed — see internal/httpx.
	UpstreamProxy string
}

func Load() *Config {
	_ = godotenv.Load()

	return &Config{
		QBittorrentHost:       getEnv("QBITTORRENT_HOST", "localhost"),
		QBittorrentPort:       getEnvAsInt("QBITTORRENT_PORT", 7185),
		QBittorrentUsername:  getEnv("QBITTORRENT_USER", getEnv("QBITTORRENT_USERNAME", "admin")),
		QBittorrentPassword:  getEnv("QBITTORRENT_PASS", getEnv("QBITTORRENT_PASSWORD", "admin")),
		ServerPort:            getEnvAsInt("MERGE_SERVICE_PORT", getEnvAsInt("SERVER_PORT", 7187)),
		BridgePort:            getEnvAsInt("BRIDGE_PORT", 7188),
		ProxyPort:             getEnvAsInt("PROXY_PORT", 7186),
		LogLevel:              getEnv("LOG_LEVEL", "info"),
		SSETimeout:            getEnvAsInt("SSE_TIMEOUT", 30),
		PluginTimeout:         getEnvAsInt("PLUGIN_TIMEOUT", 10),
		MaxConcurrentSearches: getEnvAsInt("MAX_CONCURRENT_SEARCHES", 5),

		RutrackerUsername:   getEnv("RUTRACKER_USERNAME", ""),
		RutrackerPassword:   getEnv("RUTRACKER_PASSWORD", ""),
		KinozalUsername:     getEnv("KINOZAL_USERNAME", getEnv("IPTORRENTS_USERNAME", "")),
		KinozalPassword:     getEnv("KINOZAL_PASSWORD", getEnv("IPTORRENTS_PASSWORD", "")),
		NNMClubCookies:     getEnv("NNMCLUB_COOKIES", ""),
		RutrackerCookies:   getEnv("RUTRACKER_COOKIES", ""),
		IPTorrentsUsername: getEnv("IPTORRENTS_USERNAME", ""),
		IPTorrentsPassword: getEnv("IPTORRENTS_PASSWORD", ""),

		OMDBAPIKey:       getEnv("OMDB_API_KEY", ""),
		TMDBAPIKey:       getEnv("TMDB_API_KEY", ""),
		AniListClientID:   getEnv("ANILIST_CLIENT_ID", ""),

		AllowedOrigins:         getEnv("ALLOWED_ORIGINS", "http://localhost:7186,http://localhost:7187"),
		MergeServicePort:       getEnvAsInt("MERGE_SERVICE_PORT", 7187),
		QBittorrentDataDir:   getEnv("QBITTORRENT_DATA_DIR", "/mnt/DATA"),
		DisableThemeInjection: getEnv("DISABLE_THEME_INJECTION", "") == "1",

		UpstreamProxy: getEnv("BOBA_UPSTREAM_PROXY", ""),
	}
}

func (c *Config) QBittorrentURL() string {
	return fmt.Sprintf("http://%s:%d", c.QBittorrentHost, c.QBittorrentPort)
}

func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}

func getEnvAsInt(key string, fallback int) int {
	if value, exists := os.LookupEnv(key); exists {
		if i, err := strconv.Atoi(value); err == nil {
			return i
		}
	}
	return fallback
}