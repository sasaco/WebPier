# Security and Data-Integrity Review: seismic-longitudinal-loads-report

Date: 2026-10-16

## Result

No actionable security or data-integrity findings in the reviewed 0710 change. Critical: 0; High: 0; Medium: 0; Low: 0. This is a scoped source review, not a claim that the full repository gate has passed. The root-run full gate was pending when this review completed; final acceptance remains conditional on its result.

## Review Scope

Reviewed the approved plan, `.agents/logs/review-diff-seismic-longitudinal-loads-report.patch`, both new seismic modules, and the 0710 changes in `cli.py`, `editor_calculation.py`, `editor_gui.py`, `frameweb_artifacts.py`, README, and relevant validation/publication tests. Read the existing `artifact_publication.py` implementation to check the integration boundary.

Excluded the pre-existing `pyproject.toml` / `uv.lock` changes and concurrent FrameWeb refactoring (`frameweb_common.py`, `frameweb_export.py`, `frameweb_transverse_cases.py`, and helper extraction in `frameweb_artifacts.py`). The reviewed registry change in the latter is the addition of 0710 to `REPORT_STEMS`, with `FRAMEWEB_STAGES` unchanged.

## Findings

None.

## Evidence

- `seismic_longitudinal_calculator.py:29`–`:94`, `:104`, `:170`, `:231`: required fields, numeric types/finiteness, integer schema versions, unique case identities and expected Kh labels, node/member references, and optional input-SHA shape are validated. Derived numeric values receive a final finite-value check. The frame is constructed from an explicit physical-data allowlist; input and case loads are detached copies. No saved 0610 JSON or reference PDF is read.
- `cli.py:62`, `:90`, `:106`, `:151`: the input is read once and hashed; 0710 consumes the same in-memory 0610 result. Generated output paths come from the fixed report registry. The new pair uses the existing destination validation, staging, backup, rollback, and publication path. Calculations finish before report generation starts. The new stage creates no FrameWeb artifact.
- `seismic_longitudinal_report.py:266`: rendering completes in memory before its destination is written, so a layout failure cannot leave a partially rendered PDF at the requested destination. Under CLI execution, the destination is a staging file and prior published files remain protected by the existing transaction mechanism.
- `editor_calculation.py:30`, `:113` and the shared report registry: 0710 participates in the GUI's PDF readability, input SHA, regular-file snapshot, complete-manifest and publication-generation checks. Adding the stage does not bypass these checks.
- Reviewed test cases cover malformed/missing/non-finite values, duplicate or mislabeled seismic cases, source/result nonmutation, exclusion of support metadata and old combinations, source-free rendering, rendering/JSON-write/publication failures for both empty and populated destinations, unrelated-file preservation, and missing/modified 0710 PDF/JSON manifest rejection.
- No new network client, dynamic code execution, subprocess invocation, authentication surface, credential, or dependency was introduced by the scoped change. The existing GUI subprocess path continues to use an argument list and `shell=False`.

## Validation Boundary

Root reported calculator 75, report 9, dedicated CLI 24, and existing CLI/GUI-count regression 42 targeted tests passing, plus real CLI standalone/all parity, existing four-report parity, 155 protected-file SHA comparisons, and visual PDF checks. Those results were supplied by root; this reviewer inspected code and tests and did not rerun the full suite or touch Tk. Full-suite outcome and final production publication remain root responsibilities.

The missing shared rules/STATE/DESIGN/PROGRESS artifacts were already documented and handled in the approved plan. This review used the plan, README, actual source, and tests; no unrelated project's rules were assumed.
