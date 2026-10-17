# P7 線路方向 FrameWeb 出力経路の調査

調査日: 2026-10-16。実装計画のための読取専用調査。製品コード、入力、既存出力は変更していない。本メモのみ新規作成した。対象は現在の `P7橋脚/output/0610_線路方向荷重.pdf` と同時生成 JSON。通常の `0610` / `all` 計算でも `P7橋脚/post/frameWebForJS.json` を自動更新する方針は、親エージェント経由のユーザー回答で確定した。

## 結論

PDF は数値・載荷位置・ケースの検証資料とし、実行時の変換元は PDF と同じ正規 `schema_version=2, stage=0610` の計算結果とする。`calculate_longitudinal` が返す `frame`、`basic_cases`、`combinations[].resolved_components`、`variants`、`define_cases`、`extraction_cases` は必要な構造を既に持つ。旧セル表や `legacy_audit` へ戻る必要はない。

最も重要な点は、20 基本荷重へ名目 320 係数をそのまま掛ける方式では現在の P7 の組合せを再現できないことである。衝撃は用途別橋脚低減・係数適用・0.1 kN 丸め済み、列車モーメントも採用係数適用後に支点ごとに丸めている。L/I は正規結果の解決済み作用を補助荷重へ展開し、解析用 combine では係数 1 で参照する必要がある。原本の 20 ケースと名目表は意味の追跡用に保持する。

通常計算の接続点は `pier_design/cli.py:104` の正規 0610 結果の直後である。PDF renderer と並列の純粋変換器を追加し、出力公開は既存の復元保証を post 側まで拡張する。GUI は同じ CLI を呼ぶため別の計算器を作らない。

## 現物の世代と整合

| ファイル | SHA256 |
| --- | --- |
| P7橋脚/pre/input.json | `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b` |
| output/0500_直接基礎.json | `2fd013e9b75180b534e9dc2f64bcecd29c3d3b11c23fe6cca242bb9672d39745` |
| output/0600_上部工反力.json | `ba2c335818a03cee1c8bd86692a980ec32871d3a2d56621a7e683892a10e12b4` |
| output/0610_線路方向荷重.pdf | `85334ee02cf775b8914f9cc73c6db107d522bb1625ed0fe5b7f6e66ad438383f` |
| output/0610_線路方向荷重.json | `ad98ba14bb10a9af67b0e8fcc3e4714a597beef7230ba567512713ffe89d8e66` |

- 0500/0600/0610 の `provenance.input_sha256` は現入力の SHA と一致。
- PDF は 8 頁。各頁の入力 SHA 表示は `82d5a2769dfb`。既存計画 `.agents/docs/plans/longitudinal-example2-parity.md:26–36` の最新 8 頁公開版と PDF/JSON SHA が一致する。旧 11 頁の履歴を現物と取り違えない。
- 現入力・現コードから 0500/0600/0610 をメモリ上だけで再計算し、CLI 同等の `json.dumps(ensure_ascii=False, indent=2, allow_nan=False) + newline` を Windows CRLF に合わせて比較した。3 JSON とも保存 bytes に完全一致した。出力の再生成・書込はしていない。
- 初期の Python オブジェクト比較には tuple/list 差があったが、JSON 化後は全て一致した。これをコード世代差・数値差と分類しない。
- 調査時 `P7橋脚/post` は空で、既存 FrameWeb 出力はない。

## 正規パイプラインと参照位置

| 対象 | 根拠 | 輸出に使う契約 |
| --- | --- | --- |
| 単一入力読込と SHA | cli.py:89–103 | input bytes を 1 回読み、共通 0500/0600 の provenance に同一 SHA |
| 0610 生成 | cli.py:104–109、longitudinal_calculator.py:66–103 | 0500/0600 と部位別材料から正規 schema 2 を生成 |
| 物理作用 | longitudinal_actions.py:215–256 | D1/D2/水位、S2/S10/S30、無係数 L、用途別 I、0600 採用 H |
| 用途別組合せ | longitudinal_actions.py:172–212 | 解決済み `loads` と残係数 1/0。水平のみ反転した `variants` |
| 名目表と抽出 | longitudinal_example2_cases.py:53–102、117–165 | 20 基本、20 Define、16 組合せ、8 抽出 |
| 骨組 | frame_model.py:91–184 | 実節点・実部材・意味付き node_ids・load_anchors |
| 部位材料 | longitudinal_design_conditions.py:94–136 | H2/H3＝梁、H4＝柱、H1＝柱継承、基礎／H1水平腕＝剛域 |
| 方向別ばね | foundation_springs.py:27–58 | 0500 正規 long_term/short_term、Kr_longitudinal、Double のまま |
| PDF | README.md:291–293 | 正規結果のみを描画。元入力/PDF/旧 layout を実行時に読み直さない |

`longitudinal_calculator.py:316–327` の等価柱断面、`340–365` の D1 計算は既存の採用条件である。輸出で断面形状や梁自重を別計算して上書きしない。

## 現在の骨組・材料・支持

PDF p1–2 と正規 JSON の対応。長さ m、A m²、I m⁴、E kN/m²。

| P7 実節点 ID | 役割 | x | y | Example FrameWeb 節点 |
| --- | --- | ---: | ---: | ---: |
| 1 | cap_top | 0 | 10.3 | 1 |
| 5 | h2_h3 | 0 | 8.3 | 2 |
| 6 | h3_h4 | 0 | 7.6000000000000005 | 3 |
| 2 | footing_top | 0 | 2.7 | 4 |
| 3 | footing_centroid | 0 | 1.350000023841858 | 5 |
| 4 | footing_bottom / support | 0 | 0 | 6 |

P7 ID は意味付きの安定 ID で上から連番ではない。Example の ID を直接代入しない。最小の変換は P7 の ID を保持して参照関係をそのまま写すこと。上から連番化する場合は単一の明示マップを node/member/fix/load/dimension の全参照で共用する。近接座標や PDF 表示丸めによる節点統合を追加しない。

部材 1=`1→5` H2、2=`5→6` H3、3=`6→2` H4、4=`2→3` 基礎天端→重心、5=`3→4` 重心→底面。1–3 は弾性、4–5 は剛域。現在の `A=12.15, I=7.38113, width=4.5, depth=2.7`、梁・柱・フーチングの `fck=27, E=26,500,000`。Example FrameWeb も同値だが、P7 は部位別材料を保持するため将来の梁／柱強度差に対応する必要がある。剛域の `A=I=1000` は Example FrameWeb の表現であり、P7 frame は厳密な剛域フラグしか持たない。近似剛性値の採用は外部ソルバー調査の契約と合わせる。

| 支持ケース | Kv | Ks | Kr（線路） |
| --- | ---: | ---: | ---: |
| 1 長期 | 12,788,244 | 4,262,769 | 52,218,663 |
| 2 短期 | 25,576,488 | 8,525,475 | 104,437,326 |

FrameWeb の平面 XY では支持節点の `tx=Ks, ty=Kv, rz=Kr`。正規 `spring_provenance.support_node_id` を使う。旧 macro の Single 化 Kr や直角方向 Kr を使わない。

H1>0、H2/H3/H4=0、重心が基礎端部と同座標、偏心 H1 水平腕は既存 frame が処理する。`frame_model.py:138–169` の aliases/member omission と `188–221` の接続検証を輸出でも尊重する。自重載荷対象は `load_anchors.column_line_load.member_ids`、桁受け自重は既に等価集中荷重に含まれ `automatic_self_weight=False` である。

## 現在の採用荷重

数値は正規 JSON の精度を保持する。以下の表は読みやすさのため PDF 表示桁を併記するが、実装で全値を新たに 2 桁丸めしない。

| 基本 | 載荷アンカー | 採用値 | PDF |
| --- | --- | --- | --- |
| 1 D1 | cap_top | N=8299.52、M=-610 | p3 |
| 1 D1 | footing_centroid | N=4167.4501953125、M=0 | p3 |
| 1 D1 | column_line_load の全部材 | q=297.68 kN/m、長さ合計7.6 m | p3、p1 |
| 2 D2 | cap_top | N=780、M=6.5 | p3 |
| 2 D2 | footing_centroid | N=1830.5999755859375、M=0 | p3 |
| 3 WP1 | footing_centroid | N=-2381.39990234375、M=-0 | p3 |
| 4 WP2 | footing_centroid | N=-1701、M=-0 | p3 |
| 5 WP3 | footing_centroid | N=-0、M=-0（零荷重でもケースを保持） | p3 |
| 6 S2 | cap_top | N=710、M=19.25 | p4 |
| 7 S10 | cap_top | N=1140、M=29.5 | p4 |
| 8 S30 | cap_top | N=1270、M=37.25 | p4 |
| 9 L1 無係数 | cap_top | N=567.3857116699219、M=110.52 | p4 |
| 10 L2 無係数 | cap_top | N=1134.7714233398438、M=221.04 | p4 |
| 11 I1 代表ultimate | cap_top | N=211.20000457763672、M=80.66 | p5 |
| 12 I2 代表ultimate | cap_top | N=404.3000030517578、M=158.70999999999998 | p5 |

P7 の N は下向き正、M は鉛直力×アームの独自符号である。Sample から確認した FrameWeb `load_node` の実キーは `ty=-N, rz=-M`（物理成分では Fy/Mz）。水平 H は cap_top の `tx=H`（Fx）。実装前にソルバー片持梁検算でも符号を確認する。

D1 上部の `N=9103.26−297.68×2.7=8299.52` は梁等の集中荷重から既に柱等価分布の重複分を控除した値（`longitudinal_actions.py:272–281`、PDF p3）。これをさらに分解・再控除したり、弾性部材に自動自重を加えたりしない。PDF の参考 ω2/ω3、浮力 ω は実際の集中 N に加えて載荷する値ではない。

Example FrameWeb `load.1.load_node[0].ty=-8299.53` に対し P7 の正は `-8299.52`。0.01 kN 差を原本テンプレート値へ合わせない。Example のD1分布は `load_member.direction="x", mark=2, m1="1", m2="3", P1=P2=297.68` として3連続下向き部材の局所xで表現されている。P7の非連続ID・H1分岐へ適応するには既存アンカーの各memberへ個別載荷する方が参照を明確にできる。

| 基本 | H 合計（kN、JSON精度） | 正規ばね | Example JSON のばね |
| --- | ---: | ---: | ---: |
| 13 使用性0.8LR | 240 | 1 | 1 |
| 14 使用性1.0LR | 300 | 1 | 2 |
| 15 安全性1.0LR+ρB | 473.42999267578125 | 2 | 2 |
| 16 安全性1.1LR+ρB | 513.8899993896484 | 2 | 2 |
| 17 安全性1.0LR+ρmaxB | 495.00999450683594 | 2 | 2 |
| 18 安全性1.0LR | 300 | 1 | 2 |
| 19 復旧性1.0LR+B（側別） | 463.7099914550781 | 2 | 2 |
| 20 復旧性1.0LR | 300 | 1 | 2 |

正規ばねは PDF p6、`longitudinal_example2_cases.py:21–41` に基づく。Sample の14/18/20と異なるため sample丸写しをしない。基本1–8は1、9–12は2。水平15–20の元データ経路は `longitudinal_actions.py:22–31` に明示され、15–17は旧配列の4–6番、18/20は雪専用配列、19は旧配列7番である。

## L/I の解析用補助ケース

`_support_loads` は支点別 `M=ROUND(N×arm,2)` を求めてから合算する（longitudinal_actions.py:101–105）。`_impact` は用途別上流 cp、採用 L、0.1 kN 丸め、Single 転記を順に適用する（122–143）。名目表の0.75やρを解決済みIへ再乗算しない。

| 用途・線数 | L N / M | I N / M | 参照する組合せ |
| --- | --- | --- | --- |
| service single | 567.3857116699219 / 110.52 | 128.50000381469727 / 49.04 | 7、15、16 |
| service double | 1134.7714233398438 / 221.04 | 245.29999542236328 / 96.17 | 5 |
| ultimate double | 1395.7688507080077 / 271.87 | 404.3000030517578 / 158.70999999999998 | L:2、3、8、11、12、I:3、8、12 |
| maximum double | 1531.941421508789 / 298.4 | 443.6999969482422 / 174.2 | 1、10 |

最大単線IはPDF p5の補足に存在するが、現16組合せに含まれない。I ultimate singleも原基本11として保持するが、現16組合せの採用解決値には現れない。

具体的な誤りの例:

- 組合せ1のI2: `404.3000030517578×1.35=545.805004119873` は誤り。採用は `443.6999969482422`。
- 組合せ5のI2: 代表I2×0.75の `303.22500228881836` は誤り。採用は `245.29999542236328`。
- 組合せ1のL2 M: `221.04×1.35=298.404` に対し正規は `298.40`。
- 組合せ3のL2 M: `221.04×1.23=271.8792` に対し正規は `271.87`。

輸出方針案:

1. 原基本1–20/Define1–20を保持する。1–12は正のみ、13–20は該当する水平力だけ±とする。
2. 採用L/Iは `resolved_components` を正とし、family/track/usage/effective_factorによる意味付きキーを作る。21以降へ安定した順で補助load/defineを割り当て、解析combineの該当列を係数1へ置換する。数値が偶然同じだけでは異なる意味のvariantを統合しない。補助と原基本の二重参照を作らない。
3. 現在必要な意味付き集合は L の service single/double、ultimate double、maximum doubleと、Iの同4用途である。原代表I2をultimate doubleとして再利用するか補助へ統一するかは実装契約で固定する。単純に「必ず23ケース」と決めるとLの丸め差を落とす。
4. `nominal_factor=0` / `resolution.included=False` は combineから除く。物理値が偶然0でも included=Trueの意味付き荷重は保持できるようにし、0を割る正規化を禁止する。ρ=0、service=0、雪0でも参照破損を起こさない。
5. D1/D2/水位/雪/Hの解決は物理成分だけの線形係数なので原基本＋名目係数を使える。メタデータやアームまで係数倍しない（longitudinal_actions.py:146–160）。
6. 保存する名目表と解析用combineの違いを追跡表に明記する。任意の再丸めでPDF表示値に寄せず、正規JSONの値を保持してPDFの表示桁で照合する。

16組合せの全variant数は28。水平を含む1–6、8–13は±2、7/14/15/16は1。抽出は `[1..4], [5], [6], [7], [8,9], [10..13], [14], [15,16]`（PDF p8、longitudinal_example2_cases.py:92–102）。

## 通常 CLI / GUI 統合

現状 `cli.py:67–77` は0500/0600/0610/0620/all、`--output-dir`、`--overwrite` を持ち、0610は依存0500/0600を各1回計算する。`cli.py:125–137` はoutput内の単一stagingでPDF/JSONを生成・一括公開する。`_publish_outputs` は全旧成果物を退避してから公開し、途中失敗時に旧成果物を復元する（33–64）。

通常出力へ組み込む場合の推奨:

- `0610` はPDF・正規JSON・FrameWeb JSON、`all` は従来8ファイル＋FrameWebを更新する。0500/0600/0620単独はpostに触れない。
- `--post-dir` を追加。省略時、既定production outputなら `PROJECT_DIR/post`、カスタム `--output-dir` なら `output_dir/post` を提案する。明示post-dirを最優先する。この規則なら一時検証が正式P7/postを誤更新しない。`--input` の場所やcwdから出力先を推測しない。
- 0610結果からFrameWebを作成して全検証が成功してから描画・公開へ進む。計算済み結果をもう一度preから再計算しない。
- 既存単一stagingを異なるvolumeのpostに流用すると、`os.replace` のvolume境界で失敗する。各destination親の直下へstaging/backupを用意し、共通journalで全退避・全公開・逆順復元する。全ファイルの同時renameという意味のatomicityではなく、現CLI相当の完了／復元保証である。
- 失敗時は既存9成果物を復元し、その実行で新規作成したファイルだけ除く。復元失敗時は全関係backupを残して場所を通知する。同名ディレクトリ、リンク、入力同一パス、出力同士の衝突は公開前に拒否する。
- 本体FrameWebが受け入れるトップレベル項目は外部ソルバー調査に従う。未確認のprovenanceを勝手にnative JSONへ追加しない。追跡情報をsidecarにするならsidecarも同じ公開・復元単位へ入れる。

GUIは `editor_calculation.py:164–180` がsubprocessで `run_design.py --stage all --overwrite` を実行、`118–148` の `validate_outputs` が従来8成果物の存在・JSON入力SHA・PDF可読性・改変を検査する。次の更新が必要:

- `CalculationJob`（55–60）にpost_dirまたは具体的model_pathを保持する。Controllerへcustom outputを渡した試験は隔離postへ従う。CLIへ決定済みpost-dirを明示する。
- `validate_outputs` の集合へFrameWebを追加し、snapshot/後続改変監視（`check_current_outputs`）にも含める。JSONすべてへ `_validate_provenance` を適用する現実装はFrameWebにはそのまま使えない。正規0610のSHA検証と、純粋converterによるFrameWeb再構築同値検証、または検証済みsidecarのモデルhashを用いる契約が必要。
- `return paths[::2]`（149）は現在のPDF/JSON交互列に依存する。model追加後は明示的なPDFパス集合を返し、モデルをPDFプレビューへ混ぜない。
- `editor_gui.py:668–732` の保存→計算→検証→4PDF表示の流れを保つ。成功はFrameWeb検証も終えてから出す。完了文言に解析入力の更新を短く追加できるが、PDF枚数は4のまま。

## 実装対象候補と意味のある検証

新規: `pier_design/frameweb_export.py`（正規0610→nativeモデルの純粋変換と入力契約検証）、必要なら `pier_design/artifact_publication.py`（複数出力親のstaging/復元）、追跡表の型。変更: `cli.py`, `editor_calculation.py`, 必要最小限の `editor_gui.py`, `README.md`。既存計算器、材料・ばね計算、0620正規化、旧oracleは変更不要。

新規試験は `test_frameweb_export.py` とCLI/controller統合試験に分ける。単に実装のJSONをコピーした期待値にしない。

1. PDF p1–6から独立転記した6節点・5部材・2ばね・全基本作用の期待値を照合。sampleとはID差、ばね14/18/20、用途別I、正規精度を区別する。
2. 各荷重のΣFx/ΣFy/基礎底面まわりΣMzを独立計算。native `load_node.rz=-M`、下向き`load_node.ty=-N`、Hの高さ10.3m、D1 qの7.6m区間、WP符号を検証。全体釣合いだけでなく基礎／柱の載荷位置と節点参照も照合する。
3. 16組合せ28variantを展開して、正規 `resolved_components/variants` とΣFx/ΣFy/M、支持ケース別の作用集合が一致することを検証。L/I二重係数、水平±で鉛直まで反転、短期/長期の取り違えを検出する。
4. FrameWeb/FEMPythonの実計算で、単純片持梁の符号と変位・反力、およびばねケースごとに解いた応答の重ね合わせを確認する。全組合せ荷重を一つのばねで解く代替を正解にしない。
5. 元値が同じでも意味の異なるvariant、ρ=0・service=0、任意のρ、single/doubleの分担率差、強度差、H1偏心、H2/H3=0、節点ID変更、重心端部を対象にする。既存frame fixtureを再利用し、番号固定・原本固定を検出する。
6. CLIの0610/all自動生成、0500/0600/0620非更新、production/custom post-dir、既存ファイル・ディレクトリ・symlink・入力衝突、post生成失敗、最後のpublish失敗、rollback失敗、既存9ファイルの保護を検証する。
7. ControllerはFrameWeb欠落・破損・過去世代・変更／削除時にsuccessにしない。新ファイルをPDFとして扱わず4PDFだけ返す。入力読込1回・依存計算各1回を保持する。

既存の意味ある回帰対象: `tests/test_frame_model.py:88–216`（独立形状・境界・分布荷重）、`test_longitudinal_canonical_calculator.py:177–213,344–454,533–585`（正規ばね/材料、L/I、符号、SHA）、`test_longitudinal_canonical_cli.py:65–183`（単独/all同値、依存1回、失敗復元）、`test_editor_calculation.py:243–420`（欠落、破損、入力変化、再読込）。調査では新たな製品テストを追加・実行していない。

## 残る外部契約

このメモはP7経路を主担当として調査した。FEMPythonが読む2D寸法指定、剛域のA/I近似、load_memberのグローバル方向指定、combineの係数とDefineの正負展開、pickupの包絡処理、JSONに許される補助metadataは外部ソフト調査担当の根拠と合流して決定する。内部の解析結果を本タスクで部材断面照査まで拡張しない。
