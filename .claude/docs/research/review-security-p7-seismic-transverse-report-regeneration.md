# Security Review: P7 Seismic Transverse Report Regeneration

Reviewed: 2026-10-17. Verdict: no actionable security or data-integrity findings in the approved 0720 change. Critical: 0; High: 0; Medium: 0; Low: 0.

## Scope and Method

Reviewed the approved plan, ownership manifest, current source, and direct diffs against `tmp/seismic-transverse-implementation/baseline`. Product scope: `seismic_frame.py`, the helper extraction in `seismic_longitudinal_calculator.py`, `seismic_transverse_calculator.py`, `seismic_transverse_report.py`, `cli.py`, `frameweb_artifacts.py`, and the documentation-only change in `editor_calculation.py`; also inspected the new calculation/report/CLI tests, relevant existing integration checks, and README changes. Read the unchanged `artifact_publication.py` to trace the new stage through the actual destination validation and rollback implementation.

Preexisting 0710 changes and concurrent rebar work are excluded. The review is of local calculation and report generation; it does not certify structural design results or dependency advisories. No product file was edited, no GUI was opened, and no pytest suite was rerun because source inspection did not establish a concrete suspected defect needing reproduction.

## Findings

None.

## Evidence

- `src/cli.py:63`: destinations are validated against the input path before reading or rendering. Input bytes are read once and hashed at lines 64–70; the same parsed input and same-run 0600/0620 objects reach 0720 at line 95. The 0720 provenance is stamped with that byte hash at line 96.
- `src/seismic_transverse_calculator.py:83`: source stage/schema, JSON-equivalent input snapshots, and supplied SHA syntax/agreement are checked. Numeric readers reject booleans and nonfinite values for consumed quantities; final recursive validation rejects nonfinite results. Fixed actions require matching case identity and loads, and node/member references are checked and remapped. The calculation uses copies and has no filesystem or process access.
- `src/seismic_frame.py:66`: physical geometry and material fields are copied explicitly. Support/restraint metadata is not copied. IDs, coordinates, references, representable micro-member length, and the resulting 0720 graph/physical intervals are validated before publication.
- `src/seismic_transverse_report.py:534`: all four pages are built in memory before the target parent/file is touched. It writes a unique temporary file in the target parent, replaces the target only after successful rendering, and cleans the temporary file on replacement failure. The renderer does not reopen input, saved results, or reference PDFs. Text is drawn as text; the new files contain no command execution or credential material.
- `src/cli.py:112`: 0720 participates in the existing staging and publish transaction. The fixed report-stem registry controls output names; standalone 0720 selects only its PDF/JSON pair. The unchanged publication code rejects duplicate/input-alias/symlink/nonregular destinations, backs up old artifacts before replacing new ones, restores on normal failure, and preserves recovery evidence when restoration fails. The registry makes both 0720 artifacts part of the all-stage manifest and GUI verification.
- `./tests/test_seismic_transverse_cli.py`: inspected failure injection for rendering, JSON writing, PDF/JSON publication, and backup failures, with assertions preserving selected and unselected bytes; inspected all-stage missing/modified-0720 detection and single-input/same-run checks. Calculation tests exercise malformed cases, snapshots, hashes, nonfinite quantities, anchors, and member references. Report tests check failed replacement and oversized output preservation.

## Verification Limits and Known Gate State

The parent reported the shared check stopping before pytest because of the existing uv lock mismatch; the approved plan permits the existing virtual-environment fallback. Parent-provided focused results include 77 core, 90 prior 0710, and 14 report checks passing; the integration layout failure was corrected, its failing case and 15 added checks passed, and the affected reaction CLI module finished with 32 passing. The broad partition finished with 3122 passing, two Tk initialization skips, and one failure in concurrently changed `test_column_rebar_reference` (expected input rebar version 2, actual 1). These are attributed parent results, not independently rerun here; this review does not assert a fully green global gate.

Context loader reported no rule files or STATE. Its exact gaps were `missing: [".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]`, `unreadable: []`, `warnings: ["DESIGN.md is still the uninitialised /init template; run /init to populate it"]`, `design.placeholder: true`, and `progress.entries: 0`. The approved plan and explicit delegated scope supplied the review context.
