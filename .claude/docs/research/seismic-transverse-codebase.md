# Seismic Transverse Codebase Investigation

Date: 2026-10-17. Investigation only; no application, input, or report files changed.

This document supplements the handoff and the independent PDF investigation. File references below are relative to the repository root. The `P7橋脚` application, not the absent `FrameWeb` project, is the implementation workspace.

## Current contract and reusable implementation

- `CONTEXT.md:11` defines the existing longitudinal earthquake action scope; `CONTEXT.md:23` defines the physical frame separately from support conditions; `CONTEXT.md:27` defines the 0.010 m column-base split. The root updated this glossary during investigation to add the transverse scope (`:15`) and generalize the micro-member term; the initial version had been 0710-specific.
- `P7橋脚/README.md:64` describes standalone 0710 regeneration from an in-memory dependency chain and no reference-PDF dependency. `.agents/docs/plans/seismic-longitudinal-loads-report.md:193` supersedes the earlier enlarged-detail/old-ID proposal: no enlarged detail, nodes and members numbered top down, preserve physical dimensions.
- `P7橋脚/src/seismic_longitudinal_calculator.py:106` allowlists physical frame/material fields and deliberately excludes springs, support IDs and analysis settings. Lines 172–198 renumber nodes/members and references. Lines 200–242 split the bottom of H4 by 0.010 m, require H4 > 0.010 m, reject coordinate collapse or nonvertical H4, and mark the added element's source classification as nonlinear without constitutive parameters. Lines 306–388 create a detached snapshot with 8 cases, one combination, units and provenance.
- 0710 cannot be copied mechanically: `seismic_longitudinal_calculator.py:311` requires a full schema-1 `0610.legacy_audit`; lines 245–258 select its directional horizontal cases, and lines 332–336 read its inertia. In contrast, `transverse_calculator.py:59` supplies only legacy entrypoint metadata in public schema-2 `0620.legacy_audit`.
- `frame_model.py:96` builds a role-based physical frame from geometry, merging exact coincident coordinates; lines 121–144 compute the levels and optional H1 geometry; lines 166–199 create members and load anchors. `transverse_calculator.py:72` selects transverse dimensions/Iz and materials; lines 88–92 assign beam material to H2/H3 and column material elsewhere. All 0720 role/anchor references must be remapped after the new upper level and micro-member numbering.
- Shared drawing is suitable: `frame_outline.py:31` accepts direction `w`; `frame_outline.py:188` fits the union of outline and node extents, so an upper geometric level can extend above the concrete outline. `frame_model_report.py:42` draws member geometry, lines 52 and 62 draw node/member labels. `seismic_longitudinal_report.py:113` has the micro-member dimension policy; lines 131–209 avoid near-coincident labels without an enlarged diagram.
- `seismic_longitudinal_report.py:31` derives displayed factor precision until the printed arithmetic reproduces the printed rounded result. Lines 61–73 reject unreadable/out-of-bounds text. Lines 431–453 render to a buffer before writing an invariant PDF, so layout failure does not partially replace the output.

## Existing physical transverse loads and legacy boundary

- Public `calculate_transverse(inputs, foundation, reactions, design_conditions=...)` builds canonical nonseismic schema 2 (`transverse_calculator.py:24`), with `actions`, physical frame, cases and provenance (`:44`). It does not execute the old oracle. It therefore makes a suitable source for 0720's shared D1/D2/Wp/Sw2 and frame, not for missing seismic fields.
- `transverse_actions.py:137` builds D1/D2 as separate cap and footing-centroid point loads plus column distributed loads. D1 subtracts the equivalent-column overlap over H2+H3 (`:152–163`); preserve that policy. Buoyancy has signed N at footing centroid (`:173–180`). `:183–196` builds the independently entered 2/10/30-year snow cases.
- `transverse_actions.py:21` maps `down` to L1 and `up` to L2. `:43` rejects a missing bearing position if its load is nonzero; `:51–62` retain raw force, rounded force, each bearing's own arm and row-rounded moment. `:69–88` preserve signed rates and distribute only once. The nonseismic raw moving-train reaction is not the earthquake reaction, so 0720 needs its own earthquake table builder rather than calling `train_action` unchanged.
- Old `calculate_transverse_legacy` is an audit entrypoint (`transverse_calculator.py:96`). Its selection at `:117–147` can fall back to D2 values as rates. Its earthquake rows at `:303–333` compute `source_M` from *undistributed* upstream force times arm and expose a mixed force/arm/moment rectangular sum. Its old C-side arms are inherited from B-side positions (`:287–294`). These are documented compatibility artifacts, not suitable 0720 physical values.
- Old inertia equations at `transverse_calculator.py:349–362` are useful equation evidence only. The new result should calculate those quantities from current input/0600 weights directly and must not execute the legacy selection to obtain them.

## Source of each 0720 quantity

Recommended API:

```python
calculate_seismic_transverse(
    inputs: ReactionInput,
    reactions: Mapping[str, Any],     # same-run stage 0600
    transverse: Mapping[str, Any],   # same-run canonical schema 2 stage 0620
) -> dict[str, Any]
```

The caller owns the single input read and dependency computation. Validate stage/schema, required finite fields, any supplied SHA equality and agreement between supplied inputs and source snapshots; output must be detached. Use no saved artifact, PDF, 0610, 0710 or legacy calculation dependency.

1. **D1/D2/Wp/Sw2:** copy only `0620.actions.dead_fixed`, `dead_additional`, `buoyancy_normal`, `snow_2_year`, then rebind physical node and member references to the 0720 frame. Keep the column distributed load across the same H2+H3+H4 length, including the new micro-member, without loading the upper geometric extension.
2. **Earthquake vertical train:** `reaction_calculator.py:131–136` gives each support reaction as `earthquake_load * whole_girder_length / 2`. For each of down/L1 and up/L2, multiply that one support reaction by the current signed bearing rate exactly once, using the same side's bearing arm. Mirror canonical table rounding (raw N summed and row-rounded M summed), and keep both cases independently even if totals happen to coincide.
3. **EQ1:** `reaction_calculator.py:299–301` computes current side H from local D1+D2+S2 and its moment from H*hs. `:330–343` retains this as transverse case 7. Use the full-precision `0600.transverse` row with its label/ID validated, rather than the Single transfer array.
4. **EQL:** `reaction_calculator.py:331–344` computes H = earthquake reaction * 0.30, rounded to 2 decimals, with height `span.h1 + span.h2 + span.h3 + train.height_seismic`. This 0.30 is already applied. Use transverse case 8 full-precision H/height/M and record the convention explicitly; do not multiply a second time.
5. **EQ2/self inertia:** calculate beam top/bottom and column line intensity from b*w*unit_weight_body*Kh (Kh=1), with the same 2-decimal rounding as 0710 (`seismic_longitudinal_calculator.py:261–301`). Obtain pedestal N/hG and footing N from `0600.macro_handoff_single` (`reaction_calculator.py:364–379`), preserving the established weight-transfer precision. Footing H is `W/gamma_footing*(gamma_footing-gamma_displaced)*Kh`; do not replace a tapered-footing volume with a rectangle. Keep formulas/factors/raw values/rounding and displayed aliases separate.
6. **Application level:** the PDF investigation reports EQ1/EQL at `cap_top`, not at the extra upper geometric node. Therefore retain full moments about cap_top and assign no extra H/M to the upper node. Never shift the same moment a second time.
7. **Cases:** 9 basic cases, 5 down and 6 up per reference combination page, EQ1/EQL/EQ2 to the right, EQL limited incremental, Kh=0.30. Combination 1 selects 1+2+3+4+5+7+8+9; coefficients should explicitly hold zero for unselected case 6, and the renderer should omit zero terms. The user confirmed the page-13 interpretation (5 down / 6 up) on 2026-10-17 during root planning; retain the contradictory preceding diagram labels as a source discrepancy. The code's existing down=L1/up=L2 mapping is unambiguous.

## Dimensions, upper level, and current-input arithmetic

`reaction_inputs.py:29–62` and `:66–81` distinguish lower-structure H1–H6 from each span's h1–h4 and equivalent gravity height hs. `:241–265` reads these existing fields; `:284–307` reads the earthquake line load and train gravity height. No additional input field is needed for the source upper geometric level if it is defined as h1+h2.

Current `pre/input.json:393–397` gives B h1=0.15, h2=2.60; `:416–420` gives C h1=0.10, h2=2.65. Both sum to 2.750 m. hs is separately 2.9520833333333334 / 3.0662447257383967 (`:398`, `:421`), and the reason for those equivalent heights is documented at `pre/input.json:21`. It must not be substituted for the 2.750 geometric extension. Lower H1–H6 are 0/2.0/0.7/4.9/0/2.7 (`pre/input.json:496–501`).

Recommended deterministic extension rule for review: retain an upper semantic role for each side at cap_top + (h1+h2), merge exact equal coordinates, alias a zero height to cap_top, and connect the positive distinct levels as report-only geometric members. This handles equal, unequal and zero heights without guessing a maximum/average, hiding a side, or adding an input. Preserve every existing concrete level and all applied loads at their original roles. The current input consequently has eight nodes, seven members and total geometric height 13.050 m; the micro-member is element 5 between nodes 5 and 6 after top-down numbering. Unequal upper levels naturally add another node and dimension. These members define neither a support model nor calculated nonlinear response.

Read-only execution with `P7橋脚/.venv/Scripts/python.exe -X utf8` on 2026-10-17 produced input SHA256 `0a17f5301371fead6383eb00d315f6984bfd21c8580fe2e861a12d088e67f408`:

| Quantity | Current result |
|---|---:|
| cap_top / footing_top / footing centroid / bottom y | 10.3 / 2.7 / 1.350000023841858 / 0 m |
| Earthquake RB / RC | 320 / 160 kN |
| Down train total N / M | 480.00 kN / -1028.62 kN m |
| Up train total N / M | 480.00 kN / +1028.62 kN m |
| EQ1 B H / M | 6720 / 19838 kN, kN m |
| EQ1 C H / M | 2370 / 7267 kN, kN m |
| EQ1 total H / M | 9090 / 27105 kN, kN m |
| EQL B H / C H / height | 96 / 48 kN / 5.35 m |
| EQL total H / M | 144 / 770.40 kN, kN m |
| D1 cap N / footing N / line qN | 8299.52 / 4167.4501953125 kN / 297.68 kN/m |
| D2 cap N / soil N | 780 / 1830.5999755859375 kN |
| Wp signed N / Sw2 N | -1701 / 710 kN |

These are investigation observations, not an independent reference fixture or completed verification. In particular current EQ1 H9090 differs from source H9080 because of the existing C-side +10 kN snow residual documented in input comments; do not change the user's input to force agreement. The train-table arithmetic above independently follows the proposed canonical rounding policy.

## Concrete shared-helper scope

Recommend a small pure `src/seismic_frame.py` extracted from the 0710 physical allowlist, H4 split and top-down renumbering. Give it explicit target/source stage labels so error messages remain meaningful. Accept optional semantic upper levels only for 0720, applied before final numbering. Leave existing 0710 frame output/metadata/error policy unchanged by default and prove that with its current regression suite.

Keep 0720 report-specific heading, right arrows, four-page layout, upper-level dimensions, train table, and 9-case table in `seismic_transverse_report.py`. Reuse `_Page`/font setup, physical outline fitting and graph drawing. Avoid broad refactoring of the 0710 report. Its micro-label logic and precision-sensitive formula display can be extracted to a neutral rendering helper only if direct duplication would otherwise be substantial; the plan should declare that file explicitly if chosen.

## Integration and exact change surface

New files recommended:

- `P7橋脚/src/seismic_frame.py`: pure physical extraction/split/numbering helper, optional transverse upper levels.
- `P7橋脚/src/seismic_transverse_calculator.py`: 0720 snapshot, current-input action equations, 9 basic cases and selected combination.
- `P7橋脚/src/seismic_transverse_report.py`: four-page ReportLab renderer with no reference-file reads.
- `P7橋脚/tests/test_seismic_transverse_calculator.py`, `test_seismic_transverse_report.py`, `test_seismic_transverse_cli.py`.
- `P7橋脚/tests/fixtures/seismic_transverse_example2.json`: independently transcribed reference and conflicts; never export constants from product code to make this fixture.
- `P7橋脚/tests/fixtures/seismic_transverse_current_input.json` plus a frozen input fixture if using the existing 0710 test pattern: distinguish reference numbers from reproducible current-input expectations and SHA.

Modified files recommended:

- `P7橋脚/src/seismic_longitudinal_calculator.py`: delegate only the extracted physical-frame helper; preserve existing result contract.
- `P7橋脚/src/cli.py`: add 0720 import/calculation/renderer, compute 0500→0600→0620 once as needed, with no 0610 dependency for standalone 0720; catch 0720 renderer `ValueError` as `InputError`. Existing selection/dependency points are lines 47–54, 70–104 and 112–116.
- `P7橋脚/src/frameweb_artifacts.py:37–40`: add report stem `0720_線路直角方向荷重` to the central report registry; leave `FRAMEWEB_STAGES` at 0610/0620. `publication_paths` at lines 62–75 then registers all job files automatically.
- `P7橋脚/src/editor_calculation.py:115`: update the hard-coded fourteen-artifact docstring. Runtime behavior already consumes `ALL_STAGES` and `OUTPUT_STEMS` (`:27–30`, `:123–139`, `:172`, `:265`).
- `P7橋脚/tests/test_seismic_longitudinal_cli.py:18–25`: all-stage quick-render fixture must include new renderer; count at line 91 becomes 16 artifacts.
- `P7橋脚/tests/test_frameweb_publication.py:42` and `:101`: expected stage tuples become six stages; add standalone 0720/no-post assertions and full-manifest coverage.
- `P7橋脚/tests/test_editor_calculation.py:149`, `:464`: verified artifact count becomes 16; last PDF at `:441` becomes 0720; add missing/modified 0720 validation analogous to `:303`.
- `P7橋脚/tests/test_report_cli.py:154–155`: add the new stage/stem to fixed output expectations.
- `P7橋脚/README.md` and `CONTEXT.md`: six stages, 0720 scope, dependency/precision/geometry/case policies, updated total counts and glossary.

`editor_gui.py` should not need a product-code modification: count and stage labels derive from `OUTPUT_STEMS` (`:476`, `:512–513`, `:725`), and PDF catalog ordering/recognition use the same registry (`:589–604`). Verify this instead of gratuitously touching GUI code. Similarly, `artifact_publication.py` is generic; no publication-engine edit is expected. All now becomes 12 report files + 2 native files + 2 sidecars = 16 files; the shared manifest has 14 non-sidecar entries. A standalone 0720 run publishes exactly the PDF/JSON pair and touches neither other reports nor `post`.

## Meaningful verification and invariants

Existing useful tests: `test_seismic_longitudinal_calculator.py:147` detached/no-support contract, `:366` split-without-growth, `:401` array-order-independent numbering, `:418–465` invalid/precision edge cases; `test_seismic_longitudinal_report.py:142` snapshot-only render, `:162` changed dimensions, `:236` printed-factor equality, `:301` atomic layout failure; `test_seismic_longitudinal_cli.py:45` shared upstream once, `:94` standalone/all equality, `:108` unselected preservation, `:125` failure restoration, `:170` manifest tamper detection. `test_transverse_actions.py:57` uses C's own arm, `:88` signed zero-rate sums, `:100` missing loaded positions, `:134` factor-once and alternatives.

0720 gaps to cover before publication:

- Independent PDF expectations and current-input expectations separated, especially H9080 versus current H9090, upper2.750 versus hs, and the case5/6 label conflict.
- Non-symmetric B/C arms and rates, negative and zero rates, zero earthquake line load, changed span lengths and earthquake line load; no rate normalization or double distribution; both train tracks preserved and only case5 selected.
- Change hs independently of h1+h2: EQ1 M changes, upper node does not. Change h1+h2: upper geometry and EQL lever follow current inputs, EQ1 moment follows hs; no double moment transfer. Equal/unequal/zero upper levels and nonzero/eccentric H1 must preserve connectivity and role references.
- Micro-member preserves total H4 and lower-structure height; top-down IDs, endpoint roles, actions' node IDs, line-load member lists and dimension labels all agree. Spring/support/solver metadata stays excluded.
- Raw versus Single source precision is explicit; no second Kh0.30 factor; finite validation and displayed arithmetic agree for nonround inputs. Keep footing displaced-soil subtraction and nonrectangular volume policy.
- Four pages exactly, reference sequence/layout, no spring symbols/tables/expanded detail, no missing up/down rows, right arrows and selected cases. Render all final pages to images and compare with source page layout, not merely text bounds. If a legitimate large bearing set cannot fit four readable pages, fail explicitly rather than silently omit rows or unreadably shrink them; document any supported limit.
- New-only standalone output with reference PDFs inaccessible; no saved0620 required; standalone/all identical 0720; dependencies each computed once; six-stage GUI recognizes and validates 0720; failure rollback and manifest tampering protect both newly created and pre-existing artifacts.
- Run targeted new calculator/report/CLI tests plus affected 0710, transverse, registry, editor and publication regression modules. Do not rewrite existing input, unrelated lockfiles, old independent oracle fixtures or other published reports.

## Remaining decisions for the root's plan

- Four-page scope was approved by the user during this investigation (root message).
- The user confirmed the PDF page-13 down/up interpretation, case5 down and case6 up, during planning on 2026-10-17. Preserve the other source page's disagreement in reference provenance.
- Upper-level exact-coordinate merging and using full-precision0600 EQ rows are engineering recommendations for plan validation, not previously approved design facts.
- The complete implementation plan is still awaiting its required user approval; the focused four-page and case-label decisions do not substitute for that gate. The requested 0720 standalone final publication is within the task's desired scope; any all-stage test run should use an isolated temporary output. Formal publication should regenerate from the final current input and verify the actual published pair and untouched other outputs.
