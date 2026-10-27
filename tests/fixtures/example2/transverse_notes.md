# 09_直角.pdf (§9 線路直角方向の計算（地震時以外）) — transcription notes

Basis: independently transcribed from the user-provided PDF; never generated from the application.
Source: `.claude/docs/Example橋脚2/09_直角.pdf`, 29 pages, printed 9-1 to 9-29. All pages transcribed
(model, actions and combinations in `sections`; 9-16 onward in `checks`).

## How it was transcribed

- Every page was rendered and read visually. The rotated table on 9-14 and the section-force tables on
  9-16 and 9-17 were also rendered at a higher resolution.
- The cross-check was the same as for 08:
  - All 838 values on pages with a text layer matched the PyMuPDF tokens of their page. The only misses
    are values grouped under "9-24" that are printed on 9-25.
  - The 9-14 combination table was rebuilt from word coordinates: 0 mismatches.
- Image-only pages are 9-16, 9-17, 9-19, 9-21 and 9-23.

## Section procedure and digit conventions

### 9-1 Frame model
- Same node and member scheme as 08: nodes 1 to 6, members 1 to 5, heights 2.000 / 0.700 / 4.900 /
  1.350 / 1.350.
- Width dimensions:
  - Beam 9.000, with haunch projections of 2.250 each side.
  - Column 4.500.
  - Footing 2.250 + 4.500 + 2.250 = 9.000; lower dimension 4.500 + 4.500 = 9.000, which is consistent.
- Springs: Kv and Ks are the same as 08. Kr = 86,320,647 / 172,641,294.

### 9-2 Section properties
- b = 2.70, h = 4.50 (swapped from 08). A = 12.150. I = 20.50313 (5 decimals; 20.503125 exact).
- f'ck and Ec are given for both く体 and ﾌｰﾁﾝｸﾞ.

### 9-3 and 9-4 D1, D2, buoyancy, snow
- Per-girder rows: RB G1 to G4 with arms ∓3.800 / ∓1.500, and RC G1 / G2 with arms ∓2.950.
- 鉛直力 has 2 decimals, アーム 3, ﾓｰﾒﾝﾄ 2.
- The rows are symmetric, so 合計 M = 0.00. The RB and RC sums equal 08's RB and RC (5740 / 1860, 520 /
  260, and so on).
- Footing D1 is labelled `W3` here (`P` in 08).

### 9-5 Train
- 鉛直力 = 反力 (272.47 RB, 294.92 RC, from 08) × distribution factor (3 decimals).
- Single track has up (上り) and down (下り) mirror tables, giving M = ±1210.08. Double track gives
  M = 0.00.

### 9-6 Impact
- Each girder's train 鉛直力 from 9-5 × impact coefficient: 0.245 (RB) / 0.546 (RC) single track,
  0.222 / 0.521 double track. The total is labelled Σ.

### 9-7 Vehicle lateral load (LF)
- H = 52.71 + 58.98 = 111.69 kN.
- M = (52.71 + 58.98) × 3.85 = 430.01 kN·m. The arm 3.85 is from the pier top to the beam axis.

### 9-7 and 9-8 Wind
- H at the pier top:
  - With train: 197.00 + 108.88 = 305.88.
  - Without train: 394.00 + 217.75 = 611.75.
- Hw1 on the pier body = pressure × 2.70: 1.5 × 2.70 = 4.05 and 3.0 × 2.70 = 8.10, in kN/m.
- The M table lists:
  - girder horizontal forces × arm (2.050 起点, 2.025 終点);
  - shelter vertical couples, G1 to G4 and RC G1 / G2.
- Each M is a sum of products (1001.33 / 2002.64).
- Per 9-12, Hw1 acts over 6.520 m below node 1 and stops 1.080 m above node 4.

### 9-9 to 9-12 Load diagrams
- Cases 1 to 17 as in the basic-case list.

### 9-13 Basic and Define cases
- 17 basic cases and 15 Define cases.
- Define 9 = basic {9, 10} (single track up and down) and Define 11 = {12, 13}. Define 13 to 15 have
  ± entries (LF, W1, W2).

### 9-14 Combinations
- 16 rows × 15 columns. The columns are **Define** case numbers 1 to 15 of 9-13, not the 17 basic cases.
- Coefficient digits are as in 08.

### 9-15 Extraction cases
- Same grouping as 08.

### Checks
- Section forces at member 3, JTAN 4.900.
  - Comb 3 (風最大) governs 安全性.
  - V 797.47 = 1.2 × (611.75 + 8.10 × 6.52), so Hw1 acts over 6.52 m.
- Foundation tables 9-27 and 9-29: 長期 = comb 14, 短期 = comb 15 (Md 1572.67 = 1210.08 + 0.75 × 483.45),
  鉛直力最大 = comb 10, 曲げ最大 = comb 12 (Vd 20045.00 and Hd 797.47 reconcile). The mapping is
  inferred.

## Ambiguities and inconsistencies (flagged, not resolved)

1. **9-5, single track (上り).**
   - The 鉛直力 parts sum to 567.38, but 567.39 is printed (08's total).
   - The printed parts' moments sum to 1210.095 → 1210.10, but 1210.08 is printed.
   - Individual moments sometimes match the rounded 鉛直力 × arm (G2 −71.93 from −71.925), sometimes
     the unrounded value (RC G1 −124.41, RC G2 745.60). RB G4 487.66 matches neither (487.654 rounded,
     487.667 unrounded).
   - Hidden-precision distribution factors are likely.
2. **9-5, double track.**
   - 272.47 × 0.549 = 149.586 → 149.59, but 149.58 is printed.
   - The parts sum to 1134.76; 1134.77 is printed.
   - G1 M 466.95 matches neither 122.88 × 3.8 (466.94) nor the unrounded value (466.96).
3. **9-6, impact.**
   - 42.17 × 0.546 = 23.025 → 23.02, but 23.03 is printed (it holds with unrounded 42.1736).
   - RC G1 M −67.93 matches neither 23.03 × 2.95 (67.94) nor the unrounded value (67.92).
   - 407.1 is printed with **1 decimal** (digits = 1) on both up and down tables, while every other value
     has 2.
   - Σ M 483.45 equals the sum of the printed parts, not of the unrounded ones (483.46).
4. **9-7 and 9-8, wind labels.** The H lines carry the label "橋脚天端～梁軸芯のトルクによる鉛直力",
   but the quantity is a horizontal force. The heading "橋脚天端に作用する荷重" on 9-8 has no content
   under it.
5. **9-7 vs 9-8, wind table layout.**
   - On 9-7 the 終点側 horizontal 28.88 (arm 2.025) is printed on the "シェルター" line, and the "桁"
     line is empty.
   - On 9-8 the equivalent 57.75 is on the "桁" line.
   - The 起点側 girder H in the M table (57.00 / 114.00) differs from the first H term (197.00 /
     394.00). Likewise 28.88 / 57.75 differ from 108.88 / 217.75; each gap is 140 / 80 and 280 / 160.
   - So the pier-top H includes shelter horizontal forces that are not itemised in the M table.
6. **9-7, Hw1 unit.** Hw1 is printed in `kN` on 9-7 but `kN/m` on 9-12.
7. **9-9 to 9-12, unit misprints.**
   - Case 1 prints N, M and P in `kN/m`.
   - Cases 3 to 5 print P in `kN/m`.
   - Cases 15 to 17 print M in `kN`.
   - Units are stored as printed, with "(printed)".
8. **9-13 vs 9-14, symbols.** Define 10 and 12 have the symbols `L3` and `I3`, but the 9-14 column
   headers print `L2` and `I2`.
9. **9-14, row 9 (復旧性 雪最大).** It includes W1 (wind with train) = 1.0 but no train load. This is
   transcribed as printed.
10. **Section numbering.**
    - Checks go from 9.6 to 9.9 with no 9.7 or 9.8 (durability and serviceability are not in this
      chapter).
    - The foundation heading on 9-24 is printed "8.7 基礎の照査", copied from chapter 8.
11. **9-17, comb 3 moment.** M 8256.60 does not reproduce exactly. 1.2 × (611.75 × 7.6 + 2002.64 +
    52.812 × 4.34) = 8257.37, so the Hw1 resultant arm or extent appears to differ slightly from
    6.520 / 1.080. This is unexplained and low priority.
12. **9-22 vs 9-23, γi.** The text says γi = 1.0, but the sheet prints γi = 1.20 and the ratio 0.098 =
    1.2 × 3955.8 / 48663.2. The row label is "Mu" for My.
13. **9-23, bar placement.** Side bars are Ase = 23031.80 (D32-29本, dase 2250.0) and main bars D19-9本.
    These are the 08 bars swapped, consistent with the rotated section.
14. **9-27, Be.** Be appears to use B′ even when B′ > L, contradicting the text "B′, L のうち小さいほう".
    For example 1532.52 = 0.33 × 1 × 0.344 × **9.0** × 10 × 150; Be = L = 7 would give 1191.96. The
    same holds for all 4 columns. αb and βb do use L/B′ (1.156 / 0.344), as the text says.
15. **9-27 vs 9-29, ex rounding.** 9-27 uses ex rounded to 3 decimals for B′, A′ and Pd1 / Pd2
    (8.832 / 61.824). 9-29 uses the unrounded ex (8.833 / 61.831, 7.961 / 55.727).
16. **9-27, 長期 column.** qvd 300.00 is the cap, and qd 343.74 uses the unrounded γe2 = 11.571. This is
    the same as 08 (item 15 there).
17. **9-27, 'γi･Pd／qd'.** It uses Pd1. 9-27 Pd1 / Pd2 are printed in `kN/m3`.
18. **9-29, Rhb.** Rhb is rounded to 0.1 (5997.98 → 5998.00, 4892.03 → 4892.00).
19. **Mmd.** No formula or unit is printed for 設計最大ﾓｰﾒﾝﾄ Mmd.
20. **9-1, Ks short.** 8,525,475 ≠ 2 × 4,262,769. This is the same as 08.

## Not transcribed
- The arrow geometry of the load diagrams is kept only as a note.
- All-'-' rows and columns of the check sheets are omitted (`omitted_rows`).
- Pages 9-24 to 9-26 and 9-28 are text identical to 8-27 to 8-29 and 8-31. They are summarised, not
  copied verbatim.

## Classification 3: the sample does not reduce the impact on the pier body (decision 77)

- 09 uses the girder impact coefficients as they are (9-6: 0.245 / 0.546, double 0.222 / 0.521, serviceability
  0.184 / 0.410, 0.167 / 0.391). WebPier applies RC標準 解4.4.4 to every vehicle
  (Example橋脚3 Ⅱ-2-6): i = i0 × (1 − Ds/(L + Du + Ds)), the ratio 0.751 (single) and 0.763 (double) here.
- The transcribed values stay as printed. The values that no longer agree with WebPier, and are not compared with
  it (the tests use an independent hand calculation, `tests/calc/test_transverse_loads.py`):
  - 9-6 impact loads: single track 227.78 / ±483.45 (WebPier 171.05 / ±363.04), both tracks 428.28 (WebPier 326.86).
  - everything that adds the impact load: the 9-9 to 9-13 load diagrams I1 to I3, the 9-14 combinations, the
    9-16 onward sectional forces and reactions of the combinations with an impact load.
- Not affected: the train load (9-5), the horizontal actions, and the seismic stages.

## Classification 3: one loading of each check with the train and one vehicle lateral load (decision 106)

- 9-14 (H16) makes the safety (列車最大・車横最大), damage and stability of both tracks only, and the crack (変動荷重) and
  short-term support of one track only, with one vehicle lateral load (one track's) in every combination. WebPier makes
  every check with the train for 複線 and 単線 (Example橋脚4 表4.3.2, R5) and puts the vehicle lateral load of two tracks
  (twice the one track's, Example橋脚4 III-177) in 複線: 25 combinations, 18 basic cases, 16 Define cases.
- The tests compare Example2 with the combinations it prints (`tests/calc/transverse_support.py: example2_combinations`,
  `example2_coefficients`) and the FrameWeb file with Example2's numbering (`tests/frameweb_placing.py:
  example2_loading`, which also takes Lf1 for Example2's Lf); the acceptances read the same reference file
  (`tests/acceptance/reactions_by_hand.py: reference_frameweb`).
