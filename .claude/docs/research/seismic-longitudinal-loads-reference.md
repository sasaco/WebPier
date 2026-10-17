# Seismic longitudinal loads reference review

Date: 2026-10-16. Planning evidence only; no product/input/output change.

## Requested pages

The physical PDF page indexes agree with printed page numbers. The reference PDFs are local user-provided material.

| Source | Physical / printed page | Requested content |
|---|---|---|
| Example橋脚2/08_線路.pdf | 1 / 8-1 | Frame geometry, dimensions, support springs; to be adapted for earthquake loading |
| Example橋脚2/10_線路(耐震).pdf | 8 / 10-8 | Train vertical load, bearing horizontal forces, pier self-weight inertia |
| Example橋脚2/10_線路(耐震).pdf | 12 / 10-12 | Eight basic cases and one combination |

All three pages were rendered with PyMuPDF and visually inspected. Read-only inspection PNG/text files are in `tmp/seismic-longitudinal-loads-plan/`.

## Independent reference values

- Train: B = 320.00 kN, arm = -0.325 m, M = -104.00 kN m; C = 160.00 kN, arm = 0.675 m, M = 108.00 kN m; total N = 480.00 kN, M = 4.00 kN m.
- Bearing horizontal girder inertia: B = 6790.00 kN; C = 4740.00 kN.
- Bearing horizontal train inertia: B = 64.00 kN; C = 64.00 kN.
- Normalized pier inertia coefficient Kh = 1.00.
- Beam: 2.70 * 9.00 * 24.5 * 1.00 = 595.35 kN/m.
- Column: 4.50 * 2.70 * 24.5 * 1.00 = 297.68 kN/m (rounded display).
- Footing: 7.00 * 9.00 * 2.70 * (24.5 - 18.0) * 1.00 = 1105.65 kN.

## Case definitions from 10-12

| Number | Symbol | Direction | Load classification | Meaning |
|---|---|---|---|---|
| 1 | D1 | Down | Fixed | Permanent dead load |
| 2 | D2 | Down | Fixed | Additional dead load |
| 3 | Wp | Up | Fixed | Buoyancy |
| 4 | Sw2 | Down | Fixed | Snow, 2-year return period |
| 5 | L | Down | Fixed | Earthquake train vertical load |
| 6 | EQ1 | Left | Incremental | Girder inertia, Kh = 1.00 |
| 7 | EQL | Left | Limited incremental | Train inertia, Kh = 0.20 |
| 8 | EQ2 | Left | Incremental | Pier self-weight inertia, Kh = 1.00 |

Combination 1: alpha_f = 1.0; rho_m = 1.0; direction left; cases 1 through 8 with coefficient 1; ground resistance TYPE = 1. Load classifications must be retained independently of the printed sum. This page does not specify an analysis algorithm or authorize implementation of nonlinear response calculations.

## Model context and limits

- Page 8-1 shows a 6-node frame and long/short-term springs. It contains a 6.000 m lower horizontal dimension inconsistent with the actual 7.000 m footing; use the current input geometry instead of tracing this mismatch.
- Page 10-7 shows Kv = 25,576,488 kN/m and Ks = 8,525,475 kN/m, matching the short-term values on 8-1. Its nonlinear soil information is separate from the requested frame/report scope.
- Pages 10-1 through 10-3 have a 7-node seismic solver discretization including a 0.010 m segment. The original decision to exclude this segment was superseded by the user's correction on 2026-10-17; see the verified geometry below.
- Page 8-1 short-term Kr = 104,437,326 kN m/rad. Recommended model-page representation: current physical frame geometry plus 0500 longitudinal short-term Kv/Ks/Kr, clearly labelled as elastic reference springs. The footing's nonlinear resistance law is outside this report-only scope.
- The source says other actions follow the nonseismic chapter. Refer to 0610 for D1, D2, Wp and Sw2; do not add their calculation/load-diagram pages to the requested three-page report.

## Direction must be explicit

The 07_荷重計算.pdf p18 transverse values (including train coefficient 0.30) must not replace the longitudinal bearing forces used by 10-8. The current longitudinal 0600 implementation uses coefficient 0.20 and bearing allocation, reproducing 64/64 kN. Existing saved 0600 and 0610 results have the same input SHA as the current input at inspection: `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b`.

## User decisions

- User confirmed: add a reproducible three-page app report in model/actions/combination order. App scope includes CLI/GUI generation and a companion result JSON following existing conventions; no FrameWeb seismic export or structural response/member verification.
- User corrected the model-page proposal: **do not display springs**. This supersedes the short-term spring display recommendation above. Omit the spring table, symbols and Kv/Ks/Kr labels from the page, retaining the current physical geometry, nodes and dimensions. Do not imply a fixed base or a nonlinear seismic support model merely because spring symbols are omitted. There is no need to select a seismic spring model for this report.
- For the case3 buoyancy definition, adjacent source10-10 gives -1701.0 kN. This matches existing0610 `vertical.water.normal`; select normal water level rather than high/low. Case4 uses `vertical.snow.s2` (N710/M19.25). Adjacent pages are interpretation evidence only; do not add them to the output.

## 2026-10-17 correction: column-base micro member

The user explicitly requires the 0.010 m member at the current node 2. Physical pages 1–5 were rendered and visually rechecked. The source node elevations, from top to bottom, are 10.300, 8.300, 7.600, 2.710, 2.700, 1.350, 0.000 m. Source element 4 joins source nodes 4→5 across the 0.010 m interval immediately above the footing.

The 4.900 m H4 interval is split into 4.890+0.010 m; the upper dimension is 7.590+0.010=7.600 m. Overall height stays 10.300 m. Page 3 identifies nonlinear number 1 at this interval, page 4 identifies section 1, and page 5 maps element 4 to these identifiers. This is a column-base nonlinear micro element, not a soil spring.

0710 splits the H4 connection while preserving the coordinates, physical outline, existing actions, and 0610/0620. The user's subsequent correction on 2026-10-17 requires node and element IDs to be consecutive from top to bottom, superseding the initial max+1 ID preservation. The standard model therefore matches source node IDs 1–7 and element IDs 1–6; the micro element is element 4 between nodes 4 and 5. Roles and connection references follow the renumbering, including H1 variants. The new member records its source nonlinear classification, but no constitutive law, nonlinear calculation, or conversion of other members to source rigid zones is implemented. The report remains three pages without springs, and the enlarged detail was explicitly removed at the user's request.
