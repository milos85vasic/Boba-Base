#!/usr/bin/env bash
#
# credential_leak_audit.sh — §11.4.10 / §11.4.10.A pre-store credential-leak audit.
#
# PURPOSE
#   Scan the ENTIRE tracked repository for committed secrets / credential leaks
#   and FAIL the audit if any are found. This is the §11.4.10.A "pre-store leak
#   audit" gate made standing: before ANY secret is stored (and on every CI run),
#   the tree must be provably free of:
#     1. TRACKED secret files (`.env`, `*.token`, `*.secret.json`) — these are
#        gitignored by policy and must NEVER appear in `git ls-files`.
#     2. Hardcoded passphrase / key literals in source — specifically the
#        BobaLink reference's old FIXED passphrase `"bobalink-extension"`, plus
#        any AES key material, Bearer token literal, or `BOBA_API_TOKEN=<value>`.
#     3. A crypto call that decrypts/encrypts with a LITERAL or EMPTY passphrase
#        (a fixed-key store the user does not control). BobaLink is
#        delegate-by-default: every `decrypt(...)` / `encrypt(...)` MUST take a
#        runtime variable passphrase, never a string literal / "".
#
# USAGE
#   challenges/security/credential_leak_audit.sh
#     (no arguments; run from anywhere — it cd's to the repo root)
#
# INPUTS
#   The tracked git tree (`git ls-files`). No network, no credentials read.
#
# OUTPUTS
#   stdout: per-check progress + findings.
#   Final line "CREDENTIAL-LEAK-AUDIT: PASS" + exit 0 when clean.
#   "CREDENTIAL-LEAK-AUDIT: FAIL" + a findings list + exit 1 otherwise.
#
# SIDE-EFFECTS
#   None. Read-only; greps tracked files. Never prints a matched secret VALUE
#   (only the file path + a redaction marker), per §11.4.10 (test scripts MUST
#   NEVER print or log credentials).
#
# DEPENDENCIES
#   bash, git, grep (BRE/ERE). POSIX coreutils.
#
# CROSS-REFERENCES
#   - constitution/Constitution.md §11.4.10, §11.4.10.A (credentials handling).
#   - challenges/scripts/credential_leak_grep_challenge.sh (sibling, Go-backend
#     focused); this script is the EXTENSION-aware companion (fixed-key crypto).
#   - docs/scripts/credential_leak_audit.md (companion user guide, §11.4.18).
#
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "FAIL: not inside a git work tree ($REPO_ROOT)"
  echo "CREDENTIAL-LEAK-AUDIT: FAIL"
  exit 1
fi

# Findings accumulator. Each entry is a single human-readable line; we NEVER
# embed a matched secret value — only "<path>: <reason>".
FINDINGS=()

add_finding() {
  FINDINGS+=("$1")
}

# All tracked files (the audit universe). Use NUL-safe iteration.
mapfile -d '' -t TRACKED < <(git ls-files -z)
echo "Auditing ${#TRACKED[@]} tracked files for credential leaks…"

# Is a path PRODUCTION SOURCE we own? Source-code leak checks (fixed passphrase,
# fixed-key crypto, AES/Bearer literal, BOBA_API_TOKEN value) apply HERE — not to
# docs/ (which legitimately DESCRIBE the reference's removed fixed-key defect),
# not to security TESTS (which assert that defect is ABSENT and therefore must
# name the literal), and not to docs/research/** (vendored reference material).
is_production_source() {
  case "$1" in
    extension/src/*) return 0 ;;
    download-proxy/src/*) return 0 ;;
    qBitTorrent-go/*) [[ "$1" == *_test.go ]] && return 1; return 0 ;;
    plugins/*.py) return 0 ;;
    webui-bridge.py) return 0 ;;
    *) return 1 ;;
  esac
}

# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — no TRACKED secret files (.env / *.token / *.secret.json)
#           ('.env.example' placeholders are explicitly allowed.)
# ─────────────────────────────────────────────────────────────────────────────
echo "→ [1/5] tracked secret-file check (.env / *.token / *.secret.json)…"
for f in "${TRACKED[@]}"; do
  base="$(basename "$f")"
  case "$base" in
    .env.example|*.env.example) continue ;;
    .env|*.env) add_finding "$f: TRACKED .env file (must be gitignored)" ;;
  esac
  case "$base" in
    *.token)        add_finding "$f: TRACKED *.token file (must be gitignored)" ;;
    *.secret.json)  add_finding "$f: TRACKED *.secret.json file (must be gitignored)" ;;
  esac
done

# Helper: grep a literal pattern across tracked text files, list matching paths.
# Binary files are skipped (-I). Case-insensitive where noted by caller.
grep_tracked_paths() {
  # $1 = ERE pattern, $2 = "i" for case-insensitive (optional)
  local pattern="$1" ci="${2:-}"
  local flags=(-I -l -E)
  [ "$ci" = "i" ] && flags+=(-i)
  # NUL-list tracked paths into grep; tolerate "no match" (grep exit 1).
  git ls-files -z | xargs -0 grep "${flags[@]}" -- "$pattern" 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — no FIXED-passphrase literal (reference's old "bobalink-extension")
# ─────────────────────────────────────────────────────────────────────────────
echo "→ [2/5] fixed-passphrase literal check ('bobalink-extension') in production source…"
# The reference shipped a FIXED passphrase literal "bobalink-extension"; BobaLink
# REMOVED it (delegate-by-default). Docs that DESCRIBE the removed defect, and the
# security tests that ASSERT its absence, legitimately contain the string — so the
# check is scoped to OWNED PRODUCTION SOURCE only (is_production_source). A real
# regression re-introducing the literal into extension/src/ FAILs here.
SELF_REL="challenges/security/credential_leak_audit.sh"
DOC_REL="docs/scripts/credential_leak_audit.md"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  is_production_source "$f" || continue
  add_finding "$f: fixed-passphrase literal 'bobalink-extension' present"
done < <(grep_tracked_paths '"bobalink-extension"')

# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — no fixed-key crypto: decrypt(/encrypt( with a LITERAL/EMPTY passphrase
# ─────────────────────────────────────────────────────────────────────────────
echo "→ [3/5] fixed-key crypto check (decrypt/encrypt with literal/empty key)…"
# Match an actual call whose SECOND argument is a string literal or empty string,
# e.g.  decrypt(bundle, "secret")  |  encrypt(tok, '')  |  decrypt(x, "")
# A variable passphrase (decrypt(bundle, passphrase)) is the SAFE, expected form.
# Comment / JSDoc lines (the crypto module's `@example` blocks legitimately show
# `encrypt("plain", "user-passphrase")`) are EXCLUDED via grep -v on `*`-comment
# and `//`-comment leading whitespace — we only flag real executable call sites.
LITERAL_KEY_ERE='(decrypt|encrypt)\([^,)]+,[[:space:]]*("[^"]*"|'"'"'[^'"'"']*'"'"')[[:space:]]*[,)]'
COMMENT_ERE='^[[:space:]]*(\*|//|#)'
while IFS= read -r f; do
  [ -z "$f" ] && continue
  is_production_source "$f" || continue
  # Re-scan the file for a NON-COMMENT line matching the literal-key call.
  if grep -I -E -- "$LITERAL_KEY_ERE" "$f" 2>/dev/null \
       | grep -vE "$COMMENT_ERE" >/dev/null 2>&1; then
    add_finding "$f: crypto call with a LITERAL/EMPTY passphrase (fixed key)"
  fi
done < <(
  git ls-files -z -- 'extension/src/**/*.ts' 'extension/src/*.ts' \
    | xargs -0 grep -I -l -E -- "$LITERAL_KEY_ERE" 2>/dev/null || true
)

# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — no AES key material / hardcoded Bearer literal in tracked source
# ─────────────────────────────────────────────────────────────────────────────
echo "→ [4/5] AES-key / Bearer-literal check…"
# A 64-hex AES-256 key literal assigned to a key-ish identifier.
AES_ERE='(aes[_-]?key|encryption[_-]?key|secret[_-]?key)["'"'"' ]*[:=][[:space:]]*["'"'"'][0-9a-fA-F]{32,}["'"'"']'
while IFS= read -r f; do
  [ -z "$f" ] && continue
  is_production_source "$f" || continue
  add_finding "$f: hardcoded AES/encryption key literal"
done < <(grep_tracked_paths "$AES_ERE" i)

# A hardcoded "Authorization: Bearer <token>" / Bearer "<literal>" in source.
# Scoped to production source — docs/research/** reference material legitimately
# shows example Bearer headers and is not Boba's shipped code.
BEARER_ERE='[Bb]earer[[:space:]]+[A-Za-z0-9._~+/-]{16,}={0,2}'
while IFS= read -r f; do
  [ -z "$f" ] && continue
  is_production_source "$f" || continue
  add_finding "$f: hardcoded Bearer token literal"
done < <(grep_tracked_paths "$BEARER_ERE")

# ─────────────────────────────────────────────────────────────────────────────
# Check 5 — no BOBA_API_TOKEN=<value> committed (env assignment with a value)
# ─────────────────────────────────────────────────────────────────────────────
echo "→ [5/5] BOBA_API_TOKEN value check…"
# Flag an assignment that carries a non-empty, non-placeholder value.
# Allowed (placeholders): empty, <...>, your-..., changeme, xxx, example.
BOBA_TOKEN_ERE='BOBA_API_TOKEN[[:space:]]*=[[:space:]]*["'"'"']?[A-Za-z0-9._~+/-]{8,}'
while IFS= read -r f; do
  [ -z "$f" ] && continue
  base="$(basename "$f")"
  case "$base" in .env.example|*.env.example) continue ;; esac
  # docs/research/** vendored reference material is not Boba's shipped config;
  # a real committed token in .env / a tracked config still FAILs (check 1 +
  # the value inspection below). Skip only the vendored reference corpus.
  case "$f" in docs/research/*) continue ;; esac
  # Re-grep the file to inspect the value; skip obvious placeholders.
  while IFS= read -r line; do
    val="${line#*=}"
    val="${val//[\"\' ]/}"
    case "$val" in
      ""|\<*|your-*|YOUR-*|changeme|CHANGEME|example|EXAMPLE|xxx*|XXX*|placeholder*) continue ;;
    esac
    add_finding "$f: BOBA_API_TOKEN assigned a concrete value (redacted)"
    break
  done < <(grep -I -E -- "$BOBA_TOKEN_ERE" "$f" 2>/dev/null || true)
done < <(grep_tracked_paths "$BOBA_TOKEN_ERE")

# ─────────────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────────────
echo
if [ "${#FINDINGS[@]}" -eq 0 ]; then
  echo "CREDENTIAL-LEAK-AUDIT: PASS"
  exit 0
fi

echo "Findings (${#FINDINGS[@]}):"
for finding in "${FINDINGS[@]}"; do
  echo "  - $finding"
done
echo "CREDENTIAL-LEAK-AUDIT: FAIL"
exit 1
