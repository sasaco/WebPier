# Quality Review: P7 Calculation Print Preview

## Verdict

PASS — independent source re-review confirms that the one initial Medium finding is resolved. No unresolved Medium-or-higher issue remains in the reviewed implementation. Final integration-gate execution remains the lead's validation step.

## Review Scope

- Approved plan: `.agents/docs/plans/p7-calculation-print-preview.md`.
- Scope diff: `.agents/logs/review-diff-p7-calculation-print-preview.patch` (initial review snapshot, 128461 bytes).
- Product: `src/editor_calculation.py`, `editor_gui.py`, `pdf_preview.py`; runtime dependency move in `./pyproject.toml` and `uv.lock`; `./README.md`.
- Tests: `./tests/test_editor_calculation.py`, `test_editor_gui.py`, `test_pdf_preview.py`.
- Focus: worker/main-thread boundary, busy and closing guards, save/provenance checks, result freshness, PDF lifecycle, callback cleanup and approved-plan compliance. Existing CLI publication, calculation formulas and report layouts were outside the edit scope.

## Findings

- [Medium, RESOLVED] Initial `src/editor_gui.py:458` — A generated PDF replaced after a successful run was displayed as the current calculation result. `_refresh_pdf_list()` derived current-result badges only from cached success state and path membership; `_pdf_selected()` and preview reload/render reopened the current file without comparing its identity with the verified artifact. Replacing the one-page generated PDF with a different valid two-page PDF and clicking the list refresh displayed the replacement while retaining both `今回の計算結果` and calculation success. This could attribute an unrelated engineering report to the current input. The approved plan explicitly requires detecting external updates at display time. A later replacement is distinct from the excluded concurrent-writer/shared-lock problem.

  Minimal correction: retain the final verified metadata snapshots of generated artifacts. Compare them before setting current-result badges and before reopening/rendering a selected PDF. On observable deletion, replacement or modification, mark the result stale and remove current-result badges without attempting output rollback. Keep pure image conversion errors separate when artifact snapshots are unchanged. Do not trigger a recursive full preview refresh from the render callback.

## Independent Correction Review

- `editor_calculation.py:104` / `:134` / `:247`: final snapshots of all eight generated artifacts are captured by the existing validation operation and retained by the controller only after successful publication/provenance/input checks. A new run clears the prior snapshots.
- `editor_calculation.py:271`: `check_current_outputs()` compares regular-file identity/metadata, verifies readability without retaining handles, and compares again. Detected deletion, replacement, change or access loss sets `stale`. Additional PDFs are excluded from this verified set.
- `editor_gui.py:440` / `:481`: list refresh checks validity before assigning badges. A detected change updates status and existing labels only; it does not invoke preview reload or rebuild the list from within a render callback.
- `pdf_preview.py:192` / `:277`: the access callback executes before and in `finally` after metadata reads and rendering. Selection, reload, page/zoom changes and queued renders therefore cover late changes and errors. The callback remains on the Tk main thread. A pure image-conversion exception with unchanged artifacts keeps calculation success while retaining the separate preview error.
- Reviewed regression assertions for valid PDF replacement through refresh/reload/page/zoom, deleted/corrupted/unreadable artifacts, a changed sibling JSON, unchanged repeated display, additional PDF changes and non-reentrant callback behavior. No new Medium-or-higher source defect was found. No second Codex consultation was needed because the correction follows the already reviewed recommendation without materially new architecture.

## Validation and Evidence

- Root integration gate log was inspected: `tmp/quality-gates/pytest-20261015-111841-6762610.log` ends with `599 passed in 150.54s`; this reviewer did not redundantly run the full suite.
- Root supplied isolated real-Tk/real-CLI evidence for two runs, four reports and first/last page rendering, busy/error behavior, and the 980×640 minimum viewport. These are supplied root verification, not tests executed by this reviewer.
- This reviewer executed `tmp/p7-print-preview/repro_quality_external_replace.py` in a real Tk interpreter with temporary input/output and a simulated completed controller result. Evidence: `tmp/p7-print-preview/quality-external-replacement.json`. Before replacement: one page, success, current badge. After replacement and refresh: two pages, success, current badge. `bug_reproduced: true`. Project input and output were untouched.
- The original reproduction remains historical failing evidence. It manually injected a success result; it must not be rerun unchanged against the correction because it does not populate verified snapshots. New owner tests use real controller snapshot checking. This reviewer did not start Tk concurrently with the owner's focused suite or redundantly run the full suite.

## Codex Consultation

- Read `.agents/skills/codex-system/SKILL.md` and used the repository wrapper with process-local native executable PATH and `--sandbox read-only`.
- Prompt: `.agents/logs/codex/20261015T022322Z-quality-review-p7.prompt.md`.
- Response: `.agents/logs/codex/20261015T022322Z-quality-review-p7.md` (full response read).
- Result: wrapper succeeded in 73.35 seconds, no write access. Codex independently confirmed the same Medium finding and found no other concrete Medium-or-higher defect from the supplied code. Its finding was text analysis; the reviewer separately reproduced it in Tk.

## Limits

Shared rules and DESIGN documents are absent as already established by the lead; approved plan and source were used. Metadata comparisons detect observable benign changes; they are not cryptographic PDF/JSON binding or cross-process locking, both outside scope. The correction is accepted on independent source review; final test execution and release acceptance remain with the lead.

## Lead Final Acceptance

After the reviewed correction, the lead ran the full gate: **616 passed, 1 skipped, 0 failed in 238.79s**, `overall: pass` (`tmp/quality-gates/pytest-20261015-113121-2889947.log`). The sole skip was transient Tk initialization in `test_numeric_nullable_and_invalid_input_navigation`; an isolated replay passed in 7.28s (`tmp/p7-print-preview/final-skipped-replay.txt`). All 617 cases were therefore verified successfully. This final lead evidence supersedes the pending-execution status recorded at review time. No additional product changes followed this verification.
