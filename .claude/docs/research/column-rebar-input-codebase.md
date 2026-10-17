# Column Rebar Input: Codebase Investigation

Date: 2026-10-17. Read-only investigation by delegated analysis collaborator; no product edits or test execution.

## Existing model and UI

- `P7橋脚/pier_design/rebar_model.py:3,292,321`: reinforcement units are mm, column X=transverse, Y=longitudinal, origin at upper left; geometry is W6 x B6 converted from m. `tests/test_rebar_model.py:3,6` explicitly defines one physical arrangement, with directional tables derived from it.
- `P7橋脚/pre/input.json:479,490,665-699`: current section 4500 x 2700; D32 29/face, D19 11/face, pure cover 70, automatic center, no hoops.
- `rebar_model.py:348-389,450`: automatic center requires enclosing hoop diameter. Missing hoop input leaves center unresolved and bars ungenerated. Automatic center formula is pure cover + hoop diameter + main diameter / 2.
- `rebar_model.py:458-466`: existing column basic input uses the same center cover for face depth and both ends of the row, then evenly spaces bars. This cannot express the reference 192-mm end gaps and 150-mm interior gaps or independently chosen 350-mm first side bar.
- `rebar_model.py:407,471`: shared corners require same location, diameter and material, from different directions. Other overlaps are rejected.
- `rebar_model.py:488`; `rebar_ui.py:440,736`: directional tables group physical bars by Y (longitudinal) or X (transverse), diameter and material, read-only.
- `rebar_ui.py:18,278,399`: current main table prominently shows face-direction, diameter and count/face; layer, material, center cover, clear gap and endpoint inclusion are on selected-row detail controls.
- `rebar_ui.py:291,784`; `rebar_model.py:843`: basic rows and manual XY coexist; position_mode chooses the active source; copying basic positions does not switch the active source.
- `rebar_model.py:129,254`: hoops support set counts and effective legs; automatic leg count is twice set count; explicit legs are supported.

## Preservation boundaries

- `rebar_model.py:164,179,268`: missing/null/zero and unknown fields are preserved. Viewing alone must not materialize virtual defaults into the saved document.
- `rebar_model.py:206,825`: incomplete input may be saved; impossible complete geometry must be rejected.
- `editor_gui.py:339`: editor values and reinforcement drafts are merged into a candidate document, fully validated, then applied atomically. `rebar_model.py:865` validates non-visible members too.
- `P7橋脚/README.md:5,149`: section resistance/seismic verification and main rebar solver integration are not implemented. Input usability work must not claim to provide them.
- `longitudinal_design_conditions.py:80`: concrete_strength_mpa participates in calculation material conditions; schema changes must preserve it.

## Change candidates

- `rebar_ui.py` plus a focused new `column_rebar_ui.py`: column-specific basic/detail/review workflow, preserving beam and footing UI.
- `rebar_model.py` plus a focused new `column_rebar.py`: physical generation, explicit row-position input, validation and compatibility adapters.
- `editor_gui.py`: integration with existing atomic save path only if needed.
- `tests/test_rebar_model.py`, `tests/test_rebar_ui.py`, new column-focused tests and independent reference fixture.
- `P7橋脚/README.md`, root `CONTEXT.md`.
- `P7橋脚/pre/input.json`: only if user explicitly includes reference-data correction; never an implicit migration.

## Tests and gaps

- `test_rebar_model.py:322`: shared corners and equal totals across directional tables.
- `test_rebar_model.py:388,417,448`: overlaps, missing/null preservation, unresolved automatic centers.
- `test_rebar_ui.py:216,237`: active-cell commit and atomic failure; `:573` basic/manual roundtrip; `:784` read-only directional tables and active-source switching.
- `test_rebar_model.py:21`, `test_rebar_ui.py:30`: existing cases deliberately use synthetic dimensions; no independent reference oracle for the 76 physical bars plus both directional tables.
- Add unequal end spacing, explicit 102-mm D19 center, old/new format transitions, unchanged read/save, regeneration after manual corrections, malformed inputs, exact save/reload.
- Tk tests may skip without Tk (`tests/test_editor_gui.py:18`); actual UI QA is required in addition to passing headless tests.

## Existing mock

`output/visualizations/rebar-input-ui.html:61,70,80-85` contains the exact reference arrangement as hardcoded sample coordinates; changed counts fall back to uniform spacing. Use its appearance as reference only. Its special-case positions are not a general generation algorithm.

## Technical decisions to resolve in plan

- Separate face-normal center cover from the within-face distribution rule.
- Generate one physical bar arrangement and derive both directional tables.
- Preserve printed center distances explicitly instead of inventing an automatic rounding rule.
- Define a visible, durable choice between generated and edited layout, including regeneration semantics.
- Version new data deliberately while preserving old documents on no-op reads/saves; never silently reinterpret old layouts.
