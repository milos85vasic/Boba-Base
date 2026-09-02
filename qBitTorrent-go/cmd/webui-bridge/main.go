package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/config"
	"github.com/rs/zerolog/log"
)

func main() {
	cfg := config.Load()
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	r.GET("/bridge/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.GET("/", func(c *gin.Context) {
		proxyToQBittorrent(c, cfg)
	})

	r.NoRoute(func(c *gin.Context) {
		proxyToQBittorrent(c, cfg)
	})

	addr := fmt.Sprintf(":%d", cfg.BridgePort)
	log.Info().Str("addr", addr).Msg("webui-bridge listening")
	if err := r.Run(addr); err != nil {
		log.Fatal().Err(err).Msg("bridge server failed")
		os.Exit(1)
	}
}

func proxyToQBittorrent(c *gin.Context, cfg *config.Config) {
	target := fmt.Sprintf("http://%s:%d", cfg.QBittorrentHost, cfg.QBittorrentPort)
	targetURL := target + c.Request.URL.Path
	if c.Request.URL.RawQuery != "" {
		targetURL += "?" + c.Request.URL.RawQuery
	}

	client := &http.Client{
		Timeout: 30 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	var body io.Reader
	if c.Request.Body != nil && c.Request.Method != "GET" && c.Request.Method != "HEAD" {
		body = c.Request.Body
	}

	req, err := http.NewRequest(c.Request.Method, targetURL, body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Header hygiene — mirrors webui-bridge.py:proxy_to_qbittorrent.
	//
	// Host and Content-Length are recomputed by net/http from the request
	// URL and ContentLength, so forwarding the client's copies would either
	// be ignored or actively conflict with the recomputed values.
	//
	// Referer and Origin MUST be rewritten to the upstream qBittorrent
	// origin. qBittorrent enforces same-origin on state-changing endpoints:
	// a login carrying the browser's own Referer (e.g.
	// "http://localhost:7188/") is refused with 401 even when the
	// credentials are correct, so without this rewrite nobody can log in
	// through the bridge at all. Measured against qBittorrent 5.2.3
	// (2026-09-01): mismatched Referer + correct password -> 401;
	// matching Referer + correct password -> 204 + QBT_SID cookie.
	//
	// This rewrite touches ONLY the same-origin check. Authentication
	// itself is untouched: the client's Cookie header is forwarded as-is
	// and no session is ever injected, so a wrong password is still
	// rejected and an unauthenticated request is still refused upstream.
	for k, values := range c.Request.Header {
		if strings.EqualFold(k, "Host") || strings.EqualFold(k, "Content-Length") {
			continue
		}
		if strings.EqualFold(k, "Referer") || strings.EqualFold(k, "Origin") {
			req.Header.Set(k, target)
			continue
		}
		for _, v := range values {
			req.Header.Add(k, v)
		}
	}
	req.ContentLength = c.Request.ContentLength

	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer resp.Body.Close()

	for k, values := range resp.Header {
		for _, v := range values {
			if !strings.EqualFold(k, "Content-Length") {
				c.Writer.Header().Add(k, v)
			}
		}
	}

	c.Writer.WriteHeader(resp.StatusCode)
	io.Copy(c.Writer, resp.Body)
}
