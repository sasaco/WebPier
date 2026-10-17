# Document schema v1

この文書は SoilStructure GUI と Headless が共有する JSON 入力の、現行実装で確認した意味を記録する。JSON は UTF-8（BOMなし）、文書上限は 1 MB、1セルは 256文字以内である。

## Root and pile

| Field | Meaning |
|---|---|
| `schemaVersion` | 固定値 `1` |
| `pileType` | `4` 鋼管ソイルセメント、`5` 回転杭、`6` 場所打ち杭 |
| `constructionMethod` | 杭種6だけ必須。`naturalSlurry` または `stabilizingFluid`。杭種4/5は `null` |
| `pile.diameterM` | 杭径 (m) |
| `pile.lengthM` | 杭長 (m) |
| `pile.embedmentDepthM` | 地表から杭頭までの根入れ深さ (m) |
| `pile.groundwaterDepthM` | 地表から下向き正の地下水位深さ (m) |
| `pile.unitWeight` | 杭種4/5は単位長さ重量 (kN/m)、杭種6は単位体積重量 (kN/m3) |
| `pile.stiffness` | 杭種4/5は断面二次モーメント (m4)、杭種6は弾性係数 (kN/mm2) |
| `pile.bladeOuterDiameterM`, `pile.bladeInnerDiameterM` | 杭種5の羽根外径・内径 (m) |

杭種5では羽根外径を杭径以上、羽根内径を杭径以下とする。入力制約の詳細は live validation を優先する。

## Pile group

`pileGroup.longitudinal` と `pileGroup.transverse` は同じ形を持つ。

- `lmM`, `lnM`: m方向、n方向の杭間隔 (m)
- `m`, `n`: 各方向の杭本数

両方向の `m * n` は一致させる。杭本数は1以上で、複数本方向の間隔は杭径以上を要求する。

## Soil rows

`soilRows` は地表から深度方向の順で最大15行。各数値セルは JSON number ではなく文字列または `null` とする。完全な空行は計算時に読み飛ばされる。

| Field | Unit / rule |
|---|---|
| `thicknessM` | 層厚 (m) |
| `soilKind` | `粘性土`、`砂質土`、`砂礫` |
| `nValue` | N値 |
| `wetUnitWeightKnPerM3` | 湿潤単位体積重量 (kN/m3) |
| `submergedUnitWeightKnPerM3` | 水中単位体積重量 (kN/m3) |
| `frictionAngleDegrees` | 内部摩擦角 (degree)。砂質土・砂礫で必要 |
| `cohesionKnPerM2` | 粘着力 (kN/m2)。未測定 `null` と実測 `"0"` を区別する |
| `deformationModulusKnPerM2` | 変形係数 Ed (kN/m2) |
| `deL1`, `deL2` | 液状化時の低減係数 0～1。対象外は `null` |

有効層の合計厚は `pile.embedmentDepthM + pile.lengthM` 以上必要である。

## SDC export section

`sdcExport` は SDC operation のとき必須で、次を持つ。

- `equivalentWidthPileCount`: 換算抵抗幅に用いる杭本数
- `steelPipeDiameterM`: 鋼管径 (m)
- `steelPipeThicknessMm`: 鋼管厚 (mm)
- `corrosionAllowanceMm`: 腐食しろ (mm)
- `longitudinalRows`, `transverseRows`: 各方向1～12列の杭列

各杭列は `distanceFromFirstM`（1列目からの距離 m）と `pileCount` を文字列または `null` で持つ。現行 exporter は杭種4/5/6に対応する。

杭種5では `steelPipeDiameterM` を `pile.diameterM` と一致させる。SDCの杭情報は `D1=steelPipeDiameterM`、`D2=pile.bladeOuterDiameterM`、`t1=steelPipeThicknessMm`、腐食代=`corrosionAllowanceMm` とする。断面積と断面二次モーメントは、外面腐食を控除した中空鋼管として次で算定する。

```text
A = pi/4  * ((D1 - 2c)^2 - (D1 - 2t)^2)
I = pi/64 * ((D1 - 2c)^4 - (D1 - 2t)^4)
```

ここで `t` と `c` は m に換算した鋼管厚と腐食代である。回転杭では先端の押込み側に加え、引抜き側の長期・短期鉛直ばね、非線形第2勾配、降伏・終局支持力も SDC に出力する。

## Ground displacement section

`groundDisplacement` は応答変位 operation のとき必須で、標準設計震度、地域別係数、JOT等価固有周期、JOT version、L1/L2出力指定、L2スペクトル区分、最大58行の地層条件を持つ。各行は層番号、層厚、単位体積重量、せん断弾性波速度を文字列または `null` で持つ。
