#!/usr/bin/env bash
# scripts/load-tracker-cookies.sh — auto-load per-tracker Netscape cookies.txt
# files from a well-known directory (default $HOME/Downloads) and write the
# resulting cookie-header strings into the repo's .env as <TRACKER>_COOKIES=...
# so containers pick fresh session cookies up on the next up/restart.
#
# ─── OPERATOR MANDATE ANCHOR (2026-08-15, verbatim) ───────────────
# "System seeks for cookies txt files in naming convention
#  cookies_rutracker.txt -- cookies_TRACKER.txt and loads data from them
#  for trackers which need them. Let's use by default host machine home
#  directory -> Downloads folder. So we MUST support env. vars and use of
#  cookies files."
#
# ─── PURPOSE ───────────────────────────────────────────────────────
# One primitive, one convention:
#   ${TRACKER_COOKIE_DIR:-$HOME/Downloads}/cookies_<tracker>.txt
#     (tracker = lowercase; today: rutracker | nnmclub | rutor | kinozal |
#      iptorrents)
# For every file present, this script:
#   1. Delegates parsing to scripts/extract-tracker-cookies.sh (the audited
#      single-tracker extraction primitive that already strips leading
#      dots, dedups by cookie name, filters by the tracker's OWN domain,
#      and NEVER logs cookie values — §11.4.10 credentials-handling).
#   2. Runs the §11.4.10.A pre-store leak audit — every non-trivial
#      cookie VALUE is grepped against tracked files + `git log -S` on
#      HEAD; ANY hit blocks the store (never over-writes .env with a
#      value already known to have leaked; §11.4.10 rotation is the
#      operator response).
#   3. Writes the resulting `<TRACKER_UPPER>_COOKIES='<header>'` line
#      into .env ATOMICALLY (temp file + chmod 600 + rename — the same
#      §11.4.10 write-seam the DB uses); .env stays mode 0600 and
#      gitignored.
#   4. Is IDEMPOTENT — if the file's cookie-header maps to the SAME
#      value already present in .env, the script skips it (no I/O, no
#      leak-audit, so a re-run costs O(files) parse only).
#   5. NEVER logs cookie values — only the tracker name, the count of
#      cookies parsed, the cookie NAMES (never values), and file mtime.
#
# ─── USAGE ─────────────────────────────────────────────────────────
#   scripts/load-tracker-cookies.sh [--dry-run] [--dir <path>]
#                                    [--only <tracker>] [--verbose]
#                                    [-h|--help]
#
#   Flags:
#     --dry-run           report what WOULD change; touch nothing.
#     --dir <path>        override cookie source dir (default
#                         $TRACKER_COOKIE_DIR else $HOME/Downloads).
#     --only <tracker>    process a single tracker (e.g. --only rutor);
#                         may be repeated.
#     --verbose           extra progress (per-file mtime, per-cookie
#                         count). Cookie VALUES are still never printed.
#     -h|--help           print this help block.
#
#   Env vars:
#     TRACKER_COOKIE_DIR  cookie source dir; --dir wins if both set.
#     BOBA_ENV_FILE       .env path; default $REPO_ROOT/.env.
#
# ─── INPUTS ────────────────────────────────────────────────────────
#   Netscape TSV cookies.txt files at
#     <dir>/cookies_<tracker>.txt
#   for tracker in the closed tracker→domain map below (rutracker,
#   nnmclub, rutor, kinozal, iptorrents). Any other file in <dir> is
#   IGNORED — only files matching the convention are read.
#
# ─── OUTPUTS ───────────────────────────────────────────────────────
#   Mutates .env with 0..N `<TRACKER>_COOKIES='<cookie header>'` lines
#   (one per file processed). Prints per-tracker status to stderr:
#     [load-tracker-cookies] rutracker: 15 cookie(s) — LOADED
#     [load-tracker-cookies] rutor:     22 cookie(s) — LOADED
#     [load-tracker-cookies] nnmclub:   18 cookie(s) — UNCHANGED (idempotent)
#     [load-tracker-cookies] kinozal:   file absent — SKIP
#
# ─── SIDE-EFFECTS ──────────────────────────────────────────────────
#   Writes .env only. Never reads or writes anything under
#   ~/Downloads other than the cookies_<tracker>.txt files themselves.
#
# ─── DEPENDENCIES ──────────────────────────────────────────────────
#   bash 4+, coreutils, git (for the §11.4.10.A leak audit),
#   scripts/extract-tracker-cookies.sh (delegated primitive).
#
# ─── CROSS-REFERENCES ──────────────────────────────────────────────
#   scripts/extract-tracker-cookies.sh — single-tracker extraction
#   scripts/boba-svc.sh                — invokes this loader before up/restart
#   scripts/install.sh                 — invokes this loader in Stage 6
#   start.sh                           — invokes this loader before compose up
#   docs/scripts/load-tracker-cookies.md — external user guide (§11.4.18)
#   docs/guides/tracker-credentials.md   — operator manual
#   docs/FAQ.md                          — cookie-refresh FAQ entries
#   challenges/scripts/credentials_wired_challenge.sh — RED/GREEN guard
#
# ─── EXIT CODES ────────────────────────────────────────────────────
#   0  success — every applicable file was loaded, unchanged, or absent
#      (no file present at all is a legitimate outcome, not a failure).
#   1  §11.4.10.A leak-audit failure — blocked the store; abort.
#   2  parse error — a cookie file failed the extractor's own
#      required-session-cookie check.
#   3  invocation error — bad flag / missing arg / not in repo root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

EXTRACTOR="$SCRIPT_DIR/extract-tracker-cookies.sh"
ENV_FILE="${BOBA_ENV_FILE:-$REPO_ROOT/.env}"

# Closed tracker → cookie-file-name map. The name suffix is the second
# field of the convention `cookies_<tracker>.txt` (lowercase) and the
# env var is UPPER(tracker)_COOKIES. Add a new tracker by extending
# THIS map and by teaching scripts/extract-tracker-cookies.sh the same
# tracker's domain/session-cookie in its own `case` — never guess a
# tracker here that the extractor doesn't know (§11.4.6 no-guessing).
TRACKERS=(rutracker nnmclub rutor kinozal iptorrents)

# ─── flag parsing ─────────────────────────────────────────────────
DRY_RUN=0
VERBOSE=0
COOKIE_DIR="${TRACKER_COOKIE_DIR:-$HOME/Downloads}"
declare -a ONLY=()

_usage() {
    # Print the header block (usage section) as the built-in help.
    sed -n '3,88p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while (($#)); do
    case "$1" in
        --dry-run)      DRY_RUN=1; shift ;;
        --verbose|-v)   VERBOSE=1; shift ;;
        --dir)          [[ $# -ge 2 ]] || { echo "[load-tracker-cookies] --dir needs a path" >&2; exit 3; }
                        COOKIE_DIR="$2"; shift 2 ;;
        --only)         [[ $# -ge 2 ]] || { echo "[load-tracker-cookies] --only needs a tracker" >&2; exit 3; }
                        ONLY+=("$(echo "$2" | tr '[:upper:]' '[:lower:]')"); shift 2 ;;
        -h|--help)      _usage ;;
        *)              echo "[load-tracker-cookies] unknown flag: $1 (try --help)" >&2; exit 3 ;;
    esac
done

# ─── platform + repo gate ─────────────────────────────────────────
if [[ ! -x "$EXTRACTOR" ]]; then
    echo "[load-tracker-cookies] extractor missing or not executable: $EXTRACTOR" >&2
    exit 3
fi
if [[ ! -d "$COOKIE_DIR" ]]; then
    echo "[load-tracker-cookies] cookie dir does not exist: $COOKIE_DIR — nothing to do" >&2
    exit 0
fi

_info()  { echo "[load-tracker-cookies] $*" >&2; }
_debug() { [[ "$VERBOSE" -eq 1 ]] && echo "[load-tracker-cookies] $*" >&2 || true; }

# ─── §11.4.10.A leak audit ────────────────────────────────────────
# For each cookie value (length >= 8 characters, filtering out obvious
# noise like `1` / `0` / `true`), grep tracked files + `git log -S`.
# ANY hit blocks the store. Values NEVER hit stderr — we print only
# the finding's file path / commit SHA and the cookie NAME.
_leak_audit() {
    local tracker_upper="$1"
    local header="$2"

    # Split "name=value; name=value; ..." into per-cookie lines.
    local IFS=';' entries=($header) leaked=0
    for raw in "${entries[@]}"; do
        raw="${raw## }"
        raw="${raw%% }"
        local name="${raw%%=*}"
        local value="${raw#*=}"
        # Only audit non-trivial cookies.
        [[ ${#value} -ge 8 ]] || continue
        # Skip values that are common non-secret patterns (timestamps,
        # simple bools, single-digit counters) — they routinely match
        # unrelated code and waste the audit's signal.
        case "$value" in
            true|false|null|"1"|"0"|"2") continue ;;
        esac

        # (a) Tree scan — grep tracked files for the exact value.
        if git -C "$REPO_ROOT" grep -F -l -- "$value" -- ':!/.env' ':!/scripts/load-tracker-cookies.sh' 2>/dev/null | grep -q .; then
            echo "[load-tracker-cookies] LEAK-AUDIT (§11.4.10.A): cookie name='$name' for $tracker_upper appears in tracked files:" >&2
            git -C "$REPO_ROOT" grep -F -l -- "$value" -- ':!/.env' ':!/scripts/load-tracker-cookies.sh' 2>/dev/null | sed 's/^/    /' >&2
            leaked=1
        fi

        # (b) History scan — git log -S on the exact value. Bounded to
        # last 1000 commits to keep the audit under a second on large
        # repos; a genuine leak is caught by (a) already, this is the
        # historical-forensics backstop.
        if git -C "$REPO_ROOT" log -n 1000 -S"$value" --pretty=format:%H -- 2>/dev/null | grep -q .; then
            echo "[load-tracker-cookies] LEAK-AUDIT (§11.4.10.A): cookie name='$name' for $tracker_upper appears in recent git history (first 3 commits):" >&2
            git -C "$REPO_ROOT" log -n 1000 -S"$value" --pretty=format:'    %h %s' -- 2>/dev/null | head -3 >&2
            leaked=1
        fi
    done

    if [[ $leaked -eq 1 ]]; then
        echo "[load-tracker-cookies] BLOCKED store for $tracker_upper — rotate the cookie(s) in your browser and re-export cookies_$(echo "$tracker_upper" | tr '[:upper:]' '[:lower:]').txt (§11.4.10 rotation)." >&2
        return 1
    fi
    return 0
}

# ─── atomic .env write ────────────────────────────────────────────
# Read .env, replace-or-append the given VAR=... line, write via
# temp+chmod-600+rename. Preserves ordering + comments of existing
# lines. Never leaves .env world-readable, never leaves it in a
# half-written state.
_write_env_var() {
    local var="$1"
    local value="$2"

    local tmp
    tmp="$(mktemp "${ENV_FILE}.load-tracker-cookies.XXXXXX")"
    chmod 600 "$tmp"

    if [[ -f "$ENV_FILE" ]]; then
        # Reproduce every line except the target var, then append the new one.
        grep -vE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" > "$tmp" 2>/dev/null || true
    fi
    # Single-quoted value — cookie headers contain `=` and `;` freely,
    # never single quotes (cookie tokens are RFC-6265 token+value with
    # apostrophes forbidden in the token set). The extractor never
    # emits values containing `'`, so single-quote wrapping is safe.
    printf "%s='%s'\n" "$var" "$value" >> "$tmp"
    sync
    mv -f "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

# ─── read existing var value from .env ────────────────────────────
# Returns the value with surrounding single/double quotes stripped.
# Empty string if the var is absent.
_read_env_var() {
    local var="$1"
    [[ -f "$ENV_FILE" ]] || { echo ""; return 0; }
    local line
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" | tail -1 || true)"
    [[ -n "$line" ]] || { echo ""; return 0; }
    local val="${line#*=}"
    val="${val#\"}"; val="${val%\"}"
    val="${val#\'}"; val="${val%\'}"
    echo "$val"
}

# ─── main loop ────────────────────────────────────────────────────
LOADED=0
UNCHANGED=0
ABSENT=0
BLOCKED=0
PARSE_ERR=0

# Build the effective tracker set — either --only-restricted or all.
declare -a EFFECTIVE=()
if [[ ${#ONLY[@]} -gt 0 ]]; then
    for w in "${ONLY[@]}"; do
        found=0
        for t in "${TRACKERS[@]}"; do
            if [[ "$w" == "$t" ]]; then
                EFFECTIVE+=("$t"); found=1; break
            fi
        done
        [[ $found -eq 1 ]] || _info "--only $w — not in the tracker map, ignoring"
    done
else
    EFFECTIVE=("${TRACKERS[@]}")
fi

for tracker in "${EFFECTIVE[@]}"; do
    file="$COOKIE_DIR/cookies_${tracker}.txt"
    upper="$(echo "$tracker" | tr '[:lower:]' '[:upper:]')"
    var="${upper}_COOKIES"

    if [[ ! -f "$file" ]]; then
        _info "$tracker: file absent ($file) — SKIP"
        ABSENT=$((ABSENT+1))
        continue
    fi

    _debug "$tracker: $file (mtime: $(stat -c '%y' "$file" 2>/dev/null | cut -d. -f1))"

    # Delegate to the audited extraction primitive. It writes the
    # header to stdout and the summary (count + cookie NAMES) to
    # stderr. NEVER redirect the summary elsewhere — the operator
    # needs to see it.
    #
    # The extractor is per-tracker; it knows nnmclub/rutracker/
    # iptorrents (all three are private trackers with a load-bearing
    # required session cookie the extractor validates). For trackers
    # it does not know (rutor, kinozal), do a domain-scoped inline
    # extraction using the same discipline — never a value log.
    header=""
    ex_rc=0
    if [[ "$tracker" == "nnmclub" || "$tracker" == "rutracker" || "$tracker" == "iptorrents" ]]; then
        set +e
        header="$("$EXTRACTOR" "$file" "$tracker" 2>&2)"
        ex_rc=$?
        set -e
    else
        # Inline domain scope for trackers the extractor doesn't teach.
        # Uses the SAME awk shape as extract-tracker-cookies.sh —
        # dedup-by-name, leading-dot stripped, case-insensitive
        # substring match on the tracker name (matches .rutor.is,
        # www.rutor.is, .kinozal.guru, .kinozal.tv, etc.).
        header="$(awk -F'\t' -v k="$tracker" '
            NF>=7 {
                d=$1; sub(/^\./,"",d);
                if (tolower(d) ~ tolower(k) && !(($6) in seen)) {
                    seen[$6]=1;
                    if (out != "") out = out "; ";
                    out = out $6 "=" $7;
                }
            }
            END { printf "%s", out }
        ' "$file")"
        names="$(printf '%s' "$header" | tr ';' '\n' | sed -E 's/^[[:space:]]*([^=]+)=.*/\1/' | sort -u | tr '\n' ' ')"
        n="$(printf '%s' "$header" | tr ';' '\n' | grep -c '=' || true)"
        _info "$tracker: $n cookie(s) for own domain — names: ${names:-<none>}"
        # For public trackers (rutor) an empty header is legitimate
        # (no session needed); we still write it (empty value) so the
        # env-var slot exists.
        ex_rc=0
    fi

    if [[ $ex_rc -eq 2 ]]; then
        _info "$tracker: PARSE — required session cookie missing; cookies_$tracker.txt was not exported from a logged-in session"
        PARSE_ERR=$((PARSE_ERR+1))
        continue
    fi
    if [[ $ex_rc -ne 0 ]]; then
        _info "$tracker: extractor exit=$ex_rc — skipping"
        PARSE_ERR=$((PARSE_ERR+1))
        continue
    fi

    # Idempotency: compare to current value.
    current="$(_read_env_var "$var")"
    if [[ "$current" == "$header" ]]; then
        _info "$tracker: $(printf '%s' "$header" | tr ';' '\n' | grep -c '=') cookie(s) — UNCHANGED (idempotent)"
        UNCHANGED=$((UNCHANGED+1))
        continue
    fi

    # §11.4.10.A leak audit — MUST pass before we write.
    if ! _leak_audit "$upper" "$header"; then
        BLOCKED=$((BLOCKED+1))
        continue
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        _info "$tracker: WOULD LOAD ($(printf '%s' "$header" | tr ';' '\n' | grep -c '=') cookie(s)) into $ENV_FILE as $var — DRY-RUN (no write)"
        LOADED=$((LOADED+1))
        continue
    fi

    _write_env_var "$var" "$header"
    _info "$tracker: $(printf '%s' "$header" | tr ';' '\n' | grep -c '=') cookie(s) — LOADED into .env as $var"
    LOADED=$((LOADED+1))
done

_info "summary: loaded=$LOADED unchanged=$UNCHANGED absent=$ABSENT blocked=$BLOCKED parse_err=$PARSE_ERR (dir=$COOKIE_DIR)"

# Exit rank: leak blocks > parse errs > success (per header contract).
if [[ $BLOCKED -gt 0 ]]; then exit 1; fi
if [[ $PARSE_ERR -gt 0 ]]; then exit 2; fi
exit 0
