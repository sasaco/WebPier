# WebPier 0710 → JRSNAP 5.2-L03 NDU 出力の計画調査

2026-10-17。実装なし、既存入力・出力・モデルは読取りのみ。これは親担当の計画作成用調査であり、モデル方針の決定ではない。

## 結論と境界

0710の同一計算実行からNDUを作るための荷重・寸法・柱配筋・並進ばねの根拠は揃う。0710単体は支持や非線形構成則を持たない帳票スナップショットなので、NDU生成には同一実行の0500結果、0710結果、読込み済み入力JSON、明示的なJRSNAP設定を渡す構成が必要。既存0710契約へ支持データを暗黙に混ぜない。根拠: `src/cli.py:64`、`:71`、`:80`、`:92`、`src/seismic_frame.py:66`、`./tests/test_seismic_longitudinal_calculator.py:147`。

**追加調査による訂正**: DF/GAM2の元情報は揃っている。見本 `08_線路.pdf` 28頁に平水位の加重平均式が明記され、WebPierにも適用できる。DF=4.7、GAM2=12.255319…（見本同様1桁採用なら12.3）。必須手入力の提案を撤回する。[詳細な根拠と適用条件](webpier-longitudinal-ndu-soil-derivation.md)。モデルはユーザーが見本同様を選択済み。解析profileの詳細確認は残る。旧見本の数値をコピーしない原則は維持する。

現`./post`にあるのはFrameWeb方向別JSON/付帯JSONの4ファイルで、NDUはない。PythonのNDU exporter/templateも見つからない。現在の公開登録はFrameWebについて0610/0620のみ: `src/frameweb_artifacts.py:33`。0710はPDF/JSONのみを宣言する既存テストがある: `./tests/test_frameweb_publication.py:44`。

## 必須情報と取得元

| NDU情報 | 取得元・再利用 | 確度/不足 |
|---|---|---|
| 節点・要素・部材役割 | 0710 `frame.nodes/members/node_ids`。`seismic_frame.py:66`、`:132`、`:161` | 確定。柱下端0.010mを実形状から分割し上から再採番する。固定IDを仮定しない |
| 座標軸 | 0710は上向きY、JRSNAPは右X・下Y・時計回り正。マニュアル5.2 PDF38頁、抽出JSON `JRSNAP.json:283` | 変換要。例えば基礎天端を原点とするなら `y_native=y_footing_top-y_0710`。Xは保持。原点はプロファイルで明示 |
| 剛域/非線形 | 0710はh2,h3,h4がelastic、柱下端だけnonlinearメタデータ。`seismic_frame.py:167`、`:199`、`seismic_longitudinal_calculator.py:232` | 要判断。見本同様に微小部材以外を剛域化するなら、NDU exporter固有の明示変換規則が必要。0710を破壊的に変更しない |
| コンクリート | 0710 `frame.materials.column.fck/Ec`。元はraw `鉄筋.柱.concrete_strength_mpa`。`longitudinal_design_conditions.py:80`、`:104` | 確定。fckはMPa。EcはkN/m²→NDU kN/mm²へ1e6で換算 |
| 断面幅・高さ | 0710 `frame.sections.body`。raw B6/W6からの独立断面API `rebar_model.py:310`、`:339` | 確定。線路方向は幅W6、高さB6。m→mm換算。旧4500/2700を定数化しない |
| 主筋の位置・径・本数 | raw鉄筋→`load_member`、`section_geometry`、`member_preview`、`directional_rows(...,"線路")`。`rebar_model.py:184`、`:310`、`:492`、`:676`、`:1013` | APIあり。現在入力は76本/線路11行に展開できる独立fixtureテストあり。手動モードも尊重し、未完成配筋をゼロ本で通さない |
| 帯筋 | `column_rebar.hoop_rows` `column_rebar.py:159` とraw方向別effective_legs/pitch/diameter/material | 現入力に線路D22/10脚/150/SD390あり。区間限定または複数行の採用ルールはexporterに必要 |
| 鉄筋強度・Es・材料係数等 | 材質文字列SD390等はrawにある。例のNDUは`SectJiku1=390,200,...` | WebPierにNDU材料値変換APIなし。対応材質の明示テーブル/公式根拠/未対応材質の拒否を計画する。200等を無根拠に黙用しない |
| せん断スパン・非線形特性 | 構造高さは0710 geometry/frameにあるが、La採用式・非線形番号内各選択はない | 要profile/判断。単純にH4=4.9mをLaへ入れない。見本La=7.6mは柱以外の上部高さも含む |
| 固定荷重 | 0710 `vertical`と`basic_cases[0:5]`。`seismic_longitudinal_calculator.py:188`、`:204` | 確定。D1,D2,Wp,Sw2,Lの5ケース。浮力Nは既に負。方向ラベルで再反転しない |
| 桁/列車慣性力 | 0710 `horizontal`、ケースEQ1/EQL。`seismic_longitudinal_calculator.py:110`、`:210` | 確定。EQ1増分、EQL限定増分。列車Kh=.20適用済、再乗算禁止 |
| 自重慣性力 | 0710 `inertia/formulas`。`seismic_longitudinal_calculator.py:124`、`:199`、`:212` | 確定。H2/H3/H4と微小要素分割へ再配分。H1>0のpedestal H/M、非一様分布、ゼロ高さ合併を扱う |
| 荷重組合せ | 0710 `combinations`。`seismic_longitudinal_calculator.py:249` | 1ケース、ρm=1、αf=1、左方向、8係数すべて1。既存0610常時組合せを流用しない |
| 支持節点 | 0710 `frame.node_ids.footing_bottom` | 確定。0710ではIDが再採番済み。0610 support_node_idの数値をそのまま使わない |
| 水平・鉛直ばね | 同一実行0500 `short_term.Ks/Kv`。`calculator.py:105`、`:127`、`foundation_springs.py:29` | 値あり。現保存例は8,525,475/25,576,488。短期をL2用に採用する方針は明示。旧macro_handoff_singleを使わない |
| 回転ばね用B/L/kv | 同一実行0500 `foundation.B/L`、`short_term.kv`。`calculator.py:105`、`:129` | 値あり。線路方向B=sum B7..B9、L=sum W7..W9。現在7/9/405976。旧値持込み禁止 |
| 地盤種別/φ/γ1 | 0500 `support_layer`およびraw地層。`inputs.py:128`、`:146`、`calculator.py:134` | 材料値あり。砂礫→砂質土の既存分類根拠は`calculator.py:155`。γ1の水位条件/粘着力の採用範囲はNDU profileで明示 |
| 有効根入れDF/平均GAM2 | 0500の表層厚・単位重量、0710の平水位、見本08 PDF28頁の明示式 | **既存入力から導出可能**。WebPierは4.7/12.255319…、NDU採用案12.3。専用計算関数を追加 |
| KR2/最終勾配 | V5.2マニュアルPDF155/515頁 | 5.2既定はKR2=2、最終勾配1/20。5.3既定を使わない。明示profileとして記録可能 |
| 解析ステップ・収束・制御節点・安全係数等 | 0710では定義しない | 設定profileが必要。見本の`DataInfo`、`SectSafe`等の全フィールドを一度版別に意味確認し、既知項目だけを明示的に保持する |

上表のPython相対パスは `src/` 配下。マニュアル抽出JSONは `.agents/agents/jrsnap-operator/manual-comparison-data/JRSNAP.json`。

## DF=3.78、GAM2=11.6の検討結果

5.2マニュアルはDFを「フーチング底面の有効根入れ深さ」、GAM2を「DF区間の土の平均有効単位体積重量」と定義する。PDF155頁/515頁、抽出JSON `JRSNAP.json:1102`、`:3622`。

WebPierの現入力では:

- H5=0、H6=2.7: `./pre/input.json:500`。
- df1=df2=2.0: 同`:504`。
- 高水位hw1=3.78、平水位hw2=2.7: 同`:509`。
- 表層湿潤18、水中8: 同`:634`。支持層湿潤19、水中10、φ42.2、qu0、Ed165760: 同`:648`。
- `H6+H5+MIN(df1,df2)` の既存式が表層厚4.7mを計算する。`input_formulas.py:94`、`:105`、`inputs.py:84`、`:111`。追加調査で見本の表層厚とDf、平水位の式の対応を確認した。今回の同一土被り・表層/支持層条件でDfに採用できる。
- WebPierの検索範囲でGAM2用平均処理はなく、0500出力にも当該キーはない。`calculator.py:127`が生成する結果は基礎寸法/地層/支持層/モデル係数/長短期ばねである。

現入力の3.78は高水位でありDFへコピーしない。WebPierのDfは4.7、平水位hw2=2.7なので、GAM2=(18×2.0+8×2.7)/4.7=12.255319…。見本の11.6は(18×1.08+9×2.7)/3.78の1桁採用値と一致する。計画は既存地盤条件からの自動導出へ訂正し、適用条件と丸めを明記する。

## 旧見本から移植できるもの・除外するもの

形式見本は `.claude/docs/Example橋脚2/10_線路(耐震)/線路方向_朝里川温泉P1.ndu`。**全原本のコピーと数箇所置換を製品exporterにしない**。

- 荷重コードの形式例: 固定`JLoadInfo1`第4=0 (`:140`)、増分`JLoadInfo8`第4=1 (`:172`)、限定増分`JLoadInfo9`第4=4 (`:178`)。分布荷重と集中荷重の座標系の差は5.2マニュアルPDF156頁、抽出`:1109`。数値コードは実アプリとマニュアルで独立照合して採用する。
- 微小部材の例は`ElementInfo4` (`:58`)、`NonLinInfo1` (`:87`)、断面 (`:90`)、`SectSafe1` (`:106`)。新規profileに構成則や係数を分離する。未知フィールドを見本コピーに紛れ込ませない。
- 解析用直接基礎回転ばねは`FootInfo1` (`:114`)。支持数は並進2行+回転1行で`SuppotNum=3 / SuppotRow=2 / FootRow=1` (`:107`)。杭形式の`SuppotNum=SuppotRow`を適用しない。
- **別枠照査データCHOKU_KISO** (`:115`) は解析用FootInfoと独立。旧6×9、Df3.08を持ち、現WebPierまたは見本解析条件7×9/Df3.78と揃わない。今回の出力対象外とする案が適切。生成NDUの`ChokuKisoNum=0`、関連リンク0/空を正規化保存して確認することを実装初期ゲートとする（本調査ではその新規NDUを生成していないので読込可否を実証済とはしない）。
- **旧地層表示Tisou** (`:199`)、**他案件SDCリンクSoilRenkei** (`:213`)、**旧絶対NDTPath** (`:225`) を持ち込まない。WebPier解析で不要な表示・連携情報は明示的に無効な状態から生成する。NDU保存だけでNDT/解析結果を作った扱いにしない。

## 再利用するコードと変更候補

- 新規候補: `src/jrsnap_export.py`（純粋変換とCP932/CRLF serializer/構造検証）、`jrsnap_profile.py`（5.2用既知設定・材料対応・設定検証）、`jrsnap_artifacts.py`（出力先・付帯根拠）。名前は計画時の候補。
- `cli.py:98`付近: 同一メモリ計算結果から0710 exporterを呼ぶ。現入力は`:64`で一度読む。既存PDF/JSONの再読込みやPDF逆抽出は不要。
- `frameweb_artifacts.py:62`または抽出先の汎用公開登録: `0710.native=post/線路方向.ndu`と付帯情報を登録。現在FrameWebのみ分岐する境界を明示的に拡張する。
- `cli.py:112`、`:125`、`:133`、`:149`: 既存のステージング、全成果物ハッシュ、公開後検証を再利用。NDUを単発writeしてPDFと世代が混じる経路を作らない。
- `editor_calculation.py:27`、`:137`: GUI側の公開物検証もNDUを含む契約へ広げる。GUIだけ独自NDU計算を持たない。
- `rebar_model.py:676`の方向別集計を再利用。ただし同一中心・異材質を現NDU断面表で表現できるか、単一fyk制限を確認する。既存previewが未完成行をスキップする点（`:508`）をexporterの成功扱いにしない。
- 既存 `frameweb_common.py:19` は正規作用ベクトルの考え方を共有できるが、native軸と限定増分・台形分布の意味は異なるためFrameWeb JSONへ迂回変換しない。

## 検証計画に必要な条件

1. **先行仕様ゲート**: V5.2-L03で空の正規モデル/最小モデルを保存し、必要なNDUレコード・型・既定値を確認する。非線形構成則、材料、安全係数、直接基礎回転設定、解析オプションのフィールド対応を確定。旧原本全コピーで未知を残さない。
2. **構造整合**: 連番、件数、節点/要素/断面/非線形/支持/組合せ参照、0.010m要素、CP932変換不可文字、非有限値、単位と符号。座標の表示丸めで短い要素を潰さない。B6/B7/W6/W7等変更時に原本値が残らないこと。
3. **入力同一性と作用の独立検証**: 8荷重区分、Kh再乗算なし、台形分布の合力・一次モーメント、H4分割前後の荷重保存、微小要素込みの載荷範囲、非ゼロH1と偏心、ゼロ高さ/合併節点。材料・配筋は現入力の独立oracleから検証。
4. **公開契約**: `--stage 0710`と`all`、別output/post、overwriteなし/あり、入力不足/不正・文字コード・保存失敗・ロックによる世代混在防止。0610/0620 post成果物は保持。付帯情報にsource SHA、5.2版、profile版、変換規則を残す。
5. **アプリ互換**: `.agents/skills/jrsnap-input-open-save/scripts/save-ndu.ps1 -Path <候補.ndu> -Version V52` のdry-runで読込み・保存・再保存の安定性を確認。根拠は同スクリプト`:111`以降、`roundtrip.cs:63`の公式読込/保存関数呼出し。単なるヘッダー検査とは分ける。
6. **範囲外**: NDT生成、解析実行、応答/照査結果の一致は今回の要件に自動追加しない。

既存関連テストは `test_seismic_longitudinal_calculator.py:133`（符号・Kh・限定増分）、`:147`（0710境界）、`:366`（微小要素）、`test_seismic_longitudinal_cli.py:45`（同一メモリ連鎖）、`:123`（公開失敗）、`test_column_rebar_reference.py:121`/`:146`（両方向の独立配筋oracle）、`test_frameweb_publication.py:44`（現0710公開物契約）。NDU専用の受入テストは新規に必要。

## ユーザー判断/不足の一覧

- **モデル方針**: 見本どおり柱下端非線形+他部材剛域+非線形回転ばねをユーザーが選択済み。
- **DF/GAM2**: 元情報不足という初期判断を訂正。既存地盤と平水位から自動導出する。元情報不正・未対応条件は公開しない。
- **profile採用**: 見本の解析設定・安全係数・非線形選択をV5.2用の明示profileとして採るか。5.2既定のKR2=2/最終勾配1/20は根拠あり。他の係数も項目単位で根拠を残す。
- **将来編集の扱い**: 自動生成NDUを手編集した場合、再生成で置換する出力物とするか（既存--overwrite規則と同じ扱いが自然）。自動マージは今回含めない。

## 現在の保存出力を直接再利用しない理由

調査時 raw `./pre/input.json` のSHA-256は `D8DA41D8D87A04B33A35CC45226231564EBD1DC1DCDCF3ABCE397D7487887F78`。保存0500結果の`provenance.input_sha256`は `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b` (`./output/0500_直接基礎.json:107`)。保存済みJSONと現入力の世代が異なるため、NDU生成はPDF/JSONファイルを後読込みせず、CLIが現入力を一度読んで算出したメモリ値を使う必要がある。
