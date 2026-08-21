#!/usr/bin/env bash
# check_cm_ownership_invariants.sh — CM-OWNERSHIP-INVARIANTS pre-build gate
# (FR-011 of specs/002-user-owned-downloads/, §11.4.135 permanent regression
# guard, §11.4.201 guard-asserts-the-real-condition).
#
# Purpose:
#   Assert, statically and from STRUCTURE (never a substring scan), that the
#   operator-owned-writes fix cannot be silently reverted:
#
#     (1) every linuxserver-based compose service declares PUID=0 AND PGID=0;
#     (2) NO service declares `userns_mode: keep-id`;
#     (3) the declared ownership scope config/owned_paths.yaml exists, parses,
#         and is non-empty;
#     (4) every compose service whose MOUNT SOURCES intersect that scope runs
#         as container root — no `user:` key and no Dockerfile `USER` directive
#         downgrading it away from uid 0 (E5 route completeness, task T034).
#
# WHY (4) EXISTS, AND WHY ITS ABSENCE WAS NOT A COSMETIC GAP (independent
# review finding IMPORTANT-1, reproduced on this host 2026-08-21):
#   Invariants (1)-(3) read `image:`, `environment:` and `userns_mode:`. They
#   never read `volumes:` and never read `user:`. A reviewer appended four
#   lines to a COPY of the real docker-compose.yml —
#
#       attack-writer:
#         image: python:3.12-alpine
#         user: "1000:1000"
#         volumes:
#           - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads
#
#   — and this gate printed `PASS: CM-OWNERSHIP-INVARIANTS`, exit 0. That
#   service writes into the download root as container uid 1000, which rootless
#   podman maps to host uid 100999: the reported defect, verbatim, waved
#   through by the gate that exists to make it un-revertable.
#
#   The construction is not exotic. A well-meaning "don't run containers as
#   root" hardening pass that adds `user: "1000:1000"` to download-proxy would
#   silently reintroduce the defect for `config/` — including the encrypted
#   credential store whose unreadability started this feature — while every
#   other invariant here stayed green.
#
#   tasks.md T034 and data-model.md E5 BOTH describe this gate as asserting
#   that every service mounting an in-scope path declares a route. Until (4)
#   landed it asserted no such thing, so T034 was marked [x] for a strictly
#   weaker gate than its own description. (4) is what makes the description
#   true rather than aspirational.
#
#   Each refusal names the SERVICE and WHAT was wrong, and prints the resolved
#   evidence it refused on (§11.4.201(5)).
#
# FORENSIC ANCHOR (measured on this host, 2026-08-21, research.md R6):
#   The stack runs under ROOTLESS podman, which maps container uid N to host
#   uid 100000+N-1 and container uid 0 to the HOST OPERATOR (uid 1000).
#   MEASURED on this host 2026-08-21, not assumed — `podman info` reports
#   `0->1000 (size 1)` and `1->100000 (size 65536)`, and /etc/subuid carries
#   `<operator>:100000:65536`. (Correction, same date: four places in this file
#   and two in its meta-test previously wrote the `abc` default uid 911 as host
#   uid 101910. The arithmetic gives 100910 — the error was exactly 1000, and
#   it survived because nobody re-derived it from the mapping the very next
#   line states. The 100999 figure IS correct and is the one measured
#   end-to-end: 100000 + 1000 - 1.)
#   The linuxserver.io images (`qbittorrent`, `jackett`) boot as root and drop
#   the application to the `abc` user at PUID. With PUID=1000 every download
#   landed at host uid 100999 — an identity the operator does not have:
#       download root : 6458 items at uid 1000, 1 at 100999 (renders UNKNOWN)
#       config/       : 51 items at uid 100999
#       config/boba.db: mode 600, owner unresolvable -> the operator could not
#                       read their own credential DB, so the backup that
#                       docs/BOBA_DATABASE.md §3 MANDATES was impossible.
#   THE FIX is PUID=0 / PGID=0 on those images, which makes the app write as
#   container-root == the host operator. It grants NO host privilege: rootless
#   podman's container-root is still the unprivileged operator uid on the host.
#
# WHY "linuxserver-based" IS DERIVED FROM `image:` **AND** FROM A RESOLVED
# `build:` BASE, NOT A SERVICE-NAME LIST (§11.4.201(6) — silence is not an
# exemption):
#   A hardcoded list of {qbittorrent, jackett} would leave a linuxserver
#   service added LATER silently uncovered: it would inherit the image's abc
#   default (uid 911 -> host 100910) and reproduce the defect while this gate
#   reported a clean tree. The image reference is the real condition, so the
#   scope is computed from it — the registry/namespace path components are
#   compared for EQUALITY to `linuxserver`, so a repository merely CONTAINING
#   that word (e.g. `acme/mylinuxserverfork`) is not a carrier match.
#
#   THE `image:`-ONLY DERIVATION WAS ITSELF BLIND, AND IT WAS PROVEN BLIND
#   (independent review finding MINOR-1, reproduced 2026-08-21 before this
#   fix): a service BUILT from a Dockerfile has NO `image:` key, so
#   `image_is_linuxserver(None)` was false and the service was classified
#   NOT-linuxserver and never PUID-checked. The constructed case
#
#       qbt-derived-local:
#         build: { context: ./build-ctx }     # FROM lscr.io/linuxserver/...
#         environment: [ PUID=1000 ]
#
#   PASSED this gate (exit 0) while its writes would land at host uid 100910 —
#   the exact defect FR-011 exists to make un-revertable, arrived at through a
#   hole in the gate's own scope rather than through a wrong value.
#
#   The fix RESOLVES the base instead of assuming it: for a service carrying a
#   `build:`, the Dockerfile's FROM chain is parsed (last stage = the runtime
#   image, `AS` aliases followed back, global ARG defaults substituted) and the
#   SAME namespace-equality test is applied to the resolved base — one
#   predicate, not a second forked copy (§11.4.251). When the base genuinely
#   CANNOT be resolved (Dockerfile absent, `FROM ${ARG}` with no default,
#   circular stage reference) the gate emits an "unverifiable base" FINDING and
#   REFUSES. Silence is not an exemption: an unresolvable base is precisely the
#   case where a linuxserver image could hide, so the quiet zero it used to
#   return was the §11.4.201(6) FALSE-NULL, not a clean tree.
#
#   The Dockerfile is read by INSTRUCTION TOKENS (keyword + operands), with
#   comment lines dropped before parsing — so a Dockerfile comment merely
#   MENTIONING `lscr.io/linuxserver/...` is invisible here, exactly as a
#   compose comment mentioning PUID=1000 is invisible to the YAML parse.
#
# WHY A MISSING PUID ON A LINUXSERVER SERVICE IS A FINDING, NOT A PASS:
#   Absence is not neutrality here. With no PUID the image runs the app as
#   `abc` (911) and the host sees 100910 — the exact defect class, arrived at
#   by omission instead of by a wrong value. §11.4.201(6): a quiet zero from
#   an unasserted condition is not a clean tree.
#
# WHY `userns_mode: keep-id` IS FORBIDDEN — RECORDED HERE SO THE NEXT PERSON
# DOES NOT "FIX" THIS GATE BY ADDING IT BACK:
#   `keep-id` maps the host operator's uid to the SAME uid inside the
#   container, which leaves the container with NO USABLE ROOT. The
#   linuxserver.io entrypoint boots as root to chown its config tree and drop
#   privileges; with keep-id that entrypoint cannot proceed and the container
#   HANGS at start — the failure mode measured on these images. It was
#   therefore considered and DELIBERATELY REJECTED for every service in this
#   stack, including the already-correct root-running ones (`download-proxy`,
#   `boba-jackett`, `qbittorrent-proxy-go`), which were MEASURED to write as
#   host uid 1000 as-is and were left unchanged on purpose. Reintroducing
#   keep-id would hang the stack, not harden it.
#
# WHY NON-LINUXSERVER SERVICES ARE NOT REQUIRED TO DECLARE PUID
# (§11.4.201(1) — a false-positive refusal is exactly as broken as a false
# pass): `download-proxy` (python:3.12-alpine), `boba-jackett` and
# `qbittorrent-proxy-go` (locally built) run as root already and were MEASURED
# to write as host uid 1000. They have no PUID and need none. A gate that
# demanded one would refuse a healthy tree.
#
# WHY THIS GATE IS SELF-CONTAINED (contrast with its siblings, §11.4.6):
#   check_cm_killpg_pgid_guard.sh and check_cm_healthcheck_covers_served_ports.sh
#   are thin DELEGATORS over universal engines in the constitution submodule
#   (§11.4.177). This invariant is NOT universal: it encodes boba's rootless
#   uid-mapping reality and the linuxserver PUID contract, so no shared engine
#   exists to delegate to and inventing one here would be scope creep. The
#   detection therefore lives in this file. Should the rule ever generalise,
#   the engine belongs upstream and this file becomes a delegator (§11.4.74).
#
# Usage:
#   check_cm_ownership_invariants.sh [COMPOSE_FILE] [OWNED_PATHS_FILE]
#   check_cm_ownership_invariants.sh --help
#
#   Both inputs are positional overrides so the §1.1 paired mutation can run
#   against a COPY in a temp dir and never touch the real docker-compose.yml
#   (which other work streams edit concurrently, and which the pre-build
#   NO-TRACE assertion forbids a test from writing into).
#
# Inputs:   optional compose path (default: repo-root docker-compose.yml) and
#           owned-paths path (default: repo-root config/owned_paths.yaml).
#           No stdin. Optional env PYTHON_BIN — tried FIRST among interpreter
#           candidates, but still subject to the `import yaml` probe rather
#           than trusted on sight (§11.4.201(11): probe the artifact through
#           its real invocation path).
# Outputs:  scope + per-service verdict lines on stdout, the PASS line ALWAYS
#           last (the pre-build wiring reads it with `tail -n1`); findings and
#           the FAIL summary on stderr.
# Side-effects: none. Read-only: no file is written, no network is contacted,
#           no container is touched, and NO PROCESS IS EVER SIGNALLED (so the
#           §11.4.263 pgid>1 obligation is vacuously satisfied — there is no
#           kill/killpg call in this file to guard).
# Dependencies: bash, python3 with PyYAML, scripts/lib/ownership.sh (SOURCED,
#           never re-implemented — see the §11.4.251 note at the source line).
#
# Scope DATA (consumer-owned, §11.4.35):
#   compose     : docker-compose.yml         (repo root; overridable, arg 1)
#   owned paths : config/owned_paths.yaml    (repo root; overridable, arg 2)
#   python      : $PYTHON_BIN, .venv/bin/python, python3, python (in order)
#
# Verdict:
#   0 — PASS  (>=1 linuxserver service checked, every invariant holds)
#   1 — FAIL  (a finding, a blind parse, a missing/uparseable input, or no
#              usable YAML parser — never a SKIP: an unmeasurable invariant is
#              itself a §11.4.201 bluff)
#   2 — ERROR (usage error)
#
# REGISTRATION STATUS — WIRED AND BLOCKING (§11.4.196(F)).
#   scripts/pre_build_verification.sh runs this gate BY NAME as
#   CM-OWNERSHIP-INVARIANTS: it invokes this script with no arguments, reports
#   the verdict with `tail -n1`, and routes a non-zero exit through `fail`, so
#   a finding BLOCKS the build rather than warning.
#
#   THE INVARIANT NUMBER IS DELIBERATELY NOT WRITTEN HERE, and that omission is
#   the lesson rather than laziness. This paragraph has now gone stale TWICE:
#   once claiming the gate was unwired after it had been wired, and then — in
#   the very commit that fixed that — claiming a slot number and a label
#   collision that the same commit had just renumbered away. Both times the
#   false statement lived in a gate whose entire purpose is honesty, and both
#   times the rotting part was THE NUMBER. The name is greppable and stable;
#   the number is neither. Cite the name.

set -euo pipefail

GATE_NAME="CM-OWNERSHIP-INVARIANTS"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

print_help() {
    # Print the WHOLE leading comment block, computed rather than a fixed line
    # range: a hardcoded range silently truncates the moment the header grows,
    # which is how --help drifts out of sync with the rule it documents.
    awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    print_help
    exit 0
fi
if [[ "${1:-}" == -* ]]; then
    echo "ERROR: unknown argument: $1 (usage: $(basename "${BASH_SOURCE[0]}") [COMPOSE_FILE] [OWNED_PATHS_FILE])" >&2
    exit 2
fi
if [[ $# -gt 2 ]]; then
    echo "ERROR: too many arguments (usage: $(basename "${BASH_SOURCE[0]}") [COMPOSE_FILE] [OWNED_PATHS_FILE])" >&2
    exit 2
fi

COMPOSE_FILE="${1:-${REPO_ROOT}/docker-compose.yml}"
OWNED_PATHS_FILE="${2:-${REPO_ROOT}/config/owned_paths.yaml}"

# ---------------------------------------------------------------------------
# Interpreter resolution (§11.4.201(11)): a candidate is accepted only after
# `import yaml` succeeds THROUGH it. Presence of an interpreter is a proxy;
# the real condition is "can this interpreter parse the compose file".
# ---------------------------------------------------------------------------
resolve_python() {
    local candidate
    for candidate in ${PYTHON_BIN:-} "${REPO_ROOT}/.venv/bin/python" python3 python; do
        [[ -n "${candidate}" ]] || continue
        command -v "${candidate}" >/dev/null 2>&1 || continue
        if "${candidate}" -c 'import yaml' >/dev/null 2>&1; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

PY=""
if ! PY="$(resolve_python)"; then
    # FAIL, never SKIP: an invariant nobody can measure is not an invariant
    # that holds (§11.4.201(4) conservative-safe default, stated honestly).
    echo "${GATE_NAME}: no python interpreter with PyYAML was found" >&2
    echo "  tried: \${PYTHON_BIN}, ${REPO_ROOT}/.venv/bin/python, python3, python" >&2
    echo "  This gate FAILs rather than SKIPs — an unmeasurable invariant is" >&2
    echo "  itself a §11.4.201 bluff, not a clean tree." >&2
    echo "FAIL: ${GATE_NAME} could not run (no YAML parser)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Shared readers (§11.4.251 — ONE compose parser and ONE scope parser for this
# feature, consumed by BOTH this gate and scripts/ownership_precondition.sh).
#
# The mount/`user:` invariant below needs exactly the compose facts the startup
# precondition already reads. Writing a second reader here would be the
# near-identical fork §11.4.251 forbids — and, worse, would let the two
# readers drift on the one question they both exist to answer. They therefore
# both call scripts/lib/ownership.sh.
#
# The library defines functions only and has no side effects at source time, so
# sourcing it cannot perturb this gate's read-only contract. It relaxes strict
# mode for its own callers, so strict mode is re-armed immediately after.
# ---------------------------------------------------------------------------
# shellcheck source=scripts/lib/ownership.sh
source "${REPO_ROOT}/scripts/lib/ownership.sh"
set -euo pipefail

ANALYZER_OUT="$(mktemp)"
COMPOSE_ROWS_FILE="$(mktemp)"
SCOPE_ROWS_FILE="$(mktemp)"
trap 'rm -f "${ANALYZER_OUT}" "${COMPOSE_ROWS_FILE}" "${SCOPE_ROWS_FILE}"' EXIT

# The library probes interpreters independently; hand it the one already proven
# able to `import yaml` here so the two cannot disagree about what is usable.
export PYTHON_BIN="${PY}"
export OWNED_PATHS_FILE

# A reader that could not run leaves an EMPTY file, and the analyzer reports
# that emptiness as an unreadable input rather than as "declares nothing" —
# a blind read and a clean tree must never return the same quiet zero
# (§11.4.201(6)).
if ! ownership_compose_rows "${COMPOSE_FILE}" >"${COMPOSE_ROWS_FILE}" 2>/dev/null; then
    : >"${COMPOSE_ROWS_FILE}"
fi
if ! ownership_scope_entries >"${SCOPE_ROWS_FILE}" 2>/dev/null; then
    : >"${SCOPE_ROWS_FILE}"
fi

set +e
"${PY}" - "${COMPOSE_FILE}" "${OWNED_PATHS_FILE}" "${REPO_ROOT}" \
        "${COMPOSE_ROWS_FILE}" "${SCOPE_ROWS_FILE}" >"${ANALYZER_OUT}" 2>&1 <<'PY_EOF'
"""Structural analyzer for CM-OWNERSHIP-INVARIANTS.

Emits line-oriented results the bash wrapper routes to stdout/stderr:

    INFO <text>       -> scope / per-service verdict (stdout)
    FINDING <text>    -> a refusal with its resolved evidence (stderr)

Exit 0 when no FINDING was emitted, 1 otherwise.

Everything here matches STRUCTURE (parsed YAML nodes), never substrings: a
comment that MENTIONS `keep-id` or `PUID=1000` is invisible to the parser, so
prose can never be mistaken for a declaration. This project has repeatedly
been bitten by greps matching prose (BOB-138/BOB-141).
"""
import os
import re
import sys

import yaml

compose_path, owned_paths_path, repo_root = sys.argv[1], sys.argv[2], sys.argv[3]
compose_rows_path, scope_rows_path = sys.argv[4], sys.argv[5]
compose_dir = os.path.dirname(os.path.abspath(compose_path))

findings = []
infos = []
dockerfile_text = {}


def info(msg):
    infos.append(msg)


def finding(msg):
    findings.append(msg)


def load_yaml(path, label):
    """Parse `path`, or record a finding. Returns (ok, document)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return True, yaml.safe_load(handle)
    except FileNotFoundError:
        finding("%s: file not found: %s" % (label, path))
    except OSError as exc:
        finding("%s: unreadable: %s (%s)" % (label, path, exc))
    except yaml.YAMLError as exc:
        finding("%s: does not parse as YAML: %s (%s)" % (label, path, exc))
    return False, None


def image_is_linuxserver(image):
    """True when the image reference's registry/namespace path names linuxserver.

    Component EQUALITY, never substring: `acme/mylinuxserverfork` must not
    match, or the gate would demand PUID=0 from an unrelated image — the
    false-positive refusal §11.4.201(1) forbids as firmly as a false pass.
    """
    if not isinstance(image, str) or not image.strip():
        return False
    ref = image.strip()
    # A digest pin (`repo@sha256:...`) and a tag (`repo:tag`) both end the ref;
    # the tag colon can only live in the LAST path component, so a registry
    # host carrying a port (`host:5000/ns/img`) survives this correctly.
    ref = ref.split("@", 1)[0]
    parts = ref.split("/")
    parts[-1] = parts[-1].split(":", 1)[0]
    # The namespace components are everything but the final image name.
    return any(part.lower() == "linuxserver" for part in parts[:-1])


_VAR_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}"   # ${VAR} / ${VAR:-dflt}
    r"|\$([A-Za-z_][A-Za-z0-9_]*)"                       # $VAR
)


def build_spec(service):
    """Normalise compose `build:` (string OR mapping form).

    Returns (context, dockerfile, inline_text) or None when there is no build.
    """
    spec = service.get("build")
    if spec is None:
        return None
    if isinstance(spec, str):
        return (spec, "Dockerfile", None)
    if isinstance(spec, dict):
        inline = spec.get("dockerfile_inline")
        inline = inline if isinstance(inline, str) and inline.strip() else None
        context = str(spec.get("context") or ".")
        dockerfile = str(spec.get("dockerfile") or "Dockerfile")
        return (context, dockerfile, inline)
    return None


def locate_dockerfile(context, dockerfile):
    """Resolve a build context to a real Dockerfile path.

    Returns (path, how) on success, or (None, [candidates tried]).

    Compose resolves a relative context against the COMPOSE FILE's directory,
    so that is tried FIRST and is the correct semantics. The repo root is a
    documented SECOND attempt for one specific reason: this gate takes the
    compose file as a positional argument precisely so the §1.1 paired mutation
    can run against a COPY in a temp dir, and a copied compose leaves its build
    context behind in the repo. Which candidate actually resolved is REPORTED
    (§11.4.201(5)), never silently substituted.
    """
    tried = []
    for root, label in ((compose_dir, "compose-relative"),
                        (repo_root, "repo-root-relative")):
        if os.path.isabs(dockerfile):
            candidate = dockerfile
        elif os.path.isabs(context):
            candidate = os.path.join(context, dockerfile)
        else:
            candidate = os.path.join(root, context, dockerfile)
        candidate = os.path.normpath(candidate)
        if candidate not in tried:
            tried.append(candidate)
        if os.path.isfile(candidate):
            return candidate, label
    return None, tried


def dockerfile_logical_lines(text):
    """Split a Dockerfile into logical instruction lines.

    Token-structural, not a substring scan: comment lines are dropped and
    backslash continuations are joined BEFORE any instruction is read, so a
    Dockerfile comment merely MENTIONING an image reference — or a `USER`
    downgrade — is invisible to every reader built on this.

    ONE tokenizer, deliberately: both the FROM-chain resolver and the USER
    reader below consume it. A second copy would be the near-identical fork
    §11.4.251 forbids, and the two would drift on comment and continuation
    handling — the exact carrier class BOB-138 was.
    """
    logical = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            # A comment is a comment whether or not a continuation is open.
            continue
        if not buffer and not stripped:
            continue
        if raw.rstrip().endswith("\\"):
            buffer += raw.rstrip()[:-1] + " "
            continue
        buffer += raw
        if buffer.strip():
            logical.append(buffer.strip())
        buffer = ""
    if buffer.strip():
        logical.append(buffer.strip())
    return logical


def dockerfile_last_user(text):
    """The operand of the LAST `USER` instruction, or None when there is none.

    The LAST one wins because that is what Docker leaves in effect for the
    container's process; a Dockerfile that drops to `appuser` to install
    something and then returns to `USER root` runs as root, and reading the
    first USER would refuse it — the §11.4.201(1) false positive.
    """
    found = None
    for line in dockerfile_logical_lines(text):
        parts = line.split()
        if parts and parts[0].upper() == "USER":
            operands = [t for t in parts[1:] if not t.startswith("--")]
            if operands:
                found = operands[0].strip().strip('"').strip("'")
    return found


def dockerfile_stages(text):
    """Parse a Dockerfile into ([(base_ref, alias_lower_or_None)], global_args).

    Only ARGs declared before the first FROM are collected — those are the only
    ones Docker permits a FROM line to reference.
    """
    logical = dockerfile_logical_lines(text)

    stages = []
    global_args = {}
    for line in logical:
        parts = line.split()
        if not parts:
            continue
        keyword = parts[0].upper()
        if keyword == "ARG" and not stages:
            for token in parts[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    global_args[key.strip()] = value.strip().strip('"').strip("'")
                else:
                    global_args.setdefault(token.strip(), None)
        elif keyword == "FROM":
            # `--platform=...` and any future flag are operands of FROM, not
            # the image reference.
            operands = [t for t in parts[1:] if not t.startswith("--")]
            if not operands:
                continue
            alias = None
            if len(operands) >= 3 and operands[1].upper() == "AS":
                alias = operands[2].lower()
            stages.append((operands[0], alias))
    return stages, global_args


def expand_build_arg(ref, args):
    """Substitute global ARG values into a FROM reference.

    Returns (expanded, [names that could not be resolved]). An unresolved name
    is NOT silently blanked into a match-nothing string — it is reported, so
    `FROM ${BASE}` with no default becomes an explicit unverifiable finding
    rather than a quiet "not linuxserver".
    """
    unresolved = []

    def substitute(match):
        name = match.group(1) or match.group(3)
        default = match.group(2)
        if args.get(name):
            return args[name]
        if default is not None:
            return default
        unresolved.append(name)
        return ""

    return _VAR_RE.sub(substitute, ref), unresolved


def resolve_runtime_base(text):
    """Resolve a Dockerfile's RUNTIME base image.

    The LAST stage is the image compose actually runs; an `AS` alias is
    followed back to the stage it names (with a cycle guard). Returns
    (base_ref, None) or (None, reason).
    """
    stages, args = dockerfile_stages(text)
    if not stages:
        return None, "the Dockerfile contains no FROM instruction"

    alias_index = {}
    for index, (_, alias) in enumerate(stages):
        if alias:
            alias_index[alias] = index

    index = len(stages) - 1
    seen = set()
    while True:
        if index in seen:
            return None, "the Dockerfile's build stages reference each other circularly"
        seen.add(index)
        expanded, unresolved = expand_build_arg(stages[index][0], args)
        if unresolved:
            return None, ("FROM references build argument(s) %s that have no default, "
                          "so the base image is not statically determinable"
                          % ", ".join(sorted(set(unresolved))))
        expanded = expanded.strip()
        if not expanded:
            return None, "FROM expands to an empty image reference"
        target = alias_index.get(expanded.lower())
        if target is None:
            return expanded, None
        index = target


def classify_service(name, service, image):
    """Decide whether a service runs a linuxserver-based image.

    Returns (True, evidence) / (False, evidence) / (None, None). None means
    UNVERIFIABLE — a finding has already been recorded, because a base nobody
    can resolve is exactly where a linuxserver image would hide, and reading
    that silence as "not linuxserver" is the §11.4.201(6) false-null this
    gate exists to refuse.
    """
    if image_is_linuxserver(image):
        return True, "image=%s" % image

    spec = build_spec(service)
    if spec is None:
        return False, "image=%s" % (image if image else "<no image and no build>")

    context, dockerfile, inline = spec
    if inline is not None:
        text, source = inline, "build.dockerfile_inline"
    else:
        located, how = locate_dockerfile(context, dockerfile)
        if located is None:
            finding(
                "%s: builds from `%s` (context `%s`) but its base image is "
                "UNVERIFIABLE — no Dockerfile was found, so this gate cannot "
                "tell whether the service is linuxserver-based and MUST NOT "
                "assume it is not. Tried: %s. Declare its route: give the "
                "service an explicit `image:`, or make the Dockerfile "
                "readable from here."
                % (name, dockerfile, context, "; ".join(how))
            )
            return None, None
        try:
            with open(located, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            finding(
                "%s: base image UNVERIFIABLE — its Dockerfile %s could not be "
                "read (%s). Declare its route rather than leaving the base "
                "unchecked." % (name, located, exc)
            )
            return None, None
        source = "%s (%s)" % (located, how)

    # Recorded so the mount/`user:` invariant can read this service's USER
    # directive from the SAME bytes this classification used — one read, one
    # tokenizer, no second opinion about what the Dockerfile says.
    dockerfile_text[name] = (text, source)

    base, reason = resolve_runtime_base(text)
    if base is None:
        finding(
            "%s: base image UNVERIFIABLE from %s — %s. A base this gate cannot "
            "resolve is exactly where a linuxserver image hides, so it is "
            "refused rather than assumed non-linuxserver. Declare its route: "
            "pin the base explicitly (or give the service an `image:`) so "
            "PUID can be held to 0 when it needs to be."
            % (name, source, reason)
        )
        return None, None

    evidence = "build base=%s (from %s)" % (base, source)
    return image_is_linuxserver(base), evidence


def environment_map(service):
    """Normalise compose `environment:` (list OR mapping form) to {str: str}."""
    env = service.get("environment")
    result = {}
    if isinstance(env, list):
        for item in env:
            if isinstance(item, str) and "=" in item:
                key, value = item.split("=", 1)
                result[key.strip()] = value.strip()
            elif isinstance(item, str):
                # `- PUID` (pass-through from the host env). NOT statically
                # resolvable: recorded as present-but-unresolved, never as 0.
                result[item.strip()] = None
    elif isinstance(env, dict):
        for key, value in env.items():
            result[str(key).strip()] = None if value is None else str(value).strip()
    return result


# --- Invariant 4 support: the declared scope and the compose mount/user map --
#
# WHY THIS INVARIANT EXISTS (independent review finding IMPORTANT-1, 2026-08-21)
#   Invariants 1-3 read `image:`, `environment:` and `userns_mode:` and NEVER
#   read `volumes:` or `user:`. A reviewer appended four lines to a copy of the
#   real docker-compose.yml —
#
#       attack-writer:
#         image: python:3.12-alpine
#         user: "1000:1000"
#         volumes:
#           - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads
#
#   — and this gate printed PASS, exit 0. That service's writes land at host
#   uid 100999: the reported defect, verbatim, waved through by the gate whose
#   whole job is to make it un-revertable. A well-meaning "don't run containers
#   as root" hardening pass adding `user:` to download-proxy would reintroduce
#   it for `config/` — including the encrypted credential store.
#
#   tasks.md T034 and data-model.md E5 both describe this gate as asserting
#   that every compose service mounting an in-scope path declares a route.
#   Until now it asserted no such thing, so T034 was marked done for a strictly
#   weaker gate than it described. This is the clause that makes the
#   description true.
#
# WHY THE ROUTE IS "RUNS AS CONTAINER ROOT", NOT "keep-id OR PUID=0"
#   E5's table (written before the measurements landed) lists `userns_mode:
#   keep-id` as route A for three services. keep-id was subsequently TRIED and
#   REJECTED — it leaves the container with no usable root and HANGS the
#   linuxserver images (research.md R3), and invariant 2 above now hard-FORBIDS
#   it. The three services E5 assigns to route A were MEASURED to write as host
#   uid 1000 already, for the reason this clause checks: they run as container
#   root, and rootless podman maps container uid 0 to the host operator. So the
#   real route set is {container-root, linuxserver-with-PUID=0}, and this
#   clause asserts the first while invariant 1 asserts the second.

def load_tsv(path, width, label):
    """Read a TAB-separated table, EMPTY FIELDS PRESERVED. [] when unreadable.

    `str.split("\\t")` rather than a shell-style read for the reason recorded on
    split_tsv() in scripts/ownership_precondition.sh: TAB is IFS whitespace, so
    a run of tabs collapses into one delimiter and every later column shifts
    left. A service built from a Dockerfile has no `image:` and often no PUID,
    so its row is exactly the empty-middle-fields shape that bug eats.
    """
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                fields = line.split("\t")
                if len(fields) < width:
                    fields += [""] * (width - len(fields))
                rows.append(fields)
    except OSError as exc:
        finding("%s: could not be read (%s) — the mount/`user:` invariant "
                "asserted NOTHING" % (label, exc))
    return rows


compose_rows = {row[0]: row for row in load_tsv(compose_rows_path, 6, "compose-rows")}
scope_paths = []
for row in load_tsv(scope_rows_path, 5, "scope-rows"):
    declared = row[0].strip()
    if not declared:
        continue
    if not os.path.isabs(declared):
        declared = os.path.join(repo_root, declared)
    declared = os.path.normpath(declared)
    if declared not in scope_paths:
        scope_paths.append(declared)


def path_related(a, b):
    """True when a write inside one lands inside the other.

    Checked in BOTH directions on purpose: a service mounting an ANCESTOR of a
    declared location writes into it (`./config` covers `config/boba.db`), and
    a service mounting a SUBDIRECTORY of one writes into it too
    (`./config/jackett` lands inside the declared `config`). Matching one
    direction would silently drop half the services that can produce files
    there — and this gate exists because a silent drop shipped once already.
    """
    if not a or not b:
        return False
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def user_verdict(raw):
    """Classify a run-as-user declaration. Returns (verdict, detail).

    verdict: 'root' | 'nonroot' | 'unresolvable'

    A value carrying `$` is UNRESOLVABLE, never assumed root: the environment
    that supplies it is not visible here, and reading that silence as "runs as
    root" is the §11.4.201(6) false-null — with the safe reading on the wrong
    side of it.
    """
    value = raw.strip().strip('"').strip("'")
    if "$" in value:
        return "unresolvable", value
    uid = value.split(":", 1)[0].strip()
    if uid in ("0", "root"):
        return "root", value
    return "nonroot", uid


def host_uid_note(uid):
    """The host identity a container uid maps to under rootless podman."""
    if uid.isdigit() and int(uid) > 0:
        return ("Under rootless podman container uid %s maps to host uid %d, "
                "an identity the operator does not have (this is exactly how "
                "PUID=1000 produced host uid 100999)."
                % (uid, 100000 + int(uid) - 1))
    return ("`%s` is a named account inside the image, so the host uid it maps "
            "to is whatever the image assigned it — not the operator." % uid)


NONROOT_REMEDY = (
    "A compose `user:` overrides the image entrypoint's own uid, so a "
    "linuxserver PUID=0 cannot rescue it. Run this service as container root "
    "instead — drop the `user:` key, or declare `user: \"0:0\"`; container "
    "uid 0 maps to the HOST OPERATOR (uid 1000) and grants no host privilege."
)


def check_mount_user(name):
    """Invariant 4 for one service. Records its own INFO or FINDING."""
    if not scope_paths or not compose_rows:
        # Both blind states are already reported once, above, by name. Emitting
        # a per-service echo of the same fact would bury the real finding.
        return
    row = compose_rows.get(name)
    if row is None:
        finding(
            "%s: the shared compose reader produced no row for this service, "
            "so its `volumes:` and `user:` were NEVER READ and the mount "
            "invariant asserted nothing about it. A service this gate cannot "
            "read is exactly where a non-root writer would hide."
            % name
        )
        return

    in_scope = []
    for mount in [m for m in row[4].split(",") if m]:
        for declared in scope_paths:
            if path_related(mount, declared):
                in_scope.append(declared)
                break
    if not in_scope:
        info("%s: mounts nothing in the declared ownership scope — `user:` "
             "not constrained here" % name)
        return

    where = in_scope[0]
    more = "" if len(in_scope) == 1 else " (+%d more declared location(s))" % (len(in_scope) - 1)

    raw_user = row[5]
    if raw_user:
        verdict, detail = user_verdict(raw_user)
        if verdict == "root":
            info("%s: mounts declared scope %s%s and runs as container root "
                 "(user: %s) — writes land at the host operator"
                 % (name, where, more, detail))
            return
        if verdict == "unresolvable":
            finding(
                "%s: mounts the declared location %s%s and declares "
                "`user: %s`, which is not statically resolvable, so it cannot "
                "be proven to run as container root. Declare the identity "
                "inline (`user: \"0:0\"`) or drop the key."
                % (name, where, more, detail)
            )
            return
        finding(
            "%s: mounts the declared location %s%s and declares `user: %s` — "
            "uid %s, which is NOT container-root. %s Every file this service "
            "writes into that location would land at that identity — the FR-011 "
            "defect, reintroduced through `user:` rather than through PUID. %s"
            % (name, where, more, raw_user.strip().strip('"').strip("'"),
               detail, host_uid_note(detail), NONROOT_REMEDY)
        )
        return

    entry = dockerfile_text.get(name)
    if entry is not None:
        text, source = entry
        directive = dockerfile_last_user(text)
        if directive is not None:
            verdict, detail = user_verdict(directive)
            if verdict == "nonroot":
                finding(
                    "%s: mounts the declared location %s%s and its Dockerfile "
                    "(%s) ends with `USER %s`, which is NOT container-root. %s "
                    "The downgrade is in the build rather than in compose, so "
                    "reading only the compose `user:` key would miss it "
                    "entirely. Remove the trailing USER instruction, or add "
                    "`USER root` after it, so the service writes as container "
                    "root."
                    % (name, where, more, source, directive, host_uid_note(detail))
                )
                return
            if verdict == "unresolvable":
                finding(
                    "%s: mounts the declared location %s%s and its Dockerfile "
                    "(%s) ends with `USER %s`, which is not statically "
                    "resolvable, so it cannot be proven to run as container "
                    "root."
                    % (name, where, more, source, directive)
                )
                return
            info("%s: mounts declared scope %s%s and runs as container root "
                 "(Dockerfile USER %s) — writes land at the host operator"
                 % (name, where, more, directive))
            return

    # No compose `user:` and no Dockerfile USER downgrade: the container's
    # process runs as its image default.
    #
    # HONEST GAP (§11.4.6): for an `image:`-based service this gate cannot see
    # a USER baked into an image it has not pulled, so "no declared downgrade"
    # is what is asserted here — not "the image provably runs as root". The
    # runtime half of that question belongs to the P1 container-write probe in
    # scripts/ownership_precondition.sh, which observes the identity a real
    # write actually lands at. Stated rather than papered over: a gate that
    # claimed to have proven the image's built-in USER would be asserting a
    # fact it never read.
    info("%s: mounts declared scope %s%s and runs as container root (no "
         "`user:` downgrade declared) — writes land at the host operator"
         % (name, where, more))


# --- Invariant 3: the declared ownership scope exists and parses -----------
ok, owned = load_yaml(owned_paths_path, "owned-paths")
if ok:
    if owned is None:
        # An empty file parses successfully to None. Reading that as "fine"
        # would be a FALSE-NULL: a blank scope and a healthy scope would
        # return the same quiet success (§11.4.201(6)).
        finding("owned-paths: parsed to EMPTY (%s) — a blank scope is not a "
                "valid scope; the repair would have nothing to repair"
                % owned_paths_path)
    elif not isinstance(owned, dict):
        finding("owned-paths: top level is %s, expected a mapping (%s)"
                % (type(owned).__name__, owned_paths_path))
    else:
        entries = owned.get("paths")
        if not isinstance(entries, list) or not entries:
            finding("owned-paths: `paths:` is missing or empty (%s) — the "
                    "ownership scope declares nothing" % owned_paths_path)
        else:
            bad = [i for i, e in enumerate(entries)
                   if not isinstance(e, dict) or not str(e.get("path") or "").strip()]
            if bad:
                finding("owned-paths: %d entr(y/ies) lack a non-empty `path:` "
                        "key (index %s) in %s"
                        % (len(bad), ", ".join(str(i) for i in bad), owned_paths_path))
            else:
                info("owned-paths: %s parses, %d declared location(s)"
                     % (owned_paths_path, len(entries)))

# --- Compose parse ---------------------------------------------------------
ok, compose = load_yaml(compose_path, "compose")
services = {}
if ok:
    if not isinstance(compose, dict):
        finding("compose: top level is %s, expected a mapping (%s)"
                % (type(compose).__name__, compose_path))
    else:
        raw = compose.get("services")
        if isinstance(raw, dict):
            services = {name: (svc if isinstance(svc, dict) else {})
                        for name, svc in raw.items()}

if ok and not services:
    # A blind parse (wrong key path, mangled file) returns the same empty dict
    # a genuinely service-less compose file would (§11.4.201(6)).
    finding("compose: ZERO services parsed from %s — the instrument is blind, "
            "which is not a clean tree" % compose_path)

info("compose: %s (%d service(s))" % (compose_path, len(services)))

# Invariant 4 coverage, stated BEFORE any per-service line so a reader never
# has to infer from silence whether the mount check ran (§11.4.201(6)).
if services and not compose_rows:
    finding("compose-rows: the shared reader (scripts/lib/ownership.sh "
            "ownership_compose_rows) returned NOTHING while %d service(s) "
            "parsed here — the mount/`user:` invariant is BLIND, and a blind "
            "instrument is not a clean tree" % len(services))
elif services and not scope_paths:
    info("mount/`user:` invariant: NOT RUN — the declared scope yielded no "
         "usable location, so there is nothing to test a mount against (the "
         "owned-paths finding above is the refusal)")
elif services:
    info("mount/`user:` invariant: %d declared location(s) in scope, %d "
         "compose service(s) read for `volumes:` and `user:`"
         % (len(scope_paths), len(compose_rows)))

linuxserver_checked = 0

for name in sorted(services):
    service = services[name]
    image = service.get("image")

    # --- Invariant 2: no service may declare `userns_mode: keep-id` --------
    # Applies to EVERY service, linuxserver or not: keep-id leaves the
    # container with no usable root and hangs it (see the header).
    userns = service.get("userns_mode")
    if isinstance(userns, str):
        normalised = userns.strip().strip('"').strip("'").lower()
        if normalised == "keep-id" or normalised.startswith("keep-id:"):
            finding(
                "%s: declares `userns_mode: %s` — FORBIDDEN. keep-id maps the "
                "host operator's uid straight through, so the container has NO "
                "USABLE ROOT; the linuxserver entrypoint (and the root-running "
                "services) cannot start and the container HANGS. This was "
                "considered and DELIBERATELY REJECTED for every service in this "
                "stack — do not re-add it to make a PUID finding go away."
                % (name, userns)
            )

    is_linuxserver, evidence = classify_service(name, service, image)

    # --- Invariant 4: mount-scope / run-as-user completeness (E5, FR-016) --
    # Runs for EVERY service, before the classification-driven `continue`s
    # below: the reviewer's attack service is not linuxserver-based and has no
    # PUID at all, so a check reachable only on the linuxserver path would
    # never see it.
    check_mount_user(name)

    if is_linuxserver is None:
        # UNVERIFIABLE. classify_service already recorded a finding naming what
        # it tried and why it could not decide. Deliberately NOT counted as
        # checked: an unresolved base has asserted nothing in either direction,
        # and counting it would let it satisfy the "at least one linuxserver
        # service was checked" clause below.
        continue

    if not is_linuxserver:
        # Correct as-is and deliberately unchanged: these run as root already
        # and were MEASURED to write as host uid 1000. Demanding a PUID here
        # would be the false-positive refusal §11.4.201(1) forbids. Reached now
        # only when the base was RESOLVED and found non-linuxserver, never when
        # it merely could not be read.
        info("%s: %s -> not linuxserver-based, PUID not required"
             % (name, evidence))
        continue

    linuxserver_checked += 1
    env = environment_map(service)
    resolved = []
    for key in ("PUID", "PGID"):
        if key not in env:
            finding(
                "%s: linuxserver service (%s) declares NO %s — the image then "
                "runs the app as its `abc` default (uid 911), which rootless "
                "podman maps to host uid 100910, and every file it writes is "
                "unreachable to the operator. Declare %s=0."
                % (name, evidence, key, key)
            )
            continue
        value = env[key]
        if value is None:
            finding(
                "%s: %s is passed through from the host environment and is NOT "
                "statically resolvable, so it cannot be proven to be 0 "
                "(resolved evidence: `%s` with no inline value). Declare %s=0 "
                "inline."
                % (name, key, key, key)
            )
            continue
        if value != "0":
            finding(
                "%s: %s=%s, expected 0. Under rootless podman container uid N "
                "maps to host uid 100000+N-1, so %s=%s makes this linuxserver "
                "service write as an identity the operator does not have "
                "(PUID=1000 -> host uid 100999). Container uid 0 maps to the "
                "HOST OPERATOR (uid 1000) and grants no host privilege."
                % (name, key, value, key, value)
            )
            continue
        resolved.append("%s=%s" % (key, value))

    if len(resolved) == 2:
        info("%s: %s -> linuxserver, %s OK" % (name, evidence, ", ".join(resolved)))

if services and linuxserver_checked == 0:
    # Distinguishable from the blind-parse case above (services WERE parsed),
    # but still refused rather than silently passed: the PUID clause is the
    # load-bearing half of FR-011, and deleting the services or retagging their
    # images is precisely the revert shape this gate exists to catch. If boba
    # has genuinely migrated off linuxserver images, this clause must be
    # RE-DERIVED against the new images, never deleted (§11.4.201(4)/(6)).
    finding("compose: %d service(s) parsed but ZERO are linuxserver-based, so "
            "the PUID=0 clause asserted NOTHING. If the images genuinely "
            "changed, re-derive this clause against them — do not delete it."
            % len(services))

for line in infos:
    sys.stdout.write("INFO %s\n" % line)
for line in findings:
    sys.stdout.write("FINDING %s\n" % line)

sys.exit(1 if findings else 0)
PY_EOF
ANALYZER_RC=$?
set -e

if [[ "${ANALYZER_RC}" -gt 1 ]]; then
    # A traceback (or any non-{0,1} exit) means the analyzer itself broke.
    # Reported as FAIL, not swallowed: a crashed instrument is not a clean
    # tree (§11.4.1 — a script-bug failure must never read as a product PASS).
    echo "${GATE_NAME}: analyzer exited ${ANALYZER_RC} — the instrument itself failed" >&2
    sed 's/^/        /' "${ANALYZER_OUT}" >&2
    echo "FAIL: ${GATE_NAME} could not complete" >&2
    exit 1
fi

echo "${GATE_NAME}: scope"
grep '^INFO ' "${ANALYZER_OUT}" | sed 's/^INFO /  /' || true

FINDING_COUNT="$(grep -c '^FINDING ' "${ANALYZER_OUT}" || true)"
if [[ "${FINDING_COUNT}" -gt 0 ]]; then
    {
        echo
        echo "=== FINDINGS ==="
        grep '^FINDING ' "${ANALYZER_OUT}" | sed 's/^FINDING /  - /'
        echo
        echo "FAIL: ${FINDING_COUNT} ownership-invariant violation(s) (${GATE_NAME}, FR-011)"
        echo "      The operator-owned-writes fix has been weakened or reverted."
    } >&2
    exit 1
fi

echo "PASS: ${GATE_NAME} — linuxserver PUID/PGID=0, no userns_mode keep-id, ownership scope declared, every in-scope mounter runs as container root"
exit 0
