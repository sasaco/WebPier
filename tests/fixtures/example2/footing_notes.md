# Footing response values (0800, decision 60) — transcription notes

Source: `.claude/docs/Example橋脚2/12_フーチング.pdf` pp.244–253 (§12.1 応答値の算定, (1) 線路方向 and
(2) 線路直角方向) as printed, checked against the values of `12_フーチング/0700_線路フーチング.xls`
(sheets `地盤反力 (1)`/`断面力 (1)` and `(2)`), read with Excel COM. Nothing was computed by the
application. Output: `footing.json`.

## Columns

Five columns per direction: 安全性 Md最大 (`safety_moment`), 安全性 Vd最大 (`safety_shear`), 使用性 短期
(`short_term`), 使用性 長期 (`long_term`), 地震時 (`seismic`). `Vd`, `Hd`, `Md` are the sample's own
design response values at the footing base (the 線路方向 seismic column is JRSNAP's Rvd到達ステップ 31,
10-23: H 5747.860, V 16825.971, M 52784.781; the sample prints them to 2 decimals).

`qd` is the unlimited design bearing pressure `qvd + γe2·Df` (the workbook does not round it: 長期
2357.648, printed 2357.65; the seismic column 2507.158, printed 2507.16 as qd1). The sample's Df is 3.78 and
its γe2 9.0 (安全性・短期, high water) / 11.6 (長期・地震時, normal water); WebPier's input has Df 4.70 and
its own γe2, so `qd` and `Mmd` are inputs of the distribution tests, not reproduced from WebPier's input.
With the printed qd 2507.16 the 線路方向 seismic Mmd is 52617.46 (the workbook's unrounded qd gives the printed 52617.45);
WebPier uses the printed value (ADR-0003). In the 直角 columns with ex = 0 (使用性) B′ = B = 9 > L = 7, and the workbook's
Be is B′ there too (its term_gamma 2322.00 = 0.5 × 1.000 × 0.344 × 9 × 10 × 150), where 0612 takes L.

## Distribution (地盤反力形状)

Workbook formulas (`地盤反力 (1)` rows 43–49):

- `apex` (設計最大地盤反力度 qd1) = ROUND(2Vd / (3L(B/2 − ex)), 2), printed in every column;
- Case = 4 if Md > Mmd, else 3 if apex > qd, else 2 if ex > B/6, else 1;
- Case 1: qd1, qd2 = ROUND(Vd/(BL)(1 ± 6ex/B), 2), X1 = B, X2 = 0;
- Case 2: qd1 = apex, qd2 = 0, X1 = ROUND(2Vd/(apex·L), 3);
- Case 3: qd1 = qd, X2 = ROUND(√(12B·Vd/(qd·L) − 12Vd²/(qd·L)² − 24Md/(qd·L)), 3), X1 = ROUND(Vd/(qd·L) − X2/2, 3);
- Case 4: qd1 = qd, qd2 = 0, X1 = ROUND(Vd/(qd·L), 3).

Every sample column is Case 1 except the seismic ones (Case 4). The 線路方向 seismic X1 0.746 =
16825.97 / (2507.16 × 9) = 0.74569; the 直角 one 0.978 = 16825.97 / (2456.94 × 7).

## Overhang (3) 地盤反力による断面力)

`reaction` is the sample's row: q1 at the edge, q2, the loaded length (L1, or X1 when the block ends
inside the overhang), W = ROUND((q1 + q2)/2 · L1, 2), x = ROUND(L1(2q1 + q2) / (3(q1 + q2)), 3), M = ROUND(W·x, 2).
For the seismic Case 4 row the workbook uses W = ROUND(qd1 · X1, 2), x = L1 − X1/2 and prints no q2.

**Known error of the workbook**: its q2 is `ROUND(L1·(qd1 − qd2)/X1 + qd2, 2)`, the pressure at L1 from the
qd2 (far) edge, not at the column face of the q1 side (`qd1 − (qd1 − qd2)·L1/X1`; the two agree only when
L1 = X1/2). The sample's trapezoid rows, and the Md, Vd and La of the four non-seismic columns, carry this
value. They are transcribed as printed; which formula WebPier uses is an owner decision recorded in
decision 60 and README (Example2 との既知の差).

## 4) 自重・上載土, 5) 浮力

V = ROUND(height × L1, 2) per metre of width, W = ROUND(V × γ, 2), x = L1/2, M = ROUND(W × x, 2). The
buoyancy rows use the water level above the footing base as entered (hw1 3.78, hw2 2.70, hw3 0.00) and
γ = −10.0.

## 6) 7) Md, Vd, La

Md = M_per_m − M_self + (−M_buoyancy) with the full width (L of the direction: 9.000 / 7.000) and be.
安全性 uses the high-water buoyancy, 使用性 the normal one. The sample's 6) seismic Md uses the normal
water (62.46 / 68.40) but its 7) seismic Vd uses the high water (81.30 / 85.10; workbook `S143 = -V96`);
decision 60 takes the normal water for both, so WebPier's seismic Vd is 1870.34 − 219.75 + 58.10 = 1708.69
(線路方向) and 2402.89 − 229.96 + 60.80 = 2233.73 (直角), not the sample's 1731.89 / 2258.03. `La` is Md/Vd
printed to 3 decimals (the workbook keeps it unrounded; Capacita's 1127 mm is the rounded 1.127 m).

## Effective width (2) 有効幅

be = min(overhang across, d) + column width across + min(overhang across, d) ≦ full width, d = H6 − cover.
The sample's 直角 cover is 0.125 (d 2.575); WebPier's is the bar centre 0.127 (d 2.573), decision 60.

## Hand calculation `footing_hand.json` (decision 60, the owner's choice of the corrected q2)

A stand-alone Decimal script (not kept; nothing of `webpier` imported), ROUND_HALF_UP at every printed step,
later steps from the rounded values (ADR-0003). Inputs: the sample's columns above (`footing.json`).

- `columns.<key>.reaction`: the trapezoid of each non-seismic column with the corrected
  q2 = ROUND(qd1 − (qd1 − qd2) × L1 / X1, 2), W = ROUND((q1 + q2)/2 × L1, 2), x = ROUND(L1(2q1 + q2)/(3(q1 + q2)), 3),
  M = ROUND(W x, 2); then M_full = ROUND(M × full width, 2), M_per_m = ROUND(M_full / be, 2),
  Md = ROUND(M_per_m − M_self − M_buoyancy, 2) (M_buoyancy negative: 安全性 high water, 使用性 normal water), the
  same for V with W, La = ROUND(Md / Vd, 3). Example 線路方向 安全性 Vd最大: q2 = 423.33 − (423.33 − 293.66) × 2.15/7
  = 383.50, W = 867.34, x = 1.093, M = 948.00, Md = 948.00 − 236.24 + 87.40 = 799.16, Vd = 867.34 − 219.75 + 81.30
  = 728.89, La = 1.096.
- `seismic_own_input`: the seismic column of WebPier's own input (not the sample's Df): Df 4.700, γe1 10.0, γe2 12.8
  (normal water, as `foundation_check_notes.md`), φ 42.2, Nγ 150, Nq 85, 地盤抵抗係数 1.00, with V 16825.97,
  H −5901.07, M 54168.43 of step 3 of the stand-in step table (`tests/fixtures/aggrese/fake_runner.py`): ex, B′,
  A′, δ (float atan2, rounded to 3), Ir, Iq, βb (L/B′ when B′ > L), αb, Be = min(B′, L), the two terms, qvd,
  qd = qvd + γe2 Df, Mmd = ROUND(Vd B/2 (1 − Vd/(qd B L)), 2), the apex, then the Case by the workbook's tests and
  the segments of the profile within the overhang (block: W = q × ℓ, x = (L1 − ℓ) + ℓ/2; slope: q2 at the end of
  the segment, W and x as the trapezoid above but the centroid measured from the column face,
  x = (L1 − end) + ℓ(2q1 + q2)/(3(q1 + q2))). 線路方向 (B 7, L 9): Mmd 54123.35 < Md → Case 4, X1 0.567,
  W 1870.58, x 1.867, M 3492.37, Md 3318.59, Vd 1708.93, La 1.942. 直角 (B 9, L 7): Mmd 70192.49 > Md, apex
  1250.95 < qd 3660.57, ex 3.219 > B/6 → Case 2, X1 3.843 > L1 2.25: q2 = 1250.95 × (1 − 2.25/3.843) = 518.54,
  W 1990.68, x 1.280, M 2548.07, Md 2357.76, Vd 1821.52, La 1.294.
