package corsorigins

import (
	"os"
	"reflect"
	"testing"
)

// The expected values below are not hand-written: they are the OUTPUT of the
// authoritative Python reference's own `_parse_allowed_origins`, obtained by
// exec'ing that function over download-proxy/src/api/__init__.py's source and
// driving it across this exact input space (2026-09-01):
//
//	unset (None)       -> defaults
//	""                 -> defaults
//	"   "              -> defaults
//	" , ,"             -> defaults
//	"a"                -> ["a"]
//	"a, b ,c"          -> ["a","b","c"]
//	"*"                -> ["*"]      (wildcard)
//	"a,*"              -> ["a","*"]  (wildcard)

func unsetForTest(t *testing.T, key string) {
	t.Helper()
	prev, had := os.LookupEnv(key)
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("unset %s: %v", key, err)
	}
	t.Cleanup(func() {
		if had {
			_ = os.Setenv(key, prev)
			return
		}
		_ = os.Unsetenv(key)
	})
}

func TestSplitMatchesPythonParsing(t *testing.T) {
	cases := []struct {
		raw  string
		want []string
	}{
		{"", []string{}},
		{"   ", []string{}},
		{" , ,", []string{}},
		{",,", []string{}},
		{"a", []string{"a"}},
		{"a, b ,c", []string{"a", "b", "c"}},
		{"  a  ", []string{"a"}},
		{"*", []string{"*"}},
		{"a,*", []string{"a", "*"}},
	}
	for _, tc := range cases {
		if got := Split(tc.raw); !reflect.DeepEqual(got, tc.want) {
			t.Errorf("Split(%q) = %#v, want %#v", tc.raw, got, tc.want)
		}
	}
}

func TestResolveFallsBackToDefaultsWheneverInputYieldsNothing(t *testing.T) {
	t.Setenv("MERGE_SERVICE_PORT", "7187")
	want := Defaults()

	// An ABSENT variable and a variable that parses to NOTHING must reach the
	// SAME set. Two different "defaults" reachable by two routes is the exact
	// defect this package removes.
	for _, tc := range []struct {
		name   string
		envSet bool
		env    string
	}{
		{"absent", false, ""},
		{"empty", true, ""},
		{"whitespace", true, "   "},
		{"commas", true, " , ,"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.envSet {
				t.Setenv(EnvVar, tc.env)
			} else {
				unsetForTest(t, EnvVar)
			}
			got, wildcard := Resolve(nil)
			if wildcard {
				t.Fatalf("%s must not be a wildcard", tc.name)
			}
			if !reflect.DeepEqual(got, want) {
				t.Errorf("Resolve() for %s = %#v, want the defaults %#v", tc.name, got, want)
			}
		})
	}
}

func TestResolveWildcardIsPerElement(t *testing.T) {
	// The reference tests each element AFTER splitting ("*" in the parsed
	// list), so a wildcard mixed with a host is still a wildcard. A
	// whole-string comparison — the bug this replaced — reports false here.
	for _, raw := range []string{"*", " * ", "https://a.example,*", "*,https://a.example"} {
		t.Setenv(EnvVar, raw)
		allow, wildcard := Resolve(nil)
		if !wildcard {
			t.Errorf("Resolve() with ALLOWED_ORIGINS=%q must report a wildcard", raw)
		}
		if allow != nil {
			t.Errorf("a wildcard result must carry a nil allowlist (the caller echoes the "+
				"request Origin instead of emitting a literal \"*\"); got %#v", allow)
		}
	}
}

func TestResolveExplicitBeatsEnv(t *testing.T) {
	t.Setenv(EnvVar, "https://from-env.example")
	got, wildcard := Resolve([]string{"https://explicit.example"})
	if wildcard {
		t.Fatal("not a wildcard")
	}
	if !reflect.DeepEqual(got, []string{"https://explicit.example"}) {
		t.Errorf("explicit origins must win over the environment; got %#v", got)
	}
}

func TestResolveExplicitThatParsesToNothingFallsThrough(t *testing.T) {
	// An explicit []string{" "} means the caller supplied nothing, exactly as
	// the string " " does — otherwise a caller could accidentally revoke every
	// origin by passing a blank entry.
	t.Setenv(EnvVar, "https://from-env.example")
	got, _ := Resolve([]string{"  ", ""})
	if !reflect.DeepEqual(got, []string{"https://from-env.example"}) {
		t.Errorf("an explicit list that parses to nothing must fall through to the env; got %#v", got)
	}
}

func TestDefaultsDeriveMergeServicePort(t *testing.T) {
	t.Setenv("MERGE_SERVICE_PORT", "9187")
	got := Defaults()
	want := []string{
		"http://localhost:4200",
		"http://127.0.0.1:4200",
		"http://localhost:9187",
		"http://127.0.0.1:9187",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Defaults() = %#v, want %#v", got, want)
	}

	// A fresh slice each call: a caller appending to the result (the merge
	// service does exactly that) must not mutate anyone else's defaults.
	first := Defaults()
	_ = append(first, "http://evil.example") //nolint:staticcheck // deliberately discarded
	if !reflect.DeepEqual(Defaults(), want) {
		t.Error("Defaults() leaked a shared backing array — a caller's append corrupted it")
	}
}

func TestIsExtensionOriginIsAnchored(t *testing.T) {
	allowed := []string{
		"chrome-extension://abcdefghijklmnopabcdefghijklmnop",
		"moz-extension://0c2f2a1e-1111-2222-3333-444455556666",
		"chrome-extension://a.b_c-d",
	}
	denied := []string{
		"",
		"http://chrome-extension.evil.example",
		"https://evil.example/chrome-extension://x",
		"chrome-extension://has space",
		"chrome-extension://",
		"safari-extension://abc",
		"xchrome-extension://abc",
	}
	for _, o := range allowed {
		if !IsExtensionOrigin(o) {
			t.Errorf("IsExtensionOrigin(%q) = false, want true", o)
		}
	}
	for _, o := range denied {
		if IsExtensionOrigin(o) {
			t.Errorf("IsExtensionOrigin(%q) = true, want false", o)
		}
	}
}

func TestKeyNormalisation(t *testing.T) {
	for _, tc := range []struct{ in, want string }{
		{"http://Localhost:4200", "http://localhost:4200"},
		{"http://localhost:4200/", "http://localhost:4200"},
		{"  http://localhost:4200  ", "http://localhost:4200"},
	} {
		if got := Key(tc.in); got != tc.want {
			t.Errorf("Key(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}
