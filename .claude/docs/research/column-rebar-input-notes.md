# Column Rebar Input: Requirements and Reference Evidence

Date: 2026-10-17. Planning slug: `column-rebar-input`.
Plan destination resolved by workspace.py: `.agents/docs/plans/column-rebar-input.md`.
Status: five user decisions confirmed; plan written, shape/existence validated and Codex adequacy review PASS. Implementation approval remains pending; product code and actual input have not been edited by this task.

## Confirmed user decisions

1. 専用画面を設け、必要ならJSON構造も整理する。
2. 基本入力（方向ごとの径・片面本数・間隔・かぶり）から自動配置し、必要箇所だけ詳細修正する。断面図と両方向の鉄筋配置表で確認する。
3. P7の実入力も指定原本の柱配筋に合わせる計画に含める。D32=29/面、D19=9/面、D22@150、方向別の有効本数10/6を対象とし、実入力変更は実装段階で行う。
4. 純かぶりから芯かぶりを自動計算し、必要箇所だけ芯位置を直接指定する。D19の102 mmは原本値として指定し、勝手な丸め則を追加しない。
5. 詳細修正後に基本条件を変えても修正済み配置を保持する。「再配置」で新旧を確認してから置き換える。

## Reference evidence

All page numbers below are physical PDF pages, confirmed by rendered-page inspection. Sources are local files, not design standards.

### Example bridge pier: longitudinal

`Example橋脚2/10_線路(耐震).pdf`, p6 (printed 10-6): section width 4500 mm, height 2700 mm.

- D32: 29 bars at depth 108 mm and 29 bars at depth 2592 mm.
- D19: 2 bars at each depth 350, 600, 850, 1100, 1350, 1600, 1850, 2100, 2350 mm.
- 11 table rows, 58 D32 bars plus 18 D19 bars, total 76 bars.
- Hoop/shear reinforcement: SD390, D22, count 10, pitch 150 mm.

### Example bridge pier: transverse

`Example橋脚2/11_直角(耐震).pdf`, p6 (printed 11-6): width 2700 mm, height 4500 mm.

- D19: 9 bars at depth 102 mm and 9 bars at depth 4398 mm.
- D32: 2 bars at each depth 108, 300, 450, 600, 750, 900, 1050, 1200, 1350, 1500, 1650, 1800, 1950, 2100, 2250, 2400, 2550, 2700, 2850, 3000, 3150, 3300, 3450, 3600, 3750, 3900, 4050, 4200, 4392 mm.
- 31 table rows, same diameter totals and total 76 bars.
- Hoop/shear reinforcement: SD390, D22, count 6, pitch 150 mm.

### Combined interpretation

Taking x along the 4500-mm side and y along the 2700-mm side, these two tables can be represented by one physical arrangement:

- D32: y=108/2592; x=108, 300..4200 in steps of 150, 4392.
- D19: x=102/4398; y=350..2350 in steps of 250.
- D32 edge gaps are 192 mm; interior gaps are 150 mm. Uniform spacing over the full span is not equivalent.
- Preserve the printed D19 center 102 mm as a reference value. Do not silently replace it with a calculated 101.5 mm or infer an unverified diameter/rounding rule.

### Competitor workflow

`output/visualizations/柱鉄筋入力.pdf` (12 pages):

- p2 (printed 53): direction-specific diameters, count per layer, cover, spacing; same-diameter corners may be shared. This is reference UI behavior, not automatically an adopted project rule.
- p3-p4 (54-55): multiple layers, face-specific side reinforcement and center-cover definition; distinguish same vs different diameters at corners.
- p5 (56): outer hoop and direction-specific internal hoops, separate lower and upper height zones.
- p11 (62): generate detailed rows from basic input, locally edit and mirror symmetric layouts.
- p6-p8, p12 also describe rounded corners, obround/skewed sections and bar cutoffs. Inclusion is undecided; do not import these features solely because the manual includes them.

## Implementation scope and remaining review

The five user choices above close the main input-workflow interview. The proposed initial scope is the referenced rectangular column, preserving existing multi-layer inputs and hoop height zones. New rounded/obround/skewed shapes, reinforcement cutoffs and structural resistance calculations are outside this input-usability change. The final written plan, after independent Codex validation, still requires user approval before implementation.

## Proposed generation rules grounded in the reference

Keep the existing full-span equal-spacing rule for legacy input. Add fixed-pitch centered distribution and fixed end bars with centered fixed-pitch interior bars as explicit choices. For 29 D32 bars across 4500 mm with endpoints 108/4392, the 27 interior bars at pitch150 occupy 300..4200 and leave 192-mm end gaps. For 9 D19 bars along 2700 mm, centered pitch250 produces 350..2350. Normal-to-face cover and along-face distribution must be separate quantities. These are general rules, not sample-coordinate conditionals.

## Environment and boundaries

Shared `.agents/rules`, `.agents/STATE.md`, `PROGRESS.md`, `.agents/docs/DESIGN.md` are absent. Root CONTEXT.md, project README, source/tests and prior authorized workflow are available. Existing dirty product files and inputs must be preserved during planning. Only planning/reference/glossary documentation and scratch PDF renders have been added in this task.
