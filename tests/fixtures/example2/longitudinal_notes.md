# 08_線路.pdf (§8 線路方向の計算（地震時以外）) — transcription notes

Basis: independently transcribed from the user-provided PDF; never generated from the application.
Source: `.claude/docs/Example橋脚2/08_線路.pdf`, 32 pages, printed 8-1 to 8-32. All pages transcribed
(model, actions and combinations in `sections`; 8-12 onward in `checks`).

## How it was transcribed

- Every page was rendered to PNG and read visually. Rotated or small tables (8-10, 8-12, 8-13) were also
  rendered at a higher resolution.
- Numbers were typed as the printed strings. `value` and `digits` come from those strings.
- Cross-check: every number on a page that has a text layer (8-1 to 8-11, and the foundation pages
  8-27 to 8-32) was matched against the PyMuPDF tokens of the same page. All 570 values matched. The
  only misses were values on image-only parts of the page.
- The 8-10 combination table was rebuilt from word coordinates and matched cell by cell: 0 mismatches.
- Pages 8-12, 8-13, 8-15, 8-17, 8-20, 8-22, 8-24 and 8-26 are image-only, so their values come from
  reading alone.

## Section procedure and digit conventions

### 8-1 Frame model
- The pier is a single line of nodes 1 to 6.
  - Members 1 to 3 have heights 2.000, 0.700 and 4.900, for 7.600 from the pier top (node 1) to the
    top of the footing (node 4).
  - Members 4 and 5 are 1.350 each: footing height 2.700, centroid at node 5.
  - The springs Kv, Ks and Kr sit at node 6, the footing bottom.
- Spring table (長期 / 短期): integers with thousands separators, `digits` = 0.
- Dimensions are printed with 3 decimals.

### 8-2 Section properties
- b, h: 2 decimals. A: 3 decimals. I: 5 decimals.
- f'ck 27.0. Ec printed as `2.65 x 10^7 kN/m2`; it is stored as the mantissa 2.65 plus the exponent 7.

### 8-3 Dead load (D1)
- Formulas use operands with 2 decimals (24.5 has 1) and results with 2 decimals.
- Table columns: 鉛直力 (2 decimals), アーム (3 decimals), ﾓｰﾒﾝﾄ (2 decimals). Each moment = 鉛直力 × アーム.
- 合計 sums the 鉛直力 and ﾓｰﾒﾝﾄ columns.
- `N = 合計 − q × 2.00`. The beam's own column-weight over its 2.00 m height is removed because the
  beam is added as a concentrated 1190.70.
- Downstream use, inferred from the 8-12 and 8-30 results and not printed: q = 297.68 acts over the
  full 7.600 m, members 1 to 3. The column-base N for comb 6 = 8299.53 + 297.68×7.6 + 780 + 710 =
  12051.90, which matches 8-12.

### 8-3 Superimposed dead load (D2)
- 載荷土 P = 18.0 × 7.00 × 9.00 × 2.00, minus 18.0 × 4.50 × 2.70 × 2.00 for the column. ΣP = 1830.60 is
  the footing-level P of Case 2.
- The top table gives N = 780.00 and M = 6.50 for Case 2.

### 8-3 Buoyancy
- `−10.0 × 7.00 × 9.00 × h_w`, with h_w = 3.78, 2.70 and 0.00. These are Cases 3 to 5.

### 8-4 Snow and train
- Two-row tables (RB / RC) with arms −0.325 and 0.675. The moments are exact products.

### 8-5 Impact
- 鉛直力 = train reaction (from 8-4) × impact coefficient: 0.245 / 0.546 single track, 0.222 / 0.521
  double track. The coefficient has 3 decimals and the result 2.

### 8-5 Horizontal bearing loads
- Summary table by requirement: 起点桁 / 終点桁, 2 decimals.
- Load-diagram H (Case 13 to 20) = 起点桁 + 終点桁. For example 240.00 = 160.00 + 80.00 and
  473.43 = 298.40 + 175.03.
- H acts at node 1.

### 8-6 to 8-8 Load diagrams
- Values repeated from 8-3 to 8-5. Case 13 to 20 H = row sums of the 8-5 table.

### 8-9 Basic and Define cases
- 20 basic cases. バネ prints 1 or 2: likely the 長期 / 短期 spring sets, but the page does not say so.
- Define cases 13 to 20 carry C2 = −n, i.e. both signs.
- Inferred from 8-30: the 曲げ最大 column uses the reversed horizontal case.
  - Md = |1.1(−610) + 1.2(6.5) + 29.5 + 1.23(221.04) − 495.01×10.3| = 5460.42.
  - The 鉛直力最大 column uses +H: Md = 4767.98.
  - The H arm is 10.3 = 7.6 + 2.7, from node 1 to the footing bottom.

### 8-10 Combinations
- 16 combinations × 20 columns (basic case numbers).
- Coefficients are printed with 1 decimal (1.0, 1.1, 1.2) or 2 (1.35, 1.23, 0.75). '－' is stored as
  `null`.

### 8-11 Extraction cases
- Groups of combination numbers.

### Checks (8-12 to 8-32)
- Section-force summaries:
  - Member 3, point JTAN 4.900, the column base. Values have 2 decimals.
  - The check sheets repeat them with 1 decimal (4123.90 → 4123.9).
- Ratio cells such as `0.132 < 1.00` are stored as value / compare / limit.
- Foundation tables 8-30 and 8-32: 長期支持 = comb 14, 短期支持 = comb 15, 鉛直力最大 = comb 10,
  曲げ最大 = comb 11 with H reversed. These assignments come from reconciling Vd and Md and are not
  printed.

## Ambiguities and inconsistencies (flagged, not resolved)

1. **8-1, footing width.** The lower dimension line prints 3.000 + 3.000 = 6.000. The upper line gives
   2.150 + 2.700 + 2.150 = 7.000, and 8-3 and 8-30 use B = 7.00. The value is transcribed as printed
   (`footing_width_bottom_dim` = 6.000, with a note).
2. **8-1, Ks short.** Ks short = 8,525,475 is not 2 × 4,262,769 = 8,525,538. Kv and Kr short are
   exactly 2 × long. The same values appear on 9-1.
3. **8-4, double-track RB.** RB = 544.93, but 2 × 272.47 = 544.94. The 8-5 impact row then prints
   544.93 × 0.222 = 120.98, which only holds if the hidden RB is about 544.94 (544.93 × 0.222 =
   120.974 → 120.97). The 8-5 double-track total 428.28 ≠ 120.98 + 307.31 = 428.29; it equals the sum of
   the unrounded parts, 428.283.
4. **8-5, single-track RB.** 272.47 × 0.245 = 66.755 rounds half-up to 66.76, but 66.75 is printed: a
   hidden reaction below 272.47, or truncation.
   - The RB moment −21.70 matches the unrounded product (66.755 × 0.325 = 21.695), not the printed
     66.75 (→ −21.69).
   - The RC moment 108.69 also matches the unrounded value (161.026 × 0.675), not 161.03 × 0.675 =
     108.695 → 108.70.
   - So moments are taken from hidden unrounded intermediates.
5. **8-5, horizontal table, 終点桁 column.** It is not consistent with one B value.
   - 起点桁 implies LR = 200 and B = 80 for every row.
   - 終点桁 gives B = 61.0 (1.0LR + 1.23B), 69.5 (1.1LR + 1.23B), 64.5 (1.0LR + 1.35B) and 53.1
     (復旧性 1.0LR + 1.23B).
   - 復旧性 1.0LR + 1.23B (165.31) also differs from 安全性 1.0LR + 1.23B (175.03).
   - Transcribed as printed. The source of these values is outside this PDF.
6. **8-7, moment arrows.** The Case 9/10 arrow is drawn counter-clockwise while Cases 1, 2, 6 to 8 and
   11/12 are clockwise. The printed M values are all positive except Case 1. The sign convention of the
   drawing is unclear.
7. **8-9, バネ column.** The meaning of 1 / 2 is not printed.
8. **8-11, header cell.** The 抽出ケース name-column header prints `0.375` instead of a label (stray
   cell).
9. **Section numbering.** "8.7 耐久性の照査" (8-18) and "8.7 基礎の照査" (8-27) are both numbered 8.7.
10. **8-17, Vsd row.** Vsd (鉄骨部分) = 20622.5 on an RC member, and Vyd = Vcd + Vsd = 3024.6 + 20622.5.
    The label probably stands for the stirrup term Vwd. Transcribed as printed.
11. **8-20 and 8-24, σc limit.** The label prints `σc≦0.4/f''cd`, but the limit 10.8 = 0.4 × 27.0, so it
    means 0.4·f''cd.
12. **8-22, γbc.** γbc is printed 1.00, while 8-21 states γb = 1.3 for Vcd in the shear-crack check.
    Vhd / 0.7·Vcd prints `300.0<2901.2`.
13. **8-25 vs 8-26, γi.** The text says γi = 1.0 for 復旧性, but the sheet prints γi = 1.20 and the
    ratio 0.114 = 1.20 × 3619.6 / 38260.8. The row label is "Mu" although the text defines My.
14. **8-30, ex rounding.** B′ = B − 2ex and Pd1 / Pd2 use ex rounded to 3 decimals (B′ = 6.928,
    Pd1 = 267.51). 8-32 recomputes B′ and A′ from the unrounded ex (6.929 / 62.361, 6.957 / 62.613,
    6.501 / 58.509). The two pages disagree in the 3rd decimal.
15. **8-30, 長期 column.**
    - qvd prints 300.00, the 長期 limit "300 + γe2Df" category, rather than the sum of the printed
      terms (1186.56 + 1212.47).
    - qd = 343.74 = 300 + 11.571 × 3.78 uses the unrounded γe2. The printed 11.6 would give 343.85.
    - The term 1212.47 also uses the unrounded γe2 = 11.5714. With 11.6 it would be 1215.47.
16. **8-30, sign of Md.** Md is printed as an absolute value. For example, Md 長期 = |−610 + 6.5 + 19.25|
    = 584.25.
17. **8-30, label 'γi･Pd／qd'.** It uses Pd1, the maximum (267.51 / 343.74 = 0.778), not pd (262.20).
18. **8-30, Pd units.** Pd1 / Pd2 are printed with the unit `kN/m3`; kN/m2 is expected.
19. **8-30 and 8-32, Rhb.** Rhb = frs·Vd·tanφ appears to be rounded to 0.1 and then printed with 2
    decimals: 4892.03 → 4892.00 and 6758.05 → 6758.00.
20. **8-30, Mmd.** 設計最大ﾓｰﾒﾝﾄ Mmd has no unit or formula printed. The values were transcribed but
    cannot be derived from this PDF.
21. **8-18, flowchart.** The flowchart boxes are truncated in print. Only the text was kept.

## Not transcribed
- The diagram geometry of 8-6 to 8-8 (arrow drawings): only the printed values and a short note are
  kept.
- Rows or columns printed entirely as '-' in the check sheets are omitted (listed under
  `omitted_rows`).

## Classification 3: the sample does not reduce the impact on the pier body (decision 77)

- 08 uses the girder impact coefficients as they are (8-5: 0.245 / 0.546, double 0.222 / 0.521, serviceability
  0.184 / 0.410, 0.167 / 0.391). WebPier applies RC標準 解4.4.4 to every vehicle
  (Example橋脚3 Ⅱ-2-6): i = i0 × (1 − Ds/(L + Du + Ds)), with the ratio 0.751 (single) and 0.763 (double) for this pier
  (Ds 2961.88, Du 8380.00, L 567.39 / 1134.78).
- The transcribed values stay as printed. The values that no longer agree with WebPier, and are therefore not
  compared with it (the tests use an independent hand calculation, `tests/calc/test_longitudinal_loads.py`):
  - 8-5 impact loads I1 227.78 / 86.99 and I2 428.28 / 168.11 (WebPier: 171.05 / 65.33 and 326.85 / 128.53).
  - everything that adds the impact load: the 8-6 to 8-9 load diagrams I1 / I2, the 8-10 combinations, the
    8-11 onward sectional forces and reactions of the combinations with an impact load.
- Not affected: the train load (8-4), the bearing forces (8-5 horizontal), the girder wind, and the seismic
  stages.
