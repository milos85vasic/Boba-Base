# Session Manual QA Checklist — 2026-08-18

**Revision:** 1
**Last modified:** 2026-08-18T21:40:00Z
**Authority:** §11.4.185 (manual-QA-final human sufficiency gate) + §11.4.153 (per-feature
Status/video-confirmation format). Automated gates are NECESSARY but NOT SUFFICIENT — this
checklist is the human confirmation step the constitution requires before this session's
deliverables can be considered fully done.
**Scope:** deliverables shipped/verified in the boba-stack session spanning commits `457cca4`
(constitution v68 pointer/loader fix) through `63f3f88` (HEAD at authoring time). See
`docs/CONTINUATION.md` Rev 24 for the full session narrative this checklist confirms.
**Per §11.4.238:** every item below was already exercised by an automated check or a live
captured-evidence probe in this session (cited per feature). This checklist's job is
CONFIRMATION, not discovery — if the operator finds something NEW and unreported here, that is
itself a coverage-escape and should be filed as its own workable item with a
`docs/QA_DISCOVERY_LEDGER.md` entry (out of this document's scope — see that file directly).

---

## Executive summary

**Sign off if all 12 features below PASS.**

| # | Feature | Automated evidence already captured | Manual confirmation needed |
|---|---|---|---|
| 1 | Boba stack container reachability | `docker ps` / `podman ps` health checks | Yes — visual confirm of all 4 UIs/APIs |
| 2 | qBittorrent WebUI (7185) | HTTP 200 curl | Yes — log in, see torrent list |
| 3 | Merge Search Dashboard (7187) | HTTP 200 curl + dashboard HTML captured | Yes — visually confirm layout renders |
| 4 | Jackett management page (7187/jackett) | HTTP 200 curl | Yes — visually confirm credentials UI |
| 5 | boba-jackett API (7189) | `/healthz` 200 curl (API-only, no standalone UI) | Yes — confirm health JSON in browser |
| 6 | Search functionality (cross-tracker + dedup) | Live captured run, 42 trackers / 1640 raw / 468 merged (uncommitted evidence, this session) | Yes — run one search yourself |
| 7 | Download flow (proxy + cookies, freeleech-only) | Live captured run: add → verify → stop → delete (uncommitted evidence, this session) | Yes — run one freeleech download + verify cleanup |
| 8 | BOB-112 `/healthz` TTL cache (DDoS mitigation) | Live `wrk` load test: 97.1%→0.0% timeout rate (`e2a2e3e`) | Yes — hit `/healthz` rapidly, confirm no hang |
| 9 | Constitution v68 amendment landing | Submodule pointer bump (`c4e2d93`, `f8aa956`) + `constitution/CLAUDE.md` Revision-68 header | Yes — spot-check one new anchor's text |
| 10 | Resource-pressure timer (armed) | `systemctl --user list-timers` shows next fire in ~35 min | Yes — confirm timer + last-run log |
| 11 | CONST-033 challenge (host cannot suspend) | Re-run this session: 4/4 PASS | Yes — re-run + eyeball output |
| 12 | Pre-build gate (27/27 GREEN) | Re-run this session: `27 passed, 0 failed` at HEAD `63f3f88` | Yes — re-run yourself |

**Video-confirmation note (§11.4.153):** none of the 12 items below have a fresh screen recording
tied specifically to this session's changes. Recording infrastructure exists for this project
(`/Volumes/T7/Downloads/Recordings/`, see `docs/features/Status.md` "Video-recording
confirmations") but was not exercised for this batch — every "Video-confirmation status" cell
below is honestly `PENDING (not recorded this session)`. If the operator wants durable video
evidence, the fastest path is `asciinema rec` for the CLI/curl-driven items (6, 7, 8, 10, 11, 12)
and a screen capture for the browser-driven items (2, 3, 4, 5).

---

## FEATURE-01 — Boba stack container reachability

- **Component:** docker-compose stack (qbittorrent, jackett, boba-jackett, qbittorrent-proxy)
- **Category:** Infrastructure / smoke test
- **Implementation reference:** `docker-compose.yml` (service definitions); orchestrated via
  `./start.sh` (see `CLAUDE.md` "Pick the right restart level"); systemd wrapper
  `scripts/boba-svc.sh` (commit `444d94e`) for boot-persistent operation.
- **Wiring status:** DEPLOYED — confirmed live this session: `qbittorrent` (healthy, up 39 min),
  `jackett` (healthy, up 39 min), `boba-jackett` (healthy, up 38 min), `qbittorrent-proxy`
  (healthy, up 38 min, host-network mode bundling ports 7186/7187/7188).
- **Manual test steps:**
  1. Run `podman ps` (or `docker ps` on a docker-only host) and confirm all 4 boba containers show
     `Up` with `(healthy)` where a healthcheck is defined.
  2. Alternatively run `./scripts/boba-svc.sh health` (systemd-wrapped path) or `./start.sh -s`
     (direct compose path) and read the per-endpoint probe output.
- **Expected outcome:** all 4 containers `Up (healthy)`; no `Restarting` / `Exited` / `unhealthy`
  states.
- **Video-confirmation status:** PENDING (not recorded this session).

---

## FEATURE-02 — qBittorrent WebUI (http://localhost:7185)

- **Component:** qbittorrent container, WebUI
- **Category:** UI / end-user surface
- **Implementation reference:** `docker-compose.yml` `qbittorrent` service; credentials are
  hardcoded `admin`/`admin` per `CLAUDE.md` (do not change).
- **Wiring status:** DEPLOYED — `curl -o /dev/null -w '%{http_code}' http://localhost:7185/`
  returned `200` this session.
- **Manual test steps:**
  1. Open `http://localhost:7185` in a browser (or via the proxy at `http://localhost:7186` for
     the auth-injected path).
  2. Log in with `admin` / `admin`.
  3. Confirm the torrent list view loads (may be empty — that is fine).
- **Expected outcome:** WebUI loads, login succeeds, torrent list panel renders without a
  blank/error page.
- **Video-confirmation status:** PENDING (not recorded this session). Historical confirmation
  exists from a prior session — see `docs/features/Status.md` "Video-recording confirmations"
  table, `boba-web-dashboard-tour.mp4` (qBit-Connected header indicator) — but that recording
  predates this session's changes and does not stand in for a fresh confirmation.

---

## FEATURE-03 — Merge Search Dashboard (http://localhost:7187)

- **Component:** qbittorrent-proxy (Python/FastAPI) merge-search dashboard
- **Category:** UI / end-user surface
- **Implementation reference:** `download-proxy/src/api/__init__.py` (FastAPI app);
  `docs/qa/task-e2e-journey/dashboard_response.html` (captured this session, HTTP 200, 2505
  bytes) — **note: this evidence directory is uncommitted at the time this checklist was
  authored** (produced by a concurrent in-session task; it will land in a future commit — do not
  cite a commit SHA for it until it is committed).
- **Wiring status:** DEPLOYED — `curl` returns `200` with a full `<title>Боба Dashboard</title>`
  HTML page.
- **Manual test steps:**
  1. Open `http://localhost:7187` in a browser.
  2. Confirm the "Боба Dashboard" page renders (header, search box, tracker list).
  3. Toggle the theme switch (if present) and confirm the page re-renders without breaking.
- **Expected outcome:** dashboard loads with a visible search UI and tracker/result panels; no
  blank page or client-side JS error in the console.
- **Video-confirmation status:** PENDING (not recorded this session).

---

## FEATURE-04 — Jackett management page (http://localhost:7187/jackett)

- **Component:** Angular dashboard `/jackett` route, backed by boba-jackett (7189)
- **Category:** UI / end-user surface
- **Implementation reference:** `docs/JACKETT_INTEGRATION.md` § "Auto-Configuration"; boba-jackett
  owns credentials/overrides in `config/boba.db` per `docs/BOBA_DATABASE.md`.
- **Wiring status:** DEPLOYED — `curl -o /dev/null -w '%{http_code}' http://localhost:7187/jackett`
  returned `200` this session.
- **Manual test steps:**
  1. Open `http://localhost:7187/jackett` in a browser.
  2. Confirm the credentials/overrides management UI renders (Add-credential dialog, indexer
     override list).
  3. Do NOT save new credentials during this pass unless you intend to (this page writes to
     `config/boba.db`).
- **Expected outcome:** page loads with the Jackett credentials management UI, no error banner.
- **Video-confirmation status:** PENDING (not recorded this session). A prior-session recording
  (`boba-web-jackett-add-credential.png`, per `docs/features/Status.md`) exists but predates this
  session's changes.

---

## FEATURE-05 — boba-jackett API health (http://localhost:7189)

- **Component:** boba-jackett (Go/Gin), port 7189
- **Category:** API / infrastructure (no standalone browser UI of its own — the root path `/`
  correctly 404s; its management surface is served through the Angular dashboard at
  `:7187/jackett`, FEATURE-04 above)
- **Implementation reference:** `qBitTorrent-go/internal/jackettapi/health.go` (see also
  FEATURE-08 below for the specific `/healthz` TTL-cache fix); this file currently has an
  **uncommitted, in-progress edit** in the working tree at the time this checklist was authored —
  the evidence below reflects the last-committed state (`91b52db` / `e2a2e3e`), not whatever is
  mid-edit.
- **Wiring status:** DEPLOYED — `curl -o /dev/null -w '%{http_code}' http://localhost:7189/healthz`
  returned `200` this session. `curl http://localhost:7189/` correctly returns `404` (no root
  route is expected/registered — this is NOT a defect).
- **Manual test steps:**
  1. Open `http://localhost:7189/healthz` directly in a browser or via `curl`.
  2. Confirm a JSON body is returned (e.g. `{"status":"healthy", ...}`).
  3. Confirm `http://localhost:7189/` returns a plain 404 (expected — do not file a bug for this).
- **Expected outcome:** `/healthz` returns 200 with a status JSON body within well under 1 second.
- **Video-confirmation status:** N/A — no UI to record; confirmed by curl/browser JSON view.

---

## FEATURE-06 — Search functionality: cross-tracker search with dedup

- **Component:** Merge search service (`/api/v1/search/sync`), 42 registered trackers
- **Category:** Core functionality
- **Implementation reference:** `download-proxy/src/merge_service/search.py` (orchestration) +
  `download-proxy/src/merge_service/deduplicator.py` (dedup). Session evidence:
  `docs/qa/task-e2e-journey/search_response.json` + `search_response_raw.log` + `summary.md`
  (captured live this session, 358 KB raw response, 42 trackers queried, 1640 raw results merged
  to 468 unique) — **uncommitted at the time this checklist was authored** (concurrent in-session
  task; will land in a future commit).
- **Wiring status:** DEPLOYED — proven end-to-end this session via real HTTP against the live
  stack (no mocks, no deep-link shortcuts, per §11.4.143).
- **Manual test steps:**
  1. Open `http://localhost:7187`.
  2. Enter a search term (e.g. `"Ubuntu"` or `"1080p"`) and submit.
  3. Confirm results appear from multiple trackers (check the per-result tracker label / the
     dashboard's tracker-count indicator).
  4. Confirm no obvious duplicate rows for what is clearly the same release across trackers (a
     small number of near-duplicates from genuinely different releases is expected and NOT a
     dedup failure).
- **Expected outcome:** results render within a few seconds, spanning more than one tracker, with
  the merged/deduplicated count visibly lower than the raw per-tracker sum.
- **Video-confirmation status:** PENDING (not recorded this session). Prior-session recording
  `boba-web-search-flow.mp4` exists (per `docs/features/Status.md`, confirms "829 results (288
  merged)") but predates this session.

---

## FEATURE-07 — Download flow: proxy fetch with cookies (freeleech-only)

- **Component:** Download proxy (`/api/v1/download`) → qBittorrent Web API passthrough
- **Category:** Core functionality
- **Implementation reference:** tracker-credential wiring `b1af169`; cookies-file autoload
  convention `619a5f6`; loader closed-set fix `457cca4`. Session evidence:
  `docs/qa/task-e2e-journey/download_response.log` + `qbit_torrent_info_pretty.json` +
  `qbit_cleanup.log` (captured live this session: add → verify registered/downloading → stop →
  delete with `deleteFiles=true` → re-verify removed) — **uncommitted at the time this checklist
  was authored**.
- **Wiring status:** DEPLOYED — proven end-to-end this session; the torrent added was confirmed
  `freeleech: true` / tagged `[free]` **before** selection, per the project's freeleech-only
  constraint (`CLAUDE.md`).
- **Manual test steps:**
  1. Search for content on a tracker known to have freeleech-tagged results (e.g. IPTorrents —
     look for the `IPTorrents [free]` tag in the tracker display name).
  2. Click download/add on a **freeleech-tagged** result ONLY. Do not add a non-freeleech
     IPTorrents result — this costs ratio on a live account.
  3. Confirm the torrent appears in the qBittorrent WebUI (7185) torrent list, actively connecting
     to peers.
  4. Stop and delete the torrent (with "delete files" checked) to avoid consuming bandwidth/disk
     unnecessarily during this QA pass.
- **Expected outcome:** the torrent registers in qBittorrent within seconds of clicking download;
  stop+delete removes it cleanly (re-querying the torrent list shows it gone).
- **Honest note:** this feature genuinely requires live, working tracker credentials
  (`IPTORRENTS_USERNAME`/`PASSWORD` or equivalent per `.env`) to test the private-tracker path.
  If credentials have expired/rotated since this session, this step will fail for a credential
  reason unrelated to the download-flow code itself — check `docs/guides/tracker-credentials.md`
  before filing a bug.
- **Video-confirmation status:** PENDING (not recorded this session).

---

## FEATURE-08 — BOB-112: `/healthz` TTL cache (DDoS-amplification mitigation)

- **Component:** boba-jackett, `internal/jackettapi/health.go`
- **Category:** Bug fix / resilience (§11.4.85 stress test)
- **Implementation reference:** fix commit `91b52db` (TTL cache around
  `Jackett.GetCatalog()`); load-test proof commit `e2a2e3e` (live `wrk` 4-thread/100-connection/
  30s run: baseline with cache bypassed = 400/412 requests timed out (97.1%); post-fix = 0/812,149
  timed out (0.0%), 27,049 req/s, p99 latency 19.89ms).
- **Wiring status:** DEPLOYED per the committed code and load-test evidence above. **Honest
  status-custody note (§11.4.6):** the workable-items DB record for `BOB-112` still shows
  `Status: Queued` at the time of writing, even though the fix and its live proof are committed —
  this looks like a status-write gap (the DB row was never flipped to a terminal status after the
  fix landed), not a code defect. Worth a separate, small follow-up to correct the DB status; it
  does not block this manual-QA pass, which is about the runtime behavior.
- **Manual test steps:**
  1. Run `curl http://localhost:7189/healthz` a handful of times in quick succession (a simple
     `for i in $(seq 1 20); do curl -sS -o /dev/null -w '%{time_total}\n' http://localhost:7189/healthz; done`
     one-liner is enough — no need to reproduce the full `wrk` load test).
  2. Confirm every response returns quickly (well under 1 second) and with HTTP 200.
  3. Optional deeper check: run `challenges/scripts/ddos_resilience_challenge.sh --healthz` if you
     want the full regression-guard re-run (this is what `e2a2e3e`'s evidence was captured with).
- **Expected outcome:** rapid repeated hits to `/healthz` never hang or time out; latency stays
  low and flat regardless of request rate.
- **Video-confirmation status:** N/A — no UI; confirmed by curl timing output / challenge script
  console output.

---

## FEATURE-09 — Constitution v68 amendment landing (docs regenerated)

- **Component:** `constitution/` submodule + boba's submodule pointer
- **Category:** Governance / documentation sync
- **Implementation reference:** boba pointer-bump commits `f8aa956` (22-anchor amendment round
  §11.4.239-262 + 5 extensions) and `c4e2d93` (bump to `helixconstitution-v68` tag,
  `34731bf` — CHANGELOG for v68). Confirmed this session: `git submodule status constitution`
  resolves to `fab23f0` (`helixconstitution-v68-15-gfab23f0`, i.e. 15 commits past the v68 tag —
  the tag itself plus later same-day housekeeping commits); `constitution/CLAUDE.md` header reads
  `Revision | 68`.
- **Wiring status:** DEPLOYED — the new anchors (§11.4.239 through §11.4.262, plus the
  §11.4.140/141 anchor-number-collision re-mint to §11.4.255/256) are present in
  `constitution/CLAUDE.md` at the time of writing.
- **Manual test steps:**
  1. Run `git submodule status constitution` from the boba repo root and confirm the pinned SHA
     matches (or descends from) `34731bf` / the `helixconstitution-v68` tag.
  2. Open `constitution/CLAUDE.md` and spot-check ONE new anchor, e.g. search for `§11.4.238` (the
     "automated QA must be the discoverer" anchor) and confirm the full anchor text is present and
     readable (not a stub/truncation).
  3. Confirm boba's own `CLAUDE.md` (repo root) still opens with the
     `## INHERITED FROM constitution/CLAUDE.md` pointer block, so the inheritance chain is intact.
- **Expected outcome:** submodule pointer matches; the spot-checked anchor's full text is present
  and legible; boba's own `CLAUDE.md` inheritance pointer is unbroken.
- **Video-confirmation status:** N/A — text/documentation artifact, no UI.

---

## FEATURE-10 — Resource-pressure timer (armed + running)

- **Component:** `boba-resource-pressure-check.timer` / `.service` (systemd --user unit)
- **Category:** Host-safety / preventive monitoring (CONST-033 family)
- **Implementation reference:** wiring commit `ecb3bfe` (pre-build invariant 25 +
  hourly systemd --user timer); root-cause + guard commit `1f42357`; stress+chaos coverage
  `2b544f7`.
- **Wiring status:** DEPLOYED — `systemctl --user list-timers` shows
  `boba-resource-pressure-check.timer` with a next-fire time roughly 35 minutes out and a
  last-run roughly 42 minutes ago at the time of writing; a fresh log line exists under
  `docs/qa/pre_build_resource_pressure/` (permission `600`, as expected for a host-evidence file).
- **Manual test steps:**
  1. Run `systemctl --user list-timers | grep boba-resource-pressure-check` and confirm a
     `NEXT` time is scheduled (not blank/inactive).
  2. Run `systemctl --user status boba-resource-pressure-check.service` and confirm the last run
     exited `0` (success).
  3. Run the underlying check directly: `bash challenges/scripts/resource_pressure_signature_challenge.sh`
     and confirm it prints `PASS: no resource-pressure signatures over threshold` at the end.
- **Expected outcome:** timer is enabled and scheduled; last service run succeeded; manual
  re-invocation of the underlying challenge script reports clean (all 5 signatures below
  threshold) on a healthy host.
- **Video-confirmation status:** N/A — host-safety daemon, no UI; confirmed by `systemctl`/script
  console output.

---

## FEATURE-11 — CONST-033 challenge (host cannot be suspended)

- **Component:** `challenges/scripts/host_no_auto_suspend_challenge.sh`
- **Category:** Host-safety gate (CONST-033 hard ban)
- **Implementation reference:** `challenges/scripts/host_no_auto_suspend_challenge.sh` (defense in
  depth: target masking + `sleep.conf` override + logind `IdleAction` override, fix applied
  historically at `2026-04-26T18:58:55+02:00`).
- **Wiring status:** VERIFIED THIS SESSION — re-ran live: `sleep.target` / `suspend.target` /
  `hibernate.target` / `hybrid-sleep.target` all `masked`; `AllowSuspend=no` present;
  `logind IdleAction=ignore`; zero "will suspend" journal broadcasts since the fix was applied.
  Result: **4/4 PASS**.
- **Manual test steps:**
  1. Run `bash challenges/scripts/host_no_auto_suspend_challenge.sh` and confirm the final line
     reads `=== summary: 4 pass, 0 fail ===`.
  2. If it reports any FAIL, do NOT attempt to fix by actually suspending/testing suspend
     behavior live (§CONST-033 hard ban) — escalate per the incident-triage protocol in
     `constitution/Constitution.md` § "CONST-033 Operational Note" instead.
- **Expected outcome:** `4/4 PASS`, exactly as re-confirmed this session.
- **Video-confirmation status:** N/A — shell script assertion, no UI; console output is the
  evidence.

---

## FEATURE-12 — Pre-build gate (27/27 GREEN)

- **Component:** `scripts/pre_build_verification.sh` (25 named invariants, some emitting more
  than one `PASS` line each — 27 total pass-lines this session, 0 fails)
- **Category:** Release-gate / governance
- **Implementation reference:** `scripts/pre_build_verification.sh` — Invariant 25 is the newest
  (`CM-RESOURCE-PRESSURE-SIGNATURE-CHECK`, wired by `ecb3bfe`); Invariant 24
  (`CM-DOCS-CHAIN-ENGINE-VERIFY`) and Invariant 23 (`CM-NO-PRODUCTION-MUTATION-RESIDUE`) are the
  next-newest.
- **Wiring status:** VERIFIED THIS SESSION — re-ran live at HEAD `63f3f88`:
  `=== Result: 27 passed, 0 failed ===`. This matches `docs/CONTINUATION.md` Rev 24's terminal
  claim exactly.
- **Manual test steps:**
  1. From the repo root, run `bash scripts/pre_build_verification.sh` (a full run takes roughly
     2-3 minutes on this host; it is safe to run repeatedly — every check is read-only or
     self-cleaning).
  2. Confirm the final line reads `=== Result: N passed, 0 failed ===` with `0` failed. `N` may
     drift upward over time as more invariants land — treat any non-zero `failed` count as a
     release blocker.
  3. If any invariant fails, DO NOT tag/release — file the failure as its own workable item citing
     the exact invariant name printed (e.g. `CM-DOCS-CHAIN-ENGINE-VERIFY`).
- **Expected outcome:** `0 failed`, matching (or exceeding, if more invariants have since landed)
  the `27 passed` baseline confirmed this session.
- **Video-confirmation status:** N/A — CLI script, no UI; console output is the evidence.

---

## Recovery steps for common issues

**A container is down / shows `Exited` or `Restarting`:**
1. Check logs first: `podman logs --tail 100 <container-name>` (or `docker logs`).
2. Use the project's own orchestrator — **never** raw `podman start`/`docker start` directly on a
   single container per `CLAUDE.md`'s restart-level discipline:
   - Python source change → `./start.sh --reload-python`
   - Plugin file change → `./install-plugin.sh` then `./start.sh --reload-plugins`
   - `docker-compose.yml` / env / base-image change → `./start.sh --recreate`
   - No known cause / general "just bring it back up" → `./start.sh` (idempotent, brings up
     whatever is down) or, on a systemd-managed host, `./scripts/boba-svc.sh restart`.
3. After any restart, re-verify: `curl` each of the 4 ports (7185/7187/7189, plus 9117 for
   Jackett itself) and confirm HTTP 200/301 as appropriate, or re-run
   `./scripts/boba-svc.sh health`.

**A service reports `unhealthy` in `podman ps` / `docker ps`:**
1. `podman inspect <container> --format '{{json .State.Health}}'` to see the failing healthcheck
   command and its last output.
2. Cross-check the healthcheck command directly (e.g. for `boba-jackett`:
   `wget -qO- http://localhost:7189/healthz` from inside the container's network namespace, or
   `curl http://localhost:7189/healthz` from the host if the port is published).
3. If the healthcheck itself times out repeatedly, treat this as a resource-pressure signal —
   run `bash challenges/scripts/resource_pressure_signature_challenge.sh` (FEATURE-10 above)
   before assuming it is a code defect in the unhealthy service.

**Search returns zero results across ALL trackers (not just one):**
1. Confirm Jackett itself is reachable: `curl http://localhost:9117/`.
2. Check `JACKETT_API_KEY` is set in `.env` (auto-extracted at container startup per
   `docker-compose.yml`) — a missing/stale key breaks every tracker at once.
3. If only SOME trackers return zero, that is expected/tracker-specific (rate limits, expired
   cookies, geo-blocks) — see `docs/QA_DISCOVERY_LEDGER.md` and `docs/research/` for
   known per-tracker issues before filing a new bug.

**Download flow fails at the credential/login step:**
1. See `docs/guides/tracker-credentials.md` — cookies expire periodically and require a
   `browser export → restart` refresh per the "Cookies-file autoload" convention.
2. Re-run `scripts/load-tracker-cookies.sh` (auto-invoked by `boba-svc up`/`restart`/`start.sh`
   boot, but safe to invoke manually) then restart the affected container.

**`pre_build_verification.sh` fails on Invariant 24 (`CM-DOCS-CHAIN-ENGINE-VERIFY`):**
- This has been a recurring source of transient FAILs this session (see commits `7077107`,
  `a4173c8`-adjacent history, `81e42d4`). Re-run once after confirming `docs_chain` submodule is
  at the pointer boba expects (`git submodule status docs_chain`) before filing a new bug — a
  stale docs_chain checkout is the most common cause.

---

## Filing a defect from this checklist

If any PASS above is negative: **file `BOB-<NNN>` and refer back to session commits.**

1. Use the project's workable-items tooling (`cmd/workable-items` / the DB at
   `docs/workable_items.db`) to mint a new `BOB-NNN`, or hand the details to whichever agent is
   driving the next session — do not hand-edit `docs/Issues.md` directly (it is generated from the
   DB per §11.4.93).
2. Cite the specific FEATURE-NN block above, the exact manual test step that failed, and the
   commit SHA(s) listed in that block's "Implementation reference" as the starting point for
   root-cause investigation (§11.4.114 last-known-good-tag regression isolation).
3. Per §11.4.238, also add an entry to `docs/QA_DISCOVERY_LEDGER.md` recording this as a
   `manual-qa` discovery-channel find — this checklist finding something IS itself information the
   automated regime should be strengthened to catch next time; the ledger entry is where that
   strengthening gets tracked (that file is out of this checklist's edit scope — do not edit it
   from here, file the entry through the normal workable-item + ledger-update flow).
4. Do NOT mark the corresponding item "PASS" in any session summary until the filed `BOB-NNN` is
   itself closed with real captured evidence (§11.4.6 — no self-certification without pasted
   command output).

---

## Anti-bluff disclosures (§11.4.6)

- Every commit SHA cited above was verified to exist in this repository (`git cat-file -e`) at
  the time this checklist was authored — none were fabricated or assumed.
- FEATURE-06 and FEATURE-07's cited evidence (`docs/qa/task-e2e-journey/`) was **uncommitted** at
  authoring time — it was produced by a concurrent in-session task and is cited as live evidence
  of behavior, not as a committed artifact; do not search git history for a commit SHA for it
  until it lands.
- FEATURE-08's DB-status discrepancy (BOB-112 shows `Queued` despite a committed, load-tested fix)
  is disclosed honestly above rather than silently glossed over or silently "fixed" by this
  checklist (which has no mandate to edit the workable-items DB).
- FEATURE-05 notes `qBitTorrent-go/internal/jackettapi/health.go` has an uncommitted, in-progress
  edit in the working tree at authoring time (visible in `git status`); this checklist's evidence
  reflects the last-COMMITTED state of that file, and the operator should be aware a newer,
  in-flight change may supersede it by the time this checklist is actually run.
- No video-confirmation exists for any of this session's specific changes (§11.4.153) — this is
  stated as an honest gap, not concealed. Prior-session recordings are referenced only where
  directly relevant, with an explicit note that they predate this session's changes.
- This checklist's author (a subagent) did not have tracker credentials to actually exercise
  FEATURE-07 independently beyond reading the concurrent task's captured output; the operator is
  the first fully-independent human confirmation of that flow.
