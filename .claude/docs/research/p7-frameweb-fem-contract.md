# P7 線路方向 FrameWeb 保存 JSON・FEMPython 入力契約調査

調査日: 2026-10-16。実装前の読取調査。FEMPython の製品ソース、Example 原本、P7 の入力・出力は変更していない。

## 結論

生成対象は **FrameWebforJS/FrameWebforCS の保存 JSON** とする。Python FEM へ渡す解析 JSON は別形であり、保存 JSON をそのまま Python の `FemModel` に読ませる方法は採らない。既存の `FrameWebforCS.Headless.exe` が保存 JSON → 計算要求投影 → Python 再計算 → DEFINE/COMBINE/PICKUP → PIK/PDF の正規経路を提供する。

Example 保存 JSON は dimension=2、6 節点・5 部材、支持ばね 2 組、20 荷重ケース、20 DEFINE、16 COMBINE、8 PICKUP。現在の headless は Example の空部材荷重行をエラーにするが、**空行だけ除いた一時コピー**は計算・PIK・変位/反力 CSV 出力に成功した。P7 生成時には空 `load_member` placeholder を出力せず、荷重のないケース自体は残せる。

## 調査対象と実行環境

- ソース基準: `C:/Users/sasai/Documents/structural-mcp/FEMPython/`。以下のソース参照はこのルートからの相対パス。
- 入力原本: `Example橋脚2/08_線路/frameWebForJS.json`。
- 原本 SHA-256: `244085acff3aee31a78f466e506cab317e920c0d506b0fd6aa9a7e14fadb70b3`。
- FEMPython の `AGENTS.md` と context-loader を読取り。ルール 10 ファイル、STATE、DESIGN を確認。loader は `missing=["PROGRESS.md"]`, `unreadable=[]`, `warnings=[]`, `design.placeholder=false`, `progress.entries=0`。
- 既存 Release runner を利用。実行 envelope の engineVersion は `1.0.0+018d0d0ee9453464b0b541a5344ce5a6c0acdfc6`。ソース側に別タスクの未コミット変更あり。本調査で build/restore/update/source編集はしていないため、今回の実測は既存バイナリの実測と区別する。
- GUI の実操作・保存往復は未実施。下記は GUI の load/save ソース経路を確認した結果であり、GUI 操作成功を主張しない。

## 保存形式と計算形式の相違

| 項目 | 保存 JSON | 計算要求への投影 | 根拠 |
|---|---|---|---|
| `dimension` | `2` を明示 | 2/3 だけ受理。省略時 3 | `FrameWebforCS/calculation/CalculationRequest.cs:28` |
| `node` | ID 文字列をキーに x/y/z | 非接続節点を除き、空座標を 0、2D は z=0 | 同:79,109,452 |
| `member` | `ni`,`nj`,`e`,`cg` | ni/nj を参照検証して整数化、cg 既定 0 | 同:80 |
| `element` | 外側 TYPE → 内側断面番号 | E/G/Xp/A/J/Iy/Iz の空欄を補完。2D は G/J/Iy=1 | 同:117 |
| `fix_node` | TYPE ごとの節点拘束/ばね行 | 空行を除き、空成分を 0、2D 面外拘束を全節点へ追加 | 同:69,452,487 |
| `load_node` | n,tx,ty,tz,rx,ry,rz,row | 正の n: 節点力。負の n: 強制変位へ変換、÷1000 | 同:159 |
| `load_member` | `m1`,`m2` の範囲と荷重パラメータ | 範囲を個別 `m` 行へ展開、距離/値を数値化・丸め | 同:245,280,406 |
| `define/combine/pickup` | 保存対象 | Python への要求には含めず、基礎ケース結果から後処理 | 同:37; `CalculationDerivedPresenter.cs:90` |
| `three` | 表示カメラ | 計算要求に含めない | `InputDataService.cs:373`; `CalculationRequest.cs:37` |
| `result`, `resultDimension` | 既存結果を含むことがある | headless は既存結果を無視し常に再計算 | `Headless/README.md:61` |
| `rate` | Example に各 1 が残る | 現行計算要求がコピーしないため荷重倍率には使わない | `CalculationRequest.cs:148`; `tests/io/test_legacy_cases_api.py:99` |

Angular も `getInputJson(null)` が保存、`getInputJson(0)` が計算の別経路である。DEFINE/COMBINE/PICKUP/three/result は保存枝、2D 補完は計算枝だけで実行する。根拠: `FrameWebforJS/src/app/providers/input-data.service.ts:192,264,285,305`。

P7 は新規の入力ファイルとして result を付けず、技術的に不要な空行、入力レイアウト metadata、カメラを Example から無条件に複製しない。`three` は省略可能。付ける場合 `three.camera` の x/y/z を正しい有限値で記録する必要がある (`InputDataService.cs:282`)。

## 2D 座標・断面・拘束

### 座標と断面

- 解析平面は全体 XY。水平 x、鉛直上向き y。面内自由度は tx/ty/rz。節点荷重 tx/ty は力、rz は Z 軸回りモーメント。
- 2D で効く断面値は E/A/Iz。A は断面積、Iz は XY 曲げの断面二次モーメント。`bar_element.py:191` の剛性が `E*Iz` と local y/rz を対応させる。
- 単位は自動換算されない。P7/Example の kN・m 系では E=kN/m²、A=m²、Iz=m⁴、節点力=kN、モーメント=kN·m、分布力=kN/m、並進ばね=kN/m、回転ばね=kN·m/rad を一貫して用いる (`FrameWeb/README.md:61`)。
- `element["1"]["1"]` と member.e=1 の対応を維持する。外側はケースが選択する材料/断面 TYPE、内側は部材が参照する断面 ID (`legacy_beam.py:79`; `file_io.py:317`)。
- Example 柱は E=26500000、A=12.15、Iz=7.38113、Xp=0.00001。剛域は同じ E、A=1000、Iz=1000。P7 への値の流用はせず P7 の計算書/正本に従う。
- Example の G/J/Iy=null は保存として許され、2D 投影時に 1 になる。これを実材料の G やねじり剛性と解釈しない。線形旧形式の既定 shear_correction は false (`legacy_beam.py:88`)。
- `Xp` は熱膨張係数として材料へ渡る (`file_io.py:325`)。自重用密度ではない。自重を部材荷重で載せるため、別の自重を二重加算しない。

### 節点ばね 2 組

`fix_node` 数値は 0=自由、1=固定、それ以外=線形ばね剛性（Python は絶対値を採用）。特に剛性値「1」はばねでなく固定を表すため、入力生成時にこの legacy 約束を守る (`file_io.py:481`)。

Example は節点 6 だけに面内ばねを指定する。

| TYPE | tx | ty | rz |
|---|---:|---:|---:|
| 1 | 4262769 | 12788244 | 52218663 |
| 2 | 8525475 | 25576488 | 104437326 |

TYPE 2 の tx は TYPE 1 のちょうど 2 倍ではなく、`2*4262769=8525538` に対して保存値 8525475。元資料の値を転記するのであり、「短期は長期の2倍」として再生成しない。

`load[id].fix_node` がそのケースの支持 TYPE を選ぶ。Python はケースごとに入力を deepcopy し、element/fix_node/joint/fix_member の選択 TYPE だけ残す (`legacy_beam.py:63`)。2 組を同時に足して単一のばねにはしない。

Example の `fix_member` 根セクションは存在しない。各荷重ケースに残る `fix_member:1/2` は節点ばねそのものではない。節点ばねを作るために架空の fix_member 行を作成しない。P7 でも必要なのは fix_node 2 組。

2D 投影は各支持 TYPE に全節点の tz=rx=ry=1 を追加する (`CalculationRequest.cs:471`)。このため headless 結果の support_reactions に面外拘束のみの節点も現れ得る。実計算では Example の節点 1～5 の反力は全成分 0、節点 6 に面内反力がある。検算は各ケースの全反力総和と、実ばね節点の個別値を区別する。

## 荷重パラメータと符号

### 節点荷重

正の n を使う通常節点荷重では tx=+X、ty=+Y、rz=右手系 +Z モーメント。したがって下向き力は ty<0。行番号 row は編集位置を表す。Example の D1 では節点1 ty=-8299.53/rz=+610、節点5 ty=-4167.45 を使用。

`n<0` は別機能の強制変位であり、P7 の荷重符号を表すために n の符号を変えない (`CalculationRequest.cs:163`)。

PDF の出力符号を JSON 入力符号へ無条件に戻さない。現行 desktop の 2D PDF 表示に回転/Mz 符号変換がある一方、canonical result/PIK/CSV は raw 値である。今回の入力照合では節点荷重と座標・平衡を基準にする。

### 部材荷重

| キー | 意味・注意 |
|---|---|
| `m1`,`m2` | 保存形式の部材 ID 範囲。正の 1～3 は 1,2,3 各部材へ同じ行を展開。solver 形式は `m` |
| `direction="x"` | 部材局所 x、ni→nj。`gx/gy/gz` は全体軸、x/y/z は局所軸 |
| `mark=2` | 分布荷重。P1/P2 は区間両端の強度 |
| `mark=1` | 集中力。L1/P1, L2/P2 の各組が I 端からの位置と荷重 |
| `mark=11` | 集中モーメント。距離規則は mark1 と同じ |
| `mark=9` | 温度荷重。本件の D1 では使用しない |
| `mark=0` | 無効行。新規出力は不要な無効行を作らない |
| mark2, L1 | I 端から荷重開始位置までの距離 |
| mark2, L2>=0 | J 端から荷重終了位置までの余白。L1=L2=0 は全長載荷 |
| mark2, L2<0 | L1 からの載荷長さ指定。前行との相対位置等の追加規則あり |

根拠: `CalculationRequest.cs:245,280,406`; `legacy_beam.py:149,163,174,183`; `elements/loaded_bar_element.py:129`。

相対距離は旧入力の row 連続性、文字列 `"-0"`、整数 mm 丸めを使う複雑な仕様を持つ。本件で全長の柱自重を表すには m1/m2 の正の範囲、L1=L2=0 を使えばよく、相対入力を新規導入する必要はない。

**Example D1 確認**: `{m1:"1",m2:"3",direction:"x",mark:2,L1:"0",L2:0,P1:297.68,P2:297.68,row:1}`。部材 1～3 は上から下へ ni→nj を向けるため、局所 x 正の 297.68 は下向き荷重。全体方向 gy を用いた場合の -297.68 と同じ力向きになる。根拠: `bar_element.py:60,78` の第一基底は `(nj-ni)/L`。

投影で部材荷重の距離は mm 単位、P1/P2 は小数第2位に丸められる (`CalculationRequest.cs:430`)。生成値の精度と解析へ入る精度を分けて検証する。節点荷重はこの P1/P2 丸め経路を通らない。

## DEFINE / COMBINE / PICKUP

同じ `C1` でも 3 種類で意味が異なる。`CalculationDerivedInputSnapshot.cs:39` が対応を明示する。

| セクション | キー | 値 | Example |
|---|---|---|---|
| define | C1/C2… は候補欄 | 符号付き基本ケース ID | define13={row:13,C1:13,C2:-13} |
| combine | C13 などの番号が DEFINE ID | 係数 | combine6 に C1=1,C2=1,C6=1,C13=1 |
| pickup | C1/C2… は候補欄 | COMBINE ID | pickup1={row:1,C1:1,C2:2,C3:3,C4:4} |

DEFINE の `{C1:13,C2:-13}` は +case13 と -case13 の **候補包絡**であり、+13 と -13 の足し算ではない。各評価位置、各 focus 成分、max/min について選び、選んだケースの全6成分を一緒に保持する (`CalculationDerivedPresenter.cs:138`)。

COMBINE は対応する DEFINE の同じ focus/max-min 結果を係数倍して成分ごとに加算する (`CalculationDerivedPresenter.cs:180`)。PICKUP は列挙された COMBINE の中から各成分最大/最小を選び、相関した全成分と選択 COMBINE ID を保持する (同:234)。2D の focus は変位 dx/dy/rz、力 fx/fy/mz (同:133)。

**長短期ばねが混在する組合せ**: 各基本ケースをそのケースのばねで先に解析し、その結果を後で加算する。組合せ荷重を一つに足し、一つの支持 TYPE で再解析する方式にはならない。この点を P7 の検算にも維持する。

Example の COMBINE1 は `1.1*D1 + 1.2*D2 + 1*D7 + 1.35*D10 + 1.35*D12 + 1*D15`。case1/2/7 は支持 TYPE1、case10/12/15 は TYPE2。実測の節点6 dx_max 相関ベクトルを、各基本ケースの結果と係数から別途足し直し、最大成分残差 0 を確認した。これは sourceCaseId `1,2,7,10,12,15` の場合の数値照合であり、P7 の設計組合せ表の正当性を代替しない。

Example 保存 JSON の case14/18/20 の fix_node は 2。ただし親調査で Example PDF の対応表は 1 と確認されたため、P7 での選択 TYPE は Example 保存値を機械コピーせず、P7 の PDF/正本のケース表を優先する既知差異として扱う。

## 空荷重ケースと空編集行

### 実際に発生した空行エラー

Example 原本の `load.2.load_member[0]` などは `{P1:null,P2:null,row:1}` だけの空行。現在の `NormalizeRelativeMemberRows` は「部材がない/値がないなら skip」より先に mark/direction を検証するため、headless は次で停止した。

```text
exit 1
INVALID_INPUT: CalculationRequestException:
load.2.load_member row 1: unsupported mark .
```

根拠: `CalculationRequest.cs:292` の mark 検証、296 の direction 必須判定、299 の空行 skip の順番。新規 P7 出力は `load_member` がないケースでキーを省略する。Example 原本修正や FEMPython の製品修正は今回の範囲にしない。

### case5 を残してよい

荷重のない case5 自体は名前・TYPE 選択を保持し、DEFINE5、COMBINE の C5=1 を残しても headless は成功する。投影は有効荷重のないケースを解析対象から除外し、warning `EMPTY_LOAD_CASE_SKIPPED` と `skippedLoadCases:["5"]` を報告する。派生結果への寄与はなし。case5 の「ゼロ結果」は生成しない。

根拠: `CalculationRequest.cs:188`; `HeadlessCalculation.cs:38,117,155`; `CalculationDerivedPresenter.cs:50`; `Headless/tests/RunnerTests.cs:172`。case ID 自体を保存から消すと DEFINE が未解決参照となり得るため、zero case と missing case は区別する。

## 実計算の記録

一時ファイル群: `tmp/p7-frameweb-plan/fem_contract/`。

1. 原本を既存 runner に渡す → 上記の空 load_member 行で失敗。原本・予定出力は不変。
2. `example-no-empty-member-rows.json` を作成。case2/3/4/6～20 の空部材荷重行だけ除外（18 ケース）。case5、全荷重値、支持ばね、DEFINE/COMBINE/PICKUP は変更なし。
3. runner は成功 (`executionStatus=success`, `engineeringStatus=not_checked`)。dimension2、nodes6、members5、cases19、results19、pickups8、skippedLoadCases1。
4. `example-headless-normalized/` に result.json、pickup.pik、pickup-displacement.csv、pickup-reaction.csv が生成された。

| artifact | bytes | SHA-256 |
|---|---:|---|
| result.json | 1127252 | 864d18690091645e451b16a991b9c8587ec5d23a8bd9766548ba9cf86ee313bb |
| pickup.pik | 24374 | 9a28c50e1c5a5234351c98ef2bae6935819313fe6ef0a6451b80b52d58310690 |
| pickup-displacement.csv | 23799 | 44e22a7aa1a5cb8105e9322922a904e72abf4db8f12bf2bada5b3e462d70b2b9 |
| pickup-reaction.csv | 7570 | fcea6fab660b1f05ad9579dc4cea38acd4c2f9f747f7e4c6e0b50b8688f30ee0 |

独立平衡チェック（Example D1）:

```text
全体 Fy = -8299.53 - 4167.45 - 297.68*7.6 = -14729.348 kN
節点6 反力 Fy = +14729.348 kN → 残差 0
外力 Mz = +610 kN*m、節点6 反力 Mz = -610 → 残差 0
```

支持 TYPE ごとの基礎変位実測:

| case | TYPE | 上部水平力 | 基礎 dx [m] | 基礎 rz [rad] |
|---|---:|---:|---:|---:|
| 13 | 1 | 240 | 5.6301432238059345e-5 | -4.733939664445258e-5 |
| 14 | 2 | 300 | 3.518865517757075e-5 | -2.9587122902782864e-5 |

各 dx は H/tx、各 rz は -H*10.3/rz の直接計算と対応する。case14 の選択 TYPE は前述の Example PDF/JSON 差異を含むため、この値を P7 の期待値へ移さない。

## 実装時の検証経路

### 正規 headless コマンド

FEMPython ルートから PowerShell で実行する。output-dir は絶対パスかつ不存在/空でなければならず、既存出力を上書きしない。次のコマンドは P7 実装後の計画用であり、現時点では P7 ファイル未生成・未実行。

```powershell
& 'FrameWebforCS/Headless/bin/Release/net10.0-windows/FrameWebforCS.Headless.exe' run `
  --input 'K:/ニュージャパンコンサルタンツ/26_LRT鉄道照査/./post/frameWebForJS.json' `
  --output-dir 'K:/ニュージャパンコンサルタンツ/26_LRT鉄道照査/tmp/p7-frameweb-validation/first-run' `
  --generate-pdf true `
  --generate-pik true `
  --generate-pickup-displacement-csv true `
  --generate-pickup-reaction-csv true `
  --pdf-sections input,section_force,pickup_section_force,displacement,pickup_displacement
```

初期の数値確認だけなら `--generate-pdf false` で十分。最終の入力報告書視認は input PDF を生成し、元PDFの節点・部材・荷重・支持・組合せと比較する。headless が生成する PDF section に応力「図」は含まれず、入力/断面力表/PICKUP表/変位表の検証である。

runner は stdout に protocolVersion1 の JSON envelope を一つ返し、成功 exit0。engineVersion、ok、warning、cases、skipped cases、artifact size/hash を保存する。`result.json` の canonical 部分、derived 部分を別に検査する (`Headless/README.md:72`)。

### GUI 保存往復の確認方法

FrameWebforCS は JSON ファイルを `InputFileLoader.Open` で読む。全 input セクションの解析・検証が `InputDataService.JsonDataOpen` に集まり、変更前に準備した後で一括適用する (`InputFileLoader.cs:10`; `InputDataService.cs:238`)。保存は `GetSaveJson` に集約 (同:373)。

実装完了時は新規 P7 JSON をアプリで開き、別名の検証用 JSON に保存し、再読込する。後述の Single 保存投影を明示して比較し、以下を確認する。「元の全数値が完全に不変」を受入条件にしない。

- dimension2、node/member接続、2組の fix_node、ケースTYPE、DEFINE/PICKUP参照は不変。node座標・fix_node剛性・element E/A/Iz・荷重成分は、各型の既知Single投影後の期待値と一致。COMBINE係数は現行実装でDouble。
- UI が付ける `three`、空セクション、レイアウトや row 情報を、そのまま byte比較の差異として失敗判定しない。
- 往復後 JSON を headless で再計算し、独立に構成したGUI投影後入力からの結果と比較する。正規nativeのraw headless結果との違いは別途数値化し、同一との主張はしない。
- 保存対象は一時ファイル。元の入力と最終出力を検証のため上書きしない。

既存テスト参考: `FrameWebforCS/tests/InputLoadLayoutPersistenceTests.cs:12`, `InputCombineColumnsTests.cs:130`, `TransverseInputCorrectionTests.cs:377`, `InputFileLoaderTests.cs:8`。これらは製品 contract の参考であり、今回の P7 の実データ往復をまだ証明していない。

### 最小限の受入条件

- 元データの SHA 保持。生成値に finite・参照整合性・正の部材長・節点順序を検査。
- データに空 member-load placeholder、古い result、未解決 DEFINE/COMBINE/PICKUP 参照がない。
- 有効/零荷重ケース数、TYPE選択、全荷重の合力・基礎回りモーメント、D1自重合力を事前集計。
- headless の既知 zero case warning 以外に新規 warning/error がない。
- 各基本ケースで外力と反力の水平・鉛直・基礎回りモーメントが釣り合う。
- 長短期ばねは各基本ケースの基礎 u=F/K、theta=M/K で別々に確認。
- 派生値を基本結果から独立再集計。±候補選択を含む DEFINE、係数和 COMBINE、包絡 PICKUP の source ID と全相関成分を検査。
- GUI 保存往復後の値は型別の明示投影と一致し、想定外の差分がない。正規nativeとGUI投影後入力・結果の差は明示する。PDF の表示丸め/符号と raw 結果の差は表示規則として整理。

## 実装範囲外・未確認

- FEMPython の空行受理挙動の修正は今回実施しない。新規 JSON 生成側で有効行だけ出す。
- Example PDF との完全な結果数値一致は本メモの担当外。PDF/JSON の支持 TYPE 差異があるので無条件に golden にしない。
- 今回 PDF を新規生成・レンダリングしていない。GUI 実操作もしていない。
- 解析成功は設計照査成立を意味しない。runner 自身も engineeringStatus=not_checked を返している。

## 追加確認: provenance の保存先

任意の top-level `provenance` 等の JSON キーを追加しても、FrameWebforCS の GUI 保存で保持される契約はない。`InputDataService.JsonDataOpen:243` は既知セクションを個別に解析し、`GetSaveJson:378` は保存対象の固定キーから新しい辞書を作る。未知キーを残す extension-data 領域・元 root の再利用はない。Angular も `input-data.service.ts:202` から固定キーを再構築する。

したがって、native JSON の中に独自 provenance を埋めず、`frameWebForJS.provenance.json` 等の sidecar を同時生成する設計を推奨する。最低限、入力 soilstructure/アプリ正本の SHA、0610 JSON の SHA、0610 PDF の SHA、生成 native JSON の SHA、generator/version、数値の出典、auxiliary case の対応表、意図的な Example 差異を保存する。生成物を一時領域で全て作成・検証し、native と sidecar を対応する組として公開する。

GUI の別名保存で空セクションや row/layout/camera が変わると native の bytes SHA は変わる。古い sidecar をそのまま新しい保存ファイルの出典保証として扱わない。GUI の保存往復検証は元ファイルの厳密 SHA と、解析に影響するデータの意味比較を区別し、新しい bytes SHA が必要なら明示的に再発行する。sidecar を GUI 自体が維持してくれるとは仮定しない。

## 追加確認: native rigid は有限剛性区間指定

保存形式には明示的な `rigid` 配列がある。GUI reader が受理する型は `{ "m":"1", "Ilength":0.2, "Jlength":0.3, "e":2 }`（m は文字列、e は整数）。根拠: `FrameWebforCS/components/input/InputRigidZoneService.cs:66,93`。GUI保存→要求投影を保持する既存テストは `FrameWebforCS/tests/RigidZoneConversionTests.cs:21`。

しかし `rigid` は「I/J端側の区間へ別材料/断面 e を割当てる」機能であり、無限剛性の幾何拘束ではない。Python は Ilength と L-Jlength で部材を分割し、その区間の material_id/section_id を指定 e に変更するだけである (`legacy_beam.py:142,275`)。文書も同じ説明 (`FrameWeb/docs/wiki/data-structures.md:66`)。今回確認した保存→要求→legacy beam 経路に、剛域を別の多点拘束へ変換する処理はない。

そのため、Example と同じく明示節点/部材4/5を持つ P7 モデルで native rigid に置き換えても、自動的に「完全剛体」にならない。既存の節点・荷重位置を保持し、剛域用要素に E=26.5e6 kN/m²、A=1000 m²、Iz=1000 m⁴を与える構成はソフトの有限剛性近似として説明できる。これは **Example と同じモデル化の採用案**であり、P7 の設計規準から導いた剛域剛性という意味ではない。

P7 の `material_provenance.footing` が display_strength を表すなら、それだけを根拠に剛域 E を footing の Ec へ変更しない。梁/柱の実断面 E と、数値モデル上の剛域材料を別の断面 ID で持ち、剛域 E/A/Iz の出典・採用理由を sidecar に明記する案が適切。梁/柱 Ec の違いが必要なら別 section に割り当てる。

剛域近似は有限であるため、実装検証では剛域の変形量、基礎反力・柱断面力・代表変位が剛域剛性の段階的増加でどう変わるかを確認する。感度確認は剛域部分のモデル妥当性確認であり、solver warning の有無だけで無限剛体と同等と判定しない。いずれの倍率も P7 の最終入力へ無断で反映せず、採用モデルと検証用変種を分離する。

追加集計: 実計算された normalized Example の derived は **19 DEFINE / 16 COMBINE / 8 PICKUP**。保存の DEFINE は20件だが、zero case5 が解析対象から外れるため出力 DEFINE5 は存在しない。native に最終的に何ケース作るか（用途別の補助ケース追加等）は P7 の計画側のケース対応表によって固定する。

## 追加確認: GUI Single量子化と headless Double経路（受入条件を訂正）

**正規native JSON → raw headless と、正規native JSON → GUI読込 → GUI計算/保存は、必ずしも同じ値で解析しない。** GUIの多数の編集値が `float?` (IEEE754 binary32/Single) で保持されるためである。前述のGUI検証条件はこの確認に基づき修正した。製品のDouble化は本タスクで実施しない。

### 型と経路

| 項目 | GUI内型 / reader | raw headless |
|---|---|---|
| node x/y/z | `float?` property、JsonSerializer deserialize | 元JsonNodeをclone、空欄補完とz=0のみ |
| member ni/nj/e | string、番号として扱う | IDを整数化・検証 |
| member cg | `float?` | 元値を維持、空欄0 |
| element E/G/Xp/A/J/Iy/Iz | `float?` field、TryGetSingle | 元値を維持、空欄0、2D G/J/Iy=1 |
| fix_node tx/ty/tz/rx/ry/rz | `float?`、TryGetSingle | Number=double.TryParseで正規化、2D補完 |
| load_nodeの6荷重成分 | `float?`、TryGetSingle | Number=double.TryParse、符号付きnの既定変換 |
| load_member P1/P2 | `float?`、TryGetSingle | Number=double.TryParse後に0.01単位丸め |
| load_member L1/L2 | string、文字列を保持 | Double読込後、既知の相対変換・mm丸め |
| LL_pitch | `float?` | Number=double.TryParse |
| COMBINE係数 | **double**、TryGetDouble | 同じParseCombineJson/Double |
| DEFINE/PICKUPの候補ID | int、TryGetInt32 | 同じParseCombineJson/Int32 |
| fix_member（本P7モデルは不使用） | float? | **例外**: headless投影もfloatへ明示cast |
| rigid長さ（本P7案は不使用） | float?、TryGetSingle | 元JsonNodeをclone |

ソース根拠:

- `components/input/InputNodesService.cs:14,21,89`。
- `components/input/InputMembersService.cs:14`。
- `components/input/InputElementsService.cs:12,98,119`。
- `components/input/InputFixNodeService.cs:15,88,111,120`。
- `components/input/InputLoadService.cs:15,23,43,836,862`。
- `providers/DataHelperModule.cs:75,138,151,194`: 反射で field 型を読み、float なら TryGetSingle。保存辞書には boxed float が入る。
- `components/input/InputCombineService.cs:31,63,163`: 現行COMBINEは `clsCombine<double>` と `TryGetDouble`。既存 `InputCombineColumnsTests.cs:133` 等が GetSingle/7.25f を使っていても、実装の格納型がfloatという根拠にはならない（7.25は両方で正確）。
- `calculation/CalculationDerivedInputSnapshot.cs:9,43`: 係数はDoubleのまま派生計算へ渡す。
- `calculation/CalculationRequest.cs:614`: NumberはDouble。`fix_member`だけ同:533-537でSingleへcast。
- `Headless/HeadlessCalculation.cs:20,27,35`: raw保存文字列から要求と派生定義を作り、GUI `JsonDataOpen` を通さない。
- `providers/InputDataService.cs:123,130,147`: GUI計算要求も編集serviceからJSONをserializeしてから共通要求builderへ渡す。保存せずにGUIで計算してもSingle由来の投影を経る。
- `components/menu/MenuComponent.cs:303`: GUI保存は `GetSaveJson()` → `JsonSerializer.Serialize`。

### SingleをDoubleにcastするだけでは保存後の期待値にならない

GUIの計算snapshot/保存JSONはSingleをSystem.Text.Jsonで短いround-trip decimalへserializeし、そのJSONをDoubleとして計算要求へ読み直す。このため、数値期待値は

```text
Q(v) = parseDouble(serializeSingle(parseSingle(v)))
```

で作る必要がある。`double(float(v))` だけを期待値にすると誤る。

一時ハーネス `tmp/p7-frameweb-plan/fem_contract/float-probe/` を .NET10.0.13 で実行し、製品と同じ `JsonElement.GetSingle` → boxed float の辞書 → `JsonSerializer.Serialize` → `GetDouble` を17値で確認した。GUI自体は起動していない。結果は `float-projection-probe.json` に保存。

| 元JSON値 | Single内部値（Doubleで表示） | 再保存JSON数値 / Q(v) | 元値との差 |
|---:|---:|---:|---:|
| 52218663 | 52218664 | 52218664 | +1 |
| 104437326 | 104437328 | **104437330** | **+4** |
| 10.3 | 10.300000190734863 | 10.3 | 0 |
| 12.15 | 12.149999618530273 | 12.15 | 0 |
| 7.38113 | 7.381130218505859 | 7.38113 | 0 |
| 297.68 | 297.67999267578125 | 297.68 | 0 |
| -8299.53 | -8299.5302734375 | -8299.53 | 0 |
| 1.234567891234 | 1.2345678806304932 | 1.2345679 | 約8.766e-9 |

104437330 は保存後Doubleの値であり、floatの厳密値104437328とは異なる。再びSingleへ読めば同じbit列に戻るため、serializerのround-trip保証に反しない。再保存で見かけのdecimalが元に戻る値でも、GUI内部の描画/geometry処理はSingleを使う点を区別する。

### P7計画に採るべき受入基準

1. generatorはPDF/正本に由来する正規精度をnative JSONへ保存し、GUIに合わせて最初からSingleへ落とさない。原本native SHAをsidecarへ記録する。
2. raw native → headless の入力投影では、既知の2D補完・部材荷重mm/0.01丸め以外にSingle化を入れない。本P7のfix_node/element/node/load_nodeはDouble経路を検証する。
3. GUI互換確認用に、型別のQ(v)を独立に適用した期待JSONを一時領域で用意する。参照ID・case選択・COMBINE係数をまとめてfloat化しない。
4. GUI読込→別名保存を期待JSONと比較し、Single保存投影・既知metadata以外の差異を許容しない。幅広い一律tolで量子化を隠さない。GUI保存を原本nativeへ自動的に置き換えない。
5. raw native/headless と GUI投影後/headless の数値差を区別して記録する。GUI計算結果の比較対象は後者。派生計算はそれぞれの基礎ケース結果とDouble係数から独立再構成する。
6. solver浮動小数点誤差の受入値は入力投影差と別に扱う。量子化でPICKUPの選択源が変わった場合も黙って同一とせず、source IDと相関全成分の差として報告する。

この修正により「GUI保存往復で正規Double値が完全保持される」「raw headlessとGUI解析が無条件に数値一致する」との要求/主張は採らない。ソフト改修を含めないP7 native生成では、正規出力とGUI既知精度の双方を追跡して互換性を判定する。
