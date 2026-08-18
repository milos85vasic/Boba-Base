# BOB-115 Evidence — RED→GREEN Regression-Guard + §1.1 Mutation Transcript

**Revision:** 1
**Last modified:** 2026-08-18T19:37:41Z
**Item:** BOB-115 — Fix workable-items validate over-scoping to Updated-events (BOB-010 id=64 pattern)
**Constitution:** §11.4.5 / §11.4.69 / §11.4.115 / §11.4.226 (closure-evidence-at-closure + RED→GREEN + §1.1 mutation)

Full `go test` transcript: RED on the unfixed source, GREEN on the fixed source, RED again under the §1.1 paired mutation (event_type clause stripped), GREEN again after restoring the fix, and the full package suite confirming no other regression (one pre-existing, unrelated `TestDiffCmd_NoPathsSkipsMarkdownComparison` failure verified to fail identically on the unfixed source too).

```text
Task #54 — workable-items validate over-scoping to Updated-events (BOB-010 id=64)
------------------------------------------------------------------------------------
Root cause: unresolvableClosureEvidence() (constitution/scripts/workable-items/cmd/
workable-items/sync.go) scoped its evidence-path-resolvability check to
"item's CURRENT status is terminal" but never to "the item_history ROW is
itself a closure event". BOB-010's real closure (history id=4, event=Completed)
recorded a resolvable evidence_path; a LATER Updated event (history id=64,
on=2026-08-10) recorded evidence_path="scripts/docs_chain.sh" — the file's
pre-rename name (git-mv'd to scripts/workable-items-export.sh by commits
0558399/d9d512d). The validator flagged the Updated row as an unresolvable
CLOSURE claim, which it is not (§11.4.5/§11.4.69/§11.4.123/§11.4.226 bind the
closure event's pointer, never every subsequent note on an already-closed
item).

Fix: added `AND h.event_type IN ('Fixed', 'Implemented', 'Completed',
'Obsolete')` to the query — the SAME closed set correct_evidence.go's
closureEvents / assign.go's hasClosureEvidence already recognise (§11.4.6:
reused, not re-derived).

------------------------------------------------------------------------------
STEP 1 — RED: new regression test FAILS on the UNFIXED source
------------------------------------------------------------------------------
$ go test -run TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation -v ./cmd/workable-items/
=== RUN   TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation
add: created WIT-707 (Bug, status=Queued) in Issues
close: moved WIT-707 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No3787987596/003/closure-artefact.log)
    validate_evidence_test.go:327: guard flagged 1 violation(s) for an Updated-event evidence_path on a closed item (§11.4.201(1) over-scoping — Updated is not a closure event): [WIT-707: closure evidence_path does not resolve (well-formed path, but nothing exists there) — history id=3, event=Updated, on=2026-08-10: "/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No3787987596/001/renamed-away-bef …" (§11.4.5/§11.4.69/§11.4.123/§11.4.226 — a closure's captured proof must be producible on demand)]
--- FAIL: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation (0.01s)
FAIL
FAIL	github.com/HelixDevelopment/HelixConstitution/scripts/workable-items/cmd/workable-items	0.010s
FAIL
exit=1

------------------------------------------------------------------------------
STEP 2 — GREEN: same test PASSES on the FIXED source
------------------------------------------------------------------------------
$ go test -run TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation -v ./cmd/workable-items/
=== RUN   TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation
add: created WIT-707 (Bug, status=Queued) in Issues
close: moved WIT-707 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No3526214413/003/closure-artefact.log)
validate: OK — 1 items, all invariants satisfied
--- PASS: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation (0.01s)
PASS
ok  	github.com/HelixDevelopment/HelixConstitution/scripts/workable-items/cmd/workable-items	(cached)
exit=0

------------------------------------------------------------------------------
STEP 3 — §1.1 PAIRED MUTATION: strip the event_type clause -> test FAILs again
------------------------------------------------------------------------------
$ (mutation: removed 'AND h.event_type IN (...)' clause)
=== RUN   TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation
add: created WIT-707 (Bug, status=Queued) in Issues
close: moved WIT-707 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No2290695618/003/closure-artefact.log)
    validate_evidence_test.go:327: guard flagged 1 violation(s) for an Updated-event evidence_path on a closed item (§11.4.201(1) over-scoping — Updated is not a closure event): [WIT-707: closure evidence_path does not resolve (well-formed path, but nothing exists there) — history id=3, event=Updated, on=2026-08-10: "/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No2290695618/001/renamed-away-bef …" (§11.4.5/§11.4.69/§11.4.123/§11.4.226 — a closure's captured proof must be producible on demand)]
--- FAIL: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation (0.01s)
FAIL
FAIL	github.com/HelixDevelopment/HelixConstitution/scripts/workable-items/cmd/workable-items	0.009s
FAIL
exit=1

------------------------------------------------------------------------------
STEP 4 — restore fix, re-confirm GREEN + full package suite (only pre-existing
unrelated TestDiffCmd_NoPathsSkipsMarkdownComparison failure remains, verified
independently to fail identically on the STASHED pre-fix source too)
------------------------------------------------------------------------------
=== RUN   TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation
add: created WIT-707 (Bug, status=Queued) in Issues
close: moved WIT-707 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No3526214413/003/closure-artefact.log)
validate: OK — 1 items, all invariants satisfied
--- PASS: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation (0.01s)
PASS
ok  	github.com/HelixDevelopment/HelixConstitution/scripts/workable-items/cmd/workable-items	(cached)
exit=0
group add: created g-low-pri-high-sev (destination=main priority=5 state=open)
group add: created g-low-pri-low-sev (destination=main priority=5 state=open)
group add: created g-high-pri (destination=main priority=1 state=open)
group add: created g-no-open-members (destination=main priority=0 state=open)
group add: created g-complete-state (destination=main priority=0 state=open)
group add: created g-other-dest (destination=feature:x priority=0 state=open)
group state: g-complete-state open -> group-complete
group add: created g-a (destination=main priority=3 state=open)
group add: created g-b (destination=main priority=3 state=open)
group add: created g-c (destination=main priority=1 state=open)
group add: created grp-solo (destination=main priority=1 state=open)
NEXT-GROUP: grp-solo -> track track-1 (destination=main priority=1)
group add: created grp-high (destination=main priority=1 state=open)
group add: created grp-low (destination=main priority=2 state=open)
NEXT-GROUP: grp-low -> track track-1 (destination=main priority=2)
group add: created grp-empty (destination=main priority=1 state=open)
NEXT-GROUP: no candidate group available for track track-1 (destinations=main) right now
group add: created grp-a (destination=main priority=1 state=open)
assign next-group: claim-script invocation failed for grp-a: fork/exec /tmp/.private/milosvasic/TestAssignNextGroupCmd_ClaimScriptMissingIsHardError3395885502/002/does-not-exist.sh: no such file or directory
group add: created grp-a (destination=main priority=1 state=open)
assign next-group: --db is required
assign next-group: --track is required
assign next-group: --destinations is required (comma-separated, non-empty — design §3.3)
assign next-group: --claim-script is required (§11.4.176-A exactly-once claim CLI path)
group add: created grp-target (destination=main priority=1 state=open)
group add: created grp-other (destination=main priority=1 state=open)
NEXT-ITEM: no open item in group grp-other for track t1 right now
group add: created grp-order (destination=main priority=1 state=open)
group add: created grp-exclude (destination=main priority=1 state=open)
group add: created grp-none-open (destination=main priority=1 state=open)
NEXT-ITEM: no open item in group grp-none-open for track t1 right now
assign next-item: group no-such-group not found
assign next-item: --db is required
assign next-item: --track is required
assign next-item: --group is required (the track's already-claimed group_id)
group add: created grp-open-member (destination=main priority=1 state=open)
group add: created grp-no-evidence (destination=main priority=1 state=open)
group add: created grp-e2e-complete (destination=main priority=1 state=open)
add: created WIT-700 (Task, status=Queued) in Issues
group set: classified WIT-700 -> group=grp-e2e-complete destination=main
close: moved WIT-700 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=qa-results/assign-p3/wit-700-evidence.log)
assign group-complete: grp-e2e-complete -> group-complete (1 member(s) all terminal-with-evidence)
group add: created grp-zero-members (destination=main priority=1 state=open)
assign group-complete: group grp-zero-members has zero classified members — nothing to complete (classify at least one item first)
assign group-complete: group no-such-group not found
Issues.md: 2 items, 3 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_WriterEmitsHeadingOnOwnLine3707505730/001/wi.db
wrote /tmp/.private/milosvasic/TestATM627_WriterEmitsHeadingOnOwnLine3707505730/001/out.md (342 bytes)
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_IntegrityGuard_DetectsLocationMismatch393385197/001/wi.db
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_IntegrityGuard_ValidateFailsAndNamesInvariant291586097/001/wi.db
validate: OK — 2 items, all invariants satisfied
validate: 4 violation(s):
  - ATM-900: Fixed-location item has NON-terminal status "Queued" — a Fixed-location item must carry a terminal `… (→ Fixed.md)` status; a non-terminal item belongs in Issues (§11.4.15/ATM-627 INTEG-03) [section]
  - Issues: DB not renderable by db-to-md (§11.4.93): segment references unknown item "ATM-900" [section]
  - dangling item-segment (document=Issues, seq=1, atm_id=ATM-900, rep=section): no item at current_location=Issues (§11.4.135/ATM-627)
  - missing item-segment (atm_id=ATM-900, rep=section): item at current_location=Fixed has NO doc_segments row — db-to-md would silently drop it (§11.4.93/ATM-627)
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_ValidateCatchesUnrenderableDB3478124165/001/wi.db
validate: 2 violation(s):
  - Issues: DB not renderable by db-to-md (§11.4.93): segment references unknown item "ATM-900" [section]
  - dangling item-segment (document=Issues, seq=1, atm_id=ATM-900, rep=section): no item at current_location=Issues (§11.4.135/ATM-627)
sync db-to-md: render issues: segment references unknown item "ATM-900" [section]
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_ValidateCatchesLocationMismatchDB2888346831/001/wi.db
validate: 4 violation(s):
  - ATM-900: Fixed-location item has NON-terminal status "Queued" — a Fixed-location item must carry a terminal `… (→ Fixed.md)` status; a non-terminal item belongs in Issues (§11.4.15/ATM-627 INTEG-03) [section]
  - Issues: DB not renderable by db-to-md (§11.4.93): segment references unknown item "ATM-900" [section]
  - dangling item-segment (document=Issues, seq=1, atm_id=ATM-900, rep=section): no item at current_location=Issues (§11.4.135/ATM-627)
  - missing item-segment (atm_id=ATM-900, rep=section): item at current_location=Fixed has NO doc_segments row — db-to-md would silently drop it (§11.4.93/ATM-627)
sync db-to-md: render issues: segment references unknown item "ATM-900" [section]
wrote /tmp/.private/milosvasic/TestATM627_ValidateCatchesLocationMismatchDB2888346831/001/out_repaired.md (156 bytes)
Issues.md: 2 items, 3 segments
Fixed.md: 0 items, 1 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RedBaseline_DbToMdSilentlyDropsItem1125013979/001/wi.db
validate: OK — 2 items, all invariants satisfied
wrote /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RedBaseline_DbToMdSilentlyDropsItem1125013979/001/out_issues.md (164 bytes)
wrote /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RedBaseline_DbToMdSilentlyDropsItem1125013979/001/out_fixed.md (9 bytes)
Issues.md: 2 items, 3 segments
Fixed.md: 0 items, 1 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_SegmentBackfill_ValidateCatchesMissingSegments3848337921/001/wi.db
validate: OK — 2 items, all invariants satisfied
validate: 1 violation(s):
  - missing item-segment (atm_id=ATM-980, rep=section): item at current_location=Issues has NO doc_segments row — db-to-md would silently drop it (§11.4.93/ATM-627)
Issues.md: 2 items, 3 segments
Fixed.md: 0 items, 1 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RepairBackfillsAndDbToMdIncludesItem2177683368/001/wi.db
validate: OK — 2 items, all invariants satisfied
repair-bodies: scanned 2 items — applied 1 change(s): 0 rewrite, 0 populate, 2 noop, 1 backfill-segment
validate: OK — 2 items, all invariants satisfied
wrote /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RepairBackfillsAndDbToMdIncludesItem2177683368/001/out_issues.md (320 bytes)
wrote /tmp/.private/milosvasic/TestATM627_SegmentBackfill_RepairBackfillsAndDbToMdIncludesItem2177683368/001/out_fixed.md (9 bytes)
Issues.md: 2 items, 3 segments
Fixed.md: 0 items, 1 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_SegmentBackfill_Idempotent3564065864/001/wi.db
validate: OK — 2 items, all invariants satisfied
repair-bodies: scanned 2 items — applied 1 change(s): 0 rewrite, 0 populate, 2 noop, 1 backfill-segment
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_StatusDesync_ValidateCatchesColumnBodyDrift3833189795/001/wi.db
validate: OK — 2 items, all invariants satisfied
validate: 1 violation(s):
  - ATM-900 [Issues/section]: items.status="In progress" but body_md **Status:** line derives "Queued" (§11.4.93/ATM-627 column↔body desync)
validate: OK — 2 items, all invariants satisfied
Issues.md: 1 items, 2 segments
Fixed.md: 1 items, 2 segments
synced 2 total items into /tmp/.private/milosvasic/TestATM627_StatusDesync_DirectGuard3852918593/001/wi.db
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestRepairBodies_NormalizesTrailingNewline_RedPolarity2010854313/001/wi.db
validate: OK — 3 items, all invariants satisfied
wrote /tmp/.private/milosvasic/TestRepairBodies_NormalizesTrailingNewline_RedPolarity2010854313/002/rt_Issues.md (374 bytes)
wrote /tmp/.private/milosvasic/TestRepairBodies_NormalizesTrailingNewline_RedPolarity2010854313/002/rt_Fixed.md (171 bytes)
~ ATM-970 body differs (md=149 bytes db=148 bytes)
diff: 1 difference(s)
repair-bodies: scanned 3 items — applied 1 change(s): 1 rewrite, 0 populate, 2 noop, 0 backfill-segment
wrote /tmp/.private/milosvasic/TestRepairBodies_NormalizesTrailingNewline_RedPolarity2010854313/003/rt_Issues.md (374 bytes)
wrote /tmp/.private/milosvasic/TestRepairBodies_NormalizesTrailingNewline_RedPolarity2010854313/003/rt_Fixed.md (171 bytes)
diff: DB and Markdown are in sync
repair-bodies: scanned 3 items — already canonical (0 rewrite, 0 populate, 0 backfill-segment); no changes
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestUpdate_NormalizesTrailingNewline2473891338/001/wi.db
validate: OK — 3 items, all invariants satisfied
update: ATM-970 updated in Issues (status=Queued, type=Bug)
Issues.md: 2 items, 3 segments
synced 2 total items into /tmp/.private/milosvasic/TestAttribution_FixtureWithFields_RoundTripsByteIdentical2377128655/001/workable_items.db
wrote /tmp/.private/milosvasic/TestAttribution_FixtureWithFields_RoundTripsByteIdentical2377128655/001/Issues.regen.md (619 bytes)
Issues.md: 2 items, 3 segments
synced 2 total items into /tmp/.private/milosvasic/TestAttribution_LegacyFixture_RoundTripsByteIdentical1169830986/001/workable_items.db
wrote /tmp/.private/milosvasic/TestAttribution_LegacyFixture_RoundTripsByteIdentical1169830986/001/Issues.regen.md (520 bytes)
validate: OK — 2 items, all invariants satisfied
add: created WIT-700 (Bug, status=Queued) in Issues
validate: OK — 1 items, all invariants satisfied
add: created WIT-701 (Task, status=Queued) in Issues
add: created WIT-800 (Bug, status=Queued) in Issues
close: moved WIT-800 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=docs/qa/WIT-800/run.md)
add: created WIT-901 (Task, status=Queued) in Issues
add: created WIT-902 (Task, status=Queued) in Issues
add: created WIT-903 (Task, status=Queued) in Issues
Workable items by Assigned-To:
  @bob           2
  @milos85vasic  1
  ------------------
  TOTAL          3
Workable items by Created-By:
  @alice      2
  Claude      1
  ---------------
  TOTAL       3
add: created OLD-002 (Feature, status=Queued) in Issues
group add: created mistiq-vader-rebrand (destination=feature:mistiq-vader priority=7 state=open)
classify: proposed 2 unclassified item(s) -> /tmp/.private/milosvasic/TestClassifyPropose_ATM633GoldenBad_DescriptionMentionMustNotCla752276921/002/proposal.md / /tmp/.private/milosvasic/TestClassifyPropose_ATM633GoldenBad_DescriptionMentionMustNotCla752276921/002/proposal.tsv (review before a future `group set --from`)
classify: --propose is required (the only supported mode this phase implements — design §9 step 1)
classify: --db is required
classify: proposed 1 unclassified item(s) -> /tmp/.private/milosvasic/TestClassifyCmd_WritesUnderRequestedOutPrefix1562592695/002/sub/dir/myproposal.md / /tmp/.private/milosvasic/TestClassifyCmd_WritesUnderRequestedOutPrefix1562592695/002/sub/dir/myproposal.tsv (review before a future `group set --from`)
add: created WIT-810 (Bug, status=Queued) in Issues
close: evidence "/tmp/.private/milosvasic/TestCloseEvidenceRecordTime_Polarity2226858060/001/DEFINITELY_NOT_A_REAL_PATH/x.log" does not resolve (well-formed path, but nothing exists there; resolved to "/tmp/.private/milosvasic/TestCloseEvidenceRecordTime_Polarity2226858060/001/DEFINITELY_NOT_A_REAL_PATH/x.log") — a closure's captured proof must be producible on demand (§11.4.5/§11.4.69/§11.4.123/§11.4.226). Capture the artefact first, then record the closure
add: created WIT-811 (Bug, status=Queued) in Issues
close: moved WIT-811 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestCloseEvidenceRecordTime_AcceptsRealArtefact4082250881/002/EVIDENCE.md)
add: created WIT-812 (Bug, status=Queued) in Issues
close: moved WIT-812 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=docs/qa/run-1/EVIDENCE.md)
add: created WIT-820 (Bug, status=Queued) in Issues
close: moved WIT-820 Issues→Fixed (status=Obsolete (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinksobsolete-details2345619649/002/EVIDENCE.md)
obsolete-details: evidence "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log" does not resolve (well-formed path, but nothing exists there; resolved to "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log") — a closure's captured proof must be producible on demand (§11.4.5/§11.4.69/§11.4.123/§11.4.226). Capture the artefact first, then record the closure
obsolete-details: WIT-820 written (Since:2026-08-08 Reason:feature-removed Superseding:none Evidence:/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinksobsolete-details2345619649/003/EVIDENCE.md)
add: created WIT-830 (Bug, status=Queued) in Issues
subtask-add: created WIT-830-001 (parent=WIT-830, session="record-time-evidence-probe", status=Queued)
subtask-status: evidence "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log" does not resolve (well-formed path, but nothing exists there; resolved to "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log") — a closure's captured proof must be producible on demand (§11.4.5/§11.4.69/§11.4.123/§11.4.226). Capture the artefact first, then record the closure
subtask-status: WIT-830-001 Queued -> Completed (→ Fixed.md)
add: created WIT-840 (Bug, status=Queued) in Issues
move: evidence "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log" does not resolve (well-formed path, but nothing exists there; resolved to "/tmp/.private/milosvasic/TestEvidenceRecordTime_OtherSinks2165050925/001/never/captured.log") — a closure's captured proof must be producible on demand (§11.4.5/§11.4.69/§11.4.123/§11.4.226). Capture the artefact first, then record the closure
move: WIT-840 relocated Issues→Fixed (status=Fixed (→ Fixed.md), reason=record-time evidence probe)
add: created WIT-841 (Bug, status=Queued) in Issues
move: WIT-841 relocated Issues→Fixed (status=Fixed (→ Fixed.md), reason=no evidence supplied)
add: created WIT-901 (Task, status=Queued) in Issues
close: moved WIT-901 Issues→Fixed (status=Completed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestCorrectHistoryEvidence_RefusesNonExistentPath1465838590/002/SEED_EVIDENCE.md)
correct-history-evidence: evidence "/tmp/.private/milosvasic/TestCorrectHistoryEvidence_RefusesNonExistentPath1465838590/003/DEFINITELY_NOT_A_REAL_PATH/x.lo …" does not resolve (well-formed path, but nothing exists there; resolved to "/tmp/.private/milosvasic/TestCorrectHistoryEvidence_RefusesNonExistentPath1465838590/003/DEFINITELY_NOT_A_REAL_PATH/x.log") — a closure's captured proof must be producible on demand (§11.4.5/§11.4.69/§11.4.123/§11.4.226). Capture the artefact first, then record the closure
add: created WIT-901 (Task, status=Queued) in Issues
close: moved WIT-901 Issues→Fixed (status=Completed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestCorrectHistoryEvidence_GreenApplyAndAudit4138617904/002/SEED_EVIDENCE.md)
correct-history-evidence: WIT-901 history id=2 (Completed) evidence_path set to /tmp/.private/milosvasic/TestCorrectHistoryEvidence_GreenApplyAndAudit4138617904/003/CORRECTED_EVIDENCE.md (audit row appended)
add: created WIT-902 (Bug, status=Queued) in Issues
correct-history-evidence: refusing — item WIT-902 carries NON-terminal status "Queued" (§11.4.226 evidence-class-at-closure scopes this correction to CLOSED items; a non-closed item's audit trail is out of scope)
add: created WIT-001 (Bug, status=Queued) in Issues
validate: OK — 1 items, all invariants satisfied
add: created DEM-001 (Task, status=Queued) in Issues
add: created DEM-002 (Task, status=Queued) in Issues
add: created DEM-003 (Task, status=Queued) in Issues
add: --description fails §11.4.91 floor (2 words / 9 chars; need ≥6 words OR ≥40 chars)
add: created WIT-042 (Feature, status=Queued) in Issues
wrote /tmp/.private/milosvasic/TestAdd_FixedPoint1981232984/002/Issues.md (188 bytes)
Issues.md: 1 items, 1 segments
synced 1 total items into /tmp/.private/milosvasic/TestAdd_FixedPoint1981232984/002/second.db
wrote /tmp/.private/milosvasic/TestAdd_FixedPoint1981232984/002/Issues.2.md (188 bytes)
add: created WIT-100 (Bug, status=Queued) in Issues
close: --evidence is required (§11.4.5/§11.4.90 captured-evidence mandate)
close: moved WIT-100 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=docs/qa/WIT-100/transcript.md)
add: created WIT-200 (Task, status=Queued) in Issues
close: moved WIT-200 Issues→Fixed (status=Completed (→ Fixed.md), evidence=docs/qa/WIT-200/run.md)
wrote /tmp/.private/milosvasic/TestClose_RoundTripsAndValidates840175926/003/Fixed.md (249 bytes)
Fixed.md: 1 items, 1 segments
synced 1 total items into /tmp/.private/milosvasic/TestClose_RoundTripsAndValidates840175926/003/second.db
validate: OK — 1 items, all invariants satisfied
add: created WIT-777 (Bug, status=Queued) in Issues
add: created WIT-888 (Task, status=Queued) in Issues
close: moved WIT-888 Issues→Fixed (status=Implemented (→ Fixed.md), evidence=docs/qa/WIT-888/run.md)
close: item WIT-NOPE not found in Issues (nothing to close)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: recorded entry_id=1 on ATM-300-001 (PASS, tested_by=HelixQA)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: a PASS run REQUIRES --evidence (§11.4.149 — a PASS without captured evidence is a bluff)
diary add: PASS --evidence "/tmp/.private/milosvasic/TestDiaryGroupAddPassRejectsMissingEvidence1398506999/002/does_not_exist.json" does not exist as a file on disk (§11.4.149 — evidence must be real captured proof)
diary add: PASS --evidence "/tmp/.private/milosvasic/TestDiaryGroupAddPassRejectsMissingEvidence1398506999/003" does not exist as a file on disk (§11.4.149 — evidence must be real captured proof)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
diary add: recorded entry_id=2 on ATM-300-001 (SKIP, tested_by=Operator)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: --tested-by must be one of: User | Operator | AI-agent | HelixQA
diary add: --result must be one of: PASS | FAIL | SKIP
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: target ATM-999-777 not found in items (a diary entry needs an existing item / sub-task)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
diary add: recorded entry_id=2 on ATM-300-001 (PASS, tested_by=HelixQA)
Testing diary for ATM-300-001 (2 entries, oldest first):
  [1] 2026-06-10T01:00:00Z  AI-agent   FAIL
       observations:  first run failed
       action:        status unchanged
  [2] 2026-06-10T02:00:00Z  HelixQA    PASS
       observations:  second run green
       action:        status unchanged
       feature-class: audio_output
       evidence:      /tmp/.private/milosvasic/TestDiaryGroupListAndSummaryRoundTrip3846261805/002/pass.json
diary list: no diary entries for ATM-300
Testing-diary summary (total/pass/fail/skip, last verdict, last run):
  ATM-300-001       total=2 P=1 F=1 S=0  last=PASS @ 2026-06-10T02:00:00Z
Testing-diary summary (total/pass/fail/skip, last verdict, last run):
  ATM-300-001       total=2 P=1 F=1 S=0  last=PASS @ 2026-06-10T02:00:00Z
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary add: --id is required
diary list: --id is required
diary add: --db is required
diary summary: --db is required
diary add: --observations are required
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: a PASS run REQUIRES --evidence (§11.4.69 — a PASS without captured evidence is a bluff)
diary-add: recorded entry_id=1 on ATM-300-001 (PASS, tested_by=AI-agent)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: --tested-by must be one of: User | Operator | AI-agent | HelixQA
diary-add: --result must be one of: PASS | FAIL | SKIP
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
diary-add: recorded entry_id=2 on ATM-300-001 (PASS, tested_by=HelixQA)
diary-add: recorded entry_id=3 on ATM-300-001 (SKIP, tested_by=AI-agent)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
add: created ATM-300 (Bug, status=Queued) in Issues
subtask-add: created ATM-300-001 (parent=ATM-300, session="diary-session", status=Queued)
diary-add: recorded entry_id=1 on ATM-300-001 (FAIL, tested_by=AI-agent)
subtask-export: wrote /tmp/.private/milosvasic/TestSubtaskExportWritesThreeMarkdownDocs3487531936/002/issues/ATM-300/sessions/001 {Session,Diary,Summary}.md
subtask-export: --no-formats set; skipped HTML/PDF/DOCX siblings
add: created WIT-001 (Bug, status=Queued) in Issues
export: wrote /tmp/.private/milosvasic/TestExportCmd_NeverRegressesRevisionBelowCommittedFile2642827367/002/Issues.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_NeverRegressesRevisionBelowCommittedFile2642827367/002/Fixed.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_NeverRegressesRevisionBelowCommittedFile2642827367/002/Issues_Summary.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_NeverRegressesRevisionBelowCommittedFile2642827367/002/Fixed_Summary.md
export: --no-formats set; skipped HTML/PDF/DOCX sibling generation
export: wrote /tmp/.private/milosvasic/TestExportCmd_PreservesRevisionWhenContentUnchanged261882858/002/Issues.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_PreservesRevisionWhenContentUnchanged261882858/002/Fixed.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_PreservesRevisionWhenContentUnchanged261882858/002/Issues_Summary.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_PreservesRevisionWhenContentUnchanged261882858/002/Fixed_Summary.md
export: --no-formats set; skipped HTML/PDF/DOCX sibling generation
add: created WIT-001 (Bug, status=Queued) in Issues
add: created WIT-002 (Feature, status=Queued) in Issues
add: created WIT-003 (Task, status=Queued) in Issues
close: moved WIT-003 Issues→Fixed (status=Completed (→ Fixed.md), evidence=qa-results/2026-05-31/wit-003.log)
export: wrote /tmp/.private/milosvasic/TestExportCmd_EmitsDocsAndSummaries4173001091/003/Issues.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_EmitsDocsAndSummaries4173001091/003/Fixed.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_EmitsDocsAndSummaries4173001091/003/Issues_Summary.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_EmitsDocsAndSummaries4173001091/003/Fixed_Summary.md
export: --no-formats set; skipped HTML/PDF/DOCX sibling generation
add: created WIT-001 (Task, status=Queued) in Issues
close: moved WIT-001 Issues→Fixed (status=Completed (→ Fixed.md), evidence=qa-results/2026-07-10/wit-001.log)
export: wrote /tmp/.private/milosvasic/TestFixedSummary_ColumnAlignedHeader2229146738/003/Issues.md
export: wrote /tmp/.private/milosvasic/TestFixedSummary_ColumnAlignedHeader2229146738/003/Fixed.md
export: wrote /tmp/.private/milosvasic/TestFixedSummary_ColumnAlignedHeader2229146738/003/Issues_Summary.md
export: wrote /tmp/.private/milosvasic/TestFixedSummary_ColumnAlignedHeader2229146738/003/Fixed_Summary.md
export: --no-formats set; skipped HTML/PDF/DOCX sibling generation
Fixed.md: 3 items, 4 segments
synced 3 total items into /tmp/.private/milosvasic/TestUpdateDescription_TableRepresentation_RoundTripsCleanly3576401497/001/wi.db
update: FIX-2026-05-19#1 updated in Fixed (status=Implemented (→ Fixed.md), type=Feature)
wrote /tmp/.private/milosvasic/TestUpdateDescription_TableRepresentation_RoundTripsCleanly3576401497/001/out_Fixed.md (392 bytes)
diff: DB and Markdown are in sync
Fixed.md: 3 items, 4 segments
synced 3 total items into /tmp/.private/milosvasic/TestUpdateDescription_TableRepresentation_RenderItemBodyCorrupts3262793920/001/wi.db
wrote /tmp/.private/milosvasic/TestUpdateDescription_TableRepresentation_RenderItemBodyCorrupts3262793920/001/out_Fixed_red.md (472 bytes)
Fixed.md: 2 items, 4 segments
synced 2 total items into /tmp/.private/milosvasic/TestObsoleteDetails_DualRepresentation_NoSiblingClobber3434216016/001/wi.db
obsolete-details: HXC-044 written (Since:2026-07-12 Reason:not-reproducible Superseding:none Evidence:docs/qa/HXC-044/f_dbtool_evidence.md)
wrote /tmp/.private/milosvasic/TestObsoleteDetails_DualRepresentation_NoSiblingClobber3434216016/003/Fixed.regen.md (744 bytes)
Fixed.md: 2 items, 4 segments
synced 2 total items into /tmp/.private/milosvasic/TestUpdate_DualRepresentation_NoSiblingClobber3917771681/001/wi.db
update: HXC-044 updated in Fixed (status=Obsolete (→ Fixed.md), type=Bug)
Fixed.md: 2 items, 4 segments
synced 2 total items into /tmp/.private/milosvasic/TestRepresentationScopeIsLoadBearing824286166/001/wi.db
group add: created grp-a (destination=main priority=3 state=open)
group add: created grp-feature (destination=feature:mistiq-vader priority=7 state=open)
group add: <group_id> "Grp_With_Bad_Chars" must be lowercase snake/kebab (§11.4.29): letters a-z, digits, hyphens only
group add: <destination> "not-a-valid-destination" must be 'main' or 'feature:<slug>' (design §3.1)
group add: <priority> "not-an-int" must be an integer
group add: --state must be one of: open | in-progress | group-complete
group add: created grp-dup (destination=main priority=1 state=open)
group add: group grp-dup already exists
group add: created video-bugs (destination=main priority=2 state=open)
group add: created urgent-main (destination=main priority=0 state=open)
group add: created zzz-same-priority (destination=main priority=2 state=open)
group add: created mistiq-vader-rebrand (destination=feature:mistiq-vader priority=7 state=open)
urgent-main                   dest=main                  priority=0     state=open            priority ordering fixture group urgent-main
video-bugs                    dest=main                  priority=2     state=open            priority ordering fixture group video-bugs
zzz-same-priority             dest=main                  priority=2     state=open            priority ordering fixture group zzz-same-priority
mistiq-vader-rebrand          dest=feature:mistiq-vader  priority=7     state=open            priority ordering fixture group mistiq-vader-rebrand
group add: created a-main (destination=main priority=1 state=open)
group add: created b-feature (destination=feature:x priority=2 state=open)
group list: no groups match
group add: created grp-edit (destination=main priority=5 state=open)
group set: grp-edit updated (destination=feature:new-dest priority=9)
group set: group nonexistent-group not found
group add: created grp-noop (destination=main priority=1 state=open)
group set: at least one mutable field flag is required (--title/--destination/--priority/--scope-note/--roadmap-ref)
group add: created grp-bad-edit-dest (destination=main priority=1 state=open)
group set: --destination "not-valid" must be 'main' or 'feature:<slug>'
group add: created mistiq-vader-rebrand (destination=feature:mistiq-vader priority=7 state=open)
add: created WIT-500 (Task, status=Queued) in Issues
group set: classified WIT-500 -> group=mistiq-vader-rebrand destination=feature:mistiq-vader
validate-groups: OK — 1 items, 1 groups, all design §3.1 invariants satisfied
add: created WIT-501 (Bug, status=Queued) in Issues
group set: group nonexistent-group not found (referential integrity — classify into an existing group only)
group add: created grp-for-unknown-item (destination=main priority=1 state=open)
group set: item WIT-999 not found in Issues
group add: created grp-conflict (destination=main priority=1 state=open)
group set: --item (Mode B: item classification) does not take a positional <group_id> — use --group instead
group add: created grp-lifecycle (destination=main priority=1 state=open)
group state: grp-lifecycle open -> in-progress
group state: grp-lifecycle in-progress -> group-complete
group add: created grp-bad-transition (destination=main priority=1 state=open)
group state: <new_state> must be one of: open | in-progress | group-complete
group state: group no-such-group not found
add: created WIT-500 (Bug, status=Queued) in Issues
close: moved WIT-500 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_RelocatesFixedToIssuesWithStatus1098005807/002/close.md)
move: WIT-500 relocated Fixed→Issues (status=Ready for testing, reason=fix landed and wired; only the runtime GREEN is owed (§11.4.69 artifact_not_yet_built))
add: created WIT-501 (Bug, status=Queued) in Issues
close: moved WIT-501 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_MintsNoReopenEvent1651543279/002/close.md)
move: WIT-501 relocated Fixed→Issues (status=Ready for testing, reason=runtime GREEN owed, not a defect)
add: created WIT-502 (Bug, status=Queued) in Issues
close: moved WIT-502 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_PreservesAuthoredBody3983506855/002/close.md)
move: WIT-502 relocated Fixed→Issues (status=Ready for testing, reason=runtime GREEN owed)
add: created WIT-001 (Bug, status=Queued) in Issues
move: WIT-001 stays in Issues (status=Queued, reason=no-op relocation exercising the byte-identical path)
add: created WIT-001 (Bug, status=Queued) in Issues
add: created WIT-510 (Bug, status=Queued) in Issues
close: moved WIT-510 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_RefusesInvariantViolatingCombinations1593022603/002/close.md)
move: refusing — status "Queued" is NON-terminal and cannot live at Fixed (§11.4.15/ATM-627 INTEG-03: a Fixed-location item must carry a terminal `… (→ Fixed.md)` status)
move: refusing — status "Fixed (→ Fixed.md)" is TERMINAL and belongs at Fixed, not Issues (§11.4.15; pass --status with a non-terminal value to move it back to Issues)
add: created WIT-520 (Bug, status=Queued) in Issues
close: moved WIT-520 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_DoesNotRefuseLegitimateMoves4048831094/002/close.md)
move: WIT-520 relocated Fixed→Issues (status=In testing, reason=legitimate reverse-of-close)
move: WIT-520 relocated Issues→Fixed (status=Fixed (→ Fixed.md), reason=legitimate re-close)
add: created WIT-530 (Bug, status=Queued) in Issues
close: moved WIT-530 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestMoveCmd_RejectsIncompleteInvocation777803509/002/close.md)
move: --to is required and must be Issues or Fixed
move: --to is required and must be Issues or Fixed
move: --why is required (recorded in the item_history audit row)
move: --id is required
move: item WIT-999 not found in Issues or Fixed
add: created WIT-001 (Bug, status=Queued) in Issues
update: WIT-001 updated in Issues (status=In progress, type=Bug)
add: created WIT-001 (Task, status=Queued) in Issues
update: --description fails §11.4.91 floor (2 words / 9 chars; need ≥6 words OR ≥40 chars)
update: item WIT-999 not found in Issues
add: created WIT-001 (Bug, status=Queued) in Issues
update: at least one mutable field flag is required (--title / --severity / --description / --type / --status / --created-by / --assigned-to)
add: created WIT-001 (Bug, status=Queued) in Issues
reopen: WIT-001 reopened in Issues (By:AI On:2026-05-31 Reason:test-failed Evidence:qa-results/2026-05-31/wit-001-fail.log)
add: created WIT-001 (Bug, status=Queued) in Issues
reopen: --who is required and must be AI or User (§11.4.34 By)
reopen: --why is required (§11.4.34 closed-set): test-failed | manual-testing-detected | captured-evidence-contradicts | end-user-report | cycle-re-discovered | design-reconsidered
reopen: --who is required and must be AI or User (§11.4.34 By)
reopen: --when is required (§11.4.34 On: ISO date YYYY-MM-DD)
reopen: --incident is required (§11.4.34 Evidence; a reopen without evidence is a §11.4.7 demotion-without-evidence bluff)
reopen: --why "i-felt-like-it" not in §11.4.34 closed-set: test-failed | manual-testing-detected | captured-evidence-contradicts | end-user-report | cycle-re-discovered | design-reconsidered
add: created WIT-001 (Task, status=Queued) in Issues
block: WIT-001 set Operator-blocked in Issues (WHAT:Needs operator to provision a Linux x86_64 gate host)
add: created WIT-001 (Task, status=Queued) in Issues
block: --details is required and must be non-empty (§11.4.21 WHAT)
block: --details is required and must be non-empty (§11.4.21 WHAT)
add: created ATM-901 (Bug, status=Queued) in Issues
close: moved ATM-901 Issues→Fixed (status=Obsolete (→ Fixed.md), evidence=docs/qa/ATM-901/evidence.md)
obsolete-details: ATM-901 written (Since:2026-06-09 Reason:not-reproducible Superseding:none Evidence:docs/qa/ATM-901/evidence.md)
obsolete-details: ATM-901 written (Since:2026-06-09 Reason:not-reproducible Superseding:none Evidence:docs/qa/ATM-901/evidence.md)
add: created ATM-902 (Bug, status=Queued) in Issues
close: moved ATM-902 Issues→Fixed (status=Obsolete (→ Fixed.md), evidence=docs/qa/ATM-902/evidence.md)
obsolete-details: --reason must be one of the §11.4.90 closed-set: superseded-by-design-change | superseded-by-later-mandate | feature-removed | duplicate-of | unsupported-topology | not-reproducible
add: created ATM-905 (Bug, status=Queued) in Issues
obsolete-details: item ATM-905 status is "Queued", not Obsolete — close it with `close ATM-905 --status obsolete` first (§11.4.90)
add: created WIT-001 (Bug, status=Queued) in Issues
export: wrote /tmp/.private/milosvasic/TestExportCmd_RelativeFlags_AnchorAtInvocationPWD_NotProcessCwd2900206146/001/docs/Issues.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_RelativeFlags_AnchorAtInvocationPWD_NotProcessCwd2900206146/001/docs/Fixed.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_RelativeFlags_AnchorAtInvocationPWD_NotProcessCwd2900206146/001/docs/Issues_Summary.md
export: wrote /tmp/.private/milosvasic/TestExportCmd_RelativeFlags_AnchorAtInvocationPWD_NotProcessCwd2900206146/001/docs/Fixed_Summary.md
export: --no-formats set; skipped HTML/PDF/DOCX sibling generation
add: created WIT-400 (Bug, status=Queued) in Issues
close: moved WIT-400 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_PreservesAuthoredBody2014042414/002/close.md)
reopen: WIT-400 reopened, relocated Fixed→Issues (By:AI On:2026-07-20 Reason:captured-evidence-contradicts Evidence:docs/evidence/WIT-400.md)
add: created WIT-401 (Bug, status=Queued) in Issues
close: moved WIT-401 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_WritesReopenedDetails977437787/002/close.md)
reopen: WIT-401 reopened, relocated Fixed→Issues (By:AI On:2026-07-20 Reason:captured-evidence-contradicts Evidence:docs/evidence/WIT-401.md)
add: created WIT-402 (Bug, status=Queued) in Issues
close: moved WIT-402 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_DetailLineIsUpserted227779820/002/close.md)
reopen: WIT-402 reopened, relocated Fixed→Issues (By:AI On:2026-07-20 Reason:captured-evidence-contradicts Evidence:docs/evidence/WIT-402.md)
reopen: WIT-402 reopened in Issues (By:User On:2026-07-21 Reason:test-failed Evidence:docs/evidence/WIT-402-second.md)
add: created WIT-403 (Bug, status=Queued) in Issues
close: moved WIT-403 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_TableRepresentationPreservedVerbatim132190464/002/close.md)
reopen: WIT-403 reopened, relocated Fixed→Issues (By:AI On:2026-07-20 Reason:test-failed Evidence:docs/evidence/WIT-403.md)
add: created WIT-410 (Bug, status=Queued) in Issues
close: moved WIT-410 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_MultilinePriorDetail_CollapsesToOne226709042/002/close.md)
reopen: WIT-410 reopened, relocated Fixed→Issues (By:AI On:2026-07-20 Reason:captured-evidence-contradicts Evidence:docs/evidence/WIT-410.md)
add: created WIT-411 (Bug, status=Queued) in Issues
close: moved WIT-411 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_MultilinePriorDetail_HistoryKeepsBoth765651951/002/close.md)
reopen: WIT-411 reopened, relocated Fixed→Issues (By:User On:2026-07-21 Reason:manual-testing-detected Evidence:docs/evidence/WIT-411.md)
add: created WIT-300 (Bug, status=Queued) in Issues
close: moved WIT-300 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_MigratesFixedItemToIssues3816507297/002/close.md)
reopen: WIT-300 reopened, relocated Fixed→Issues (By:AI On:2026-07-11 Reason:test-failed Evidence:qa-results/2026-07-11/wit-300-fail.log)
validate: OK — 1 items, all invariants satisfied
add: created WIT-001 (Bug, status=Queued) in Issues
reopen: WIT-001 reopened in Issues (By:AI On:2026-07-11 Reason:test-failed Evidence:qa-results/x.log)
add: created WIT-301 (Bug, status=Queued) in Issues
close: moved WIT-301 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestReopenCmd_LocationFixedOverrideKeepsInFixed3298818880/002/close.md)
reopen: WIT-301 reopened in Fixed (By:AI On:2026-07-11 Reason:test-failed Evidence:qa-results/y.log)
add: created WIT-302 (Bug, status=Queued) in Issues
close: moved WIT-302 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestValidate_CatchesReopenedInFixed847262550/002/close.md)
validate: OK — 1 items, all invariants satisfied
validate: 1 violation(s):
  - WIT-302: Fixed-location item has NON-terminal status "Reopened" — a Fixed-location item must carry a terminal `… (→ Fixed.md)` status; a non-terminal item belongs in Issues (§11.4.15/ATM-627 INTEG-03) [section]
validate: OK — 1 items, all invariants satisfied
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestRepairBodies_ClearsDesyncs_RedPolarity3537090322/001/wi.db
validate: OK — 3 items, all invariants satisfied
validate: 2 violation(s):
  - ATM-970 [Issues/section]: items.status="In progress" but body_md **Status:** line derives "Queued" (§11.4.93/ATM-627 column↔body desync)
  - ATM-971 [Fixed/section]: items.status="Completed (→ Fixed.md)" but body_md has NO **Status:** line (md→db would derive "Queued") (§11.4.93/ATM-627 column↔body desync)
repair-bodies: scanned 3 items — applied 2 change(s): 1 rewrite, 1 populate, 1 noop, 0 backfill-segment
validate: OK — 3 items, all invariants satisfied
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestRepairBodies_Idempotent990455604/001/wi.db
validate: OK — 3 items, all invariants satisfied
repair-bodies: scanned 3 items — applied 2 change(s): 1 rewrite, 1 populate, 1 noop, 0 backfill-segment
repair-bodies: scanned 3 items — already canonical (0 rewrite, 0 populate, 0 backfill-segment); no changes
validate: OK — 3 items, all invariants satisfied
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestRepairBodies_PreservesDetailBlocksOnRewrite2767406079/001/wi.db
validate: OK — 3 items, all invariants satisfied
repair-bodies: scanned 3 items — applied 1 change(s): 1 rewrite, 0 populate, 2 noop, 0 backfill-segment
Issues.md: 2 items, 3 segments
Fixed.md: 1 items, 2 segments
synced 3 total items into /tmp/.private/milosvasic/TestRepairBodies_PopulatesEmptyBodyFromColumns1867935472/001/wi.db
validate: OK — 3 items, all invariants satisfied
repair-bodies: scanned 3 items — applied 1 change(s): 0 rewrite, 1 populate, 2 noop, 0 backfill-segment
add: created WIT-001 (Bug, status=Queued) in Issues
add: created WIT-002 (Bug, status=Queued) in Issues
add: created WIT-003 (Feature, status=Queued) in Issues
Workable items by Status:
  Queued  3
  -----------
  TOTAL   3
add: created WIT-001 (Bug, status=Queued) in Issues
add: created WIT-002 (Bug, status=Queued) in Issues
add: created WIT-003 (Feature, status=Queued) in Issues
Workable items by Type:
  Bug      2
  Feature  1
  ------------
  TOTAL    3
Workable items by Severity:
  Critical  2
  Low       1
  -------------
  TOTAL     3
Workable items by Status:
  Queued  3
  -----------
  TOTAL   3
report: choose at most one of --by-type / --by-status / --by-severity / --by-assigned / --by-creator / --obsolete-audit
§11.4.90 Obsolete audit:
  WIT-OBS — an obsoleted item lacking its triple-check details row
      ⚠ §11.4.90 GAP: no obsolete_details row (bare-assertion Obsolete)
  1 Obsolete item(s), 1 compliance gap(s)
§11.4.90 Obsolete audit:
  WIT-OBS — an obsoleted item lacking its triple-check details row
      Since: 2026-05-30  Reason: superseded-by-later-mandate  Superseding: §XY
      Triple-check evidence: git-log: commit abc123 removed the feature; grep confirms no callers remain
  1 Obsolete item(s), 0 compliance gap(s)
Issues.md: 45 items, 46 segments
Fixed.md: 69 items, 70 segments
synced 114 total items into /tmp/.private/milosvasic/TestRoundTrip_RealDocs1608631639/001/workable_items.db
wrote /tmp/.private/milosvasic/TestRoundTrip_RealDocs1608631639/001/Issues.regen.md (40954 bytes)
wrote /tmp/.private/milosvasic/TestRoundTrip_RealDocs1608631639/001/Fixed.regen.md (40784 bytes)
Issues.md: 45 items, 46 segments
Fixed.md: 69 items, 70 segments
synced 114 total items into /tmp/.private/milosvasic/TestValidate_OK_RealDocs1782024481/001/workable_items.db
validate: OK — 114 items, all invariants satisfied
validate: OK — 1 items, all invariants satisfied
validate: 1 violation(s):
  - HXC-999: description too short (1 words / 5 chars): "short"
validate: migrate representation: copy items rows: NOT NULL constraint failed: items_new.created_at
add: created WIT-001 (Bug, status=Queued) in Issues
update: WIT-001 updated in Issues (status=In progress, type=Bug)
validate: OK — 1 items, all invariants satisfied
add: created WIT-002 (Bug, status=Queued) in Issues
reopen: WIT-002 reopened in Issues (By:AI On:2026-07-04 Reason:test-failed Evidence:qa/x.log)
validate: OK — 1 items, all invariants satisfied
add: created WIT-003 (Task, status=Queued) in Issues
block: WIT-003 set Operator-blocked in Issues (WHAT:operator must reconfigure the host)
validate: OK — 1 items, all invariants satisfied
add: created WIT-004 (Bug, status=Queued) in Issues
close: moved WIT-004 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestNoStatusMutationLeavesDesyncclose2557949878/002/close-evidence.log)
validate: OK — 1 items, all invariants satisfied
add: created ATM-025 (Bug, status=Queued) in Issues
subtask-add: created ATM-025-001 (parent=ATM-025, session="s", status=Queued)
subtask-status: ATM-025-001 Queued -> In progress
validate: OK — 2 items, all invariants satisfied
add: created ATM-025 (Bug, status=Queued) in Issues
subtask-add: created ATM-025-001 (parent=ATM-025, session="s", status=Queued)
subtask-status: ATM-025-001 Queued -> In progress
validate: OK — 2 items, all invariants satisfied
add: created WIT-050 (Bug, status=Queued) in Issues
add: created WIT-060 (Task, status=Queued) in Issues
block: WIT-060 set Operator-blocked in Issues (WHAT:operator must do X)
add: created ATM-025 (Bug, status=Queued) in Issues
add: created ATM-026 (Task, status=Queued) in Issues
subtask-add: created ATM-025-001 (parent=ATM-025, session="s", status=Queued)
subtask-add: created ATM-025-002 (parent=ATM-025, session="s", status=Queued)
subtask-add: created ATM-025-003 (parent=ATM-025, session="s", status=Queued)
subtask-add: created ATM-026-001 (parent=ATM-026, session="t", status=Queued)
add: created BG (Bug, status=Queued) in Issues
subtask-add: created BG-001 (parent=BG, session="x", status=Queued)
subtask-add: parent ATM-999 not found in items (a sub-task needs an existing parent)
add: created ATM-100 (Bug, status=Queued) in Issues
subtask-add: created ATM-100-001 (parent=ATM-100, session="D3-post-flash-2026-06-10", status=Queued)
add: created ATM-200 (Bug, status=Queued) in Issues
subtask-add: created ATM-200-001 (parent=ATM-200, session="s", status=Queued)
subtask-status: ATM-200-001 Queued -> In progress
subtask-status: --evidence is required to reach Completed (§11.4.69)
subtask-status: ATM-200-001 In progress -> Completed (→ Fixed.md)
Issues.md: 1 items, 2 segments
synced 1 total items into /tmp/.private/milosvasic/TestATM627_StatusDesync_RealisticMultiBlockBody560438947/001/wi.db
validate: 1 violation(s):
  - ATM-950 [Issues/section]: items.status="Operator-blocked" but body_md **Status:** line derives "Reopened" (§11.4.93/ATM-627 column↔body desync)
Issues.md: 1 items, 2 segments
synced 1 total items into /tmp/.private/milosvasic/TestDiffCmd_BareDBOnlyReportsColumnBodyDesync1038513198/001/wi.db
Fixed.md: 2 items, 4 segments
synced 2 total items into /tmp/.private/milosvasic/TestDiffCmd_NoPathsSkipsMarkdownComparison140447993/001/wi.db
--- FAIL: TestDiffCmd_NoPathsSkipsMarkdownComparison (0.00s)
    sync_diff_nopaths_test.go:66: RED: expected diff --db without --issues/--fixed to invent false-positive 'present in DB, absent in Markdown' lines on an in-sync DB, but output has none — defect not reproduced:
        diff: DB and Markdown are in sync
Fixed.md: 2 items, 4 segments
synced 2 total items into /tmp/.private/milosvasic/TestDiffCmd_CompositeKeyNoSpuriousDivergence4071945591/001/wi.db
add: created WIT-001 (Bug, status=Queued) in Issues
update: WIT-001 updated in Issues (status=Queued, type=Bug)
add: created WIT-001 (Bug, status=Queued) in Issues
update: WIT-001 updated in Issues (status=In progress, type=Bug)
add: created WIT-401 (Task, status=Queued) in Issues
block: WIT-401 set Operator-blocked in Issues (WHAT:operator must reconfigure the host ADB daemon limits)
validate: 1 violation(s):
  - WIT-401: Operator-blocked unblock_condition has no enumerated unblock CHOICES (§11.4.148 D3): "operator raises the host ADB daemon file-descriptor limit"
add: created WIT-402 (Task, status=Queued) in Issues
block: WIT-402 set Operator-blocked in Issues (WHAT:operator decides the host ADB daemon mitigation)
validate: OK — 1 items, all invariants satisfied
add: created WIT-403 (Task, status=Queued) in Issues
validate: 2 violation(s):
  - WIT-403 [Issues/section]: items.status="Operator-blocked" but body_md **Status:** line derives "Queued" (§11.4.93/ATM-627 column↔body desync)
  - WIT-403: Operator-blocked with no operator_block_details row (§11.4.148 D3)
add: created WIT-701 (Bug, status=Queued) in Issues
close: moved WIT-701 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_ResolvableAbsolutePath_NoViolation1413457176/003/closure-artefact.log)
validate: OK — 1 items, all invariants satisfied
add: created WIT-702 (Bug, status=Queued) in Issues
close: moved WIT-702 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_ResolvableRelativePath_AnchoredAtPWD_NoViola1142843734/003/closure-artefact.log)
add: created WIT-703 (Bug, status=Queued) in Issues
close: moved WIT-703 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_WellFormedPathButMissingFile_Violation3411169017/003/closure-artefact.log)
add: created WIT-704 (Bug, status=Queued) in Issues
close: moved WIT-704 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_NarrativeText_Violation2643069931/002/closure-artefact.log)
add: created WIT-705 (Bug, status=Queued) in Issues
validate: OK — 1 items, all invariants satisfied
add: created WIT-706 (Bug, status=Queued) in Issues
close: moved WIT-706 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestValidate_UnresolvableClosureEvidence_FailsThenPassesWhenEvid2592559514/003/closure-artefact.log)
validate: 1 violation(s):
  - WIT-706: closure evidence_path does not resolve (well-formed path, but nothing exists there) — history id=2, event=Fixed, on=2026-08-18: "/tmp/.private/milosvasic/TestValidate_UnresolvableClosureEvidence_FailsThenPassesWhenEvid2592559514/001/qa/run-7/capture …" (§11.4.5/§11.4.69/§11.4.123/§11.4.226 — a closure's captured proof must be producible on demand)
validate: OK — 1 items, all invariants satisfied
add: created WIT-707 (Bug, status=Queued) in Issues
close: moved WIT-707 Issues→Fixed (status=Fixed (→ Fixed.md), evidence=/tmp/.private/milosvasic/TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_No4104596393/003/closure-artefact.log)
validate: OK — 1 items, all invariants satisfied
group add: created group-a (destination=main priority=1 state=open)
validate-groups: OK — 2 items, 1 groups, all design §3.1 invariants satisfied
group add: created group-a (destination=main priority=1 state=open)
group add: created group-b (destination=main priority=2 state=open)
group add: created group-a (destination=main priority=1 state=open)
validate-groups: OK — 1 items, 1 groups, all design §3.1 invariants satisfied
group add: created group-a (destination=main priority=1 state=open)
group add: created group-a (destination=main priority=1 state=open)
validate-groups: OK — 1 items, 1 groups, all design §3.1 invariants satisfied
validate-groups: OK — 1 items, 0 groups, all design §3.1 invariants satisfied
group add: created group-a (destination=main priority=1 state=open)
validate-groups: OK — 1 items, 1 groups, all design §3.1 invariants satisfied
group add: created urgent-main (destination=main priority=0 state=open)
validate-groups: OK — 1 items, 1 groups, all design §3.1 invariants satisfied
group add: created urgent-main (destination=main priority=0 state=open)
group add: created group-a (destination=main priority=1 state=open)
group add: created group-a (destination=main priority=1 state=open)
group add: created group-a (destination=main priority=1 state=open)
FAIL
FAIL	github.com/HelixDevelopment/HelixConstitution/scripts/workable-items/cmd/workable-items	0.912s
FAIL
package-suite-exit=1

```
