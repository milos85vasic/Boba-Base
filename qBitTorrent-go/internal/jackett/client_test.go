package jackett

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSessionWarmupAndCatalog(t *testing.T) {
	warmedUp := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "POST" && r.URL.Path == "/UI/Dashboard":
			http.SetCookie(w, &http.Cookie{Name: "Jackett", Value: "session"})
			warmedUp = true
			w.WriteHeader(302)
		case r.URL.Path == "/api/v2.0/indexers":
			if !warmedUp {
				w.WriteHeader(401)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.Write([]byte(`[{"id":"rutracker","name":"RuTracker.org","type":"private","configured":false}]`))
		}
	}))
	defer srv.Close()
	c := NewClient(srv.URL, "test-key")
	if err := c.WarmUp(); err != nil {
		t.Fatalf("WarmUp: %v", err)
	}
	cat, err := c.GetCatalog()
	if err != nil {
		t.Fatalf("GetCatalog: %v", err)
	}
	if len(cat) != 1 || cat[0].ID != "rutracker" {
		t.Fatalf("got %+v", cat)
	}
}

func TestPostConfig(t *testing.T) {
	var captured string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && strings.Contains(r.URL.Path, "/config") {
			body := make([]byte, 1024)
			n, _ := r.Body.Read(body)
			captured = string(body[:n])
			w.WriteHeader(200)
		}
	}))
	defer srv.Close()
	c := NewClient(srv.URL, "k")
	body := []map[string]any{{"id": "username", "value": "u"}}
	if err := c.PostIndexerConfig("x", body); err != nil {
		t.Fatalf("Post: %v", err)
	}
	if !strings.Contains(captured, `"username"`) {
		t.Fatalf("body not posted: %s", captured)
	}
}

// TestIndexerStatusMapping exercises every documented TestIndexer branch:
// 200→nil("ok"), 401→"auth_failed", other 4xx/5xx→"http_<code>". The
// handler layer maps these strings to the spec §8.2 status enum, so the
// EXACT error text is load-bearing. RED-on-regression: if the 401 branch
// were dropped, the 401 case would return "http_401" and this fails.
func TestIndexerStatusMapping(t *testing.T) {
	cases := []struct {
		name   string
		status int
		wantOK bool
		wantMsg string
	}{
		{"ok", 200, true, ""},
		{"auth", 401, false, "auth_failed"},
		{"server", 500, false, "http_500"},
		{"forbidden", 403, false, "http_403"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.status)
			}))
			defer srv.Close()
			c := NewClient(srv.URL, "k")
			err := c.TestIndexer("rutracker")
			if tc.wantOK {
				if err != nil {
					t.Fatalf("status %d: want nil, got %v", tc.status, err)
				}
				return
			}
			if err == nil {
				t.Fatalf("status %d: want error %q, got nil", tc.status, tc.wantMsg)
			}
			if err.Error() != tc.wantMsg {
				t.Fatalf("status %d: want msg %q, got %q", tc.status, tc.wantMsg, err.Error())
			}
		})
	}
}

// TestIndexerUnreachable covers the transport-failure branch (no server
// listening) — it MUST map to the "unreachable" sentinel, not a generic
// wrapped error. RED-on-regression: a generic fmt.Errorf would not equal
// "unreachable" and the handler would mis-classify the indexer status.
func TestIndexerUnreachable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := srv.URL
	srv.Close() // close immediately → connection refused
	c := NewClient(url, "k")
	err := c.TestIndexer("x")
	if err == nil || err.Error() != "unreachable" {
		t.Fatalf("want unreachable, got %v", err)
	}
}

// TestDeleteIndexerIdempotent covers DeleteIndexer's three documented
// outcomes: 200→nil, 404→nil (idempotent — already absent), other 4xx/5xx
// →error. RED-on-regression: if the `!= 404` guard were dropped, the 404
// case would return an error and break idempotent reconciliation.
func TestDeleteIndexerIdempotent(t *testing.T) {
	cases := []struct {
		name    string
		status  int
		wantErr bool
	}{
		{"deleted", 200, false},
		{"already-absent", 404, false},
		{"server-error", 500, true},
		{"bad-request", 400, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var gotMethod string
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				gotMethod = r.Method
				w.WriteHeader(tc.status)
			}))
			defer srv.Close()
			c := NewClient(srv.URL, "k")
			err := c.DeleteIndexer("rutracker")
			if (err != nil) != tc.wantErr {
				t.Fatalf("status %d: wantErr=%v, got %v", tc.status, tc.wantErr, err)
			}
			if gotMethod != "DELETE" {
				t.Fatalf("expected DELETE verb, got %s", gotMethod)
			}
		})
	}
}

// TestGetCatalogErrorBranches covers GetCatalog's 401 → "jackett_auth_failed"
// and other-4xx → "jackett_catalog_http_<code>" error mappings (the success
// path is already covered by TestSessionWarmupAndCatalog). RED-on-regression:
// collapsing the 401 branch into the generic one would change the error text
// the UI relies on to prompt a re-auth.
func TestGetCatalogErrorBranches(t *testing.T) {
	cases := []struct {
		status  int
		wantMsg string
	}{
		{401, "jackett_auth_failed"},
		{503, "jackett_catalog_http_503"},
	}
	for _, tc := range cases {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(tc.status)
		}))
		c := NewClient(srv.URL, "k")
		_, err := c.GetCatalog()
		srv.Close()
		if err == nil || err.Error() != tc.wantMsg {
			t.Fatalf("status %d: want %q, got %v", tc.status, tc.wantMsg, err)
		}
	}
}

// TestGetIndexerTemplateShapes covers the dual-shape normalisation
// (bare-array vs {config:[...]} envelope) AND the HTTP-error + bad-shape
// branches. RED-on-regression: dropping the envelope case returns
// "unexpected template shape" for the {config:...} input and this fails.
func TestGetIndexerTemplateShapes(t *testing.T) {
	t.Run("bare-array", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte(`[{"id":"username","value":""}]`))
		}))
		defer srv.Close()
		out, err := NewClient(srv.URL, "k").GetIndexerTemplate("x")
		if err != nil || len(out) != 1 || out[0]["id"] != "username" {
			t.Fatalf("bare-array: out=%v err=%v", out, err)
		}
	})
	t.Run("config-envelope", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte(`{"config":[{"id":"password","value":""}]}`))
		}))
		defer srv.Close()
		out, err := NewClient(srv.URL, "k").GetIndexerTemplate("x")
		if err != nil || len(out) != 1 || out[0]["id"] != "password" {
			t.Fatalf("envelope: out=%v err=%v", out, err)
		}
	})
	t.Run("http-error", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(500)
		}))
		defer srv.Close()
		_, err := NewClient(srv.URL, "k").GetIndexerTemplate("x")
		if err == nil || !strings.Contains(err.Error(), "HTTP 500") {
			t.Fatalf("http-error: want HTTP 500, got %v", err)
		}
	})
	t.Run("bad-shape", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte(`"a bare string is not a template"`))
		}))
		defer srv.Close()
		_, err := NewClient(srv.URL, "k").GetIndexerTemplate("x")
		if err == nil || !strings.Contains(err.Error(), "unexpected template shape") {
			t.Fatalf("bad-shape: want unexpected template shape, got %v", err)
		}
	})
}
