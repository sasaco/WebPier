# Seismic transverse reference evidence

Investigated 2026-10-17 for the planned 0720 report. Product code, input, and published outputs were not modified. Page numbers below are physical PDF pages, counted from 1. Reference PDFs were rendered with the existing PyMuPDF runtime (system Poppler was unavailable) and inspected as images, not only text.

## Evidence and page scope

- `Example橋脚2/09_直角.pdf`: 29 pages; visually inspected p1.
- `Example橋脚2/11_直角(耐震).pdf`: 27 pages; visually inspected p1-5, p8-13. The requested four-page adaptation uses 09 p1 for the clean skeleton presentation, 11 p1-5 for seismic geometry, 11 p8 and p9 for actions, and 11 p13 for combinations.
- Images and matching text: `tmp/seismic-transverse-planning/ordinary-p01.png` and `.txt`; `seismic-p01` through `seismic-p05`, `seismic-p08` through `seismic-p13`, each `.png` and `.txt`.
- Independent arithmetic from the current JSON, without invoking product calculation functions: `tmp/seismic-transverse-planning/independent-input-check.json`.

The four-page interpretation is internally consistent: model, action calculations (1), action calculations (2), combination specification. It intentionally omits the reference nonlinear constitutive tables, load-diagram pages, response analysis and checks. The user explicitly confirmed this four-page arrangement on 2026-10-17. This confirms the page scope; approval of the complete implementation plan is a separate gate.

## Model correspondence

09 p1 has a six-node, five-member centerline through the physical pier, with 2.000 + 0.700 + 4.900 m above the footing and 1.350 + 1.350 m in the footing. It shows footing springs and a spring table; the user's inherited instructions explicitly remove those visual items.

11 p1/p2 add an upper 2.750 m member and split 0.010 m from the existing 4.900 m column base. From top to bottom:

| Member | Upper/lower nodes | Reference length (m) | Correspondence |
|---|---|---:|---|
| 1 | 1-2 | 2.750 | Upper superstructure level to pier cap top |
| 2 | 2-3 | 2.000 | Input lower-structure H2 |
| 3 | 3-4 | 0.700 | Input lower-structure H3 |
| 4 | 4-5 | 4.890 | Input H4 minus 0.010 |
| 5 | 5-6 | 0.010 | Column-base micro member, within H4 |
| 6 | 6-7 | 1.350 | Footing top to its centroid |
| 7 | 7-8 | 1.350 | Footing centroid to bottom |

The reference total height 13.050 m is 2.750 + physical height 10.300 m. The displayed 10.340 m dimension ends at node 5 above the micro member, and is not the total above-footing height (10.350 m). Do not copy 13.050 or 10.340 as fixed constants.

Current inputs match those dimensions: lower H1=0, H2=2, H3=.7, H4=4.9, H5=0, H6=2.7 (`P7橋脚/pre/input.json:495`). Upper B h1+h2=.15+2.60=2.750 and C h1+h2=.10+2.65=2.750 (`input.json:393`, `input.json:416`). These are distinct from the input aggregate inertia centroid heights hs=2.9520833333333334 and 3.0662447257383967 (`input.json:398`, `input.json:421`).

The interpretation of the 2.750 m upper member as h1+h2 is supported by the visual slab/bearing geometry and exact current-input correspondence. The source page does not explicitly label this dimension with the input variable names. Treat it as a documented mapping, not as proof that hs equals 2.750.

Important load-placement evidence from 11 p12: EQ1 H/M and EQL H/M are both drawn at the SECOND node, the cap top, below the 2.750 m extension. The topmost node above that point remains visible. Therefore retaining the full cap-top moment H*hs or H*train_height and moving the same H/M to the upper node would double count its height. Use cap_top as the semantic load anchor. The same second-node placement appears for D1/D2/snow/train on p10-11.

11 p3/p4 mark the base micro member as nonlinear/section 1; p5 lists element 5 as nonlinear 1, section 1 and elements 1-4/6-7 as rigid. This supports the geometric correspondence only. The report must not imply that material constitutive laws, nonlinear resistance or response analysis have been calculated. Existing 0710 geometry already uses top-down IDs and role-based anchors (`seismic_longitudinal_calculator.py:172`, `:200`); a new extra node must update all referenced IDs after final ordering.

For changed input, the existing frame builder handles zero-height coalescing, positive H1 and nonuniform footing centroid heights (`frame_model.py:91`, `:113`, `:131`, `:137`). Do not replace this with a hardcoded eight-node array. How unequal B/C values of h1+h2 are represented is not answered by the reference, because its two heights coincide. The proposed implementation policy is to retain distinct role-based geometric nodes for unequal side heights and merge exactly equal heights. These upper nodes add no mass and carry no applied loads; cap-top H/M remain unchanged. Do not replace the two input levels with a maximum or average. This policy is a planning decision pending approval of the complete implementation plan, not a claim about the reference's analysis model.

## Page 8: train distribution and girder inertia

### Earthquake train vertical loads

Reference support loads are RB=320.00 kN, RC=160.00 kN. The existing 0600 calculation computes these as earthquake line load times full span length divided by 2 (`reaction_calculator.py:131`): current 32 kN/m * 20 m / 2 = 320 and 32 * 10 / 2 = 160.

| Track | B rates (G1-G4) | B arms (m) | C rates (G1-G2) | C arms (m) | Sum N (kN) | Sum displayed-row M (kN m) |
|---|---|---|---|---|---:|---:|
| Up | -.020, .176, .373, .471 | -3.8, -1.5, 1.5, 3.8 | .143, .857 | -2.95, 2.95 | 480.00 | +1028.62 |
| Down | .471, .373, .176, -.020 | -3.8, -1.5, 1.5, 3.8 | .857, .143 | -2.95, 2.95 | 480.00 | -1028.62 |

Current input supports this directly: L1=down, L2=up, matching the existing `TRACK_KEYS` (`transverse_actions.py:21`). Preserve negative bearing reactions. Each force is upstream earthquake reaction times that bearing's track rate once; moment uses that bearing's own arm, including C-side arms. Do not use nonseismic raw train reactions or impact/ultimate factors. Round each displayed row M to two decimals and sum those rows, consistent with the existing physical vertical table convention (`transverse_actions.py:51`, `:59`).

### EQ1: reference split versus current aggregate input

Reference p8 H=6720+2360=9080 kN at Kh=1. Its moment table contains B girder 5520*2.750=15180, B shelter vertical torque rows (-530*-3.8)+(-210*-1.5)+(210*1.5)+(530*3.8)=4658, C girder 1720*2.750=4730, C shelter (-430*-2.95)+(430*2.95)=2537. Total M=27105 kN m.

Current input expressly excludes a separate shelter feature and represents the aggregate with D1+D2+S2 and freely entered equivalent hs (`input.json:21`; `P7橋脚/README.md:205`, `:298`). Current 0600 implementation already calculates H=D1+D2+S2 and M=H*hs (`reaction_calculator.py:299`, `:330`, `:334`). Thus:

| Side | D1 | D2 | S2 | H at Kh=1 (kN) | hs (m) | M (kN m) |
|---|---:|---:|---:|---:|---:|---:|
| B | 5740 | 520 | 460 | 6720 | 2.9520833333333334 | 19838 |
| C | 1860 | 260 | 250 | 2370 | 3.0662447257383967 | 7267 |
| Sum | | | | **9090** | | **27105** |

The C-side +10 kN difference versus reference 2360 is explicitly recorded in the input provenance as an unaccepted reference residual retained to preserve the longitudinal case. The present task says use and preserve current input, so the correct regenerated current-input report shows **9090**, not a fabricated 9080. Do not lower S2 or change hs to force a reference match. State the difference in planning/research and verification; preserve the established product rule that development comparison history does not fill the calculation PDF.

The reference's separately listed girder/shelter subrows cannot be reconstructed uniquely from the current aggregate D1/D2/S2/hs. Render the supported B/C equivalent expressions and totals in the same calculation-page style, rather than inventing shelter detail or hardcoding the old subrows.

## Page 9: EQL and self inertia

Reference EQL already contains Kh=.30: H_B=.30*320=96; H_C=.30*160=48; H=144 kN. The cap-top moment is 96*5.35+48*5.35=770.40 kN m. Current 0600 uses .30 once, with height h1+h2+h3+vehicle earthquake center height (`reaction_calculator.py:322`, `:331`, `:333`, `:344`). Current B and C both give 2.750+1.10+1.50=5.350 m. Do not apply .30 again in the combination. The 0710 limit .20 and bearing fixed/movable logic are inapplicable here.

Reference Kh=1 self inertia:

- Beam top: 2.70*9.00*24.5=595.35 kN/m.
- Column: 4.50*2.70*24.5=297.675 -> 297.68 kN/m.
- Footing: 7.00*9.00*2.70*(24.5-18.0)=1105.65 kN, acting at its centroid.

Current inputs match all of these. For a changed taper, the beam-bottom distributed intensity is (B1-B4-B5)*(W1-W4-W5)*body_gamma*Kh, currently 297.675 -> 297.68. These formulas are already documented by 0710 (`seismic_longitudinal_calculator.py:261`). For a nonrectangular footing, use actual 0600 footing weight / footing gamma * (footing gamma-displaced-soil gamma), rather than always multiplying bounding dimensions (`seismic_longitudinal_calculator.py:288`). The current rectangular dimensions are B7+B8+B9=7 and W7+W8+W9=9 (`input.json:474`, `:485`).

Reference p12 gives additional evidence for self-inertia load placement: the top distributed segment is the 2.000 m beam segment; the lower intensity spans the taper/column interval, and the footing force acts at the centroid. The 0.010 split must preserve the original continuous column-load extent and total, not add an extra weighted 0.010 m. H1>0 handling should preserve the existing pedestal weight and equivalent moment pattern, although the reference/current input H1=0 does not exercise it.

## Page 13: exact case and combination definitions

| Case | Symbol | Direction | Kind | Name / coefficient |
|---:|---|---|---|---|
| 1 | D1 | down | fixed | Fixed dead load |
| 2 | D2 | down | fixed | Additional dead load |
| 3 | Wp | up | fixed | Buoyancy |
| 4 | Sw2 | down | fixed | Snow, 2-year |
| 5 | L | down | fixed | Train, down track |
| 6 | L | down | fixed | Train, up track |
| 7 | EQ1 | right | incremental | Girder earthquake inertia, Kh=1.00 |
| 8 | EQL | right | limited incremental | Train earthquake inertia, Kh=.30 |
| 9 | EQ2 | right | incremental | Self earthquake inertia, Kh=1.00 |

Only combination 1 is printed: alpha_f=1.0, rho_m=1.0, direction right, ground resistance TYPE=1, **1+2+3+4+5+7+8+9**, with implicit coefficient 1 for every term. Case 6 is an available alternative but is not included. No max-of-up/down algorithm or second reverse-direction combination is shown. TYPE=1 is a condition label; it does not establish calculated ground resistance.

Reference contradiction: p11 load diagrams label Case5 as up and Case6 as down, opposite to p13. On 2026-10-17 the user explicitly confirmed p13 as the authority for the new report: Case5=down, Case6=up, and combination 1 selects the down track. Together with p8's explicit named up/down force rows, Case5 therefore carries down N480/M-1028.62 and Case6 up N480/M+1028.62. Preserve this recorded source discrepancy; do not swap the case definitions based on p11. This choice is resolved.

## Implementation boundaries and outstanding choices

- Public 0620 is schema 2 and explicitly nonseismic; `legacy_audit` is only an entrypoint/source pointer (`transverse_calculator.py:24`, `:44`, `:59`). Existing physical D1/D2/buoyancy/S2 actions and frame can be reused, remapping anchor IDs. Obtain earthquake inputs from current 0600/input, not the old selected-track `calculate_transverse_legacy` load tables.
- Keep load quantities, height provenance, applied Kh, and remaining coefficient separate. H and M belong to an anchor; kN/m must not be added to point kN. The upper geometry member has no new mass by itself.
- The user confirmed the four-page arrangement and p13 case authority on 2026-10-17. State these confirmed choices and the equivalently grouped B/C girder calculation in the reviewable plan. The current-input instruction already determines the +10 kN result; it does not authorize input adjustment to force agreement.
- The proposed policy for unequal B/C h1+h2 is distinct role-based geometric nodes, with exactly equal levels merged. Preserve both side heights as source evidence; use no maximum/average replacement and do not equate either level with hs. Upper nodes add no mass or loads, and H/M remain at cap_top. This proposed implementation policy remains subject to complete-plan approval.
- No additional domain numerical input is missing for regenerating the requested current P7 four-page artifact. Remaining questions about analysis laws or capacity are outside scope and must not block this loads-only task.
