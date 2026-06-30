// Package jackett implements a thin HTTP client for the Jackett admin API
// covering session warmup, catalog browse, indexer template fetch,
// configuration POST, and indexer deletion. The client is stateless beyond
// the cookie jar carried in its underlying *http.Client.
package jackett

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"time"
)

// CatalogEntry is a single indexer entry returned by /api/v2.0/indexers.
type CatalogEntry struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Type        string `json:"type"`
	Configured  bool   `json:"configured"`
	Language    string `json:"language"`
	Description string `json:"description"`
}

// Client is the Jackett admin-API HTTP client.
type Client struct {
	base          string
	apiKey        string
	adminPassword string
	http          *http.Client
}

// NewClient returns a Client targeting the given Jackett base URL and api key,
// with an EMPTY dashboard admin password (the default Jackett install). For a
// password-protected dashboard use [NewClientWithPassword].
func NewClient(base, apiKey string) *Client {
	return NewClientWithPassword(base, apiKey, "")
}

// NewClientWithPassword returns a Client carrying the dashboard admin password
// used for the cookie-session login the Jackett MANAGEMENT API requires (see
// the package doc + [Client.login]). The password is injected at runtime
// (§6.R: JACKETT_ADMIN_PASSWORD env), defaults to empty, and is NEVER a literal
// in tracked source. cookiejar.New(nil) cannot fail with a nil options
// argument, so the discarded error is safe.
func NewClientWithPassword(base, apiKey, adminPassword string) *Client {
	jar, _ := cookiejar.New(nil)
	return &Client{
		base:          strings.TrimRight(base, "/"),
		apiKey:        apiKey,
		adminPassword: adminPassword,
		http: &http.Client{
			Timeout: 30 * time.Second,
			Jar:     jar,
			// Do NOT auto-follow redirects. The MANAGEMENT API answers an
			// apikey-only request with HTTP 302 → /UI/Login when the dashboard
			// is password protected; an auto-following client would land on the
			// HTML login page (200) and fail to decode it as JSON, masking the
			// real cause. We surface the 302 to doManaged so it can run the
			// cookie-session login and retry (see login + doManaged).
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}
}

// WarmUp eagerly establishes the Jackett dashboard session cookie that the
// MANAGEMENT API (catalog browse, indexer /config) requires. It delegates to
// [Client.login] using the configured admin password. WarmUp is an
// OPTIMISATION, not a requirement: every management call independently runs
// the login-on-302 retry via doManaged, so a missing or expired session
// recovers transparently. Callers that ignore WarmUp's error are still safe.
func (c *Client) WarmUp() error {
	return c.login()
}

// login establishes the Jackett dashboard session cookie by POSTing the
// configured admin password to /UI/Dashboard. The Set-Cookie is captured by
// the client's cookie jar (net/http stores response cookies before applying
// CheckRedirect, so this works whether Jackett answers with 200 or 302). The
// dashboard password is injected at runtime (§6.R) and defaults to empty (the
// out-of-the-box Jackett install issues a session for the empty password).
//
// login is used ONLY for the MANAGEMENT API. The Torznab results/caps feeds
// authenticate by apikey and never call this.
//
// A wrong admin password is detected two ways: an explicit 401/403, OR (real
// Jackett's actual behavior) a 200 re-render of the login page with NO
// Set-Cookie. Either way login returns an error so management calls fail
// loudly instead of silently reporting a false success.
func (c *Client) login() error {
	form := url.Values{}
	form.Set("password", c.adminPassword)
	req, err := http.NewRequest("POST", c.base+"/UI/Dashboard", strings.NewReader(form.Encode()))
	if err != nil {
		return fmt.Errorf("build login request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("jackett dashboard login: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return fmt.Errorf("jackett_dashboard_login_rejected_%d", resp.StatusCode)
	}
	if base, perr := url.Parse(c.base); perr == nil && c.http.Jar != nil {
		if len(c.http.Jar.Cookies(base)) == 0 {
			return fmt.Errorf("jackett_dashboard_login_no_session_cookie")
		}
	}
	return nil
}

// doManaged issues a MANAGEMENT request built by mk and transparently handles
// the cookie-session requirement: if the first response is an HTTP redirect
// (Jackett bounces apikey-only management calls to /UI/Login when the
// dashboard is password protected), it runs the dashboard login to acquire the
// session cookie and retries the request ONCE. The cookie lives in the client
// jar and is replayed automatically by net/http on the retry and on every
// later call. mk MUST build a fresh *http.Request each call (so a POST body is
// re-readable on the retry).
func (c *Client) doManaged(mk func() (*http.Request, error)) (*http.Response, error) {
	req, err := mk()
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	if !isRedirect(resp.StatusCode) {
		return resp, nil
	}
	// Session missing/expired → authenticate and retry once.
	_ = resp.Body.Close()
	if lerr := c.login(); lerr != nil {
		return nil, lerr
	}
	req2, err := mk()
	if err != nil {
		return nil, err
	}
	resp, err = c.http.Do(req2)
	if err != nil {
		return nil, err
	}
	if isRedirect(resp.StatusCode) {
		_ = resp.Body.Close()
		return nil, fmt.Errorf("jackett_management_unauthorized_after_login")
	}
	return resp, nil
}

// isRedirect reports whether status is one of the HTTP redirect codes Jackett
// uses to bounce an unauthorized management request to /UI/Login.
func isRedirect(status int) bool {
	switch status {
	case http.StatusMovedPermanently, http.StatusFound, http.StatusSeeOther,
		http.StatusTemporaryRedirect, http.StatusPermanentRedirect:
		return true
	default:
		return false
	}
}

// GetCatalog returns the unconfigured-indexer catalog used by the "Add
// indexer" UI. The configured=false query param scopes the result to
// indexers the user can still add (configured ones are filtered out).
func (c *Client) GetCatalog() ([]CatalogEntry, error) {
	resp, err := c.doManaged(func() (*http.Request, error) {
		u, err := url.Parse(c.base + "/api/v2.0/indexers")
		if err != nil {
			return nil, fmt.Errorf("parse catalog url: %w", err)
		}
		q := u.Query()
		q.Set("apikey", c.apiKey)
		q.Set("configured", "false")
		u.RawQuery = q.Encode()
		req, err := http.NewRequest("GET", u.String(), nil)
		if err != nil {
			return nil, fmt.Errorf("build catalog request: %w", err)
		}
		req.Header.Set("Accept", "application/json")
		return req, nil
	})
	if err != nil {
		return nil, fmt.Errorf("get catalog: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == 401 {
		return nil, fmt.Errorf("jackett_auth_failed")
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("jackett_catalog_http_%d", resp.StatusCode)
	}
	var entries []CatalogEntry
	if err := json.NewDecoder(resp.Body).Decode(&entries); err != nil {
		return nil, fmt.Errorf("decode: %w", err)
	}
	return entries, nil
}

// GetIndexerTemplate returns the configuration field template for the given
// indexer id. Jackett's response is either a top-level array of fields or a
// {config: [...]} envelope depending on version; both shapes are normalised
// to []map[string]any.
func (c *Client) GetIndexerTemplate(id string) ([]map[string]any, error) {
	resp, err := c.doManaged(func() (*http.Request, error) {
		u := fmt.Sprintf("%s/api/v2.0/indexers/%s/config?apikey=%s", c.base, id, c.apiKey)
		req, err := http.NewRequest("GET", u, nil)
		if err != nil {
			return nil, fmt.Errorf("build template request: %w", err)
		}
		req.Header.Set("Accept", "application/json")
		return req, nil
	})
	if err != nil {
		return nil, fmt.Errorf("get template: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("template fetch HTTP %d", resp.StatusCode)
	}
	var raw any
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, fmt.Errorf("decode template: %w", err)
	}
	switch v := raw.(type) {
	case []any:
		out := make([]map[string]any, 0, len(v))
		for _, item := range v {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		return out, nil
	case map[string]any:
		if cfg, ok := v["config"].([]any); ok {
			out := make([]map[string]any, 0, len(cfg))
			for _, item := range cfg {
				if m, ok := item.(map[string]any); ok {
					out = append(out, m)
				}
			}
			return out, nil
		}
	}
	return nil, fmt.Errorf("unexpected template shape")
}

// PostIndexerConfig submits filled-in template fields for the given indexer.
// The fields slice is JSON-encoded as the request body.
func (c *Client) PostIndexerConfig(id string, fields []map[string]any) error {
	body, err := json.Marshal(fields)
	if err != nil {
		return fmt.Errorf("marshal config: %w", err)
	}
	resp, err := c.doManaged(func() (*http.Request, error) {
		u := fmt.Sprintf("%s/api/v2.0/indexers/%s/config?apikey=%s", c.base, id, c.apiKey)
		req, err := http.NewRequest("POST", u, bytes.NewReader(body))
		if err != nil {
			return nil, fmt.Errorf("build config request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")
		return req, nil
	})
	if err != nil {
		return fmt.Errorf("post config: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("config POST HTTP %d", resp.StatusCode)
	}
	return nil
}

// TestIndexer probes a configured indexer by hitting its /config endpoint.
// This is a minimal "is the indexer reachable and authorised" check; it
// does NOT run a real torznab search query (that's deferred to a follow-up
// task wiring the search path through this client).
//
// Returns:
//   - nil on HTTP 200 (caller maps this to status="ok").
//   - error with message "auth_failed" on HTTP 401.
//   - error with message "unreachable" on transport/network failure.
//   - error with message "http_<code>" on any other 4xx/5xx response.
//
// The handler in [internal/jackettapi.HandleTestIndexer] inspects the error
// text to map to the spec §8.2 status enum.
func (c *Client) TestIndexer(id string) error {
	resp, err := c.doManaged(func() (*http.Request, error) {
		u := fmt.Sprintf("%s/api/v2.0/indexers/%s/config?apikey=%s", c.base, id, c.apiKey)
		req, err := http.NewRequest("GET", u, nil)
		if err != nil {
			return nil, fmt.Errorf("build test request: %w", err)
		}
		req.Header.Set("Accept", "application/json")
		return req, nil
	})
	if err != nil {
		return fmt.Errorf("unreachable")
	}
	defer resp.Body.Close()
	if resp.StatusCode == 401 {
		return fmt.Errorf("auth_failed")
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("http_%d", resp.StatusCode)
	}
	return nil
}

// DeleteIndexer removes a configured indexer. A 404 is treated as success
// (already absent) so the caller can drive idempotent reconciliation.
func (c *Client) DeleteIndexer(id string) error {
	resp, err := c.doManaged(func() (*http.Request, error) {
		u := fmt.Sprintf("%s/api/v2.0/indexers/%s?apikey=%s", c.base, id, c.apiKey)
		req, err := http.NewRequest("DELETE", u, nil)
		if err != nil {
			return nil, fmt.Errorf("build delete request: %w", err)
		}
		return req, nil
	})
	if err != nil {
		return fmt.Errorf("delete indexer: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 && resp.StatusCode != 404 {
		return fmt.Errorf("delete HTTP %d", resp.StatusCode)
	}
	return nil
}
