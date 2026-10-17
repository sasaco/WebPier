# Seismic longitudinal loads: codebase evidence

Read-only investigation on 2026-10-16 for `seismic-longitudinal-loads-report`. Product source, inputs, and outputs were not edited. Reference-page visual investigation is owned by the parent planning agent; page descriptions below that mention the PDFs use its findings.

Later user decision: add the recommended three-page application report, but **do not display springs** (「バネは表示しない」). This supersedes all short-term spring display recommendations below. The plan selects a narrow validated in-memory0610 adapter and omits springs from the0710 public frame. Read the plan for the final implementation decision.

## Current generation and exact values

- Current `P7橋脚/pre/input.json` SHA256 is `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b`. Saved 0600 and 0610 provenance both carry this same SHA. Values below were read from those saved JSONs, not regenerated as part of planning.
- `P7橋脚/src/reaction_calculator.py:131-136`: earthquake vertical train reaction is line load × whole girder length × 0.5. Current inputs are 32 kN/m and lengths 20/10 m: RB=320, RC=160 kN. `P7橋脚/src/longitudinal_calculator.py:181-183` takes the existing Single transfer; `:368-373` forms side moments before summing. With arms −0.325/+0.675 m the result is N=480 kN, M=4 kN m (−104+108).
- `P7橋脚/src/reaction_calculator.py:245-247` uses whole-girder D1+D2+S2 for earthquake girder force and train force `ROUND(local earthquake reaction × 2 × 0.2, 2)`. `:290-292` adopts the full force for a fixed bearing, half for movable. Current B movable/C fixed therefore gives girder B=6790/C=4740 kN and train B=64/C=64 kN, matching the parent agent's visual reading of physical p8 of 10_線路(耐震).pdf.
- B=6790 is `(5740+660+5740+520+460+460)/2`: the far-end A D2 is 660, whereas local B D2 is 520. The local B transverse weight is 6720. Their 70 kN difference is explained by the asymmetric far-end dead load; it must not be removed by reusing the transverse formula.
- C=4740 is `(1860+260+250)×2`. The 4730 value in the other source is already documented as a 10 kN residual at `P7橋脚/pre/input.json:21`; changing S2 would break the already-correct longitudinal target. The existing permission to tolerate wind M differences does not approve any seismic-number change.
- `P7橋脚/src/longitudinal_calculator.py:377-388` fixes the normalized pier inertia Kh=1.00, computes beam top/bottom and column intensity, and subtracts displaced soil from footing inertia. Current values are pedestal H=M=0, beam top=595.35, beam bottom=297.68, column=297.68 kN/m and footing=1105.65 kN. These match the target page as reported by the parent agent.
- Consequently **no new input is necessary to reproduce the specified p8 numerical values**. The existing train Kh=0.20 and pier/girder unit Kh=1.00 should be explicit result metadata, not an invisible second coefficient or a new guessed input.
- A different formula at `P7橋脚/src/reaction_calculator.py:331` uses 0.30 for transverse train inertia. It is deliberately distinct from longitudinal 0.20; do not substitute 96/48 kN from that path into 0710.

## Existing public/legacy boundaries

- `P7橋脚/src/longitudinal_calculator.py:66-105` defines public 0610 as nonseismic schema 2 with 20 basic families and 16 combinations. It puts former earthquake calculations exclusively under `legacy_audit`.
- `P7橋脚/src/longitudinal_calculator.py:391-418` exposes the useful legacy earthquake values as `vertical.train.earthquake`, horizontal rows 9 and 10, and `inertia`. These are usable evidence for the formulas, but should not become the public 0710 result contract merely by renaming the legacy report.
- `P7橋脚/src/longitudinal_calculator.py:422-427` mixes old nonseismic and earthquake groups into the old case model. The new target p12 case definitions need their own small model/independent fixture; do not use the old entire combination table.
- `P7橋脚/tests/test_longitudinal_canonical_calculator.py:213-225` asserts the public/legacy separation. `P7橋脚/tests/test_longitudinal_example2_report.py:180-213` checks that 0610 has no public earthquake content.
- `.agents/docs/plans/longitudinal-example2-parity.md:24-36` records the owner's correction removing unsolicited load-diagram pages. `:274-300` records the final eight-page public output. New 0710 must not restore those pages or change 0610.
- The transverse parity plan is completed with final restoration/simplification records (`.agents/docs/plans/transverse-example2-parity.md:96-144`, `:279`). Both FrameWeb plans exclude seismic new loads (`p7-longitudinal-frameweb-input.md:54`, `p7-transverse-frameweb-input.md:64`), so a new seismic native export is outside the requested three-page report.

## Frame, springs, and renderer reuse

- `P7橋脚/src/frame_model.py:91-185` builds physical geometry from the current input: cap top, footing top/centroid/bottom and H2/H3/H4 boundaries; it merges only exactly equal coordinates, handles positive H1, and marks footing members rigid. The shared 0610/0620 frame has six nodes/five members for the frozen input. The 0710-only adapter now splits the bottom 0.010 m of H4, following the user's 2026-10-17 correction. The original description of this as a fictitious soil node was incorrect: source 10 p1–5 identify a column-base nonlinear micro element.
- `P7橋脚/src/longitudinal_calculator.py:190-204` assembles the base four-node frame and calls `build_frame_model`. `:73` obtains the canonical longitudinal springs.
- `P7橋脚/src/foundation_springs.py:27-58` copies 0500 canonical Kv/Ks and directional Kr without Single conversion, and records source path/unit/precision. Current short-term longitudinal Kv=25,576,488 kN/m, Ks=8,525,475 kN/m, Kr=104,437,326 kN m/rad. Long-term values are 12,788,244 / 4,262,769 / 52,218,663.
- `P7橋脚/src/longitudinal_design_conditions.py:80-91` reads existing beam/column/footing concrete strengths. `:94-136` applies materials without changing geometry; H2/H3 use beam, H4 uses column, H1 inherits column, rigid members keep null material refs. Current fck=27 and Ec=26,500,000 kN/m² follow the existing RcDan interpolation.
- `P7橋脚/src/longitudinal_example2_report.py:29-87` provides the current Japanese table/text style; `:90-104` draws a physical frame through shared outline/graph helpers. `:338-356` demonstrates the expected snapshot-only renderer, A4 page size, input SHA footer, and continuous numbering. Avoid calling `_model` unchanged because it says nonseismic and shows both terms.
- Current model sheet basis after user corrections: current physical geometry plus the column-base 0.010 m split; no spring symbols, values, or support model. The nonlinear constitutive law, conversion of other members to rigid zones, response analysis, and member checks remain outside scope.

## App integration and concrete likely files

New files, names to confirm in the plan:

- `P7橋脚/src/seismic_longitudinal_calculator.py`: public stage 0710 result, current-input/upstream validation, explicit normalized/load-specific Kh, target p12 cases and source metadata.
- `P7橋脚/src/seismic_longitudinal_report.py`: exactly three pages (seismic model, loads corresponding to physical p8, cases corresponding to physical p12), consuming only the result.
- `P7橋脚/tests/fixtures/seismic_longitudinal_example2.json`: independently transcribed source values/case semantics, including zero entries and coefficients.
- `P7橋脚/tests/test_seismic_longitudinal_calculator.py`, `test_seismic_longitudinal_report.py`, `test_seismic_longitudinal_cli.py`.
- `P7橋脚/output/0710_線路方向荷重.pdf` plus its traceable `.json` partner.

Modified files:

- `P7橋脚/src/cli.py:46-98`: add stage choice/description, required 0500/0600 calculation dependency, 0710 computation and renderer. Read input once, give all results the same SHA. `:100-140` already stages/publishes a selected report pair safely.
- `P7橋脚/src/frameweb_artifacts.py:33-39`: add 0710 directly to `REPORT_STEMS`, **not** to `FRAMEWEB_STAGES`. `:64-72` derives report artifacts and native exports separately. Adding only a PDF requires no seismic native schema.
- `P7橋脚/src/editor_calculation.py:36-41`: include 0710 in `OUTPUT_STEMS` (prefer the shared report registry). `:124-150` verifies report pairs and an ALL_STAGES publication manifest; comments/counts and tests must reflect five report pairs plus four existing native/sidecar files.
- `P7橋脚/src/editor_gui.py:512`: change the four-stage user label. The catalogue uses `OUTPUT_STEMS`; the PDF viewer itself is stage-independent.
- `P7橋脚/README.md:3-57`, `:94-100`, `:158-164`: document 0710, five stages, 14 all artifacts / 12 manifest entries + two sidecars, and the three-page scope.
- Existing all-stage CLI/editor/publication tests with four-stage or twelve-artifact assumptions: `tests/test_report_cli.py`, `test_reaction_cli.py`, `test_longitudinal_canonical_cli.py`, `test_transverse_cli.py`, `test_frameweb_cli.py`, `test_frameweb_publication.py`, `test_editor_calculation.py`, `test_editor_gui.py`, `test_pdf_preview_dialog.py` as affected by exact assertions. Do not change the legacy numeric oracle fixtures.

Reuse existing foundation/material/frame/rounding/drawing/publication helpers. A small shared builder extracted from the existing longitudinal frame/load preparation is preferable to consuming saved 0610 JSON. If a full canonical 0610 calculation is used internally, document the extra validation/dependency and avoid calculating it twice in all; it would otherwise make seismic generation depend on unrelated nonseismic case resolution. The final design should explicitly choose this seam before implementation.

Minimal suggested result contract: `schema_version`, `stage: "0710"`, `input` snapshot, `design_conditions`, `frame` (current physical frame plus selected short-term support metadata), `seismic_conditions` (girder/pier Kh=1 and train Kh=0.2 with their distinct meanings), `vertical` (fixed, additional, S2, earthquake train), `horizontal` (girder/train per side and total), `inertia` (pedestal, beam top/bottom, column, footing and formula factors), `basic_cases`/`combinations`/other p12 definitions only when present in the specified source, `provenance` (source document + physical page, dependency paths, precision, input SHA), `units`, and `warnings`. A pure adapter over an in-memory canonical 0610 result may take `frame`, `vertical.fixed/additional/snow.s2`, and explicitly named earthquake fields from `legacy_audit`; it must validate those fields and build new p12 cases, never copy `legacy_audit.combinations`. This is a low-risk transitional alternative to extraction if the plan accepts its extra calculation dependency.

## Meaningful verification and residual decisions

- Exact source/current fixture: train RB/RC=320/160, N/M=480/4; girder H=6790/4740; train H=64/64; self inertia=595.35/297.68/297.68/1105.65. Verify every p12 coefficient/reference independently from the PDFs, not from the renderer.
- Change seismic line load or girder lengths: vertical N/M and train H must move by their different formulas without changing dead inertia.
- Swap fixed/movable bearings: check full/half whole-girder inertia and full/half train inertia. Change only far-end A D2/S2 to detect accidental use of local B weight. Vary S10/S30 without affecting earthquake forces.
- Change B/C support arms, asymmetric geometry, H1 positive, unit weights/displaced soil, and footing dimensions: verify moments, physical nodes, pedestal visibility and unit-Kh inertia. Zero loads remain valid; nonfinite/missing required upstream paths fail clearly.
- Directional springs: reuse asymmetric-footing tests in `tests/test_foundation_springs.py` so 0710 cannot accidentally use transverse Kr or old Single macro springs. Missing normal springs must not fall back silently.
- Renderer: exactly three A4 pages, required section order and text, all numeric and coefficient cells, input SHA, no clipping/overlap, PDF rendered to PNG and visually inspected. A renderer must not reread `input.json` or the source PDF at runtime.
- CLI 0710 alone vs all: identical 0710 result for same bytes; 0500/0600 calculated only once; 0710 standalone updates only its PDF/JSON; failures restore both old files and preserve other artifacts. Verify all/GUI includes 0710 in the shared manifest and preview sequence.
- Source documents carry different seismic values/model purposes. The specified p8 matches the current longitudinal path; source 07 transverse values should be described, not “corrected” into 0710. The page12 case meanings and choice of short-term elastic reference springs remain user-facing domain decisions for the parent grill session.

## Workspace constraints

At investigation, `git status --short` showed pre-existing changes only in `P7橋脚/pyproject.toml` and `P7橋脚/uv.lock` (parent identifies local GridLayoutPdf dependency work). Preserve them. No project AGENTS/context/shared state files were found by the parent context-loader, so no unrelated FrameWeb-wide rules were assumed. Runtime source provenance remains Excel/PDF independent (`P7橋脚/README.md:3`).
