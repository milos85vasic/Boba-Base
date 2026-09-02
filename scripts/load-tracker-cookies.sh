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
#   4  .env write aborted — the validated rewrite failed a safety
#      invariant (grep error, line-count, or key-set). .env was left
#      byte-for-byte UNCHANGED; nothing was lost. Ranks above 1 and 2
#      because BOBA_MASTER_KEY lives in .env (CLAUDE.md: "Loss = total
#      credential loss") and the operator must see this first.

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
#
# ROOT CAUSE (fixed 2026-09-01). The filter step used to read
#     grep -vE ... "$ENV_FILE" > "$tmp" 2>/dev/null || true
# then unconditionally `mv -f "$tmp" "$ENV_FILE"`. `|| true` swallows EVERY
# grep failure — unreadable source, ENOSPC on the write, a malformed pattern
# (grep exit 2) — and `2>/dev/null` hides the reason. On any of those the
# temp file is empty or truncated and the `mv` publishes it OVER .env.
# .env holds BOBA_MASTER_KEY, and per CLAUDE.md "Loss = total credential
# loss": the AES-256-GCM key for `tracker_credentials` in config/boba.db is
# unrecoverable, so this single unchecked `|| true` could destroy every
# stored credential in the system.
#
# The rewrite is now VALIDATED BEFORE it is published, not merely atomic:
#   (a) grep's real exit status is honoured — 0 (lines kept) and 1 (all lines
#       matched / empty source) are the only legal outcomes; >=2 is an error
#       and ABORTS. Its stderr is captured, and any diagnostic ABORTS too.
#   (b) LINE COUNT invariant: the temp file must hold exactly
#       (original lines - lines removed for this var) + 1 appended line.
#       A truncated or empty temp file cannot satisfy it.
#   (c) KEY-NAME invariant: the set of variable names in the temp file must
#       equal the original set with $var guaranteed present. This catches
#       content loss a line count alone would miss (e.g. a partial write
#       that happens to land on the right number of lines). Names only are
#       compared and printed — values NEVER leave this function (11.4.10).
# Any failed check removes the temp file, leaves .env byte-for-byte
# untouched, prints a loud diagnostic, and returns 1 so the caller can
# record it and exit non-zero. A backup alone was rejected as the fix: a
# backup nobody verifies is not a safeguard.
#
_write_env_var() {
    local var="$1"
    local value="$2"

    local tmp
    tmp="$(mktemp "${ENV_FILE}.load-tracker-cookies.XXXXXX")"
    chmod 600 "$tmp"

    local err
    err="$(mktemp)"

    # Abort helper — never publishes $tmp, never touches $ENV_FILE.
    _abort_write() {
        echo "[load-tracker-cookies] FATAL: refusing to rewrite $ENV_FILE — $1" >&2
        echo "[load-tracker-cookies]        $ENV_FILE left UNCHANGED. No data was lost." >&2
        if [[ -s "$err" ]]; then
            echo "[load-tracker-cookies]        scanner diagnostics:" >&2
            sed 's/^/[load-tracker-cookies]          /' "$err" >&2
        fi
        rm -f "$tmp" "$err"
        unset -f _abort_write
        return 1
    }

    local orig_lines=0 kept_lines=0 removed=0 rc=0
    local -a orig_keys=() tmp_keys=()

    if [[ -f "$ENV_FILE" ]]; then
        [[ -r "$ENV_FILE" ]] || { _abort_write "$ENV_FILE exists but is not readable"; return 1; }

        # awk counts a final line lacking its newline as a record; wc -l does not.
        orig_lines="$(awk 'END{print NR+0}' "$ENV_FILE")"
        mapfile -t orig_keys < <(sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)=.*/\2/p' "$ENV_FILE" | sort -u)

        # Reproduce every line except the target var, then append the new one.
        set +e
        grep -vE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" > "$tmp" 2>"$err"
        rc=$?
        set -e
        # 0 = lines kept, 1 = nothing kept (legal: file empty or only the var).
        # >=2 = grep itself failed: THE case the old `|| true` erased.
        if [[ $rc -ge 2 ]]; then
            _abort_write "grep exited $rc while filtering $ENV_FILE"
            return 1
        fi
        if [[ -s "$err" ]]; then
            _abort_write "grep emitted diagnostics while filtering $ENV_FILE"
            return 1
        fi

        kept_lines="$(awk 'END{print NR+0}' "$tmp")"
        removed="$(grep -cE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" || true)"
        if [[ "$kept_lines" -ne $(( orig_lines - removed )) ]]; then
            _abort_write "line-count invariant violated: kept=$kept_lines expected=$(( orig_lines - removed )) (original=$orig_lines, removed=$removed for ${var})"
            return 1
        fi
    fi

    # Single-quoted value — cookie headers contain `=` and `;` freely,
    # never single quotes (cookie tokens are RFC-6265 token+value with
    # apostrophes forbidden in the token set). The extractor never
    # emits values containing `'`, so single-quote wrapping is safe.
    if ! printf "%s='%s'\n" "$var" "$value" >> "$tmp" 2>"$err"; then
        _abort_write "could not append ${var} to the temp file (disk full?)"
        return 1
    fi

    # Post-append invariants, checked against the file that is about to
    # become .env — not against what we intended to write.
    if [[ "$(awk 'END{print NR+0}' "$tmp")" -ne $(( kept_lines + 1 )) ]]; then
        _abort_write "post-append line count is $(awk 'END{print NR+0}' "$tmp"), expected $(( kept_lines + 1 ))"
        return 1
    fi

    mapfile -t tmp_keys < <(sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)=.*/\2/p' "$tmp" | sort -u)
    local expected_keys actual_keys
    expected_keys="$(printf '%s\n' "${orig_keys[@]+"${orig_keys[@]}"}" "$var" | sed '/^$/d' | sort -u)"
    actual_keys="$(printf '%s\n' "${tmp_keys[@]+"${tmp_keys[@]}"}" | sed '/^$/d' | sort -u)"
    if [[ "$expected_keys" != "$actual_keys" ]]; then
        echo "[load-tracker-cookies] key-set diff (NAMES only, never values):" >&2
        diff <(printf '%s\n' "$expected_keys") <(printf '%s\n' "$actual_keys") >&2 || true
        _abort_write "key-set invariant violated: the rewrite would drop or invent variables in $ENV_FILE"
        return 1
    fi

    sync
    if ! mv -f "$tmp" "$ENV_FILE"; then
        _abort_write "atomic rename onto $ENV_FILE failed"
        return 1
    fi
    chmod 600 "$ENV_FILE"
    rm -f "$err"
    unset -f _abort_write
    return 0
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
WRITE_ERR=0

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

    if ! _write_env_var "$var" "$header"; then
        _info "$tracker: WRITE ABORTED — $ENV_FILE left untouched (see FATAL above)"
        WRITE_ERR=$((WRITE_ERR+1))
        continue
    fi
    _info "$tracker: $(printf '%s' "$header" | tr ';' '\n' | grep -c '=') cookie(s) — LOADED into .env as $var"
    LOADED=$((LOADED+1))
done

_info "summary: loaded=$LOADED unchanged=$UNCHANGED absent=$ABSENT blocked=$BLOCKED parse_err=$PARSE_ERR write_err=$WRITE_ERR (dir=$COOKIE_DIR)"

# Exit rank: write aborts > leak blocks > parse errs > success.
# A write abort ranks highest: it means .env could not be safely rewritten,
# which the operator must see before anything else (BOBA_MASTER_KEY lives there).
if [[ $WRITE_ERR -gt 0 ]]; then exit 4; fi
if [[ $BLOCKED -gt 0 ]]; then exit 1; fi
if [[ $PARSE_ERR -gt 0 ]]; then exit 2; fi
exit 0
