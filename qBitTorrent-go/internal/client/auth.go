package client

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

func (c *Client) Login(username, password string) error {
	loginURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/auth/login"})
	data := url.Values{}
	data.Set("username", username)
	data.Set("password", password)

	resp, err := c.HTTPClient.PostForm(loginURL.String(), data)
	if err != nil {
		return fmt.Errorf("login request failed: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	trimmed := strings.TrimSpace(string(body))

	// BOB-LOGIN-FIX (2026-09-01). MEASURED against qBittorrent v5.2.3 /
	// WebAPI 2.15.1: a SUCCESSFUL login returns HTTP 204 with an EMPTY body
	// and sets a cookie named QBT_SID_<port>. qBittorrent 4.x returned HTTP
	// 200 with body "Ok." and a cookie named "SID".
	//
	// The previous implementation required all three 4.x signals, so it could
	// never authenticate against a 5.x server. It went unnoticed because every
	// test in this package injected a "SID" cookie itself — validating the
	// parser against a fixture that agreed with it rather than against
	// qBittorrent.
	//
	// The session cookie is the AUTHORITATIVE success signal (this is what the
	// Python download-proxy already relies on); status/body are accepted as
	// corroborating signals for both major versions.
	// STALE-JAR FIX (independent review I1, 2026-09-01): read THIS RESPONSE's
	// Set-Cookie, never the persistent jar. `Jar.Cookies(loginURL)` returns any
	// SID/QBT_SID* cookie from ANY earlier request, so a Client that logged in
	// successfully once and then called Login() again with wrong or rotated
	// credentials would see the server answer 401 with no Set-Cookie, still find
	// the OLD cookie in the jar, and report success. That is the same stale-jar
	// false-success class the shell path avoids by removing its cookie jar
	// before every attempt.
	//
	// Unreachable via NewClient today (fresh jar + single Login), but Login is
	// exported and callers may supply their own jar — so the seam is closed at
	// the source rather than left to caller discipline.
	var sessionCookie string
	for _, cookie := range resp.Cookies() {
		if cookie.Name == "SID" || strings.HasPrefix(cookie.Name, "QBT_SID") {
			sessionCookie = cookie.Value
			break
		}
	}

	switch {
	case sessionCookie != "":
		// Authoritative: the server issued a session.
	case resp.StatusCode == http.StatusNoContent:
		// M-a (review 2026-09-01): a 204 with NO Set-Cookie is not a usable
		// login. Previously this returned nil while leaving c.sid empty, so
		// Login() succeeded but IsAuthenticated() was false and every
		// subsequent call failed with a confusing, unrelated symptom. A
		// cookie-stripping proxy in front of qBittorrent produces exactly
		// this. Report it where it happens instead.
		return fmt.Errorf(
			"login returned HTTP 204 but no session cookie was set: "+
				"qBittorrent issues QBT_SID_<port> on success, so a cookie-stripping "+
				"proxy or a mismatched Referer/Origin is the likely cause (body=%q)",
			trimmed,
		)
	case resp.StatusCode == http.StatusOK && trimmed == "Ok.":
		// qBittorrent 4.x success.
	case resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent:
		return fmt.Errorf("login failed: HTTP %d: %s", resp.StatusCode, trimmed)
	default:
		return fmt.Errorf("login rejected: %s", trimmed)
	}

	if sessionCookie != "" {
		c.mu.Lock()
		c.sid = sessionCookie
		c.mu.Unlock()
	}
	return nil
}

func (c *Client) IsAuthenticated() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sid != ""
}
