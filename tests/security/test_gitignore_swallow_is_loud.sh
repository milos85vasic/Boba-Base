#!/usr/bin/env bash
#
# Purpose : BOB-212 RED (§11.4.115 / §11.4.224) — prove that authoring a NEW
#           credential-named SOURCE file under a first-party source root is
#           SILENTLY swallowed by .gitignore, and that NO signal distinguishes
#           "file was swallowed" from "no file was authored" (§11.4.201(6)
#           FALSE-NULL in the commit path itself).
#
#           Acceptance (BOB-212): such a file either commits normally OR
#           produces a LOUD refusal naming the blocking rule — never silence.
#           This test asserts that DISJUNCTION, so it is fix-direction-agnostic:
#           it flips GREEN under a narrowed glob (direction a) OR under a
#           swallow-guard (direction b). The direction stays an operator
#           decision (§11.4.66); the test does not prejudge it.
#
# Usage   : bash tests/security/test_gitignore_swallow_is_loud.sh
#           RED_MODE=1 bash tests/security/test_gitignore_swallow_is_loud.sh
#
# Inputs  : the REPOSITORY'S OWN .gitignore (copied verbatim into a scratch
#           git tree — real rules, no mock, §11.4.27). Nothing in the real
#           repository is created, staged, added, or modified.
# Outputs : human-readable verdict on stdout.
# Exit    : 0  all assertions hold (guard mode: the swallow is LOUD — fixed)
#           1  RED assertion failed (guard mode: the swallow is SILENT — defect present)
#           2  INSTRUMENT BROKEN or SECRET LEAK — the control needle failed, or
#              real secret material stopped being ignored. Distinct from 1 so a
#              blind harness can never be read as "defect present" (§11.4.201(1),
#              §11.4.1: a FAIL for a script-internal reason is a FAIL-bluff).
#
# Polarity (§11.4.115): RED_MODE=1 asserts the DEFECT IS PRESENT (exit 0 today
#           = reproduction captured). Default (RED_MODE=0) is guard mode:
#           exit 1 today, exit 0 once the swallow is loud.
#
# Side-effects : creates and removes one mktemp -d scratch tree. No network,
#           no container, no signal delivery, no host power-state change.
# Depends : bash, git, mktemp.
# Refs    : BOB-212; §11.4.10 (credentials never reach git — the golden-FALSE),
#           §11.4.201(1)/(6) (false-positive refusal + false-null),
#           §11.4.115 (RED on the broken artifact + polarity switch),
#           §11.4.224 (test-first), §11.4.83 (evidence under docs/qa/).
# Doc     : docs/scripts/test_gitignore_swallow_is_loud.md
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RED_MODE="${RED_MODE:-0}"

# The guard that direction (b) would add. Referenced, deliberately NOT created
# by this test — its absence is part of what the RED proves.
SWALLOW_GUARD="${SWALLOW_GUARD:-$REPO_ROOT/scripts/pre_build/check_gitignore_swallow.sh}"

# The file under test: a plausible NEW credential-named source file under a
# first-party source root. This is the exact shape the BOB-204 stream lost.
SUBJECT_REL="qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go"
# §11.4.201(1) control needle: same root, same extension, NO credential word.
CONTROL_REL="qBitTorrent-go/internal/jackettapi/zzz_probe_failclosed_test.go"

# Golden-FALSE corpus: real secret-bearing material. MUST stay ignored today
# AND after any fix. Without this, deleting the glob would look "green".
SECRETS=(
  ".env"
  "config/.env"
  "production.env"
  "secrets/api.key"
  "server.pem"
  "client.p12"
  "keystore.jks"
  "download-proxy/qbittorrent_creds.json"
  "config/aws_credentials.json"
  "tracker_credentials.yaml"
  "db_credentials.enc"
  "cookies_rutracker.txt"
  "RUTRACKER_session.txt"
  "my_password.txt"
  "service_credentials"
)

fail_red=0; fail_hard=0
ok()   { printf '  [ok]     %s\n' "$*"; }
red()  { printf '  [RED]    %s\n' "$*"; fail_red=1; }
hard() { printf '  [BROKEN] %s\n' "$*"; fail_hard=1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob212_red.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# ---------------------------------------------------------------- scratch tree
build_tree() {  # $1 = "with-subject" | "without-subject"
  local dir="$WORK/$1"
  rm -rf "$dir"; mkdir -p "$dir"
  git -C "$dir" init -q .
  git -C "$dir" config user.email bob212@local
  git -C "$dir" config user.name  bob212
  cp "$REPO_ROOT/.gitignore" "$dir/.gitignore"          # the REAL rules
  mkdir -p "$dir/$(dirname "$CONTROL_REL")"
  printf 'package jackettapi // control needle\n' > "$dir/$CONTROL_REL"
  if [ "$1" = "with-subject" ]; then
    mkdir -p "$dir/$(dirname "$SUBJECT_REL")"
    printf 'package jackettapi // BOB-212 subject: a real authored source file\n' \
      > "$dir/$SUBJECT_REL"
  fi
  printf '%s' "$dir"
}

status_of() { git -C "$1" status --porcelain --untracked-files=all; }

echo "BOB-212 RED — .gitignore silent-swallow of credential-named source files"
echo "repo: $REPO_ROOT"
echo "mode: $([ "$RED_MODE" = 1 ] && echo 'RED_MODE=1 (assert defect PRESENT)' || echo 'guard (assert swallow is LOUD)')"
echo

WITH="$(build_tree with-subject)"
WITHOUT="$(build_tree without-subject)"

# ============================================================ CONTROL NEEDLE ==
echo "-- control needle (§11.4.201(7)(b)): harness can see a visible new file --"
if status_of "$WITH" | grep -qF -- "$CONTROL_REL"; then
  ok "non-credential-named sibling IS visible in git status — harness proven seeing"
else
  hard "control needle ABSENT from git status — harness is blind; every zero below is void"
fi
echo

# ================================================== A1: swallowed, no signal ==
echo "-- A1: is the credential-named source file visible to the commit path? --"
subject_visible=0
if status_of "$WITH" | grep -qF -- "$SUBJECT_REL"; then subject_visible=1; fi
rule="$(printf '%s\n' "$SUBJECT_REL" | git -C "$WITH" check-ignore --no-index -v --stdin || true)"
if [ "$subject_visible" = 1 ]; then
  ok "file is visible in git status (commits normally) — acceptance limb 1 met"
else
  printf '  ..       file is INVISIBLE to git status; blocking rule: %s\n' "${rule:-<none>}"
fi

# ================================== A2: does a LOUD refusal exist instead? ====
echo "-- A2: does a swallow-guard exist and refuse loudly, naming rule + file? --"
guard_loud=0
if [ -x "$SWALLOW_GUARD" ]; then
  gout="$("$SWALLOW_GUARD" "$WITH" 2>&1 || true)"
  grc=$( "$SWALLOW_GUARD" "$WITH" >/dev/null 2>&1; printf '%s' "$?" )
  if [ "$grc" -ne 0 ] \
     && printf '%s' "$gout" | grep -qF -- "$SUBJECT_REL" \
     && printf '%s' "$gout" | grep -qE 'gitignore:[0-9]+'; then
    guard_loud=1
    ok "guard refused (exit $grc) and named both the file and the .gitignore rule"
  else
    printf '  ..       guard present but did not refuse loudly (exit %s)\n' "$grc"
  fi
else
  printf '  ..       no swallow-guard at %s\n' "$SWALLOW_GUARD"
fi
echo

# ===================================== A3: THE SILENCE — the §11.4.201(6) null =
echo "-- A3: does ANY signal distinguish 'swallowed' from 'never authored'? --"
sa="$(status_of "$WITH")"; sb="$(status_of "$WITHOUT")"
if [ "$sa" = "$sb" ]; then
  printf '  ..       git status is BYTE-IDENTICAL with and without the file:\n'
  printf '  ..         world A (file authored)   -> %s\n' "$(printf '%s' "$sa" | md5sum | cut -c1-16)"
  printf '  ..         world B (file never made) -> %s\n' "$(printf '%s' "$sb" | md5sum | cut -c1-16)"
  silence=1
else
  ok "git status differs between the two worlds — the author gets a signal"
  silence=0
fi
echo

# ============================================== VERDICT on the acceptance rule =
echo "-- ACCEPTANCE (BOB-212): commits normally OR loud refusal — never silence --"
if [ "$subject_visible" = 1 ] || [ "$guard_loud" = 1 ]; then
  ok "a signal reaches the author"
else
  red "NEITHER limb holds: the file is invisible AND nothing refuses loudly."
  red "  swallowed by: ${rule:-<none>}"
  red "  an author who writes this file gets NO indication it did not land."
fi
if [ "$silence" = 1 ] && [ "$guard_loud" = 0 ]; then
  red "FALSE-NULL CONFIRMED (§11.4.201(6)): 'file swallowed' and 'no file authored'"
  red "  are indistinguishable to the commit path. A blind instrument and a clean"
  red "  tree return the identical quiet zero."
fi
echo

# =========================================================== GOLDEN-FALSE =====
echo "-- GOLDEN-FALSE (§11.4.201(1)/§11.4.10): real secrets MUST stay ignored --"
leaks=0
for s in "${SECRETS[@]}"; do
  mkdir -p "$WITH/$(dirname "$s")" 2>/dev/null || true
  printf 'SECRET-PLACEHOLDER\n' > "$WITH/$s"
  if printf '%s\n' "$s" | git -C "$WITH" check-ignore --no-index --stdin >/dev/null 2>&1; then
    :
  else
    hard "LEAK: '$s' is NOT ignored — a fix that admits secret material is strictly"
    hard "      worse than the defect it closes (§11.4.10)."
    leaks=$((leaks + 1))
  fi
done
if [ "$leaks" = 0 ]; then
  ok "all ${#SECRETS[@]} secret-bearing shapes remain ignored"
fi
# and none of them may appear in git status either
if status_of "$WITH" | grep -qE '(\.env|\.pem|\.key|\.p12|\.jks|_creds\.json|_password|RUTRACKER_|cookies_)'; then
  hard "a secret-shaped path appeared in git status — leak at the commit path"
fi
echo

# ================================================================== EXIT ======
if [ "$fail_hard" -ne 0 ]; then
  echo "RESULT: INSTRUMENT BROKEN or SECRET LEAK (exit 2) — verdict above is void."
  exit 2
fi
if [ "$RED_MODE" = 1 ]; then
  if [ "$fail_red" -ne 0 ]; then
    echo "RESULT: RED_MODE=1 — DEFECT REPRODUCED on the current .gitignore (exit 0)."
    exit 0
  fi
  echo "RESULT: RED_MODE=1 — defect NOT reproducible; the swallow is already loud (exit 1)."
  exit 1
fi
if [ "$fail_red" -ne 0 ]; then
  echo "RESULT: FAIL (exit 1) — the swallow is SILENT. BOB-212 acceptance not met."
  exit 1
fi
echo "RESULT: PASS (exit 0) — the swallow is LOUD (or the file commits normally)."
exit 0
