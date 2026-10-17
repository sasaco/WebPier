# Security Review: P7 Calculation Print Preview

Date: 2026-10-15

Verdict: **PASS** — no actionable introduced security findings.

## Review Scope

Reviewed the approved plan and the initial complete nonempty patch `.agents/logs/review-diff-p7-calculation-print-preview.patch` (128461 bytes), with source inspection of the unchanged CLI publication contract. A focused follow-up below covers the output-status fix in the regenerated 151667-byte patch.

- `P7橋脚/pier_design/editor_calculation.py`
- `P7橋脚/pier_design/editor_gui.py`
- `P7橋脚/pier_design/pdf_preview.py`
- `P7橋脚/tests/test_editor_calculation.py`
- `P7橋脚/tests/test_editor_gui.py`
- `P7橋脚/tests/test_pdf_preview.py`
- `P7橋脚/pyproject.toml`
- `P7橋脚/uv.lock`
- `P7橋脚/README.md`

Focus: command execution, path and file handling, output integrity, bounded logs, PDF resource handling, and dependency changes.

## Findings

None. Critical: 0; High: 0; Medium: 0; Low: 0.

## Reviewed Controls

- `editor_calculation.py:156`: the child runs the current Python executable and an absolute application-owned script through an argument list with `shell=False`. Input and output paths are separate arguments; Japanese text, spaces, and shell metacharacters are not evaluated as shell code. Production output derives from the application directory, independent of the input directory and cwd.
- `editor_gui.py:509`: calculation always passes through the existing save and external-change checks, compares the saved fingerprint before dispatch, releases preview resources, and acquires the operation guard before starting the worker. Save/open/close and navigation entry points also enforce the guard.
- `editor_calculation.py:95` and `:103`: success requires exit code 0, eight regular files, readable PDFs/JSON, matching input SHA in all four JSON artifacts, stable before/after file metadata, and a final input SHA check. Failure and stale results are not presented as a current successful calculation.
- Output overwrite and restoration remain in the unchanged `cli.py:32` publication routine. The GUI does not introduce additional deletion or rollback logic. PDF enumeration is limited to direct children and excludes symlinks and non-files; extra PDFs are preview-only.
- Temporary stdout/stderr files are context managed and deleted on normal and exceptional exits. Each displayed log tail is bounded to 48 KiB. Logs remain local and there is no new network transmission, credential storage, or executable interpretation of log text.
- `pdf_preview.py:48` and `:74`: PDFs are opened in context managers, rendered one page at a time, and converted to a raster image; preview does not launch an external program or execute PDF actions. Raster dimensions and total pixels are bounded, and invalid/deleted PDFs produce a local error without being rewritten.
- The dependency patch moves the existing PyMuPDF requirement from dev to runtime with no version, artifact hash, or package-source change. This review checks the introduced dependency change; it is not a fresh third-party advisory audit.

## Validation Evidence

Inspected the root integration gate log `tmp/quality-gates/pytest-20261015-111841-6762610.log`: **599 passed in 150.54s**, with no skips. Reviewed the tests for process argument boundaries, failed spawning, bounded logs and handle cleanup, missing/corrupt/mismatched artifacts, output changes during validation, input changes, blocked GUI entry points, and isolated real-CLI reruns. The full suite was not redundantly rerun by this reviewer.

The approved plan explicitly excludes shared locking and complete detection of unrelated concurrent writers. The SHA/stat checks are assessed against that documented contract, not as a cryptographic PDF-to-JSON binding.

## Follow-up: Display-Time Output Changes

Rechecked the quality review fix on 2026-10-15. Security verdict remains **PASS**, with no new findings.

- `validate_outputs` retains the eight regular-file snapshots only after complete validation, and starting another calculation clears the prior snapshot set.
- `check_current_outputs` compares only those known output paths, checks readability through a one-byte read in a context manager, and compares metadata again after closing the handle. A detected change, deletion, non-regular file, or read failure invalidates the result; it does not write, delete, launch a command, or open arbitrary additional paths.
- Preview callbacks run before and after metadata reads and rendering. The host callback updates calculation status and list labels without reopening or recursively rendering the preview. Existing rendering limits and resource cleanup remain intact.
- Additional PDFs remain outside the verified output set. An image-conversion failure with unchanged files remains separate from calculation validity.

This was a source-only focused recheck requested by the lead. No additional tests were run by this reviewer; the post-fix root integration gate was pending at the time of this follow-up. The earlier 599-test result above describes the pre-fix gate.

## Context and Changes

Shared rules, STATE, DESIGN, PROGRESS, and library notes remain absent as already documented in the approved plan. Review used the approved plan and current code. No product file was modified by this reviewer.

## Lead Final Acceptance

After the reviewed correction, the lead ran the full gate: **616 passed, 1 skipped, 0 failed in 238.79s**, `overall: pass` (`tmp/quality-gates/pytest-20261015-113121-2889947.log`). The sole skip was transient Tk initialization in `test_numeric_nullable_and_invalid_input_navigation`; an isolated replay passed in 7.28s (`tmp/p7-print-preview/final-skipped-replay.txt`). All 617 cases were therefore verified successfully. This final lead evidence supersedes the pending-execution status recorded at review time. No additional product changes followed this verification.
