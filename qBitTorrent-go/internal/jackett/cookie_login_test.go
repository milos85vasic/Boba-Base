package jackett

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// --- Behaviorally-equivalent Jackett fake (Anti-Bluff / CONST-XII Third Law) ---
//
// Real password-protected Jackett authorizes the Torznab feeds (/results,
// /caps) by apikey alone, but the MANAGEMENT API (/api/v2.0/indexers and the
// per-indexer /config) requires the dashboard SESSION COOKIE: an apikey-only
// management request is answered with HTTP 302 → /UI/Login. The apikey is NOT
// sufficient for management.
//
// The fake below reproduces that exact behavior so a client that forgets the
// cookie-session login is caught:
//   - POST /UI/Dashboard with the correct `password` form field  → Set-Cookie
//     session + 302 (login succeeds, cookie established).
//   - POST /UI/Dashboard with a WRONG password                    → 200, NO
//     Set-Cookie (real Jackett re-renders the login page; no session).
//   - GET management endpoints WITHOUT the session cookie         → 302 Location
//     /UI/Login (apikey present but insufficient).
//   - GET management endpoints WITH the valid session cookie      → 200 JSON.
//   - GET /UI/Login                                               → 200 HTML
//     (so a naive redirect-follower lands on a non-JSON page, exactly like the
//     real product — the RED failure mode is honest).
//
// This is NOT a bluff-fake: it refuses management on apikey alone. A client
// that only sends the apikey fails against it, just as it would against real
// Jackett.
const fakeSessionCookieName = "Jackett"

func newPasswordProtectedJackett(t *testing.T, adminPassword string) *httptest.Server {
	t.Helper()
	const sessionValue = "valid-session-token"

	hasValidSession := func(r *http.Request) bool {
		ck, err := r.Cookie(fakeSessionCookieName)
		return err == nil && ck.Value == sessionValue
	}

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		// Dashboard login: establishes the session cookie iff the posted
		// password matches the server's configured admin password.
		case r.Method == http.MethodPost && r.URL.Path == "/UI/Dashboard":
			_ = r.ParseForm()
			if r.PostFormValue("password") == adminPassword {
				http.SetCookie(w, &http.Cookie{
					Name:  fakeSessionCookieName,
					Value: sessionValue,
					Path:  "/",
				})
				w.Header().Set("Location", "/")
				w.WriteHeader(http.StatusFound) // 302 on success (real Jackett)
				return
			}
			// Wrong password: real Jackett re-renders the login page with 200
			// and NO Set-Cookie.
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("<html>login</html>"))

		// The login page a 302 points at — HTML, not JSON.
		case r.URL.Path == "/UI/Login":
			w.Header().Set("Content-Type", "text/html")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("<html>Jackett login</html>"))

		// Management API: configured-indexers enumeration (discovery).
		case r.URL.Path == "/api/v2.0/indexers":
			if !hasValidSession(r) {
				w.Header().Set("Location", "/UI/Login")
				w.WriteHeader(http.StatusFound) // 302 — apikey alone is NOT enough
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"rutracker","name":"RuTracker.org","type":"private","configured":false}]`))

		// Management API: per-indexer config template.
		case strings.HasPrefix(r.URL.Path, "/api/v2.0/indexers/") && strings.HasSuffix(r.URL.Path, "/config"):
			if !hasValidSession(r) {
				w.Header().Set("Location", "/UI/Login")
				w.WriteHeader(http.StatusFound)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"username","value":""},{"id":"password","value":""}]`))

		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
}

// TestFakeJackettRefusesManagementWithoutCookie proves the fake is
// behaviorally equivalent to real password-protected Jackett: a bare apikey
// management request (no session cookie) gets HTTP 302 → /UI/Login. If this
// ever returns 200, the fake has degraded into a bluff-fake and every test
// built on it is worthless — so this guard is load-bearing.
func TestFakeJackettRefusesManagementWithoutCookie(t *testing.T) {
	srv := newPasswordProtectedJackett(t, "")
	defer srv.Close()

	// Raw client that does NOT follow redirects and carries NO cookie.
	raw := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	resp, err := raw.Get(srv.URL + "/api/v2.0/indexers?apikey=test-key&configured=false")
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("apikey-only management call: want 302, got %d (fake is a bluff-fake)", resp.StatusCode)
	}
	if loc := resp.Header.Get("Location"); !strings.Contains(loc, "/UI/Login") {
		t.Fatalf("want redirect to /UI/Login, got Location=%q", loc)
	}
}

// TestManagementCookieLogin_DiscoveryViaCookiePath is the core anti-bluff
// test: against a password-protected Jackett (empty admin password — the
// default install), a management call made with the apikey ALONE must
// transparently acquire the dashboard session cookie and succeed. The client
// is NOT pre-warmed here on purpose: the management path itself must drive the
// cookie login.
//
// FALSIFIABILITY REHEARSAL: removing the cookie-session login (the c.login()
// call inside doManaged) makes GetCatalog see the 302→/UI/Login and fail —
// observed verbatim in the porting evidence:
//
//	GetCatalog via cookie path: jackett_unreachable
//
// i.e. the discovery returns an error instead of the rutracker entry. A test
// that still passed after that mutation would be a bluff.
func TestManagementCookieLogin_DiscoveryViaCookiePath(t *testing.T) {
	srv := newPasswordProtectedJackett(t, "") // empty admin password = default Jackett
	defer srv.Close()

	c := NewClient(srv.URL, "test-key")

	// Discovery (GET /api/v2.0/indexers) — apikey only; must auto-login.
	cat, err := c.GetCatalog()
	if err != nil {
		t.Fatalf("GetCatalog via cookie path: %v", err)
	}
	if len(cat) != 1 || cat[0].ID != "rutracker" {
		t.Fatalf("discovery returned wrong data via cookie path: %+v", cat)
	}

	// Per-indexer config template (GET .../config) — same management surface,
	// must also be authorized by the (now-cached) session cookie.
	tmpl, err := c.GetIndexerTemplate("rutracker")
	if err != nil {
		t.Fatalf("GetIndexerTemplate via cookie path: %v", err)
	}
	if len(tmpl) != 2 || tmpl[0]["id"] != "username" {
		t.Fatalf("config template wrong via cookie path: %+v", tmpl)
	}
}

// TestManagementCookieLogin_ConfigurableAdminPassword proves the admin
// password is configurable (§6.R) and actually used in the dashboard login:
// the fake requires a non-empty password, and only a client constructed with
// the matching password establishes a session and reaches the management API.
func TestManagementCookieLogin_ConfigurableAdminPassword(t *testing.T) {
	const adminPW = "s3cr3t-dashboard-pw"
	srv := newPasswordProtectedJackett(t, adminPW)
	defer srv.Close()

	// Correct password → management succeeds.
	ok := NewClientWithPassword(srv.URL, "test-key", adminPW)
	if _, err := ok.GetCatalog(); err != nil {
		t.Fatalf("GetCatalog with correct admin password: %v", err)
	}

	// Wrong/empty password → login cannot establish a session → management
	// must FAIL (never a false success). This is the cookie-verification guard.
	bad := NewClientWithPassword(srv.URL, "test-key", "wrong-password")
	if _, err := bad.GetCatalog(); err == nil {
		t.Fatalf("GetCatalog with wrong admin password: want error, got success (cookie not verified)")
	}
}
