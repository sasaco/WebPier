# reaction.json transcription notes (Example橋脚2, PDFs 05 and 07)

Transcribed by hand from page images (130 dpi) and checked against PyMuPDF text tokens. Every numeric token in the text layer of each page is either in reaction.json or is a heading/section number, a subscript, or a coefficient inside a combination label (for example "0.8 LR", "1.23B", "kh=1.0"). The drawing dimensions 3800/150 (7-15) and 3850/100 (7-16) are only in the image, not in the text layer. No application code or output was consulted.

## Conventions observed
- PDF 05 has no printed page numbers. Its sections use `page: null` and `pdf_page` 1-4. PDF 07 prints "7 - 1" to "7 - 18".
- Digits: 05 reaction tables print kN to 1 decimal and train shares to 3 decimals. Share totals print to 1 decimal in 05 ("1.0", "2.0", "1.2") but to 3 decimals in 07 7-3 ("1.000", "2.000"). 05 shelter distribution tables print to 2 decimals, distances to 3, α to 2, ΣXi² to 3 and coefficients to 5. 07 formula lines print to 2 decimals, lever arms to 3, and iF and ρf to 3. Thousands use a space separator ("5 740.00"); it is removed in `value`.
- "※10kN切り上げ" (05 p3/p4) rounds the magnitude up to the next 10 kN and keeps the sign (-116.11 -> -120, 64.52 -> 70, 292.00 -> 300).
- Supports: RA/RB are the start girder's (20.0 m) start and end bearings, and RC/RD are the end girder's (10.0 m). In 05, each girder is F at its start end and M at its end end. The pier carries RB (movable) and RC (fixed); this is inferred from the bearing type labels in 7-5 to 7-12 and the HB/HC labels in 7.3.

## Per-section procedure and findings
- 05 p1 start girder: per-bearing tables. D1, D2, snow, wind and EQ are given directly; nothing is derived. Shelter D2 is 60/10/10/60 (sum 140) at the start end but 10/-10/-10/10 (sum 0) at the end end. The end-end table is printed that way; flagged as notable, not as an error.
- 05 p2 end girder: the end-end (movable) shares L1 0.686/0.543, L2 -0.029/0.257 and L1+L2 0.657/0.800 differ from the start end (0.857/0.143). Their printed totals 1.2 / 0.2 / 1.5 are 1-decimal roundings of 1.229 / 0.228 / 1.457, so they do not add to 1.0/1.0/2.0. G3/G4 cells are blank.
- 05 p3 shelter transverse, start side (9 frames S1-S9, S2 = 下束部): α×ΣHy summed gives Hdy; Mdy = Hdy × 3.952. Vertical reaction = ±Mdy × x/ΣXi² (ΣXi² = 33.380). Horizontal reaction = Hdy/4. Both are then rounded up to 10 kN. α prints 2 decimals, but α×ΣHy uses the exact α = 1 - d/18.750 (S3: 0.2333 × 252.90 = 59.01, not 0.23 × 252.90 = 58.17). Wind S2 ΣHy is 57.35, the same as the standard frames; only the seismic row has 552.52 at S2.
  - Wind: Hdy 258.08 equals the exact 258.075 (half-up), but the printed parts add to 258.09. Mdy 1019.91 = 258.075 × 3.952; using the printed 258.08 gives 1019.93.
  - Seismic: Hdy is printed as 1168.00, but the printed parts add to 1168.01 and the exact value from the printed ΣHy is 1168.012. This cannot be reproduced from the printed values. Mdy 4615.94 = 1168.00 × 3.952.
  - Vertical G2/G3 seismic 207.43 uses the unrounded coefficient 1.5/33.38. With the printed 0.04494 it would be 207.44.
- 05 p4 shelter transverse, end side (S1-S5, span 8.950, α = 1 - d/8.950): same procedure, with ΣXi² = 17.405, lever arm 3.955 (to 橋脚天端) and Hdy/2.
  - Wind Hdy 143.38 (exact 143.375). Mdy 567.05 uses 143.375; using 143.38 gives 567.07.
  - Seismic Hdy is printed as 632.24, but both the parts and 2.5 × 252.90 give 632.25. Mdy 2500.52 is not 632.24 × 3.955 (= 2500.51).
  - These suggest hidden unrounded Hy (≈126.4485). Allow about ±0.02 tolerance on these totals.
- 7-1 (1) support reactions are combined from 05:
  - RA D1 = 5000 + 740 = 5740, RA D2 = 520 + 140 = 660, RB D2 = 520 + 0.
  - RC D1 = 1460 + 400 = 1860, D2 = 260.
  - Snow is the 05 shelter totals.
  - Wind/EQ shelter totals are 0.0.
  - The L 使用性 row is the 2-decimal RA to RD from the formulas below, rounded to 1 decimal. The L 地震 row comes from 7-2 4).
- 7-1 (2)1) RA to RD use P = 160.00 per axle. RB is the moment of 4 axles at 16.625/14.425/1.625/-0.575 over 18.850. RA = 4P - RB. RC = P(7.425 + 9.625)/9.250. RD = 2P - RC. RB = 272.4668 and RD = 25.0811 unrounded.
- 7-2: ρf = 197/160 = 1.231 (exact 1.23125) and 160/160 = 1.000. Seismic train reaction = 32.0 kN/m × span × 1/2. The iF values repeat 05 p1/p2.
- 7-3 main girder reactions: girder + shelter = 合計 for D1 and D2 per G; the 05 tables are repeated. The start girder prints a 合計 column only after the B支点 columns; the end girder prints 合計 only for C支点, with none for D. RA = 2 × (1530 + 1340) = 5740.
- 7-4 longitudinal girder forces:
  - Long rail: 10 kN/m (or 8 kN/m) × L × 2 tracks.
  - Braking: (0.20 + 0.80/Lv·L)·T and starting: (0.19 + 0.76/Lv·L)·T, with Lv = 20.00 and T = 160.00. Braking governs.
  - Seismic: T = (D1 + D2 + S2) × Kh, summed over both bearings of each girder (RA + RB, RC + RD). The printed template "T = ( D1 + D2 + S2 ) ) × Kh" has an unbalanced parenthesis.
  - The heading "(1) 桁に働く水平荷重 #" has a stray "#".
- 7-5:
  - Seismic train inertia: T = (R + R) × μ, with μ = 0.20, using the 7-2 seismic train reactions.
  - Bearing rule for the movable bearing: T/n (n = 2), μ·Rm and 0.1·T/n are printed. The chosen H always equals T/n, which is less than μRm in every case.
  - Bearing rule for the fixed bearing: H = max(T - ½μRm, T/n), with μ = 0.1 printed as "0.1".
  - Rm (movable) uses RB-side loads: D1 5740, D2 520, S 460/740/820.
  - Rm (fixed) uses D1 1860, D2 260 and the end girder's snow.
  - 0.8LR uses T1 = 320.00 (the 8 kN/m value).
- 7-6 1.0LR: the label says "L + 0.75I", but the formula uses train × 2 × (1 + iF) with the fatigue/serviceability double-track iF (0.167 / 0.391), and no 0.75 appears. The printed Rm label is truncated ("複線 #") and a stray "0" sits after 可動支承に働く鉛直荷重.
- 7-6 to 7-11, fixed bearing: the train term uses 25.08 (= RD, the end girder's movable end in 7-1), not RC = 294.92, even though 7.3 assigns this pier's end-girder bearing to C (HC uses the RC formula). Flagged as possibly intentional, since a smaller Rm is conservative for T - ½μRm. Not resolved.
- 7-6 to 7-11, rounding: every Rm is computed with unrounded RB/RD.
  - 7-8 fixed: 2851.85 (with 25.08 it would be 2851.84). 7-11 fixed: 2613.85 vs 2613.84. 7-6 fixed: 2439.78 vs 2439.77.
  - 7-7 movable: 8576.98 vs 8576.99. 7-8/7-9 movable: 8497.07 vs 8497.08.
  - A checker must use unrounded RB/RD to reproduce the printed values.
- 7-7, 7-8 and 7-11 use the safety double-track iF (0.222 / 0.521).
- 7-9 1.0LR + 1.35B: the label says "1.23L" / "1.23複線L" (no I), but the formula still contains (1 + 0.222) and (1 + 0.521), and Rm equals 7-8's.
  - Decision 119: WebPier follows the label and leaves the impact out of this Rm (1.1D1 + 1.2D2 + 1.0 × ρ × L + S10), as in 0610's braking-maximum combination and Example橋脚4 III-45 to III-57. The values that depend on it (Rm, μRm, T − ½μRm, H at the fixed bearing, the 7-13 total) are tested by independent hand calculation, not against this page.
- 7-10 / 7-12 1.0LR: Rm uses S30, with 1.1/1.2 load factors in 7-10 and 1.0/1.0 in 7-12.
- 7-11 restorability: T1 = 1.0 × 400 + 1.23 × 160, but T2 = 1.0 × 200 + **1.0** × 96.00 = 296.00. That is inconsistent with the "1.23B" combination label; it would be 318.08 with 1.23. The 7-13 summary carries 165.31, which is derived from T2 = 296.00.
- 7-13 seismic: the movable bearing takes T1/n = 13580/2 = 6790 and the fixed bearing takes the full T2 = 4740. Train: 128/2 = 64 (movable) and the full 64 (fixed). Summary 合計 = 起点桁 + 終点桁 for every row (all check). Its "使用性 1.0 LR (2)" row = 7-6, "安全性 1.0 LR" = 7-10, "復旧性 1.0 LR" = 7-12.
- Decision 120: WebPier adds the reduced-dead-load cases (0.9D1 + 0.8D2) 1.1LR+1.23B and 1.0LR+1.35B (Example橋脚4 III-45〜57 ③⑤), which Example2 07 does not have; they are tested by independent hand calculation (classification 3, a different standard edition).
- 7-14 vehicle lateral: LF = 0.2 × 160.0 = 32.00 per axle.
  - HB = LF × (14.425 + 16.625)/18.85. Only 2 axles are used here, unlike the 4-axle RB in 7-1; the diagram differs.
  - HC = LF × (7.425 + 9.625)/9.25.
  - y1 = 0.15 + 2.60 + 1.100 (start) and 0.10 + 2.65 + 1.100 (end), both 3.850. M1 = H × y1.
  - The spans in the formulas print 18.85 / 9.25 (2 decimals), but the diagram prints 18.850 / 9.250.
  - The beam sketch prints the G spacing as 2.30/3.00/2.30 (05 p3 shows 2300/1500/1500/2300) and 5.90 for the end girder (05 p4 shows 2950 + 2950).
- 7-15 / 7-16 wind with train (ω1 = 1.5):
  - Girder part = ω × h × L / 2.
  - Shelter part = (05 horizontal wind reactions, 4 × 70 = 280 or 2 × 80 = 160) × 1/2. The origin of the 1/2 is not printed; it presumably equals 1.5/3.0, but that is not stated.
  - y1 = h/2 + 0.15 (or + 0.10). M1 uses only the girder part.
  - Labels: in 7-15 "HB" labels the girder part (57.00) and the total 197.00 is unlabeled; in 7-16 the total is labeled "HC = 108.88".
  - 28.88 is 28.875 rounded half-up.
- 7-17 wind without train (ω1 = 3.0): the shelter part is the full 280 / 160. M1 again uses the girder part only. 116.94 comes from 116.94375.
- 7-18 seismic transverse:
  - Kh = 1.00: girder part = 05 girder-only D1 + D2 (5000 + 520; 1460 + 260), with no snow. Shelter (死+雪) = 4 × 300 = 1200 and 2 × 320 = 640, from the 05 ceil-10 horizontal reactions.
  - y1 = 0.15 + 2.60 (or 0.10 + 2.65) = 2.750. M1 uses the girder part only.
  - The end-side total 2360.00 is labeled "HB" (presumably HC); the key is `seismic_transverse.end.total`, and `printed_label` keeps "HB".
  - Train with Kh = 0.30: H = 7-2 seismic train reaction (320 / 160) × 0.30, y1 = … + 1.100 + 1.500 = 5.350.
- Not present in 05/07: pier self weight, pier centroid heights, centrifugal load, and any explicit longitudinal wind. reaction.json lists these under `not_present_in_05_07`.

## Classification 3: the impact on the pier body (decision 77)

- 07 7-2 prints only the girder impact coefficients. Example橋脚3 Ⅱ-2-6 (2.1.5 (b), RC標準 解4.4.4) reduces them for the
  pier body: i = i0 × (1 − Ds/(L + Du + Ds)). WebPier prints that after the girder coefficients in 6.3 (2) and uses it in
  0610 / 0620. The values in this file are the girder coefficients and stay as printed; the pier-body coefficients have
  no sample value in Example2 and are checked by hand in `tests/calc/test_reaction_train.py`.
