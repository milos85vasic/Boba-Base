// Package corsorigins is the SINGLE source of truth for resolving the CORS
// origin allowlist across every Go service in this repository.
//
// WHY IT EXISTS (§11.4.251 — no byte-identical forks). Two Go CORS middlewares
// (internal/middleware for the merge service, internal/jackettapi for
// boba-jackett) each carried their own copy of "read ALLOWED_ORIGINS, split it,
// pick a default". The copies drifted: they disagreed on wildcard detection
// (whole-string vs per-element) and on what an all-whitespace value means
// (fall back to defaults vs revoke every origin), and neither derived its
// default port from MERGE_SERVICE_PORT. Both copies now call this package, so
// the semantics cannot diverge again without a single visible edit here.
//
// THE CONTRACT IS THE PYTHON MERGE SERVICE, and it was MEASURED rather than
// read: download-proxy/src/api/__init__.py's _parse_allowed_origins was
// exec'd over its own source and driven across the full input space.
//
//	raw                | result
//	-------------------+------------------------------------------
//	unset (None)       | defaults
//	""                 | defaults      <- NOT an empty allowlist
//	"   "              | defaults
//	" , ,"             | defaults
//	"a"                | ["a"]
//	"a, b ,c"          | ["a","b","c"]  (comma-separated, each stripped)
//	"*"                | wildcard
//	"a,*"              | wildcard       <- detected PER ELEMENT, not whole-string
//
// The load-bearing property is that a value which parses to NOTHING falls back
// to the defaults. Failing closed to an empty allowlist would look like a safe
// choice, but it diverges from the reference implementation and silently breaks
// the dashboard for an operator whose ALLOWED_ORIGINS is merely malformed.
package corsorigins

import (
	"os"
	"regexp"
	"strings"
)

// EnvVar is the environment variable both services read.
const EnvVar = "ALLOWED_ORIGINS"

// Wildcard is the single entry that opens the allowlist to any origin.
const Wildcard = "*"

// extensionOriginRe mirrors the Python reference's _EXTENSION_ORIGIN_REGEX.
//
// A browser extension (e.g. the BobaLink WebExtension) calls the service from a
// background fetch whose Origin is chrome-extension://<32-char-id> (Chromium)
// or moz-extension://<uuid> (Firefox). A plain allowlist cannot cover these
// because the id is per-install, and a CORS wildcard would not match either
// since it only applies to the scheme-less host form. The pattern is anchored
// end-to-end so an http(s) site whose host merely CONTAINS "chrome-extension"
// is not matched.
var extensionOriginRe = regexp.MustCompile(`^(chrome-extension|moz-extension)://[A-Za-z0-9._\-]+$`)

// IsExtensionOrigin reports whether origin is a browser-extension origin.
func IsExtensionOrigin(origin string) bool {
	return extensionOriginRe.MatchString(origin)
}

// MergeServicePort returns the port the merge service is served on, mirroring
// the Python reference's `_MERGE_PORT = os.getenv("MERGE_SERVICE_PORT",
// "7187")`. The value is read at call time, never cached, so a test or an
// operator changing the variable is honoured.
func MergeServicePort() string {
	if v := strings.TrimSpace(os.Getenv("MERGE_SERVICE_PORT")); v != "" {
		return v
	}
	return "7187"
}

// Defaults returns the allowlist used when the operator has configured none.
// It is byte-for-byte the Python reference's _DEFAULT_ORIGINS, INCLUDING the
// port derivation — the dashboard dev server on :4200 and the merge-service
// SPA on the real merge port, each on both the localhost name and the
// 127.0.0.1 IPv4 literal.
//
// A fresh slice is returned on every call so a caller cannot mutate the
// defaults for everyone else.
func Defaults() []string {
	port := MergeServicePort()
	return []string{
		"http://localhost:4200",    // ng serve dev server
		"http://127.0.0.1:4200",    // ng serve dev server (IPv4)
		"http://localhost:" + port, // merge service Angular SPA
		"http://127.0.0.1:" + port, // merge service Angular SPA (IPv4)
	}
}

// Split parses one comma-separated ALLOWED_ORIGINS value into its entries,
// trimming each and dropping empties — the Python reference's
// `[p.strip() for p in raw.split(",")]` followed by its empty filter.
//
// It deliberately does NOT apply the default fallback: Split reports exactly
// what the operator wrote, so a caller can distinguish "parsed to nothing" from
// "parsed to something". Resolve applies the fallback.
func Split(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if t := strings.TrimSpace(p); t != "" {
			out = append(out, t)
		}
	}
	return out
}

// Resolve returns the effective allowlist and whether it is a wildcard.
//
// Precedence, matching the Python reference:
//
//  1. explicit (a non-empty list passed by the caller — dependency injection,
//     used by tests and by callers that already read the variable themselves);
//  2. the ALLOWED_ORIGINS environment variable, when it is PRESENT;
//  3. Defaults().
//
// Steps 1 and 2 both go through Split, so an input that parses to nothing
// (empty, whitespace, commas) falls through to Defaults() rather than
// producing an empty allowlist.
//
// wildcard is true when ANY resolved entry is "*", matching the reference's
// per-element `"*" in _allowed_origins`. When wildcard is true the returned
// allowlist is nil: the caller must echo the request's specific Origin rather
// than emitting a literal "*".
func Resolve(explicit []string) (allow []string, wildcard bool) {
	return ResolveWithDefaults(explicit, Defaults())
}

// ResolveWithDefaults is Resolve with a caller-supplied fallback set, for a
// service whose default allowlist is a documented superset of the shared one
// (the merge service adds the download-proxy origin).
//
// The fallback is applied at EVERY step that resolves to nothing — an absent
// variable and a variable that parses to nothing reach the SAME set. Having
// two different "defaults" reachable by two different routes is precisely the
// defect this package was created to remove: before it, the merge service fell
// back to a 2-entry list when ALLOWED_ORIGINS was absent and a 6-entry list
// when it was present-but-empty, so the dev server on :4200 was granted or
// denied depending on a distinction no operator would think to make.
func ResolveWithDefaults(explicit, defaults []string) (allow []string, wildcard bool) {
	origins := normalise(explicit)

	if len(origins) == 0 {
		// os.LookupEnv, not os.Getenv: the present-but-empty and absent cases
		// are read explicitly so it is visible that they converge, rather than
		// converging by accident.
		if raw, present := os.LookupEnv(EnvVar); present {
			origins = Split(raw)
		}
	}
	if len(origins) == 0 {
		origins = normalise(defaults)
	}
	if len(origins) == 0 {
		origins = Defaults()
	}

	for _, o := range origins {
		if o == Wildcard {
			return nil, true
		}
	}
	return origins, false
}

// normalise trims and drops empty entries from an already-split list, so an
// explicit []string{" "} is treated as "the caller supplied nothing" exactly as
// the string " " is.
func normalise(in []string) []string {
	out := make([]string, 0, len(in))
	for _, o := range in {
		if t := strings.TrimSpace(o); t != "" {
			out = append(out, t)
		}
	}
	return out
}

// Index builds a lookup set from an allowlist, applying the comparison
// normalisation both middlewares use: lowercased, with any trailing slash
// removed. An Origin header is canonically lowercase and never carries a
// trailing slash (RFC 6454), so this only makes a hand-written ALLOWED_ORIGINS
// entry more forgiving — it never widens what a browser can actually send.
func Index(allow []string) map[string]bool {
	m := make(map[string]bool, len(allow))
	for _, o := range allow {
		m[Key(o)] = true
	}
	return m
}

// Key normalises a single origin for comparison against an Index.
func Key(origin string) string {
	return strings.ToLower(strings.TrimRight(strings.TrimSpace(origin), "/"))
}
