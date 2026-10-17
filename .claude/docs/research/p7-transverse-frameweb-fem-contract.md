# P7 直角方向 FrameWeb native JSON・FEMPython 契約追加調査

調査日: 2026-10-16。実装計画用の読取調査。対象は `.claude/docs/Example橋脚2/09_直角/frameWebForJS.json`、予定出力は `./post/線路直角方向.json`。製品ソース、Example 原本、P7 入出力、既存調査メモを変更していない。調査用コピー・計算結果は `tmp/p7-transverse-frameweb-plan/fem_contract/` のみに作成した。

共通契約は [線路方向の調査メモ](p7-frameweb-fem-contract.md) を再利用する。本メモは直角方向固有の荷重・包絡・風分布荷重を補足する。GUI 実操作と PDF 生成は今回実施していない。

## 結論

1. 17 基本ケース、15 DEFINE、16 COMBINE、8 PICKUP の native 構造を利用できる。ただし入力にある空部材荷重 2 行は現 headless でエラーになる。空行だけ除去したコピーは 16 実解析ケース・16 COMBINE・8 PICKUP を正常生成した。ゼロ荷重ケース 5 は native に残し、解析ではスキップされる。
2. **Example の風荷重 `m1=1,m2=-3,L2=1.08` をそのまま転用してはいけない。** 現 C# 投影は L2 を各部材へ適用し、旧 Angular の連続部材荷重と結果が異なる。P7 は物理的な対象部材ごとに正の単一 ID と明示的な L1/L2 を出力する。
3. DEFINE は相互に独立して包絡される。P7 の列車・衝撃で要求する `single_track` の同一上り/下り選択は native に直接表せない。同じ支持条件の L+I を、係数反映済みの上り/下り複合荷重ケースへまとめ、ひとつの DEFINE の候補とする。
4. LF/W1/W2 の ± DEFINE はケースの全成分を同時に反転する。ひとつの荷重にある H/M/qH の相関は保持できる。LF と W1 の間に相互拘束はないという P7 正本の仕様なら、各 DEFINE の独立 ± は適合する。
5. 正本 native の精度、raw headless の投影、GUI の既知 Single 保存投影を別の受入対象とする。COMBINE 係数は Double。sidecar に元入力・0620 JSON・native の SHA、補助ケース対応表、ソフト基準を記録する方針を維持する。

## 実行基準・原本保全

FEMPython ソース参照の基準ルートは `C:/Users/sasai/Documents/structural-mcp/FEMPython/`。以下のソースパスはこのルートからの相対位置。AGENTS と共通ルールの確認は前回調査を継承した。

| 項目 | 調査時値 |
|---|---|
| source HEAD | `7488c8fb4d6c100438a9691747ceb11fd9e66358` |
| source worktree status | 空、調査完了時にも確認 |
| 実行 runner の engineVersion | `1.0.0+018d0d0ee9453464b0b541a5344ce5a6c0acdfc6` |
| Headless.exe SHA-256 | `474bc1bc9da6dd5cda466f815753cbb61cdfc53c11473106e5d94e994eff0247` |
| Headless.dll SHA-256 | `32ff5c0bf93f50249eb4260eeb16d9f05f5028403e79ca48043dcdc7904a4ac6` |
| FrameWebforCS.dll SHA-256 | `4e7284b10fb3c91e8ba544b62d53b9eee8cb0f8b4c08c59e5dca0f1b19e876fa` |
| Example native SHA-256 | `8ff9e589ffd70af6cba3c89cb999b2735ce9f7734801df29015b7cc1e5cbf5ff` |

既存 runner を使用し build/restore/update はしていない。C# バイナリの engineVersion と現在の source HEAD は一致しないため、ソース読解と実行実測を区別する。Python は runner の通常経路で現在の `FrameWeb/src` を読み込む。P7 実装時には使用する runner/ソースを再固定し、既知の風投影差が解消されたと推測せず再検証する。

調査ファイルのパス・サイズ・SHA、空行除去の内容は `tmp/p7-transverse-frameweb-plan/fem_contract/manifest.json` に保存した。原本 SHA は調査完了時も上記と一致。

## Example 直角の native 構造

6 節点の x は 0、y は順に 10.3、8.3、7.6、2.7、1.35、0 m。5 部材は 1→2→3→4→5→6 の下向き接続。部材 1～3 は柱、4～5 は有限剛性の剛域。section TYPE 1 内の断面 1 は E=26,500,000、A=12.15、Iz=20.50313、断面 2 は E=26,500,000、A=Iz=1000。寸法 2 の XY 解析では E/A/Iz が有効で、G/J/Iy は共通投影が補完する。

native の節点 spring は節点 6 のみ。下表の値は Example 固有であり P7 に数値転用しない。

| fix_node TYPE | tx | ty | rz | 使用 load |
|---|---:|---:|---:|---|
| 1 | 4,262,769 | 12,788,244 | 86,320,647 | 1～8 |
| 2 | 8,525,475 | 25,576,488 | 172,641,294 | 9～17 |

各 load は `element=1`, `rate=1`, `LL_pitch=0.1`。symbol は LL ではなく、移動列車を展開する入力ではない。長期/短期は各ケースで別々の剛性行列として解析し、その**結果**を COMBINE が加算する。単一支持条件の荷重合計を再解析するものではない。根拠は `FrameWeb/src/fem/legacy_beam.py:63,79` のケース選択、および `FrameWebforCS/calculation/CalculationDerivedPresenter.cs:180,209` の結果成分加算。

### 基本荷重の数値と方向

下表は native 原本の値。力 kN、モーメント kN m、分布荷重 kN/m。正の global y は上。節点 rz は global z 回り。node1 の高さは 10.3 m、node5 は 1.35 m。

| load | 記号 | 入力内容 |
|---:|---|---|
| 1 | D1 | node1 ty=-8299.53、node5 ty=-4167.45。部材1～3の local x に mark2, P1=P2=+297.68、L1=L2=0 |
| 2 | D2 | node1 ty=-780、node5 ty=-1830.6 |
| 3 | Wp1 | node5 ty=+2381.4 |
| 4 | Wp2 | node5 ty=+1701 |
| 5 | Wp3 | 荷重なし |
| 6 | Ss2 | node1 ty=-710 |
| 7 | Ss10 | node1 ty=-1140 |
| 8 | Ss30 | node1 ty=-1270 |
| 9 | L1 | node1 ty=-567.39、rz=-1210.08 |
| 10 | L2 | node1 ty=-567.39、rz=+1210.08 |
| 11 | L3 | node1 ty=-1134.77、rz 空 |
| 12 | I1 | node1 ty=-227.78、rz=-483.45 |
| 13 | I2 | node1 ty=-227.78、rz=+483.45 |
| 14 | I3 | node1 ty=-428.28、rz 空 |
| 15 | Lf | node1 tx=-111.69、rz=-430.01 |
| 16 | W1 | node1 tx=+305.88、rz=-1001.33。部材1～3 local y に q=+4.05、旧連続範囲指定 m2=-3、L2=1.08 |
| 17 | W2 | node1 tx=+611.75、rz=-2002。部材1～3 local y に q=+8.1、同じ範囲指定 |

部材 local x は ni→nj の下向きであるため D1 の正 q は下向き。下向き XY 部材の local y は global +x であるため風の正 q は右向き。根拠: `FrameWeb/src/fem/elements/bar_element.py:60,78`、`loaded_bar_element.py:129`。P7 の部材方向・global 荷重軸を確認し、別接続方向へ記号だけ転用しない。

L1/L2 の左右・上り下りは **同じ鉛直符号で偏心モーメントだけ反転**する2ケースであり、ひとつの荷重ケースを ± にすることでは表せない。また Example Lf の負 tx と負 rz は基部モーメントについて互いに反対の効果となる。`Mz_base = rz - y*tx` は `-430.01 - 10.3*(-111.69) = +720.397`。P7 の H/M の正規符号を Example の見かけの符号だけで決めない。

### DEFINE / COMBINE / PICKUP

DEFINE 1～8 は同番号 load のみ。9=[9,10]、10=[11]、11=[12,13]、12=[14]、13=[15,-15]、14=[16,-16]、15=[17,-17]。

COMBINE は 16 個。`Ck` の k は DEFINE ID、値は係数であり、行中の列順序を表さない。Example の主要列車項は次のとおり。

| COMBINE | 列車・衝撃項 | その他の特徴 |
|---|---|---|
| 1,10 | 1.35 D10 + 1.35 D12 | Lf 1.23 D13、W1 1 D14、10 は Wp3 D5 追加 |
| 2,11 | 1.23 D10 + 1.23 D12 | Lf 1.35 D13、W1 1 D14、11 は Wp3 D5 追加 |
| 5 | 1 D10 + 0.75 D12 | 使用時縁応力度 |
| 7 | 1 D9 + 0.75 D11 | 単線変動荷重のみ |
| 8 | 1.23 D10 + 1.23 D12 | Lf 1.23 D13、W1 1 D14 |
| 15,16 | 1 D9 + 0.75 D11 | 永久・雪・水位条件を追加 |

PICKUP は順に `[1,2,3,4]`, `[5]`, `[6]`, `[7]`, `[8,9]`, `[10,11,12,13]`, `[14]`, `[15,16]`。

DEFINE の C1/C2 は符号付き **load ID**、PICKUP の C1/C2 は **COMBINE ID**。DEFINE は各評価位置・着目成分の最大/最小を選び、選択元ケースの全6成分を保持する。同値は先の候補が残る。COMBINE は同じ着目モードの各 DEFINE 全6成分を係数倍して加算し、PICKUP はその全6成分を COMBINE ごと選択する。根拠: `CalculationDerivedInputSnapshot.cs:39,43,48`、`CalculationDerivedPresenter.cs:138,152,164,167,169,180,209,234,250`（ともに `FrameWebforCS/calculation/`）。

## 風の負 m2: 旧 native の意味と現投影の相違

旧 Angular の `FrameWebforJS/src/app/components/input/input-load/input-load.service.ts:767,804,826,889,917,921,1169` は負 m2 による部材グループを連続長さで扱う。Example の 1～3 部材総長は 7.6 m、末端余白 1.08 m なので載荷長は 6.52 m。部材1は2.0 m全長、部材2は0.7 m全長、部材3は4.9-1.08=3.82 m。

一方、現 `FrameWebforCS/calculation/CalculationRequest.cs:245` の `ExpandMemberRow` は ID の絶対値 begin～end を走査し、mark2 の負 m2 特有の連続載荷計算を行わない。各行に同じ L1/L2 をコピーする。`:406,424` の `PositionMemberRows` は start+end が部材長を超えるとその行の荷重をゼロにする。このため原本の指定では部材1が0.92 m、部材2が0 m、部材3が3.82 m、合計4.74 mとなる。

| ケース | 旧連続区間の外力 Fx | 空行のみ除去した現計算の反力 Fx | 旧連続区間の外力 Mz | 現計算反力 Mz |
|---|---:|---:|---:|---:|
| W1 | +332.286 | -325.07699999982816 | -4337.79224 | +4276.587830000135 |
| W2 | +664.562 | -650.1439999996597 | -8674.82148 | +8552.412660000275 |

W1 の連続区間外力は `305.88 + 4.05*6.52 = 332.286`、基部モーメントは `-1001.33 -305.88*10.3 -4.05*6.52*(10.3+3.78)/2 = -4337.79224`。原本に埋め込まれた旧 `result` はこの連続区間相当の値だが、旧反力表示は今回 canonical と逆符号なのでそのまま同値比較しない。今回の headless は旧 result を利用せず再計算している。

診断コピー `example-explicit-wind-members.json` は、空行除去済みモデルの W1/W2 部材荷重だけを次の3行へ置換した。P7 の製品 JSON ではない。

```json
[
  {"m1":"1","m2":"1","direction":"y","mark":2,"L1":0,"L2":0,"P1":4.05,"P2":4.05,"row":1},
  {"m1":"2","m2":"2","direction":"y","mark":2,"L1":0,"L2":0,"P1":4.05,"P2":4.05,"row":2},
  {"m1":"3","m2":"3","direction":"y","mark":2,"L1":0,"L2":1.08,"P1":4.05,"P2":4.05,"row":3}
]
```

W2 は同じ区間で P1=P2=8.1。この診断実行の反力は W1 `Fx=-332.2859999998269,Mz=4337.792240000138`、W2 `Fx=-664.5619999996544,Mz=8674.821480000279`。意図した連続外力との全体釣合い残差は最大 3.46e-10 で、欠落の原因が範囲投影にあることを確認した。

P7 では数値範囲 `m1..m2` に依存せず、正本の物理対象部材を列挙する。非連番の member ID を中間整数で埋めない。L1/L2 は ni/nj 側の非載荷長であり、総区間長から各部材との交差長を求める。現投影は距離を 0.001 m、P1/P2 を 0.01 に丸める（同ファイル`:430`）ため、独立釣合いでは正本外力と投影済み外力を分け、丸め差を特定する。単純に solver 反力に合わせて入力期待値を作らない。

## 選択相関: native の限界と P7 の複合ケース案

`FrameWebforCS/components/input/InputCombineService.cs:148` は DEFINE/COMBINE/PICKUP の未知キーを拒否する。`selection_group`, `compatibility_group`, `coupled_group` などを追加する native schema 機能はない。`CalculationDerivedPresenter.cs:138` は DEFINE ごとに独立包絡するため、別々の D9 と D11 に同じ候補順序を入れても、上り/下りの同時選択は保証されない。

Example は対称のため同じ方向が選ばれやすく、正常結果だけでは相関保証を証明できない。そこで調査専用 `selection-coupling-diagnostic.json` は L の9/10を維持し、I の12/13のモーメントだけ逆にした人工ケースを作成した。これは P7 の設計値ではない。独立 `D9 +0.75 D11` と、同じ上り同士/下り同士を事前合計した helper18/19 のひとつの DEFINE とを実解析した。

| node1 dx_max | 選択元 | dx | rz |
|---|---|---:|---:|
| 独立 DEFINE 加算 | 9,13（上り L + 下り I） | 0.00017885408941236477 | -0.00003126774976730555 |
| 同じ線の複合候補 | 18（上り L + 上り I） | 0.00009638241991476809 | -0.000016849832160751204 |

この診断により、native の独立 DEFINE では禁止組合せを作れること、および事前複合候補で相関を保持できることを確認した。

P7 正本の `define_cases` 9/11 と resolved candidates は `single_track` の up/down を共有する。`src/transverse_actions.py:255,262,278,281,288,290,294` は L/I を用途別係数で実効化し、`factor_applications=1,remaining_multiplier=1` と compatibility group を持たせている。生成器はこの **resolved 実効荷重** を一度だけ合計し、native COMBINE では1倍とする。元の名目係数を再び掛けない。

親調査側と合意した計画上の対応は次のとおり。実装はしていない。

| native helper load | 内容 | helper DEFINE | 置換対象 COMBINE |
|---|---|---|---|
| 18 | 両線・終局1.35用途の resolved L+I | 16=[18] | 1,10 |
| 19 | 両線・終局1.23用途の resolved L+I | 17=[19] | 2,8,11 |
| 20 | 両線・使用時の resolved L+I | 18=[20] | 5 |
| 21,22 | 単線・使用時の上り/下り resolved L+I | 19=[21,22] | 7,15,16 |

元の17基本 load と15 DEFINE は参照・追跡用に残す。追加後は22 load /19 DEFINE /16 COMBINE /8 PICKUP。上表 COMBINE から元 L と I の2項を両方除き、helper DEFINE を係数1で1項入れる。helpers は同じ `fix_node=2`、同じ element TYPE で合成する。異なる spring TYPE の荷重を一つの helper に混在させることはしない。実装受入では source load、用途、effective coefficient、option/up/down、helper ID の全対応を sidecar で検査する。

LF/W1 の positive/negative は互いの group ではなく、各ケース内部の H/M/qH を同時反転する仕様。native -case は全6結果成分を反転するため、反転させたくない鉛直 N/qN が含まれていないことを確認する。canonical `transverse_actions.py:255` では H/M/qH が符号反転し、N/qN は係数倍だけなので、鉛直成分を含む将来ケースを安易に ± DEFINE へ入れない。

## 実計算と独立照合

原本を直接 runner へ渡すと exit1: `INVALID_INPUT: load.1.load_member row 2: unsupported mark .`。空行検査より前の mark 検査が原因（`CalculationRequest.cs:292`）。一時コピーでは load1 の `{P1:null,P2:null,row:2}` と load16 の `{m1:"",L1:null,P1:null,P2:null,row:2}` のみ除去した。原本との差分を JSON 意味比較し、これら2行以外に変更がないことを確認した。古い `result` もコピーに残したが headless は無視する。

空行除去コピー実行は exit0、dimension2、内部節点8、部材5、実ケース16、PICKUP8。DEFINE 実結果は14（ゼロケース5の DEFINE が欠ける）、COMBINE16、PICKUP8。警告は `EMPTY_LOAD_CASE_SKIPPED` の load5 のみ。風明示3行の診断コピーは内部節点7となる。荷重端で内部節点が追加されるため、native の6節点と結果 topology 数が同じである必要はない。

再実行例（FEMPython ルートから、出力先は未存在または空ディレクトリを指定）:

```powershell
& 'FrameWebforCS/Headless/bin/Release/net10.0-windows/FrameWebforCS.Headless.exe' run `
  --input 'K:/ニュージャパンコンサルタンツ/26_LRT鉄道照査/tmp/p7-transverse-frameweb-plan/fem_contract/example-no-empty-member-rows.json' `
  --output-dir 'K:/ニュージャパンコンサルタンツ/26_LRT鉄道照査/tmp/p7-transverse-frameweb-plan/fem_contract/recheck-new' `
  --generate-pdf false --generate-pik true `
  --generate-pickup-displacement-csv true --generate-pickup-reaction-csv true
```

`audit.py` は基礎ケース結果から DEFINE の符号・候補選択・同値順序、COMBINE 全成分加算、PICKUP 全ベクトル選択を独立に再構成し、`audit.json` に結果を保存した。3種類の結果（変位・反力・部材力）、全位置・全着目モードを対象に 5,928 行、35,568 成分、5,928 出典 ID を比較して差0、失敗0。これは派生演算の検証であり、基礎 solver の正しさをそれだけで証明するものではない。

別に物理外力と反力の釣合い、および spring の `u + R/K = 0` を確認した。例:

| 基本ケース | 独立外力・反力確認 | spring 確認 |
|---|---|---|
| D1 | 下向き総荷重 8299.53+4167.45+297.68×7.6=14729.348、Ry=14729.348 | TYPE1 uy=-0.001151788157936314、uy+Ry/Ky=-9.32e-18 |
| 上り L | Ry=567.39、Mz=1210.08 | TYPE2 uy=-2.2184046535239708e-5、rz=-7.009215303958507e-6、各残差0 |
| 下り L | Ry=567.39、Mz=-1210.08 | 同じ uy、rz は正、各残差0 |
| Lf | Rx=111.68999999997106、Mz=-720.3970000000229 | TYPE2 ux+Rx/Kx=2.57e-17、rz+Mz/Kr=-6.19e-18 |

空行除去モデルの全ケースは**現投影済み**外力との釣合い残差最大3.41e-10。旧連続区間を意図した外力との比較では W1/W2 だけがそれぞれ Fx7.209/14.418、Mz-61.20441/-122.40882 不一致である。明示風3行モデルでは旧連続区間との最大残差3.46e-10に戻る。この区別を P7 受入でも保存する。

主要 artifact: `normalized-headless/result.json` SHA=`ded43ef1f6b6eca773961bb84735e57a6f7256d97a3338144169967c11d41883`、`explicit-wind-headless/result.json` SHA=`ff26e81b70feb6b614284505fba81244116184c17a34955d3ba8c839ddac4ce4`、`selection-coupling-headless/result.json` SHA=`e5b24ab6ed3ea9da2e425ae96cf0fa5841838d9da6578aca249829d2660d6365`。詳細は manifest。

## 精度・保存互換性・計画への受入項目

前回共通メモの型調査を適用する。native 正本は元の Double 精度を保持する。raw headless は node/element/fix_node/load_node 等の数値を Double で読み、部材荷重だけ既知の距離/強度丸めがある。GUI は主要入力を Single で保持し、保存時は `Q(v)=parseDouble(serializeSingle(parseSingle(v)))` に変わる。COMBINE は Double（`InputCombineService.cs:163`）であり一律 Single 化しない。

GUI 往復は独立に作った型別 Q 投影と比較し、raw native と無条件に同値と主張しない。GUI 後の解析は Q 投影後の expected input から検証する。生成 native に任意の provenance top-level キーを加えても GUI 保存で維持されないので、計画では `線路直角方向.provenance.json` 等の sidecar を別途公開する。main native の同一 SHA、0620 正本 SHA、input SHA、helper mapping、source HEAD/runner SHA/engineVersion を sidecar で結ぶ。既存 publisher が完成済みとは扱わない。

実装時は少なくとも (a) 非連番部材への明示風区間、(b) canonical H/M の基部釣合い、(c) 上り/下りの L+I 一致、(d) LF/W1 の独立 ± とケース内部成分相関、(e) 長短期 spring 選択、(f) zero5 の native 残置と解析スキップ、(g) 係数二重適用の排除、(h) 16 COMBINE/8 PICKUP と全6成分・source ID の派生照合を受入に含める。調査の headless success は `engineeringStatus=not_checked` であり、P7 正本の設計合否を判定したという意味ではない。
