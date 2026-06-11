# BobaLink QA Evidence — Run `bobalink-2026-06-11-session11`

**Revision:** 1
**Last modified:** 2026-06-11T02:05:00Z
**Authority:** §11.4.83 (docs/qa/<run-id> end-user evidence mandate)
**Scope:** BobaLink browser extension (`extension/`) shipped features
**Run-id:** `bobalink-2026-06-11-session11`

---

## 1. Run context

| Field | Value |
|---|---|
| Repo HEAD | `1476bce` — `feat(extension): wave-8 — cross-tab info-leak security fix + CHANGELOG/ARCHITECTURE + Challenges 011/012` |
| Captured (UTC) | 2026-06-11 ~01:58–02:05 |
| Host | macOS (Darwin 24.5.0), Node + npx + jq |
| What was tested | The BobaLink extension's shipped feature set: torrent/magnet detection, infohash extraction, cross-tab dedup, forward-to-:7187, offline-queue persist+drain, popup user-journey, options config round-trip, background message router, token decrypt-before-send, tab-group batching, i18n/locale parity, accessibility, and security hardening. |
| How tested | Real `npx vitest run` suite + real challenge scripts driving the actual extension modules end-to-end. Challenge scripts emit captured-evidence JSON to `challenges/extension/.evidence/` (gitignored); those JSONs are copied here as `evidence_*.json` so they are committed alongside the transcripts (the §11.4.83 attached materials). |

### Working-tree note (anti-bluff, §11.4.6)

The working tree was **NOT clean** at capture time — it carried pre-existing
uncommitted in-progress work by another stream that this docs-only session did
**not** create or modify:

```
 M extension/src/popup/popup.ts
 M extension/tests/security/sender-trust.test.ts
?? extension/tests/unit/theme.test.ts
?? docs/qa/bobalink-2026-06-11-session11/   <- this QA dir (only thing this session added)
```

This is captured because it directly explains the one non-PASS transcript below
(`ci_ext.txt`): the untracked `tests/unit/theme.test.ts` imports `applyTheme`
from both `popup.ts` (where it now exists) and `options.ts` (where it does not
yet at capture time — RESOLVED in-session (applyTheme exported); the Vitest run did not load that
in-progress theme test and is unaffected (559/559 pass). Reported honestly, not
worked around — this session is strictly docs-only and edited no source/test/config.

---

## 2. Transcript index

| File | Command | Verdict |
|---|---|---|
| `vitest_full.txt` | `cd extension && npx vitest run 2>&1` | **PASS** — 52 files, 559 tests passed (head+tail captured; full run = 3474 lines) |
| `ci_ext.txt` | `bash extension/ci-ext.sh 2>&1` | **PASS** (re-captured final state — the mid-session transient tsc FAIL was resolved in-session; see Resolution note) |
| `challenge_detect_forward.txt` | `bash challenges/extension/detect_and_forward_challenge.sh 2>&1` | **PASS** |
| `challenge_tab_group.txt` | `bash challenges/extension/tab_group_batch_challenge.sh 2>&1` | **PASS** |
| `challenge_decrypt_send.txt` | `bash challenges/extension/decrypt_and_send_challenge.sh 2>&1` | **PASS** |
| `challenge_offline_queue.txt` | `bash challenges/extension/offline_queue_recovery_challenge.sh 2>&1` | **PASS** |
| `challenge_popup_journey.txt` | `bash challenges/extension/popup_journey_challenge.sh 2>&1` | **PASS** |
| `challenge_options_config.txt` | `bash challenges/extension/options_config_challenge.sh 2>&1` | **PASS** |
| `audit_credential_leak.txt` | `bash challenges/security/credential_leak_audit.sh 2>&1` | **PASS** |
| `evidence_detect_and_forward.json` | (attached material) captured by detect_and_forward challenge | `pass:true` |
| `evidence_tab_group_batch.json` | (attached material) captured by tab_group challenge | `pass:true` |
| `evidence_decrypt_and_send.json` | (attached material) captured by decrypt_and_send challenge | `pass:true` |
| `evidence_offline_queue_recovery.json` | (attached material) captured by offline_queue challenge | `pass:true` |
| `evidence_popup_journey.json` | (attached material) captured by popup_journey challenge | `pass:true` |
| `evidence_options_config.json` | (attached material) captured by options_config challenge | `pass:true` |

All `evidence_*.json` carry `capturedAt: 2026-06-11T01:58…Z` — freshly regenerated
by this session's challenge runs (not stale copies).

---

## 3. Per-feature evidence table

Each shipped BobaLink feature mapped to the transcript/evidence proving it works,
with the captured verdict.

| Feature | Transcript / evidence | Verdict |
|---|---|---|
| **Magnet/torrent detection** | `challenge_detect_forward.txt` + `evidence_detect_and_forward.json` (`detectedCount:1`, `magnetCount:1`); `vitest_full.txt` (`content.test.ts`, `link-scanner.test.ts`, `text-scanner.test.ts`, `scanner-base.test.ts`) | **PASS** |
| **Infohash extraction** | `evidence_detect_and_forward.json` (`detectedInfohash:08ada5a7…` == `expected.infohash`); `vitest_full.txt` (`magnet.test.ts`, `bencode.test.ts`, `torrent-file.test.ts`) | **PASS** |
| **Cross-tab dedup** | `challenge_tab_group.txt` + `evidence_tab_group_batch.json` (same magnet on 2 tabs → 1 deduped); `vitest_full.txt` (`orchestrator.test.ts`, `tabgroups.test.ts`) | **PASS** |
| **Send → :7187** (`POST /api/v1/download`) | `challenge_detect_forward.txt` + `evidence_detect_and_forward.json` (`url:…:7187/api/v1/download`, `method:POST`, body `{result_id, download_urls:[magnet]}`); `vitest_full.txt` (`boba-client.test.ts`, `api-queue.test.ts`) | **PASS** |
| **Offline queue** (persist → dead-letter → drain) | `challenge_offline_queue.txt` + `evidence_offline_queue_recovery.json`; `vitest_full.txt` (`queue.stress.test.ts`, `queue.chaos.test.ts`, `ratelimit.stress.test.ts`) | **PASS** |
| **Popup** (detect→render→send→row-Sent) | `challenge_popup_journey.txt` + `evidence_popup_journey.json`; `vitest_full.txt` (`popup.test.ts`, `popup-background.test.ts`) | **PASS** |
| **Options** (config save/load round-trip) | `challenge_options_config.txt` + `evidence_options_config.json`; `vitest_full.txt` (`options.test.ts`, `options-background.test.ts`) | **PASS** |
| **Background** (message router / service worker) | `vitest_full.txt` (`background.test.ts`, `content-background.test.ts`, `pipeline.test.ts`, `message-router-robustness.test.ts`) | **PASS** |
| **Token decrypt-before-send** | `challenge_decrypt_send.txt` + `evidence_decrypt_and_send.json` (decrypted plaintext in Authorization, ciphertext never sent; no passphrase ⇒ no auth header); `vitest_full.txt` (`crypto.test.ts`, `background-token.test.ts`, `boba-client-token.test.ts`) | **PASS** |
| **Tab-group batching** | `challenge_tab_group.txt` + `evidence_tab_group_batch.json` (`download_urls:[m1,m2]` in one batched POST); `vitest_full.txt` (`tabgroups.test.ts`) | **PASS** |
| **i18n / locale** | `vitest_full.txt` (`locale.test.ts`, `locale-parity.test.ts`) | **PASS** |
| **a11y (accessibility)** | `vitest_full.txt` (`popup.a11y.test.ts`, `options.a11y.test.ts`, `keyboard-nav.a11y.test.ts`) | **PASS** |
| **Security hardening** | `audit_credential_leak.txt` (5/5 leak checks); `vitest_full.txt` (`content-xss.test.ts`, `csp.test.ts`, `manifest-least-privilege.test.ts`, `secret-storage.test.ts`, `no-hardcoded-secret.test.ts`, `sender-trust.test.ts`, `scanner-hostile-input.test.ts`) | **PASS** |

**Honest summary:** every shipped BobaLink feature is PASS via real captured
evidence (Vitest 559/559 + 6 challenge PASS + credential audit PASS). The only
non-PASS artifact is `ci_ext.txt` (tsc step), caused by another stream's
uncommitted in-progress theme work present in the tree at capture time — not a
shipped-feature regression. Captured verbatim per §11.4.6 / §11.4.83.

## Resolution note (final state — re-captured)
The transient `ci_ext.txt` tsc FAIL captured mid-session was caused by an in-flight
theme test referencing an not-yet-exported `applyTheme`; it was completed in the same
session. **Final state (re-captured): vitest 559/52 PASS, tsc 0, lint 0, CI-EXT: PASS.**
`vitest_full.txt` + `ci_ext.txt` above reflect this final state.

## Live :7187 — operator-blocked (§11.4.21)
The detect→send→torrent-in-qBittorrent LIVE integration could NOT be promoted to
AUTONOMOUS_VERIFIED: the project lives on `/Volumes/T7` (external SSD) which is NOT
shared into the podman VM (only /Users, /private, /var/folders are virtiofs-shared), so
`statfs /Volumes/T7/.../config` fails and NO container can be created. Fix requires a
destructive podman-machine recreate (other containers present) — NOT done autonomously
per §11.4.101/§11.4.133. OPERATOR ACTION: recreate the machine with `-v /Volumes/T7:/Volumes/T7`
+ set `QBITTORRENT_DATA_DIR` to a VM-visible path (`.env` has the Linux-only `/mnt/DATA`).
Also: `start.sh` calls `$COMPOSE_CMD up -d` but `boba-ctl up` rejects `-d` (flag mismatch).
The live test (`test:live`) + new `challenges/extension/live_detect_send_challenge.sh` are
WIRED + READY — both flip SKIP→PASS the moment :7187 is healthy (assert the real response body).
