# BOB-140 — CM-HEALTHCHECK-COVERS-SERVED-PORTS upstreamed into the constitution: closure evidence

**Revision:** 1
**Last modified:** 2026-08-20T15:36:36Z

## What BOB-140 asked for

`scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh` (landed with
BOB-138) implemented a rule every project under this constitution needs — a
container health check MUST cover every port its service serves, because a
check probing a subset asserts a proxy signal instead of the real condition
(§11.4.201). Its detection logic already carried zero boba literals, so per
§11.4.177 / §11.4.28 / §11.4.74 it belongs in the constitution and must be
consumed BY REFERENCE, with boba shipping a thin delegator holding only scope
DATA (§11.4.35).

The deferral was deliberate and tracked, not an oversight: a concurrent agent
was editing `constitution/scripts/gates/` at the time, and two writers in one
submodule directory risks losing work (§11.4.197). That directory was clean at
constitution HEAD `997d48f` when this work began.

## What landed

| File | Role |
|---|---|
| `constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh` | NEW — the universal detection ENGINE |
| `constitution/scripts/gates/cm_healthcheck_covers_served_ports_mutation_test.sh` | NEW — the paired §1.1 mutation test |
| `scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh` | CONVERTED — thin delegator, scope DATA only |

`config/served_ports.yaml` needed no change: the manifest schema the engine
consumes is exactly the one boba already declared.

The engine's interface is `--compose <file> --manifest <file> [--quiet]`, with
`HEALTHCHECK_PORTS_COMPOSE` / `HEALTHCHECK_PORTS_MANIFEST` /
`HEALTHCHECK_PORTS_PYTHON` env equivalents. It carries **no** project literal
and refuses (exit 2) rather than guessing a consumer's paths.

## The two properties that had to survive the move

Both are load-bearing. Each is now a property of the ENGINE, asserted by the
engine's own mutation test rather than by prose:

1. **Zero services checked ⇒ FAIL.** A quiet zero from a blind instrument is
   indistinguishable from a clean tree (§11.4.201(6)). Two independent routes
   are covered: an empty manifest, and a manifest whose every `serves` list is
   empty (an implementation counting skipped entries as "checked" would pass
   the second).
2. **No python with PyYAML ⇒ FAIL, never SKIP.** Without a parser the gate
   cannot assert anything; §11.4.201(4)'s conservative-safe outcome is to
   refuse and say so honestly.

Neither degraded. Evidence for both is pasted below (sections D and E), taken
through the delegator on boba's real tree.

## A. Output equivalence with the pre-move implementation

Both spellings run against the same real compose file and manifest. The old
implementation is `git show HEAD:` of the pre-conversion script, run with
explicit paths (a copy outside the repo cannot derive boba's `PROJECT_ROOT`).

```
old rc=0
new rc=0
--- stdout diff (empty == byte-identical) ---
STDOUT IDENTICAL
--- stderr diff ---
STDERR IDENTICAL
--- md5 ---
bd38e61fe453938dd28fb971c927c5cb  /tmp/out_old.txt
bd38e61fe453938dd28fb971c927c5cb  /tmp/out_new.txt
```

The invocation contract is therefore preserved exactly: same path, same optional
positional `[COMPOSE_FILE] [MANIFEST]`, same exit codes, same `PASS:` / `FAIL:`
line shapes, and the PASS line is still **last** — which matters, because
pre-build invariant 44 reads it with `tail -n1`.

## B. Delegator on boba's real tree

```
$ bash scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh
  ok  qbittorrent: healthcheck covers all served ports [7185]
  ok  jackett: healthcheck covers all served ports [9117]
  ok  download-proxy: healthcheck covers all served ports [7186, 7187]
  ok  qbittorrent-proxy-go: healthcheck covers all served ports [7187]
  ok  boba-jackett: healthcheck covers all served ports [7189]
CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS (5 services verified)
rc=0
```

## C. Paired §1.1 mutation test — both directions

13 fixtures, 11 FAIL-on-mutation and 2 PASS-on-clean negative controls.

```
======================================================================
§1.1 paired-mutation meta-test for CM-HEALTHCHECK-COVERS-SERVED-PORTS
anchors: §11.4.201 (guard asserts the real condition) / §11.4.254
fixtures under: /tmp/.private/milosvasic/hcports_mut.thRv7J
======================================================================
✅ META OK:   BOB-138 literal shape (serves 7186+7187, probes only 7186) — gate correctly FAILed on the mutation
✅ META OK:   BOB-138 fixed shape (health check probes BOTH served ports) — gate correctly PASSed on clean fixture
✅ META OK:   declared service with NO healthcheck at all — gate correctly FAILed on the mutation
✅ META OK:   substring near-miss (serves 7187, probes 71870 — must NOT match inside) — gate correctly FAILed on the mutation
✅ META OK:   UNDECLARED compose service with a healthcheck + ports — gate correctly FAILed on the mutation
✅ META OK:   STALE manifest entry (declared but absent from the compose file) — gate correctly FAILed on the mutation
✅ META OK:   ZERO services checked (empty manifest) — blind, not clean — gate correctly FAILed on the mutation
✅ META OK:   ZERO services checked (all 'serves' lists empty) — blind, not clean — gate correctly FAILed on the mutation
✅ META OK:   no python with PyYAML — BLIND gate must FAIL, not skip — gate correctly FAILed on the mutation
✅ META OK:   missing compose file (blind input) — gate correctly FAILed on the mutation
✅ META OK:   missing manifest file (blind input) — gate correctly FAILed on the mutation
✅ META OK:   negative control: every service fully covered (list + string test forms) — gate correctly PASSed on clean fixture
✅ META OK:   negative control: port-less worker absent from manifest is not 'undeclared' — gate correctly PASSed on clean fixture
======================================================================
✅ META PASS — CM-HEALTHCHECK-COVERS-SERVED-PORTS FAILs-on-mutation AND PASSes-on-clean for every fixture (§1.1 proof holds)
META rc=0
```

The two negative controls exist because §11.4.201(1) makes a false-positive
refusal a FAIL-bluff exactly as a false pass is a PASS-bluff. Control 1 is a
multi-service fixture where every health check legitimately covers all its
served ports, exercising both `test:` spellings (list form and bare string
form) plus a genuine multi-port probe. Control 2 pins the undeclared-service
rule's boundary: a port-less worker absent from the manifest publishes nothing
and must not be reported.

## D. Zero-services case, through the delegator

```
$ bash scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh "$T/compose.yml" "$T/manifest.yml"
CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — checked 0 services; the gate is blind (empty manifest or no matching services), not clean
rc=1  <-- MUST be 1 (blind, not clean)
```

## E. Missing-PyYAML case, through the delegator

The delegator's interpreter candidates include an **absolute** `.venv/bin/python`
path, so `PATH` shadowing alone cannot reach it. The fixture therefore builds a
throw-away project root containing the real delegator, the real constitution
(by symlink) and byte-identical copies of the real compose file and manifest —
but no `.venv`, so every candidate is `PATH`-reachable and shadowable. The
sanity run proves the fixture PASSes with a real interpreter first, so the
subsequent FAIL is attributable to the interpreter and nothing else.

```
Sanity: this throw-away root PASSes with a real interpreter —
CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS (5 services verified)
  rc=0

Now shadow python3/python with interpreter-shaped executables that have no PyYAML.
ONLY the interpreter changes — the compose file and manifest are byte-identical.
CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — no python interpreter with PyYAML available
  tried:  /tmp/.private/milosvasic/tmp.JMcPyCC3d7/root/.venv/bin/python python3 python
  the gate cannot parse the compose file, so it cannot assert anything.
  This is a BLIND gate, not a clean tree (§11.4.201(6)).
  rc=1  <-- MUST be 1: a BLIND gate FAILs, it never skips and never passes
```

## F. Real mutation on boba's own compose file, through the delegator

Reverting the download-proxy health check to its exact pre-BOB-138 state — one
line changed, nothing else — must be refused.

```
--- the ONLY difference from the real compose file ---
230c230
<       test: ["CMD-SHELL", "python -c \"import urllib.request as u; u.urlopen('http://localhost:7186/', timeout=5); u.urlopen('http://localhost:7187/health', timeout=5)\" || exit 1"]
---
>       test: ["CMD-SHELL", "python -c \"import urllib.request as u; u.urlopen('http://localhost:7186/', timeout=5)\" || exit 1"]

--- delegator against the MUTATED compose (real manifest, unchanged) ---
CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL
  - download-proxy: serves [7186, 7187] but its healthcheck probes none of [7187]
      healthcheck: CMD-SHELL python -c "import urllib.request as u; u.urlopen('http://localhost:7186/', timeout=5)" || exit 1
      -> a dead port in [7187] reports HEALTHY forever (§11.4.201 proxy signal)
  ok  qbittorrent: healthcheck covers all served ports [7185]
  ok  jackett: healthcheck covers all served ports [9117]
  ok  qbittorrent-proxy-go: healthcheck covers all served ports [7187]
  ok  boba-jackett: healthcheck covers all served ports [7189]
  rc=1  <-- MUST be 1

--- G. paired control: same command, UNMUTATED compose ---
  ok  qbittorrent: healthcheck covers all served ports [7185]
  ok  jackett: healthcheck covers all served ports [9117]
  ok  download-proxy: healthcheck covers all served ports [7186, 7187]
  ok  qbittorrent-proxy-go: healthcheck covers all served ports [7187]
  ok  boba-jackett: healthcheck covers all served ports [7189]
CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS (5 services verified)
  rc=0  <-- MUST be 0
```

## H. No duplicated detection logic (§11.4.177)

The delegator's complete executable body — 19 lines, comments and blanks
stripped — is engine resolution, scope DATA and one `exec`:

```
     1	set -euo pipefail
     2	SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
     3	PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
     4	CONST_GATE="${PROJECT_ROOT}/constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh"
     5	if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
     6	    sed -n '2,80p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
     7	    exit 0
     8	fi
     9	if [[ ! -f "$CONST_GATE" ]]; then
    10	    echo "CM-HEALTHCHECK-COVERS-SERVED-PORTS: ERROR — shared gate engine missing: $CONST_GATE" >&2
    11	    echo "  (§11.4.177 — this gate is consumed by reference; run" >&2
    12	    echo "   'git submodule update --init constitution' to restore it)" >&2
    13	    exit 2
    14	fi
    15	COMPOSE_FILE="${1:-${PROJECT_ROOT}/docker-compose.yml}"
    16	MANIFEST="${2:-${PROJECT_ROOT}/config/served_ports.yaml}"
    17	PY_CANDIDATES="${PYTHON_BIN:-} ${PROJECT_ROOT}/.venv/bin/python python3 python"
    18	exec env HEALTHCHECK_PORTS_PYTHON="$PY_CANDIDATES" \
    19	    bash "$CONST_GATE" --compose "$COMPOSE_FILE" --manifest "$MANIFEST"
```

Detection-primitive census over executable lines only:

| primitive | delegator | engine |
|---|---|---|
| `yaml` | 1 | 5 |
| `safe_load` | 0 | 2 |
| `re.search` | 0 | 1 |
| `healthcheck` | 1 | 7 |
| `serves` | 0 | 6 |
| `PYEOF` | 0 | 2 |
| `UNDECLARED` | 0 | 1 |
| `findings` | 0 | 7 |
| `checked` | 0 | 5 |

The delegator's two non-zero counts are **file paths, not logic**:
`config/served_ports.yaml` on line 16 and the engine filename on lines 4 and 10.
Every detection primitive lives in exactly one place.

## I. Invariant 44 wiring intact

`scripts/pre_build_verification.sh` was **not** edited. Its exact code path,
replayed:

```
CONST_GATE_TIMEOUT = 300s
  ✅ PASS  CM-HEALTHCHECK-COVERS-SERVED-PORTS: CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS (5 services verified)
           (747ms, well inside the 300s budget)
```

The doubled gate name is pre-existing formatting in invariant 44's `pass` call,
not a regression — it prefixes the label onto `tail -n1` of the gate's own
output, and the gate's output has always begun with its own name.

## Syntax checks

```
engine bash -n OK
mutation-test bash -n OK
delegator bash -n OK
```

## Honest boundary (§11.4.6)

Stated as facts, not assumed:

- **`PYTHON_BIN` semantics changed, deliberately and for the stronger.** The old
  script trusted a set `PYTHON_BIN` on sight, with no `import yaml` probe. It is
  now the first candidate but is probed like any other, so a `PYTHON_BIN`
  lacking PyYAML falls through to the next candidate instead of failing
  confusingly downstream (§11.4.201(11): probe the artifact through its real
  invocation path). This is documented in the delegator header, not silent.
- **A new exit code 2 exists** for a missing engine or an engine usage error.
  Invariant 44 treats any non-zero, non-124 status as FAIL, so a missing
  constitution submodule blocks the build rather than passing — the correct
  direction. Exit codes 0 and 1 are unchanged.
- **Docker-compose parsing is unchanged**, including the shape it does not
  handle: the engine reads `services.<name>.healthcheck.test` and
  `services.<name>.ports` from a single compose file. It does not resolve
  `extends`, multi-file overlays, or profiles. That limit existed before this
  move and is not newly introduced; it is not currently exercised by boba.
- **The mutation test needs PyYAML to run.** If absent it exits 2 (environment
  error), never 0 — an unseeing meta-test must not report success.
- **`docs/scripts/check_cm_healthcheck_covers_served_ports.md` does not exist.**
  §11.4.18 requires a companion user guide for every shell script. This gap
  pre-dates BOB-140 (the pre-move script's header cross-referenced the document
  as though it existed). The delegator's header now states the gap honestly
  instead of citing a non-existent file; boba has no `CM-SCRIPT-DOCS-SYNC`
  invariant wired in `scripts/pre_build_verification.sh`, so nothing mechanical
  catches it. **This remains open and is not claimed closed** — `docs/scripts/`
  is outside this work item's file ownership, so it was not created here.
- **Nothing was committed or pushed** in either repository, and no container was
  restarted, per this work item's scope.

## Verdict

CM-HEALTHCHECK-COVERS-SERVED-PORTS now lives in the constitution as a
project-agnostic engine with a paired §1.1 mutation test proving both
polarities; boba consumes it by reference through a 19-line delegator carrying
only scope DATA; the invocation contract and output are byte-identical to the
pre-move implementation; and both load-bearing FAIL properties — zero services
checked, and no usable YAML parser — survive the move, proven end-to-end
through the delegator.
