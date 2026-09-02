package client

import (
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"net/url"
	"testing"
)

// TestLogin_QBittorrent5_204EmptyBodyQBTSIDCookie pins the MEASURED behaviour
// of qBittorrent v5.2.3 (WebAPI 2.15.1), captured live on 2026-09-01:
//
//	POST /api/v2/auth/login  ->  HTTP 204, EMPTY body, Set-Cookie: QBT_SID_7185=...
//
// The pre-fix client required HTTP 200 AND body "Ok." AND a cookie literally
// named "SID" — all three are qBittorrent 4.x signals. Against a real 5.x
// server it therefore failed at the very first check, so the Go backend could
// never authenticate. Every existing Go test injected a fake "SID" cookie
// itself, so the suite validated the parser against a fixture that agreed
// with it rather than against qBittorrent (a producer=oracle collapse).
func TestLogin_QBittorrent5_204EmptyBodyQBTSIDCookie(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "QBT_SID_7185", Value: "abc123session", Path: "/"})
			w.WriteHeader(http.StatusNoContent) // 204, empty body
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	jar, _ := cookiejar.New(nil)
	base, _ := url.Parse(srv.URL)
	c := &Client{BaseURL: base, HTTPClient: &http.Client{Jar: jar}}

	if err := c.Login("admin", "admin"); err != nil {
		t.Fatalf("qBittorrent 5.x login must succeed on 204 + empty body + QBT_SID cookie, got error: %v", err)
	}
	if !c.IsAuthenticated() {
		t.Fatal("client must be authenticated after a 5.x login (QBT_SID cookie captured)")
	}
}

// TestLogin_QBittorrent4_200OkStillWorks is the backward-compatibility half:
// the 4.x signal must keep working, so the fix widens acceptance rather than
// swapping one narrow rule for another.
func TestLogin_QBittorrent4_200OkStillWorks(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.SetCookie(w, &http.Cookie{Name: "SID", Value: "legacy456", Path: "/"})
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("Ok."))
	}))
	defer srv.Close()

	jar, _ := cookiejar.New(nil)
	base, _ := url.Parse(srv.URL)
	c := &Client{BaseURL: base, HTTPClient: &http.Client{Jar: jar}}

	if err := c.Login("admin", "admin"); err != nil {
		t.Fatalf("legacy 4.x login must still succeed, got: %v", err)
	}
	if !c.IsAuthenticated() {
		t.Fatal("client must be authenticated after a 4.x login")
	}
}

// TestLogin_RejectsGenuineFailure is the NEGATIVE CONTROL (§11.4.201(1)):
// widening acceptance must NOT make the client accept a real rejection.
func TestLogin_RejectsGenuineFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte("Unauthorized"))
	}))
	defer srv.Close()

	jar, _ := cookiejar.New(nil)
	base, _ := url.Parse(srv.URL)
	c := &Client{BaseURL: base, HTTPClient: &http.Client{Jar: jar}}

	if err := c.Login("admin", "wrong"); err == nil {
		t.Fatal("a 401 with no cookie MUST be reported as a login failure")
	}
	if c.IsAuthenticated() {
		t.Fatal("client must NOT be authenticated after a rejected login")
	}
}

// TestLogin_StaleJarCookieMustNotFakeSuccess is the mutation arm for review
// finding I1. A Client whose jar ALREADY holds a session cookie must still
// report failure when the server rejects the credentials — the jar is history,
// the response is truth. Before the fix this returned nil (false success).
func TestLogin_StaleJarCookieMustNotFakeSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Genuine rejection: 401, and deliberately NO Set-Cookie.
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte("Unauthorized"))
	}))
	defer srv.Close()

	jar, _ := cookiejar.New(nil)
	base, _ := url.Parse(srv.URL)
	// Pre-seed the jar as if a PREVIOUS successful login had happened.
	jar.SetCookies(base, []*http.Cookie{{Name: "QBT_SID_7185", Value: "stale-from-earlier-login", Path: "/"}})

	c := &Client{BaseURL: base, HTTPClient: &http.Client{Jar: jar}}

	if err := c.Login("admin", "now-wrong-password"); err == nil {
		t.Fatal("a 401 with no Set-Cookie MUST be a failure even when the jar holds an older session cookie")
	}
	if c.IsAuthenticated() {
		t.Fatal("client must not be authenticated after a rejected re-login")
	}
}

// TestLogin_204WithoutCookieIsAnError is the M-a mutation arm. A 204 with no
// Set-Cookie previously returned nil while leaving c.sid empty — Login()
// "succeeded" but IsAuthenticated() was false, so the failure surfaced later
// as an unrelated symptom. Report it at the source.
func TestLogin_204WithoutCookieIsAnError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent) // 204, but deliberately NO Set-Cookie
	}))
	defer srv.Close()

	jar, _ := cookiejar.New(nil)
	base, _ := url.Parse(srv.URL)
	c := &Client{BaseURL: base, HTTPClient: &http.Client{Jar: jar}}

	if err := c.Login("admin", "admin"); err == nil {
		t.Fatal("a 204 with no session cookie must be reported as an error, not a silent success")
	}
	if c.IsAuthenticated() {
		t.Fatal("client must not report authenticated when no session cookie was issued")
	}
}
