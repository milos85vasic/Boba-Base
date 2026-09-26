#!/usr/bin/env bash
# test_check_fail_open_unanalysed_langs.sh — per-language RED/GREEN,
# golden-false, control-needle and paired-mutation arms for
# scripts/pre_build/check_fail_open_unanalysed_langs.sh (BOB-191).
#
# Arms:
#   per language (go, rs, rb, c):
#     <lang>-BAD   golden-bad fixture  -> exit 1, the expected rule named
#     <lang>-GOOD  golden-good fixture (fail-CLOSED handling) -> exit 0
#   GF1 golden-FALSE: the REAL qBitTorrent-go auth_middleware.go (constant-time
#       compare, 401 + return) — the fixture BOB-191 names — is not flagged
#   GF2 golden-FALSE: the idioms quoted inside comments/strings are not hits
#   B1 fail-closed: a nonexistent root -> exit 2
#   M1 paired mutation (Rust/Ruby/C): the analyser's rule table blanked ->
#       its built-in control needle is not seen -> the scan refuses (exit 2)
#       instead of reporting 0 hits
#   M2 paired mutation (Go): the empty-body test inverted -> the Go control
#       needle is not seen -> exit 2
#
# Usage: bash tests/pre_build/test_check_fail_open_unanalysed_langs.sh
# Exit:  0 all arms behaved; 1 otherwise; 3 go or python3 missing.
# Constitution: §1.1, §11.4.107(10), §11.4.201(1)(6)(7)(b), §11.4.224, §11.4.250.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PB="${REPO}/scripts/pre_build"
GATE="${PB}/check_fail_open_unanalysed_langs.sh"
PASS=0; FAIL=0
command -v go >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || { echo "ABORT: go and python3 are required (exit 3)"; exit 3; }
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

arm() {  # <label> <want-rc> <needle-or-empty> <gate> <args...>
    local label="$1" want="$2" needle="$3" gate="$4"; shift 4
    local out rc
    out="$(bash "${gate}" "$@" 2>&1)"; rc=$?
    if [[ "${rc}" -eq "${want}" ]] && { [[ -z "${needle}" ]] || grep -qF -- "${needle}" <<<"${out}"; }; then
        echo "  PASS  ${label} (exit ${rc})"; PASS=$((PASS+1))
    else
        echo "  FAIL  ${label}: wanted exit ${want} + '${needle}', got exit ${rc}"
        sed 's/^/          /' <<<"${out}" | sed -n '1,10p'; FAIL=$((FAIL+1))
    fi
}
fx() { mkdir -p "${TMP}/$1"; cat > "${TMP}/$1/$2"; echo "${TMP}/$1"; }

echo "BOB-191 fail-open scan for Go/Rust/Ruby/C — arms"

d="$(fx go-bad svc.go <<'EOF'
package svc

import "os"

func Delete(p string) int {
	err := os.Remove(p)
	if err != nil {
	}
	return 204
}
EOF
)"
arm "go-BAD empty error branch is reported" 1 "GO-EMPTY-ERR-BRANCH" "${GATE}" "${d}"
d="$(fx go-bad2 w.go <<'EOF'
package svc

func Work() {
	defer func() { recover() }()
	panic("x")
}
EOF
)"
arm "go-BAD deferred bare recover() is reported" 1 "GO-SWALLOWED-PANIC" "${GATE}" "${d}"
d="$(fx go-good v.go <<'EOF'
package svc

import "errors"

func Valid(err error) bool {
	if err != nil {
		return false
	}
	return true
}

func Guard(e error) error {
	if e != nil {
		return errors.New("refused")
	}
	defer func() {
		if r := recover(); r != nil {
			panic(r)
		}
	}()
	return nil
}
EOF
)"
arm "go-GOOD fail-closed error handling stays silent" 0 "OK: 0 fail-open hits" "${GATE}" "${d}"

d="$(fx rs-bad a.rs <<'EOF'
fn save() {
    match write() {
        Ok(_) => log(),
        Err(_) => {}
    }
    if let Err(e) = flush() {}
}
EOF
)"
arm "rs-BAD empty Err arm is reported" 1 "RS-EMPTY-ERR-ARM" "${GATE}" "${d}"
d="$(fx rs-good b.rs <<'EOF'
fn allowed() -> bool {
    match check() {
        Ok(_) => true,
        Err(_) => false,
    }
}
EOF
)"
arm "rs-GOOD Err arm that denies stays silent" 0 "OK:" "${GATE}" "${d}"

d="$(fx rb-bad a.rb <<'EOF'
def load
  begin
    risky
  rescue => e
  end
  cfg = parse(raw) rescue nil
end
EOF
)"
arm "rb-BAD empty rescue is reported" 1 "RB-EMPTY-RESCUE" "${GATE}" "${d}"
arm "rb-BAD rescue nil is reported" 1 "RB-RESCUE-NIL" "${GATE}" "${d}"
d="$(fx rb-good b.rb <<'EOF'
def load
  begin
    risky
  rescue => e
    raise AuthError, e.message
  end
end
EOF
)"
arm "rb-GOOD rescue that re-raises stays silent" 0 "OK:" "${GATE}" "${d}"

d="$(fx c-bad a.c <<'EOF'
int save(void) {
    int rc = write_all();
    if (rc != 0) {}
    return 0;
}
EOF
)"
arm "c-BAD empty failure branch is reported" 1 "C-EMPTY-ERR-BRANCH" "${GATE}" "${d}"
d="$(fx c-good b.c <<'EOF'
int save(void) {
    int rc = write_all();
    if (rc != 0) {
        return -1;
    }
    return 0;
}
EOF
)"
arm "c-GOOD failure branch that returns an error stays silent" 0 "OK:" "${GATE}" "${d}"

mkdir -p "${TMP}/gf1"; cp "${REPO}/qBitTorrent-go/internal/jackettapi/auth_middleware.go" "${TMP}/gf1/"
arm "GF1 golden-FALSE real auth_middleware.go (fail-closed) is not flagged" 0 "OK: 0 fail-open hits across 1 Go" "${GATE}" "${TMP}/gf1"

d="$(fx gf2 q.rs <<'EOF'
// Err(_) => {}
fn f() -> &'static str { "if let Err(e) = x {}" }
EOF
)"
cat > "${d}/q.c" <<'EOF'
/* if (rc != 0) {} */
const char *s = "if (rc != 0) {}";
EOF
arm "GF2 golden-FALSE idioms inside comments and strings are not hits" 0 "OK:" "${GATE}" "${d}"

arm "B1 fail-closed: nonexistent root" 2 "does not exist" "${GATE}" "${TMP}/nope"

# M1 — blank the Rust/Ruby/C rule table in a COPY of the scripts.
MD="${TMP}/m1"; mkdir -p "${MD}"; cp -r "${PB}/failopen_go" "${MD}/"
cp "${GATE}" "${PB}/failopen_lang_analyzer.py" "${MD}/"
python3 - "${MD}/failopen_lang_analyzer.py" <<'EOF'
import sys, re
p = sys.argv[1]; s = open(p).read()
s2 = s.replace('RULES = {', 'RULES_ORIG = {', 1) + '\nRULES = {k: [] for k in RULES_ORIG}\n'
s2 = s2.replace('\n\nif __name__ == "__main__":', '\nRULES = {k: [] for k in RULES_ORIG}\n\nif __name__ == "__main__":', 1)
open(p, "w").write(s2)
EOF
arm "M1 mutation: Rust/Ruby/C rules blanked -> control needle unseen -> refuses (not a clean 0)" 2 "control needles failed" "${MD}/check_fail_open_unanalysed_langs.sh" "${TMP}/c-bad"

# M2 — invert the Go empty-body test in a COPY.
MD="${TMP}/m2"; mkdir -p "${MD}"; cp -r "${PB}/failopen_go" "${MD}/"
cp "${GATE}" "${PB}/failopen_lang_analyzer.py" "${MD}/"
sed -i 's/len(x.Body.List) == 0/len(x.Body.List) != 0/' "${MD}/failopen_go/main.go"
if cmp -s "${MD}/failopen_go/main.go" "${PB}/failopen_go/main.go"; then
    echo "  FAIL  M2 mutation sed did not change the Go analyser copy"; FAIL=$((FAIL+1))
else
    arm "M2 mutation: Go empty-body test inverted -> control needle unseen -> refuses" 2 "Go control needle NOT seen" "${MD}/check_fail_open_unanalysed_langs.sh" "${TMP}/go-bad"
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
