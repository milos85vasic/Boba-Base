# BOB-161 CM-NO-FAIL-OPEN-SKIP — §11.4.209 independent review, round 1

**Verdict: NO-GO** — 0 BLOCKING / 5 IMPORTANT / 7 MINOR
Substrate: Fable (§11.4.209). Reviewer structurally separate from the author (§11.4.70).
Date: 2026-08-25. Loop re-arms per §11.4.134 — remediate, re-review to zero findings AND zero warnings.

## Why this is a NO-GO and not a nitpick

A **reviewer-authored** mutation survives the entire suite while silently halving real
detection. That is the §11.4.115(F) unvalidated-instrumentation condition, and
§11.4.194(6)(d) predicts exactly this: the author's own six mutations were all caught;
the reviewer's first different one was not.

    mutation: SESSION_HINTS = ()
    suite:    19/19 GREEN  (unchanged)
    corpus:   6 findings -> 4      (test_merge_api.py:180 and :484 vanish)
    and then: gate prints "BELOW baseline — lower BASELINE to 4"

The last line is the dangerous part: weakening the instrument presents itself as
progress, and the baseline would lock it in.

## Findings

### IMPORTANT
1. **R3 evasion — tuple-form broad except.** `except (Exception,):` / `except (ValueError, Exception):`
   over a probe PASSES though semantically identical to `except Exception:`. Live shape at
   `tests/unit/api_layer/test_theme_stream.py:145` (a `pass` today, one keystroke from an escape).
2. **SESSION_HINTS unvalidated** — see above. A third of the live baseline rests on it.
3. **Fifth blind condition: unreadable files vanish.** `except OSError: continue` (analyzer 368-370).
   Demonstrated: 2-file corpus, one chmod-000 containing a real fail-open → "parsed 1" → **PASS**.
   Same false-null class the four blind checks exist to close, applied to OSError. Broken symlink
   is the realistic trigger.
4. **R1's "unambiguous attribute" assumption refuted (§11.4.194(2)).** `job.status` on a domain
   object fires R1 on an honest environmental skip; this repo already uses `stat.status` /
   `metadata.status` in probe-capable dirs. Zero live FPs — latent, not active.
5. **"TRACKED SEPARATELY (§11.4.197)" had no tracker row.** Filed by the conductor as **BOB-192**.

### MINOR
1. Ratchet absorbs a one-out-one-in swap (count-baseline); pre-build discards stdout on PASS so the
   changed finding-SET is invisible at the seam. Matches sanctioned precedent; a fingerprint-set
   baseline would close it.
2. `from pytest import skip` evades all rules. Zero corpus instances.
3. `RESPONSE_DERIVERS` is dead code — bare-Name propagation subsumes it.
4. `["status_code"]` subscript arm of `reads_status` covered by no test and no corpus instance.
5. Two latent FP vectors absent from HONEST LIMITS (environmental skip nested under a
   status-success branch; rebound-name taint with no kill-set).
6. Wiring comment says "18 cases"; the suite reports 19.
7. §11.4.18 companion doc absent. The author's "four gates have none" is literally true but
   inverts the evidence — **7 of 12** sibling gates DO have companions, so skipping grows a
   monotone-decreasing debt class (§11.4.261).

## Verified good (proven by execution, not assumed)

19/19 suite confirmed by real run · all 6 baseline findings read and confirmed genuinely fail-open ·
narrow-except skips beside them correctly untouched · both prior author-fixed false positives hold,
with correct R2 attribution · carriers hold including three the author did not write (f-string text,
multi-line raw string containing complete fail-open code, `# type:` comments) · four blind refusals
distinct · exact BOB-092 SKIP-on-404 repro caught in a fresh file · exit codes 0/1/2 measured ·
no self-tightening (sha-verified) · wiring top-level, uses the file's pass/fail helpers, honest
§11.4.3 SKIP when absent, self-scopes to its checkout · `bash -n` + `shellcheck -S warning` clean.

Nothing found invalidates the detector's core definition, the ratchet mechanism, or the wiring.

## Not analysed (stated, never assumed safe)

python3-absent exit-2 branch (host has python3; read-only verification) · behaviour on Python
versions other than the host's 3.14.6 · skips outside `pytest.skip` in shell/Go harnesses (outside
the gate's declared scope) · the 175 dirty exports in the worktree (excluded by instruction, and
not authored by this change).
