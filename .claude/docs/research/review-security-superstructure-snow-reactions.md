# Security Review: Superstructure Snow Reactions

## Summary

PASS. No Critical, High, Medium, or Low security/data-integrity findings were identified in the approved snow-input and two-table feature.

The review used `tmp/snow-reactions/preservation.json` as the scope manifest and `.agents/logs/review-snow-feature.patch` as the baseline-relative feature diff. Concurrent frame/rebar work in the global review patch was excluded.

## Review Scope

- Core input and calculation boundaries: `src/reaction_inputs.py`, `reaction_weights.py`, and `reaction_calculator.py`, together with their scoped tests.
- Virtual missing inputs, type preservation, readonly totals, and saving: `src/editor_model.py`, `editor_gui.py`, and `editor_forms.py`, with the snow-specific model/GUI/formula tests and field-path fixture changes.
- Report data isolation: `src/reaction_report_snow.py`, `reaction_report_pagination.py`, and report tests.
- Initial data/documentation and integration: `./pre/input.json`, `README.md`, and the snow-specific CLI/0610/0620 regression tests listed in the scope manifest.
- New dependencies, dynamic execution, file destinations, secrets, and outbound calls in the scoped additions.

## Findings

None. Severity totals: Critical 0, High 0, Medium 0, Low 0.

## Evidence

- `reaction_inputs.py:168` rejects booleans, strings, container values, nonfinite numbers, and integer-to-float overflow. Snow B/C details reuse this validation with `null_zero=True` at `reaction_inputs.py:328`; negative details remain invalid. The parser calls the existing required bearing and end-parent validation before the new snow readers (`reaction_inputs.py:363`). Coverage includes malformed parents and all three snow keys in `tests/test_reaction_inputs.py:256`, `:270`, `:279`, and `:301`.
- Missing/null A/D values remain `None` in the typed input (`reaction_inputs.py:340`). The fallback checks `value is None`, preserving explicit zero and signed direct inputs (`reaction_weights.py:86`). B/C saved totals are not read; only the ten bearing details are aggregated. Both detail and girder sum overflow raise a path-specific `InputError` (`reaction_weights.py:80`, `:97`), covered by `tests/test_reaction_weights.py:169`, `:225`, and `:236`.
- The missing-field exception is limited to the existing A/D manual-load allowlist and recognized B/C snow-detail paths (`editor_model.py:21`, `:29`). Booleans are excluded as list indices. Actual detail cells are generated from existing bearing rows; index/type failures remain readonly in `_grid_data` (`editor_gui.py:676`). New B/C paths do not create missing lists or arbitrary hierarchy. Unknown paths are explicitly rejected by `tests/test_editor_model.py:339`.
- Opening legacy files binds absent snow fields as virtual blanks without assigning values (`editor_gui.py:679`). Only changed fields are parsed and applied after all pending fields parse successfully (`editor_gui.py:281`). The existing save implementation still copies the document, checks fingerprints, creates a backup, fsyncs the temporary file, and replaces the target (`editor_model.py:312`); the snow patch does not modify that machinery. No-op preservation, single-key materialization, unknown-extension retention, readonly B/C totals, paste/delete/undo/redo, signed A/D values, and invalid-edit atomicity are exercised at `tests/test_editor_gui.py:815`, `:844`, `:858`, and `:915`.
- Snow is calculated independently and returned only as `snow_loads` plus typed input/provenance (`reaction_calculator.py:303`, `:334`, `:337`). Existing dead-load and downstream numerical paths still consume the original dead-load objects. `tests/test_reaction_calculator.py:141` compares all pre-existing result boundaries; `tests/test_longitudinal_calculator.py:75` and `tests/test_transverse_calculator.py:80` compare entire downstream results after excluding only the changed snow input snapshot.
- The dedicated renderer reads the calculated `snow_loads` dictionary and deep-copies source table layout before extending it (`reaction_report_snow.py:34`, `:123`). It does not reread input, mutate the shared layout cache, or invent workbook cell addresses. Repeated-render isolation is covered at `tests/test_reaction_report_snow.py:145`.
- Invalid snow is rejected before rendering/publication and existing output bytes are retained in `tests/test_reaction_cli.py:283`.
- Scoped additions introduce no subprocess/shell/eval/exec path, outbound communication, credential handling, or dependency changes. The preservation artifact records 342 existing input leaves preserved, with 66 new snow inputs and four metadata leaves. An earlier verification recorded all 31 protected files and eight production outputs unchanged. The final artifact records 29 protected files and six production outputs unchanged, with two concurrent external updates to the 0610/0620 output PDFs preserved. No snow agent published any of the eight production output files; snow report/CLI verification used temporary destinations. Protected runtime code, oracle data, and layout source remain unchanged.

## Verification and Limits

Static review included the scoped diff, current source at the affected boundaries, and the new regression assertions. The existing integration artifact reports `overall: pass`; its referenced log records 2308 passed and one Tk initialization skip. The lead reports a separate 167-test GUI/model run with no skips and is handling replay of the exact skipped case. These execution results were inspected/reported evidence, not tests rerun by this reviewer.

No independent full-suite/Tk execution or new reproducer was run: inspection found no concrete uncertainty requiring one, and duplication was excluded by the assigned review scope. PDF visual QA and live GUI usability remain the lead/other reviewers' verification responsibility. Arbitrary invalid direct construction of typed dataclasses and pre-existing save races were not broadened into this feature review.

The known missing shared context (`.agents/rules`, `.agents/STATE.md`, `PROGRESS.md`, and `.agents/docs/DESIGN.md`) was reconfirmed and left unchanged as instructed; no project initialization was performed.

## Final Lead Verification

After the localized formatting correction, the lead's final full gate passed: 2311 passed, 1 skipped in 245.12s (0:04:05). The original one Medium finding is resolved; independent quality re-review has no active High/Medium findings. The normal QA PDF is byte-identical to its pre-fix version, and all later 32 pages match baseline bitmaps. This addendum records coordinated lead evidence rather than a further reviewer-run full suite. See `tmp/snow-reactions/integration.json` and `tmp/snow-reactions/quality-recheck-verification.json`.
