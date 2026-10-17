# Column Rebar Input Implementation Tasks

Approved: 2026-10-17. Plan: ../plans/column-rebar-input.md. TDD + parallel-agent-dev.

## Ownership and dependency graph

- Core owner: column_rebar.py, rebar_model.py, test_column_rebar.py; owns geometry, hoops, v1/v2 and state transitions. Publish API contract before UI implementation.
- UI owner: column_rebar_ui.py, rebar_ui.py, editor_gui.py, test_column_rebar_ui.py; preserves current unrelated edits and existing public facade. Preparatory reading may run in parallel; implementation depends on frozen core API.
- Reference owner: fixtures/column_rebar_example2.json, test_column_rebar_reference.py, later WebPier/pre/input.json and README. Fixture is independent; actual input update only after core/UI verification.
- Root: all test gates, snapshot protection, integration verification, actual GUI QA, review coordination, plan/task tracking.
- All agents: no git reset/stash/checkout, no whole-tree formatting, no dependency/lockfile edits, no unowned file changes, no weakening or skipping existing assertions.
- Reviews: parallel input/data preservation, state/GUI integration, test/plan quality. Resolve all Medium+ before completion.

Graph: (independent reference fixture || core schema/model) -> root gate + API freeze -> UI/state integration -> root gates -> WebPier/README -> GUI QA and parallel reviews -> fixes -> final gates/coverage.

## TDD cases (root acceptance list)

- [x] R1: independently transcribed reference76 bars, diameter totals58/18, full11/31 rows and material/hoop values. `column-core-final-1`.
- [x] M1: three generators including fixed ends108/4392, internal27@150 and centered9@250. `column-core-final-1`.
- [x] M2: 0/1/2/3 counts, positive/finite lengths, budget, boundary/overlap and shared corners. `column-core-final-1`.
- [x] M3: v1 unchanged read/save and legacy geometry; v2 feature promotion; malformed/unknown modes and versions; v2 retained when saving other members. `column-core-final-1`.
- [x] M4: separate enclosing hoop diameter and direction totals10/6; no set/shape inference; null/unknown/height interval preservation. `column-core-final-1`.
- [x] M5: automatic center, explicit102, multiple layers and incomplete vs impossible placement. `column-core-final-1`.
- [x] S1: detail snapshot and frozen new material, legacy material inheritance, manual_basis and pending change reload. `column-core-final-1`.
- [x] S2: regenerate preview/apply/cancel/failure/stale; preserve detail mode; explicit switch to auto/restore. `column-core-final-1`.
- [x] U1: dedicated basic fields and hoop direct inputs; reference generated via widget edits; direction and diagram selection. `column-ui-green-4`26passed, zero skips.
- [x] U2: detail edit/regen comparison and cancellation; incomplete notices; active-cell commit. Green4, Green5 and Green6; final comparison capture inspected.
- [x] I1: column/beam/footing switch and unedited data preservation; save/SaveAs/reload/busy/atomic failure. `column-ui-green-2` plus Green4 actual-WebPier roundtrip; equivalent full-suite gate still tracked in Q3.
- [x] P1: actual WebPier exact reference after save/reload and non-column JSON equality; source PDFs unchanged. `column-webpier-green-1`, Green4 and final-audit.json. This task did not regenerate calculation outputs; concurrent seismic output changes are preserved and separately attributed.
- [x] Q1: real GUI QA1360x900 and980x640, diagrams/tables/input/errors visible. Owned Tk captures and widget tests; native mouse automation unavailable.
- [x] Q2: parallel reviews converge to zero Medium+. Round4–6 findings are closed; final two independent narrow rereviews both C0/H0/M0/L0.
- [x] Q3: equivalent full root gate `column-rebar-full-final`:3802passed, failed0, skipped0; core96%/UI90%/combined92%, threshold80%. Standard check.ps1 remains an environmental failure from the preexisting stale lockfile; no lockfile edit.

## Environment

Rules/STATE/DESIGN/PROGRESS absent as already reported and authorized. .claude/skills/tdd-workflow absent; canonical .agents/skills/tdd applies. Python-only project: Rust/Clippy examples do not apply. Existing WebPier venv is the managed uv environment. Root runs every TDD gate via that interpreter and run_tests.py --runner python, avoiding unrelated lockfile changes. Final check.ps1 is run with explicit ProjectRoot; any environmental failure is diagnosed and reported, never labeled passed.

Baseline: tmp/column-rebar-implementation/baseline-sha256.json, baseline-status.txt, baseline.diff. Do not replace baseline files.

## Run log

- Implementation approval recorded. Baseline `column-rebar-baseline`: 152 passed / 1 skipped (212.01s). Skip must not substitute for real GUI QA.
- Core M1: `column-core-red-1` valid failure (3 missing-facade assertions), then `column-core-green-1` 3 passed. Boundary cases are next.
- Independent R1: `column-reference-red-1` 1 failed / 1 passed; failure is unsupported root version 2. Source transcription integrity passed.
- Dedicated UI: `column-ui-red-1` 5 failed / 1 skipped; all failures identify the missing dedicated component. Investigate environmental skip before final acceptance.
- Test wrappers require both PYTHONUTF8=1 and PYTHONIOENCODING=utf-8 for child pytest on Windows. Earlier decoding failures are not Red/Green evidence.
- Coverage tooling installed only under `tmp/column-rebar-implementation/test-tools`; project dependencies and lockfile remain unchanged. Add this directory to PYTHONPATH for coverage gates.
- M2: `column-core-red-2` 15 failed / 9 passed; `column-core-green-2` 24 passed, including small counts, missing fields, invalid placement and shared corners.
- P1: `column-webpier-red-1` valid assertion failure for shipped root version 1. Actual input is held until core/UI integration passes.
- `.agents/check.ps1 -ProjectRoot <workspace>` was attempted: `overall=fail`, uv exits 2 because existing uv.lock is stale. Log `tmp/quality-gates/pytest-20261017-084738-9546482.log`. Final equivalent full pytest gate will use the managed environment without lockfile updates.
- Native Computer Use initialization succeeded but `sky.list_apps` fails with unavailable native pipe / os error 2, including after kernel reset and reinitialization. No native UI actions occurred. Q1 will use the owned real-Tk harness plus rendered window captures and widget integration tests; final report must distinguish this from mouse-driven verification.
- Legacy hoop return: explicit operation confirms removal of new `column_hoops`, preserves old `band_rows` and root version 2, leaves detailed positions intact. No added stash field. Cancel must preserve everything. This resolves Step4's bidirectional source-switch wording.
- M3/M4/M5 and reference model: `column-core-red-3` 18 failed / 28 passed, then `column-core-green-3` 47 passed including every reference coordinate and directional row. Reference tests corrected the stable member_preview tuple interface without changing oracle expectations.
- Existing model/material regression: `column-model-regression-1` 159 passed (test_rebar_model + test_longitudinal_design_conditions).
- S1: `column-core-red-4` 13 failed / 46 passed; `column-core-green-4` 59 passed. Initial detail snapshot, frozen materials (including null), legacy inheritance, saved basis/pending and atomic table replacement verified.
- S2: `column-core-red-5` 8 failed / 59 passed; `column-core-green-5` 67 passed. Detached comparison, stale/modified candidate rejection, apply remaining detailed, explicit auto/archive/restore and changed-dimension repair verified.
- UI1 partial integration `column-ui-green-1a`: 4 passed / 1 failed. At980x640 direction table was clipped; fixed by moving common inputs into left scroll pane and using explicit right-pane grid rows. Retry including incomplete regeneration is running.
- Owned Tk capture `tmp/column-rebar-implementation/qa-small-retry.png` inspected: correct app, diagram/table/action controls visible at980x640. Harness uses a scratch recipe, leaves real input untouched. Final captures will use updated real-input copy and completed controls.

## Review findings to resolve

Early reference/data review (round 0), three accepted MEDIUM findings, no CRITICAL/HIGH. Exact scenarios/lines in `.agents/logs/column-rebar-reference.md`.

- [x] R0-A: explicit new-hoop removal is not persisted by changed-leaf patching; preserve old bands and root v2. Fixed, root coverage gate171passed.
- [x] R0-B: new distribution's face-normal cover wrongly constrained by min(width,height), rejecting valid tall/wide rectangles; separate normal depth from in-plane span while preserving legacy semantics. Fixed, root coverage gate171passed.
- [x] R0-C: new equal-spacing distribution with null endpoints must stay incomplete, not silently become 'exclude endpoints'. Fixed, root coverage gate171passed.
- [x] R1-D (root review, MEDIUM): restoring default empty manual_positions with no recorded basis must reject nonexistent archive, rather than silently activate zero-bar detail. Preserve intentional empty new archive with basis. Red7 two failures, `column-core-final-1`234passed. Shared predicate column_has_detail added.

Core6 accepted fixes: `column-core-red-6` 4 failed / 67 passed; `column-core-coverage-2` 171 passed including all core/existing model/reference recipe tests, new pure module coverage93% >=80%. First coverage attempt had a mistyped node and ran no tests; not evidence.

UI2 gate `column-ui-red-2`: 8 intended missing-feature failures, 5 passed, 2 Tk initialization skips. UI implementation may proceed; replay skipped initial edit/size cases at final verification. Native Tcl intermittent file-read failures predate this change (local files exist); no dependency reinstall or skip workaround introduced.

Concurrent work: README changed while this task held its edits (current SHA0BE900AB... at09:05); preserve it by editing only reinforcement documentation. Real input and dependency hashes still match implementation baseline.

Final core/data review round1 confirmed A/B/C/D fixed and found two further MEDIUM issues (no CRITICAL/HIGH):

- [x] R2-M1: generated manual_basis must replace its prior source snapshot atomically, otherwise recursive save merge retains old hoop-source input and creates false pending state after reload. `column-core-red-8` valid1failure; `column-core-green-8`1passed and `column-core-final-2`237passed.
- [x] R2-M2: finite integer-valued float layer1e20 self-references through rounded layer-1; new layout/regeneration paths must not leak RecursionError. `column-core-red-9`2failures; exact integer subtraction fixed, `column-core-final-2`237passed.
- [x] R2-M2b: valid1001-layer chain still exceeds recursion depth. `column-core-red-10`2 intended failures; memoized iteration preserves predecessor semantics without a depth limit. `column-core-final-4`:239passed, pure module93% coverage. final-3 had mistyped root node IDs and ran no tests; not evidence.
- [x] R3-M1: virtual detail table follows changed common cover/material before first edit and snapshots the latest automatic layout, preserving pending invalid text. Red3/replay then Green3 verified.
- [x] UI3: modal-construction cleanup, compatibility copy confirmation, X/Y arrows, and active-new-hoop schematic excluding retained inactive legacy shapes. Green3 verified.

UI2 implementation ready; combined new/old UI and coverage gate `column-ui-green-2` running. Old UX-test changes inspected: preserve coordinate, saved-data and inactive-detail assertions while adopting explicit detail/auto transitions and neutral table wording.

Actual-WebPier GUI roundtrip test prepared separately in test_column_rebar_reference_ui.py: copies real input into pytest temporary files, exercises normal open/save/SaveAs/reopen, compares the complete normalized document and all reference bars/rows, and verifies real-source bytes remain untouched. Existing loader normalization is separately recorded.

- `column-ui-green-2`:69passed/1Tk initialization skip, dedicated UI coverage86%>=80. Skipped size test at test_column_rebar_ui.py:107 will be replayed. UI3 review regressions pending.
- `column-webpier-ui-red-1`:1 intended failure on actual rootversion1; existing loader normalization was empty. Actual input/README owner released for the approved narrow update after core/UI2 verification, with pure/GUI Green to follow.
- Concurrent seismic work is regenerating WebPier output files. Our task does not write calculation outputs; final preservation audit distinguishes those concurrent changes from this task instead of claiming all output hashes stayed unchanged.

- WebPier update: `column-webpier-green-1`3passed. Root `input-audit.json` confirms only8 approved changed/added subtrees, non-column exact equality, source PDFs and dependencies unchanged. Concurrent test_editor_gui.py changes only concern0720 report counts/pages and were inspected/preserved.
- `column-ui-red-3`:5 intended failures/1Tk skip; `column-ui-red-3-replay`:1 intended stale-table failure. `column-ui-green-3`:20passed/2Tk skips, UI86% coverage, including actual WebPier normal open/save/SaveAs/reopen with full diagram/table/document equality. Skips: small-size parameter and legacy-hoop return; final repeat required.
- Review round4 accepted3 deduplicated Medium findings: malformed new containers reaching widgets; present incomplete distribution mode being silently filled; refused direction switch leaving the selector label inconsistent. README's old column labels corrected separately (Low).
- Core11 malformed container fix: Red8failed/1pass; `column-core-final-5`249passed, core94% coverage. Shape-only loading preserves absent/incomplete/unknown values and numerical repair. Independent UI-owner rereview: C0/H0/M0/L0.
- UI4 mode/selector fixes: `column-ui-red-4`2 intended failures/1pass/1Tk skip. `column-ui-green-4` all25 dedicated UI cases plus actual WebPier GUI running; narrow parallel rereviews underway.

Round4 final independent rereviews completed: reference owner C0/H0/M0/L0; core owner H0/M0/L0 (no Critical identified); UI owner core11 C0/H0/M0/L0. No deferred findings. Evidence in the three dedicated implementation logs. Product/test files frozen for final root gates and visual acceptance.

Round5 accepted Medium: selecting an existing legacy column band row invokes the shared details renderer, which resets `_derived_sheet` even though the dedicated right-hand table remains visible. Later cover/diameter changes can therefore leave that table stale. UI owner will add one focused regression and retain the dedicated table reference; beam/footing behavior remains scoped as before. Waiting for Green4 to finish before editing.

- `column-ui-green-4`:26passed, zero skips, UI88% coverage. All earlier dedicated UI skipped cases now executed successfully.
- Round5 closure: `column-ui-red-5`1 intended stale60/70 failure; `column-ui-green-5`2passed including explicit legacy return. Independent core/reference narrow rereviews both C0/H0/M0/L0. Conditional sheet-reference preservation leaves beam/footing reset behavior unchanged.
- Real Tk QA captured and inspected1360x900 and980x640 basic, hoops, detail, pending, error, and scrolled condition/detail screens under `tmp/column-rebar-implementation/qa-final-*.png`. Direction labels, units, fixed figure, detail status, controls and scroll access are legible.
- Visual acceptance identified one remaining comparison-footer issue: at820x560 the apply/cancel button captions are vertically clipped. UI6 adds a focused real-Tk geometry regression before a bounded layout fix. This is the sole remaining product change; full-suite gate follows it. Native Computer Use remains unavailable; these are owned real-Tk rendered captures, not mouse-driven native automation.
- UI6: `column-ui-red-6`1 intended failure (button height16px versus requested35px); `column-ui-green-6`3passed/1 environmental Tk initialization skip. New geometry regression, stale-candidate rejection and modal cleanup passed; cancel/apply case awaits full-suite execution or isolated replay. Comparison body now reserves intro/summary/footer height and lets only the table/figure row shrink.
- Round6 independent rereviews: core and reference owners both C0/H0/M0/L0. Root inspected the replacement `qa-final-comparison.png`: both button captions fully visible, old/new diagrams, counts and scrollable position tables intact. All product files frozen for `column-rebar-full-final` (full suite, both new modules, coverage minimum80%).
- Final preservation recheck `tmp/column-rebar-implementation/final-audit.json`: all6 protected hashes unchanged, non-column input equality true, actual WebPier SHA256 `d8da41d8d87a04b33a35cc45226231564ebd1dc1dcdcf3abce397d7487887f78`. Concurrent commit2477dfb includes some earlier in-progress work; root made no commit and retains the independent baseline for attribution.

## Final acceptance

- `column-rebar-full-final`: observed=passed, wrapper exit0; **3802 passed in811.01s**, failed0/skipped0. Both new modules pass the80% coverage gate: pure core96%, dedicated UI90%, combined92%.
- JUnit confirms all3802 test cases executed without failure/error/skip, including the earlier Tk-skipped regeneration cancel/apply case and new footer geometry test. No further replay or repeat suite is required.
- All14 frozen source/test/input/README hashes match before/after the gate. Final input/non-column/PDF/dependency preservation audit passed; `git diff --check` passed.
- Final native-tool limitation remains explicit: owned real-Tk captures and widget integration tests were used, not native mouse automation. The standard locked-uv entry point failed on the preexisting lockfile mismatch; the equivalent full managed-environment gate passed.
- No remaining implementation/review findings. Plan and all acceptance items complete. Continuation tool catalog no longer exposes linksee-memory calls; final evidence is retained in this file, the plan, dedicated logs and final-audit.json.
