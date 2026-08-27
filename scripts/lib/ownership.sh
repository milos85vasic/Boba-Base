#!/usr/bin/env bash
# scripts/lib/ownership.sh — shared helpers for feature 002-user-owned-downloads.
#
# Purpose:
#   Resolve the declared ownership scope (config/owned_paths.yaml), resolve the
#   operator's uid, and PROBE a location by actually creating a file in it and
#   reading the owner back.
#
# Usage:
#   source "${PROJECT_ROOT}/scripts/lib/ownership.sh"
#
# Inputs:   OWNED_PATHS_FILE (optional) overrides the scope file path.
# Outputs:  functions only; no side effects at source time.
# Side-effects: probe_location() creates and REMOVES one temporary file in the
#   probed directory. Nothing else writes.
# Dependencies: bash, stat, mktemp, python3 with PyYAML (for scope parsing).
# Cross-references:
#   specs/002-user-owned-downloads/contracts/startup-precondition.md
#   specs/002-user-owned-downloads/data-model.md (E1 scope, E4 probe result)
#
# WHY probe_location() WRITES A REAL FILE (FR-010b — the load-bearing rule):
#   Ownership of a location cannot be inferred from the location itself. A
#   directory owned by the operator can still receive files owned by someone
#   else, which is EXACTLY the defect this feature exists to fix: the download
#   root's children were uid 1000 while new writes landed at uid 100999.
#   Checking the directory's own owner, or the configured PUID, or "no error
#   occurred", are all PROXIES for the real condition. §11.4.201 forbids
#   asserting a proxy in place of the condition, and a probe that passes
#   because it never wrote anything is a false pass.

set -uo pipefail

# ---------------------------------------------------------------------------
# ownership_project_root — resolve the repository root from this file's path.
# ---------------------------------------------------------------------------
ownership_project_root() {
    local d
    d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    printf '%s\n' "${d}"
}

# ---------------------------------------------------------------------------
# ownership_operator_uid / _gid — the identity everything must end up owned by.
#
# This is the uid of the account RUNNING the check, deliberately: the feature's
# definition of "correct owner" is "whoever started the system" (spec
# Assumptions), not a configured constant that could drift from reality.
# ---------------------------------------------------------------------------
ownership_operator_uid() { id -u; }
ownership_operator_gid() { id -g; }

# ---------------------------------------------------------------------------
# ownership_scope_file — path to the declared scope, overridable for tests.
# ---------------------------------------------------------------------------
ownership_scope_file() {
    printf '%s\n' "${OWNED_PATHS_FILE:-$(ownership_project_root)/config/owned_paths.yaml}"
}

# ---------------------------------------------------------------------------
# ownership_python — first interpreter that can actually import yaml.
#
# PROBED, not assumed: an interpreter that exists but lacks PyYAML cannot parse
# the scope, and treating it as usable produces a confusing downstream failure
# instead of an honest one here.
# ---------------------------------------------------------------------------
ownership_python() {
    local root cand
    root="$(ownership_project_root)"
    for cand in "${PYTHON_BIN:-}" "${root}/.venv/bin/python" python3; do
        [[ -n "${cand}" ]] || continue
        if command -v "${cand}" >/dev/null 2>&1 && "${cand}" -c 'import yaml' >/dev/null 2>&1; then
            printf '%s\n' "${cand}"; return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# ownership_scope_entries — emit one TAB-separated row per declared entry:
#     <resolved-path>\t<kind>\t<optional>\t<preserve_mode>\t<recursive>
#
# `${VAR:-default}` in a declared path is expanded against the environment, so
# the host-specific download root is resolved at run time rather than hardcoded
# into shared logic (§11.4.35).
#
# Returns 2 (not 1, and never 0) when the scope cannot be read: a caller must be
# able to distinguish "scope says nothing is wrong" from "I could not read the
# scope at all" (§11.4.201(6)).
#
# A DECLARED ENTRY THAT RESOLVES TO NO USABLE LOCATION IS ALSO A READ FAILURE
# (R2-M1, MEASURED 2026-08-26 against the pre-fix parser)
# ---------------------------------------------------------------------------
# This function used to drop such an entry with a bare `continue`. Measured
# consequence, on a 2-entry scope whose first entry was `${UNSET_VAR}`:
# ownership_repair.sh announced "(1 declared locations)", walked only the
# survivor, exited 0 and WROTE A COMPLETION MARKER. One DECLARED location had
# silently vanished, and no consumer could tell that scope from an honest
# 1-entry one — the §11.4.201(6) false-null, where a blind read and a clean
# tree return the same quiet number.
#
# Two shapes are refused, both of which mean "the declaration does not denote
# the location it claims to":
#
#   (1) the expansion is EMPTY — an unset/empty `${VAR}` with no default, an
#       explicit `${VAR:-}`, a missing or null `path:` key, or a list item that
#       is not a mapping at all. A declared location that is nothing has no
#       legitimate meaning; `optional: true` says the path may be ABSENT from
#       the filesystem, never that the DECLARATION may be absent.
#
#   (2) the expansion is NON-EMPTY but a `${VAR}` WITHOUT a default resolved to
#       nothing, so the path silently became a DIFFERENT one. MEASURED: with
#       `<root>/decoy/${UNSET}/leaf` the parser produced `<root>/decoy/leaf`,
#       the fence accepted it (absolute and deep enough) and the repair chowned
#       a tree the scope never declared, exit 0. The fence's depth floor is NOT
#       a backstop here — it only catches collapses that land on `/` or a bare
#       top-level directory, not one that lands on another well-formed path.
#
# `${VAR:-default}` — including the explicit `${VAR:-}` — is the operator
# STATING what empty means, and is never refused by (2). That shape is the
# shipped scope's first entry (`${QBITTORRENT_DATA_DIR:-/mnt/DATA}`), so a rule
# that swallowed it would refuse the live product: a false-positive refusal,
# which §11.4.201(1) forbids exactly as firmly as a false pass. Both golden-FALSE
# fixtures are pinned in tests/unit/test_ownership_repair.sh Case 23.
#
# WHY THE WHOLE SCOPE AND NOT JUST THE OFFENDING ENTRY
#   The completion marker carries a fingerprint over the PARSED entries and
#   start.sh reads it as "already repaired", so a partial walk that exits 0 does
#   not merely miss a location once — it LATCHES the miss on every subsequent
#   start. ownership_repair.sh:485-489 already recorded the identical decision
#   for the declared-path fence ("ONE BAD ENTRY REFUSES THE WHOLE RUN … Refusing
#   per-entry and proceeding with the rest would silently repair a partial scope
#   while writing a marker that claims the whole one"), and two different answers
#   to one question is the second dialect §11.4.251 forbids. Magnitude is not a
#   semantic boundary either: `paths: []` (every entry vanishing) is already
#   exit 2, so letting 1-of-2 exit 0 would put the operator's mental model on an
#   arbitrary cliff.
#
# WHY HERE AND NOT IN EACH CONSUMER
#   This parser is the only layer that still holds the raw spelling and the
#   variable name; every layer above it has already lost them (§11.4.241 —
#   enforce at the strongest rung that can see the invariant). It also gives all
#   three consumers (ownership_repair.sh, ownership_precondition.sh,
#   check_cm_ownership_invariants.sh) ONE predicate instead of three crosschecks
#   that could disagree about expansion semantics (§11.4.251).
#
# NOTHING is written to stdout when the scope is refused: a caller that ignored
# the exit code would otherwise consume a partial scope.
# ---------------------------------------------------------------------------
ownership_scope_entries() {
    local py scope
    scope="$(ownership_scope_file)"
    [[ -f "${scope}" ]] || { echo "ownership: scope file not found: ${scope}" >&2; return 2; }
    py="$(ownership_python)" || {
        echo "ownership: no python3 with PyYAML — cannot parse ${scope}" >&2
        echo "ownership: this is a BLIND read, not an empty scope" >&2
        return 2
    }
    "${py}" - "${scope}" <<'PYEOF'
import os, sys, re, yaml

# ${VAR} and ${VAR:-default}. group(2) present == a default was supplied, which
# is the operator stating what empty means; group(3) is that default's text.
VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}')

doc = yaml.safe_load(open(sys.argv[1])) or {}
rows = []
vanished = []


def _named(vs):
    return "; ".join(
        "${%s} is unset or empty and the entry supplies no ':-' default" % v
        for v in dict.fromkeys(vs)
    )


for idx, e in enumerate(doc.get("paths") or [], start=1):
    if not isinstance(e, dict):
        vanished.append((idx, str(e),
                         "the list item is not a mapping, so it declares no "
                         "`path:` key and resolves to an empty path"))
        continue

    raw = e.get("path")
    raw = "" if raw is None else str(raw)

    # SPELLING CHECK, before anything is substituted (R3-N1, measured
    # 2026-08-26). The documented grammar is exactly `${VAR}` and
    # `${VAR:-default}`. Two spellings satisfy neither and used to survive as a
    # literal or corrupted path rather than being refused:
    #   * NESTED `${A:-${B}}` — the default group `[^}]*` cannot span the INNER
    #     `}`, so that `}` closes the OUTER form and the trailing one is
    #     stranded. Measured: both-unset produced the literal row
    #     `.../${B}/leaf`; A set produced the corrupted `.../tmp/x}/leaf`.
    #     Neither is the path the operator declared.
    #   * an opener the grammar cannot consume at all — `${}`, `${1}`, or an
    #     unterminated `${VAR` — which the substitution leaves in place, so the
    #     marker survives into the walked path.
    #
    # WHY IT IS REFUSED RATHER THAN LEFT TO FAIL LATER: a NON-optional entry of
    # either shape does fail honestly ("does not exist", exit 1), but an
    # `optional: true` one logs `absent, declared optional — skipped`, exits 0
    # and writes the marker — a corrupted path that reads as a successful run
    # while repairing nothing. That is the same under-repair-while-reporting-
    # success shape the vanished rule below closes for the whole-path case.
    #
    # IT JUDGES THE DECLARED SPELLING ONLY (§11.4.201(1)). `raw` is read
    # straight from the tracked scope file; a variable's VALUE that happens to
    # contain `${` is env-writer-controlled exactly as QBITTORRENT_DATA_DIR is
    # and is never reached here — nor is a literal `}` in a directory name,
    # because only an unconsumed `${` opener counts. Both are pinned as
    # golden-FALSE cases in the suite.
    _nested = [m.group(0) for m in VAR_RE.finditer(raw)
               if m.group(3) is not None and "${" in m.group(3)]
    if _nested or "${" in VAR_RE.sub("", raw):
        if _nested:
            why = ("the entry's spelling was not fully resolved: %s nests one "
                   "`${...}` inside another's default, which the documented "
                   "`${VAR}` / `${VAR:-default}` grammar does not cover — the "
                   "inner `}` closes the outer form and the remainder is left "
                   "stranded, so the walked path would not be the declared one"
                   % "; ".join(dict.fromkeys(_nested)))
        else:
            why = ("the entry's spelling was not fully resolved: it contains a "
                   "`${` the documented `${VAR}` / `${VAR:-default}` grammar "
                   "cannot consume (an empty, non-identifier, or unterminated "
                   "name), so the marker would survive into the walked path")
        vanished.append((idx, raw, why))
        continue

    # Variables that resolved to nothing AND supplied no default. An entry
    # written `${VAR:-...}` (the explicit `${VAR:-}` included) never lands here.
    undeclared = []

    def sub(m, _u=undeclared):
        var, has_default, dflt = m.group(1), m.group(2) is not None, m.group(3)
        val = os.environ.get(var) or (dflt if dflt is not None else "")
        if not val and not has_default:
            _u.append(var)
        return val

    path = VAR_RE.sub(sub, raw)

    if not path:
        if not raw:
            why = ("the entry declares no usable `path:` key — it is missing, "
                   "null, or an empty path")
        elif undeclared:
            why = "it expanded to an empty path: " + _named(undeclared)
        else:
            why = "it expanded to an empty path"
        vanished.append((idx, raw, why))
        continue

    if undeclared:
        vanished.append((idx, raw,
                         "it expanded to '%s', a DIFFERENT path than declared: %s"
                         % (path, _named(undeclared))))
        continue

    rows.append("\t".join([
        path,
        str(e.get("kind", "")),
        "1" if e.get("optional", False) else "0",
        "1" if e.get("preserve_mode", False) else "0",
        "1" if e.get("recursive", True) else "0",
    ]))

if vanished:
    w = sys.stderr.write
    w("ownership: %d declared entr%s in %s resolved to no usable location:\n"
      % (len(vanished), "y" if len(vanished) == 1 else "ies", sys.argv[1]))
    for idx, raw, why in vanished:
        w("ownership:   entry %d — path: %r — %s\n" % (idx, raw, why))
    w("ownership: refusing the WHOLE scope, not only these entries: the completion\n")
    w("ownership:   marker's fingerprint claims EVERY declared location, so a partial\n")
    w("ownership:   walk that exited 0 would latch the miss on every later start.\n")
    w("ownership: remedy: give the entry a default (${VAR:-/path}), set the variable,\n")
    w("ownership:   or remove the entry. `optional: true` does not cover this — it\n")
    w("ownership:   says the path may be ABSENT, not that the DECLARATION may be.\n")
    sys.exit(2)

# Written only once every entry resolved: a caller that ignored the exit code
# must never be handed a partial scope.
sys.stdout.write("".join(r + "\n" for r in rows))
PYEOF
}

# ---------------------------------------------------------------------------
# probe_location <dir> — create a real file, read its owner back, remove it.
#
# Echoes one of: ok | wrong-owner:<uid> | unwritable | absent   (data-model E4)
# Return: 0 for ok, 1 for every other verdict.
#
# The probe file is created inside the probed directory ON PURPOSE — ownership
# is a property of the filesystem and mount the file lands on, so probing
# anywhere else would answer a different question.
#
# ---- THE AGREED PROPERTY IS uid, NOT uid+gid (BOB-207, §11.4.250) ----------
# This reads `%u` and compares against ownership_operator_uid(), and does NOT
# read `%g`. That asymmetry is deliberate and is the feature's single
# definition of "correct ownership", not an oversight:
#
#   * data-model E4 models this very result with `probe_uid` / `expected_uid`
#     and the verdict enum `ok|wrong-owner|unwritable|absent` — no gid field,
#     no gid verdict. Reading `%g` here would produce data E4 does not model,
#     and refusing on it would need a verdict this enum cannot express (the
#     honest attempt emits `wrong-owner:1000`, naming the CORRECT uid as the
#     fault — an FR-010a violation).
#   * contracts/startup-precondition.md P1 says compare against "the operator's
#     uid"; FR-001/FR-002/FR-003/FR-010b all say "owned by the account".
#   * scripts/ownership_precondition.sh — the shipped FR-010 gate — is uid-only
#     at every site, INCLUDING its own independent P1 container-write probe.
#
# ownership_repair.sh's walk was, until BOB-207, the one place that meant
# uid+gid; it was narrowed to match this. If a future change widens either
# side, widen BOTH and amend E4 first — a probe and a repair that disagree
# about which property they mean is the §11.4.250 primitive defect, and
# whichever answer the operator happens to read is then not a fact about the
# system.
# ---------------------------------------------------------------------------
probe_location() {
    local dir="$1" want probe got
    want="$(ownership_operator_uid)"

    [[ -e "${dir}" ]] || { echo "absent"; return 1; }
    if [[ -f "${dir}" ]]; then
        # A declared FILE (e.g. the credential store): read its owner directly.
        # There is nothing to create, so this is the one case where reading the
        # target itself IS the real condition rather than a proxy for it.
        got="$(stat -c '%u' "${dir}" 2>/dev/null)" || { echo "unwritable"; return 1; }
        [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }
        echo "wrong-owner:${got}"; return 1
    fi

    probe="$(mktemp "${dir}/.ownership-probe.XXXXXX" 2>/dev/null)" || { echo "unwritable"; return 1; }
    got="$(stat -c '%u' "${probe}" 2>/dev/null)"
    rm -f "${probe}"
    [[ -n "${got}" ]] || { echo "unwritable"; return 1; }
    [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }
    echo "wrong-owner:${got}"
    return 1
}

# ---------------------------------------------------------------------------
# ownership_scope_fingerprint — sha256 over the sorted declared scope.
#
# Used by the repair marker (data-model E2). A change to the scope MUST
# invalidate the marker, otherwise a newly-declared path is silently never
# repaired: the marker would say "already done" about work never performed.
# ---------------------------------------------------------------------------
#
# EMITS NOTHING WHEN THE SCOPE REFUSES (R3-N4). Piping straight into `sha256sum`
# hashed the parser's EMPTY output before `pipefail` surfaced its exit 2, so a
# refused scope printed `e3b0c442…` — the sha256 of the empty string — on
# stdout while returning non-zero. Every current caller guards the rc, so
# nothing was broken; but round 3 made a non-zero rc reachable from a new cause
# (unresolved and vanished declarations), and a refusing function that emits a
# plausible-looking value is a trap for the next caller that captures stdout
# and forgets. The entries are materialised FIRST and the function returns
# before hashing, so a refusal produces an empty stdout and the rc.
# BYTE-IDENTICAL TO THE PIPE IT REPLACES, for every input (proven 2026-08-26).
# Command substitution strips trailing newlines, so re-adding one unconditionally
# would hash "\n" instead of "" for a scope that parses to ZERO rows — a
# DIFFERENT fingerprint for the `paths: []` shape, which returns rc 0. That case
# is refused downstream before any marker is written, so the value never reaches
# disk; the empty branch below removes the divergence anyway rather than relying
# on that. Verified against the live shipped scope: old pipe, new function and
# the on-disk marker written by the old code all yield c41619d2…, so no
# completion marker silently re-arms.
ownership_scope_fingerprint() {
    local entries
    entries="$(ownership_scope_entries)" || return $?
    if [[ -z "${entries}" ]]; then
        printf '' | LC_ALL=C sort | sha256sum | cut -d' ' -f1
    else
        printf '%s\n' "${entries}" | LC_ALL=C sort | sha256sum | cut -d' ' -f1
    fi
}

# ---------------------------------------------------------------------------
# ownership_compose_rows <compose-file> [extra-root ...] — emit one
# TAB-separated row per compose service:
#
#     <service>\t<image>\t<userns_mode>\t<PUID>\t<mount-src,...>\t<user>
#
# THE SINGLE COMPOSE READER FOR THIS FEATURE (§11.4.251 — no second copy).
#   It was a bash function private to scripts/ownership_precondition.sh until
#   2026-08-21, when an independent review (finding IMPORTANT-1) proved the
#   FR-011 pre-build gate had NO mount analysis at all and passed a compose
#   file that reintroduced the defect through the `user:` key. Teaching the
#   gate to read mounts by writing it a second parser would have been the
#   near-identical fork §11.4.251 forbids — and would have let the two readers
#   drift on exactly the question they both have to answer. It therefore moved
#   here, and BOTH the precondition and the gate consume this one function.
#
# WHY THE `user` FIELD IS EMITTED RAW AND NEVER VARIABLE-EXPANDED:
#   `image`, `userns_mode`, `PUID` and the mount sources are expanded against
#   the live environment, because the caller needs the value that will actually
#   be used. `user` is deliberately NOT: an unset `${SVC_UID}` would expand to
#   the empty string, and an empty `user` field is indistinguishable from "this
#   service declares no user: at all" — the §11.4.201(6) FALSE-NULL, and the
#   one that matters most here, because "declares no user:" is the SAFE reading
#   and "cannot be resolved" is not. Callers receive the raw text and decide;
#   a value carrying `$` is reported unresolvable, never assumed to be root.
#
# WHY RELATIVE MOUNT SOURCES ARE NORMALISED AGAINST SEVERAL ROOTS:
#   Compose resolves a relative source against the COMPOSE FILE's directory.
#   The pre-build gate takes its compose path as an argument precisely so the
#   §1.1 paired mutation can run against a COPY in a temp dir, and a copied
#   compose leaves `./config` pointing at a temp directory that intersects no
#   declared location — so a single-root resolution would make the mutation
#   fixture silently drop half the ownership scope and pass. Every candidate
#   root is therefore emitted, and a caller treats the service as in-scope when
#   ANY candidate matches. That direction is the conservative-safe one
#   (§11.4.201(4)): it can only widen what gets checked, never narrow it.
#
# WHY A NAMED VOLUME IS NOT A HOST PATH:
#   Compose's short syntax treats a source that does not begin with `.`, `/`,
#   `~` (or a `$` placeholder resolving to one) as a NAMED VOLUME, which lives
#   in the runtime's own storage and can never be a declared host location.
#   Normalising `myvol` into `<root>/myvol` would invent a host path nobody
#   mounts — a §11.4.201(1) false positive waiting for the first project that
#   names a volume after a declared directory.
#
# Returns non-zero when the compose file is missing/unreadable/unparseable, so
# a caller can distinguish "declares nothing" from "could not be read".
# ---------------------------------------------------------------------------
ownership_compose_rows() {
    local compose="$1"; shift
    local py
    [[ -f "${compose}" ]] || return 1
    py="$(ownership_python)" || return 1
    "${py}" - "${compose}" "$(ownership_project_root)" "$@" <<'PYEOF'
import os, re, sys, yaml

compose = sys.argv[1]
roots = []
for candidate in [os.path.dirname(os.path.abspath(compose))] + list(sys.argv[2:]):
    candidate = os.path.abspath(candidate)
    if candidate not in roots:
        roots.append(candidate)

try:
    doc = yaml.safe_load(open(compose)) or {}
except Exception as exc:                       # unreadable/unparseable compose
    print("compose: %s" % exc, file=sys.stderr)
    sys.exit(1)

_VAR = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}')


def expand(value):
    def sub(m):
        var, dflt = m.group(1), m.group(3)
        return os.environ.get(var) or (dflt if dflt is not None else "")
    return _VAR.sub(sub, str(value))


def normalise(raw_src):
    """Absolute candidate paths for one mount source, or [] for a named volume."""
    if not raw_src:
        return []
    if raw_src[0] not in "./~$":
        return []                               # named volume, not a host path
    src = expand(raw_src)
    if not src:
        return []
    if src.startswith("~"):
        src = os.path.expanduser(src)
    if os.path.isabs(src):
        return [os.path.normpath(src)]
    out = []
    for root in roots:
        candidate = os.path.normpath(os.path.join(root, src))
        if candidate not in out:
            out.append(candidate)
    return out


for name, svc in (doc.get("services") or {}).items():
    if not isinstance(svc, dict):
        continue
    image = expand(svc.get("image") or "")
    userns = expand(svc.get("userns_mode") or "")

    puid = ""
    env = svc.get("environment") or []
    pairs = env.items() if isinstance(env, dict) else [
        tuple(str(e).split("=", 1)) for e in env
    ]
    for kv in pairs:
        if len(kv) == 2 and str(kv[0]).strip() == "PUID":
            puid = expand(kv[1]).strip()

    # RAW on purpose — see the header note on the FALSE-NULL this avoids.
    user = svc.get("user")
    user = "" if user is None else str(user).strip()

    sources = []
    for vol in (svc.get("volumes") or []):
        if isinstance(vol, dict):
            raw = str(vol.get("source", "") or "")
        else:
            # Expand AFTER taking the source token, but split on the colon that
            # separates source from target FIRST — a `${VAR:-/mnt/DATA}:/dst`
            # entry carries a colon inside the placeholder, so a naive split
            # would tear the default value in half and yield a bogus source.
            text = str(vol)
            depth = 0
            cut = len(text)
            for i, ch in enumerate(text):
                if text.startswith("${", i):
                    depth += 1
                elif ch == "}" and depth:
                    depth -= 1
                elif ch == ":" and depth == 0:
                    cut = i
                    break
            raw = text[:cut]
        for candidate in normalise(raw):
            if candidate not in sources:
                sources.append(candidate)

    print("\t".join([name, image, userns, puid, ",".join(sources), user]))
PYEOF
}

# ---------------------------------------------------------------------------
# ownership_normalise_path <path> — LEXICAL normalisation. Collapses `//`,
# drops `.`, and resolves `..` against the preceding component. Echoes the
# result; the input's absolute/relative character is preserved.
#
# WHY LEXICAL AND NOT `realpath`/`readlink -f`:
#   (a) TOCTOU. Resolving symlinks answers a question about the filesystem at
#       resolve time, and the declared path is walked LATER — a link swapped in
#       between check and walk would make the fence assert about a path the
#       repair never touches. A lexical answer is a property of the STRING and
#       cannot be raced.
#   (b) It buys nothing. find's default -P does not descend a symlinked root,
#       and scripts/ownership_repair.sh's absolutise() strips the trailing
#       slash that would otherwise make find traverse one. A symlinked declared
#       root is already contained without resolving it.
#   (c) It must work on paths that DO NOT EXIST. `.env` and config/boba.db are
#       declared `optional: true` precisely because they are legitimately absent
#       before first boot, and a fence that could not judge an absent path would
#       have to either skip it (a hole) or refuse it (a §11.4.201(1) false
#       positive).
#
# `..` above the root of an absolute path is the root itself, per POSIX
# (`/..` == `/`) — so a `..` climb can never escape upward into nothing.
# ---------------------------------------------------------------------------
ownership_normalise_path() {
    local p="$1" abs=0 seg rest joined="" i
    local -a stack=()
    [[ -n "${p}" ]] || { printf '%s' ''; return 1; }
    [[ "${p}" == /* ]] && abs=1
    rest="${p}"
    while [[ -n "${rest}" ]]; do
        seg="${rest%%/*}"
        if [[ "${seg}" == "${rest}" ]]; then rest=""; else rest="${rest#*/}"; fi
        case "${seg}" in
            ''|'.') ;;
            '..')
                if [[ ${#stack[@]} -gt 0 && "${stack[$(( ${#stack[@]} - 1 ))]}" != ".." ]]; then
                    unset "stack[$(( ${#stack[@]} - 1 ))]"
                    stack=("${stack[@]}")
                elif [[ "${abs}" -eq 0 ]]; then
                    stack+=("..")
                fi
                ;;
            *) stack+=("${seg}") ;;
        esac
    done
    for (( i = 0; i < ${#stack[@]}; i++ )); do
        joined="${joined}/${stack[${i}]}"
    done
    if [[ "${abs}" -eq 1 ]]; then
        printf '%s' "${joined:-/}"
    else
        printf '%s' "${joined:+${joined#/}}"
    fi
}

# ---------------------------------------------------------------------------
# THE DECLARED-PATH FENCE (§11.4.252 fail-closed).
#
# WHY IT EXISTS
#   scripts/ownership_repair.sh filters the WALK to items under a declared
#   path and called that "the scope fence". That is circular: it fences to the
#   declared path, and nothing constrained what a declared path may BE. The
#   shipped config/owned_paths.yaml declares
#       - path: "${QBITTORRENT_DATA_DIR:-/mnt/DATA}"
#   and `.env` — untracked, unreviewed, and not in any review's diff — supplies
#   that variable. MEASURED 2026-08-25: with QBITTORRENT_DATA_DIR=/ the repair
#   really did launch
#       find / \( ! -uid 1000 -o ! -gid 1000 \) -printf '%U\t%G\t%m\t%p\0'
#   — a recursive walk of the entire filesystem, observed in `ps` and killed by
#   pid. That is the condition this fence removes.
#
# WHY NOT SIMPLY "MUST BE UNDER THE PROJECT ROOT"
#   Because that would break the feature. The download root is INTENTIONALLY
#   outside the project; refusing it would be the §11.4.201(1) false-positive
#   refusal — a guard refusing on a condition that is absent. The fence
#   therefore splits on how the entry was WRITTEN:
#
#     RELATIVE entries  A repo-relative path denotes something in the
#                       repository. After normalisation it must still be inside
#                       the project root. An entry that climbs out with `..` was
#                       written to escape, and the scope format does not license
#                       that. (The project root must itself clear the depth
#                       floor, so a pathological root cannot smuggle one in.)
#
#     ABSOLUTE entries  Bounded by SHAPE, since nothing else bounds them:
#                        * at least MIN_COMPONENTS path components, and
#                        * never a system tree, nor anything under one.
#
# WHY THE FLOOR IS 2, MEASURED NOT CHOSEN
#   The shipped default is `/mnt/DATA` — exactly 2 components. 2 is therefore
#   the floor the shipped configuration forces; a lower floor would admit `/`
#   and the bare top-level directories, and a higher one would refuse the
#   documented default. This host's real root, /run/media/<user>/<disk>/Downloads,
#   has 5.
#
# WHY THE DENYLIST IS ALSO NEEDED
#   The floor alone does not catch `/usr/lib` — 2 components, passes the floor.
#   Both rules are load-bearing; neither subsumes the other.
#
# WHY /run, /home, /media, /mnt, /opt, /srv, /tmp ARE **NOT** DENYLISTED
#   MEASURED from this host's .env: the operator's real library is
#   /run/media/<user>/<disk>/Downloads. A denylist that swallowed /run would
#   refuse the live configuration — the same false-positive class the fence
#   must not become. Only trees where a recursive ownership rewrite is
#   destructive or meaningless are listed.
#
# HONEST BOUNDARY (§11.4.6)
#   This fence bounds the SHAPE of a declared path. It cannot decide that a
#   well-shaped absolute path is the tree the operator MEANT: an absolute
#   out-of-project path with enough depth is exactly what a download root is,
#   so it must be accepted. What it removes is the class traced to a
#   catastrophic outcome — filesystem roots, bare top-level directories, system
#   trees, and `..` escapes. It is also SHAPE-only: it deliberately does not
#   require the path to be operator-owned, because a root-owned mount point
#   with operator-owned content beneath it is the ordinary state of a removable
#   disk, and refusing it would refuse the very case the feature exists for.
#
#   IT JUDGES THE SPELLING; THE KERNEL RESOLVES THE PATH (R2-N1, MEASURED
#   2026-08-26). ownership_normalise_path() is LEXICAL, so an existing symlink
#   in a NON-FINAL component of a declared path is invisible here: the kernel
#   resolves it at walk time and the walk names items under the link's TARGET.
#   Measured with a pre-existing `…/piv/hop → real` and a declared
#   `…/piv/hop/data`, the walk named `…/real/data/victim` — no race required,
#   so this is not merely the TOCTOU artifact the normaliser's own rationale
#   describes. A symlinked FINAL component IS contained (find's default -P does
#   not descend it, and the trailing slash that would defeat that is stripped —
#   pinned by Case 17). What bounds the intermediate case is not this fence but
#   WHO CAN WRITE those components: they sit ABOVE the declared root, outside
#   every container bind mount, and an actor able to write there can edit the
#   untracked `.env` that supplies the root anyway — so no capability is
#   gained. Tracked as BOB-201 — the item that RECORDS this static reach, with
#   its scope and severity bounds and an operator-owned resolve-or-accept
#   decision (§11.4.66). Round 3 cited BOB-159 here, which is the WARM-START
#   repair-window item and whose body never mentioned symlinks at all: a
#   pointer that looked like coverage and was none, so no tracker query could
#   have found this reach (§11.4.214). Case 24 now reads this id out of the
#   fence and asks the tracker whether it exists AND records the reach, so the
#   next dangling citation fails a check instead of passing one. Stated here
#   because a fence that let a reader infer symlink safety it does not provide
#   would be the overstatement §11.4.6 forbids.
#
#   ONE WELL-SHAPED PATH IS DENIED BY COMPUTATION, NOT BY SHAPE (R2-N2): the
#   container runtime's own storage under $HOME — see
#   ownership_fence_runtime_trees() below for the rule, its reasoning and its
#   own honest limit.
# ---------------------------------------------------------------------------
OWNERSHIP_FENCE_MIN_COMPONENTS=2

# Closed set. Absolute, no trailing slash. Extending it can only ever narrow
# what the repair may touch, never widen it.
OWNERSHIP_FENCE_SYSTEM_TREES="/bin /boot /dev /etc /lib /lib32 /lib64 /libx32 /proc /root /sbin /sys /usr /var"

# ownership_path_components <abs-path> — number of non-empty path components.
ownership_path_components() {
    local p="$1" n=0 seg rest
    rest="${p}"
    while [[ -n "${rest}" ]]; do
        seg="${rest%%/*}"
        if [[ "${seg}" == "${rest}" ]]; then rest=""; else rest="${rest#*/}"; fi
        [[ -n "${seg}" ]] && n=$(( n + 1 ))
    done
    printf '%s' "${n}"
}

# ---------------------------------------------------------------------------
# ownership_fence_runtime_trees — trees that are neither system trees nor
# download roots: the CONTAINER RUNTIME's own storage, whose files are owned by
# mapped subuids BY DESIGN rather than by the operator.
#
# WHY IT IS NOT IN OWNERSHIP_FENCE_SYSTEM_TREES
#   That list is static and absolute. Rootless storage lives under the
#   operator's own $HOME (or $XDG_DATA_HOME), so the path is per host and must
#   be computed.
#
# WHY IT IS DENIED AT ALL (R2-N2, measured 2026-08-26)
#   `/home/<user>` clears the depth floor and is deliberately NOT denylisted —
#   `/home/<user>/Downloads` is an ordinary download root the fence must keep
#   accepting, and refusing it would be the §11.4.201(1) false positive. A
#   declared root at or above `~/.local/share/containers` is therefore accepted
#   by shape, and the repair's `podman unshare` fallback would rewrite the
#   subuid-owned rootless container storage that this project's §11.4.161
#   rootless mandate depends on. Recoverable (re-pull the images), destructive
#   to the runtime, and NO download root has ever lived inside container
#   storage — so the deny has no false-positive cost and removes a real hazard.
#
# HONEST LIMIT (§11.4.6): this resolves the DEFAULT graphroot and the
#   XDG_DATA_HOME-relocated one, both of which are pure string operations. It
#   does NOT resolve a graphroot relocated in storage.conf or via
#   CONTAINERS_STORAGE_CONF: reading those would make the fence depend on
#   filesystem state at check time, which is exactly the raceable property
#   ownership_normalise_path() documents as disqualifying. A host that has
#   moved its graphroot is NOT covered by this rule.
#
# A computed value that came out degenerate is DISCARDED rather than used, by
# two DIFFERENT guards (MEASURED 2026-08-26 — the earlier comment here named
# the wrong cause):
#   * RELATIVE base — a relative HOME or XDG_DATA_HOME never reaches the
#     candidate at all; the `== /*` guard on `base` discards it.
#   * SHALLOWER THAN THE DEPTH FLOOR — reached via a degenerate XDG_DATA_HOME,
#     NOT via an unset HOME: `XDG_DATA_HOME=/` computes `/containers`
#     (1 component) and is discarded. An unset, empty or `/` HOME computes
#     `/.local/share/containers` — 3 components, so it is KEPT, as a harmless
#     narrow phantom deny that no real root lives under. Under those same
#     degenerate values an ordinary root such as `/data/Downloads` is still
#     ACCEPTED: the deny never broadens into a top-level prefix.
# A deny rule that broadened into a top-level prefix would refuse legitimate
# roots, and a fence that over-refuses is a §11.4.201(1) FAIL-bluff of the same
# severity as one that under-refuses.
# ---------------------------------------------------------------------------
ownership_fence_runtime_trees() {
    local base cand
    base="${XDG_DATA_HOME:-${HOME:-}/.local/share}"
    [[ "${base}" == /* ]] || return 0
    cand="$(ownership_normalise_path "${base}/containers")" || return 0
    [[ "${cand}" == /* ]] || return 0
    [[ "$(ownership_path_components "${cand}")" -ge "${OWNERSHIP_FENCE_MIN_COMPONENTS}" ]] || return 0
    printf '%s\n' "${cand}"
}

# ownership_path_fence <resolved-abs-path> <declared-was-relative:0|1> <project-root>
#
# Returns 0  the path may be walked.
# Returns 1  REFUSED — the reason is printed on stderr.
#
# FAIL-CLOSED (§11.4.252): every input that is not exactly what this predicate
# expects returns 1. An argument it cannot judge is refused, never waved
# through — an unjudgeable declared path is precisely the case where a
# permissive default would hand the repair an unbounded tree.
ownership_path_fence() {
    local p="${1:-}" was_rel="${2:-}" root="${3:-}" norm root_norm sys ncomp

    if [[ $# -ne 3 ]]; then
        echo "ownership: fence called with $# arguments, expected 3 — refusing" >&2
        return 1
    fi
    if [[ -z "${p}" || "${p}" != /* ]]; then
        echo "ownership: fence received a non-absolute path: '${p}' — refusing" >&2
        return 1
    fi
    if [[ "${was_rel}" != "0" && "${was_rel}" != "1" ]]; then
        echo "ownership: fence received an unusable relative-flag: '${was_rel}' — refusing" >&2
        return 1
    fi
    if [[ -z "${root}" || "${root}" != /* ]]; then
        echo "ownership: fence received a non-absolute project root: '${root}' — refusing" >&2
        return 1
    fi

    norm="$(ownership_normalise_path "${p}")"
    if [[ -z "${norm}" || "${norm}" != /* ]]; then
        echo "ownership: '${p}' could not be normalised — refusing" >&2
        return 1
    fi

    # --- system trees: refused for relative and absolute entries alike, and
    # checked FIRST so the message names the strongest reason. ---------------
    for sys in ${OWNERSHIP_FENCE_SYSTEM_TREES}; do
        if [[ "${norm}" == "${sys}" || "${norm}" == "${sys}"/* ]]; then
            # A repository legitimately checked out under a system tree (say
            # /usr/local/src) keeps working: its RELATIVE entries are judged by
            # containment below, which is the stronger guarantee. Only an
            # ABSOLUTE entry naming a system tree is refused here.
            if [[ "${was_rel}" -eq 0 ]]; then
                echo "'${norm}' is inside the system tree ${sys}; a recursive ownership change there is never a download root" >&2
                return 1
            fi
        fi
    done

    # --- container-runtime storage: computed, absolute entries only --------
    # Absolute-only for the same reason as the system trees above: a REPOSITORY
    # that legitimately lives under one of these prefixes keeps working, because
    # its relative entries are bounded by project containment, which is the
    # stronger guarantee.
    if [[ "${was_rel}" -eq 0 ]]; then
        local rt
        while IFS= read -r rt; do
            [[ -n "${rt}" ]] || continue
            if [[ "${norm}" == "${rt}" || "${norm}" == "${rt}"/* ]]; then
                echo "'${norm}' is inside the container-runtime storage tree ${rt}; those files are owned by mapped subuids by design and a recursive ownership change there breaks the rootless runtime (§11.4.161)" >&2
                return 1
            fi
        done < <(ownership_fence_runtime_trees)
    fi

    if [[ "${was_rel}" -eq 1 ]]; then
        # --- relative: must stay inside the project root -------------------
        root_norm="$(ownership_normalise_path "${root}")"
        if [[ -z "${root_norm}" || "${root_norm}" != /* ]]; then
            echo "the project root '${root}' could not be normalised — refusing" >&2
            return 1
        fi
        ncomp="$(ownership_path_components "${root_norm}")"
        if [[ "${ncomp}" -lt "${OWNERSHIP_FENCE_MIN_COMPONENTS}" ]]; then
            echo "the project root '${root_norm}' has ${ncomp} path component(s), fewer than the ${OWNERSHIP_FENCE_MIN_COMPONENTS} required — a repo-relative entry cannot be bounded against it" >&2
            return 1
        fi
        if [[ "${norm}" != "${root_norm}" && "${norm}" != "${root_norm}"/* ]]; then
            echo "'${norm}' was declared as a repo-relative path but resolves OUTSIDE the project root '${root_norm}' — a relative entry may not climb out with '..'" >&2
            return 1
        fi
        return 0
    fi

    # --- absolute: bounded by shape ---------------------------------------
    ncomp="$(ownership_path_components "${norm}")"
    if [[ "${ncomp}" -lt "${OWNERSHIP_FENCE_MIN_COMPONENTS}" ]]; then
        if [[ "${norm}" == "/" ]]; then
            echo "'${p}' resolves to the filesystem root '/' — a recursive ownership change of the whole filesystem is never a declared scope" >&2
        else
            echo "'${norm}' has ${ncomp} path component(s), fewer than the ${OWNERSHIP_FENCE_MIN_COMPONENTS} required (the shipped default /mnt/DATA has 2) — a bare top-level directory is never a download root" >&2
        fi
        return 1
    fi
    return 0
}
