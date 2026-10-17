# Security / Data-integrity Review: pier-height-boundary-nodes

## Result

承認済み固定ソースの機能コードに、新規の Critical / High / Medium / Low のセキュリティ・データ整合性欠陥は見つかりませんでした。追跡していたB9文書矛盾は、修正文書2件のlive適用を独立確認して解消済みです。liveの両parserも承認済み固定コピーとSHA一致、明示B9優先の実行分岐を確認しました。本番成果物の更新・最終gate完了は主担当の別検証対象です。

## Scope and Method

- 対象は `C:/Users/sasai/AppData/Local/Temp/codex-pier-height-verification-20261015` の固定ソース、同所の `review-scope.json`、`review-approved.patch`、承認済み計画です。live K の競合中parserは対象外です。
- `frame_model.py`、両方向計算器の差分、両parserのB9分岐、図・モデル表描画コード、関連するモデル・parser・CLIテストを読みました。変更されていない `cli.py` の計算→描画→一時保存→公開の境界も確認しました。
- 共通gateの保存JSONを確認しました。`overall=pass`、`tools.pytest.status=pass`、`exit_code=0`、2065 passed / 251.88s。レビュー担当は全体テストを再実行していません。主担当の別gate結果は別証跡として扱います。
- `tmp/pier-height-boundary-nodes/comparison-final-after.json` の既定・パラペット・非対称基礎の両方向の比較結果を読みました。これは主担当の生成した証跡であり、レビュー担当の独立再実行ではありません。
- 外部通信、秘密情報、動的コード実行、依存追加の有無も確認しました。新規3モジュールにネットワーク・shell・ファイル削除・書込の処理はありません。

## Findings

新規の機能コード上の指摘: None。

確認できた保護・整合性は次のとおりです。

- `pier_design/frame_model.py:31`、`:71`、`:91`、`:186` は有限値、正の丸め後断面、座標精度で消える正の高さ、重複/ゼロ長部材、不正な参照、支持までの連結を公開前に検査します。十進中心と実際の極小偏心は別に扱います。
- `pier_design/frame_model.py:106`、`:171` は入力と旧frameをdeep copyし、旧4点のid/x/y/source_rowと合流先を保持します。完全優先順による合流後にも全roleと元行が残り、新しい境界に架空の元行を追加しません。
- `pier_design/frame_model.py:173` の固定load_anchorsは既存柱頭・基礎重心・分布荷重部材へ接続し、H1上端へ集約荷重を移しません。`automatic_self_weight=false`で、builderは数値荷重を生成・加算しません。両計算器の変更もframe生成と承認済み注記に限定されています。
- `pier_design/inputs.py:91`、`reaction_inputs.py:191` は明示B9（0を含む）を優先し、欠落/nullの場合だけB7へfallbackします。不正な明示値を黙ってfallbackしないテストもあります。GUIの自動式はこの変更に含まれません。
- `pier_design/cli.py:94` は読込済み入力byte列からSHAを一度求め、同じ結果系列へ付けます。`:110` より前に選択stageの全計算が完了するため、H1検査エラーで描画・公開は始まりません。新規CLIテストはrendererを失敗検知用に差し替え、エラー戻り値、既存全成果物のbyte不変、入力byte不変を検証します。
- 新規描画は固定名・数値・モデル内参照をCanvasへ描くだけで、入力由来のコード/HTML/SQLを評価しません。ファイル公開・復旧・symlink拒否は既存CLIを使い、今回そこに変更はありません。

## Known Integration Issues and Resolution

### [Medium, known, resolved] READMEのB9説明が承認済みbackendの動作と逆

- **Location:** `./README.md:120`、`:156`、`:313`（固定レビューコピー）。最初の箇所は自動表示一覧後の包括的な説明です。live版は別編集により行位置がずれる可能性があります。
- **Reproduction:** `tests/fixtures/pier_models/parapet-asymmetric.json` はB7=0.35、B9=0.2です。固定コピーの両parserはB9=0.2を保持しますが、READMEは「計算時は参照元から再計算」「B7＋B8＋B7」「GUI・CLIともB7」と説明します。CLIを使う利用者が、明示入力が採用されないと誤認します。
- **Fix:** 自動表示段落を「GUIでは上記の欄を自動表示し、更新・保存します。計算時のB9は後述の明示入力優先に従います。」とし、他の数式項目の再計算説明は維持してください。0500段落とサンプル段落には「JSONにB9が明示されていれば、その値（0を含む）を使用し、欠落/nullの場合だけB7を用います。基礎幅はB7＋B8＋採用したB9です。GUIのB9自動計算は従来どおりです。」と記載してください。既存の15有効桁表示の説明は維持してください。
- **Status:** 主担当へ通知後、修正案を確認し、下記のlive適用まで確認して解消しました。

#### 修正提案の確認

`tmp/pier-height-boundary-nodes/approved-docs/./README.md` と同 `tests/fixtures/pier_models/README.md` を確認しました。3箇所とも明示B9（0を含む）を優先し、欠落/nullのみB7を採用する説明へ揃い、指摘解決案として妥当です。GUIで開いて保存すると例のB9=.2がB7=.35へ更新されること、CLIへ原JSONを直接渡す経路、重心高Single `1.1779999732971191 m`、typed adapterは過去の元数式snapshot照合に限ることも明示されています。15有効桁表示の説明は保持されています。

#### Live適用の確認

停止確認後の主担当merge連絡を受け、liveの2READMEと上記確認済み提案のSHA256一致を独立確認しました。メインREADMEは `C556C03DCEBF0CD07BC16AFC274501F0AC7D8C9503F29F4EA67C06D31CFDA55B`、fixture READMEは `E1FCF66337C7D375CC9DF2118E767A512FE354504F7AE1104CD3077F3138F799` です。**提案確認済・live適用済み、文書指摘解消済み**へ更新します。この再確認では製品コード変更・テスト実行はしていません。

### Live B9所有権の競合（停止確認・merge後の対象分岐確認済み）

主担当から停止確認後のmerge完了の連絡を受けました。レビュー担当もlive `inputs.py:92` の `raw_b9 is None` の場合だけfallbackする分岐と、`reaction_inputs.py:192` の欠落/nullの場合だけformulaを使う分岐を読みました。両ファイルのSHA256は承認済みCコピーと一致しています（inputs: `E3AC0F7A51B86016451A2F3A38B3B968A0A9B97BB74E5D90BB3D7E233BB8F8D6`、reaction_inputs: `0F6C9C1EBD098E7C6BDFED71B2A04A8C286E54EC03CFC1BEE98CABB10B240A0E`）。本番更新・最終gate完了はこの分岐確認と別に主担当が検証中です。

## Limits

構造解析ソルバ、設計基準への適合、未変更のGUI・計算式全体の再設計、依存パッケージ全体の脆弱性監査は対象外です。新規依存はありません。Ruff未利用・coverage未計測と、テストの成功を区別します。製品ソース、テスト、入力、成果物は編集していません。
