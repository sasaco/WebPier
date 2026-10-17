# Security Review: P7 PDF Preview Modal and Automatic Advance

## Summary

結論: PASS。承認済み計画と所有差分の 7 ファイルを照合し、修正が必要なセキュリティ・データ整合性の問題は見つからなかった。製品コードやテストは変更していない。

## Review Scope

- 承認済み計画: `.agents/docs/plans/p7-pdf-preview-modal-continuous.md`。
- 所有範囲: `.agents/logs/agent-teams/team-execute-p7-pdf-preview-modal-continuous/review-scope.json` の 7 ファイル。指定の所有差分と、親が SHA-256 一致を確認したローカルスナップショットの実ソースを読んだ。除外された並行作業は評価対象外。
- `P7橋脚/pier_design/pdf_preview.py`: PDF 読込・自動遷移・画像と予約の解放。PDF は引き続き context manager 内で開閉される (:49–67)。ページ寸法・倍率・描画量の制限は維持される (:88–109)。自動送り先も既存の `show_pdf()` を通り (:421–433)、アクセス確認はメタ情報読込と描画の前後に実施される (:212–228, :304–327)。追加のスレッド・プロセス・ネットワーク処理はない。
- `P7橋脚/pier_design/pdf_preview_dialog.py`: パスと表示ラベルの分離、スナップショットの順序、モーダルと終了処理。ツリー項目 ID から元の `Path` を引き (:166–191, :208–239)、ラベルをパスやコマンドに変換しない。読込不可の次項目を自動で飛ばす経路はない。ローカル grab (:125–140) と冪等な終了処理 (:269–303) を確認した。
- `P7橋脚/pier_design/editor_gui.py`: 一覧走査は既存 output 内の通常の PDF 候補に限定され、シンボリックリンク除外を維持する (:439–450)。freshness の根拠は既存 controller のままで、アクセス通知では状態とラベルだけを更新する (:514–534)。保存・fingerprint 確認後、busy 設定と worker 起動前にプレビューを閉じる (:536–568)。成功検証・busy 解除後に自動表示し、表示失敗を計算失敗と混同しない (:486–504, :582–607)。別名保存時も成功したパス変更の後にだけ閉じる (:733–748)。
- `P7橋脚/tests/test_pdf_preview.py`: PDF ハンドルの閉鎖と Windows での置換 (:52–77)、欠損・破損した次 PDF で停止して再試行する検証 (:562–608)、自動送り後のハンドル閉鎖と予約・画像解放 (:611–637) を確認した。
- `P7橋脚/tests/test_pdf_preview_dialog.py`: ラベルとパスを混同しない一覧更新 (:198–245)、破損・削除された次項目で停止 (:349–376)、各 close 経路と部分構築・grab 失敗後の解放と再作成 (:379–480) を確認した。
- `P7橋脚/tests/test_editor_gui.py`: 保存・fingerprint 失敗時の状態保持 (:898–924)、計算中の全入口ガード (:927–980)、外部 PDF・JSON 変更時の失効と追加 PDF の区別 (:1116–1199)、自動表示順序と失敗後再試行 (:1252–1341)、別名保存結果別の寿命 (:1344–1370) を確認した。
- `P7橋脚/README.md`: プレビュー関連の操作・失敗・結果ラベル説明 (:94–106) を実装と照合した。並行する骨組み図の追記は評価していない。
- 未変更の `editor_calculation.py:95–147, :279–301` を連携上の根拠として参照し、通常ファイル確認・検証済み成果物の同一性と読み取り確認・stale 遷移が維持されることを確認した。
- 検証実行は親の integration gate を参照した: overall `pass`、pytest `1596 passed, 4 warnings in 245.19s (0:04:05)`。親の確認で skip は 0。レビュー中は CLI consultation や全体テストの再実行をしていない。新鮮な coverage 計測値はない。

## Findings

None。Critical 0 / High 0 / Medium 0 / Low 0。

Guard helper が検出した `pdf_preview_dialog.py:278–300` の 4 個の `except tk.TclError: pass` は、親や Tk 資源が既に破棄された場合の限定された終了処理であり、機能未実装の代用ではない。親 binding 解除、preview cleanup と grab 解放、destroy、フォーカス復帰を別々に保護し、終了通知は finally で一度だけ実行する。部分構築失敗・grab 取得後失敗・親破棄を含む検証がある。

新しい Tk 初期化時 skip とテスト終了時の TclError 許容も確認した。skip は Tk ウィンドウ作成自体が失敗した場合だけで、製品処理や assertion の例外を隠さない。ダイアログ fixture は破棄後も callback error の不在を assertion で検証する (`test_pdf_preview_dialog.py:75–90`)。

## Communication with Teammates

- ← Lead: 所有範囲・承認済み計画・凍結済み実装・親実行の gate・除外対象・スナップショットを受領した。
- → Lead: PDF アクセス、freshness、終了処理の確認を進め、具体的な問題が見つかっていない旨を通知した。
- → Lead: 本報告と work log を提出する。製品修正要求はない。

## Issues Encountered

- 共通ルール等の欠如はユーザーにより既に免除されたため、承認済み計画、P7 README、実ソースに基づき確認した。
- 初回の PowerShell 読取で文字化けがあったため、以降は UTF-8 を明示し、承認済み計画を読み直した。

