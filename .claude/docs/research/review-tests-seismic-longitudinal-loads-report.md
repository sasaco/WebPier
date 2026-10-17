# Test Review: seismic-longitudinal-loads-report

## Summary

Independent read-only review on 2026-10-16. One Medium gap was confirmed and then closed: nonround factor precision was not checked in the PDF substitution expressions. The adaptive formatter and the added regression test now verify the actual displayed equations. The subsequent Decimal zero-divisor rounding boundary is also protected and covered by a real-PDF regression. No open High/Medium test gap remains in this review. Overall acceptance still depends on the root full gate.

## Review Scope

- Approved plan, the three new seismic test modules and three frozen fixtures; related calculator/renderer/CLI code; modified CLI, publication, controller, GUI tests; unchanged reusable PDF preview tests.
- Evidence: `tmp/seismic-longitudinal-loads-implementation/root-validation.json`, `diff-evidence.json`, the slug-specific review patch, and implementation work logs with retained test results.
- Coverage: **not measured**. `gather_diff.py` reports `coverage: null`; no percentage is inferred and no coverage dependency was installed.
- Existing dependency changes and concurrent FrameWeb helper refactoring were excluded from the owned feature review.
- Follow-up scope: `P7橋脚/tests/test_longitudinal_cli.py`, added by root after the full gate exposed an overlooked eight-file all-stage expectation.

## Findings

### [Medium, resolved] Nonround input precision was untested in report substitution expressions

- Files: `P7橋脚/tests/test_seismic_longitudinal_report.py:151`; affected renderer `P7橋脚/src/seismic_longitudinal_report.py:153` and footing factor formatting in `_inertia`.
- The calculator mutation at `test_seismic_longitudinal_calculator.py:196` uses `b1=3.113`, `w1=9.377`, and `unit_weight_body=25.237`. Their product is `736.683197437`, rounded to `736.68 kN/m`. Before the fix, the PDF displays `3.11 × 9.38 × 25.2 = 736.68`, although the displayed factors give `735.13 kN/m`.
- Existing report variants check final action values and layout, but retain the default one-decimal unit weight and do not assert the high-precision factors. Thus this meaningful input-change regression escapes those tests.
- Required regression: render valid nonround geometry and unit weights, assert the displayed substitution factors preserve the input precision and the adopted final value, including the footing factors; retain the baseline formatting and three-page readable bounds. The test should consume the real calculated snapshot, not a fabricated PDF text expectation alone.
- Resolution independently reviewed: `_formula_factors` starts with reference precision and increases displayed precision until decimal arithmetic reproduces the adopted two-decimal result. `test_nonround_formula_factors_reproduce_the_displayed_results` uses the calculator's real nonround mutation, extracts the resulting PDF text, and independently recomputes Hw1/Hw2/Hw3, pedestal H/M, and footing H using `Decimal`/`ROUND_HALF_UP`. It explicitly requires `3.113 × 9.377 × 25.237 × 1.00 = 736.68`, checks three-page readable bounds, and limits unhelpful floating-point tails. This test would fail on the original fixed-precision renderer.
- Final verified implementation evidence: report module 11 tests plus dedicated CLI 24 tests, **35 passed in 37.58 seconds**, read directly from `tmp/seismic-longitudinal-loads-implementation/report/focused-report-cli.txt`. This follows the final 2026-10-16 22:24:38 JST renderer/test update. The baseline PDF remains byte-identical with SHA256 `90e53877bc2d3e94b87b09e4abb39ebb8cbbf9bf424bd18987ac1c74b86fe445`. The reviewer also read the full nonround candidate's extracted text and confirmed the new factor strings in all affected equations.
- Additional boundary checked: `test_small_positive_formula_divisor_adds_precision_before_evaluation` uses a real calculation with footing unit weight `0.04`, whose initial one-decimal representation is `0.0`. The formatter catches `DecimalException` for that candidate and increases precision. The test requires a successfully generated three-page PDF containing `/ 0.04`, the adopted footing result, and readable bounds. This would fail without the new guard.
- Status: **closed**, including the Decimal exception boundary follow-up. Root reports successful formal 0710 regeneration with the final code and unchanged baseline bytes.

### Full-gate follow-up: old all-stage expected set corrected

The gate exposed `test_each_dependency_is_calculated_once[all]` in the previously unchanged `test_longitudinal_cli.py`. The exact red log shows CLI success and one calculation per dependency already passed; the remaining assertion expected the old eight root files and rejected the two authorized 0710 outputs. Independently reviewed the three-line-scope adjustment: explicitly append the 0710 pair to `ALL_NAMES`, add its renderer to the existing quick-render fixture, and add its renderer to the invalid-H1 no-render guard. The assertion remains exact set equality, 0610-only expectations remain intact, and the no-render guard is strengthened. No product code changed. Directly checked `integration-longitudinal-cli-green.txt`: the entire file now passes, **25 passed in 22.02 seconds**. This is a valid contract update, not a weakened test.

## Contract Coverage Confirmed

| Contract | Evidence reviewed |
|---|---|
| Independent source values | Original PDF display values/case semantics in `seismic_longitudinal_example2.json` are separate from current input expectations. Extracted reference pages 8 and 12 agree with the recorded values. The frozen input fixture is bound to its SHA. Zero pedestal and lower-beam expectations are explicitly current-input data. |
| Physical values and semantics | Tests cover signed Wp, S2, Kh=0.20 already applied, one-time coefficient application, eight case classifications and the single coefficient table. |
| Meaningful mutations | Earthquake train load including zero, span lengths, swapped bearings, signed arms, remote A D2/S2, nonseismic snow independence, nonround geometry/material weights, taper and nonzero pedestal. |
| Rounding and detached data | Independent Decimal/Single helpers verify the established rounding boundary. The span test preserves the unrounded sum of side moments. Nested mutation checks verify the input, frame roles, and case load copies do not alias the upstream result. |
| Invalid input | Missing fields, wrong types including bool, NaN/infinity, top schema/stage, case uniqueness/type/meaning, non-unit pier Kh, inconsistent formulas, malformed member references, malformed SHA, and derived overflow have rejection tests. |
| Requested PDF | Three A4 pages, heading/order/page labels, reference values, units, eight cases, no springs/fixed-base additions, six current nodes and actual dimensions, bearing labels, selectable text, readable vector/text bounds, nonzero inertia rows, taper, and train changes. Root visual evidence supplements text/bounds assertions. |
| Runtime independence | Renderer guards prohibit opening JSON/PDF/spreadsheet sources and check nonmutation. Adapter source has no filesystem reads; CLI passes the exact in-memory 0610 object. |
| Standalone/all | Counts verify one input read and one upstream calculation per run. Standalone succeeds in an empty directory, produces only the 0710 pair and no FrameWeb export. Real standalone/all JSON and three PDF pages are equal. Existing artifacts are preserved. |
| Publication failure | Sixteen combinations cover standalone/all, existing/empty destinations, render OSError/ValueError, JSON write failure, and last-file publication failure. Assertions compare all bytes and staging cleanup. |
| Manifest and GUI | Missing/tampered PDF and JSON are rejected. Controller expectations derive from the five-stage registry; readable tampering and post-success freshness are checked. GUI order/count and selecting/rendering all three 0710 pages are covered. |

## Test Execution Results

- This reviewer did not rerun the full suite, Tk tests, or already-completed focused tests; the root owns the shared full gate.
- Retained completed implementation results at review time: calculator **75 passed**, report **9 passed**, dedicated CLI **24 passed**, selected existing regression **42 passed**. These are 150 passed test invocations across distinct focused scopes, not a full-suite result.
- After the final precision and Decimal-boundary correction: report **11 passed** and dedicated CLI **24 passed** in one completed **35-test run (37.58 seconds)**. This supersedes the intermediate 34-test run and replaces the initial report/CLI evidence for the revised renderer; repeat runs are not added as unique test coverage. The root full gate had already collected/imported the old renderer, so the corrected code is verified by this separate focused run.
- Full-gate follow-up: `test_longitudinal_cli.py` **25 passed in 22.02 seconds** after the authorized all-stage expectation update. Inspected both `integration-longitudinal-cli-red.txt` (exact old expectation failure) and `integration-longitudinal-cli-green.txt` in the team work-log directory. No duplicate full/Tk run was started by this reviewer.
- The broader implementation GUI/controller run was intentionally stopped to avoid shared-desktop interference. Its partial output is **not** a PASS result.
- The root full gate exposed the stale expectation described above; its final status, any other failures/skips, and final acceptance must be recorded separately. The focused green result does not relabel the original full-gate run as PASS.
- Root validation evidence confirms standalone/all byte equality, four existing report JSON/text/page parity, all 14 output files, unchanged SHA for 155 protected files, and visual QA of the baseline and three variants.
- Coverage: **not measured**. Ruff: unavailable/skipped in the supplied diff evidence.

## Limitations

Reviewing every defensive branch does not imply measured branch coverage. The controller/GUI tests include purposeful synthetic readable artifacts for publication and UI contracts; real CLI generation and root visual inspection provide the complementary report-content checks. Full-suite acceptance remains contingent on the root gate and completion of the separate quality review.
