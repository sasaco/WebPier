# P7線路直角方向NDU 実装・受入記録

2026-10-17。ユーザーの「線路直角方向も同様に作業してください」に基づく追加機能。正式成果物が完成するまで、本資料の途中経過を完成記録として扱わない。

## 作業版と所有範囲

前回の正式受入が参照する `p7-ndu-final-review-20261017` を保ち、別の `C:/Users/sasai/AppData/Local/Temp/p7-transverse-ndu-20261017` へ356ファイルを複製した。共有P7の帳票移行を上書きしない。開始時のソースSHA・入力／成果物37ファイルSHAは `tmp/p7-transverse-ndu/root/` に保存した。core、連携、独立受入を分担し、所有権preflightは重複なし。

共通ルール読込0件、STATE未存在。context-loaderの結果は `missing=[".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]`、`unreadable=[]`、`warnings=["DESIGN.md is still the uninitialised /init template; run /init to populate it"]`、`design.placeholder=true`、`progress.entries=0`。前回と同じ既知の欠落であり、CONTEXT・既存承認・今回の明示指示・方向別資料を用いて作業を継続する。

## 確定した方向差とAPI

- 0720は9ケース。上下線の列車荷重を独立に保存し、現在0720の組合せ係数 `[1,1,1,1,1,0,1,1,1]` を維持する。旧直角見本の8ケースへ合わせない。
- 直角断面は2700×4500 mm、31配筋行、最外側9-D19・芯102 mm、帯筋6脚。FootInfoの幅9 m・長さ7 mを採用する。根拠は方向別field mapと独立oracleに記録する。
- 直角見本の上部構造節点が制御点。現在0720のB/Cは同一節点、La=10350 mm、La/d=約2.353。B/Cが異なる高さなら新しい制御点選択を行わずv1未対応として拒否する。制御は350step・目標+0.35 m・限定増分最終300。
- 単独0710／0720は各4成果物、allは20成果物。既存FrameWebは0620側の出力なので、正式0720単独では変更しない。GUIはall固定と既存チェック欄を保持し、チェック時に両方向を出す。
- `PreparedGeneration` はstageキーの方向別model/path/metadataを保持する。既存単一属性は0710/allで0710、0720単独で0720の選択aliasとする。allの受入は両方向の独立照合と実アプリ往復が終わるまで公開しない。

## 入力4項目の追加

`jrsnap_transverse` にVcd=2.0、Vsd=1.3、Vdd=1.8、粗骨材最大寸法25 mmを追加した。「同様に」の指示に従う前回と同じ初期値で、既存の線路方向4値を恒久的なaliasにはしない。その他の全JSON値が不変であることを確認した。

- 旧入力SHA: `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`。
- 新入力SHA: `10955ada22130e4b0e249c8c146175809e3eb10cee93331bba75d7c73763173b`。
- 共有と新隔離版のinputとSHA名snapshotを同じbytesで保存した。旧snapshotも保持した。
- 差分証拠: `tmp/p7-transverse-ndu/root/approved-input-additions.json`。
- 作成済みの0710/NDUは旧入力世代の成果物として保持し、今回4設定の追加を理由に書き換えない。前回受入の原入力はsnapshotとsource archiveから参照できる。

## 開始時の関連検証

隔離版の最初の関連gateは294 passed・3542 deselected・100 errors（81.20秒）。100件はいずれも既存0720 calculator fixtureのraw SHA不一致だった。隔離側はCRLFでSHA `beab0526…`、共有の未変更fixtureと期待値はLFでSHA `0a17f5301371fead6383eb00d315f6984bfd21c8580fe2e861a12d088e67f408`。JSON同一、CRLF→LF以外のbytes差なしを確認し、新隔離版だけ元fixtureへ戻した。期待値・assertion・以前の受入ソースを変更していない。

復元後の `test_seismic_transverse_calculator.py` は **100 passed in 2.38s**。この修復は製品不具合の修正ではなく隔離テスト資料の改行復元である。`baseline-gate.json` の元failは履歴として保持し、証拠を `baseline-fixture-newlines.json` に記録した。正式レビュー前に修正後関連gateを改めて実行する。

## クラッシュ後の引継ぎと正式公開（2026-10-17 19:00〜19:40）

- クラッシュ時点：隔離版の実装・関連gate（637 passed）・実V52初回probe（候補 `16f2da64…`、2回保存一致、200レコード/724項目照合）まで完了。共有への統合・正式公開は未実施だった。
- 共有統合：所有ファイルは開始時baselineから共有側変更なしを確認。17ファイルを3-way merge（`git merge-file`）し、衝突は cli.py（共有の `_rendering_identity`・全計算snapshot検査を保持し、方向別 `ndu_models` へ一般化）、accept_jrsnap_ndu.py（共有の依存hash検査を保持し、方向別 `_check_direction_binding` を追加）、README（共有の `uv sync` 説明を保持）の3件のみ手動解消。新規4ファイルを追加。適用前の共有ファイルは `tmp/p7-transverse-ndu/integration/pre-apply/`。
- 共有での検証：JRSNAP/editor/CLI系 448 passed＋GUI/reporting/CLI 495 passed。失敗4件（test_editor_calculation の0720頁数4→3、test_reaction_cli 31→23頁×2、test_report_cli[parapet]）は統合前の共有コードでも同一に失敗し、並行中の帳票移行（flow描画）に起因する既存失敗。本件では変更していない。
- 共有コードで0720単独＋JRSNAPを生成し、NDU `16f2da64…` が隔離版probe候補と同一bytesであることを確認。
- 正式公開：前回0710と同様に隔離検証版 `p7-transverse-ndu-20261017` から `--stage 0720 --jrsnap --overwrite` で実V52受入を実行し、共有 `output/`・`post/` へ4件公開。receipt: `.agents/docs/research/p7-transverse-ndu-acceptance-20261017-final.json`（status=complete、解析未実行）。
  - `post/線路直角方向.ndu` 16f2da64…／`.ndu.provenance.json` b343fb4e…
  - `output/0720_線路直角方向荷重.pdf` 7bef9895…（4頁、旧版とbytes同一）／`.json` d11baf43…（入力世代10955ada…へ更新）
- 0710成果物・線路方向NDU・FrameWeb（線路直角方向.json等）は不変（更新時刻・SHA確認）。
- 未実施：別担当レビュー、all（20件）の正式受入、NDT出力・解析。
