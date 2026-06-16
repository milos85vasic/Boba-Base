package client

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestStartSearch_QueryEncoding is a §11.4.135 standing regression guard for the
// Python merge-service bug class where a multi-word search query (containing a
// literal space) was interpolated RAW into the outbound request URL/body and
// crashed the HTTP layer / produced a malformed request.
//
// The Go client builds the qBittorrent WebAPI v2 /search/start request via
// url.Values + http.Client.PostForm (search.go StartSearch:30,36), which
// percent-encodes every value automatically. This test pins that safe behavior:
// the server-side received "pattern" form value MUST round-trip EXACTLY to the
// original multi-word / unicode query, AND the raw request body MUST contain no
// literal space (proving it was encoded, not interpolated raw).
//
// RED proof (mutation): rewrite StartSearch to build the body by raw
// fmt.Sprintf interpolation (e.g. "pattern="+query) instead of url.Values, and
// this test FAILs (decoded pattern mismatch / raw space present in body).
func TestStartSearch_QueryEncoding(t *testing.T) {
	cases := []struct {
		name  string
		query string
	}{
		{"multi_word", "ubuntu server 24.04"},
		{"leading_trailing_spaces", "  the matrix  "},
		{"unicode_cyrillic", "Игра престолов"},
		{"ampersand_and_equals", "rick & morty s01=hd"},
		{"plus_and_percent", "c++ 100% complete"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var gotPattern string
			var gotRawBody string
			var sawPatternField bool

			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == "/api/v2/auth/login" {
					http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
					w.WriteHeader(http.StatusOK)
					_, _ = w.Write([]byte("Ok."))
					return
				}
				if r.URL.Path == "/api/v2/search/start" {
					// Capture the raw body BEFORE Go's form parser decodes it, so
					// we can assert there is no raw (unencoded) space in the wire
					// payload — a raw space is exactly the interpolation bug.
					raw, _ := readAll(r)
					gotRawBody = raw
					// Re-parse the captured raw body deterministically.
					vals, _ := url.ParseQuery(raw)
					gotPattern = vals.Get("pattern")
					_, sawPatternField = vals["pattern"]

					w.Header().Set("Content-Type", "application/json")
					_ = json.NewEncoder(w).Encode(map[string]int{"id": 7})
					return
				}
			}))
			defer server.Close()

			client, err := NewClient(server.URL, "admin", "admin")
			require.NoError(t, err)

			id, err := client.StartSearch(tc.query, []string{"all"}, "all")
			require.NoError(t, err, "multi-word/unicode query must not crash the request layer")
			assert.Equal(t, 7, id)

			// User-observable outcome 1: the server received the EXACT query the
			// user typed, decoded losslessly from the encoded body.
			require.True(t, sawPatternField, "request must carry a 'pattern' field")
			assert.Equal(t, tc.query, gotPattern,
				"decoded pattern must round-trip exactly to the user query")

			// User-observable outcome 2: the wire body was encoded, not raw —
			// a literal space in the body proves raw interpolation (the bug).
			assert.NotContains(t, gotRawBody, " ",
				"raw request body must not contain a literal space (would be unencoded interpolation)")

			// Sanity: the encoded body must be a parseable query string and
			// reconstruct into a valid URL with no error.
			_, perr := url.ParseQuery(gotRawBody)
			assert.NoError(t, perr, "request body must be a well-formed encoded query string")
		})
	}
}

// readAll drains the request body into a string. Kept local so the guard test
// has no dependency beyond the standard library.
func readAll(r *http.Request) (string, error) {
	if r.Body == nil {
		return "", nil
	}
	var sb strings.Builder
	buf := make([]byte, 4096)
	for {
		n, err := r.Body.Read(buf)
		if n > 0 {
			sb.Write(buf[:n])
		}
		if err != nil {
			if err.Error() == "EOF" {
				return sb.String(), nil
			}
			return sb.String(), err
		}
	}
}
