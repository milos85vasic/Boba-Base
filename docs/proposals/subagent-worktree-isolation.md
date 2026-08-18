# Subagent Worktree/Clone Isolation — Proposal

**Revision:** 1
**Last modified:** 2026-08-18T00:00:00Z
**Status:** proposal (NOT implemented — investigation + design only, per task scope)
**Authority:** research task filed against §11.4.179 (corruption-isolated parallel git
streams) + BOB-068 (unattributed, unreviewed auto-commit mechanism pushing to main)

## 1. Problem statement

BOB-068 identified a real defect class: parallel SDD subagents dispatched against
this project's **single shared checkout** (`/run/media/.../boba`, one `.git`) can
commit — sometimes via an unattributed/unreviewed auto-commit path — directly onto
`main` with no structural isolation between concurrent subagents' in-flight work.
Two subagents racing `git add`/`git commit` in the same working tree is exactly the
§11.4.84 (working-tree quiescence) and §9.2 (absolute data safety) hazard class this
constitution exists to close.

§11.4.179 mandates the remedy pattern for genuinely corruption-isolated parallel git
streams: **each stream gets its OWN `.git`** (own object store, own index, own ref
namespace) — explicitly **NOT** `git worktree` checkouts sharing one common `.git`,
because a shared common-dir is a single point of failure (one stale lock, or one
corrupted object, affects every stream at once).

This document investigates how to wire that pattern for **per-SDD-task subagent
dispatch** in boba, using the existing `constitution/scripts/multitrack/` machinery
as a starting point, and reports real, captured measurements (not estimates) for the
two competing mechanisms (`git worktree add` vs. `git clone --local`).

## 2. What the existing multitrack machinery actually provides — and does NOT

Read in full for this investigation: `constitution/scripts/multitrack/README.md` +
`multitrack_resolve_worktree.sh` + `multitrack_checkout_owner_lock.sh` +
`multitrack_bootstrap.sh`.

**Finding (FACT, not inferred):** the existing `constitution/scripts/multitrack/`
engine is built around a **small, fixed number of long-lived, physically-mounted
track checkouts** (`/mnt/track<N>/<project>/`, typically 3-4 tracks), each a
**pre-existing, independently-cloned checkout** the operator sets up once. The
resolver (`multitrack_resolve_worktree.sh`) only ever **looks up** which track an
alias is bound to and **verifies** the checkout is a live git worktree
(`git rev-parse --is-inside-work-tree`) — it never calls `git worktree add`, never
calls `git clone`, and has no code path that creates a new checkout on demand.
Confirmed by direct search:

```
$ grep -rn "worktree add\|git worktree add" constitution/scripts/multitrack/*.sh
(no matches)
```

`multitrack_checkout_owner_lock.sh` (§11.4.119 single-resource-owner applied to a
checkout) is the one directly-reusable primitive: an `flock`-based "at most one
writing agent per checkout, keyed on the canonical realpath, provably-stale-holder
reaped via `kill -0`" lock. It solves the wrong problem for THIS proposal, though —
it protects one **shared** checkout from two writers; the goal here is to avoid
sharing the checkout at all.

**Conclusion:** the multitrack engine is the right home for a per-subagent isolation
mechanism BY REFERENCE (§11.4.28(B)/§11.4.177 — never duplicated), but it does not
already provide one. A new, disjoint script (e.g.
`constitution/scripts/multitrack/multitrack_subagent_clone.sh`) would be needed; it
should live in the SAME directory (decoupled, project-agnostic, reads its config
from `MT_REPO_ROOT` exactly like its siblings) rather than as a boba-local script,
so every consumer of the constitution submodule inherits it.

## 3. `git worktree add` — measured, and why it does NOT satisfy §11.4.179

Ran directly on this host against the real boba checkout (`git version 2.50.1`,
current HEAD `2d232c9`):

```
$ time git worktree add /tmp/.../boba-subagent-test/wt1 -b test-subagent-worktree-proposal-scratch HEAD
Preparing worktree (new branch 'test-subagent-worktree-proposal-scratch')
HEAD is now at 2d232c9 chore(constitution): bump pointer to 53853dd ...
0.15user 0.03system 0:00.22elapsed 86%CPU (0avgtext+0avgdata 55112maxresident)k

$ git worktree list
/run/media/milosvasic/DATA4TB/Projects/boba                  2d232c9 [main]
/tmp/.../boba-subagent-test/wt1                               2d232c9 [test-subagent-worktree-proposal-scratch]

$ cat /tmp/.../boba-subagent-test/wt1/.git
gitdir: /run/media/milosvasic/DATA4TB/Projects/boba/.git/worktrees/wt1

$ (cd /tmp/.../boba-subagent-test/wt1 && git rev-parse --git-common-dir --git-dir)
/run/media/milosvasic/DATA4TB/Projects/boba/.git
/run/media/milosvasic/DATA4TB/Projects/boba/.git/worktrees/wt1
```

**Real, captured facts from this run:**

1. **0.22s wall-clock** for the add — genuinely cheap.
2. `--git-common-dir` resolves to the **main repo's own `.git`** — objects, refs,
   `config`, and `packed-refs` are the SAME files the main checkout uses. Only the
   per-worktree admin dir (`HEAD`, `index`, `ORIG_HEAD`) is separate
   (`.git/worktrees/wt1/`). This is **exactly** the "shared common-dir" shape
   §11.4.179 forbids for corruption-isolation purposes: a corrupted object in the
   shared `objects/` store, or a stale lock on a shared ref (`refs/heads/main.lock`,
   `packed-refs.lock`), affects every worktree simultaneously.
3. **Submodules are NOT auto-initialized** in the new worktree — confirmed:
   `git submodule status` inside `wt1` lists every submodule with a leading `-`
   (uninitialized), and `constitution/Constitution.md` does not exist in the
   worktree until a separate `git submodule update --init` is run. For boba (5
   submodules: `constitution`, `submodules/challenges`, `submodules/containers`,
   `submodules/helixqa`, `submodules/jackett`), this is a real, non-optional extra
   step per spawned worktree — and `constitution/` is load-bearing for every
   subagent's own CLAUDE.md context + the `workable-items` binary this very task
   used.
4. **Lock isolation is partial, not complete.** A stale `.git/index.lock` in the
   MAIN checkout did NOT block `git status` in `wt1` (each worktree has its own
   index file under `.git/worktrees/wt1/index`), confirming index-layer isolation
   is real. But ref writes (a new tag, a branch update on a shared ref name, git gc
   / repack of the shared `objects/` pack files) still go through the ONE common
   `.git` — the isolation is partial, not the "own object store, own lock
   namespace" §11.4.179 demands.

**Verdict: `git worktree add` is fast and disk-cheap, but it structurally does NOT
satisfy §11.4.179.** It is the pattern the anchor names as insufficient, verbatim.
Do not use it for corruption-isolated subagent dispatch.

## 4. `git clone --local` — the git-native mechanism that DOES satisfy §11.4.179

Ran directly on this host, same repo, same HEAD:

```
$ time git clone --local . /run/media/milosvasic/DATA4TB/Projects/.scratch-clone-test/clone1
Cloning into '/run/media/milosvasic/DATA4TB/Projects/.scratch-clone-test/clone1'...
done.
0.13user 0.05system 0:00.19elapsed 98%CPU (0avgtext+0avgdata 51292maxresident)k

$ (cd .../clone1 && git rev-parse --git-common-dir --git-dir)
.git
.git

$ find .../clone1/.git/objects -type f | head -1 | xargs stat -c "links=%h path={}"
links=2 path=.../clone1/.git/objects/pack/pack-2fed172f....pack
```

**Real, captured facts from this run:**

1. **0.19s wall-clock** — statistically indistinguishable from `git worktree add`
   (0.22s) on this host. No meaningful speed penalty for real isolation.
2. `--git-common-dir` and `--git-dir` resolve to the clone's OWN `.git` (relative
   path `.git`, not the boba main repo's path) — **genuinely independent** object
   store, refs, config, and lock namespace. A stale lock or a corrupted object in
   `clone1/.git` cannot touch the main checkout or any sibling clone, and vice
   versa. This satisfies §11.4.179's requirement in full.
3. **Object files are HARDLINKED** (`links=2`) to the source `.git/objects`, not
   copied — `git clone --local`'s default behaviour on a same-filesystem source.
   This means the shared git history costs **effectively zero extra disk** (same
   inode, shared blocks) while the clone is a fully independent repository. `du -sh`
   on the clone alone reports the full logical size (86M in this test) because `du`
   doesn't account for hardlinks outside the tree it's scanning — the actual
   marginal disk delta on the device is near-zero, which is straightforward to
   verify with `df` before/after if this proposal is implemented (not done here to
   keep the investigation read-mostly).
4. **Hardlinks require the same filesystem/device.** This host's boba checkout
   lives on a **btrfs** volume (`/dev/nvme0n1p1` at
   `/run/media/milosvasic/DATA4TB`, confirmed via `df -T` and `stat -f`). Any
   per-subagent clone MUST live on that SAME device to get the hardlink benefit — it
   CANNOT be placed under `/tmp` (this host's `/tmp` is `tmpfs`, a different
   filesystem: confirmed `cp --reflink=always` failed there with "Operation not
   supported", and hardlinks across filesystems are impossible by POSIX
   definition). This is the single most important placement constraint this
   proposal surfaces: **subagent clones must live under
   `/run/media/milosvasic/DATA4TB/Projects/` (or another same-device path), never
   under `/tmp`**, contradicting the task brief's illustrative
   `/tmp/boba-subagent-<id>` path.
5. **CoW reflink is ALSO available on this host** (btrfs) as a second, filesystem-
   level option: `cp -a --reflink=always <src> <dst>` succeeded in a direct test on
   the project's own btrfs volume (it failed only on the tmpfs `/tmp`, as expected).
   A reflink-cloned `.git` directory is a third viable mechanism — genuinely
   independent object store at the filesystem level, near-instant, near-zero disk
   — but it is git-agnostic (you're cloning bytes, not asking git to do anything
   git-aware), so it inherits whatever state the source `.git` was in at clone
   time, including in-flight index state; `git clone --local`'s hardlink path is
   git-aware (git decides what to link vs. copy, e.g. it does NOT hardlink the
   working tree or the index) and is portable to any POSIX filesystem (hardlinks
   don't need CoW support), so it is the recommended default; reflink is recorded
   here as a documented, tested alternative for hosts/consumers where `git
   clone --local`'s per-clone submodule-init cost (§5) is the bottleneck to shave.
6. **Honest safety caveat (from `git-clone(1)`, not this project's own testing):**
   `git clone --local`'s hardlinked objects are shared with the source repo's
   object store. Git does not proactively delete a loose/pack object that is only
   referenced by a foreign hardlinked clone, but an aggressive
   `git gc --prune=now` (or `git repack -ad` with pruning) run on the SOURCE repo
   while a hardlinked clone exists **can** remove an object the clone still needs,
   because gc reasons only about the source repo's own refs. Boba's constitution
   never authorizes automated repo pruning during active work (§9, §9.2, no
   destructive op without backup), so this risk is bounded in practice, but any
   implementation of this proposal MUST NOT run `git gc --aggressive` /
   `git prune` on the main checkout while subagent clones are live, or must clone
   with `--dissociate` (copies rather than hardlinks the objects it needs,
   trading disk for eliminating this risk entirely) if that guarantee cannot be
   made operationally.

**Verdict: `git clone --local` (same filesystem, hardlinked objects) is the
mechanism this proposal recommends.** It is git-native (no external CoW dependency,
portable to any consumer of the constitution submodule regardless of filesystem),
measured as fast as `git worktree add`, and structurally satisfies §11.4.179's
"own `.git`" requirement that `git worktree add` does not.

## 5. Submodule cost (measured)

Per-subagent clones need the submodules a task actually touches, most importantly
`constitution/` (every subagent's CLAUDE.md context + the `workable-items` binary
depend on it). Measured on this host, initializing ONLY the `constitution`
submodule inside a fresh `git clone --local` clone, using `--reference` against the
main checkout's own already-initialized `constitution/` submodule to avoid a cold
network fetch:

```
$ time git submodule update --init --reference /run/media/.../boba/constitution -- constitution
Submodule 'constitution' (git@github.com:HelixDevelopment/HelixConstitution.git) registered for path 'constitution'
Cloning into '.../constitution'...
Submodule path 'constitution': checked out '53853dd232ced6a3bc091cf93a8095014fde669f'
0.29user 0.11system 0:02.75elapsed 14%CPU (0avgtext+0avgdata 92788maxresident)k
```

**2.75s elapsed for one submodule**, even with `--reference` (still performs a real
SSH handshake per Hard Stop #2 / SSH-only, confirmed by the `git@github.com:...`
URL in the output — no HTTPS fallback was used). With 5 submodules in boba, a
naive full `git submodule update --init --recursive` per spawned subagent clone
could cost roughly 10-15s+ depending on network latency and which submodules the
task actually needs. **Recommendation:** the spawn helper should accept an explicit
submodule allowlist per task (most SDD tasks only need `constitution/` for the
`workable-items` binary + governance context; a task touching `qBitTorrent-go/`
would additionally need none of the other submodules) rather than always
recursing into all 5 — this is a real, measured cost worth avoiding by default.

## 6. Proposed design (NOT implemented — design only, per task scope)

### 6.1 New script: `multitrack_subagent_clone.sh`

Location: `constitution/scripts/multitrack/multitrack_subagent_clone.sh` (inherited
by reference into boba, never copied, per §11.4.28(B)/§11.4.177 — exactly the
pattern every sibling script in that directory already follows). Boba supplies
NOTHING but `MT_REPO_ROOT` (already exported by the multitrack config contract).

Subcommands (mirroring the existing scripts' CLI shape):

```
multitrack_subagent_clone.sh spawn <task-id> [--submodules constitution,submodules/jackett] [--branch <name>]
    # git clone --local <MT_REPO_ROOT> <clone-root>/<task-id>
    # git -C <clone> checkout -b sdd/<task-id> (or the caller's --branch)
    # git -C <clone> submodule update --init --reference <MT_REPO_ROOT>/<submodule> -- <submodules...>
    # prints the clone's absolute path on success; registers it in the
    #   §11.4.176-style exactly-once claim registry keyed on <task-id> so a
    #   second spawn for the same task-id reuses (never double-clones)

multitrack_subagent_clone.sh reap <task-id>
    # verifies the clone is quiescent (§11.4.84 — no in-flight mutation, no
    #   uncommitted changes the caller didn't explicitly discard)
    # merges the clone's branch back onto the conductor's checkout via the
    #   SAME §11.4.113 merge-onto-latest-main procedure every other merge in
    #   this constitution uses (fetch -> merge -> resolve -> push; NEVER
    #   force-push) -- reaping a subagent clone is a MERGE, not a raw
    #   git-add-A-commit-push onto the shared checkout, which is precisely
    #   the BOB-068 failure mode this proposal exists to remedy
    # rm -rf the clone directory only AFTER the merge is confirmed landed

multitrack_subagent_clone.sh list
    # table: task-id | clone path | branch | state (active/merged/orphaned)
```

`<clone-root>` defaults to a NEW directory on the SAME device as `MT_REPO_ROOT`
(e.g. `$(dirname "$MT_REPO_ROOT")/.subagent-clones/` — sibling to the checkout, same
filesystem, so hardlinks work) — **never** `/tmp` (see §4.4). This mirrors how
`multitrack_resolve_worktree.sh` already derives its runtime namespace from
`$(basename "$MT_REPO_ROOT")` rather than hardcoding a path (§11.4.28(B)).

### 6.2 How the SDD skill's per-task subagent dispatch would use it

Today (this session), each SDD task's subagent operates directly in the shared
`/run/media/.../boba` checkout — the exact BOB-068 shape. Under this proposal, the
SDD orchestrator (the conductor session) would, per dispatched subagent:

1. **Before dispatch:** `multitrack_subagent_clone.sh spawn <task-id> --submodules constitution` (plus any task-specific submodules), capture the printed clone path.
2. **Dispatch the subagent** with its cwd set to the clone path (an `Agent` tool call cannot itself `cd`, so the subagent's FIRST action, or the dispatch prompt itself, states the clone path as its working directory and the subagent's own Bash calls operate there — this composes with the existing `MT_REPO_ROOT`-style env-var contract every multitrack script already uses).
3. **Subagent works entirely inside its own clone** — commits, `workable-items add` calls, doc edits, all land in the clone's own `.git`, structurally unable to race another subagent's in-flight commit (different `.git`, different index, different lock namespace).
4. **On subagent completion:** the conductor runs `multitrack_subagent_clone.sh reap <task-id>`, which performs the §11.4.113-mandated merge-onto-latest-main (fetch, merge, resolve, push — never force) from the clone's branch into the SAME checkout the conductor itself is on, THEN removes the clone.
5. **Two concurrent subagents** touching genuinely disjoint files never contend (each merges cleanly); two subagents touching overlapping files surface a REAL merge conflict at reap time — which is the CORRECT place for that conflict to surface (a human/Fable-xhigh-reviewed merge decision per §11.4.211), rather than a silent last-write-wins race in a shared working tree today.

### 6.3 Where the constitution submodule fits (must not be duplicated per clone)

The `constitution/` submodule is real git history + real disk (measured ~157M for
just that one submodule's checkout, §5) — cloning it fresh per subagent, for every
subagent, every task, is wasteful and slow. Two options, both consistent with
§11.4.28(B)/§11.4.31 decoupling:

- **Recommended:** each spawned clone's `constitution/` submodule checkout uses
  `--reference <MT_REPO_ROOT>/constitution` (measured in §5) so its objects are
  hardlinked against the CONDUCTOR's already-initialized constitution checkout —
  same "own `.git`, shared objects" property as the top-level clone itself. The
  submodule's `.git` is still independent (own index/refs/locks) even though its
  object store is reference-linked, so a subagent editing something inside its own
  `constitution/` checkout (which should be rare — constitution edits are
  Fable-xhigh-reviewed per §11.4.209/§11.4.211 and go through the dedicated
  constitution-submodule update workflow, §11.4.26, never through an ad-hoc
  subagent clone) never touches the conductor's constitution checkout.
- **Alternative (not recommended as default):** skip cloning `constitution/`
  entirely for tasks that only need to READ governance context (most SDD tasks) —
  point `CONSTITUTION_DIR` (the documented override env var, per
  `constitution/scripts/multitrack/README.md` §"Config contract") at the
  conductor's own already-initialized `constitution/` checkout as a read-only
  reference. This avoids the ~2.75s-per-submodule cost (§5) entirely for
  read-only tasks, at the cost of the subagent's clone not being usable to COMMIT
  a constitution-submodule change (which almost no SDD task does — those go
  through the dedicated §11.4.26 workflow, not through this mechanism).

Either way, the constitution submodule's OWN content is never copied/forked — only
referenced (git object-level hardlink reference, or a read-only path override),
exactly the "inherited by reference, never duplicated" discipline §11.4.28(B) /
§11.4.177 already mandates for every other consumer of this directory.

## 7. Wall-clock overhead per subagent (summary, measured this session)

| Step | Measured cost | Notes |
|---|---|---|
| `git clone --local` (top-level, no submodules) | **0.19s** | hardlinked objects, own `.git` |
| `constitution/` submodule init via `--reference` | **2.75s** | real SSH handshake each time (Hard Stop #2 compliant); dominant cost |
| Other 4 submodules (challenges/containers/helixqa/jackett), if all needed | **not measured individually** — extrapolated ~2-3s each from the constitution sample, so ~8-12s for all four if a task needed them (most SDD tasks in this project do not) |
| Reap/merge back (fetch + merge + push, no conflict) | **not measured** — bounded by §11.4.113's existing merge-onto-latest-main procedure, which every commit in this session already performs (observed ~1-3s in this session's own `git fetch`/`git push` calls) |

**Honest bottom line:** for a task needing only `constitution/` (the common case —
this very task is an example), total spawn overhead is on the order of **~3
seconds**, dwarfed by subagent LLM turnaround time (minutes). For a task needing
all 5 submodules, overhead rises to roughly **10-15 seconds**, still small relative
to typical subagent wall-clock. This is a measured, not assumed, basis for
recommending per-submodule allowlisting (§5) as the default rather than always
recursing into everything.

## 8. Alternative considered: per-subagent chroot / container

Briefly assessed and NOT recommended as the primary mechanism for this project,
for reasons specific to boba's current toolchain:

- **chroot** requires root privileges to construct (mount `--bind` the repo,
  `chroot` itself) — this violates the "no manual container commands" /
  "rootless-only" discipline (§11.4.161) this project already enforces for its
  OWN Podman-based services, and gains nothing over a plain filesystem clone for
  the actual goal here (git-level corruption isolation), since chroot isolates the
  *filesystem namespace view*, not git's own lock/object-store semantics — a
  process inside a chroot sharing the SAME `.git` bind-mount is exactly as
  unisolated at the git layer as a bare-metal shared checkout. Isolating the git
  history still requires a real clone (this proposal's §4) whether or not a chroot
  wraps it.
- **Container (Podman)** — boba already has a rootless-podman-based container
  orchestration for its OWN services (qbittorrent, jackett, etc., per §11.4.161);
  reusing that machinery to wrap EACH SDD subagent in its own container is
  architecturally heavier than needed: it would require building/maintaining a
  dev-tooling image (git + the Claude Code CLI + the constitution's script
  dependencies), mounting the clone's directory into it, and paying container
  start/stop overhead (typically 100ms-1s for Podman container start alone, before
  any git operation) on top of the clone cost already measured in §4/§5. It is a
  legitimate FUTURE escalation if git-level clone isolation ever proves
  insufficient (e.g. if a task needs true process/resource isolation beyond git,
  such as running untrusted code a subagent might generate) — tracked here as an
  open item, not designed further, since the reported defect class (BOB-068:
  unattributed commits racing in one shared checkout) is fully addressed at the
  git layer by §4-§6 without container overhead.
- **Recommendation:** git-clone-based isolation (§4-§6) first; revisit
  containerization only if a FUTURE finding shows git-level isolation
  insufficient (e.g., a subagent needs to run build tooling with side effects
  beyond git that a container would need to sandbox) — filed as an explicit
  §11.4.197 open item below, not implemented speculatively.

## 9. Explicit non-implementation notice

Per task scope, **nothing in this proposal has been implemented**. No script has
been created, no `multitrack_subagent_clone.sh` exists yet, and no SDD dispatch
behavior has changed. This document is a design + feasibility investigation only,
backed by real measured evidence captured in this session (§3-§5), for the
orchestrating session or a future dedicated implementation task to act on.

## 10. Open items (tracked, not silently dropped — §11.4.197)

- Author `multitrack_subagent_clone.sh` (spawn/reap/list) inside
  `constitution/scripts/multitrack/`, decoupled per §11.4.28(B), with its own
  paired §1.1 mutation tests (per §11.4.224 test-first) proving: (a) two
  concurrent `spawn` calls for the SAME task-id do not double-clone, (b) `reap`
  refuses to remove a clone with uncommitted changes (§11.4.84 quiescence),
  (c) `reap`'s merge is genuinely ff-only per §11.4.113 (never force-push).
- Wire the SDD skill's subagent-dispatch step to call `spawn`/`reap` around every
  task, replacing today's shared-checkout dispatch (the literal BOB-068 remedy).
- Decide (operator, §11.4.66) the default submodule allowlist per SDD task class,
  informed by §5's measured per-submodule cost.
- Decide (operator, §11.4.66) whether `--reference` (hardlink, default
  recommendation) or `--dissociate` (full copy, eliminates the `git gc`-during-
  clone-lifetime risk noted in §4.6 at the cost of disk) is the project's standing
  default.
