#!/usr/bin/env bash
# cm_dangerous_combination_fail_closed.sh — CM-DANGEROUS-COMBINATION-FAIL-CLOSED
# gate (anchor §11.4.252).
#
# ── Purpose ──────────────────────────────────────────────────────────────────
# §11.4.252 mandates: any code path COMBINING >= 2 dangerous capabilities
# (mutation / untrusted-input / credential-access / external-side-effect /
# shell-exec / irreversible) MUST FAIL CLOSED -- refuse unless every
# precondition is verifiably satisfied, NEVER fail open on an ambiguous /
# missing / unresolvable signal. The anchor names a CLOSED SET of fail-open
# ANTI-PATTERN SHAPES that are the concrete violation forms:
#     catch { /* ignore */ }
#     credential = credential || default
#     if (!valid) { log("warn"); return proceed(input); }
#     target = user_input || default_target
#     unbounded retry { dangerous(); }
#
# ── Detection scope (honest, stated tradeoff — §11.4.6) ─────────────────────
# PROVING that a code path genuinely COMBINES >= 2 dangerous capabilities
# (per the anchor's 6-member taxonomy) requires real data-flow / control-
# flow analysis this gate CANNOT honestly claim. This gate therefore
# implements the LITERAL, NAMED, structurally-precise HALF of the anchor --
# detecting the two most structurally unambiguous fail-open anti-pattern
# SHAPES the anchor itself enumerates:
#
#   (A) SWALLOWED EXCEPTION — a handler that neither re-raises, nor logs, nor
#       performs any fallback work. Two concrete, decidable body shapes:
#         (A1) SWALLOW          the sole body statement is `pass` (or `...`)
#         (A2) SILENT DEFAULT   the sole body statement returns a TRIVIAL
#                               LITERAL (bare `return`, a constant, or an
#                               EMPTY container). Handing the caller a
#                               plausible-looking value that carries zero
#                               information about the failure is the same
#                               fail-open defect as `pass` -- arguably worse,
#                               because the caller cannot tell it happened.
#       For C-family/JS/TS/Java/C#/PHP the analogue is an empty or
#       comment-only `catch (...) { }` body.
#
#   (C) SUPPRESSED-EVERYTHING CONTEXT MANAGER — `with contextlib.suppress(
#       Exception)` (or `BaseException`). This is the SAME defect as (A1)
#       written as a `With` node instead of a `Try` node: it swallows every
#       exception the block can raise and continues. It is called out
#       separately because linters commonly push authors toward it -- ruff's
#       SIM105 says "use contextlib.suppress instead of try-except-pass" --
#       so a gate blind to it does not merely have a gap:
#       every SIM105 autofix silently MIGRATES a detected site into an
#       undetected one while the lint count falls, which reads as progress.
#
#       DETECTION IS BY IMPORT BINDING, NOT BY NAME (§11.4.201(7)(a)):
#       `contextlib.suppress` / an aliased module (`import contextlib as ctx`
#       -> `ctx.suppress`) / a direct import (`from contextlib import
#       suppress [as quiet]`) all resolve; a project-LOCAL function that
#       happens to be called `suppress` does NOT (matching the bare name
#       would refuse healthy code -- a §11.4.201(1) FAIL-bluff).
#
#       ONLY THE BROAD FORM IS FLAGGED. `suppress(Exception)` /
#       `suppress(BaseException)` swallow everything and are the violation.
#       `suppress(FileNotFoundError)` is a DECLARED, BOUNDED tolerance --
#       the developer named exactly the one failure they accept and every
#       other exception still propagates -- and is deliberately NOT flagged.
#       `suppress()` with NO arguments is likewise NOT flagged: it suppresses
#       NOTHING (`issubclass(exc, ())` is always False), verified empirically
#       rather than assumed (§11.4.6). An argument list that cannot be
#       resolved statically (a starred/computed argument) is reported under
#       its own distinct message per §11.4.201(4)'s conservative-safe-on-
#       unresolvable rule, naming the unresolved signal rather than guessing.
#
#       HONEST RESIDUAL GAPS (§11.4.6) -- named, never silent:
#         * ASYMMETRY. A NARROW `try/except X: pass` IS flagged by (A1)
#           while the semantically-equivalent `with suppress(X)` is NOT, so
#           a SIM105 rewrite of a narrow handler moves that site out of
#           scope. Flagging narrow suppression instead would fire on the
#           idiomatic, correct form, and a false-positive storm is the worse
#           defect (§11.4.201(1)) -- so the asymmetry is recorded as a known
#           gap rather than closed by over-reach. Whether to close it is a
#           consumer/operator decision (§11.4.66), not a default this gate
#           picks; a consuming project measures its OWN corpus before
#           deciding, since the trade depends entirely on how many narrow
#           sites that corpus holds.
#         * INDIRECTION. Resolution is syntactic and FLOW-INSENSITIVE, so it
#           errs in BOTH directions on value-flow shapes -- measured, not
#           assumed, and BOTH modes agree on every case below (no divergence):
#             - UNDER: a call reached indirectly is NOT seen --
#               `getattr(contextlib, "suppress")(...)`, or a module rebound
#               through an intermediate local (`s = othermod` then
#               `s.suppress(...)`, correctly silent; `c = contextlib` then
#               `c.suppress(...)`, missed). Measured ast_rc=0 / text_rc=0.
#             - OVER: a name BOUND to contextlib and later REBOUND away
#               (`import contextlib as c` ... `c = othermod` ...
#               `c.suppress(Exception)`) is still matched on the import that
#               no longer holds at the call. Measured ast_rc=1 / text_rc=1.
#           Both directions need value-flow analysis this gate does not
#           claim. The OVER case is contrived and broken-at-runtime for any
#           module lacking a `suppress`, so it is DOCUMENTED, not built for;
#           both remain review territory (§11.4.142/§11.4.194).
#         * BREADTH BY NAME. Any attribute named `Exception` counts as broad,
#           so a project module's own `errors.Exception` would be flagged.
#           This is deliberately the conservative direction: over-reporting a
#           genuinely-named `Exception` is recoverable, silently passing the
#           builtin is not.
#         * DEGRADED MODE. The text fallback approximates the binding from
#           the import LINES. It DOES resolve a module alias NAME (so
#           `import contextlib as ctx` -> `ctx.suppress(...)` is matched,
#           while an unrelated `othermod.suppress(...)` is not), but it
#           cannot see anything that is not on the single `with` line or in
#           a recognised import line. It ANNOUNCES itself, and its gaps are
#           MEASURED against this gate rather than assumed (§11.4.6).
#
#           DIRECTION, stated precisely. This sentence has been WRONG TWICE,
#           and the shape of both errors is the same -- an absolute claim the
#           code did not support -- so it is now stated WITHOUT one: an
#           earlier revision called every gap an UNDER-report; the revision
#           after it corrected the direction but asserted exactly ONE
#           over-reporting class, and an independent reviewer then MEASURED
#           three more. Text mode is an APPROXIMATION, *not* a floor: a floor
#           may not contain false hits, and text mode has SEVERAL measured
#           over-reporting classes.
#
#           BOTH lists below are MEASURED SAMPLES, not proven-complete
#           censuses (§11.4.118 -- "we found no others" is a bluff unless the
#           search is enumerated, and the enumeration here is a set of probed
#           shapes, not a proof of exhaustion). Every entry was reproduced
#           with a control-needle-proven probe and carries its measured
#           ast/text verdict. NO claim is made that further classes do not
#           exist; a class found later is EXPECTED, is appended here, and per
#           §11.4.238 its absence from this list is itself the finding.
#
#           The measured UNDER gaps -- a real violation the text scan misses;
#           all SEVEN measured ast=1 / text=0:
#             - an ALIASED direct import (`from contextlib import suppress
#               as quiet`): the bound name is unknowable from the call site;
#             - an UNRESOLVABLE argument list (`suppress(*EXCS)`, and equally
#               the keyword form `suppress(**kw)`): the AST analyser reports
#               both under its own conservative-safe message (§11.4.201(4)),
#               but the line carries no `Exception` token for a text scan to
#               match;
#             - a BOM'd file whose contextlib import is on line 1: the BOM
#               bytes precede `import` and defeat the line-anchored match;
#             - a MULTI-LINE call (`suppress(<newline> Exception <newline>)`):
#               the exception class is not on the `with` line;
#             - a TRAILING-POSITION multi-import (`import os, contextlib`);
#             - a from-import whose NAME LIST CONTINUES ONTO ANOTHER LINE
#               (`from contextlib import (<newline> suppress, ...)`, or a
#               backslash continuation): the bound names are not on the
#               matched line, so nothing binds. Same-line lists -- bare,
#               parenthesised, and with `suppress` in any position -- are
#               bound correctly;
#             - a SEMICOLON-COMPOUND statement (`import contextlib; import
#               os`, and equally `import os; from contextlib import
#               suppress`): both import regexes are line-anchored and accept
#               only a comma or end-of-line after the module name, so a `;`
#               ends the match and NOTHING binds. Rare and PEP8-hostile, but
#               legal Python; measured ast=1 / text=0 in both forms.
#           All seven are seen correctly by the AST analyser -- which is
#           exactly why it is the primary and this is only the fallback.
#
#           The measured OVER classes -- healthy code the text scan REFUSES;
#           all measured ast=0 / text=1, each a §11.4.201(1) FAIL-bluff:
#             - OVER-1, WHOLE-LINE STRING CARRIER. A `with contextlib.
#               suppress(Exception):` line written INSIDE a docstring or a
#               string literal (a style guide documenting the anti-pattern,
#               this gate own fixtures) satisfies the line-shaped `with` test
#               and is matched as if it were code.
#             - OVER-2, STRING-HARVESTED IMPORT. A docstring containing
#               `from contextlib import suppress` -- or `import contextlib`
#               -- BINDS that name in the licensing table, so a genuinely
#               project-LOCAL `suppress(Exception)` elsewhere in the same
#               file is then refused. A DISTINCT MECHANISM from OVER-1: the
#               string-blindness lives in the IMPORT HARVESTERS (T1-T3), not
#               in the with-line test, so closing one would not close this.
#               (Control needle: a `#`-COMMENTED import does NOT poison the
#               table -- measured text=0 -- because those regexes are
#               line-anchored. The blindness is to STRINGS specifically.)
#             - OVER-3, STRING-ARGUMENT CARRIER. A REAL `with` line whose
#               STRING ARGUMENT quotes the pattern -- `with lock.hold("never
#               use suppress(Exception) here"):` in a file that really does
#               import contextlib. Unlike OVER-1 the LINE IS CODE; only the
#               argument is a carrier. Measured for both the bare and the
#               dotted spelling.
#             - OVER-4, EXCEPT-SHAPE STRING CARRIER. The same class in the
#               OTHER text scanner: a docstring or string constant holding
#               `except Exception:` / `pass` is read by `scan_py_text` as a
#               handler (the L5 fixture measures text=1 with two hits). The
#               "FALSE POSITIVES" paragraph further down predicts exactly
#               this shape; it is recorded HERE because the previous
#               over-direction list silently scoped itself to the suppress
#               scanner while stating a cardinality for text mode as a whole.
#
#           THE EXCEPT SHAPE ALSO HAS ITS OWN TEXT-MODE *UNDER* DIRECTION,
#           enumerated here because the per-shape caveat previously named
#           only the OVER class above and so read as if the under-direction
#           were the suppress scanner problem alone (§11.4.201(6): a
#           direction nobody names reads as a direction nobody has):
#             - EXCEPT-UNDER-1, ONE-LINE HANDLER. `except Exception: pass`
#               written on a SINGLE line is missed: the except-line matcher
#               requires end-of-line after the colon and then looks at the
#               NEXT line for the body. Measured ast=1 / text=0.
#             - EXCEPT-UNDER-2, DOCSTRING BEFORE THE BODY. A handler whose
#               `pass` is preceded by a string statement -- `except
#               Exception:` / `"why we ignore this"` / `pass` -- is missed
#               for the same reason: the line after the `except` is not the
#               body statement. The AST analyser drops the docstring and
#               classifies the swallow correctly. Measured ast=1 / text=0,
#               and pinned in STRUCTURAL mode by fixture L38.
#           Both are UNDER-reports of the text FALLBACK only; neither
#           affects the AST analyser, which is the primary.
#
#           CLOSED THIS ROUND (it was a fifth over class, found by review):
#           a `#` COMMENT on a REAL `with` line -- `with suppress(
#           FileNotFoundError):  # was suppress(Exception) before review` --
#           was matched as if the comment were the call own argument, which
#           sat OUTSIDE the string-literal class above even though this
#           header already predicted comment carriers for the `except` shape.
#           The with-line scan now strips a trailing comment QUOTE-AWARELY
#           before any shape or token test (see `strip_comment`).
#
#           THIS CLOSE DID OPEN AN UNDER-REPORT, AND THE UNDER-REPORT WAS
#           ITSELF A REGRESSION -- recorded here because the previous
#           revision of this paragraph asserted the opposite as an ABSOLUTE
#           ("opens NO under-report ... cuts only at a `#` PROVABLY outside
#           every string"), and that assertion was refuted by measurement,
#           not by argument. The first strip read a triple quote as three
#           independent one-character toggles, so in a line such as
#           `with lock.hold(<DQ3>a<DQ>#b<DQ3>), suppress(Exception):` the
#           quote after `a` closed the string early, the `#` INSIDE it read
#           as outside, the line was cut there, and the real
#           `suppress(Exception)` after the cut was SILENTLY DELETED from the
#           scan. Measured ast=1/text=0 for both the double- and
#           single-quoted triple forms, while reverting the strip CALL alone
#           restored text=1: the pre-strip scanner had caught both. The word
#           "provably" was doing no work -- nothing proved it.
#
#           WHAT IS CLAIMED NOW is bounded and measured, never absolute: the
#           strip tracks single AND triple delimiters and honours backslash
#           escapes; every shape this gate carries a fixture for strips at
#           the intended position or not at all; an UNTERMINATED quote leaves
#           the line UNCUT. TWO BLIND SPOTS REMAIN OPEN and are named in
#           `strip_comment` itself -- an opening quote on an EARLIER line,
#           and PEP 701 nested same-quote f-strings -- because each needs
#           state a single-line function does not have. Neither is claimed
#           absent or unreachable. Pinned by fixtures L30 (the carrier), L33
#           (a `#` inside a string), L34 (an escaped quote before one), L35
#           and L36 (the two triple delimiters) and L37 (the apostrophe half
#           of the tracker, which L33/L34 both left unpinned).
#
#           WHY OVER-1..OVER-4 ARE NOT CLOSED -- scope-bounded per
#           §11.4.112(5), because the previous revision stated this verdict
#           TOO WIDELY ("STRUCTURALLY unclosable ... deciding that a line
#           lives inside a string requires the parse tree"), which overstates
#           it twice over:
#             (a) The exact decision needs LEXICAL STRING-REGION TRACKING --
#                 knowing which byte ranges of the file are inside a string
#                 -- NOT the parse tree. A line scanner has neither, which is
#                 why the classes exist, but the claim is about LEXING.
#             (b) A BOUNDED PARTIAL DEFENCE EXISTS and is DELIBERATELY NOT
#                 BUILT: a running triple-quote fence counter (track `"""`
#                 and `'''` openers as the file is read; treat lines inside
#                 an open fence as non-code) correctly labels every carrier
#                 shape measured here. It is DECLINED because its failure
#                 mode runs the WRONG WAY: a lone triple-quote inside a
#                 single-quoted string, an f-string, or a comment flips the
#                 fence, and every subsequent REAL line in that file is then
#                 treated as non-code -- trading a visible, recoverable
#                 over-report for a SILENT UNDER-report across the rest of
#                 the file. This gate has already recorded that asymmetry
#                 once ("over-reporting a genuinely-named `Exception` is
#                 recoverable, silently passing the builtin is not"), and it
#                 decides here too -- and the DECLINE half of that reasoning
#                 has since been independently re-measured and held: a lone
#                 triple quote inside a single-quoted string does flip a
#                 naive fence counter and does silently suppress a later real
#                 violation.
#                 THE ACCEPT HALF DID NOT HOLD. The comment strip that
#                 closed the fifth class was accepted on an ABSOLUTE about
#                 the direction its ambiguity always resolves -- that it
#                 could only ever keep text, never lose any. That absolute is
#                 REFUTED and is deliberately NOT restated here even to
#                 quote it, because a sentence asserting it, in any framing,
#                 is indistinguishable from the real thing to a grep and to
#                 a skimming reader. What actually happened: the
#                 triple-quote blindness LOST text on a SAME-LINE shape (see
#                 the OVER-5 paragraph above), so the asymmetry argument was
#                 sound in general and MISAPPLIED here -- at that revision
#                 the strip was not on the side of it that was claimed.
#                 The strip is retained because the defect was in the QUOTE
#                 MODEL, not in the decision to strip: a same-line model
#                 needs no cross-line state and so cannot inherit the fence
#                 counter failure mode. NO directional guarantee replaces the
#                 refuted one. What licenses the strip now is narrower and
#                 checkable: a measured fixture set (L30, L33-L37, L40, L41)
#                 in which every shape strips at the intended position or not
#                 at all, plus TWO explicitly-named remaining blind spots
#                 whose direction is NOT claimed either way.
#           ADJACENT GOALS THIS VERDICT DOES NOT COVER (enumerated per
#           §11.4.112(5), never absorbed into the word "impossible"):
#             (i)   the fence-count partial defence above;
#             (ii)  a REFUSAL-TO-DECIDE mode that reports lines inside an
#                   apparent triple-quote region as UNRESOLVED rather than
#                   silently deciding either way (§11.4.201(4) applied to the
#                   text scanner);
#             (iii) a real lexer for the fallback;
#             (iv)  a SAME-LINE triple-quote-aware quote model -- distinct
#                   from (i) because it carries NO cross-line state and so
#                   cannot inherit the fence counter failure mode, and
#                   distinct from (iii) because it decides only "is this `#`
#                   inside a string on THIS line".
#           (iv) WAS OMITTED FROM THIS ENUMERATION WHEN THE STRIP LANDED, and
#           that omission is why a defect with a cheap, state-free fix was
#           argued about as though the only alternatives were a fence counter
#           or a lexer. It has since been BUILT and is what `strip_comment`
#           now implements; it is listed here as a closed goal so the
#           enumeration records the shape of the miss, not only its repair.
#           (i), (ii) and (iii) remain UNDECIDED -- an operator / consumer
#           call (§11.4.66), none measured here. The AST analyser is immune
#           to all four OVER classes by construction, which is why it is the
#           primary and this is only the fallback.
#
#       IDENTIFICATION LAYER -- which call is a `suppress()` call AT ALL
#       (§11.4.201(7)(a)). The licensing table further down answers "do this
#       file's imports license the NAME?"; this layer answers the PRIOR
#       question, "is this token even the name?", and the SAME presence-shaped
#       defect that licensing kept re-growing lives here too. Per §11.4.250 a
#       class returning at a new layer is a signal about the primitive, not
#       about the instance -- so this layer is ENUMERATED with the same
#       EXACT/PRESENCE discipline instead of being left to be re-derived:
#
#         AST analyser (`is_suppress_call`)
#           I1 `item.context_expr` isinstance ast.Call               EXACT
#           I2 dotted: `func.attr == "suppress"` (whole attribute)   EXACT
#           I3 dotted: `isinstance(func.value, ast.Name)` -- the
#              prefix must be a SIMPLE name, so
#              `pkg.contextlib.suppress(` is NOT a contextlib call   EXACT
#           I4 bare: `isinstance(func, ast.Name)` + id lookup        EXACT
#
#         Text fallback (`scan_py_text_suppress`)
#           I5 the statement line matches the `with`-line regex      PRESENCE
#              -- line-shaped, not parse-shaped: this is the
#              approximation that admits OVER-1 and OVER-3 above.
#              It is NOT "the only PRESENCE-class decision left in
#              either layer" -- an earlier revision claimed that and
#              measurement refuted it: the import harvesters T1-T3
#              are equally line-shaped (that is OVER-2), and shape
#              (B) plus the C-family half of shape (A) are
#              line-shaped in EVERY mode (see MODE-INDEPENDENT
#              CARRIERS below). Cardinality claims about this gate
#              own PRESENCE surface have now been wrong twice; none
#              is made here.
#           I6 the call token is the WHOLE identifier `suppress`,
#              a required non-word character (or line start) before
#              it, so `try_suppress(` is not read as `suppress(`     EXACT
#           I7 the dotted prefix is the identifier immediately
#              before the `.` AND is not itself dot-/word-preceded
#              -- the text mirror of I3                              EXACT
#           I8 the breadth token `(Base)?Exception` is word-boundary
#              matched within THIS call's own argument list (paren-
#              balanced), never the rest of the line              EXACT/BOUNDED
#              -- the WORD-BOUNDARY test is exact on BOTH sides
#              (prefix pinned by fixture L15, suffix by L32). The
#              ARGUMENT-LIST BOUND is approximate: `arglist` counts
#              parens over RAW characters, so a paren inside a
#              STRING argument miscounts depth. Measured across
#              every constructible divergence shape, that string
#              sits in suppress OWN argument list, which the AST
#              analyser then reports UNRESOLVED (§11.4.201(4)) --
#              ast=1/text=1, so both modes fail CLOSED and no mode
#              divergence escapes. Labelling this bound "EXACT" (as
#              an earlier revision did) overstated it.
#
#       I6 / I7 / I8 were each added after a MEASURED ast=0 / text=1
#       divergence -- three live §11.4.201(1) FAIL-bluffs in which text mode
#       refused provably-healthy code -- and each is pinned by its own
#       negative-control fixture in the paired mutation test.
#
#   (B) CREDENTIAL SILENTLY DEFAULTED TO A LITERAL — a credential-shaped
#       identifier (credential/secret/token/api_key/apikey/password/passwd,
#       case-insensitive) assigned via an `||` / `or` fallback DIRECTLY to a
#       quoted string LITERAL. This is the literal `credential = credential
#       || default` anti-pattern. A fallback to an env-var read / secrets-
#       manager call / config lookup is a DIFFERENT, legitimate pattern and
#       is deliberately NOT flagged (§11.4.6 — a literal default value is
#       the unambiguous violation shape; a secondary CREDENTIAL SOURCE is
#       not).
#
# ── Why Python is analysed STRUCTURALLY, not textually (§11.4.201(7)(a)) ────
# Shape (A) is a property of the PARSE TREE, not of the source text, and a
# text scanner gets it wrong in BOTH directions -- each direction a §11.4
# bluff in its own right:
#
#   FALSE NEGATIVES (a §11.4.201(6) false-null: the gate returns a confident
#   number that is an APPROXIMATION, not a census) — a line-anchored regex
#   cannot see
#     * `except Exception:  # noqa: S110`   (a trailing comment; the sites a
#       human consciously reviewed and annotated are exactly the ones the
#       scanner goes blind to)
#     * `except (OSError, ValueError):`     (a tuple clause)
#     * a comment sitting between `except` and `pass` (so a reviewer ADDING
#       an explanatory comment silently deletes the site from the report)
#     * `except: return None`               (the (A2) silent-default shape)
#
#   FALSE POSITIVES (a §11.4.201(1) FAIL-bluff: refusing healthy code) — a
#   text scanner fires on a CARRIER: a docstring, comment, or string literal
#   that merely MENTIONS `except: pass`, such as a style guide documenting
#   the anti-pattern, or this gate's own test fixtures.
#
# A parser is immune to both by construction -- FOR THE PYTHON `Try` / `With`
# SHAPES IT OWNS: a string literal is not a `Try` node, and a comment is not
# a statement. Python files are therefore analysed with the stdlib `ast`
# module when a Python 3 interpreter is available. When one is NOT available
# the gate falls back to a hardened text scan and says so LOUDLY on stdout --
# a degraded instrument that announces its degradation, never a silent floor
# reported as a census (§11.4.6 / §11.4.201(6)).
#
# ── MODE-INDEPENDENT CARRIERS (§11.4.6 — measured, DISCLOSED, not closed) ───
# That immunity is SCOPED to the Python `Try` / `With` shapes the AST
# analyser owns, and an earlier revision stated it without the scope. It does
# NOT extend to the other two detectors: shape (B) and the C-family half of
# shape (A) are language-agnostic greps with NO structural counterpart in ANY
# mode, so their carrier false-positives fire in the PRIMARY mode too, not
# only in the degraded fallback. Each measured ast_rc=1 AND text_rc=1:
#   * Shape (B), CREDENTIAL — a comment or a docstring QUOTING the
#     anti-pattern (`# NEVER write: api_key = cfg_key or "hunter2"`, or a
#     style-guide docstring containing `password = supplied or "changeme"`)
#     is reported as a live credential default.
#   * Shape (A), C-FAMILY `catch` — a `//` comment or a string constant
#     holding `try { x(); } catch (e) { }` is reported as an empty catch
#     block, once per carrier line.
# DISCLOSED, not built for. Closing them needs a per-language comment-and-
# string model across every configured extension, and that model fails in the
# UNDER direction this gate elsewhere refuses to take: a mis-modelled string
# region deletes REAL code from the scan. The asymmetry already recorded for
# BREADTH BY NAME governs here too -- over-reporting a carrier is visible and
# recoverable; silently passing a real fail-open path is not. Whether to build
# it is an operator / consumer decision (§11.4.66) and a tracked work item
# (§11.4.197), never a default this gate picks. Stating these two is NOT a
# claim the list is complete: it is a MEASURED SAMPLE of two detectors
# (§11.4.118), exactly as the degraded-mode lists above are.
#
# This gate does NOT attempt to detect the remaining three anchor shapes
# (validate-then-proceed-anyway, untrusted-input-defaulted-to-a-target,
# unbounded-retry-around-a-dangerous-call) — each requires either multi-line
# control-flow correlation or a semantic "is this retry bounded" judgement
# that would risk becoming an unreliable, bluff-prone heuristic. Their
# coverage remains §11.4.142/§11.4.194 human-review territory, stated as an
# honest gap (§11.4.6), never silently claimed covered. Likewise a handler
# body of TWO OR MORE statements is deliberately NOT flagged: it is doing
# SOMETHING, and deciding whether that something constitutes genuine
# fallback handling is a judgement, not a decidable structural fact.
#
# ── Usage ────────────────────────────────────────────────────────────────────
#   cm_dangerous_combination_fail_closed.sh [--root <dir>] [--quiet]
#     --root <dir>   scan root (default: $DANGEROUS_COMBO_ROOT or "..")
#     --quiet        suppress per-file PASS lines (FAIL lines always shown)
#     -h|--help      print this header
#
# ── Environment overrides (§11.4.28/§11.4.35 — project-agnostic) ────────────
#   DANGEROUS_COMBO_ROOT      default scan root (else --root, else "..")
#   DANGEROUS_COMBO_EXT       space-separated source extensions to scan
#                              (default: "py go rs c cc cpp h hpp java cs js
#                               ts jsx tsx php rb")
#   DANGEROUS_COMBO_EXCLUDE   space-separated dir-name globs to prune
#                              (default: ".git node_modules vendor .venv
#                               __pycache__ scripts/gates out build dist")
#   DANGEROUS_COMBO_PYTHON    Python 3 interpreter used for AST analysis of
#                              .py files (default: python3, then python).
#
# ── Outputs ──────────────────────────────────────────────────────────────────
#   Per-hit evidence line (file:line + matched anti-pattern class) + a final
#   PASS / FAIL verdict. Degraded-mode and unparseable-file NOTEs when the
#   structural analysis could not be applied.
#
# ── Side-effects ─────────────────────────────────────────────────────────────
#   None (read-only). The AST analyser PARSES Python sources; it never
#   IMPORTS or EXECUTES them (`ast.parse` runs no user code).
#
# ── Dependencies ─────────────────────────────────────────────────────────────
#   bash, find, grep (GNU or BSD ERE), sed, awk. OPTIONALLY a Python 3
#   interpreter for structural analysis of .py files (absence is handled
#   honestly, never silently). Parses clean under bash -n.
#
# ── Cross-references ─────────────────────────────────────────────────────────
#   §11.4.252 (the anchor enforced — literal-shape half), §11.4.201(1)/(6)/
#   (7)(a) (false-positive refusal is a FAIL-bluff; a null is not evidence;
#   match structure not substring), §11.4.6 (honest documented bounded
#   limitation, never silent), §11.4.28/§11.4.35 (project-agnostic, env-var-
#   driven), §1.1 (paired mutation:
#   cm_dangerous_combination_fail_closed_mutation_test.sh).
#
# ── Exit codes ───────────────────────────────────────────────────────────────
#   0 — PASS (no candidate source files, or no anti-pattern hit found).
#   1 — FAIL (a swallowed-exception, silent-default-return, or credential-
#       default-to-literal hit).
#   2 — environment / argument error.
#
# Classification: universal (§11.4.17) — no project-specific literal.

set -uo pipefail

GATE="CM-DANGEROUS-COMBINATION-FAIL-CLOSED"
ANCHOR="11.4.252"

# SINGLE SOURCE OF TRUTH for how the degraded TEXT-mode result is described.
# FIVE call-sites announce the degradation; stating the caveat once keeps them
# from drifting apart and keeps the claim correctable in ONE place when the
# measured gap set changes (§11.4.251 — one copy, never five near-identical
# forks of a load-bearing sentence).
#
# The wording is MEASURED, not aspirational. It says APPROXIMATION rather than
# FLOOR deliberately: a floor may not contain false hits, and text mode has
# several measured over-reporting classes, so calling its output a floor would
# be a claim the code contradicts.
#
# It also states NO completeness. Two earlier revisions of this sentence each
# carried an absolute the code did not support ("every gap under-reports",
# then "ONE over-reporting class"), and both were refuted by measurement. The
# counts below are MEASURED SAMPLES and say so out loud, so a reader is told
# the size of what was probed and NOT told that nothing else exists
# (§11.4.118). The full enumeration, per class, is in the --help header.
TEXT_MODE_CAVEAT="a DEGRADED APPROXIMATION, not a census — for the suppress shape it UNDER-reports in seven measured ways and has FOUR measured OVER-reporting classes (a whole line inside a string, a licensing import harvested from a string, or a real line whose own string ARGUMENT quotes the pattern — each matched as if it were code); the except shape carries its own string-carrier OVER class AND two measured UNDER shapes of its own (a one-line except-with-pass written on a SINGLE line, and a handler whose pass is preceded by a docstring — both ast=1/text=0). Both counts are MEASURED SAMPLES, not proven-complete censuses; see --help for the per-class enumeration — §11.4.6/§11.4.118/§11.4.201(6)"
HEADER_LINES=494

root="${DANGEROUS_COMBO_ROOT:-..}"
quiet=0

while [ $# -gt 0 ]; do
    case "$1" in
        --root) root="$2"; shift 2 ;;
        --quiet) quiet=1; shift ;;
        -h|--help) sed -n "1,${HEADER_LINES}p" "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "${GATE}: unknown arg '$1'" >&2; exit 2 ;;
    esac
done

[ -d "$root" ] || { echo "${GATE}: scan root not found: $root" >&2; exit 2; }
root="$(cd "$root" && pwd)"

exts="${DANGEROUS_COMBO_EXT:-py go rs c cc cpp h hpp java cs js ts jsx tsx php rb}"
excludes="${DANGEROUS_COMBO_EXCLUDE:-.git node_modules vendor .venv __pycache__ scripts/gates out build dist}"

find_name_expr=()
first=1
for e in $exts; do
    if [ "$first" -eq 1 ]; then first=0; else find_name_expr+=(-o); fi
    find_name_expr+=(-name "*.${e}")
done

prune_expr=()
for ex in $excludes; do
    case "$ex" in
        */*) prune_expr+=(-path "*/${ex}" -o -path "*/${ex}/*" -o) ;;
        *)   prune_expr+=(-name "$ex" -o) ;;
    esac
done
if [ "${#prune_expr[@]}" -gt 0 ]; then
    unset 'prune_expr[${#prune_expr[@]}-1]'
fi

mapfile -d '' -t files < <(
    if [ "${#prune_expr[@]}" -gt 0 ]; then
        find "$root" -type d \( "${prune_expr[@]}" \) -prune -o -type f \( "${find_name_expr[@]}" \) -print0
    else
        find "$root" -type f \( "${find_name_expr[@]}" \) -print0
    fi
)

if [ "${#files[@]}" -eq 0 ]; then
    echo "⏭ ${GATE}: SKIP — topology_unsupported: no source files under scan (root=$root, ext=[$exts])"
    exit 0
fi

hits=0

# ── Python interpreter discovery for the structural analyser ────────────────
# Resolved by REAL capability, not by name alone: the candidate must actually
# run and import `ast` (§11.4.201 — assert the real condition, and take the
# conservative-safe path, announced, when the signal is unresolvable).
py_bin=""
py_usable() { # $1=candidate -> 0 when it really runs and can import ast
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c 'import sys, ast; sys.exit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1
}
if [ -n "${DANGEROUS_COMBO_PYTHON:-}" ]; then
    # An EXPLICIT operator pin is authoritative: if it does not resolve to a
    # working Python 3 the gate degrades LOUDLY rather than silently
    # substituting a different interpreter behind the operator's back
    # (§11.4.6 / §11.4.201 — say what actually happened).
    if py_usable "$DANGEROUS_COMBO_PYTHON"; then
        py_bin="$DANGEROUS_COMBO_PYTHON"
    else
        echo "⚠ ${GATE}: NOTE — DANGEROUS_COMBO_PYTHON='${DANGEROUS_COMBO_PYTHON}' is not a usable Python 3; NOT substituting another interpreter. Python files fall back to the TEXT scanner, whose results are ${TEXT_MODE_CAVEAT}."
    fi
else
    for cand in python3 python; do
        if py_usable "$cand"; then py_bin="$cand"; break; fi
    done
fi

# ── Text-scan fallback for Python (used only when no interpreter is present,
#    or for a file the parser could not read). Hardened relative to the
#    original line-anchored form so the degraded mode is a HIGHER floor:
#    it now tolerates a tuple clause and a trailing comment on the `except`
#    line, and skips comment/blank lines inside the handler body. It still
#    cannot see string-literal carriers, which is exactly why it is the
#    fallback and not the primary. ──────────────────────────────────────────
scan_py_text() { # $1=file  -> echoes one "lineno" per swallowed handler
    local f="$1"
    awk '
        function indent_of(s,   t) { t = s; sub(/[^ \t].*$/, "", t); return length(t) }
        function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
        {
            lines[NR] = $0
        }
        END {
            for (i = 1; i <= NR; i++) {
                line = lines[i]
                # `except`, optional clause (may contain a tuple / dotted name /
                # `as` binding), colon, optional trailing comment.
                if (line !~ /^[ \t]*except([ \t]+[^:#]+)?[ \t]*:[ \t]*(#.*)?$/) continue
                exc_indent = indent_of(line)
                # first REAL statement of the handler body: skip blank and
                # comment-only lines (a comment must not hide the body).
                body_i = 0
                for (j = i + 1; j <= NR; j++) {
                    t = trim(lines[j])
                    if (t == "" || substr(t, 1, 1) == "#") continue
                    body_i = j
                    break
                }
                if (body_i == 0) continue
                body = trim(lines[body_i])
                is_swallow = 0
                if (body == "pass" || body == "...") {
                    is_swallow = 1
                } else if (body ~ /^return[ \t]*$/) {
                    is_swallow = 1                 # bare `return`
                } else if (body ~ /^return[ \t]+/) {
                    # Silent default: `return <trivial literal>` only. The
                    # value is compared as a STRING rather than matched by
                    # regex so no quote character has to be escaped through
                    # the bash -> awk -> ERE layers (§11.4.201(7)(c): the
                    # quoting path is part of the instrument).
                    val = body
                    sub(/^return[ \t]+/, "", val)
                    sub(/[ \t]+$/, "", val)
                    q = sprintf("%c", 39)          # apostrophe, unquotable inline
                    if (val == "None" || val == "True" || val == "False" ||
                        val == "[]" || val == "{}" || val == "()" ||
                        val ~ /^-?[0-9]+(\.[0-9]+)?$/) {
                        is_swallow = 1
                    } else if (val ~ /^"[^"]*"$/ || val ~ ("^" q "[^" q "]*" q "$")) {
                        # A plain quoted string constant (`return "NotFound"`).
                        # An f-string / concatenation does NOT match, because the
                        # value would not START with the quote character - those
                        # compute something and are fallback handling, not a
                        # silent default.
                        is_swallow = 1
                    }
                }
                if (!is_swallow) continue
                # the handler body must consist of that ONE statement: the next
                # real line must dedent out of the body (or the file ends).
                nxt = 0
                for (j = body_i + 1; j <= NR; j++) {
                    t = trim(lines[j])
                    if (t == "" || substr(t, 1, 1) == "#") continue
                    nxt = j
                    break
                }
                if (nxt != 0 && indent_of(lines[nxt]) > exc_indent) continue
                print i
            }
        }
    ' "$f" 2>/dev/null || true
}

# Degraded-mode counterpart of shape (C). Text mode approximates the import
# binding from the import LINES: a dotted `<prefix>.suppress(` call is
# matched only when <prefix> is a NAME THIS FILE BOUND to the contextlib
# module (`import contextlib` -> `contextlib`; `import contextlib as ctx`
# -> `ctx`), and a BARE `suppress(` call only when the NAME `suppress` is
# what a `from contextlib import ...` actually BOUND.
#
# EVERY licensing decision here is a BINDING test, never a PRESENCE test.
# That distinction is the whole defect class this scanner kept re-growing
# (§11.4.250 -- the same shape returning is a signal about the primitive,
# not about the instance), so both scanners' decisions are enumerated and
# labelled rather than left to be re-derived by the next reader:
#
#   AST analyser (`suppress_bindings` / `is_suppress_call`)
#     A1 `Import` name == "contextlib"                          BINDING
#     A2 module alias recorded as `asname or "contextlib"`       BINDING
#     A3 `ImportFrom` module == "contextlib"                     BINDING
#     A4 `not node.level` (absolute, not a `.contextlib` sibling) BINDING
#     A5 imported name == "suppress" -> `asname or "suppress"`   BINDING
#     A6 imported name == "*" -> binds the real name `suppress`  BINDING
#     A7 dotted call: attr == "suppress" AND value.id in aliases BINDING
#     A8 bare call: `func.id in direct_names`                    BINDING
#     A9 `WITH_TYPES and (module_aliases or direct_names)`       presence,
#        but a pure SHORT-CIRCUIT: A7/A8 re-decide every call, so it can
#        only skip work it could never have licensed.
#
#   Text fallback (`scan_py_text_suppress`)
#     T1 `import contextlib as X` -> mod_alias[X]                BINDING
#     T2 `import contextlib` -> mod_alias["contextlib"]          BINDING
#     T3 `from contextlib import ...` -> the SET OF BOUND NAMES  BINDING
#     T4 early exit when both sets are empty                     presence,
#        but a pure SHORT-CIRCUIT, exactly as A9.
#     T5 dotted call: `prefix in mod_alias`                      BINDING
#     T6 bare call: `"suppress" in from_names`                   BINDING
#
# Each binding test is load-bearing in the SAME direction -- refusing
# healthy code (§11.4.201(1)) -- and each was measured, not assumed.
# Without the from/module split (T3 vs T1/T2), a module-only import
# licenses the BARE form and refuses a project-local `suppress()` helper
# that merely shares a file with an unrelated `import contextlib`. Without
# the PREFIX-NAME check (T5), "this file imports contextlib somewhere"
# licenses EVERY dotted `<anything>.suppress(` in it. Without the BOUND-NAME
# check (T3/T6), "this file does a from-import" licenses every bare
# `suppress(`, so a project-local helper beside `from contextlib import
# ExitStack`, or beside `from contextlib import suppress as quiet` (which
# binds `quiet`, NOT `suppress`), is refused. Each is a FAIL-bluff in
# exactly the mode that already reports a FLOOR, and a DIVERGENCE from the
# AST analyser, which resolves the same bindings structurally. Matching the
# bound NAME on BOTH branches keeps the two modes aligned.
scan_py_text_suppress() { # $1=file -> echoes one "lineno" per broad suppress
    local f="$1"
    awk '
        # Removes a trailing `#` line comment, cutting ONLY at a `#` that the
        # quote state of THIS line puts OUTSIDE every string literal. Quote
        # state is tracked character-by-character with backslash escapes
        # honoured, so `lock.hold("a\"#b")` does not lose its tail, and a
        # TRIPLE quote is tracked as ONE three-character delimiter. This
        # closes the COMMENT-CARRIER over-report (`with
        # suppress(FileNotFoundError):  # was suppress(Exception)`), measured
        # ast=0/text=1 before this strip.
        #
        # NOTE ON NOTATION: this awk program lives inside a single-quoted
        # shell string, so no apostrophe may appear anywhere below -- not even
        # in prose or in an example (§11.4.201(7)(c), the quoting path is part
        # of the instrument; writing one here is a PARSE ERROR, measured).
        # The single-quoted triple delimiter is therefore written as SQ3 and
        # the double-quoted one as DQ3.
        #
        # WHY THE TRIPLE-DELIMITER CASE IS NOT AN EXTRA. Read as three
        # independent one-character toggles, DQ3 + a + DQ + # + b + DQ3 opens
        # at char 1, closes at char 2, re-opens at char 3, and closes again at
        # the quote after `a` -- so a `#` genuinely INSIDE the string reads as
        # outside it, the line is cut there, and any real violation after the
        # cut is SILENTLY DELETED. Measured on the one-char-toggle version:
        # ast=1/text=0 for the DQ3 form AND the SQ3 form, while reverting the
        # strip CALL alone restored text=1 -- that version was therefore a
        # REGRESSION against the pre-strip scanner, trading a visible
        # over-report for a silent under-report. DQ3 + a + # + b + DQ3 (no
        # interior quote) survived by odd/even luck, which is why L33 did not
        # catch it. Pinned now by L35 (DQ3) and L36 (SQ3).
        #
        # FAILURE DIRECTION, stated as MEASURED SAMPLES rather than as a
        # guarantee (§11.4.6). An UNTERMINATED quote on this line leaves `q`
        # set and the loop returns the line UNCUT, so a line whose string
        # opens here and closes later keeps all of its text. Every shape this
        # file carries a fixture for (L30, L33-L37 for the quote model, L40 and
        # L41 for the delimiter POSITION ADVANCE) now strips at the intended
        # position or not at all. Two blind spots are KNOWN
        # and NOT closed, because each needs state this function does not
        # have:
        #   * an opening quote on an EARLIER line (a multi-line string) --
        #     this function sees one line, so a `#` inside such a region reads
        #     as outside it. Cross-line state is exactly the fence counter
        #     declined in the header, and is declined here for that reason.
        #   * PEP 701 nested same-quote f-strings (3.12+), where an f-string
        #     may contain the SAME delimiter inside its own braces. The
        #     delimiters genuinely nest, which a flat quote model cannot
        #     represent.
        # Neither is claimed absent, harmless, or unreachable, and neither
        # direction is claimed for them: they are recorded as
        # UNMEASURED-BEYOND-THE-FIXTURES so the next reader inherits the
        # boundary instead of inferring a guarantee from silence. The AST
        # analyser is immune to both by construction and remains the primary.
        function strip_comment(s,   i, c, q, n, sq, t3, d3) {
            # The apostrophe is built with sprintf rather than written
            # inline, for the reason given in NOTE ON NOTATION above.
            sq = sprintf("%c", 39)
            n = length(s)
            q = ""
            t3 = 0
            for (i = 1; i <= n; i++) {
                c = substr(s, i, 1)
                if (q != "") {
                    if (c == "\\") { i++; continue }
                    if (c != q) continue
                    if (! t3) { q = ""; continue }
                    # Inside a triple-quoted string a LONE delimiter character
                    # is ordinary content; only the full three-character run
                    # closes it.
                    d3 = q q q
                    if (substr(s, i, 3) == d3) { q = ""; t3 = 0; i += 2 }
                    continue
                }
                if (c == "\"" || c == sq) {
                    d3 = c c c
                    if (substr(s, i, 3) == d3) { q = c; t3 = 1; i += 2 }
                    else q = c
                    continue
                }
                if (c == "#") return substr(s, 1, i - 1)
            }
            return s
        }
        # Returns THIS call argument list: the text from position `i` (just
        # past the opening paren) up to its MATCHING close paren, nesting
        # tracked. Bounding the breadth scan to the call OWN arguments is what
        # keeps a SIBLING call on the same line from lending it an `Exception`
        # token it never received. An unterminated list (a multi-line call)
        # returns what this line holds -- the documented MULTI-LINE
        # UNDER-gap, unchanged by this bound.
        #
        # BLINDNESS, stated (§11.4.6): depth is counted over RAW characters, so
        # a paren inside a STRING ARGUMENT miscounts it -- `suppress(f("(("))`
        # ends the list early. Measured across every constructible divergence
        # shape, the string sits in suppress OWN argument list, which makes
        # that list statically unresolvable, so the AST analyser
        # §11.4.201(4) conservative-safe refusal fires on the same file
        # (ast=1/text=1): no mode divergence escapes and BOTH modes fail
        # CLOSED. The bound is therefore honest-but-approximate, not exact.
        function arglist(s, i,   depth, out, c) {
            depth = 1
            out = ""
            while (i <= length(s)) {
                c = substr(s, i, 1)
                if (c == "(") {
                    depth++
                } else if (c == ")") {
                    depth--
                    if (depth == 0) return out
                }
                out = out c
                i++
            }
            return out
        }
        {
            lines[NR] = $0
            # The two import kinds are tracked SEPARATELY: each licenses a
            # different call shape. Collapsing them into one flag makes a
            # module-only import license the BARE form, which false-positives
            # on a project-local suppress() living in a file that imports
            # contextlib for an unrelated reason (§11.4.201(1)).
            # Recorded as the SET OF BOUND NAMES, never as a boolean: a
            # boolean says only "this file imports contextlib somewhere",
            # which licenses every dotted `<anything>.suppress(` in the
            # file (§11.4.201(7)(a) -- presence is not a binding).
            if (match($0, /^[ \t]*import[ \t]+contextlib[ \t]+as[ \t]+[A-Za-z_][A-Za-z0-9_]*/)) {
                alias = substr($0, RSTART, RLENGTH)
                sub(/^.*[ \t]as[ \t]+/, "", alias)
                mod_alias[alias] = 1
            } else if ($0 ~ /^[ \t]*import[ \t]+contextlib([ \t]*,|[ \t]*(#.*)?$)/) {
                mod_alias["contextlib"] = 1
            }
            # The from-import is likewise recorded as the SET OF NAMES IT
            # BINDS, never as a "did this file do a from-import?" boolean.
            # A boolean licenses the BARE `suppress(` call on ANY
            # `from contextlib import <anything>`, so a project-local
            # suppress() beside `from contextlib import ExitStack` -- or
            # beside `from contextlib import suppress as quiet`, which binds
            # `quiet` and NOT `suppress` -- is refused: a §11.4.201(1)
            # FAIL-bluff and a DIVERGENCE from the AST analyser, which
            # resolves `a.asname or a.name` per imported name. Only an
            # UNALIASED `suppress`, or a star-import (which binds the real
            # name), binds `suppress`.
            if (match($0, /^[ \t]*from[ \t]+contextlib[ \t]+import[ \t]/)) {
                spec = substr($0, RSTART + RLENGTH)
                sub(/#.*$/, "", spec)
                gsub(/[()]/, " ", spec)
                n_item = split(spec, item_list, ",")
                for (q = 1; q <= n_item; q++) {
                    s = item_list[q]
                    sub(/^[ \t]+/, "", s)
                    sub(/[ \t]+$/, "", s)
                    if (s == "") continue
                    if (s == "*") { from_names["suppress"] = 1; continue }
                    orig = s
                    bound = s
                    if (match(s, /[ \t]+as[ \t]+/)) {
                        orig = substr(s, 1, RSTART - 1)
                        bound = substr(s, RSTART + RLENGTH)
                        gsub(/[ \t]/, "", orig)
                        gsub(/[ \t]/, "", bound)
                    }
                    if (orig == "suppress" && bound ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
                        from_names[bound] = 1
                    }
                }
            }
        }
        END {
            n_mod = 0
            for (k in mod_alias) n_mod++
            n_from = 0
            for (k in from_names) n_from++
            # Pure short-circuit: with NO contextlib binding of either kind
            # no call below could be licensed anyway. It skips work, it never
            # licenses any.
            if (n_mod == 0 && n_from == 0) exit 0
            for (i = 1; i <= NR; i++) {
                # Comment-stripped BEFORE the shape test and before any token
                # scan, so a `#`-commented mention of the anti-pattern on an
                # otherwise-healthy `with` line cannot license a hit OUTSIDE
                # the two blind spots the strip_comment note above enumerates.
                # INSIDE blind spot (b) it still can, measured rather than
                # assumed: an f-string whose replacement field holds an
                # SQ3-delimited literal containing a DQ (a PEP 701 nested
                # same-quote form, 3.12+) followed on the SAME line by a `#`
                # comment mentioning the broad form measures ast=0 (PASS) /
                # text=1 (FAIL) on a 3.14.6 interpreter -- the flat quote
                # model cannot represent that nesting, so the strip leaves
                # the comment in place and the commented mention IS matched.
                # ONE MEASURED SAMPLE with its instrument named, never a
                # completeness claim in either direction (§11.4.6); the
                # blind-spot note above stands unchanged.
                line = strip_comment(lines[i])
                if (line !~ /^[ \t]*(async[ \t]+)?with[ \t]/) continue
                # EVERY `suppress(` token on the line is examined IN TURN. A
                # token that is only the tail of a longer identifier, or one
                # this file imports do not license, must not STOP the scan --
                # the NEXT occurrence on the same line may still be a real
                # contextlib.suppress call, and a single-shot `match()` would
                # silently lose it.
                scan_pos = 1
                while (match(substr(line, scan_pos), /suppress[ \t]*\(/)) {
                    tok_start = scan_pos + RSTART - 1
                    tok_len = RLENGTH
                    scan_pos = tok_start + tok_len
                    before = substr(line, 1, tok_start - 1)
                    # I6 -- WHOLE-IDENTIFIER match, never a substring. A local
                    # callable whose name merely ENDS in "suppress"
                    # (`try_suppress(`) is NOT the name `suppress`; the AST
                    # analyser resolves `func.id` as a whole name and passes
                    # such a file, so matching the tail here REFUSES
                    # provably-healthy code -- a §11.4.201(1) FAIL-bluff and a
                    # mode DIVERGENCE. Measured before this guard: ast=0/text=1.
                    if (before ~ /[A-Za-z0-9_]$/) continue
                    # Dotted call (`contextlib.suppress(`) needs a MODULE import;
                    # a bare call (`suppress(`) needs a FROM import.
                    dotted = 0
                    prefix = ""
                    if (match(before, /[A-Za-z_][A-Za-z0-9_]*[ \t]*\.[ \t]*$/)) {
                        dotted = 1
                        pfx_start = RSTART
                        prefix = substr(before, RSTART, RLENGTH)
                        sub(/[ \t]*\.[ \t]*$/, "", prefix)
                        # I7 -- the AST requires the dotted prefix to be a
                        # SIMPLE `Name` node, so `pkg.contextlib.suppress(` is
                        # NOT a contextlib call (its `func.value` is an
                        # Attribute). The extractor takes only the LAST dotted
                        # component, so without this check a plain
                        # `import contextlib` licensed every
                        # `<anything>.contextlib.suppress(` on the line.
                        # Measured before this guard: ast=0/text=1.
                        if (pfx_start > 1 &&
                            substr(before, pfx_start - 1, 1) ~ /[A-Za-z0-9_.]/) continue
                    }
                    if (dotted && !(prefix in mod_alias)) continue
                    # BINDING, not presence: the only bare call token this
                    # scanner matches is the literal name `suppress`, so the call
                    # is licensed only when THAT name is what the from-import
                    # bound (mirrors the AST `func.id in direct_names` test).
                    if (!dotted && !("suppress" in from_names)) continue
                    # I8 -- the breadth token is read from THIS call OWN
                    # argument list, never from the remainder of the line: a
                    # SIBLING call argument (`suppress(ValueError),
                    # othermod.wrap(Exception)`) or a same-line body
                    # (`suppress(ValueError): log("Exception ...")`) is not
                    # this call exception class, and reading it as one
                    # refuses healthy code. Measured before this bound:
                    # ast=0/text=1 for both shapes.
                    args = arglist(line, tok_start + tok_len)
                    # Word-boundary match: MyException must NOT count as Exception.
                    if (args ~ /(^|[^A-Za-z0-9_])(Base)?Exception([^A-Za-z0-9_]|$)/) {
                        print i
                        break
                    }
                }
            }
        }
    ' "$f" 2>/dev/null || true
}

# ── (A) Python: STRUCTURAL analysis via the stdlib ast module ───────────────
# The analyser receives the file list NUL-separated on stdin and reports hits
# by ARRAY INDEX, never by path, so a path containing a tab or newline can
# never corrupt the protocol.
py_files=()
for f in "${files[@]}"; do
    case "$f" in *.py) py_files+=("$f") ;; esac
done

py_text_fallback_files=()

if [ "${#py_files[@]}" -gt 0 ]; then
    if [ -n "$py_bin" ]; then
        ast_out="$(printf '%s\0' "${py_files[@]}" | "$py_bin" -c '
import ast, sys

# Shape (A) is decided from the PARSE TREE. A comment is not a statement and
# a string literal is not a Try node, so trailing comments, tuple clauses,
# comments inside the body, and documentation carriers are all handled by
# construction rather than by an accumulating stack of regex epicycles.

TRY_TYPES = tuple(
    t for t in (getattr(ast, "Try", None), getattr(ast, "TryStar", None))
    if t is not None
)

# Shape (C) lives on a DIFFERENT node type. `contextlib.suppress` is a With
# (or AsyncWith) node, never a Try node, so a Try-only visitor is
# structurally blind to it no matter how the handler is written.
WITH_TYPES = tuple(
    t for t in (getattr(ast, "With", None), getattr(ast, "AsyncWith", None))
    if t is not None
)

# The two classes that swallow EVERYTHING. A narrower class is a declared,
# bounded tolerance and is not a fail-open defect.
BROAD_EXC = ("Exception", "BaseException")


def is_docstring(stmt):
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def is_trivial_literal(value):
    """True for a value that carries ZERO information about the failure.

    A populated container or any computed expression is deliberately NOT
    trivial: it is doing work, which is fallback handling rather than a
    silent default (§11.4.6 — flag only the decidable shape).
    """
    if value is None:                       # bare `return`
        return True
    if isinstance(value, ast.Constant):     # None / True / False / 0 / "" ...
        return True
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)) and not value.elts:
        return True
    if isinstance(value, ast.Dict) and not value.keys:
        return True
    return False


def classify(handler):
    body = [s for s in handler.body if not is_docstring(s)]
    # Two or more statements means the handler is doing something; whether
    # that something is adequate is a review judgement, not a structural fact.
    if len(body) != 1:
        return None
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return "swallow"
    if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis):
        return "swallow"
    if isinstance(stmt, ast.Return) and is_trivial_literal(stmt.value):
        return "default"
    return None


def suppress_bindings(tree):
    """Resolve which NAMES in this module actually refer to contextlib.suppress.

    Returns (module_aliases, direct_names). Matching the bare name `suppress`
    unconditionally would fire on a project-local helper of the same name --
    a §11.4.201(1) false-positive refusal -- so the binding is resolved from
    the imports THIS file declares (§11.4.201(7)(a): match structure).
    """
    module_aliases = set()
    direct_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "contextlib":
                    module_aliases.add(a.asname or "contextlib")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "contextlib" and not node.level:
                for a in node.names:
                    if a.name == "suppress":
                        direct_names.add(a.asname or "suppress")
                    elif a.name == "*":
                        direct_names.add("suppress")
    return module_aliases, direct_names


def is_suppress_call(call, module_aliases, direct_names):
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "suppress":
        return (isinstance(func.value, ast.Name)
                and func.value.id in module_aliases)
    if isinstance(func, ast.Name):
        return func.id in direct_names
    return False


def classify_suppress(call):
    """None (not a violation) | "broad" | "unresolved".

    `suppress()` with no arguments suppresses NOTHING and is not a violation.
    A purely narrow argument list is a bounded, declared tolerance.
    """
    unresolved = bool(call.keywords)
    for arg in call.args:
        if isinstance(arg, ast.Name):
            name = arg.id
        elif isinstance(arg, ast.Attribute):
            name = arg.attr
        else:
            unresolved = True
            continue
        if name in BROAD_EXC:
            return "broad"
    return "unresolved" if unresolved else None


data = sys.stdin.buffer.read().split(b"\0")
paths = [p for p in data if p]
for idx, raw in enumerate(paths):
    path = raw.decode("utf-8", "surrogateescape")
    try:
        with open(path, "rb") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (SyntaxError, ValueError, OSError, UnicodeDecodeError) as exc:
        # Never a silent skip: hand the file back for the text fallback and
        # report why the structural read failed (§11.4.201(6)).
        reason = type(exc).__name__
        sys.stdout.write("UNPARSED\t%d\t%s\n" % (idx, reason))
        continue
    module_aliases, direct_names = suppress_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, TRY_TYPES):
            for handler in getattr(node, "handlers", []):
                kind = classify(handler)
                if kind:
                    sys.stdout.write(
                        "HIT\t%s\t%d\t%d\n" % (kind, idx, handler.lineno))
            continue
        if isinstance(node, WITH_TYPES) and (module_aliases or direct_names):
            for item in node.items:
                call = item.context_expr
                if not isinstance(call, ast.Call):
                    continue
                if not is_suppress_call(call, module_aliases, direct_names):
                    continue
                kind = classify_suppress(call)
                if kind == "broad":
                    sys.stdout.write(
                        "HIT\tsuppress\t%d\t%d\n" % (idx, call.lineno))
                elif kind == "unresolved":
                    sys.stdout.write(
                        "HIT\tsuppress_unresolved\t%d\t%d\n"
                        % (idx, call.lineno))
' 2>/dev/null)"
        ast_rc=$?
        if [ "$ast_rc" -ne 0 ]; then
            # The analyser itself failed. Do NOT report a clean number from a
            # broken instrument (§11.4.201(6)); degrade loudly to text.
            echo "⚠ ${GATE}: NOTE — the Python AST analyser exited ${ast_rc}; falling back to the TEXT scanner for all Python files. Python results below are ${TEXT_MODE_CAVEAT}."
            py_text_fallback_files=("${py_files[@]}")
        else
            while IFS=$'\t' read -r tag a b c; do
                case "$tag" in
                    HIT)
                        f="${py_files[$b]}"
                        if [ "$a" = "default" ]; then
                            echo "❌ ${GATE}: FAIL — silent default return (exception handler returns a trivial literal with no re-raise/log) at ${f}:${c} (§${ANCHOR})"
                        elif [ "$a" = "suppress" ]; then
                            echo "❌ ${GATE}: FAIL — swallowed exception (contextlib.suppress over a broad exception class - swallows everything with no re-raise/log) at ${f}:${c} (§${ANCHOR})"
                        elif [ "$a" = "suppress_unresolved" ]; then
                            echo "❌ ${GATE}: FAIL — swallowed exception (contextlib.suppress whose exception list could not be resolved statically - conservative-safe refusal per §11.4.201(4)) at ${f}:${c} (§${ANCHOR})"
                        else
                            echo "❌ ${GATE}: FAIL — swallowed exception (handler body is only 'pass' with no re-raise/log) at ${f}:${c} (§${ANCHOR})"
                        fi
                        hits=$(( hits + 1 ))
                        ;;
                    UNPARSED)
                        f="${py_files[$a]}"
                        echo "⚠ ${GATE}: NOTE — ${f} could not be parsed as Python 3 (${b}); analysed by the TEXT fallback, whose result for this file is ${TEXT_MODE_CAVEAT}."
                        py_text_fallback_files+=("$f")
                        ;;
                esac
            done <<< "$ast_out"
        fi
    else
        if [ -n "${DANGEROUS_COMBO_PYTHON:-}" ]; then
            # The explicit pin was honoured and NOT silently overridden, so
            # python3/python were deliberately never tried. Saying otherwise
            # would misreport what the instrument actually did (§11.4.6).
            echo "⚠ ${GATE}: NOTE — no usable Python 3 (the explicit DANGEROUS_COMBO_PYTHON pin did not resolve; python3/python were deliberately NOT tried); Python files analysed by the TEXT scanner, whose results are ${TEXT_MODE_CAVEAT}."
        else
            echo "⚠ ${GATE}: NOTE — no Python 3 interpreter found (tried python3, python); Python files analysed by the TEXT scanner, whose results are ${TEXT_MODE_CAVEAT}. Set DANGEROUS_COMBO_PYTHON to enable structural analysis."
        fi
        py_text_fallback_files=("${py_files[@]}")
    fi
fi

# Text fallback for any Python file the parser could not cover.
if [ "${#py_text_fallback_files[@]}" -gt 0 ]; then
    for f in "${py_text_fallback_files[@]}"; do
        while IFS= read -r lineno; do
            [ -n "$lineno" ] || continue
            hits=$(( hits + 1 ))
            echo "❌ ${GATE}: FAIL — swallowed exception (Python fail-open handler, text scan) at ${f}:${lineno} (§${ANCHOR})"
        done < <(scan_py_text "$f")
        while IFS= read -r lineno; do
            [ -n "$lineno" ] || continue
            hits=$(( hits + 1 ))
            echo "❌ ${GATE}: FAIL — swallowed exception (contextlib.suppress over a broad exception class, text scan) at ${f}:${lineno} (§${ANCHOR})"
        done < <(scan_py_text_suppress "$f")
    done
fi

for f in "${files[@]}"; do
    # ── (A) C-family/JS/TS/Java/C#/PHP: catch (...) { <empty-or-comment-only> }
    # Comment-stripped-then-collapsed single-line window search (bounded to
    # avoid multi-KB false spans): scan a joined 1-3-line window starting at
    # each `catch (...) {` for an immediate `}` with nothing but whitespace/
    # a single-line comment between.
    catch_hits="$(grep -nE 'catch[[:space:]]*\([^)]*\)[[:space:]]*\{' "$f" 2>/dev/null || true)"
    if [ -n "$catch_hits" ]; then
        while IFS= read -r hit; do
            [ -n "$hit" ] || continue
            lineno="${hit%%:*}"
            window="$(sed -n "${lineno},$((lineno + 3))p" "$f" 2>/dev/null || true)"
            # strip the catch-opener prefix up to its opening brace, and
            # strip //-line-comments, then check if only whitespace/}
            body="$(printf '%s' "$window" | sed -E '1s/^.*catch[[:space:]]*\([^)]*\)[[:space:]]*\{//' | sed -E 's#//.*$##')"
            body_nows="$(printf '%s' "$body" | tr -d '[:space:]')"
            # empty (or comment-only, already stripped) body up to its FIRST
            # closing brace = swallow. Only match when the first non-ws char
            # sequence in body_nows is exactly "}" (immediate close).
            first_char="${body_nows:0:1}"
            if [ "$first_char" = "}" ]; then
                hits=$(( hits + 1 ))
                echo "❌ ${GATE}: FAIL — swallowed exception (empty/comment-only catch block) at ${f}:${lineno} (§${ANCHOR})"
            fi
        done <<< "$catch_hits"
    fi

    # ── (B) Credential silently defaulted to a literal string ──────────────
    cred_hits="$(grep -nEi '(credential|secret|token|api[_-]?key|password|passwd)[A-Za-z0-9_]*[[:space:]]*=[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*[[:space:]]*(\|\||or)[[:space:]]*["'"'"'][^"'"'"']*["'"'"']' "$f" 2>/dev/null || true)"
    if [ -n "$cred_hits" ]; then
        while IFS= read -r hit; do
            [ -n "$hit" ] || continue
            lineno="${hit%%:*}"
            text="${hit#*:}"
            hits=$(( hits + 1 ))
            echo "❌ ${GATE}: FAIL — credential silently defaulted to a literal value at ${f}:${lineno}: ${text# } (§${ANCHOR})"
        done <<< "$cred_hits"
    fi
done

echo "======================================================================"
if [ "$hits" -gt 0 ]; then
    echo "❌ ${GATE}: FAIL — ${hits} fail-open anti-pattern hit(s) found (§${ANCHOR})"
    exit 1
fi

echo "✅ ${GATE}: PASS — no swallowed-exception, silent-default-return or credential-default-to-literal anti-patterns found (§${ANCHOR})"
exit 0
