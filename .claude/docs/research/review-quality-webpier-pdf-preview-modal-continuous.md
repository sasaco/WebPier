# Quality Review: WebPier PDF Preview Modal and Automatic Advance

## Summary

PASS。承認計画、対象差分と実ソースを独立に照合し、今回の変更に起因する High / Medium / Low の指摘はありません。製品コードは変更していません。

## Review Scope

- `src/pdf_preview.py` — ページ／文書境界、縦入力の休止判定、長い同期描画後の残余イベント、after と画像の解放。
- `src/pdf_preview_dialog.py` — Path による一覧、手動／自動選択、モーダル、部分構築失敗、grab・focus・親破棄。
- `src/editor_gui.py` — singleton、計算成功後の表示、freshness の再入抑止、保存失敗・別名保存・再計算・終了との接続。
- `./tests/test_pdf_preview.py`、`./tests/test_pdf_preview_dialog.py`、`./tests/test_editor_gui.py` — 実イベント経路、境界条件、既存 assertion の適応と Guardrail 証拠。
- `./README.md` — PDF 操作説明の変更部分。
- 基準: `.agents/docs/plans/webpier-pdf-preview-modal-continuous.md`、`.agents/logs/agent-teams/team-execute-webpier-pdf-preview-modal-continuous/review-scope.json`、`.agents/logs/review-diff-webpier-pdf-preview-modal-continuous-owned.patch`。
- 並行作業の骨組み外形・帳票・`.coverage` と README の「骨組み図の橋脚外形」追記は対象外。共通 rules / STATE / DESIGN / PROGRESS の未配置はユーザー承認済みの扱いを引き継ぎました。

## Findings

None。High: 0、Medium: 0、Low: 0。

## Verification and Evidence

- `pdf_preview.py:401` では入力時刻を無視する入力にも記録し、画像なし・描画待ち・同期描画中は遷移しません。下端判定はスクロール前であり、初めて末尾を表示する操作と次へ進む操作を分離しています。`pdf_preview.py:318` の描画完了後の 250ms 下限も確認し、同期処理中に溜まった古いホイールで短い後続文書を送る危険に対応していることを確認しました。
- `pdf_preview_dialog.py:208` の共通選択処理と `:226` の文書末尾 callback は Path を同期し、callback 自身では PDF を再読込しません。`editor_gui.py:514` からの freshness 通知は状態・ラベルだけを更新し、一覧再走査・選択・show_pdf へ再入しません。
- `pdf_preview_dialog.py:269` と `editor_gui.py:486` の cleanup を照合しました。構築・transient・grab 失敗時、通常 close、親破棄、再計算開始、画面再構築、成功した別名保存で参照・画像・予約・grab を解放する流れです。保存失敗・キャンセルではモーダルを保持します。
- Guardrail の四つの製品側 `except tk.TclError: pass` は限定された破棄処理で、通常処理を代用する stub ではありません。新規 fixture の pass は既に破棄された Tk root の teardown、skip は Tk 初期化失敗だけです。削除された 18 assertions はコンボボックス／埋込みレイアウト依存の置換であり、モーダル表示・Path 選択・ラベル・計算ガード・外部変更検知を検証する assertions が残り、mapped な寸法検証も追加されています。
- 破棄中に別の Destroy binding を解除すると Tcl の古い callback が実行される可能性を疑い、限定した実 Tk probe を実施しました。空の mapped ダイアログに、先行してダイアログを閉じる root Destroy binding を設けた場合／設けない場合とも、Tcl `bgerror` は 0 件でした。実 InputEditor でも、直接 `root.destroy()` と通常 `app.close()` のいずれも破棄後の Tcl background error は 0 件でした。ダイアログを開かない比較条件でも、初期入力画面から計算画面へ切り替えた時点で同数の既存 `<lambda>` エラーが発生しました。これは破棄前かつモーダルなしでも発生するため、今回の変更の指摘に含めていません。
- root が実行した全体 gate の記録は `1596 passed, 4 warnings in 245.19s`、skip は 0 件。gate log: `tmp/quality-gates/pytest-20261015-125449-8724249.log`。18 枚の画面証跡と実帳票 3 / 34 / 9 / 17 ページの確認結果は review-scope の証拠を参照しました。レビュー役として全 suite や画面確認を再実行していません。

## Codex Consultations

- 独立した複雑ロジックの静的レビューを共有 wrapper で依頼し、response を全文読みました。結果: **PASS — no concrete new defects found in the seven owned files.**
- sandbox: `read-only`、`write_access: false`、model: `gpt-5.6-sol`、`model_reasoning_effort=medium`。byte 一致が確認されたローカル snapshot を作業ディレクトリに使用。独立レビューでも結論を実ソースと照合しました。
- prompt: `.agents/logs/codex/20261015T040353Z-quality-webpier-pdf-preview-modal-continuous.prompt.md`
- response: `.agents/logs/codex/20261015T040353Z-quality-webpier-pdf-preview-modal-continuous.md`
- execution log: `.agents/logs/codex/20261015T040353Z-quality-webpier-pdf-preview-modal-continuous.err.log`
- CLI は追加の製品テスト・GUI 操作を実施していません。gate と画面 QA は root の記録を使用しており、coverage の新規測定値はありません。

## Communication with Teammates

- → root: Guardrail の適応を確認したこと、README の並行変更を除外したこと、破棄 callback の仮説と実機 probe による否定を報告。
- ← root: 対象 7 ファイル、除外範囲、全体 gate・画面 QA・snapshot hash の確認結果を受領。

## Issues Encountered

- nested CLI は K ドライブ参照が不確かなため、指定されたローカル snapshot で実行し解決しました。
- 破棄 probe の初回出力に既存入力シート由来の Tcl エラーが含まれたため、破棄前／後を分け、モーダルなしの比較条件を追加して切り分けました。今回の変更による破棄エラーは再現しませんでした。
