#!/usr/bin/env bash
# scripts/extract-tracker-cookies.sh — extract ONLY a single tracker's own-domain
# cookies from a Netscape `cookies.txt` browser export, emitting the
# `name=value; name=value` header string that the merge proxy's *_COOKIES env
# vars consume.
#
# §11.4.10 PRIVACY GUARD: a full browser `cookies.txt` export contains the
# operator's ENTIRE cookie jar (banking, shopping, email, payments, …). This
# tool emits cookies for the requested tracker's OWN domain ONLY — every other
# site's cookies are discarded and never printed, never stored. It writes the
# header string to stdout for the caller to redirect into a chmod-600 .env;
# it logs only cookie NAMES + counts to stderr (never values).
#
# Usage:  extract-tracker-cookies.sh <cookies.txt> <nnmclub|rutracker>
#   NNMCLUB_COOKIES="$(extract-tracker-cookies.sh ~/Downloads/nnmclub.txt nnmclub)"
# Inputs: a Netscape cookies.txt (tab-separated: domain flag path secure expiry name value).
# Output: stdout = "name=value; ..." for the tracker domain; stderr = names+count.
# Exit:   0 ok (required session cookie present); 2 = required session cookie absent.
set -euo pipefail

FILE="${1:?usage: extract-tracker-cookies.sh <cookies.txt> <nnmclub|rutracker>}"
TRACKER="${2:?usage: extract-tracker-cookies.sh <cookies.txt> <nnmclub|rutracker>}"
[[ -f "$FILE" ]] || { echo "[extract] no such file: $FILE" >&2; exit 1; }

# Per-tracker CANONICAL own-domain + the session cookie that proves login.
# Canonical domain only (matches the proxy's base_url default) so a mirror's
# (.net/.me) divergent session value can't be sent to the canonical host.
case "$TRACKER" in
  nnmclub)   DOMAIN_RE='nnmclub\.to$';   REQUIRED='phpbb2mysql_4_sid' ;;
  rutracker) DOMAIN_RE='rutracker\.org$'; REQUIRED='bb_session' ;;
  *) echo "[extract] unknown tracker: $TRACKER (want nnmclub|rutracker)" >&2; exit 1 ;;
esac

# Build the header string from ONLY rows whose cookie-domain (field 1, leading
# dot stripped) matches the canonical tracker domain. Dedup by cookie NAME
# (first occurrence wins) so no duplicate name=value pair reaches the server.
# Values never hit stderr.
HEADER="$(awk -F'\t' -v re="$DOMAIN_RE" '
  NF>=7 {
    d=$1; sub(/^\./,"",d);
    if (tolower(d) ~ re && !(($6) in seen)) {
      seen[$6]=1;
      if (out != "") out = out "; ";
      out = out $6 "=" $7;
    }
  }
  END { printf "%s", out }
' "$FILE")"

# §11.4.10: log names + count ONLY (mask values).
NAMES="$(printf '%s' "$HEADER" | tr ';' '\n' | sed -E 's/^[[:space:]]*([^=]+)=.*/\1/' | sort -u | tr '\n' ' ')"
N="$(printf '%s' "$HEADER" | tr ';' '\n' | grep -c '=' || true)"
echo "[extract] $TRACKER: $N cookie(s) for own domain — names: ${NAMES:-<none>}" >&2

if ! printf '%s' "$HEADER" | grep -q "(^|; )${REQUIRED}="; then
  # grep -E for the alternation/anchor
  if ! printf '%s' "$HEADER" | grep -Eq "(^|; )${REQUIRED}="; then
    echo "[extract] FAIL: required session cookie '${REQUIRED}' not present — the export was not from a logged-in ${TRACKER} session." >&2
    exit 2
  fi
fi
printf '%s' "$HEADER"
