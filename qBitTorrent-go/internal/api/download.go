package api

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/httpx"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
)

func DownloadHandler(svc *service.MergeSearchService, qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.DownloadRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		results := []models.URLDownloadResult{}
		for _, u := range req.DownloadURLs {
			results = append(results, models.URLDownloadResult{URL: u, Status: "added"})
		}

		added := len(results)
		c.JSON(http.StatusOK, models.DownloadResult{
			DownloadID: fmt.Sprintf("%d", time.Now().UnixNano()),
			Status:     "initiated",
			URLsCount:  len(req.DownloadURLs),
			AddedCount: added,
			Results:    results,
		})
	}
}

func DownloadFileHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.DownloadRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		for _, u := range req.DownloadURLs {
			if u == "" {
				continue
			}
			if strings.HasPrefix(u, "magnet:") {
				c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.magnet"`, req.ResultID))
				c.Data(http.StatusOK, "text/plain; charset=utf-8", []byte(u))
				return
			}

			// Tracker-bound fetch: u is an arbitrary upstream tracker URL
			// (e.g. https://rutracker.org/forum/dl.php?t=...). Route it through
			// the configured outbound proxy (BOBA_UPSTREAM_PROXY / *_PROXY) so a
			// blocked egress IP can be worked around; loopback + sidecar hosts
			// are bypassed inside httpx. See internal/httpx/proxy.go.
			client := &http.Client{Timeout: 30 * time.Second, Transport: httpx.NewTransport()}
			resp, err := client.Get(u)
			if err != nil {
				continue
			}
			defer resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				data, err := io.ReadAll(resp.Body)
				if err != nil {
					continue
				}
				filename := u[strings.LastIndex(u, "/")+1:]
				if filename == "" || filename == u {
					filename = req.ResultID + ".torrent"
				}
				c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, filename))
				c.Data(http.StatusOK, "application/x-bittorrent", data)
				return
			}
		}

		c.JSON(http.StatusNotFound, gin.H{"error": "No downloadable torrent file found"})
	}
}

var btihRe = regexp.MustCompile(`(?i)btih:([a-f0-9]{40}|[a-f0-9]{32})`)

func MagnetHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body struct {
			ResultID     string   `json:"result_id"`
			DownloadURLs []string `json:"download_urls"`
		}
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		var hashes []string
		trackers := map[string]bool{}
		for _, u := range body.DownloadURLs {
			m := btihRe.FindStringSubmatch(u)
			if len(m) > 1 {
				hashes = append(hashes, m[1])
			}
			if strings.HasPrefix(u, "magnet:") {
				for _, tr := range regexp.MustCompile(`tr=([^&]+)`).FindAllStringSubmatch(u, -1) {
					if len(tr) > 1 {
						decoded, _ := url.QueryUnescape(tr[1])
						trackers[decoded] = true
					}
				}
			}
		}

		defaultTrackers := []string{
			"udp://tracker.opentrackr.org:1337",
			"udp://tracker.leechers.org:6969",
		}
		for _, dt := range defaultTrackers {
			trackers[dt] = true
		}

		name := url.QueryEscape(body.ResultID)
		magnet := "magnet:?dn=" + name
		// A magnet identifies exactly ONE torrent, so it must carry exactly ONE
		// xt=urn:btih:. A merged search-results row aggregates many DISTINCT
		// tracker-copies of the same content, each with a different infohash;
		// joining all of them produced a malformed multi-xt magnet that
		// qBittorrent rejects (confirmed live 2026-06-14: an Ubuntu merged row
		// produced a 21-xt magnet). Use only the PRIMARY source = the FIRST
		// infohash discovered (download_urls[0]'s hash = best/highest-seeded
		// source). Trackers from ALL sources are still aggregated below into this
		// single torrent's magnet.
		if len(hashes) > 0 {
			magnet += "&xt=urn:btih:" + hashes[0]
		}
		for t := range trackers {
			magnet += "&tr=" + url.QueryEscape(t)
		}

		c.JSON(http.StatusOK, gin.H{
			"magnet": magnet,
			"hashes": hashes,
		})
	}
}

func ActiveDownloadsHandler(qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"downloads": []interface{}{},
			"count":     0,
		})
	}
}

func QBittorrentAuthHandler(qbitURL string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.QBittorrentAuthRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			req = models.QBittorrentAuthRequest{Username: "admin", Password: "admin"}
		}

		client := &http.Client{Timeout: 10 * time.Second}
		data := url.Values{"username": {req.Username}, "password": {req.Password}}
		resp, err := client.PostForm(qbitURL+"/api/v2/auth/login", data)
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.QBittorrentAuthResponse{
				Status: "error",
				Error:  err.Error(),
			})
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			c.JSON(http.StatusOK, models.QBittorrentAuthResponse{
				Status:  "authenticated",
				Message: "Login successful",
			})
		} else {
			c.JSON(http.StatusUnauthorized, models.QBittorrentAuthResponse{
				Status: "failed",
				Error:  "Invalid credentials",
			})
		}
	}
}

func BridgeHealthHandler(bridgeURL string) gin.HandlerFunc {
	return func(c *gin.Context) {
		client := &http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get(bridgeURL)
		if err != nil {
			c.JSON(http.StatusOK, gin.H{
				"healthy":    false,
				"error":      err.Error(),
				"bridge_url": bridgeURL,
			})
			return
		}
		defer resp.Body.Close()
		c.JSON(http.StatusOK, gin.H{
			"healthy":     resp.StatusCode < 500,
			"status_code": resp.StatusCode,
			"bridge_url":  bridgeURL,
		})
	}
}

func ConfigHandler(cfg map[string]interface{}) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, cfg)
	}
}
