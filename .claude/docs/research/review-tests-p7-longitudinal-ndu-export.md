# Test Review: P7 Longitudinal NDU Export

レビュー日: 2026-10-17。対象は `C:/Users/sasai/AppData/Local/Temp/p7-ndu-final-review-20261017` の隔離済み機能版。共有 K: ツリーで並行中の reporting migration は対象外。範囲は `tmp/p7-ndu-implementation/root/review-task-scope.json` の 33 ファイル。Coverage: **not measured** (`coverage: null`)。

## 結論

Critical / High の指摘はない。Medium として報告した T1 は、修正コードと変異試験の証拠を再確認して **解消済み**。未解決のテストレビュー指摘は 0 件。現入力の実生成 NDU は、独立 literal oracle の 166 レコード・623 フィールド・8 ケースの基礎底面回り合力に一致し、その交差照合が通常 pytest に追加された。

隔離版では初回レビュー時点の source に対する実 JRSNAP 5.2-L03 の読込・2 回保存と保持候補の公開も完了している。受入スクリプトの別レビュー修正後の source に対応する最終 receipt、正式 P7 出力への適用、共有ツリーの最終統合確認は lead が扱う。ここでは共有ツリー全体の統合完了を主張しない。

## Findings

### [Medium / 解消済み] T1: 実 exporter / serializer の全フィールドを独立 oracle と照合する通常回帰テストがない

- 場所: `./tests/test_jrsnap_cli.py:247`、特に `:260`。関連: `./tests/test_jrsnap_acceptance.py:31`、`:58`。
- `test_real_engine_single_and_all_use_identical_ndu_bytes` は実生成物を本番 `validate_ndu_bytes` で検証し、件数・メタデータ・0710/all の同一バイトを確認する。一方、`test_independent_native_oracle_checks_fields_and_integrates_all_eight_cases` は同じ oracle から作った `reference_bytes()` を検証する。そのため通常テスト内では「本番の生成物」と「承認済みの独立した全フィールド期待値」が交差しない。
- 再現: 製品ファイルを変更せず、別 Python プロセスの `_PROFILE['section']['safety']['GBVO']` だけを 1.3 から 1.4 に変更した。実 CLI 0710/all、exporter の幾何・配筋・支持、native framing/determinism、独立 oracle 自体の検査という該当 4 テストは **4 passed in 7.86s**。同じプロセスで現入力から生成したバイトを `verify_readback` へ渡すと、期待どおり `SectSafe1[12]: 1.4 != 1.3` で拒否された。全 suite を変異状態で実行したとは主張しない。
- 影響: 正値の誤った係数や許容範囲内の誤ったフィールド割当ては、本番形式 validator と独立 parser の単体試験の両方を通り得る。初回実アプリ受入では検出できるが、通常 pytest の将来の回帰検出には残らない。
- 必要な最小ケース: oracle の `input_sha256` に対応する immutable な `pre/snapshots/ndu-origin-<SHA>.json` を用い、実 0500/0710 → `build_longitudinal_ndu_model` → `serialize_ndu` の結果を、そのまま `verify_readback(data, literal_oracle)` に渡す 1 テストを追加する。期待値や比較 parser は exporter から生成せず、既存 fixture を再利用する。実 JRSNAP は通常テストに不要。
- 現状の緩和証拠: レビュー中の独立追加照合と fresh 実アプリ受入はともに PASS。したがって現在の公開候補に誤値があるという blocker ではない。

### T1 修正後の再確認

`./tests/test_jrsnap_acceptance.py:45` の `approved_snapshot_bytes()` は literal oracle の input SHA を使って immutable snapshot を選び、実バイトの SHA 一致を assert する。`:54` の新テストは実 `_calculate_stages` による 0500/0710、実 `build_longitudinal_ndu_model`、実 `serialize_ndu` を通した結果を `verify_readback` に渡す。期待値を本番定数から生成していないことをコードで確認した。

隔離ファイルの SHA は `56f4b235a230cad3e8141dc4beeefb136232f19e9bcb00b2e4439d08b674f884` で owner の報告と一致。`tmp/p7-ndu-implementation/acceptance/review-fixes/validation-results.json` により、修正後 acceptance 71 passed / 9.14s、同じ in-memory GBVO=1.4 変異で新テストが `SectSafe1[12]: 1.4 != 1.3` を検出して期待どおり失敗したことを確認した。修正後 lead gate は **224 passed, 3712 deselected in 33.29s、overall=pass**。これで T1 を閉じる。全テスト・実アプリの重複実行はしていない。

## 確認できた検証範囲

| 観点 | 確認したテスト・実装と評価 |
|---|---|
| 数値の独立性 | fixture は承認済み入力・0500 oracle・0710 精度・独立算術の literal。`jrsnap_readback.py` は exporter とそのフィールド定数を import しない。合力だけでなく一次モーメントを独立積分し、同じ合力でも台形分布の向きを変えた変異を拒否する。 |
| 形状・単位・符号 | 現配筋、材料・寸法変更、H1 偏心形状、H2=0 の節点合流、微小部材 0.010 m と残長境界、EQL の -128 kN、EQ2 の分布・基礎慣性、Ec の単位、作用位置変更の拒否を確認。役割参照を用い、単に固定 ID だけを前提にしたテストではない。 |
| Native 構造 | CP932 strict / CRLF、再生成決定性、空の `Tisou=`、件数・参照・位置順・非有限値・不正文字・旧リンク・余分/不足/重複レコードを検査。 |
| Df / γ2 と入力 | 現 P7 と見本式の別条件、土被り差・表層厚の 1e-9 m 境界、水位両端点・範囲外、4 入力の不足/型/非有限値/正値を検証。README の限定地盤条件を一般地盤への対応不足として扱わない。 |
| 公開トランザクション | input/source/source-set/candidate/追加・欠落/モデル/計算辞書/出力先の drift を拒否。0710/all の serialize/write/staged-validation/replace/final-validation 失敗で一式を復元。公開直前の競合書込・競合削除は実際の backup 状態へ復元するテストがある。 |
| 受入証拠 | FakeCandidate は受入 orchestration の単体検査に限定し、別途実 CLI candidate と実 V5.2 の fresh 受入がある。receipt 初回作成失敗・最終更新失敗と再開・input/source/output/evidence/oracle/source-set の再検証、helper timeout/exit/不正 JSON/古い・欠落・不安定な保存結果を検査。 |
| GUI / 旧 JSON | 4 欄の未入力表示・非編集時バイト保持・編集保存再読込・空欄化、無効値で部分保存しないこと、起動時 opt-in OFF・job 捕捉・実行中無効化・生成失敗後の保存入力保持、18 成果物検証と NDU 変更による stale 検知を確認。 |
| 既存経路 | 未選択時の既存 0710 NDU 非更新、既存出力件数、FrameWeb schema 2 / publication ID、保護対象 0720 の保存済み PDF 非読込契約を含む lead gate を確認。 |

手動配筋は現 basis と自動基本配置が物理的に一致する場合だけ、地盤は表層 + 支持層・水平土被り・支持層上面 = 基礎底面・水位内部だけという v1 の明記された範囲で評価した。構造解析、NDT、GUI 操作による JRSNAP 目視検証、直角 NDU は要求していない。

## Test Execution Results

| 実行・証拠 | 結果と範囲 |
|---|---|
| lead の established + NDU full gate | **4021 passed, 1 failed, 1 skipped in 803.92s**。`tmp/p7-ndu-implementation/root/final-gate.json` は overall=fail のまま。失敗は Tk widget 消失による navigation 動作前の `select_cell` エラー。全体 PASS に読み替えない。 |
| full gate の GUI 個別再実行 | navigation 1 passed / 9.52s、save 1 passed / 8.17s。関連 7 ケース gate は 5 passed / 2 skipped / 29.86s、column の元 skip はそこで通過、追加 2 skip は新プロセスで通過。lead 提供の `gui-*-replay.log` / `gui-replay-gate.json` を根拠とする。 |
| 隔離 feature の標準 gate | `.agents/check.ps1` exit 0、**217 passed, 2 skipped, 3804 deselected in 40.88s**。全 JRSNAP + 保護対象 0720。`isolated-focused-gate.json`。 |
| 隔離 gate の GUI 2 skip | 新プロセスの選択テスト 1 passed / 2.93s、無効値保存テスト 1 passed / 4.45s。`isolated-gui-selection-replay.log`、`isolated-gui-validation-replay.log`。元 gate の skipped 表示は保持する。 |
| レビュアーの直接生成照合 | 現 frozen raw → 実計算 → 実 exporter / serializer → 独立 oracle：166 records / 623 fields / 8 cases PASS。raw SHA `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`、native SHA `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`。 |
| レビュアーの in-memory 変異試験 | 関連する既存 4 tests は 4 passed / 7.86s、その後の直接 oracle 照合は `SectSafe1[12]` の差を検出。T1 の限定的な再現であり、正常な製品全体 gate ではない。 |
| fresh 実アプリ受入 | `isolated-acceptance.json` status=complete。実 EXE file/product 5.2.3.0、assembly 5.2.3.1。候補・保存1・保存2 の各 166 records / 623 fields / 8 cases が PASS。候補 SHA は上記と一致。公開先は隔離 `candidate/{output,post}`、正式 P7 出力ではない。 |
| T1 修正後 acceptance | owner 実行 **71 passed / 9.14s**、Ruff exit 0。変異試験は新テスト 1 failed / 70 deselected / 1.07s で、誤係数を拒否する期待失敗。`acceptance/review-fixes/validation-results.json`。 |
| 修正後 lead gate | `isolated-final-gate.json` overall=pass、**224 passed, 3712 deselected in 33.29s**。GUI module を除外した gate。GUI の変更はなく、以前の 2 skip の個別 PASS 証拠を別に保持する。 |

Coverage は未測定。実施済み検証項目数からカバレッジ率を推定しない。旧受入 receipt は CLI fix 前の source hash を含む。上記 isolated receipt もその後の受入スクリプト修正前の source に対する証拠なので、最終 source の公開根拠には lead の更新後 receipt を用いる。

## 残る作業と限界

T1 は解消済み。共有ツリーでは別作業が cli/artifacts/acceptance を変更しているため、最終の共同統合確認と正式出力は lead の調整対象。shared の targeted run は real-export oracle と JSON receipt collision が PASS、PDF collision は同時 source 変更を guard が検出して停止したと owner 証拠に記録されており、共有 gate PASS とは扱わない。現レビューで製品ファイルは変更していない。
