# 11_直角(耐震).pdf — transcription notes (0720 seismic, transverse)

Independently transcribed from the user-provided PDF (pages 11-1 .. 11-27); never generated from the application.
Every page was rendered to PNG and read visually. Small tables were also rendered at higher DPI.
Values in `seismic_transverse.json` keep the printed string (`printed`), the number (`value`) and the printed decimal places (`digits`).

## 11.1 Analysis model (11-1 .. 11-7)

- 8 nodes and 7 elements. Elements 1–4, 6 and 7 are 剛域 (rigid). Element 5 (nodes 5–6, 0.010 m) is nonlinear 1 / section 1. The column (element 4, 4.890 m) is rigid.
- Segment lengths: 2.750 / 2.000 / 0.700 / 4.890 / 0.010 / 1.350 / 1.350. Overall dimensions: 13.050 (1–8), 10.340 (1–5), 0.010 and 2.700 (6–8).
  - Node 1 sits 2.750 above the beam top (node 2), at the girder/bearing level drawn in the superstructure outline.
  - Compared with the longitudinal model there is an extra rigid element (1–2, 2.750) on top.
- Section 1 (11-6): 2700 wide × 4500 high, shear span 10350 mm, 31 tiers.
  - Tiers 1 and 31 are D19×9 at 102 and 4398.
  - Tiers 2..30 are D32×2: at 108, then 300..4200 in steps of 150, then 4392.
  - Tension rebar spacing is 250. Hoops are D22×6 at 150.
  - **Observation:** the summary on 11-26 lists the main rebar as "D19-9本", i.e. tier 1 only.
- Springs (11-7): node 8, 8525475 (horizontal) and 25576488 (vertical) kN/m, the same values as the longitudinal file. The foundation text swaps B=9.000 and L=7.000. The rotational spring is Kr = 0.172641E+09 (11-24), which is kv·L·B³/12 = 172641294 (not printed).

## 11.2 Actions (11-8, 11-9)

- "下記以外の作用については §9 と同様". D1, D2, Wp and S come from §9 and are not derived here.

### (5) Train vertical load

- Each girder line: G = P × factor = vertical force, then × arm = moment.
- 上り線載荷:
  - 320.00 × (−0.020, 0.176, 0.373, 0.471) at arms (−3.800, −1.500, 1.500, 3.800)
  - 160.00 × (0.143, 0.857) at (−2.950, 2.950)
  - Σ 480.00 kN, Σ 1028.62 kN·m
- 下り線載荷: the factors are mirrored and Σ M = −1028.62.
- Factors have 3 decimals, forces 2 and arms 3.
- Moments are rounded per row: 572.736 → 572.74, −67.496 → −67.50, 404.504 → 404.50. The printed Σ equals the sum of the rounded rows (the unrounded sum is 1028.624).

### (6) Girder inertia

- H = 6720.00 + 2360.00 = 9080.00 kN.
- Torque table, moment = arm × the H or torque column:
  - girders 5520.00 × 2.750 = 15180.00 and 1720.00 × 2.750 = 4730.00
  - shelter couples (−530/−210/210/530 at ∓3.8/∓1.5, and −430/430 at ∓2.95)
  - all summed to M = 27105.00
- **Label/unit mismatch:** the column is headed "トルク(kN)" but holds a vertical force (kN) whose product with the arm is a moment.
- **Not printed:** the split of 6720 and 2360 into girder + shelter. 6720 − 5520 = 1200 and 2360 − 1720 = 640 presumably are the shelter horizontal forces; they are not stated.

### (7) Train inertia

- H = 96.00 + 48.00 = 144.00.
- M = 96.00 x 5.35 + 48.00 x 5.35 = 770.40. The arm 5.35 is printed without derivation.

### (8) Self-weight inertia

- Identical to the longitudinal file: Hw1 595.35, Hw3 297.68 and footing 1105.65 with (24.5 − 18.0).
- The Hw3/Hw2 label mismatch also exists here.

## 11.3 Load diagrams (11-10 .. 11-12)

- Case 1: N 8299.53, M 0.00, q 297.68, P 4167.45.
  - **Unit misprint:** N and M are printed with unit "kN/m".
- Case 2: N 780.00, M 0.00, P 1830.60.
- Case 3: P −1701.00 (2 decimals here; 1 decimal in the longitudinal file).
- Case 4: N 710.00, M 0.00.
  - The text layer splits "Case 4"; the image is clear.
- Case 5 "単線(上り)": N 480.00, M 1028.62. Case 6 "単線(下り)": N 480.00, M −1028.62.
- Case 7: H 9080.00, M 27105.00. Case 8: Kh=0.30, H 144.00, M 770.40.
- Case 9: Hw1 595.35, Hw2 297.68, H 1105.65, with dimensions 2.000 / 0.700 / 4.900 (4.900 = 4.890 + 0.010).
  - Case 9 also prints a stray "M" label with no value.
- Application points (diagram reading only):
  - Vertical N/M and girder/train H/M act at the second dot from the top (appears to be node 2), not at node 1.
  - Hw1 starts at node 2.
  - P and footing H act at the lowest dot (appears node 7).
  - Diagram results support this: shear 10.21 and moment 0 → 28.07 between nodes 1 and 2 imply only a small force at node 1. This is an observation, not printed.

## 11.4 Combinations (11-13)

- 9 basic cases. Seismic directions are → (opposite to the longitudinal ←).
- Combination 1: αf=1.0, ρm=1.0, "1 + 2 + 3 + 4 + 5 + 7 + 8 + 9", TYPE 1. Case 6 is omitted (coefficient recorded as 0). No numeric factors are printed; the others are recorded as 1.
- **Major label inconsistency:** the basic-case table names Case 5 "列車荷重 下り" and Case 6 "列車荷重 上り". The load diagram (11-11) names Case 5 "単線(上り)" with M = +1028.62, and 11-8 gives Σ M = +1028.62 for 上り線載荷. The combination uses Case 5 numerically. Which line name is correct cannot be decided from the print. The JSON keeps both labels as printed.

## Checks (11-14 .. 11-27)

- Pushover table, steps:
  - 10.0 / 26 / 30 / 38.4 / 131 / 223
  - The table has no ⑤-3:Khm row, although the marker appears on the chart.
  - **Inconsistency:** the (Khy+Khm)/2 row gives Kh 0.480, while Kheq is printed as 0.477 (chart, 11-15, 11-25). In the longitudinal file the two agree (0.368).
- Spectrum: Kheq 0.477, δeq 31.0, Teq 0.509. Safety: μ 7.19, δr 222.9, Khr 0.552 (step 223/350). Restorability: μ 4.22, δr 130.8, Khr 0.547 (131/350). Khy 0.401, KhL1 0.214.
  - **Hidden unrounded value:** 2.0 × √(0.031/0.477) = 0.5099 → 0.510 from the printed operands, but 0.509 is printed.
  - **Step mismatch:** KhL1 is at step "10.0" in the table but "11 / 350" on 11-15.
- Diagrams: overprinted labels recorded as illegible, not guessed:
  - moment at node 2 ("16789.?5" with "28.0?")
  - shear at node 7
  - axial force at node 7
- Member summary (11-21 and 11-26 agree):
  - θd 0.018503, with θ1 0.001750, θ2 0.027591 and θ3 0.045818. Ratios 10.573 / 0.671 / 0.404 → damage level 2.
  - Vd 6799.7 and Vud 18678.1 → 0.364. Kh/Khy 0.534.
  - All reproduce from the printed operands.
- Foundation checks (11-27; 11-22 is the same table rotated):
  - **Rounding/hidden value:** the L2 restorability rotation check has 2.270/20.000 = 0.1135, printed 0.113. Half-up rounding would give 0.114, so θd is probably slightly below 2.270 (hidden) or the rounding is not half-up. Elsewhere (for example 10-26 0.0765 → 0.077) it behaves as half-up.
  - **Step mismatch:** Ird 10.880 is listed at step 31, but the spring output gives 0.10880 at step 32 (same as the longitudinal file).
- Rotational spring output (11-24), with hidden intermediates:
  - qvd: from the printed operands 2412.90, printed 2410.90.
  - Rvd: 0.915 × 7.000 × 2454.75 = 15722.67, printed 15728.97.
  - Mmd recomputes to 67478.91, printed 67478.79.
  - Df is 3.78 in the formulas but 3.8 on 11-7.
  - The reaction is on the right (Pd2 2454.745, X1 0.979). On the ground-reaction page (11-23) it is drawn at the right edge: 8.021 + 0.979 = 9.000.

## Not transcribed

- 11-16 displacement diagram.
- The curve geometry on 11-14.
- Illegible overprinted labels.
- The 名称 cell on 11-25 (unreadably small).
