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
#         and is non-empty.
#
#   Each refusal names the SERVICE and WHAT was wrong, and prints the resolved
#   evidence it refused on (§11.4.201(5)).
#
# FORENSIC ANCHOR (measured on this host, 2026-08-21, research.md R6):
#   The stack runs under ROOTLESS podman, which maps container uid N to host
#   uid 100000+N-1 and container uid 0 to the HOST OPERATOR (uid 1000).
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
#   default (uid 911 -> host 101910) and reproduce the defect while this gate
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
#   PASSED this gate (exit 0) while its writes would land at host uid 101910 —
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
#   `abc` (911) and the host sees 101910 — the exact defect class, arrived at
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
# Dependencies: bash, python3 with PyYAML.
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
# REGISTRATION STATUS — WIRED AND BLOCKING (verified, §11.4.196(F)):
#   scripts/pre_build_verification.sh runs this gate as invariant
#   `[33/44] CM-OWNERSHIP-INVARIANTS` (the block immediately preceding that
#   file's FULL_VALIDATION section). It invokes this script with no arguments,
#   reports the verdict with `tail -n1`, and routes a non-zero exit through
#   `fail` — so a finding BLOCKS the build rather than warning.
#
#   This paragraph previously read "EXECUTABLE AND HONEST BUT NOT YET WIRED",
#   describing a §11.4.196(F) configured-vs-in-use gap that had since been
#   closed. It was corrected on 2026-08-21 after re-reading the runner rather
#   than trusting the claim: a gate whose entire purpose is honesty may not
#   carry a false statement about itself, and a stale "not wired" note is the
#   §11.4.6 failure in the direction that makes the gate look weaker than it
#   is — which invites someone to "finally wire it" and land a duplicate block.
#
#   KNOWN, NOT INTRODUCED HERE (§11.4.261 tracked, not absorbed): the literal
#   `33/44` is now carried by TWO blocks in that runner — this one and
#   `run_const_gate "33/44" "CM-CLI-AGENT-PLUGINS-WIRED"`. The slot was free
#   when this gate claimed it and a concurrently-landed gate took the same
#   number. Both blocks execute; only the printed label collides. Renumbering
#   belongs to whoever owns pre_build_verification.sh (out of this file's
#   scope), together with that file's pre-existing 35-invariants-vs-44-
#   denominator mismatch. Recorded here so the next reader is not misled by a
#   duplicated label into thinking one of the two gates does not run.
#
# Cross-references:
#   specs/002-user-owned-downloads/ FR-011 (this gate's requirement),
#   config/owned_paths.yaml (which already names this file as its consumer),
#   scripts/lib/ownership.sh + scripts/ownership_precondition.sh +
#   scripts/ownership_repair.sh (the runtime half of the same contract),
#   tests/pre_build/test_check_cm_ownership_invariants.sh (its §1.1 paired
#   mutation), scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh
#   (the sibling whose structure this file follows).
#   §11.4.1 §11.4.6 §11.4.18 §11.4.35 §11.4.69 §11.4.107(10) §11.4.108
#   §11.4.115 §11.4.135 §11.4.201 §11.4.226 §11.4.238 §11.4.263.

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

ANALYZER_OUT="$(mktemp)"
trap 'rm -f "${ANALYZER_OUT}"' EXIT

set +e
"${PY}" - "${COMPOSE_FILE}" "${OWNED_PATHS_FILE}" "${REPO_ROOT}" >"${ANALYZER_OUT}" 2>&1 <<'PY_EOF'
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
compose_dir = os.path.dirname(os.path.abspath(compose_path))

findings = []
infos = []


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


def dockerfile_stages(text):
    """Parse a Dockerfile into ([(base_ref, alias_lower_or_None)], global_args).

    Token-structural, not a substring scan: comment lines are dropped and
    backslash continuations are joined BEFORE any instruction is read, so a
    Dockerfile comment merely MENTIONING an image reference is invisible.
    Only ARGs declared before the first FROM are collected — those are the only
    ones Docker permits a FROM line to reference.
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
                "podman maps to host uid 101910, and every file it writes is "
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

echo "PASS: ${GATE_NAME} — linuxserver PUID/PGID=0, no userns_mode keep-id, ownership scope declared"
exit 0
