# 08_線路 8.5〜8.9 — transcription notes (0611 柱の断面照査, decision 48, ADR-0008)

Independently transcribed from the user-provided sample `08_線路/WebDan.wdj` (what WebDan was given) and `08_線路.pdf`
pages 8-12 .. 8-26 (what it printed); never generated from the application. The pages were rendered to PNG and read
visually. `column_section_check.json` holds what WebPier must give Capacita for the Example2 input, and the values the
explanation pages and the result pages print.

## What is transcribed from the WDJ

- Check point (`points`, `bar`, `crack`): index 6 = member 3, `JTAN`, position 4.9 (the J end of the 4.900 m member,
  the column bottom). Only bending about z (`isMzCalc`) and shear in y (`isVyCalc`) are checked. The result pages
  print one column only, `3部材(4.900)` (8-15, 8-26).
- Member 3 (`members`): group 1 `柱`, B = 4500, H = 2700 mm, n = 1.
- Bars (`bar`): `rebar1` = `rebar2` = D32 × 29, cover (to the centre) 108, spacing 150; `sidebar1` = D19 × 9, the first
  one 350 from the face, spacing 250; `stirrup` = D22, 10 legs, pitch 150. The result pages agree (`D32-29本`,
  `dast 108`, `D19-9本`, 8-15 / 8-26).
- Extraction cases (`basic.pickup_*`, by the id of each row): bending 0 → 2 (縁応力度検討用), 1 → 3 (耐久性 永久),
  5 → 1 (安全性 破壊), 6 → 5 (復旧性 地震時以外); shear 0 → 2, 1 → 3, 2 → 4, 5 → 1, 6 → 5; every other row and
  every torsion row blank. The numbers are the extraction groups of 8-11 (1 FAILURE … 5 DAMAGE).
- Safety factors (`safety.safety_factor`): the six rows 0, 2, 5, 6, 7, 8 as they are, without `title` and without
  `S_rs` / `S_rb` (steel members; Capacita's RC defaults do not have them).
- Steel (`safety.material_bar`): SD390, fsy 390 / fsu 560 for the tension bars, side bars and hoops in both diameter
  ranges. The `bend` rows (bent-up bars, SD345 in the first range) are not used: the column has no bent-up bars.
- Concrete (`safety.material_concrete`): f'ck 27, Dmax 25. Pile factor: `pile-000` (使用しない).
- Crack conditions (`crack`): environment 1 (一般の環境) on both faces and for shear, appearance checked on both faces,
  ε'csd 300 × 10⁻⁶ on both faces, kr 0.5, k4 0.85.
- Standard (`basic`): specification1 id 0 (鉄道), specification2 id 1 (運輸機構, the H16 base in RcDan), JR-001
  selected, JR-004 not selected.

## Deliberate differences from the sample (decision 48)

- `shape` is written as the number 1. The sample writes `"矩形"`, which the current Capacita does not read
  (「有効な算出点がありません」); with `1` it calculates.
- The calculation marks of the sample on points 2, 7 and 8 (members 1 and 4) are not reproduced. Only the column
  bottom is checked; the beam, haunch, column top and footing are not.
- 復旧性のせん断 is checked and printed. The sample 8-25 (2) omits it because 安全性（破壊） is satisfied; that
  reasoning depends on the input, so it is not used.
- `print_section_force_checked` is true (the sample has false): Capacita prints the section force list that 8.5
  inserts, so the report of the sample input has 13 pages.
- JR-003 (円形断面) is not written; the column is rectangular.
- `calculate_torsional_moment` stays false (no torsion check), as in the sample.
- The sample's `bar.position` (`"6.250"`) is not written: the pickup import compares it with the point's position
  (4.9) and would refuse the WDJ. The sample's `steel` rows are not written either: an RC WDJ with `steel` is refused
  (WDJ-FORMAT-CONFLICT).

## Explanation pages versus result pages

- 8-14 (8.6 (1)): γi = 1.2, γb = 1.1; 8-16 (8.6 (2)): γi = 1.2; 8-19 (8.7 (1) 3)): γi = 1.0, k4 = 0.85;
  8-21 (8.7 (2)): kr = 0.5 (一般に0.5); 8-23 (8.8 (1) 3)): γi = 1.0 and the limit printed as 0.30.
- **Error in the sample (owner decision, 2026-10-18):** 8-25 (8.9 (1)) prints γi = 1.0, but the WDJ row 6 has
  ri = 1.2 and the result page 8-26 prints γi = 1.20 (γi·Md/Myd = 0.114). The owner confirmed that γi of
  復旧性（地震時以外） is 1.2 for bending and shear: the WDJ and 8-26 are right, and the 1.0 of 8-25 is an error that is
  not reproduced (ADR-0001). WebPier writes 1.2 to the WDJ and prints the same constant in 8.9 (1) (decision 48).
  γb = 1.0 agrees (8-25, 8-26).
- The RC標準 tables of the explanation pages (σsl1, σsl2, Wlim by environment) are Capacita's values and are not
  printed by WebPier (decision 48); the values used appear on the inserted result pages.

## Acceptance values (real Capacita)

- 8-15 安全性（破壊）曲げ: Md 4123.9, N'd 15089.9, Mu 41194.0, γb 1.10, Mud 37449.1, γi 1.20, γi·Md/Mud = 0.132 < 1.00.
- 8-26 復旧性（地震時以外）曲げ: Md 3619.6, N'd 14404.5, Mu 38260.8, γb 1.00, Myd 38260.8, γi 1.20,
  γi·Md/Myd = 0.114 < 1.00.
- These are what a real run on the Example2 input must print; the table layout and the 復旧性のせん断 pages are
  expected to differ from the sample.

# 09_直角 9.5〜9.9 — transcription notes (0621 柱の断面照査, decision 48)

`column_section_check_09.json` is transcribed the same way from `09_直角/WebDan.wdj` and `09_直角.pdf` pages 9-16 ..
9-23. The extraction cases, safety factors, steel, concrete, pile factor, crack conditions, standard and
calculation switches of the sample are the same as 08's (the two WDJ files have equal `basic`, `safety` and crack
rows), so they are not transcribed twice (`same_as_08`).

## What is transcribed from the WDJ

- Check point: member 3, `JTAN`, position 4.9 (the column bottom), only `isMzCalc` and `isVyCalc`. The sample has it
  as point 6 (`sample_index`): its PIK has no point inside member 3.
- Member 3: B = 2700, H = 4500 mm (08's section turned: bending across the track).
- Bars: `rebar1` = `rebar2` = D19 × 9, cover 102, spacing 250 (the 直角 main row); `sidebar1` = D32 × 29 with
  `side_cover` and `side_ss` blank (the 線路 main row, corner bars included: Capacita spaces them evenly between the
  main bars); `stirrup` = D22, 6 legs, pitch 150 (the 直角 hoop row). The result page 9-23 agrees (`D19-9本`,
  `dast 102`, `D32-29本`).

## Deliberate differences from the sample (decision 48, owner 2026-10-18)

- The point is 7, not 6: WebPier's 0620 wind load on member 3 (decision 12) ends 2.0 m above its J end, so
  FEMPython's PIK has a point at 2.900 m inside member 3, and Capacita numbers the points in PIK order. WebPier finds the point in the PIK (export.capacita.point_index).
- The corner D32 sit at 108 mm from both faces, inside the D19 at 102 mm, so the side bars of the table are 108,
  300 … 4200, 4392 (192, then 150, then 192 apart). As in the sample they are written by number only; the owner chose
  the sample's even spacing over an input error.
- 9.7 and 9.8 are printed. The sample has neither; Capacita (as the sample's WebDan) skips the serviceability check
  (WD-1901: no permanent bending moment, no tension) and the shear durability check (WD-1906: no permanent and
  variable shear force) across the track, because the permanent actions are symmetric. WebPier prints their headings
  and explanations with the reason they are omitted; 9.7 (1) (the flexural durability check Capacita does make) is
  printed with its pages. `skipped_by_capacita` lists the two sections.
- `shape` 1, only the column bottom, 復旧性のせん断, the section force list, no `bar.position` and no `steel` rows:
  as 08.

## Explanation pages versus result pages

- 9-18 (9.6 (1)): γi = 1.2, γb = 1.1; 9-20 (9.6 (2)): γi = 1.2. The text is 08's.
- 9-22 (9.9 (1)) prints γi = 1.0 against 1.20 on 9-23: the same error as 8-25, not reproduced.

## Acceptance values

- 9-19 安全性（破壊）曲げ: Md 8256.6, N'd 13264.1, Mu 32267.7, γb 1.10, Mud 29334.2, γi 1.20, γi·Md/Mud = 0.338. The
  side bars are not counted (Ase "-"), as in the current Capacita.
- 9-23 復旧性（地震時以外）曲げ: Md 3955.8, N'd 14404.5, My 48663.2, γb 1.00, Myd 48663.2, γi 1.20, γi·Md/Myd = 0.098.
- WebPier's 0620 wind differs from the sample's (decisions 12 and 35), so its Md and the ratios differ; N'd is the
  same, so the capacities are compared. The sample's own WDJ in the current Capacita gives Mud 29326.7 and Myd
  48634.5 (the same kind of small difference as 08).
