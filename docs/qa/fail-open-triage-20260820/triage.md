# §11.4.252 fail-open triage — 2026-08-20

**Revision:** 3
**Last modified:** 2026-08-20T16:35:00Z
**Scope:** every hit reported by pre-build invariant 39
(`CM-DANGEROUS-COMBINATION-FAIL-CLOSED`, §11.4.252) over boba's five first-party
source roots.
**Purpose:** classify every hit so the operator can decide whether the gate is
promoted from ADVISORY to BLOCKING (§11.4.224(E)/§11.4.66 — that decision is
**not** made here and `scripts/pre_build_verification.sh` is **not** modified).

---

## 0. Headline numbers

| Quantity | Value |
|---|---|
| Hits reported by invariant 39 | **38** |
| Actual anti-pattern hits | **36** |
| Hits after this round's fixes | **29** |
| Bucket (A) real defects — fixed | **8** (+1 the gate cannot see, also fixed) |
| Bucket (B) correct idiom | **14** (+2 after A4/A6 were narrowed) |
| Bucket (C) vendored/third-party | **14** |
| Unclassified | **0** |

### 0.1 The "38" is a counting artifact, not two extra defects

Invariant 39 counts hits with `grep -ac '^❌'`, and the gate prints its **summary
line** with a leading `❌` as well:

```
❌ CM-DANGEROUS-COMBINATION-FAIL-CLOSED: FAIL — 4 fail-open anti-pattern hit(s) found
```

So each *failing root* contributes one phantom hit: `download-proxy/src` reports
4+1=5 and `plugins` reports 32+1=33 → 38. The real total is **36**
(4 + 32). Verified by excluding the summary line:

```
$ grep '^❌' gate_before.txt | grep -v 'fail-open anti-pattern hit(s) found' | wc -l
36
```

`scripts/pre_build_verification.sh` is not mine to edit; the one-line fix is to
count `'^❌.*FAIL — swallowed\|^❌.*FAIL — credential silently'` instead of `'^❌'`.
Left as a finding for whoever owns that file.

### 0.2 The gate's 36 is a FLOOR, not the true count — §11.4.201(6) false-null

Measured with an **independent AST instrument** (`ast.ExceptHandler` whose body is
exactly `Pass`/`...`) over the identical five roots — structure, not text, so it
is a valid control needle for the gate's regex (§11.4.201(7)):

| Population | Count |
|---|---|
| Gate-reported (post-fix) | 29 |
| AST ground truth, **same shape** the gate claims to detect | **41** |
| **Missed by the gate** | **12** |
| Additional bare `except:` whose body is not `pass` — excluded by the gate's shape **definition** | **13** |

Set difference: `comm -13 gate_set ast_set` → **zero** gate hits absent from the
AST set (the gate produces **no false positives**), **12** AST hits absent from
the gate.

#### Three distinct detector limitations, each falsifiable

**(L1) A trailing comment on the `except` line defeats the regex — 10 of the 12.**
The pattern anchors `…:[[:space:]]*$`, so `except Exception:  # noqa: S110` never
matches. Every one of these carries a suppression comment, i.e. the sites most
likely to have been consciously reviewed are exactly the ones the gate cannot see:

```
download-proxy/src/api/auth.py:470                       except Exception:  # noqa: S110
download-proxy/src/api/auth.py:534                       except Exception:  # noqa: S110
download-proxy/src/api/routes.py:945                     except Exception:  # noqa: S110
download-proxy/src/api/streaming.py:276                  except Exception as _e:  # noqa: S110
download-proxy/src/api/streaming.py:305                  except Exception:  # noqa: S110
download-proxy/src/api/streaming.py:351                  except Exception:  # noqa: S110
download-proxy/src/api/streaming.py:386                  except Exception:  # noqa: S110
download-proxy/src/merge_service/search.py:753           except Exception:  # noqa: S110
plugins/community/jackett.py:269                         except Exception:  # pylint: disable=broad-exception-caught
plugins/theme_injector.py:402                            except Exception:  # pragma: no cover — defensive
```

**(L2) A tuple `except` clause defeats the regex — 2 of the 12.**
The pattern's type group is `[A-Za-z_.]+`, which cannot match a leading `(`:

```
download-proxy/src/api/routes.py:285                     except (ValueError, TypeError):
download-proxy/src/merge_service/jackett_autoconfig.py:290  except (TimeoutError, aiohttp.ClientError):
```

**(L3) A comment line between `except` and `pass` defeats the body check —
0 current instances, but demonstrated live this round.**
The detector reads exactly `lineno + 1` and requires it to be `pass`, so any
comment inside the handler body hides the site. This is not hypothetical: the
first version of fixes F4/F6 triggered it and hid two real sites. See §3.1.

#### A fourth limitation, in the SHAPE rather than the regex

The gate defines the anti-pattern as *body is exactly `pass`*, so a handler that
swallows via an explicit default **return** is out of scope by construction. There
are **13** such bare-`except:` sites (12 in the vendored `plugins/community/` tree,
1 in the vendored `plugins/linuxtracker.py:51`), plus the one fixed this round:

```
plugins/rutor.py:121    except:
                            return int(time.time())
```

That site was found by a structural invariant in this round's guard, **not** by the
gate, and is listed below as **A9**. `except: return <default>` is materially the
same fail-open as `except: pass` — it discards the exception and substitutes a
value — so this is a genuine coverage gap, not a deliberate narrowing.

#### The 12 missed sites, triaged as far as ownership allows

Two of the 12 fall inside this task's `plugins/*.py` scope and were classified
with the same rule as the rest:

- `plugins/theme_injector.py:402` — **(B)**. `except Exception: pass` around
  gzip/deflate decompression of an HTTP body, with the enclosing function
  returning the explicit documented fallback `(body, False)` on the next line.
  One capability (untrusted input) and an explicit fallback value; below the
  anchor's ≥2 threshold. No change.
- `plugins/community/jackett.py:269` — **(C)**. Vendored (ngosang v4.9), and the
  handler carries the upstream's own `# pylint: disable=broad-exception-caught`.

The other 10 sit in `download-proxy/src/api/{auth,routes,streaming}.py`,
`download-proxy/src/merge_service/{search,jackett_autoconfig}.py` — files owned by
other agents this round. They are **listed, not triaged**; each carries a
suppression comment suggesting a prior deliberate decision, but that has not been
verified here and is **not** claimed (§11.4.6). They should be triaged by their
owners before the gate is promoted, since the fence would otherwise be written
against a set the gate never showed anyone.

#### Consequence for the promotion decision

Driving the gate to zero would **not** mean the tree holds zero fail-open shapes.
It would mean zero of *(bare or single-name) `except` clause, no trailing comment,
body exactly `pass` on the very next line*. The gate's own header already states
its bounded scope honestly (§11.4.6); L1–L3 are regex defects **within** that
declared scope and are worth fixing upstream, while the fourth is a scope choice
worth revisiting.

---

## 1. Classification method

Each hit was classified against §11.4.252's own rule, not against a style
preference:

> a code path COMBINING **≥ 2** dangerous capabilities (mutation of shared state,
> untrusted input, credential access, external side effect, shell/exec,
> irreversible) MUST refuse on an unresolvable precondition — verify every
> precondition, refuse naming the specific unresolved one, **emit captured
> evidence of the refusal**, and never default to proceed.

Three discriminators did the work:

1. **Capability count.** A single-capability path (e.g. removing an item from an
   in-process list) is out of scope by the anchor's own text. Flagging it would be
   the §11.4.201(1) false-positive refusal.
2. **Is the primary failure surfaced?** A handler that swallows only the *error
   reporting* attempt, while the primary failure is already logged or re-raised,
   is graceful degradation — explicitly *not* a fail-open. A handler that
   destroys the only signal is the violation.
3. **Provenance.** Upstream `# VERSION:`/`# AUTHORS:` headers from the qBittorrent
   search-plugins ecosystem, plus bulk-import commits ("official plugins", "from
   community repositories", "adopt 9 orphan engines"), plus byte-comparison
   against the `plugins/community/` twin where one exists.

`git blame` alone was **not** sufficient for provenance: every plugin line blames
to the operator because the vendored files were imported wholesale in bulk
commits. The upstream header + the community-twin diff are the load-bearing
evidence.

---

## 2. Full classification — all 36 hits

### Bucket (A) — REAL DEFECT (8 gate-visible + 1 gate-invisible). All fixed.

| # | File:line | Code | Why it is a defect |
|---|---|---|---|
| A1 | `plugins/env_loader.py:30` | `except Exception:` / `pass` around a `.env` read that writes into `os.environ` | **3 capabilities**: credential access (the `.env` holds tracker credentials), mutation of shared process state (`os.environ`), untrusted input (parsed file). On any read failure the file silently does not take effect, so a downstream "credentials not configured" warning misnames a **corrupt** file as an **absent** one. §11.4.252(3) violated: the reason is destroyed. |
| A2 | `plugins/iptorrents.py:77` | `except Exception:` / `pass` around a credentials-file read into `self.username`/`self.password` | **2 capabilities**: credential access + untrusted input. `_login()` at :81 then reports "No credentials configured" whatever the real cause was — an unreadable file is indistinguishable from an absent one. |
| A3 | `plugins/rutor.py:303` | **bare** `except:` / `pass` | The handler catches the `ValueError("Received HTML page instead of torrent file")` that the code itself raises **two lines above** (:302), then falls through to the generic message at :305. Untrusted input + credentialed session + filesystem write. The operator-actionable "you are being served a login page" signal is destroyed. Bare form also catches `KeyboardInterrupt`. |
| A4 | `plugins/rutor.py:324` | **bare** `except:` / `pass` around `os.unlink(temp_path)` | Re-raises the primary error (`raise e`), so the *fail-open* half is absent — but the **bare** form catches `BaseException`, so a Ctrl-C during cleanup of a credentialed download is silently discarded. Classified (A) on the unnarrowed-catch ground, stated explicitly rather than over-claimed. |
| A5 | `plugins/rutracker.py:349` | **bare** `except:` / `pass` | Identical shape to A3. For a **private** tracker an HTML body almost always means *session expired / login failed* — the single most operator-actionable diagnostic this plugin can produce, and it was being eaten. |
| A6 | `plugins/rutracker.py:370` | **bare** `except:` / `pass` around `os.unlink(temp_path)` | Identical shape to A4. |
| A7 | `plugins/helpers.py:220` | `except Exception:` / `pass` in `fetch_magnet_from_page`, then `return ""` | **2 capabilities**: external side effect (network fetch) + untrusted input. A network/TLS/HTTP failure returns `""` — byte-identical to "this page genuinely has no magnet link". The caller cannot tell them apart and no diagnostic is emitted. *Note:* `helpers.py` is vendored, but `fetch_magnet_from_page` is a **boba-added** function (commit `59a52a8`, the magnet-link WebUI feature); only that block was touched. |
| A8 | `plugins/anilibra.py:75` | `except Exception:` / `pass` wrapping `_process_release` | **2 capabilities**: network + untrusted JSON. `search()` already reports its own failures on stderr (:33), but this handler swallowed every per-release failure, so a fully-broken torrents endpoint rendered as a silent empty result set. boba-authored: commit `edd50f8` "revive anilibra tracker, rewrite for new API". |
| **A9** | `plugins/rutor.py:121` | **bare** `except:` / `return int(time.time())` | **Not reported by the gate** — see §0.2. Bare `except:` around `strptime`/`mktime` date parsing. The "now" fallback is intended behaviour; the bare form additionally catching `KeyboardInterrupt`/`SystemExit` is not. |

### Bucket (B) — CORRECT IDIOM the anchor exempts (14). No change.

| # | File:line | Code | Why it is not a defect |
|---|---|---|---|
| B1 | `download-proxy/src/api/theme_state.py:124` | `except OSError: pass` around `os.fsync(fp.fileno())` | The anchor-named exempt idiom verbatim: fsync inside a block whose outer handler **re-raises** (:132). Any real write failure propagates. Already carries `# noqa: SIM105` = deliberate. |
| B2 | `theme_state.py:130` | `except FileNotFoundError: pass` around `os.unlink(tmp_path)` | Cleanup-of-cleanup, immediately followed by `raise` at :132. The primary error is never swallowed. |
| B3 | `theme_state.py:158` | `except ValueError: pass` around `self._subscribers.remove(queue)` | **One** capability (in-process list mutation). Idempotent unsubscribe. No credential, no untrusted input, no external effect. Below the anchor's ≥2 threshold. |
| B4 | `download-proxy/src/merge_service/scheduler.py:186` | `except asyncio.CancelledError: pass` after `self._task.cancel()` | The anchor-named exempt idiom verbatim. `await self.save()` still runs afterwards — shutdown does not silently skip persistence. |
| B5 | `plugins/rutor.py:21` | `except ImportError: pass` around `from env_loader import load_env_files` | Narrow exception on an **optional sibling module**; the nova3 contract (CLAUDE.md) requires plugins to import outside the container. RuTor is a public tracker needing no auth (CLAUDE.md), so no credential precondition exists here. |
| B6 | `plugins/rutracker.py:21` | same as B5 | Same idiom. The credential precondition **does** fail closed downstream: rutracker.py:61-65 checks the `YOUR_USERNAME_HERE` sentinel and writes an explicit warning to stderr. |
| B7 | `plugins/rutor.py:250` | `except ImportError: pass` around `import socks` | Narrow, optional dependency, and the enclosing `for … else` at :252 provides an **explicit fallback** (`ProxyHandler`). The real precondition already fails closed at :231 (`raise EngineError("Proxy enabled, but not set!")`). |
| B8 | `plugins/download_proxy.py:801` | `except BrokenPipeError: pass` around `self.wfile.write(payload)` | Client disconnected mid-response. Narrow, correct, standard HTTP-handler idiom. |
| B9 | `plugins/download_proxy.py:820` | same as B8 | Same. |
| B10 | `plugins/download_proxy.py:867` | `except OSError: pass` around `os.unlink(torrent_file)` | Temp cleanup **after** the torrent was already successfully proxied. Narrow. |
| B11 | `plugins/download_proxy.py:881` | `except Exception: pass` around `self.send_error(500, str(e))` | The primary failure is **already logged** at :878 (`logger.error(f"Error handling request: {e}")`). The swallow guards only the client-notification attempt, which legitimately fails when the client has gone. Exactly §11.4.252(3)'s "emit captured evidence, then best-effort notify". |
| B12 | `plugins/download_proxy.py:945` | same shape | Primary logged at :942. |
| B13 | `plugins/download_proxy.py:951` | same shape | Primary logged at :948. |
| B14 | `plugins/nyaa.py:31` | `except ModuleNotFoundError: pass` around the `novaprinter`/`helpers` import | The **mandated** nova3 plugin-contract idiom — CLAUDE.md "Plugin System" requires `try: import novaprinter … except ImportError:` so plugins import outside the container. Flagging it would be a false refusal against the project's own contract. |

### Bucket (C) — THIRD-PARTY / VENDORED (14). No change.

Provenance evidence for each is the upstream `# VERSION:` / `# AUTHORS:` header
plus, where a `plugins/community/` twin exists, byte-comparison proving the
handler arrived with the vendored import rather than being boba-authored.

| # | File:line | Upstream provenance | Note |
|---|---|---|---|
| C1 | `plugins/nova2.py:130` | qBittorrent `nova2.py` v1.51, Fabien Devaux / Christophe Dumez, BSD | `engine_class = None` is set **before** the `try` and the comment says "when import fails, return `None`" — an explicit documented failure value. Also (B) by rule. |
| C2 | `plugins/socks.py:336` | PySocks 1.7.1, Dan-Haim — verbatim vendored library | `except socket.error: pass` in `settimeout`. Editing a vendored library in-tree is the §11.4.251 fork this project should avoid. |
| C3 | `plugins/helpers.py:124` | qBittorrent `helpers.py` v1.55 upstream charset block | `charset = "utf-8"` is assigned **before** the `try` — an explicit default. Also (B) by rule. Distinct from A7, which is the boba-added function in the same file. |
| C4 | `plugins/piratebay.py:152` | qBittorrent `piratebay.py` v3.9 | Same charset shape as C3. |
| C5 | `plugins/linuxtracker.py:30` | Joost Bremmer v1.1, GPL | Bare `except:` around the novaprinter import — the contract idiom in bare form. **Identical** in `plugins/community/linuxtracker.py:29`, proving it is upstream-original. |
| C6 | `plugins/linuxtracker.py:103` | same | Bare `except:` around `int(data.strip())` for seeds. **One** capability — below the ≥2 threshold even ignoring provenance. Identical at community:102. |
| C7 | `plugins/linuxtracker.py:109` | same | Same, for leechers. Identical at community:108. |
| C8 | `plugins/torrentproject.py:93` | mauricci v1.92 | `except Exception: pass` around `datetime.strptime`; the field keeps its original string value. Identical at `community/torrentproject.py:93`. |
| C9 | `plugins/community/anilibra.py:75` | see note below | **Byte-identical twin of A8** — see §4. |
| C10 | `plugins/community/linuxtracker.py:29` | Joost Bremmer v1.1 | Twin of C5. |
| C11 | `plugins/community/linuxtracker.py:102` | same | Twin of C6. |
| C12 | `plugins/community/linuxtracker.py:108` | same | Twin of C7. |
| C13 | `plugins/community/torrentproject.py:93` | mauricci v1.92 | Twin of C8. |
| C14 | `plugins/community/jackett.py:44` | ngosang v4.9 | `except AttributeError: pass` around `helpers.enable_socks_proxy(enable)` with the upstream comment "best effort and avoid breaking older qbt versions" — narrow, deliberate, version-compat. Also (B) by rule. |

`plugins/community/` is declared by its own `README.md` as *"community
contributions … not part of the canonical managed set"*, and none of its members
appear in `install-plugin.sh`'s canonical 12. It is treated as a vendored tree.

---

## 3. Fixes applied (bucket A)

All fixes follow one rule, matching the **BOB-139 reference shape** in
`download-proxy/src/api/streaming.py` (distinct, specific reasons rather than
collapsing into a generic one; §11.4.251 — no third variant invented):

> **Preserve the specific reason. Never fail the plugin-import path.**

Where the caller already fails closed, the fix **logs** the destroyed reason and
keeps the existing behaviour. Where the code destroyed its *own* deliberately
raised signal, the fix removes the swallow entirely. Where the handler was bare,
it is narrowed to the exceptions the guarded call can actually raise.

Raising from `env_loader` / `iptorrents` was deliberately **rejected**: both run
at nova3 plugin-**import** time, so raising would break plugin loading — worse
than the bug (the brief's explicit constraint). The credential precondition still
fails closed downstream (`rutracker.py:61` sentinel, `iptorrents.py:81` guard).

| Fix | Site | Change |
|---|---|---|
| F1 | `env_loader.py:30` | `except Exception: pass` → `except Exception as exc:` + `print(f"env_loader: failed to read {path}: …", file=sys.stderr)`. Added `import sys`. Non-fatal by design. |
| F2 | `iptorrents.py:77` | → `logger.warning("IPTorrents: could not read credentials from %s: %s: %s", env_path, type(exc).__name__, exc)`. **Values are never logged** (§11.4.10) — path and exception type only. |
| F3 | `rutor.py:303` | Swallow **removed**. `decode(errors="ignore")` with a valid codec cannot raise, so the `try` was both unnecessary and harmful. The HTML `ValueError` now reaches the caller. |
| F4 | `rutor.py:324` | bare `except:` → `except OSError:`. Behaviour unchanged; `KeyboardInterrupt` no longer swallowed. |
| F5 | `rutracker.py:349` | Same as F3 (retains the `<!doctype` check). |
| F6 | `rutracker.py:370` | Same as F4. |
| F7 | `helpers.py:220` | → logs to `sys.stderr` (already imported at :37). The `""` return contract is **preserved** so callers' "not found" fallback is unchanged. |
| F8 | `anilibra.py:75` | → `print(f"Release {release_id} error: {e}", file=__import__("sys").stderr)` — the **same idiom already used by `search()` at :33**, minimal diff, no new import. |
| F9 | `rutor.py:121` | bare `except:` → `except (IndexError, ValueError, OverflowError, OSError):` — exactly what the list-index / `strptime` / `mktime` calls raise. The "now" fallback is unchanged. |

### 3.1 A fix that blinded the gate — caught and reverted (§11.4.201)

The first version of F4/F6 placed the explanatory comment **between**
`except OSError:` and `pass`. That is limitation **L3** above, and it made both
sites invisible to the gate: the reported count fell 36 → 28 while only **6**
sites had genuinely been eliminated. Two had merely been hidden.

Reporting a 28 obtained that way would have been a §11.4 PASS-bluff at the metric
layer — the number would have improved because the instrument went blind, not
because the code got better. The comment was re-anchored **above** the handler, the
sites are visible again, and the honest count is **30**:

```
36  before
-6  genuinely eliminated (A1, A2, A3, A5, A7, A8)
 0  A4/A6 — narrowed from bare `except:` to `except OSError:`, but still a
    swallow SHAPE by the gate's definition, and correctly so: they remain
    visible and are declared bucket-B in the exemption fence
──
30  after
```

A9 never appeared in either count — the gate cannot see it (§0.2, fourth
limitation).

---

## 4. §11.4.251 finding — byte-identical fork (RESOLVED)

`plugins/anilibra.py` and `plugins/community/anilibra.py` were **byte-identical**
(`md5 a9e20a0a…`) and both were rewritten by boba in commit `edd50f8`. Fix **F8**
could only touch the top-level copy — the community tree is outside this task's
declared file ownership — which would have left the two diverging by exactly that
handler, manufacturing the fork §11.4.251 forbids.

The transferable patch was published here rather than applied silently, and the
coordinator landed it on the twin in the **same commit** (`0795721`). Verified:

```
ast.dump(plugins/anilibra.py) == ast.dump(plugins/community/anilibra.py)   -> True
```

The two files are **behaviourally identical**; the defect is fixed in both and the
gate no longer reports `community/anilibra.py:75`.

**Residual, honestly stated:** they are no longer *byte*-identical — the two
explanatory comments differ in wording. Nothing behavioural depends on it, but the
md5-equality property that made drift between these twins trivially detectable is
gone. The durable fix remains the §11.4.251 one — extract a single copy rather
than maintain two — and that stays a tracked follow-up, not something this round
resolved.

---

## 5. §11.4.120 finding — two stale gates asserted the pre-fix behaviour (RESOLVED)

Fixes F3/F5 made two existing unit tests fail, because they asserted the message
that only existed **because** of the bug:

```
tests/unit/test_plugin_rutor.py:439      match="not a valid torrent file"
tests/unit/test_plugin_rutracker.py:601  match="not a valid torrent"
```

Per §11.4.120 those FAILs were the **correct signal that the fix landed** and
required **reconciliation** — never a fake-pass, never a revert of the fix. The
fix did not over-broaden: the sibling non-HTML cases in the same classes
(`test_non_bencode_non_html_raises`, `test_non_torrent_binary_raises`) still pass
with the generic message.

`tests/unit/` is outside this task's declared ownership, so the reconciliation was
**not** applied here. It was surfaced to the coordinator, who owned it and
completed it:

- Verified the analysis independently before rewriting either gate.
- RED before: 2 failed, 13 passed → GREEN after: 15 passed, with the two generic-
  message siblings still asserting the generic string (the evidence of no
  over-broadening).
- Discriminator per §11.4.115(F): restored the actual bare-`except:` **swallow
  structure** rather than deleting the message string (a string-deletion mutation
  is a refused tautology); the reconciled gate FAILED, then restored byte-identical
  (`md5 ee1af14a…`), zero residue.

Confirmed green from this side: the targeted regression subset covering every
changed file is **642 passed, 0 failed**.

Transferable lesson recorded by the coordinator: the rutor assertion pattern
appears **twice** in that file (the second being `test_non_bencode_non_html_raises`),
so a blind string replace would have silently rewritten the wrong test. The edit
had to be re-anchored on the `html_data` line.

---

## 6. Evidence

Oracle strategy (§11.4.245): **INVARIANT** — the expected behaviour comes from
§11.4.252(3) itself ("a path that cannot complete MUST emit captured evidence
naming the unresolved precondition"), asserted on user-observable output (stderr
text, the raised exception's message, the returned value), never on the
implementation agreeing with itself.

Both polarities (§11.4.201(1)): every failure-path test demanding a refusal is
paired with a normal-path test proving the feature still works **and** emits no
spurious diagnostic.

- `test_fail_open_regression.py` — 29 guards over all 9 (A) sites
- `red_run.txt` — RED baseline at `git HEAD c95b0c1`: **8 failed, 18 passed**
- `green_run.txt` — after fixes: **29 passed**

### Paired §1.1 mutation — each fix reverted, its own guard must FAIL

```
mutate env_loader.py -> 1 failed, 25 passed
mutate iptorrents.py -> 1 failed, 25 passed
mutate rutor.py      -> 2 failed, 24 passed
mutate rutracker.py  -> 2 failed, 24 passed
mutate helpers.py    -> 1 failed, 25 passed
mutate anilibra.py   -> 1 failed, 25 passed
all restored         -> 26 passed
```

Every guard catches its own negation — none is decoration.

### CONST-XII no-op-stub check (a mutation the author did not write, §11.4.194(6)(d))

Reverting a fix restores the *old code*, which a guard could in principle detect
by shape rather than by behaviour. The stronger mutation keeps the new structure
(`except Exception as exc:` — the swallow is **not** restored) and replaces only
the diagnostic with a no-op — a plausible-looking "fix" that fixes nothing:

```
stub applied to plugins/env_loader.py  ->  1 failed, 25 passed
restored (0 mutation markers, §11.4.84) ->  26 passed
md5 3d5768e7c0ad6d31d254fc657c1395f9
```

The guard fails, so it is asserting the user-observable outcome (a diagnostic
actually reaches stderr), not the presence of a code pattern.

### nova3 stream integrity — the risk the fixes themselves introduced

Every fix adds a **new write**. nova3 harvests search results by parsing plugin
**stdout**, so a diagnostic landing there would corrupt the result stream for the
end user — a worse defect than the swallow it replaced. All eight diagnostics go
to `stderr` (or `logger`), and three standing guards now prove it at runtime
rather than by inspection:

```
env_loader   stdout=''  stderr_nonempty=True
helpers      stdout=''  returned=''  stderr_nonempty=True
anilibra     stdout=''  stderr_nonempty=True
```

Each asserts the diagnostic **did** fire (the precondition) and that stdout stayed
byte-empty.

### Gate before / after

```
BEFORE: 36   (download-proxy/src 4, plugins 32, scripts 0, qBitTorrent-go 0, frontend/src 0)
AFTER:  29   (download-proxy/src 4, plugins 25, scripts 0, qBitTorrent-go 0, frontend/src 0)
```

7 genuine eliminations — the 6 first-party (A) sites plus
`plugins/community/anilibra.py:75`, whose §11.4.251 twin patch landed in the same
commit (§4). A4/A6 deliberately remain **visible** as declared bucket-B rather
than hidden from the instrument (see §3.1).

### Other checks

```
python3 -m py_compile plugins/*.py plugins/community/*.py   -> OK all plugins
ruff check plugins/ docs/qa/fail-open-triage-20260820/      -> All checks passed!
pytest tests/unit -k "<every changed file>"                 -> 642 passed, 0 failed
pytest tests/unit  (FULL suite, 18m59s)                     -> 4415 passed, 3 failed
pytest docs/qa/fail-open-triage-20260820/                   -> 29 passed
```

### Full-suite attribution — the 3 failures are PRE-EXISTING (§11.4.6)

The full run finished **4415 passed, 3 failed**. Exit code was 0, which is *not*
evidence (an earlier backgrounded run also exited 0 with an empty output file), so
the three were attributed by **experiment**, not by reasoning:

```
git checkout 1dd7b0a -- plugins/     # the commit BEFORE this work
  -> 3 failed   (identical three)
git checkout HEAD -- plugins/        # restore
  -> md5sum -c: all 6 files OK       # byte-exact restore verified
```

They fail identically **without** any of this round's changes, so none is
attributable to it:

| Test | Owner |
|---|---|
| `test_main.py::…test_start_fastapi_server_imports_uvicorn` | another agent's `main.py` — asserts `asyncio.run(server.serve())` but now receives their new `_serve_with_heartbeat` coroutine |
| `test_auth_coverage.py::…test_no_credentials` | `download-proxy/src/api/auth.py` `all_trackers_auth_status` — untouched here; `grep -rn env_loader download-proxy/src/` is **empty**, so there is no import path from any changed file |
| `test_no_runtime_service_skips` | flags `tests/scaling/test_boba_scaling.py:73` — a scaling test untouched here |

The nova3 plugin contract is guarded explicitly: `test_nova3_contract_preserved`
loads `rutor`, `rutracker`, `anilibra` and `iptorrents` and asserts each still
exports its engine class with `url`, `name`, `supported_categories`, `search()`
and `download_torrent()`. A fix that broke plugin loading would fail there.

---

## 7. What promoting the gate to BLOCKING now requires

Not a decision made here (§11.4.224(E)/§11.4.66 — operator-owned).

The 30 remaining hits are **0 bucket (A)**: 16 bucket (B) — the original 14 plus
A4/A6, which are now narrow `except OSError:` cleanup handlers but remain swallow-
SHAPED and therefore still reported — and 14 bucket (C). None
is a defect. Promotion therefore requires a checked-in exclusion/exemption fence
declaring those 30, each justified from a closed class set, per §11.4.224(E) —
first-party (B) entries and vendored (C) entries are different justifications and
should be listed as such.

Three honest caveats for that decision:

1. **§0.2 (L1–L3)** — the gate misses **12** sites of the very shape it claims to
   detect, so a zero-hit gate does not mean zero swallowed exceptions. Worth
   fixing upstream before promotion, otherwise the fence will be written against
   an undercount.
2. **§0.2 (fourth limitation)** — `except: return <default>` is out of the gate's
   shape by construction; **13** such sites remain, all in vendored trees.
3. **§0.1** — invariant 39's hit count is inflated by one per failing root.

---

## 8. UNKNOWN / not determined (§11.4.6)

- **Nothing was left unclassified.** All 36 gate-reported hits carry a bucket and a
  justification.
- **Upstream-exactness of C1–C4, C14 was not byte-verified.** Those five files have
  no `plugins/community/` twin to diff against, and fetching upstream was out of
  scope. Their (C) classification rests on the upstream `# VERSION:`/`# AUTHORS:`
  header plus the bulk-import commit message — strong, but not byte-proof. Stated
  as a bounded limitation rather than claimed as certainty. C5–C8 **are**
  byte-verified against their twins.
- **Whether `plugins/community/` should be a §11.4.224(E) declared exclusion or be
  brought into first-party scope** is an operator decision, not made here.
