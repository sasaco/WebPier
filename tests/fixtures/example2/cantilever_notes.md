# 13_片持ち梁照査 13.1〜13.2, 13.5 (1) — transcription notes (0900 / 0910, decision 59)

Independently transcribed from the user-provided sample `13_片持ち梁照査.pdf` (text and rendered pages 13-1 .. 13-37,
13-54, 13-55), the load workbook `07_荷重計算/朝里川Bv_P1_荷重計算.xlsm` (sheets §13.鉛直荷重, 水平荷重, 片持梁の自重,
荷重の集計, 作用の組合せ) and `13_片持ち梁照査/WebDan.wdj`; never generated from the application. `cantilever.json`
holds the values WebPier must reproduce for the Example2 input, the values it must give Capacita, and the values of
the sample that WebPier deliberately does not reproduce.

## What must match the sample exactly (same inputs, same logic)

- The three train loadings (13-1, 13-2): RB maximised, RC maximised, RB + RC maximised (0600's loading); B支点最大
  differs since decision 125 (below).
- The train on each bearing (13-3 .. 13-8): one track with the larger track share, both tracks with the double
  share, the impact with the girder coefficient of that track count; the cantilever carries the larger load.
- The vehicle lateral torque (13-9 .. 13-11): 0.2 × the maximised girder's reaction (B支点最大: 103.55 = 0.2 × 517.77,
  106.48 = 0.2 × 532.41 since decision 125;
  C支点最大: 83.37 = 0.2 × 416.86) at the rail height 3.850, ΣXi² = 2 × (1.5² + 3.8²) = 33.3800; for B+C支点最大 0600's
  one-car junction (52.71 / 58.98). The end girder's ±M/5.9000 is M × 2.95 / (2 × 2.95²).
- The seismic train torque (13-14): 96.00 = 320 × 0.300 at 5.350 (0600's values).
- The self weight (13-23) and the torsion arm Y = (2.000 + 0.700)/2 = 1.350.
- The seismic T of each girder (13-15, 13-20): 0.386 × 13580 + 128 = 5369.88 (origin) and 0.386 × 4740 + 64 =
  1893.64 (end); the torsion arm Y = 1.350.
- The combination table's factors, states, remarks and 摘要 (13-30 .. 13-37), and which rows of the WDJ force table
  are filled.

## Deliberate differences from the sample (decision 59)

- **Bearing forces along the track (decision 125, a known difference since 2026-10-30)**: `bearing_forces` and
  `actions.LRB` hold Example2 13's model (the rubber bearings Hbd = μ·Rm without a cap at the movable end, the
  stoppers max(T − ½μRm, T/n) at the fixed end, shared by the counts of the devices). WebPier follows Example橋脚4
  (R5, V-13〜V-25): each bearing of a girder end takes T / n (n its occupied bearing slots), capped by μ·Ni of its own
  vertical force in the case at a movable end, with T of the loading's train layout. The values are no longer
  compared with this transcription (which is kept unchanged); the new ones are fixed by hand calculation in
  `tests/calc/test_cantilever_bearings.py` (case 9: 149.20 and 100.00, the seismic case 204.07 (capped from 1342.47)
  and 946.82, Mt 1553.70), and they change the Mt of the cases with a bearing force (case 10: 1118.50, the sample
  1058.29). Decision 125 also adds four 使用性（損傷） cases (23〜26), so the sample's cases 23〜31 are WebPier's 27〜35.

- **B支点最大 (decision 125, a known difference since 2026-10-30)**: the sample (13-1 a)) sets P-16's four axles from
  the bearing B (levers 18.850, 16.650, 13.850, 11.650: RB 517.77, RA 122.23). The search of the RB maximum now counts
  an axle exactly at the girder joint on the origin girder (that of the RC maximum on the end girder; RB + RC as
  before, so 0600 is unchanged), and finds the axles at 19.425 (the girder end), 17.225, 14.425, 12.225 and −0.575:
  RB = 160 × 62.725 / 18.85 = 532.41, RA 267.59 (the same as 0600's layout ②, the origin girder only). The transcribed
  `loadings`, `train_per_bearing` (B支点最大), `torques.lateral` (B支点最大) and `actions.L/LF/I_ultimate` (B支点最大) are kept
  unchanged; WebPier's values are fixed by hand in `tests/calc/cantilever_support.py` (`ORIGIN_MAX_*`) and the tests
  that use them: G1 単線 0.471 × 532.41 = 250.77 (sample 243.87), G2 複線 292.29 (284.26), the impact 61.44 (59.75),
  the lateral force 106.48 at 3.850 m: M 409.95, G1 46.67 (45.38). The cases with B支点最大 (1, 4, 9, 12, 15, 19, 24,
  29, 33) change with them (case 9's Ni 2616.48).
- **The torsion of the bearing forces along the track (decision 125)**: added with the sign of the rest of the case's
  Mt (the forces act either way). Example2's Mt are all positive, so its values do not change.
- **End girder X**: the sample types 0.645 (荷重の集計 I4 = 1605 → 2250 − 1605); the bearing position gives
  2.95 − 2.25 = 0.700. Every Md of the sample's tables and combinations carries the 0.645, so the Md totals of
  `actions` and the Md of the combinations are checked by hand calculation, not against the sample.
- **Snow shelter**: the sample adds a shelter's share to the wind torque (±120 / ±50 per girder, halved with the
  train), the seismic girder torque (±530, ×Kh) and the seismic girder force (5520 = 5000 + 520 without snow; WebPier
  uses 0600's (D1 + D2 + S2) × Kh = 6720 × Kh). The input has no shelter; the wind and the girder inertia across the
  track are 0600's forces, heights and moments.
- **最大応答震度 across the track**: the sample uses 0.552 (Case 1, 安全性); WebPier takes the largest value of both
  blocks and every Case of Aggre-SE's summary workbook (0.571 for the current post/ workbook).
- **使用性 impact**: the sample's 13-26 (b) repeats the 安全性 impact (59.75 …); WebPier uses the 使用性 coefficients
  (0.184 / 0.167 / 0.410 / 0.391), so the 使用性 impact is smaller (ADR-0001).
- **Rounding**: products and sums use the printed parts (ADR-0003): 複線 G1 of B支点最大 517.77 × 0.451 = 233.51
  (sample 233.52), 単線 G1 of C支点最大 102.71 × 0.471 = 48.38 (sample 48.37), its impact at C支点最大 416.86 × 0.521 = 217.18
  (sample 217.19), 複線 G2 of B+C支点最大 272.47 × 0.549 = 149.59 (sample 149.58), I B+C支点最大 Mt 93.49 (sample 93.50),
  Rm of 1.0LR+1.23B 8576.99 (0600's
  printed parts; sample 8576.98), 地震時列車 Mt 43.58 (sample 43.57), I C支点最大 N 229.03 (sample 229.04), case 10 Mt
  1058.28 (sample 1058.29; 1118.50 since decision 125), case 24 Mt 1437.43 (sample 1437.42; WebPier's case 28,
  1782.91 since decision 125), Mcrd 7055.19 (sample 7053.1 from the unrounded I).
- **WDJ**: `shape` is the number 1 (the sample's "矩形" is not read by the current Capacita); the force table fills
  Vd6, Mt0, Mt1 and Mt6 too (the sample leaves them blank and so skips the restorability shear and the torsion
  durability checks); the `shear` table gives the shear span a = 1.55 m (the farthest cantilever bearing), written as La 1550 (mm,
  as RcDan reads it: La / d; 2026-10-19, a length in m had been taken for 1.55 mm) instead of
  the sample's `La: 1` on the point (to RcDan, La 1 means "from |Md / Vd|"); the point list has one point (the sample has nine, eight empty); `steel` rows
  are not written; `sidebar2.side_cover` 184 (the side bars' centre) is the cover the main bars' spacing
  (2700 − 2 × 184)/16 = 145.75 is measured from; ε'csd is 300 from 13-55 (the sample's WDJ holds 450).
- **ΣN**: Capacita computes it from the WDJ (`train_A_count` 60, `service_life` 100, NA 10.39); the external
  N-EQUIVALENT program's 10.39 is an input (片持ち梁の照査.疲労).
- **Factor of one**: the train and impact factor is ρ × γ at 0600's two decimals, so cases 27〜35 (the sample's
  23〜31) print `1.00` where the sample prints `1.0`.
- Decision 119 (before decision 125 replaced the model): the 1.0 LR + 1.35B bearing case took the train without impact in Rm (the label of 07 7-9 says "1.23複線L", but its formula has (1 + i)). The values from it (13 bearing forces and LRB actions of 1.0 LR + 1.35B: Hbd 849.71, per rubber 212.43, Hsd 187.01, per stopper 26.72, H 212.43, Mt 286.78) are tested by independent hand calculation, not against this sample. The transcription is unchanged.
