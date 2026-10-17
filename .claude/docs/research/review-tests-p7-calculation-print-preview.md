# Test Review: P7 calculation and PDF preview

Status: PASS for source/test review — the Medium gap is resolved; no open material test finding. Follow-up execution results are recorded separately below.

## Scope and evidence

Reviewed the approved plan and nonempty initial scoped patch `.agents/logs/review-diff-p7-calculation-print-preview.patch` (128461 bytes at initial review), the three changed/new test modules, their production implementations, runtime dependency changes, README, and existing CLI publication/rollback tests. Re-reviewed the subsequent artifact-identity fix directly in current source and tests. The unrelated `.claude/docs/Example橋脚2/` work is outside this review.

- Root integration gate log `tmp/quality-gates/pytest-20261015-111841-6762610.log`: **599 passed, 0 failed, 0 skipped**, 150.54 seconds. This reviewer inspected the log and did not repeat the unchanged full suite.
- `tmp/p7-print-preview/ui-evidence.json` and its harness show two real CLI runs through the real Tk app, four PDF/JSON pairs, matching input SHA, first/last pages of all four reports, responsive events, and zero callback errors.
- `tmp/p7-print-preview/layout-evidence.json` records 1360×900 and 980×640 layouts, minimum preview canvas 690×232, and invalid-input exit 2 with existing outputs unchanged.
- The preview implementer's work log records isolated `--no-dev` import, PDF rendering, and PhotoImage creation with pytest/pypdf absent. PyMuPDF is now runtime with its locked version unchanged.
- Coverage: **not measured**. No numerical coverage claim is made. Ruff was unavailable and is not claimed as passing.

## Findings

- **[Medium — resolved] `./tests/test_editor_gui.py` / calculation result labels and preview reload:** the initial tests did not assert revocation of the prior “今回の計算結果” label when a generated PDF was externally replaced after success. The fix retains the final validated snapshots for all eight artifacts and checks identity/readability at list refresh and before/after preview metadata reads and rendering.

  The new GUI regression replaces a generated PDF with a different valid three-page file, then covers refresh, reload, page navigation, and zoom. Every case requires stale state, an old-output label, and a recalculation message; non-refresh cases also prohibit recursive list refresh from the preview callback. Additional cases cover deletion, corruption, read denial, and changed sibling JSON. `PendingCalculation` inherits the production `check_current_outputs()` implementation, so these GUI assertions do not mock away the fix.

  Real controller tests assert all-eight snapshot retention and exercise PDF/JSON replacement, deletion, corruption, and read denial. Unchanged refresh and unrelated extra PDFs preserve success; render-only failures remain independent of calculation status. The real same-input rerun test now verifies the new current-output check after each successful run. Legitimate reruns still need no timestamp or content difference.

- Open findings: none.

## Existing test quality

The new tests meaningfully cover subprocess argument isolation, fixed output destination, worker/main-thread division, unconsumed completion guards, nonzero/spawn/thread/log failures, bounded UTF-8 logs, every missing artifact, JSON/PDF corruption, access errors, SHA mismatch, mutation during validation, and same-input real CLI reruns. Temporary inputs/outputs isolate production files.

GUI tests cover pending cell flush, invalid numeric edits, clean external changes before dispatch, save/fingerprint failure, duplicate execution, keyboard and close guards, event pumping, navigation/state preservation, old-result labels after failed reruns and input changes, dispatch recovery, and independent preview errors. Preview tests cover file handles, first/last pages, invalid pages, zoom/allocation bounds, empty/encrypted/non-PDF inputs, missing/corrupt/replaced files, rendering retry, cleanup/debounce, and wheel routing.

The old focusless tests were **not weakened**: the helper transfers focus to another Tk interpreter before withdrawal, while callers retain `focus_get() is None`, open editor, atomic flush, undo, and commit assertions. No skips or assertions were removed to hide the baseline setup failures.

Existing `test_reaction_cli.py` publication/backup/restoration lock-failure tests and `test_transverse_cli.py` all-eight-publications renderer failure test remain unchanged. These exercise injected `PermissionError` boundaries; the GUI's isolated invalid-input run separately demonstrates old output preservation.

## Follow-up execution

Inspected `tmp/p7-print-preview/gui-output-identity-targeted.txt`: **78 passed, 0 failed, 2 skipped, 42 deselected**, 76.99 seconds. The owner's targeted run includes all 18 new artifact-identity regressions, same-input actual CLI rerun, and rendering-error independence. The two skips are inherited Tk initialization failures in the existing preview recovery/cleanup tests; the owner is replaying those in isolation.

The root will run the final integration gate. This reviewer did not run concurrent Tk tests or claim the initial 599-test result covers the subsequent fix. Test design/source review is PASS; the root's final acceptance report must record the isolated replays and final gate separately.

## Lead Final Acceptance

After the reviewed correction, the lead ran the full gate: **616 passed, 1 skipped, 0 failed in 238.79s**, `overall: pass` (`tmp/quality-gates/pytest-20261015-113121-2889947.log`). The sole skip was transient Tk initialization in `test_numeric_nullable_and_invalid_input_navigation`; an isolated replay passed in 7.28s (`tmp/p7-print-preview/final-skipped-replay.txt`). All 617 cases were therefore verified successfully. This final lead evidence supersedes the pending-execution status recorded at review time. No additional product changes followed this verification.
