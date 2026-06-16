package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLoad_Defaults(t *testing.T) {
	os.Clearenv()
	cfg := Load()
	assert.Equal(t, "localhost", cfg.QBittorrentHost)
	assert.Equal(t, 7185, cfg.QBittorrentPort)
	assert.Equal(t, "admin", cfg.QBittorrentUsername)
	assert.Equal(t, "admin", cfg.QBittorrentPassword)
	assert.Equal(t, 7187, cfg.ServerPort)
	assert.Equal(t, 7188, cfg.BridgePort)
	assert.Equal(t, "info", cfg.LogLevel)
	assert.Equal(t, 30, cfg.SSETimeout)
	assert.Equal(t, 10, cfg.PluginTimeout)
	assert.Equal(t, 5, cfg.MaxConcurrentSearches)
	assert.False(t, cfg.DisableThemeInjection)
}

func TestLoad_EnvOverride(t *testing.T) {
	os.Clearenv()
	os.Setenv("QBITTORRENT_HOST", "myhost")
	os.Setenv("QBITTORRENT_PORT", "9999")
	os.Setenv("SERVER_PORT", "8888")
	os.Setenv("BRIDGE_PORT", "7777")
	os.Setenv("LOG_LEVEL", "debug")
	os.Setenv("SSE_TIMEOUT", "60")

	cfg := Load()
	assert.Equal(t, "myhost", cfg.QBittorrentHost)
	assert.Equal(t, 9999, cfg.QBittorrentPort)
	assert.Equal(t, 8888, cfg.ServerPort)
	assert.Equal(t, 7777, cfg.BridgePort)
	assert.Equal(t, "debug", cfg.LogLevel)
	assert.Equal(t, 60, cfg.SSETimeout)
}

func TestLoad_TrackerAuth(t *testing.T) {
	os.Clearenv()
	os.Setenv("RUTRACKER_USERNAME", "ru_user")
	os.Setenv("RUTRACKER_PASSWORD", "ru_pass")
	os.Setenv("IPTORRENTS_USERNAME", "ipt_user")
	os.Setenv("IPTORRENTS_PASSWORD", "ipt_pass")

	cfg := Load()
	assert.Equal(t, "ru_user", cfg.RutrackerUsername)
	assert.Equal(t, "ru_pass", cfg.RutrackerPassword)
	assert.Equal(t, "ipt_user", cfg.IPTorrentsUsername)
	assert.Equal(t, "ipt_pass", cfg.IPTorrentsPassword)
}

func TestLoad_TrackerCookies(t *testing.T) {
	os.Clearenv()
	os.Setenv("NNMCLUB_COOKIES", "nnm-cookie-blob")
	os.Setenv("RUTRACKER_COOKIES", "ru-cookie-blob")

	cfg := Load()
	// RUTRACKER_COOKIES MUST be read into RutrackerCookies (parity with
	// NNMClubCookies). The docker-compose go-profile service passes
	// RUTRACKER_COOKIES through; without this read it would be a dead env var.
	assert.Equal(t, "ru-cookie-blob", cfg.RutrackerCookies)
	assert.Equal(t, "nnm-cookie-blob", cfg.NNMClubCookies)
}

func TestLoad_KinozalFallback(t *testing.T) {
	os.Clearenv()
	os.Setenv("IPTORRENTS_USERNAME", "ipt_user")
	os.Setenv("IPTORRENTS_PASSWORD", "ipt_pass")

	cfg := Load()
	assert.Equal(t, "ipt_user", cfg.KinozalUsername)
	assert.Equal(t, "ipt_pass", cfg.KinozalPassword)
}

func TestLoad_MetadataAPIKeys(t *testing.T) {
	os.Clearenv()
	os.Setenv("OMDB_API_KEY", "omdb_key")
	os.Setenv("TMDB_API_KEY", "tmdb_key")
	os.Setenv("ANILIST_CLIENT_ID", "anilist_id")

	cfg := Load()
	assert.Equal(t, "omdb_key", cfg.OMDBAPIKey)
	assert.Equal(t, "tmdb_key", cfg.TMDBAPIKey)
	assert.Equal(t, "anilist_id", cfg.AniListClientID)
}

func TestQBittorrentURL(t *testing.T) {
	os.Clearenv()
	cfg := Load()
	assert.Equal(t, "http://localhost:7185", cfg.QBittorrentURL())

	os.Setenv("QBITTORRENT_HOST", "qb")
	os.Setenv("QBITTORRENT_PORT", "9090")
	cfg = Load()
	assert.Equal(t, "http://qb:9090", cfg.QBittorrentURL())
}