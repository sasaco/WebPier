# Security / Data Integrity Review: P7 Longitudinal NDU Export

レビュー日: 2026-10-17

## Summary

未解消の指摘は0件。初回レビューで相対出力パスと受入記録のパス衝突検査にLowの不具合を1件確認し、SEC-1修正後のコード・証拠確認とJSON/PDF衝突2ケースの独立再実行で解消を確認した。通常の候補公開、入力・ソース・候補バイトの変更検出、sidecarによる同一世代確認、ロールバック、CP932/CRLF処理について、今回の範囲で追加の具体的な不具合は確認していない。

共有作業ツリーには別セッションの帳票移行が進行中のため、製品コードは `C:/Users/sasai/AppData/Local/Temp/p7-ndu-final-review-20261017` の凍結版だけをレビューした。共有ツリーへの統合確認は別途必要であり、本レビューをその確認済み証拠として扱わない。

## Review Scope

- 対象は `tmp/p7-ndu-implementation/root/review-task-scope.json` の33パスと `review-task.patch`。brief末尾の隔離指示を優先した。
- 重点確認: `pier_design/cli.py`、`jrsnap_artifacts.py`、`jrsnap_design_conditions.py`、`jrsnap_export.py`、`jrsnap_ndu.py`、`jrsnap_readback.py`、`scripts/accept_jrsnap_ndu.py`。
- GUIからの引継ぎ: `editor_calculation.py`、`editor_model.py`、`editor_gui.py` の変更箇所。関連テストとfixture、CONTEXT、承認計画を参照した。
- 変更のない `artifact_publication.py` と `frameweb_artifacts.py` は、公開・復旧・パス解決の呼出先として確認した。既存処理自体を今回の変更と誤認していない。
- `context-loader` / `linksee-memory` / `team-execute` のレビュー手順を適用し、NDU形式スキルの適用範囲と不変条件を参照した。欠けているrules/STATE/DESIGNはbriefで既知とされており、新設していない。
- 製品ファイルは変更していない。再現では新規一時ディレクトリだけへ入力複製・候補・受入記録を生成し、実アプリ実行はmockに差し替えた。

## Findings

### SEC-1 [Low / 解消済み] 相対出力先の結果JSONを受入記録で作成できる

以下は修正前の問題と再現記録。修正確認は直後の「SEC-1 Close-out」に記載した。

- **場所**: `P7橋脚/scripts/accept_jrsnap_ndu.py:317`（315–318行の衝突検査）。関連する相対パスの生成は `P7橋脚/pier_design/cli.py:289`。
- **原因**: 受入記録の `path` は `.resolve()` 済みだが、`candidate.artifact_hashes` のPDF/JSONキーは `--output-dir` の相対Pathを保持する。`path in candidate.artifact_hashes` は同じ実ファイルを表す相対Pathと絶対Pathを一致と判定しない。
- **再現条件**: 新規の出力先で `--output-dir output --receipt output/0710_線路方向荷重.json` を指定する。正しいP7入力、実計算・実NDUシリアライザーを使用し、実アプリの複製読戻し部分のみ `first=second=candidate bytes` を返すmockへ差し替えて再現した。入力は一時ディレクトリへ全バイト複製し、製品ファイルには触れていない。
- **実測結果**: `InputError: 候補生成後に出力先が変更されました: output\0710_線路方向荷重.json` で失敗する。一方、失敗後のこの結果JSONパスには `status="verified_pending_publication"` の受入記録が残る。その他の正式成果物は未公開だった。
- **影響**: 公開直前の出力先変更検出が働くため、成功の誤報・NDU公開・既存成果物の喪失は生じない。ただし、本来は事前拒否されるパス衝突が結果JSONの作成まで進み、計算結果用パスを別スキーマの受入記録で占有する。設定ミスが必要で既存ファイル上書きも防止されるためLowとした。
- **推奨修正**: `path in {artifact.resolve() for artifact in candidate.artifact_hashes}` のように両側を正規化して比較する。相対 `output_dir` と結果PDF/JSONそれぞれへのreceipt衝突で、受入記録・evidence・snapshotを作成する前に拒否する回帰ケースを追加する。
- **再現対象の受入スクリプトSHA-256**: `37249785a24ca585a952e975ed40ff1828d853c51ca652e8760f989f5ce13466`。

## SEC-1 Close-out

- 修正後の凍結版 `scripts/accept_jrsnap_ndu.py:317` は `{artifact.resolve() for artifact in candidate.artifact_hashes}` と解決済みreceiptパスを比較する。受入記録・evidence・snapshotの作成より前に同一実パスを拒否することをコードで確認した。
- スクリプトの実測SHA-256は `9072b6367acba2dada486fd8bffe684d1c4cb320b3249f9b04b88db3be544add` で、担当者の修正証拠と一致した。
- `tests/test_jrsnap_acceptance.py:71` の追加テストは実生成経路、相対output、JSON/PDFの2ケースを使い、`Receipt collides` での拒否と、入力以外のファイル・snapshot・evidenceが残らないことを検証する。
- レビュアーが隔離版で `python -X utf8 -m pytest P7橋脚/tests/test_jrsnap_acceptance.py -q -p no:cacheprovider -k receipt_collision_with_relative_real_output` を独立実行し、**2 passed / 69 deselected / 4.44s、exit0**を確認した。実アプリ・全体ゲートは再実行していない。
- `tmp/p7-ndu-implementation/acceptance/review-fixes/validation-results.json` の隔離71 passed / exit0とruff passを確認した。`after-hashes.json` では共有側の既存差分保持も記録されている。共有側では並行編集によりPDFケースがsource driftで停止したため、その実行を全件passと扱わない。解消判定は凍結版のコードと成功した隔離検証に基づく。
- 受入スクリプトのソースSHAが変わったため、下記の実V52受入証拠は修正前の履歴である。修正後の最終ゲート・正式受入はリード担当であり、この再レビューで実施済みとは主張しない。

## Verification Evidence

- 独立再現: 上記SEC-1の実計算・実シリアライザーを使用する一時領域テストを実行し、例外と失敗後のファイル内容を確認した。PowerShell/子Pythonの終了コード0は再現スクリプト自体の正常終了であり、候補公開成功を意味しない。
- SEC-1修正前の実V52受入証拠 `tmp/p7-ndu-implementation/root/isolated-acceptance.json` を初回レビュー時に読込み、当時の凍結版 `_check_binding(receipt, published=True)` を再実行してpassを確認した。新たなアプリ起動・receipt書換えは行っていない。以下のID・ハッシュはその時点の履歴である。
- 同receiptのstatusは `complete`、publication IDは `49c7522984764d31ab0afca298c0a5ea`、対象4成果物、166レコード/623フィールド/8荷重合力を照合済み。NDU SHA-256は `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`。GUI検査・解析実行はfalseのまま維持されている。
- リード実行の隔離focused gate `isolated-focused-gate.json` は `overall: "pass"`、`pytest.status: "pass"`、`exit_code: 0`（217 passed / 2 Tk skipped）。本レビューでは全スイートを再実行していない。
- リードの既存全体ゲートは4021 passed / 1 GUI failed / 1 Tk skippedでoverall failを維持している。失敗・skip対象には新規インタープリタ等での成功記録があるが、元ゲートをpassへ読み替えていない。共有ツリーの後続変更まで検証した証拠でもない。

## Limits

このレビューは凍結した機能実装のセキュリティ・データ整合性確認であり、未対応と明記された土層・水位・配筋条件の拡張、全NDU仕様の検証、耐震解析、GUI実操作による受入ではない。公開は既存実装どおり複数ファイルのOSレベル単一トランザクションではなく、変更検出・journal・バックアップ復旧を用いる。
