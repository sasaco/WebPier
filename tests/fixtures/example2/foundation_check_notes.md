# Foundation check (0612 / 0622, decision 54) — hand-calculation notes

Basis: an independent hand calculation; never generated from the application. Nothing under `webpier/` and
no foundation-check test was read or imported. The only sources are:
- the equations of decision 54;
- the sample pages 8-27 to 8-32 (`08_線路.pdf`) and 9-24 to 9-29 (`09_直角.pdf`), through
  `longitudinal.json` / `transverse.json`, with a spot check against the PDF text layer of 8-30 and 9-27.

Output: `foundation_check.json`.

## How the values were obtained

- A small stand-alone Python script with `decimal.Decimal`.
- Every printed quantity is rounded once, half away from zero, to its printed digits. Later steps use the
  rounded value (ADR-0003).
- Not rounded, because they are not printed: 6ex/B, the ratio B′/L (or L/B′), tanφ, and the base 1 − δ/φ
  before squaring.
- δ = atan(Hd/Vd) is evaluated in float from the printed Hd and Vd, then rounded to 3 decimals. The nearest
  case to a rounding boundary is 1.20086 → 1.201, so float error cannot matter.
- tan(42.2°) is a float converted with `Decimal(repr(...))`.
- Two products fall exactly on a half and are rounded away from zero:
  - 0612 short term term_γ = 0.50 × 1.000 × 0.345 × 6.956 × 10.0 × 150 = 1799.865 → 1799.87;
  - sample 8-30 Rvd = 238495.725 → 238495.73.
  The sample prints both values the same way.

### Actions

- Vd = −fy, Hd = |fx|, Md = |mz| at the footing-bottom support node. Each is rounded to 2 decimals from the
  CSV strings given in `inputs.reactions`.
- Values such as −6.991E-66 give Hd = 0.00 and δ = 0.000.

### Cover soil γe2 (Df = 4.700)

| water level | hw | wet segment Df − hw | submerged segment hw | γe2 |
|---|---|---|---|---|
| normal (long term) | 2.700 | 2.000 | 2.700 | (2.000 × 18.0 + 2.700 × 9.0) / 4.700 = 12.83 → **12.8** |
| high (short term, safety) | 3.780 | 0.920 | 3.780 | (0.920 × 18.0 + 3.780 × 9.0) / 4.700 = 10.76 → **10.8** |

The long-term limit is 300 + 12.8 × 4.700 = **360.16**. In both directions the long-term qd_unlimited
(2914.36 / 2919.76) exceeds it, so the long-term qd = 360.16.

### Equations

The equations are the ones in decision 54 and the task statement:

- ex = Md/Vd;
- B′ = B − 2ex; A′ = B′·L;
- trapezoid when ex ≤ B/6 (true for all eight columns, so x = B);
- Iγ = (1 − δ/φ)²; Iq = (1 − δ/90)²;
- βb = 0.5 − 0.2·r, with r = B′/L, or L/B′ when B′ > L;
- Be = min(B′, L);
- term_γ = frγ·Iγ·βb·Be·γe1·Nγ; term_q = frq·Iq·γe2·Df·(Nq − 1);
- qvd = term_γ + term_q; qd = qvd + γe2·Df;
- Rvd = A′·qvd + γe2·Df·A′;
- Mmd = Vd·B/2·(1 − Vd/(qd·B·L));
- Rhb = frs·Vd·tanφ.

Ratios:

- Long and short term:
  - bearing = γi·γa·pd1/qd;
  - rotation = γi·γa·ex/limit, with limit B/6 or B/4 printed to 3 decimals (1.167 / 1.750 for 0612,
    1.500 / 2.250 for 0622).
- Safety:
  - vertical = γi·γa·Vd/Rvd;
  - rotation = γi·γa·Md/Mmd.
- Horizontal: γi·Hd/Rhb with γi = 1.0 and no γa.

### Fields in the JSON

- `qvd` is always the sum term_γ + term_q, also for the long term. The cap acts only on `qd`.
- `rvd` and `vertical` are null except in the safety columns.
- `bearing`, `rotation_limit` and `rotation_ex` are null in the safety columns.
- `rotation_moment` is null except in the safety columns.
- `mmd` is given for all four columns because the sample prints Mmd in every column.
- `judgement` is an addition to the requested fields. It records OK/NG per ratio (OK when ≤ 1.000). Every
  ratio of 0612 and 0622 is OK.

### WebPier actions compared with the sample actions

These differences are recorded, not investigated here.

- 0612, compared with 8-30:
  - Long term: Vd, Hd and Md are identical.
  - Short term: Vd 18788.39 vs 18788.17; Md 408.40 vs 408.49.
  - Safety, vertical maximum: Vd 22585.15 vs 22585.12; Md 4767.97 vs 4767.98.
  - Safety, moment maximum: Vd 21870.78 vs 21870.77; Md 5460.44 vs 5460.42.
  - Hd is identical in all four columns.
- 0622, compared with 9-27:
  - Vd: the long term and the moment maximum are identical (16348.95, 20045.00). The short term (18788.38)
    and the vertical maximum (22585.13) differ by 0.21 and 0.01.
  - Hd and Md differ (wind, decisions 12 and 35).

## Reproducing the sample's resistance side

The same equations were fed the sample's own inputs:

- Df = 3.78;
- γe2 = 11.6 (normal, long term) and 9.0 (high);
- the printed Vd, Hd and Md of 8-30 and 9-27;
- for the long term, qvd printed as the cap 300.00 and qd = 300 + γe2·Df.

These deliberate differences from the sample were kept:

- the printed ex everywhere;
- Be = min(B′, L);
- the printed γe2 in the long-term qd;
- Rhb rounded once to 2 decimals.

The αb, c, Nc and average pd rows were not recalculated: WebPier does not print them.

### 8-30 (longitudinal, vertical support)

Matches, all four columns unless noted:

- ex 0.036 / 0.022 / 0.211 / 0.250;
- B′ 6.928 / 6.956 / 6.578 / 6.500; A′ 62.352 / 62.604 / 59.202 / 58.500;
- δ 0.000 / 0.000 / 1.201 / 1.297; x = 7.000;
- Pd1 267.51 / 303.85 / 423.33 / 421.55; Pd2 251.50 / 292.60 / 293.66 / 272.76;
- Iγ 1.000 / 1.000 / 0.944 / 0.939; Iq 1.000 / 1.000 / 0.973 / 0.971;
- βb 0.346 / 0.345 / 0.354 / 0.356;
- term_γ 1186.56 / 1799.87 / 2209.20 / 2183.71, since Be = B′ here because B′ < L;
- term_q, short term and safety: 1428.84 / 1862.95 / 1859.12;
- qvd: 300.00 (long, cap) / 3228.71 / 4072.15 / 4042.83;
- qd, short term and safety: 3262.73 / 4106.17 / 4076.85;
- Rvd 243093.48 / 238495.73; γi·γa·Vd/Rvd 0.134 / 0.132;
- γi·Pd/qd 0.778 / 0.093;
- rotation limits 1.167 / 1.750; γi·γa·ex/limit 0.031 / 0.013;
- Mmd, short term and safety: 59748.03 / 72146.55 / 70029.45;
- γi·γa·Md/Mmd 0.095 / 0.112.

Differences, long-term column only:

- **term_q 1215.47 vs 1212.47.** The sample uses the unrounded γe2 = 11.5714…:
  0.33 × 11.5714 × 3.78 × 84 = 1212.47. With the printed 11.6 the result is 1215.47.
- **qd 343.85 vs 343.74.** 300 + 11.6 × 3.78 = 343.848 → 343.85, while the unrounded γe2 gives 343.74.
  (longitudinal_notes.md item 15 also gives 343.85.)
- **Mmd 14035.80 vs 14021.98.** Feeding qd = 343.74 into the same formula gives exactly 14021.98. The
  Mmd formula is therefore confirmed, and the only difference is qd.

The long-term bearing ratio is unaffected: 267.51 / 343.85 = 0.77799 → 0.778, as printed.

### 8-32 (longitudinal, horizontal support)

Matches:

- Vd / Hd / Md;
- ex;
- Rhb 5621.90 (short) and 6544.30 (moment maximum);
- γi·Hd/Rhd 0.000 / 0.000 / 0.070 / 0.076, so all four ratios are OK.

Differences:

- **B′ 6.928 / 6.956 / 6.500 vs 6.929 / 6.957 / 6.501.** The sample rounds B − 2·(unrounded ex). The third
  column is 6.578 either way.
- **A′ 62.352 / 62.604 / 58.500 vs 62.361 / 62.613 / 58.509.** The sample's A′ is its own B′ × 9.000.
  These cells do not enter the ratio because c′ = 0.
- **Rhb 4892.03 vs 4892.00 (long term), and 6758.05 vs 6758.00 (vertical maximum).**
  - The unrounded values are 4892.026 and 6758.049.
  - The sample rounds to 0.1 and prints 2 decimals.
  - 5621.904 and 6544.297 give the same value either way.

### 9-27 (transverse, vertical support)

Matches:

- ex 0.000 / 0.084 / 0.153 / 0.519;
- B′ 9.000 / 8.832 / 8.694 / 7.962; A′ 63.000 / 61.824 / 60.858 / 55.734;
- δ 0.000 / 0.000 / 0.494 / 2.278; x = 9.000;
- Pd1 259.51 / 314.93 / 395.06 / 428.26; Pd2 259.51 / 281.52 / 321.93 / 208.09;
- Iγ 1.000 / 1.000 / 0.977 / 0.895; Iq 1.000 / 1.000 / 0.989 / 0.950;
- βb 0.344 / 0.341 / 0.339 / 0.324, with r = L/B′ because B′ > L in every column;
- term_q, short term and safety: 1428.84 / 1893.58 / 1818.91;
- qvd long 300.00 (cap);
- rotation limits 1.500 / 2.250; γi·γa·ex/limit 0.000 / 0.037;
- γi·Pd/qd long 0.755;
- γi·γa·Md/Mmd, vertical maximum: 0.053.

Differences caused by **Be**. Here Be = min(B′, L) = L = 7.000 in every column, but the sample uses B′
(transverse_notes.md item 14).

| quantity | this calculation | sample |
|---|---|---|
| term_γ | 1191.96 / 1790.25 / 2330.01 / 2040.01 | 1532.52 / 2258.78 / 2893.88 / 2320.36 |
| qvd (short, safety) | 3219.09 / 4223.59 / 3858.92 | 3687.62 / 4787.46 / 4139.27 |
| qd (short, safety) | 3253.11 / 4257.61 / 3892.94 | 3721.64 / 4821.48 / 4173.29 |
| Rvd | 259109.63 / 216969.12 | 293425.63 / 232594.14 |
| γi·Pd/qd short | 0.097 | 0.085 |
| γi·γa·Vd/Rvd | 0.126 / 0.133 | 0.111 / 0.124 |
| Mmd (short, safety) | 76796.04 / 93075.46 / 82830.14 | 77771.81 / 94076.27 / 83325.40 |
| γi·γa·Md/Mmd, moment maximum | 0.181 | 0.180 |

Substituting the sample's Be = B′ into the same equations reproduces every sample value in this table:

- term_γ 1532.52 / 2258.78 / 2893.88 / 2320.36;
- qvd 3687.62 / 4787.46 / 4139.27; qd 3721.64 / 4821.48 / 4173.29;
- Rvd 293425.63 / 232594.14;
- ratios 0.085 / 0.111 / 0.124;
- Mmd 77771.81 / 94076.27 / 83325.40;
- rotation ratios 0.053 / 0.180.

The rest of the 9-27 sheet is therefore consistent with these equations.

Differences in the long-term column, the same as in 8-30:

- term_q 1215.47 vs 1212.47;
- qd 343.85 vs 343.74;
- Mmd 18046.03 vs 18028.26. With qd = 343.74 the formula gives 18028.26.

### 9-29 (transverse, horizontal support)

Matches:

- Vd / Hd / Md;
- ex;
- Rhb 5621.90 (short);
- γi·Hd/Rhd 0.000 / 0.000 / 0.029 / 0.133.

Differences:

- **B′ 8.832 / 7.962 vs 8.833 / 7.961**, and **A′ 61.824 / 55.734 vs 61.831 / 55.727**. As in 8-32, the
  sample uses the unrounded ex and its own B′ × L. The vertical-maximum column is 8.694 / 60.858 either way.
- **Rhb 4892.03 vs 4892.00, 6758.05 vs 6758.00, and 5997.98 vs 5998.00.** The sample rounds to 0.1.

## Classification 3: the reactions come from the sample's FrameWeb file (decision 77)

- The reaction CSV strings in `inputs.reactions` are the sample's, whose impact loads have no pier-body reduction. They are
  fixed inputs here, so these values are unchanged. The input that WebPier itself writes for the frame analysis now has the
  reduced impact loads, so its reactions differ from these (re-accepted with the real runners, see the acceptance records).
- Decision 120 changed the combinations of the 0612 short-term and safety columns (each check at low and high water,
  the short term the edge-stress check): the acceptance compares only the long-term column with 8-30 (its combination by
  the check, 長期支持) and holds the others to the hand sum of the loads of the combination WebPier picks
  (classification 3). The hand values of those three columns above are kept as transcribed; the acceptance test
  no longer checks them.
