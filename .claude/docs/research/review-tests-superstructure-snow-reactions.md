# Test Review: Superstructure Snow Reactions

## Summary

No material test gaps or weakened-test regressions were found in the approved snow-input and report-table scope. Existing independent Excel oracle checks remain intact. The added cases exercise the three snow cases separately and retain the boundary that snow does not enter existing horizontal or other downstream calculations.

## Review Scope

Coverage: **not measured**. `tmp/snow-reactions/gather-diff.json` contains `coverage: null`; no percentage is inferred from test counts. Its Ruff result is `skipped` because Ruff is unavailable.

The feature scope is the 22 paths recorded in `tmp/snow-reactions/preservation.json`, with incremental edits checked in `.agents/logs/review-snow-feature.patch` against `tmp/snow-reactions/baseline`. Concurrent frame, rebar, output, and preview changes in the global patch are excluded. Reviewed the approved plan plus the following test areas and their implementation paths:

- Input/model/aggregation: `./tests/test_reaction_inputs.py`, `test_reaction_weights.py`, `test_reaction_calculator.py`; `reaction_inputs.py`, `reaction_weights.py`, `reaction_calculator.py`.
- Editor: `./tests/test_editor_model.py`, `test_editor_gui.py`, `test_editor_formulas.py`, `fixtures/editor_field_paths.json`; `editor_model.py`, `editor_gui.py`, `editor_forms.py`, `pre/input.json`, `README.md`.
- Report: `./tests/test_reaction_report_snow.py`, `test_reaction_report.py`; `reaction_report_snow.py`, `reaction_report_pagination.py`.
- Integration: `./tests/test_reaction_cli.py`, `test_longitudinal_calculator.py`, `test_transverse_calculator.py`; preservation, pipeline, GUI, and PDF QA evidence under `tmp/snow-reactions`.

## Findings

None. No Critical, High, Medium, or Low correction is requested from this review.

Evidence supporting the result:

- `./tests/test_reaction_weights.py:169` supplies explicit, independent expected A/B/C/D and AB/CD vectors and all 20 detail triples. The inputs use poisoned cached B/C totals; the expectations do not come from `calculate_snow`. `:198` isolates d10, and `:213` checks explicit zero and negative A/D inputs at both ends.
- `./tests/test_reaction_inputs.py:210` distinguishes missing/null inputs without input mutation, while `:230` covers partial cases and explicit zero. `:247` checks all three keys at B/C/A/D against bool, strings, dash, containers, NaN, infinities, and huge integers. `:268`, `:276`, and `:298` preserve nonnegative B/C and existing parent validation. Sum overflow is checked with full paths in `./tests/test_reaction_weights.py:223` and `:233`.
- `./tests/test_editor_gui.py:815` asserts 66 virtual blank fields, no dirty state, and byte-preserving no-op save. `:844` compares the entire saved document after one virtual edit. `:858` uses real sheet paste/delete/undo/redo and attempts writes into readonly B/C totals on both sides, then verifies saved types and calculated values. `:902` retains dash as a saved string while requiring calculation rejection. `:915` checks atomic failure without loss of other pending edits.
- `./tests/test_editor_formulas.py:175` checks d2 position and each L1-L4 total after row insertion. Existing GUI expectation updates at `./tests/test_editor_gui.py:662` and `:693` preserve the complete pre-edit A/D content rather than assuming the new initial null keys are absent. Their equality assertions remain meaningful; removed legacy keys or changed unknown values would fail them.
- `./tests/test_reaction_report_snow.py:18` defines fixed numerical vectors and `:43` hardcodes expected rendered coordinates independently of the new renderer. `:67` checks all 18 support values, 60 detail values, five instances of each label, page count, D1+D2 count, and A/D red versus calculated black styling. `:91` checks 118 old numeric cells, `:124` checks rules/page bounds, `:145` checks cache/result immutability across snow/no-snow/snow renders, and `:166` checks G10 alone. PDF QA evidence additionally compares all pages 3-34 against baseline bitmaps.
- `./tests/test_reaction_cli.py:234` exercises editor-model save to both CLI stages with fixed expected vectors and real PDFs/JSONs. `:283` verifies invalid snow rejects before rendering and preserves all eight existing output files. Actual sheet handling is covered separately by the editor GUI cases above.
- `./tests/test_reaction_calculator.py:141` compares every existing result field, excluding only the typed snow input and independent snow result. The existing independent public-value/Single oracle at `:55` remains unchanged. `./tests/test_longitudinal_calculator.py:75` and `./tests/test_transverse_calculator.py:80` compare the complete downstream result after removing only typed `input.snow`. `tmp/snow-reactions/verify_pipeline.py` and its `pipeline-invariance.json` also compare all four stages with only those specific snow exclusions.

Tests use temporary input/output directories and fresh or copied input structures. GUI fixtures instantiate actual Tk/sheet objects; dialog methods are mocked to avoid modal interaction. CLI transaction mocks deliberately fail if an invalid input reaches rendering. No added broad skip, xfail, numerical-tolerance relaxation, removed oracle assertion, or production-output write was found in the feature patch.

## Test Execution Results

- Reviewer execution: no duplicate pytest/full-suite/Tk runs, as instructed by the lead after its coordinated gate; no reproducer was needed because no candidate defect remained.
- Coordinated gate inspected in `tmp/snow-reactions/integration-gate.json`: **2308 passed, 1 skipped, 0 failed in 298.86s**. The single existing Tk initialization skip is assigned to the lead for isolated replay and is not counted here as a pass.
- Inspected owned-run evidence: core **288 passed**; GUI/model/formulas **167 passed, 0 skipped**; report **12 passed**; five CLI cases and two downstream invariance cases reported passing by the lead. These overlap the full suite and are not summed.
- `tmp/snow-reactions/report/verification.json`: 34 PDF pages; all 78 snow values; pages 3-34 identical to baseline renders. Latest `tmp/snow-reactions/preservation.json`: 342 existing input leaves preserved, 66 new inputs, 29 protected files and six production outputs unchanged. Earlier 31/eight preservation held at that check; concurrent external work subsequently regenerated the 0610/0620 PDFs, which the snow work preserved. Snow CLI/QA rendering uses temporary outputs.
- Coverage: **not measured**. Ruff: **skipped / unavailable**.

## Communication with Teammates

- From lead: restricted review to snow feature paths, provided independent verification evidence, requested material missing regressions only, and prohibited duplicate full-suite/Tk runs and code edits.
- To lead: reported no material gap or masked-defect finding; clarified that the pipeline evidence filename is `pipeline-invariance.json`, rather than `fullpipeline-invariance.json`.

## Issues Encountered

- Shared context remains absent: the loader returned `missing: [".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]`, `unreadable: []`, `warnings: ["DESIGN.md is still the uninitialised /init template; run /init to populate it"]`, `design.placeholder: true`, and `progress.entries: 0`. The lead already reported this state and authorized the scoped work without initialization.
- The initial provided pipeline artifact name did not exist; inspected `tmp/snow-reactions/pipeline-invariance.json` and its generator instead.
- The global patch includes concurrent changes outside this feature; the saved implementation-start baseline and 22-path preservation manifest define the review scope.
- Lead reported an intermediate existing-Tk replay group of three passes and one initialization skip; a fresh isolated replay remains with the lead. The owned 167-test GUI/model/formula run already completed without skips.

## Final Lead Verification

After the localized formatting correction, the lead's final full gate passed: 2311 passed, 1 skipped in 245.12s (0:04:05). The original one Medium finding is resolved; independent quality re-review has no active High/Medium findings. The normal QA PDF is byte-identical to its pre-fix version, and all later 32 pages match baseline bitmaps. This addendum records coordinated lead evidence rather than a further reviewer-run full suite. See `tmp/snow-reactions/integration.json` and `tmp/snow-reactions/quality-recheck-verification.json`.
