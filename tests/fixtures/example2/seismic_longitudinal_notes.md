# 10_線路(耐震).pdf — transcription notes (0710 seismic, longitudinal)

Independently transcribed from the user-provided PDF (pages 10-1 .. 10-26); never generated from the application.
Every page was rendered to PNG and read visually. Most pages are images, so the text layer was used only as a cross-check.
Values in `seismic_longitudinal.json` keep the printed string (`printed`), the number (`value`) and the printed decimal places (`digits`).

## 10.1 Analysis model (10-1 .. 10-7)

- Procedure: single-line frame, 7 nodes and 6 elements. Elements 1, 2, 3, 5 and 6 are 剛域 (rigid). Element 4 (nodes 4–5, 0.010 m) is the only nonlinear member (非線形番号 1, 断面番号 1). The 4.890 m column itself is rigid, so all flexural nonlinearity sits in the column-base micro member.
- Printed segment lengths, top to bottom: 2.000 / 0.700 / 4.890 / 0.010 / 1.350 / 1.350 (3 decimals). Overall dimensions: 10.300, 7.590 (node 1–4), 0.010 and 2.700 (node 5–7). Depths below node 1 under `derived` are sums of these and are not printed.
- The i/j node of each element is read from the drawing on 10-2. The table on 10-5 gives only element, nonlinear and section numbers.
- Section 1 (10-6): 4500 × 2700 mm, shear span 7600 mm, fc' 27, Ec 26.5 kN/mm², SD390, 11 tiers (D32×29 at 108 and 2592; D19×2 at 350..2350 in steps of 250), hoops D22×10 at 150. Integers are printed with 0 decimals. Factors such as 1.30 are printed with 2 decimals.
- Springs (10-7): node 7 horizontal 8525475 kN/m, vertical 25576488 kN/m. The foundation text gives B=7.000 m, L=9.000 m, kv=405976 kN/m3, Df=3.8 m, γ1=10.0, γ2=11.6, φ=42.2度, k=2.
  - Not printed (observation only): 25576488 = kv × B × L exactly. 8525475 = 135325 × 63, which is kv/3 rounded to an integer and then multiplied by the area; it is not kv × A / 3 (= 8525496).
  - The rotational spring is printed only on 10-23 as Kr = 0.104437E+09. This equals kv·L·B³/12 = 104437326.
  - `c＝0.0kN/m3`: the unit is printed as kN/m3 (sic).

## 10.2 Actions (10-8)

- "下記以外の作用については §8 と同様". Only train load, bearing horizontal forces and self-weight inertia are printed here. D1, D2, Wp and S appear only as totals on the load diagrams. Their derivation is in §8 (file 08), which is not part of this transcription.
- Train vertical load (single track): RB 320.00 × arm −0.325 = −104.00, and RC 160.00 × 0.675 = 108.00. Totals: 480.00 kN and 4.00 kN·m. Forces have 2 decimals and arms have 3.
- Bearing horizontal forces, seismic, 1.0 EQ:
  - girder: 6790.00 + 4740.00, which matches Case 6 H = 11530.00
  - train: 64.00 + 64.00, which matches Case 7 H = 128.00
  - **Ambiguity:** the derivation of 64.00 for the end girder is not printed here. Case 7 is labelled Kh=0.20, and 0.20 × 320 = 64 but 0.20 × 160 = 32. Do not infer it; see §8.
- Self-weight inertia, Kh = 1.00:
  - Hw1 = 2.70 × 9.00 × 24.5 × 1.00 = 595.35 kN/m
  - Hw3 = 4.50 × 2.70 × 24.5 × 1.00 = 297.68 kN/m. The unrounded value is 297.675, rounded half-up to 2 decimals.
  - Footing H = 7.00 × 9.00 × 2.70 × (24.5 − 18.0) × 1.00 = 1105.65 kN. In these formulas dimensions are printed with 2 decimals, the unit weight with 1, and Kh with 2.
  - **Label mismatch:** the column load is called "Hw3" on 10-8 but "Hw2" on the load diagram (10-11).
  - **Notable:** footing inertia uses (24.5 − 18.0) = 6.5 kN/m3, i.e. it subtracts 18.0. The page does not explain the 18.0 (likely the soil unit weight). It is transcribed as printed.

## 10.3 Load diagrams (10-9 .. 10-11)

- Case 1 D1: N 8299.53, M −610.00, q 297.68 (= Hw3/Kh, column self-weight per m) and P 4167.45. 4167.45 = 7×9×2.7×24.5, which is not printed.
- Case 2 D2: N 780.00, M 6.50, P 1830.60.
- Case 3 Wp: P −1701.0. **Digit inconsistency:** 1 decimal here, while all other loads have 2 decimals; the transverse file prints −1701.00.
- Case 4 S: N 710.00, M 19.25.
- Case 5 train (seismic): N 480.00, M 4.00. These are the 10-8 totals.
- Cases 6, 7 and 8: H 11530.00, H 128.00, and Hw1 595.35 / Hw2 297.68 / H 1105.65.
- The Case 8 drawing has dimensions 2.000 (Hw1), 0.700 (taper from Hw1 to Hw2) and 4.900 (Hw2).
  - **Inconsistency:** the model column is 4.890 + 0.010; 4.900 is the sum.
  - **Ambiguity:** the intensity over the 0.700 haunch is not printed. The drawing shows a linear taper.
- Application points (diagram reading, not printed as node numbers):
  - N, M and H act at the top node.
  - q runs down to the first dot (footing top).
  - P and footing H act at the lower dot, which appears to be node 6 (footing mid-depth).

## 10.4 Combinations (10-12)

- 8 basic cases. Directions: ↓ for D1, D2, Sw2 and L; ↑ for Wp; ← for EQ1, EQL and EQ2.
- Load types: 固定 for cases 1–5, 増分 for 6 and 8, 限定増分 for 7.
- One combination: αf=1.0, ρm=1.0, direction ←, "1 + 2 + 3 + 4 + 5 + 6 + 7 + 8", 地盤抵抗TYPE 1.
- No numeric factors are printed (the header is "荷重補正係数+基本Case"). The JSON records a coefficient of 1 for each case and flags it.

## Checks (10-13 .. 10-26)

- Pushover table (10-13), steps:
  - 15.1 / 29 / 30 / 33 / 177 / 245 / 285
  - Kh is printed with 3 decimals and δ with 1.
  - Kheq 0.368 = (Khy 0.350 + Khm 0.386)/2.
- Spectrum (10-14): Kheq 0.368, δeq 30.5 mm, Teq 0.576. Restorability: μ 5.78, δr 176.3, Khr 0.385. Safety: μ 9.32, δr 284.3, Khr 0.386. KhL1 0.214.
  - **Hidden unrounded value:** Teq = 2.0 × √(0.031/0.368) gives 0.5805 → 0.580 from the printed operands. The printed result 0.576 matches δeq = 0.0305 m (= 30.5 mm). The printed "0.031" is a 3-decimal display of 0.0305.
  - **Step mismatch:** KhL1 is at step "15.1" in the 10-13 table but "増分ステップ 16 / 300" on 10-14. The other steps agree (285, 245, 177).
- Diagram labels (10-16 .. 10-18): red labels belong to 安全性. Some are overprinted with a second, different label; these are recorded as illegible with the candidate strings, not guessed.
  - Shear at node 6.
  - Axial force at nodes 4/5 and node 6.
- Member summary (10-20 and 10-25 agree):
  - θd −0.035392, with θ1 −0.002614, θ2 −0.029959 and θ3 −0.037156. Ratios 13.539 / 1.181 / 0.953 → damage level 3.
  - Vd 5732.9 and Vud 19578.3 → 0.293.
  - These ratios reproduce from the printed operands.
- Foundation checks (10-26; 10-21 is the same table rotated):
  - All ratios reproduce from the printed operands with half-up rounding. For example 1.530/20.000 = 0.0765 → 0.077, so this is half-up, not banker's rounding.
  - **Step mismatch:** Ird = 10.657 is listed at step 30, but the spring output (10-23) gives 底面塑性化率 0.10657 at step 31 (Ird is in %, ×100).
  - Mmd 53918.3 at step 16 (L1) differs from Mmd 52615.2 on 10-23 at step 31.
- Rotational spring output (10-23), with hidden unrounded intermediates:
  - qvd: from the printed operands, 1.0×0.306×0.484×0.726×10.00×150.00 + 1.0×0.625×11.60×3.78×84 = 2463.31, but 2462.40 is printed.
  - qd = 2462.40 + 11.60×3.78 = 2506.248, printed 2506.24 (Pd1 = 2506.244).
  - Rvd: 0.726 × 9.000 × 2506.24 = 16375.77, printed 16371.21. The effective B′ is ≈ 0.7258.
  - Mmd recomputes to 52615.24, printed 52615.17.
  - Kr′ = 0.522187E+08, while Kr/2 = 0.5221850E+08.
  - **Df inconsistency:** the formulas use Df = 3.78, while 10-7 prints Df = 3.8.
  - The formula line `＝Ａ'( 0.726× 9.000)×   2506.24)` has unbalanced parentheses as printed.
- Response summary (10-24) agrees with 10-14.

## Not transcribed

- 10-15 displacement diagram (no numbers).
- The geometry of the curve on 10-13.
- Illegible overprinted labels.
- The 名称 cell on 10-24, which is printed in an unreadably small font.
