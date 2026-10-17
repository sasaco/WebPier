## Implementation Plan: WebPier Transverse FrameWeb Input

作成日: 2026-10-16 / slug: `webpier-transverse-frameweb-input`

状態: 2026-10-16、実装・独立レビュー・FEMPython受入・全3385件の回帰確認（修正箇所とTkの個別実行を含む）・通常0620による本番生成まで完了。[実装・検証記録](../research/webpier-transverse-frameweb-implementation-verification.md)に成果物SHAと実行別の結果を記載。

### Purpose

`.claude/docs/Example橋脚2/09_直角.pdf` と `.claude/docs/Example橋脚2/09_直角/frameWebForJS.json` の数値対応を明らかにし、WebPierの0620帳票と同じ骨組・作用を、指定FEMPython内のFrameWebforCS GUIと既存headlessで読み込み解析できる `./post/線路直角方向.json` に出力する。これはnative保存JSONであり、Python解析エンジンへ直接渡す入力形式ではない。

前回のユーザー回答「通常の橋脚計算でもJSONを自動更新する」と今回の「同様に」を引き継ぎ、通常の `--stage 0620` / `--stage all` とGUI全工程計算に組み込む。現物の資料名は **`./output/0620_直角方向荷重.pdf`** であり、指定の「0620_線路直角方向荷重.pdf」に相当する。資料名を変更せず、生成先はユーザー指定名にする。

### Scope

正規0620結果をnative保存形式へ変換する処理、通常計算からの自動生成、公開・世代検証、実ソフトでの受入を対象とする。既存の[線路方向計画](webpier-longitudinal-frameweb-input.md)は本調査開始時には未実装だったが、調査中に並行して実装が開始された。以下は開始時の数値調査と、完了前に確認した統合先の変更を区別して記す。

#### 調査根拠と対象世代

- [Example2の数値対応](../research/webpier-transverse-frameweb-example-mapping.md)：29頁を抽出、入力p1～15・結果p16～17を描画して確認。17荷重・15Define・16組合せ・8抽出を全件対応付け。
- [WebPier計算経路](../research/webpier-transverse-frameweb-pipeline-investigation.md)：現0620の正規値、用途別L/I、37状態、CLI/GUIの変更箇所、既存試験。
- [FEMPythonの契約と実測](../research/webpier-transverse-frameweb-fem-contract.md)：native読込み、分布荷重、符号・候補選択、単精度、既存headlessの実測。

本計画と根拠文書のページ番号はPDF先頭を1とする物理ページ。PDF→JSONの対応を調べた上で、日常実行時にはPDFを再解析せず、**PDFと同じ正規0620結果オブジェクト**から生成する。表示桁からDouble値を復元したり、古い保存結果を流用したりしない。

| 調査対象 | SHA-256 |
|---|---|
| `.claude/docs/Example橋脚2/09_直角.pdf`（29頁） | `b6a7f5658b9f98ee8a7d6b29691edcb0209bc7455fa8309d4e3a2e16605474de` |
| `.claude/docs/Example橋脚2/09_直角/frameWebForJS.json` | `8ff9e589ffd70af6cba3c89cb999b2735ce9f7734801df29015b7cc1e5cbf5ff` |
| `./pre/input.json` | `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b` |
| `./output/0620_直角方向荷重.pdf`（12頁） | `64a5ac2380530b4fb1996889b11a375a31fc7b6821669731d022eba1fff3140a` |
| `./output/0620_直角方向荷重.json` | `07f76b318c482d92353a6b037c2bb522fbcdb44158a513322066cbbbe49a2bca` |

現入力・現コードから0500/0600/0620をメモリ内で再計算した結果は、CLIと同じ直列化・改行によって保存済み3 JSONとbytes一致した。PDFの入力SHAも同じ。既存成果物の上書きはしていない。証跡は `tmp/webpier-transverse-frameweb-plan/`。実装時は最新世代を再確認し、ここに記載したSHAを将来入力の固定条件にしない。

外部ソフトは `C:/Users/sasai/Documents/structural-mcp/FEMPython/`。調査時ソースHEAD `7488c8fb4d6c100438a9691747ceb11fd9e66358` と、既存Release runnerのengineVersion `1.0.0+018d0d0ee9453464b0b541a5344ce5a6c0acdfc6` は異なる。実測と読解の根拠を区別する。今回の外部ソフト作業ツリーはcleanであり、ソフトの修正・ビルドは今回の前提にしない。

#### 変更ファイルと成果物

| 対象 | 変更内容 |
|---|---|
| 共通拡張 `src/frameweb_export.py` | 追加された0610変換器の共通直列化を抽出し、方向別adapter・検証profileからnativeを構築する |
| 新規 `src/frameweb_transverse_cases.py` | 0620の17基本、用途別L+I補助、Define/Combine/Pickup、出典対応 |
| 共通拡張 `src/frameweb_artifacts.py` | 現0610固定のファイル名・規約版・付帯JSON・検証をstage別登録と全体manifestへ拡張 |
| 共通拡張 `src/artifact_publication.py` | 追加された親別staging/backup/復元を再利用し、必要な公開後検証・journalだけを拡張 |
| `src/cli.py` | 0620/allへの接続、共通 `--post-dir`、stage別成果物登録 |
| `src/editor_calculation.py` | post成果物を含めた完了検証・改変検知、明示的な4 PDF一覧 |
| `./README.md` | 出力先、補助ケース、係数、ソフト互換・再生成方法 |
| 新規 `./tests/test_frameweb_transverse_export.py`、`test_frameweb_transverse_cases.py` | 方向固有の独立期待値・全状態・異常入力 |
| 共通 `test_frameweb_cli.py`、既存 `test_transverse_cli.py`、`test_editor_calculation.py` 等 | 方向間非干渉、公開失敗・復元、GUI世代検証 |
| 新規 `./tests/fixtures/frameweb_transverse_example2_mapping.json`、`frameweb_transverse_webpier_reference.json` | PDF/JSONから独立転記する数値、既知差異、全240名目係数、37状態 |
| 納品 `./post/線路直角方向.json` | FEMPython native保存JSON |
| 同時出力 `./post/線路直角方向.provenance.json` | 入力・0620 PDF/計算JSON・nativeのSHA、変換版、全ケース/補助/出典対応 |

線路方向側 `frameweb_cases.py` と共有するのは形式・モデル直列化・公開処理。0610と0620の作用schemaや衝撃の意味は方向別adapterで明示する。共有CLI/publisher/controllerの変更担当を一人に集約し、進行中の0610実装を上書きしない。

**並行変更の再確認（2026-10-16 19:49 JST）**：`frameweb_export.py`、`frameweb_cases.py`、`frameweb_artifacts.py`、`artifact_publication.py` が存在し、CLI/GUIにも0610の接続が入っていた。完了・受入済みとは判定していない。調査担当はこれらを変更していない。実装開始時に再読込し、次の差分を統合する。

- `build_frameweb_input(result)` / `FrameWebExport(document, source_mapping)` の公開戻り値を維持し、stageでadapterを選ぶ。現在の `_validate_frame` はlongitudinal方向限定、`validate_frameweb_input` はload/Define各28・gyのみ・線路用Define形を固定している。単に条件を削除せず、共通参照検証＋明示した0610/0620 profileへ分ける。0620は22 load/19 Define・gx/gy・単線候補を検証し、0610の厳密な検証を残す。既存の引数なし呼出しは0610として互換維持し、artifact validatorは明示stageを渡す。
- `frameweb_paths(post_dir)`、`build_provenance(...)`、`validate_frameweb_artifacts(...)` は現在0610固定。stage引数/descriptorを追加し、既存呼出しの既定は0610。名前・帳票stem・規約版を一つの登録に寄せる。`resolve_post_dir` は既存の共通実装をそのまま再利用する。
- 現sidecarはschema1でnative/0610 JSON/PDFの3件を結ぶ。全体manifestとpublication IDの新規出力はschema2へ版上げする。0610の既存schema1は旧形式として方向単独の確認に限定し、両方向allの世代保証を満たしたとは扱わない。通常allの次回生成で両sidecarを同じ新形式へ更新する。0620単独実行で既存0610 sidecarを勝手に書き換えない。
- `ArtifactStaging`、`validate_destinations`、`publish_outputs`、`RecoveryError` と従来CLI `_publish_outputs` の互換は維持する。親別backupと通常例外時の復元は追加済みなので作り直さない。全体journal/公開後検証はまだ別途確認し、不足部分を追加する。
- 現CLIは `"0610" in stages` の時だけnativeを作る。これを選択stageごとのregistryへ広げ、全nativeを先に用意してから全sidecarを末尾へ並べる。GUIは既に `pdf_paths` 明示と10成果物検証へ変更されているため、`paths[::2]` の再修正は不要。方向別post登録を両方向12件へ拡張する。

0500/0600/0610/0620の計算式・入力・帳票内容の変更、例題の修正、地震等の新荷重、断面照査、FEMPython本体の改修は対象外。通常生成は標準Pythonで完結し、FEMPython起動・Excel・OCR・ネットワークを要求しない。FEMPythonは受入検証に使用する。

#### 数値リンク：形状・材料・支持条件

根拠はExample p1～2、WebPier p1～2、`result.frame`。同じ形状でも節点IDは異なるためWebPierのIDを維持する。

| 役割 | Example ID | WebPier ID | 現WebPier `(x,y)` m |
|---|---:|---:|---|
| 梁天端 | 1 | 1 | (0,10.3) |
| H2/H3境界 | 2 | 5 | (0,8.3) |
| H3/H4境界 | 3 | 6 | (0,7.6000000000000005) |
| 基礎天端 | 4 | 2 | (0,2.7) |
| 基礎重心 | 5 | 3 | (0,1.350000023841858) |
| 基礎底面・支持点 | 6 | 4 | (0,0) |

- 部材1＝1→5、2＝5→6、3＝6→2、4＝2→3、5＝3→4。現在1/2はbeam材料、3はcolumn材料、4/5は剛域。
- 弾性断面は `A=12.15 m², Iz=20.50313 m⁴, E=26,500,000 kN/m²`。**線路方向のIz=7.38113を使わない。** 材料が現在同値でも梁/柱の参照を保持する。
- 外側断面TYPE1の内部IDは共通計画に合わせ、1＝body/梁、2＝body/柱、3＝有限剛性剛域、4＝H1/parapet/柱（存在時）。`member.e` とloadの `element=1` は異なる階層。
- 剛域はExampleの `E=26,500,000, A=Iz=1000` を明記した互換規約として採用する。PDFに1000の指定はなく完全剛体ではない。nativeのrigid指定も有限断面への切替なので、それへ機械的に置換しない。
- `dimension=2`、x-y平面、曲げ自由度rz。支持点は4、`tx=Ks, ty=Kv, rz=Kr`。長期1は `(4,262,769,12,788,244,86,320,647)`、短期2は `(8,525,475,25,576,488,172,641,294)`。Krは正規0500の直角方向値。長期の2倍やSingle化値から再構成しない。
- 基本1～8は長期1、9～17は短期2で、Example PDF/JSONも全件一致。線路方向で発見したばね番号差を直角方向へ持ち込まない。
- native拘束値は0自由・1固定・その他ばね。必要ばねは正、値1を固定へ黙って変換せず拒否。NaN/Inf・未知参照・零長部材も拒否する。
- H1・偏心・零長区間の統合は正規frameとload_anchorsを信頼し、座標やIDを輸出側で再計算しない。`Xp=1e-5`、未使用3D欄等はソフト互換値として記録する。自重自動加算・独自端部解放は導入しない。

#### 数値リンク：17基本作用と荷重点

正規Nは下向き、Hは右向き、Mは時計回りを正とし、nativeは **`ty=-N, tx=H, rz=-M`**。`actions` の `points/line_loads` だけを荷重へ写す。支承別 `rows`、表示用 `table_totals`、`details` は再載荷しない。

| 基本 | 作用 | 現WebPierの天端 N / H / M（kN, kN m） | その他 | WebPier PDF |
|---:|---|---|---|---|
| 1 | D1 | 8299.52 / 0 / 0 | 重心N4167.4501953125、柱qN297.68 | p3 |
| 2 | D2 | 780 / 0 / 0 | 重心N1830.5999755859375 | p3 |
| 3 | WP1 | ― | 重心N-2381.39990234375 | p4 |
| 4 | WP2 | ― | 重心N-1701 | p4 |
| 5 | WP3 | ― | 重心N-0（ゼロケース） | p4 |
| 6 | S2 | 710 / 0 / 0 | ― | p4 |
| 7 | S10 | 1140 / 0 / 0 | ― | p4 |
| 8 | S30 | 1270 / 0 / 0 | ― | p4 |
| 9 | L上り | 567.39 / 0 / 1210.08 | ― | p5 |
| 10 | L下り | 567.39 / 0 / -1210.08 | ― | p5 |
| 11 | L複線 | 1134.77 / 0 / 0 | ― | p5 |
| 12 | I上り | 171.70 / 0 / 364.43 | ultimate、係数1の基本値 | p6 |
| 13 | I下り | 171.70 / 0 / -364.43 | 同上 | p6 |
| 14 | I複線 | 328.70 / 0 / 0 | 同上 | p6 |
| 15 | LF車両横 | 0 / 111.69 / 430.01 | ±候補 | p7 |
| 16 | W1列車あり風 | 0 / 305.87999725341797 / 2124.358680408477 | 柱qH4.050000000000001 | p7 |
| 17 | W2列車なし風 | 0 / 611.75 / 4248.643817901611 | 柱qH8.100000000000001 | p8 |

天端はnode1、重心はnode3。分布区間はcanonical `column_line_load.member_ids=[1,2,3]`、y2.7～10.3の7.6m。D1はH2+H3の重複分を既に控除済み。総重量を再度足したり、Exampleの控除手順で再計算したりしない。

部材ごとに `mark=2,m1=m2=正ID,L1=L2=0,P1=P2` の実行行を作る。鉛直qNはグローバル `gy=-qN`、水平qHは `gx=qH`。空の編集行は生成しない。全長はframeが決めた各部材長で、番号の範囲から部材を推測しない。

現在のゼロMや上下対称は固定仕様ではない。非対称支承・土荷重偏心・負の分担率で生じるMを保持する。N=0でもM≠0の偶力は有効荷重。上り/下りは別正IDであり、下りを上りケース全体の負号で作るとNまで反転するので不可。

#### ExampleとWebPierを分けて扱う既知差異

| 項目 | 調査結果 | 実装での扱い |
|---|---|---|
| 車両横H/M | Example図は右H111.69・時計回りM430.01、JSONはtx=-111.69/rz=-430.01 | 図とJSONの相対符号が不一致。WebPierのH+をtx+、M+をrz−へ写す |
| W2モーメント | Example PDF2002.64、JSON2002.00。PDF結果側も後者を使用 | 例題の端数欠落を再現しない。WebPier正規M4248.643817901611を使う |
| 柱風の区間 | Exampleは上6.52m、下端1.08m非載荷。WebPier正規モデルは全7.6m | WebPierのmember_ids/全長を維持。例題から未指定の1.08m除外を追加しない |
| 連続分布構文 | Example `m1=1,m2=-3,L2=1.08` は旧結果では連続材端の控除。現C#は各部材にL2を適用し短い部材2を落とす | 各部材を正IDで明示する。FEMPython修正を前提にしない |
| D1集中力 | Example8299.53、WebPier正規8299.52 | WebPierの既存丸め経路を保持 |
| 衝撃 | Example単線227.78/複線428.28、WebPier基本171.70/328.70 | WebPierの橋脚用低減と用途別値を採用 |
| 旧結果キャッシュ | 16ケースのcached結果は保存入力の符号・端数を反映 | `result/three`等を生成入力へコピーせず、別途解析する |

例題W1の合力は連続材解釈で332.286 kNだが、空行だけ除いた現headless再解析では325.077 kN。W2は664.562対650.144 kN。この差を出力器の許容差へ隠さない。例題1.08m除外の設計理由は確定していないが、WebPierの現定義を変えない本作業の阻害条件ではない。

WebPierの独立釣合い参考値はLF `(Fx,M時計回り)=(111.69,1580.417)`、W1 `(336.659997253418,5474.992652118683)`、W2 `(673.3100000000001,10949.808817901612)`。天端Mは付加偶力であり、基礎底まわりには `H×10.3 + qH×7.6×6.5` を別途加える。これらは入力作用で、外部ソフトの反力符号と区別する。

#### Define・係数・相関を保存する変換

正規モデルは `schema_version=2,stage=0620,direction=transverse,case_model_version=example2-nonseismic-pier-impact-v1`。基本17、Define15、Combine16、Pickup8。係数表は **16×15＝240セルのDefine係数**であり、基本17列や0610の表へ読み替えない。

原Define1～8は基本1～8、9=[9,10]、10=[11]、11=[12,13]、12=[14]、13=[15,-15]、14=[16,-16]、15=[17,-17]。複線の表記L3/I3と係数表L2/I2はラベル別名であり、ID10/12で対応させる。

native Defineは加算ではなく候補包絡。単線LのDefine9とIのDefine11を別々に選ばせると、上りL＋下りIが許される。WebPierの `selection_group=single_track` と候補 `direction/compatibility_group` を満たすため、**同じ線の解決済みL+Iを短期支持2の一つの荷重ケースに合成**する。nativeへ独自groupキーを入れても対応できない。

用途別L/Iは `combinations[].resolved_components[].candidates[].loads` を採用する。`remaining_multiplier=1` で係数適用済み。例として最大複線Iは443.7（328.7×1.35=443.745ではない）、使用性複線Iは245.3（328.7×0.75=246.525ではない）、使用性単線IMは272.73（364.43×0.75ではない）。Lにも表の丸めがあるため、L/I両方を解決値から使う。

| native補助load | native補助Define | 意味 | 現L N/M | 現I N/M | 合成N/M | 使用Combine |
|---:|---:|---|---|---|---|---|
| 18 | 16 | 複線・終局最大 | 1531.94/0 | 443.7/0 | 1975.64/0 | 1,10 |
| 19 | 17 | 複線・終局一般 | 1395.77/0 | 404.3/0 | 1800.07/0 | 2,8,11 |
| 20 | 18 | 複線・使用性 | 1134.77/0 | 245.3/0 | 1380.07/0 | 5 |
| 21 | 19候補1 | 単線・使用性上り | 567.39/1210.08 | 128.5/272.73 | 695.89/1482.81 | 7,15,16 |
| 22 | 19候補2 | 単線・使用性下り | 567.39/-1210.08 | 128.5/-272.73 | 695.89/-1482.81 | 7,15,16 |

原17基本・15Defineは監査用に残し、nativeは **22 load / 19 Define / 16 Combine / 8 Pickup** とする。追加Define16～18は単候補、19は `[21,22]`。該当Combineから元L/Iの2列を同時に除去し、補助Defineを**係数1**で参照する。元係数との二重乗算・二重計上を禁止する。

D/W/LF等は正規resolverの `_scale` と同じ線形倍算なので、原基本・原Define・名目係数を使う。これが正規resolved点/線荷重と一致することを構築時に照合し、一致しない新定義を黙って近似しない。分布荷重のソルバー丸めは基本を解析する段階で起きるため、係数適用済みqを再度2桁にして基本へ焼き込まない。

**投影順序の具体例**：正規 `_scale` はD1のqを `297.68×1.1=327.448` とし、2桁へ再丸めしない。基本q297.68を解析して応答を1.1倍するnative方式は、この327.448を保存する。resolved qを別のmark2基本へ焼き込むとソルバーが327.45に変え、全長7.6mでは鉛直合力を0.0152 kN増加させる。よってD1×1.1用の補助を追加する案は採用しない。「resolvedを再度solver入力にした結果」を無条件oracleにせず、**正規物理作用327.448**を一次基準にする。現在の22/19件はこの入力で正規作用との同値性が成立することを確認する受入値で、将来未知の入力を件数へ無理に合わせる仕様ではない。

入力比較は (1) 未投影canonical物理作用、(2) 基本ケースをnative投影した作用×native係数、(3) 支持別解析応答、(4) 37状態、(5) Combine/Pickup包絡の順で分離する。(1)と(2)の差は独立に算出する。現在のqは2桁なので一致する。将来の入力で強度/距離投影により下記の転記・演算誤差基準を超える差が出る場合は、黙って補助へ焼き込んだり許容差を広げたりせず、位置・元値・投影値付きエラーで公開を止める。形式上の同値性と、正規作用の再現性は別々に検証する。

補助は値の偶然一致で重複排除せず、family/usage/係数役割/track/spring/elementの意味で固定スロットを与える。同じ補助を使う複数Combineの候補値・参照が一致することも確認する。正規値がゼロならIDを詰めずゼロ定義を保持し、名目係数0でL/I成分が欠ける場合はその補助参照を外す。片方だけ存在、支持/断面違い、未対応groupや係数形は明示エラーとし、別ばね荷重を合成しない。

LFとW1は**独立した±**のまま。各横荷重のH/M/qHは一緒に反転し、無関係な鉛直作用は反転しない。現在の横荷重N/qNは0であることを検証してからnative負IDを使う。将来水平Defineに非零鉛直成分が入った場合は、この表現を無条件に再利用しない。

| Combine ID | 有効項（Tは上表のL+I） | 状態数 |
|---:|---|---:|
| 1 | 1.1D1+1.2D2+S10+T最大+1.23LF±+W1± | 4 |
| 2 | 1.1D1+1.2D2+S10+T一般+1.35LF±+W1± | 4 |
| 3 | 1.1D1+1.2D2+S2+1.2W2± | 2 |
| 4 | 1.1D1+1.2D2+S30 | 1 |
| 5 | D1+D2+S2+T使用性複線 | 1 |
| 6 | D1+D2+S2 | 1 |
| 7 | T使用性単線(up/down) | 2 |
| 8 | D1+D2+S10+T一般+1.23LF±+W1± | 4 |
| 9 | D1+D2+S30+W1± | 2 |
| 10 | Combine1の項+WP3 | 4 |
| 11 | Combine2の項+WP3 | 4 |
| 12 | Combine3の項+WP3 | 2 |
| 13 | Combine4の項+WP3 | 1 |
| 14 | D1+D2+WP2+S2 | 1 |
| 15 | D1+D2+WP3+S2+T使用性単線(up/down) | 2 |
| 16 | D1+D2+WP1+S2+T使用性単線(up/down) | 2 |

合計**37状態**。単線L/Iを独立直積にすると43状態になり不正な6状態が混入する。Combine10～13もnativeに他Combine参照を作るのではなく表の項を展開する。Combine9の風は原定義どおりW1を使い、名称からW2へ訂正しない。

Pickup1～8の参照先は順に `[1,2,3,4] / [5] / [6] / [7] / [8,9] / [10,11,12,13] / [14] / [15,16]`。nativeではDefineのC列の**値＝基本ID**、Combineの**C列番号＝Define ID・値＝係数**、Pickupの**C列の値＝Combine ID**。これらを混同しない。

#### 共有する出力契約と精度境界

- stage別登録で0610→`frameWebForJS.json`、0620→`線路直角方向.json`、それぞれ同名stemの `.provenance.json` を管理する。前のユーザー指定名を変えない。
- 0620単独はPDF/計算JSON/native/sidecarの4件。0610単独は線路側のみ、0500/0600単独はpostを触らない。直角だけ実装済みのallは既存8+直角2＝10件、両方向実装後は12件。途中状態を最終両方向完了と報告しない。
- 共通 `--post-dir` は明示値を最優先。既定のproduction outputなら `./post`、カスタムoutputならその配下 `post`。CLI/GUI/検証が同じ解決関数と成果物登録を使う。
- 各出力親内にstaging/backupを作り、全旧版退避→全新規配置→sidecar最後の順で公開する。途中例外では新規を除去し旧版へ逆順復元。別volume間のrenameは行わない。既存ファイルなしの場合や復元失敗の復旧先も扱う。
- 強制終了後は次回起動時に未完了journal/世代混在を検出し、成功表示を止めて退避先と復旧対象を示す。自動復旧で他の並行計算を上書きする機能は今回追加しない。通常例外時の自動復元と区別してREADMEへ記す。
- 真の複数ファイルOS原子性は保証できない。各sidecarは対象のPDF/計算JSON/native/input SHAと同じpublication IDを持ち、ジョブ全体の宣言成果物を検証してから成功とする。共通 `artifact_manifest` に**その公開ジョブの全非sidecar成果物**の役割・パス・SHAを列挙し、`expected_sidecars` に必要sidecarの役割・パスを記す。両方向allなら非sidecar10件＋sidecar2件。両sidecarのmanifest・publication IDが一致し、宣言集合がジョブ登録と完全一致することを確認する。sidecar同士のSHAを相互参照する循環は作らない。一方が存在するだけでall成功とせず、プロセス停止後の混在も検知する。
- nativeは既知キーだけを出し、`result/resultDimension/three`・独自provenance・空編集行を含めない。**全成分ゼロの点荷重行・分布荷重行も省略し、ケースとDefineのIDは残す。** ゼロ値の行を残すと現runnerはそのケースも解析するため、EMPTY扱いと混同しない。現在のケース5などの省略一覧を生成モデルから予測して `EMPTY_LOAD_CASE_SKIPPED` と派生Defineのゼロ省略を検証する。
- 実装時の実ソフト検証で、全零の抽出対象Combineは利用不能参照になることを確認した。例えば使用性係数0ではCombine7が利用不能になり、Pickup4が `INVALID_DERIVED_REFERENCE` で失敗する。固定スロットと出典対応を維持する今回の形式では、有効な非零load→Define→Combineを辿り、利用不能Combineを参照するPickupは位置付きエラーで**公開前に拒否**する。非零係数でも元作用が全零なら同じ検査を行う。利用されない零基本や、他の有効成分を持つCombine内の零成分は引き続き許容する。微小荷重・架空荷重を補わず、既存成果物は保持する。
- 使用中Defineに零候補と非零候補が混在する場合も拒否する。実ソフトは零候補を落としてexit0で包絡を返すため、参照の存在確認だけでは不十分である。helper21だけを零とした診断では、本来0となるCombine7の天端dy最大値が負値になった。未使用の原Defineはこの制約の対象外とし、N=0でもM非零の荷重は有効候補として保持する。
- 保存nativeの数値をPDF表示桁やfloat32へ先に丸めない。既存headless直接読込みはDoubleだが、GUIはnode/section/spring/load等をSingleで保持する。GUI往復の期待値は型ごとに `Q(v)=DoubleParse(JsonSerialize(SingleParse(v)))`、Combine係数はDouble。単にDouble(Single(v))とするのも不正確。
- ソルバーは部材荷重P1/P2を2桁、距離をmmへ投影する。保存値・ソルバー投影値・GUI再保存値を別々に記録して検証する。GUI別名保存は正式nativeを上書きせず、そのSHAが変われば元sidecarは無効とする。

### Implementation Steps

以下は実装時の順序。高リスクの候補相関・数値投影を先に確定し、受入用の候補を一時領域で検証した後に通常計算へ接続する。各段階で指定外の資料・成果物・既存staged変更を保護する。

#### Step 1: 独立期待値と入力・外部形式の契約を固定

- [x] 最新入力・対象PDF/JSON・外部runner/主要ソースのSHA、版、dirty状態、既存postを記録する。進行中の線路側実装を再読込し、上記の0610固定APIと検証profileを拡張する場所を確定する。共有変更の競合がある場合は担当間で所有範囲を合わせてから編集する。
- [x] Example入力p1～15とWebPier p1～12から骨組、支持、17基本、15Define、240係数、8Pickupを独立fixtureへ転記する。既知差異を数値と出典ページごとに区別する。
- [x] 正規schema/stage/direction/case/frame版、全ID・anchor・material/section・単位・有限値を検証する契約を定義する。欠損をゼロに、未知形式を既知形式に推測しない。
- [x] 外部契約を小さな診断モデルで固定する。gx/gy、節点H/M、長短期支持、ゼロケース、負ID、独立Defineと同線L+Iの違いを確認する。

**Verification**: 実装関数から作らない期待値が揃う。単線L/Iの曲げ方向を意図的に相反させた診断で、独立包絡と同線包絡を区別できる。Exampleの不整合を「期待値一致」で正当化しない。

#### Step 2: 共通native直列化と0620基本作用の変換

- [x] ファイルI/O・PDF解析・再計算を含まない純粋関数でframe、要素TYPE、支持、点/線荷重を変換する。入力オブジェクトを変更せず、出力順とIDを決定的にする。
- [x] WebPierの役割・ID・材料と直角Iz/Krを維持し、17基本をすべて生成する。D1の重複・D2重心荷重の欠落を防ぐ。
- [x] 分布を実在する各部材へgx/gyで明示し、0作用と空行を区別する。風1.08mの除外や負m2構文を持ち込まない。
- [x] 既存frameのH1・零長統合・偏心・異材料を同じadapterで通す。未対応断面/部材種は位置付きエラーにする。

**Verification**: 6節点/5部材・全ばね・全17作用を、支持別、節点別、部材別のベクトルで照合する。合力だけの比較にせず、荷重点の取り違えも検出する。水平単位荷重と偶力の反力符号、D1局所xと明示gy、風gxを小モデルで解析確認する。

#### Step 3: 用途別補助・相関・全状態と出典の構成

- [x] 上表の固定5補助スロットを正規resolved L/Iから作り、支持/element/載荷位置ごとに合成する。単線のup/downを同じ方向で対応させる。
- [x] 原Defineと4補助Define、全16Combine、8Pickupを構成し、L/I旧列の除去と補助係数1を保証する。非L/I原係数の再利用はresolvedとの一致確認を伴わせる。
- [x] 複数Combineが共有する補助の一致、係数0、真のゼロ荷重、未知group、L/I片方欠落、支持違いを検証する。値一致でIDを統合しない。
- [x] source path/基本ID/DefineID/usage/係数適用経路/track/補助ID/Combine/Pickupの対応を付帯データにする。PDFの名目240係数とnative係数が異なる理由を追跡可能にする。
- [x] exporterとは独立にcanonical候補から37状態を列挙するoracleを試験側に作る。native参照を展開した状態集合との一致を検査する。
- [x] D1×1.1についてcanonical/係数付きnativeのq327.448が一致し、解決済みqを基本へ焼き込むと327.45へ変わる反例を固定する。5層の比較を分離し、投影損失を伴う未知入力の拒否を試験する。

**Verification**: 現入力22/19/16/8と37状態、全240名目係数の対応が一致する。不正な上下混合6状態がない。全LF/W混合符号を含む。使用性I245.3、単線IM272.73、最大I443.7、L1531.94の丸め反例を固定する。非標準係数、係数0、非対称支承、signed ratesの完全/近接相殺、N0/M非零で誤変換を検出する。

#### Step 4: 一時候補をFEMPythonで解析し意味を検証

- [x] 指定ソフトの既存 `FrameWebforCS/Headless/bin/Release/net10.0-windows/FrameWebforCS.Headless.exe` に絶対入力パスと新規一時出力先を渡す。`run --input ... --output-dir ... --generate-pdf false --generate-pik true --generate-pickup-displacement-csv true --generate-pickup-reaction-csv true` を使い、ソフトを改修しない。
- [x] 全基本・補助を個別の支持ケースで解析する。同じ用途・実効係数を反映したresolved L/Iを診断用の別荷重にして支持2で解析し、その和と補助応答を比較する。元の基本L/Iへ名目係数を掛けた応答で代用しない。長短期混在は各支持で解いた応答の和で検証し、全荷重を単一ばねで解くoracleを作らない。
- [x] 37状態の独立応答和と、16Combine/8Pickupの各照査成分max/minを比較する。各focusで選んだ候補の全成分を保持し、無関係な成分の極値を一つの物理状態へ継ぎ合わせない。同値極値は許される候補集合で判定する。
- [x] 入力作用と反力の釣合い、支持変位と剛性、風の全長、点偶力、材料参照を照合する。剛域値を検証用コピーで増加させた感度も記録するが、正式採用値は勝手に変更しない。
- [x] nativeをGUIモデル読込み・別名保存経路で往復させる。型付きQ変換後の意味比較と再解析を行い、直接headless検証と区別する。

**Verification**: 有効ケースの変位・反力・断面力が有限、空ケース省略が予測内、全参照が有効。exit0やケース数一致だけで受け入れない。上記WebPier LF/W釣合い値と全状態、GUI既知精度変化が説明できる。版依存の問題は候補段階で解決する。

#### Step 5: CLI/GUIへ接続し成果物を一括公開

- [x] 同じ0620結果からPDF/計算JSON/nativeを作り、出力先registryと `--post-dir` を共通化する。0500/0600は各1回、0620単独で0610を余計に計算しない。
- [x] CLI接続前に、各親内staging/backup、全体journal、overwrite保護、sidecarの最後の配置、例外時復元を単独試験で完成させる。sidecarは実際に公開するbytesのSHAと上記manifestを持ち、全体再検証が通るまでbackupを残す。
- [x] 既存 `CalculationJob.post_dir` と明示的な4 `pdf_paths` を維持し、宣言成果物を両方向へ拡張する。GUI完了時に入力SHA、PDF/結果JSON/native/sidecarの世代・参照・全SHAを照合する。
- [x] 完了後の `check_current_outputs` にpostも含める。片方向だけ欠損・改変・別世代でも成功表示を維持しない。GUIスレッド規約・ログ/エラー処理を保持する。
- [x] READMEに出力名、通常計算での更新、補助ケース表、PDF名目係数との違い、GUI再保存時の扱いを説明する。

**Verification**: 0620単独4件、実装済み方向のall件数、両実装後12件、4 PDF表示、0610/0500/0600との非干渉を確認する。custom output/custom postがproductionへ漏れない。変換失敗、既存post衝突、書込不能、公開途中・最後のsidecarでの故障、復元失敗を注入し、旧版保護または復旧先を検証する。入力変更、sidecar/native改変、片方向の欠落をGUIが検出する。

同じ入力のCLI 0620・CLI all・GUI allが生成する直角nativeのbytesも一致させる。publication IDなど実行ごとの値はsidecar側だけに置き、nativeの再現性を保つ。

#### Step 6: 回帰検証・通常0620生成・納品

- [x] 関連pytestと公開/GUI試験を実施する。共有部に変更するため `.agents/check.ps1` 全体ゲートを1回実行し、既存変更由来の失敗と今回差分を区別する。
- [x] 0610も実装済みなら両方向の通常allを一時出力先で検証し、線路側の骨組/ケース/出力名を壊していないことを確認する。未実装ならその状態を明記する。
- [x] 本番更新前の候補SHA、runner path/hash/engineVersion、native/計算結果/PDF対応表、22/19/16/8、37状態、ゼロ省略、解析検証、GUI往復結果を保存する。
- [x] 通常0620経路から `./post/線路直角方向.json` と付帯JSONを生成し、最終SHAと参照を検証する。入力・元Example・他stage成果物・先行計画を意図せず変更していないことを確認する。

**Verification**: 数値対応、全状態、外部ソフト読込み/解析、通常生成、失敗復元の各条件を満たす。納品ファイルが実在し、生成元と同じ入力世代である。これは入力変換とソフト互換の検証であり、橋脚の構造安全性照査完了とは区別して報告する。

#### 照合精度の基準

- PDFは正規値に同じ表示書式を適用した文字列で照合する。既知差異は一覧で個別管理する。
- 転記値は厳密一致、加算/係数計算は `abs_error <= 1e-10 + 1e-12*max(abs(expected),abs(actual))`。原荷重・名目係数再利用の検証もここで行う。
- 解析釣合い・応答加算の力/モーメントは `1e-6 + 1e-8*scale`（scale＝各寄与絶対値の和）、変位/回転は `1e-10 + 1e-7*abs(expected)`（m/rad）。不一致時は投影、符号、条件数を調べ、理由なく閾値を広げない。
- mark2の2桁化・距離mm化は独立に期待値を作る。元のcanonical荷重との投影差も別に報告し、既知変換のためという理由だけで設計荷重の差を隠さない。現在のq297.68/4.05/8.10は2桁で一致する。
- GUI往復は型付きQの期待値と比較し、bytes一致を要求しない。元nativeをGUI値へ丸めて納品することもしない。

### Risks & Considerations

- **単線相関**：対称な例題は独立包絡でも極値が偶然一致する。診断モデルと37状態の集合一致で確認し、現入力の極値だけを根拠にしない。
- **係数と丸め**：0620の基本Iはultimate係数1で、0610の代表基本と意味が違う。用途別resolvedを使い、0.75や1.23を後から重ねない。
- **資料/ソフト差**：LFの相対符号、風端数、部分載荷、負m2の処理、旧cached結果を分ける。WebPierの確定済み正規モデルをExample値へ戻さない。
- **ケース別の支持条件**：各ケースの支持条件を保持する。線形合成できるのは同じ構造/支持でのL+Iであり、長期Dと短期Lを一つの支持で解かない。
- **複数出力先**：例外時復元と世代検出を実装するが、強制停止に対する全ファイル同時原子性は約束しない。成功判定はジョブ全体のSHA検証による。
- **方向間統合**：線路実装が並行して進行中。追加済み共通コードと0610固定の厳密検証を再利用・分離し、0610/0620双方の登録・異なるIz/Kr/ケース形式を回帰対象にする。調査時のファイル内容を完成版と仮定しない。
- **外部GUI精度**：保存時のSingle化と未知キー欠落は独立の制約。正式nativeと出典sidecarのペアを管理する。
- **既存作業の保護**：多数のstaged変更がある。対象ファイルの最新版を読み、既存計算・入力・試験を巻き戻さない。

### Open Questions

- 出力先は `./post/線路直角方向.json`、通常0620/all自動更新を採用。既存PDFの実名を使う。追加のユーザー回答が必要な入力条件は現時点でない。
- ExampleのLF符号・風の端数/1.08m除外理由は未確定だが、WebPierの正規作用を優先するので実装を止める条件ではない。設計式を変更する必要が判明した場合は変換実装とは切り分け、具体的差異を提示する。
- 外部ソフト直接解析、GUI data-service往復、37状態の独立応答検証は実装後に完了した。実GUIウィンドウ操作とは区別する。詳細は実装・検証記録を参照。
- 完全剛体やGUI内Double保持への変更は今回の対象外。必要になれば外部ソフト/モデルの別変更として判断する。

#### 計画の検証記録

- 3観点の調査：Example対応、WebPier計算経路、FEMPython契約を独立担当で確認。
- 文書構成 `plan-doc` とworkspace実体検証：PASS、警告なし。相対参照先は全件存在。
- [Codex手順分解](../../logs/codex/20261016T104214Z-plan-webpier-transverse-frameweb-input-steps-inline.md)：数値・相関・公開設計を検討。D1投影補助の提案は正規 `_scale` の再丸めなし規約に反するため不採用とし、五層の独立比較と明示反例を追記。
- [初回妥当性レビュー](../../logs/codex/20261016T104804Z-plan-webpier-transverse-frameweb-input-validate.md)：PASS。D1補助不採用の理由も確認済み。レビューCLIは共有/一時ファイル読取りが拒否されたため、検証済み計画全文と関連ソース本文を直接渡したread-onlyレビューであり、レビューCLI自身による追加のファイル調査ではない。
- その後の並行0610実装に対応した統合差分を反映。[更新版の最終レビュー](../../logs/codex/20261016T105224Z-plan-webpier-transverse-frameweb-input-validate-integration.md)：**PASS**。重大な欠落・順序矛盾・追加のユーザー判断が必要な阻害条件なし。方向別検証、schema1/2の移行、全12成果物の世代検証を確認済み。レビューの任意提案にあるstage等の照合は正規結果・付帯JSONを対象とし、nativeに存在しない独自キーは追加しない。
- 保護対象の照合：Example2原本、WebPier入力、既存8 PDF/JSONは開始時SHAを維持。前回線路計画のSHAは並行の実装着手・調査訂正により変わっており、本担当はその変更を保持した。直角の製品実装・本番JSON生成は行っていない。

#### レビュー反映 (2026-10-16, ラウンド1)

- 独立FEMPython受入は、現WebPier候補SHA `b692a9ec5157af8daf0000bd31e70085b2fe697140515e3765322dde1f769dba` についてPASS。22,062数値・3,168選択元の比較、37状態、GUI data-service往復・型付きQ比較、剛域感度、9故障注入を確認。実GUI画面操作とは区別する。
- Medium: 使用性係数0の全零Combine7は指定runnerで利用不能となり、Pickup4参照が失敗する。今回の固定形式で表せない条件を公開前に拒否する契約へ補足し、零load/Defineの省略を辿る検査を追加する。修正後の独立再レビューで完了を確認する。
- High: 使用中Defineの一部候補だけが真の零の場合、実ソフトがexit0でも零候補を包絡から落とす。helper21を零とした診断で、Combine7 node1のdy最大値が0ではなく `-4.37051023794295e-5`（source22）になった。零/非零の混在も公開前拒否へ追加し、全零参照不可と別に回帰・再レビューする。現WebPier候補はこの条件に該当しない。
- CLI allをルート担当が別の一時出力へ実行し、12成果物・共通publication ID・10件の非sidecar SHAを独立照合。直角nativeは上記受入候補とbytes一致。既存8帳票のうち7件はbytes一致、0610 PDFは作成時刻metadataが変わったが全8ページの文字・描画pixelsが一致。証跡: `tmp/webpier-transverse-frameweb-implementation/root-integration/verification.json`。

#### 実装受入・本番生成 (2026-10-16)

- ラウンド1のHigh/Medium所見を回帰試験付きで修正し、独立再レビューPASS。現WebPier候補のbytesは不変。最終受入は36,318数値比較・5,544選択元/全ベクトル比較、37状態、16Combine/8PickupでPASS。
- 関連329試験PASS、対象6moduleカバレッジ95%。非Tk全3144試験を実行し、古い統合入力に対する5拒否を確認した。元fixtureを維持して統合試験条件を明示し、修正対象 `test_report_cli.py` の11試験はすべてPASS。独立レビューもPASS。
- 通常 `--stage 0620 --overwrite` から指定postにnative・付帯JSONを生成。native SHA `b692a9ec5157af8daf0000bd31e70085b2fe697140515e3765322dde1f769dba` は受入候補と完全一致。0620 PDF/計算JSON・入力・Example原本は開始時bytesと同じ。他stage帳票と線路postは直前SHAを維持。
- 共有全体ゲートは3379 PASS・5 FAIL・1 SKIPで完了。5件は収集時の旧統合試験本体で、修正後11件の再実行でPASS。Tk環境由来の1件も同一nodeの新規プロセス実行でPASS。全3385 nodeを照合した最終結果に未確認・未解決失敗なし。元の全体コマンドをPASSに書き換えず、全実行の根拠を `tmp/webpier-transverse-frameweb-implementation/final-suite-results.json` に保存した。
