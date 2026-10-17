# P7線路方向NDU出力の実装記録

2026-10-17。承認計画: [p7-longitudinal-ndu-export](../plans/p7-longitudinal-ndu-export.md)。ユーザー「はい進めてください」で実装・検証・初回0710/NDU生成を開始。

## 実装責務

- ndu_mapping: 地盤条件導出、NDUモデル、CP932シリアライザー、フィールド対応表。
- pdf_inputs: NDU専用成果物台帳、CLI/GUI、共通公開処理との連携。
- ndu_acceptance: 独立期待値、実アプリ保存後レコード照合、保持候補の受入公開。
- root: 工程確認、統合検証、独立レビュー、初回成果物の生成。

所有権検査は `.agents/logs/ownership-team-execute-p7-longitudinal-ndu-export.json` に対しpreflight成功、重複なし。新規snapshot/receiptのglob未一致は予定ファイルのため。

## 開始時の証拠

- 現在入力SHA: `d8da41d8d87a04b33a35cc45226231564ebd1dc1dcdcf3abce397d7487887f78`。
- 同一バイトの受入スナップショット: `./pre/snapshots/ndu-origin-d8da41d8d87a04b33a35cc45226231564ebd1dc1dcdcf3abce397d7487887f78.json`。
- 現0710 PDF/JSON、Example NDU、既存post4ファイルの開始SHAは `tmp/p7-ndu-implementation/root/baseline-hashes.json` に保存。
- 実装前の `.agents/check.ps1` はuvの既存lock不整合でテスト起動前に停止。ログ `tmp/quality-gates/pytest-20261017-122254-8304706.log`。依存更新を行わず、`UV_NO_SYNC=1`で既存環境の同じ全pytestを実行して確認する。

## Gate 1の実アプリ確認

インストール先 `C:/RTRI_Program/JRSNAP(Ver5.2-L03)/JRSNAP_Input.exe` はFileVersion/ProductVersion=5.2.3.0、AssemblyVersion=5.2.3.1。SHA-256=`90928f1844cd033b2e0f30485205631d367910f6a38e15cb3845ffc1ba064807`。

見本を複製し、旧CHOKU・基礎照査リンク・地層表示・SoilRenkei・NDTPathを除外した一時モデルで、5.2本体のread/saveを検証した。`ChokuKisoNum=0`、`G_intCHOKU_KISO_Link_Num=0`、支点case0、`SRenkeiNum=0`、`TishouNum=0`が読める。ただし `Tisou=` 空行を保持する必要があり、この行自体を削除するとreaderが空文字→Byte変換で失敗する。

- 一時入力: `tmp/p7-ndu-implementation/root/empty-tisou.ndu`。
- 保存後ヘッダー: `Virsion=5.2.3.S.4`。
- 第1/第2保存SHAが一致: `4d041fa3722397305e44b04fb9a4978f588cd313c614026161c9ab224b5b99c6`。
- 旧原本は未変更。helper検査モードを使い、GUI操作・NDT出力・解析は行っていない。

## 未完了の工程

field map確定、製品実装、回帰検証、独立レビュー、P7実値による初回受入と正式公開は進行中。これらの完了を確認するまでNDU生成完了とは扱わない。

## 6部材モデルの技術確認と追加条件

1要素1部材の6部材表現を、同じ7節点・6要素と接続で実アプリ読書きした。`tmp/p7-ndu-implementation/root/six-members-readback-result.json` に103レコード一致と2回保存安定を記録。正規化SHAは `e234e2417d4b3499bc44481bd5aa67a40d4daf5ce3cc15053dd379f02a838599`。`Member_BunpuBane` と `ShabuzaiMeInfo` は元の位置に各ブロックを維持する。NDU readerは逐次行読込のため、項目名が同じでも前方へ移動すると境界例外になる。

未入力の2項目を具体化して非同期確認した: せん断用部材係数 Vcd=2.0 / Vsd=1.3 / Vdd=1.8（標準1.3 / 1.1 / 1.2）と粗骨材最大寸法25 mmを、見本の設定としてP7へ採用するか。承認済み計画の追加工学条件ゲートに従う。回答に依存しない地盤導出・成果物連携・独立読戻しの実装は開始し、正式生成は条件確定後とする。

## 入力画面追加への仕様変更

ユーザー回答「入力画面に追加する」により、せん断部材係数3個と粗骨材最大寸法を編集可能なraw入力へ変更する。見本値を初期値にして今回のNDUへ使用するかは別途回答待ち。Df/γ2自動導出を維持する。4項目保存後の原本を新SHAスナップショットとして保全し、旧起点からの差分4項目だけを照合して受入する。

## 中間品質ゲート

`UV_NO_SYNC=1` と既存venvを使った `.agents/check.ps1` がexit0、overall pass。全3802件が844.98秒で通った。ログ: `tmp/quality-gates/pytest-20261017-122403-8445712.log`。実装中に完了した中間検証であり、新規NDU試験を含む最終検証とは区別する。

```json
{"overall":"pass","tools":{"pytest":{"status":"pass","exit_code":0,"summary":"3802 passed in 844.98s (0:14:04)"}}}
```

所有権を更新して入力欄に必要な `editor_model.py` と同testsをpdf_inputsへ追加し、preflightを再実行して重複なし。受入スクリプトの新wrapperを用いた6部材形式probeも実5.2で2回保存安定、保存対象は一時複製だけ。

## 4項目の実値確定

ユーザー回答「見本値を初期値にして作成する」で4項目の今回採用が確定した。`pre/input.json` の `jrsnap_longitudinal` に `shear_factor_vcd=2.0`、`shear_factor_vsd=1.3`、`shear_factor_vdd=1.8`、`aggregate_max_mm=25` を追加した。他のJSON値は旧起点と完全一致。

- 新入力SHA: `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`。
- 新起点: `./pre/snapshots/ndu-origin-7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93.json`。全バイト一致、旧起点は保存継続。
- 差分証拠: `tmp/p7-ndu-implementation/root/approved-input-additions.json`。
- PDF skillの作成開始markerをこの時点で1回実行、exit0。0710更新1PDFとして記録。

## 実値の一時受入と0710表示確認

独立担当が新入力7f22…f0d93と旧d8da…7f78の差分4項目のみを再確認し、oracleの数値期待値を変えず入力世代と承認状態を更新した。初回受入スクリプトで一時出力先 `tmp/p7-ndu-implementation/acceptance/real-input/` へ0710/NDUの4候補を生成し、実5.2 read/save・623欄/166records・8ケースの合力と基礎底面回りモーメントを照合、同じ保持候補を公開、receipt completeまで成功した。正式P7出力はこの時点では未更新。

rootはその0710全3頁をレンダーして確認。図・式・表・頁番号に欠けや重なりなし。保存済み旧0710との抽出本文差分は3頁ともゼロ（`tmp/p7-ndu-implementation/root/0710-candidate-text-diff.json`）。入力世代の更新と、変わらない作用値・帳票本文を区別する。

## 実装完了と最終ゲート開始

3担当の製品実装は完了した。地盤導出・モデル・serializerの90件、成果物/CLI/計算制御の110件、GUI/modelの160件、独立受入の68件がそれぞれ成功した。ネットワークドライブ上のall+JRSNAPで18ファイル初回公開と上書き、GUIの期待集合/6PDF検査も成功（`tmp/p7-ndu-implementation/integration/real-all-verification.json`）。既存通常0710の試験24件も成功し、同一検証を二重実行する回帰を修正している。

新規モジュールのruffは成功。既存GUI関連6ファイルの指摘28件はベースラインにも存在し、本変更の新規指摘は0件（`tmp/p7-ndu-implementation/integration/lint-baseline-comparison.json`）。diff収集helperではPATH上にruffがなくskippedになったため、これをlint成功とは扱わず上記の明示実行結果を用いる。coverageは未測定。

12:49:18にrootの最終全体ゲートを開始した。`tmp/quality-gates/pytest-20261017-124918-8096003.log` と終了時の `tmp/p7-ndu-implementation/root/final-gate.json` が証拠。実装後のimport整列だけを行った2担当はcore90件/integration110件を再実行して成功。最終ゲート終了後、別担当3名の独立レビューを開始する。実装担当ごとの同じ全体テストの重複実行は行わず、この共有ゲートを使用する。

Windowsの所有権/diff helperはPYTHONUTF8・PYTHONIOENCODINGを子プロセスにも設定し、git core.quotepath=falseをプロセス限定で適用する。これにより日本語パスの認識・reconcileが成功した。review用の追加所有権もpreflightで重複なし。

## 最終ゲート第1回と修正対象

第1回は `overall=fail`、pytest `1 failed, 4021 passed, 1 skipped in 1067.91s`（exit1、gate exit2）。原本結果は `tmp/p7-ndu-implementation/root/final-gate-first-attempt.json` に保全した。失敗は既存 `test_seismic_transverse_cli.py::test_standalone_needs_no_reference_pdf_or_saved_result_and_matches_all` であり、NDU用に導入した公開後SHA検査が既定の0720経路でも公開PDFを読み直したため。既存の検証条件を弱めず、新しい検査をJRSNAP選択時に限定して従来の入出力契約を保つ。

別の1件のスキップは既知のTk初期化の一時失敗。対象 `test_column_rebar_ui.py::test_present_incomplete_distribution_preserves_missing_mode_until_explicit_choice[distribution1]` は新プロセスで再実行し `1 passed in 11.72s`（`tmp/p7-ndu-implementation/root/skipped-test-replay.log`）。スキップを成功へ読み替えない。

最初の全体実行中にも最終の局所修正があったため、担当の修正・関連チェック後はソースを固定して全体ゲートを再実行する。正式成果物の公開と独立レビューはゲート成功後に進める。

## 別作業の同時変更と検証範囲

第2回開始後、別作業の帳票ライブラリ移行が同じP7へ新規 `pier_design/reporting/`、`tests/reporting/`、そのfixture・scripts・docsを追加し、uv.lockも更新したことを検出した。新規移行試験が未実装機能を要求して失敗していたため、NDU作業の試験として扱わずrootの実行だけを中断（`final-gate-external-tests-interrupted.json`、pytest exit-1）。他作業のプロセス・ファイルを停止・削除・復元していない。

13:13:05より `.agents/check.ps1` を `UV_NO_SYNC=1`、`PYTEST_ADDOPTS=--ignore=./tests/reporting` で再実行。従来の全top-level試験と今回のNDU試験を対象とし、同時追加された別機能の試験だけを除外する。ログ `tmp/quality-gates/pytest-20261017-131305-6511426.log`。結果は帳票移行の合格証拠にはしない。

全差分は125パス・21MBに増えた。所有権と今回の研究資料に絞った33パス・408373bytesを `tmp/p7-ndu-implementation/root/review-task-scope.json` / `review-task.patch` に保存し、別作業と以前から存在するスキル類を明記して分離した。今回更新したNDUスキル参照文書は含む。製品と試験の固定SHAを `final-gate-source-hashes.json` に保管し、今回の対象ソースに変更がないことを確認している。

## 隔離した検証版と回帰結果

13:25までに別セッションの移行が `cli.py`・`jrsnap_artifacts.py`・`accept_jrsnap_ndu.py` にも変更を加えた。元に戻さず、git HEADのP7と先に保全した今回の33ファイルから `C:/Users/sasai/AppData/Local/Temp/p7-ndu-final-review-20261017` に検証版を構築した。141対象中132ファイルは保存SHAと一致し、変更前チェックアウトの混在改行を再現できなかった既存9ファイルはgit HEADの内容を使用した（`isolated-source-verification.json`）。全ファイルのバイト一致とは主張しない。

既存全体＋NDUの最終実行は `1 failed, 4021 passed, 1 skipped in 803.92s`、gateはoverall failのまま記録した。失敗はGUIのtksheetで無効Tk widget command、スキップはTk初期化時の一時エラー。関連7ケースの再実行はoverall pass／5 passed・2 skipped。スキップされた2ケースはそれぞれ新規Pythonプロセスで1 passed（9.52秒／8.17秒）、元のスキップ対象も関連実行で成功。既存0720回帰は別途128件成功で確認した。これらを全体gateが一度で成功した記録に読み替えない。

隔離版のNDU関連＋保護対象0720のgateはoverall pass、217 passed・2 skipped・3804 deselected（40.88秒）。GUI初期化による2 skipは個別新プロセスで1 passedずつ（2.93秒／4.45秒）。証拠は `isolated-focused-gate.json` と `isolated-gui-*-replay.log`。

隔離版から実入力で再度受入し、JRSNAP 5.2-L03の2回保存、166レコード・623欄・8ケース照合、同じ候補の一時公開が成功した。`isolated-acceptance.json` はpublication ID `49c7522984764d31ab0afca298c0a5ea`、NDU SHA `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`。レビュー修正前の記録なので正式出力の受入記録には再利用せず、修正完了後に再検証する。

## 独立レビューと修正

セキュリティ・品質・テストの3担当が隔離版を独立に確認した。現時点の修正対象は次の3点。

- SEC-1（Low）: 相対output-dirと受入receiptの保存先が同じ場合、resolveの不統一で衝突を見逃す。公開は止まるが、結果JSON位置に途中receiptが残るため、すべての成果物パスを絶対化して比較し回帰試験を追加する。
- T1（Medium）: 実生成物と独立literal oracleを直接比較するpytestが不足。承認済み不変入力から実計算→export→serialize→独立readback検証を追加する。現行P7は直接照合で166レコード・623欄・8ケース一致。
- 配筋の対応範囲: 選択方向の主筋段の外側／間に側面筋が入る配置では、NDUの先頭／末尾N段と意図した主筋集合が異なる。v1では同一性を検証し、不一致配置を明示拒否する。今回のP7配筋はこの不一致に該当しない。

修正は各元担当が隔離版と共有版に同じ最小差分を適用し、別セッションの帳票移行を保持する。正式0710/NDUは、検証した隔離版から承認済み入力を用いて生成する方針とした。共有側の別機能の完了判定・全体移行の承認はこのNDU受入とは区別する。

## 修正後の検証と正式成果物

配筋選択の検証を追加し、側面筋の外側配置・段間割込み・同段混入を拒否した。正常な複数段と基本配置に一致する手動配置を維持し、core試験95件が成功。品質担当も元の2反例の拒否と正常2段の出力を独立再確認した。今回P7の生成NDUは修正前後で全6298 bytes一致。受入処理のパス衝突修正と独立oracleへの実生成クロスチェックを追加し、受入試験71件が成功。誤係数GBVO=1.4の変異は新テストが `SectSafe1[12]` で検出した。セキュリティ担当は衝突2例を独立実行して成功した。

rootによる修正後の隔離版gateはexit0・overall pass、**224 passed, 3712 deselected in 33.29s**（`tmp/p7-ndu-implementation/root/isolated-final-gate.json`）。全JRSNAP関連と保護対象0720を選び、今回再変更していないGUI moduleを除外した。GUIの前回成功／個別再実行は上記別証拠を参照する。全4000件の一括成功や共有の帳票移行全体の成功という意味ではない。

2026-10-17 13:43:45 JSTに正式受入・公開が完了した。

- 受入記録: [p7-longitudinal-ndu-acceptance-20261017-final.json](p7-longitudinal-ndu-acceptance-20261017-final.json)、status=`complete`。
- 公開ID: `ec20665af3a04ab192b8fbd6a70e91c7`。入力SHAは承認済み `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`。
- 正式4ファイル: `./output/0710_線路方向荷重.pdf` と同JSON、`./post/線路方向.ndu` と `線路方向.ndu.provenance.json`。隔離版から共有の承認済み入力を読み、候補を保持したまま実アプリ受入後に一括公開した。
- NDU SHA: `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`。CP932・CRLF。Df=4.7 m、γ2=12.3 kN/m³、4追加入力は承認済みの2.0／1.3／1.8／25 mm。
- JRSNAP 5.2-L03（File/Product 5.2.3.0、Assembly 5.2.3.1）で候補の複製を読込・2回保存し、候補と各保存で166レコード・623欄・8荷重ケースを独立照合。正式NDUは保持していた候補bytesをそのまま公開し、アプリ正規化後bytesと取り替えていない。
- 公開後4ファイル・証拠のSHA、Example原本と既存FrameWeb等5ファイルの不変を再検証。0710全3頁は目視済み候補と本文・レンダー画素が完全一致。`tmp/p7-ndu-implementation/root/final-verification.json` はpass。
- 並行移行によるソース上書きと区別できるよう、実受入が参照した70ファイルの全bytesと承認済み入力を `p7-longitudinal-ndu-acceptance-20261017-final.evidence/accepted-source.zip` に保存し、manifestの各SHAと照合した。実行環境・アプリ本体はarchive対象外で、版・本体SHAは受入記録に残す。

実アプリのGUI画面確認、NDT作成、構造解析、応答・耐震安全性の照査は行っていない。通常生成sidecarの `app_read_verified=false`・`analysis_run=false` は仕様どおり保持し、この外部受入記録を初回の読込・再保存証拠とする。

共有側には今回の最小修正とREADMEの対応範囲を反映済み。帳票移行のソースは保持した。共有テスト3例のうち2例は成功し、残る1例はテスト中に別セッションがソースを変更したため既存競合検出で停止した。隔離版では同じ全ケースが成功しており、並行移行の進行中の状態を本機能の安定版検証と混同しない。

共有版についても、担当が現在入力→実0500/0710→モデル→serializer/validatorを読み取りだけで実行し、14ソースの前後SHAが安定した状態でNDU SHA `02e247…26ed71` と入力SHAの一致を確認した（`tmp/p7-ndu-implementation/integration/shared-integration-review.json`）。移行差分の静的確認では同一計算・保持候補・manifest・一括公開とrollbackの境界を壊す具体問題は認められなかった。共有版でのPDF描画・公開・実アプリ受入や、移行が広げた通常出力の検査全体を検証したものではない。

独立3レビューのQ1（High）・T1（Medium）・SEC-1（Low）はすべて修正後に各レビュアーが解消確認し、未解消指摘は0件。詳細と修正前の記録は `review-{quality,tests,security}-p7-longitudinal-ndu-export.md` に保持した。

最終整理では6担当のwork-log契約検証とreview workspace存在検証が成功した。所有権reconcileは `ok=true`、重複・未割当・未実施ownerはいずれも0件。既存資料と別帳票移行の77パス等は理由付き `ownership-exclusions.json` で区別し、今回成果物へ取り込まず保持した。今回対象の `git diff --check` はexit0。計画Step 6・7とtask listを完了へ更新した。
