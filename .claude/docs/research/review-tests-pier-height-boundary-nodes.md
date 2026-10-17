# Test Review: pier-height-boundary-nodes

## Summary

承認済み固定コピーのレビューでは、製品動作に関するCritical/High/Mediumの指摘はありません。Lowの回帰試験改善候補が1件あります。live作業フォルダは別セッションによるB9競合が続いているため、本結果は固定コピーに限ります。

## Review Scope

- 対象: `C:/Users/sasai/AppData/Local/Temp/codex-pier-height-verification-20261015` の承認済みsource/tests/fixtures。`review-scope.json`、`review-approved.patch`、承認計画、leadの比較証拠を確認。
- Coverage: **not measured**。`gather_diff`のcoverageはnullであり、測定率を推定していません。ruffも未実行と区別しています。
- 共通rules/STATE/DESIGN/PROGRESSの不在はユーザー承認済み。context-loader結果は `missing: [".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]`, `unreadable: []`, `warnings: ["DESIGN.md is still the uninitialised /init template; run /init to populate it"]`, `design.placeholder: true`, `progress.entries: 0`。本担当はteam-executeの独立Test reviewerとして直接レビューしました。

## Findings

### [Low] 表内の途中分割と行の完全性を永続回帰試験へ追加できる

- File: `./tests/test_longitudinal_report.py:365`、`:383`。両方向を同一パラメータ試験で扱います。
- 現状: `MODEL_TABLE_BOTTOM=300` は実際の継続頁・後続荷重頁順序・全footer連番/SHAを検査します。一方、表の開始位置y=101では10行まで収まり、サンプルの8節点表と7部材表はそれぞれ1頁に収まります。`draw_model_conditions.table`の行途中chunk分割を通りません。続頁の全節点/部材行が各1回出ることも、現試験の最後は見出しだけを確認しています。通常高さの別試験では全行の値を確認済みです。
- 再現条件: `parapet_asymmetric`、b/w両方向、`MODEL_TABLE_BOTTOM=200` にすると節点表・部材表とも本当に途中で分割されます。chunk境界で次行を飛ばすような将来の回帰は、現行300試験だけでは検出しにくい状態です。
- 推奨: 200のケースを追加し、`実節点座標（続き）`/`実部材接続（続き）`を確認して、独立fixtureの全節点行/接続行が継続頁全体に順序通り各1回存在することを検査する。
- 現在の実装は独立probeで200でも両方向とも全8節点/7部材が各1回、footer連番も正常でした。製品不具合や完了阻害事項ではありません。

## Verified Scope

- `expectations.json`は10ケース×2方向の固定辞書です。元の4点とsource行、全roles/node_ids、弾性/剛域の接続と参照、支持、load_anchorsの全フィールドを検査します。新fixture生成時に製品builderを呼ぶ経路はありません。サンプル数値は既存独立oracleと完全一致し、追加出典注記だけが差分です。
- builderの72組合せ（方向を含む）、合流完全優先順の全上端一致例、decimal中心、1e-12/1e-100の実偏心、符号反転、正の極小高さの保持/表現不能時拒否を確認。独立追加probeではH2/H3/H4=0/.5、基礎高0/2、重心0/中間/天端、H1なし/中心/左右偏心、b/wの384組合せについて、全nodes/roles/source_rows/legacy alias/members/support/load_anchorsを完全比較してPASSしました。
- H1自重の5.29 kNと引継ぎSingle 5.289999961853027を区別する試験、元分布荷重の力・底面回り一次モーメント保存を確認。旧Excel全セル/転記/係数のassertは維持されています。歴史入力adapterは別並行変更の式復元に対する準備であり、固定期待値を書き換えていません。現在parserを通る独立サンプル/CLI試験も別途あります。
- 同一上流入力契約の変更前後比較 `tmp/pier-height-boundary-nodes/comparison-final-after.json` は既定/パラペット/非対称基礎で0500/0600結果完全一致、0610/0620のframeと承認済み0610注記以外を完全一致としています。荷重頁本文のtext/vector/pixel一致も確認対象です。
- CLIは両サンプル＋既定で各stage/allの実PDF生成、結果完全一致・共通入力SHA・原入力非破壊を検査。H1幅0/丸めI=0では0610/allおよび0620単独がrender前に失敗し、既存8成果物を保持する試験があります。
- 独立追加CLI probeではB3=.6/W3=.01として0610 H1 I=.00018は有効、0620だけI=0となる入力を使いました。allは0620の入力エラーで終了2、renderer未呼出、既存8ファイルのbytes完全保持でした。
- 継続頁の実PDF試験は両方向でページ増加・後続荷重頁本文順序・全footer連番とSHAを検査します。追加200 probeでは表内途中分割の10モデル頁を実生成し、全8節点/7部材行が各1回かつ全footer連番を確認しました。

## Test Execution Results

- 共通full gate（reports担当実行）: **2065 passed, 0 skipped**, 251.88s, overall=pass, exit=0。証拠: `tmp/pier-height-boundary-nodes/reports-gate.json`。
- lead独立full gate: **2064 passed, 1 skipped**, 173.45s, overall=pass, exit=0。Tk表示初期化の既存GUI試験1件が環境都合でskip。leadから同関数全4パラメータの隔離再実行 **4 passed**, 8.27s の報告を受領。証拠: `tmp/pier-height-boundary-nodes/root-final-gate.raw.json`。
- 本reviewの追加read-only probe: topology384条件PASS、0620専用エラーall公開前拒否1条件PASS、表内分割PDF2方向PASS。いずれも終了0、製品source/tests/fixtureは変更していません。既存full suiteの重複実行はしていません。
- Coverage: not measured。

## Limitations and Pending Integration

- 本レビューは構造応答ソルバの妥当性評価を含みません。今回の成果は荷重を変えない接続付き計算入力モデルです。
- live B9処理および後続で競合したlive試験への承認済み内容の反映、README先行段落のGUI/B9説明修正、本番4成果物の公開はleadが別途追跡中です。本レビューのPASSをliveの反映完了と扱わないでください。
- 原本PDF/xlsを新しい計算oracleとして再抽出していません。既存独立oracleと固定された形状契約を根拠としています。
