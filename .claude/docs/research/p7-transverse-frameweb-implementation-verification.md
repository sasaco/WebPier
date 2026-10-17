# P7 線路直角方向 FrameWeb 実装・検証記録

2026-10-16。[実装計画](../plans/p7-transverse-frameweb-input.md)に対する実装記録。
実装・独立レビュー・指定ソフト受入・回帰確認・通常0620経路による本番生成を完了した。

## 実装した経路

`--stage 0620` は通常の0620計算結果から、PDF・計算JSONと同時に
`./post/線路直角方向.json` と `線路直角方向.provenance.json` を生成する。
`--stage all` とGUIの全工程計算は、線路方向を含む12成果物を検証する。
表示する帳票は従来どおり4 PDF。カスタム出力先の場合はその配下の `post`、
`--post-dir` 指定時は指定先を使用する。

日常実行ではPDFを読み直さず、PDFに渡す正規0620結果から変換する。
PDF表示桁から数値を復元せず、元の数値精度を保持する。
Exampleの符号差・風モーメント端数差・風載荷区間差は既存調査文書に分離し、
P7の正規作用を優先した。計算式、入力条件、Example原本は変更しない。

実装箇所は `src/frameweb_export.py`、
`frameweb_transverse_cases.py`、`frameweb_artifacts.py`、
`artifact_publication.py`、`cli.py`、`editor_calculation.py`。
再生成方法と外部ソフトの制約は `./README.md` に記載した。

## 変換の確認結果

| 項目 | 確認結果 |
|---|---|
| 骨組 | 正規モデルの6節点・5部材・長短期2支持を保持 |
| 断面 | A=12.15 m²、直角Iz=20.50313 m⁴、E=26,500,000 kN/m² |
| 剛域 | Example互換の有限断面 A=Iz=1000 を明示 |
| 符号 | tx=H、ty=−N、rz=−M。分布はglobal gx/gy |
| 基本作用 | 17基本を保持し、零行だけ省略 |
| L/I | 正規resolved値から同じ線・用途のL+I補助5件を構成 |
| native件数 | 22 load、19 Define、16 Combine、8 Pickup |
| 組合せ | 名目240係数を追跡、合法37状態。単線L/Iの異なる線の混合を禁止 |
| D1分布 | 基本q297.68×1.1=327.448を維持。327.45に再丸めしない |
| native形式 | 既知9トップレベルキーのみ。結果キャッシュ・独自metadataなし |
| 出典 | 付帯JSONへ正規source path、用途・線・係数適用・補助・参照・SHAを保存 |

補助ケースは、終局最大複線1975.64、終局一般複線1800.07、
使用性複線1380.07、使用性単線上下それぞれN695.89・M±1482.81。
基本IへPDFの名目係数を再乗算せず、正規結果の用途別丸めを保存する。

## 指定FEMPythonによる独立受入

使用した外部ソフトは `C:/Users/sasai/Documents/structural-mcp/FEMPython/`。
既存 `FrameWebforCS/Headless/bin/Release/net10.0-windows/FrameWebforCS.Headless.exe`
を使用し、外部ソフトを改修・再ビルドしていない。

- ソースHEAD: `7488c8fb4d6c100438a9691747ceb11fd9e66358`（clean）。
- runner engineVersion: `1.0.0+018d0d0ee9453464b0b541a5344ce5a6c0acdfc6`。
- runner exe SHA-256: `474bc1bc9da6dd5cda466f815753cbb61cdfc53c11473106e5d94e994eff0247`。
- 受入native SHA-256: `b692a9ec5157af8daf0000bd31e70085b2fe697140515e3765322dde1f769dba`。

実装担当とは別の担当が、exporterと外部解析コードをimportしない
3自由度Euler–Bernoulli骨組・ばねの計算を作成し、閉形式4条件で自身の実装を確認した。
その独立計算と指定runnerの全基本・補助、各支持条件、37状態、16 Combine、8 Pickupを比較した。

**36,318数値比較、5,544選択元・相関した全成分ベクトルの比較がPASS。**
力・モーメント最大差は `2.058004611171782e-8`、変位・回転最大差は
`1.51311255192077e-15`。計画の許容差を変更していない。
resolved L/Iを別々に解析した和と補助ケース応答も確認した。
9種類の故障注入を検出し、剛域断面10倍の感度診断も記録した（正式値は維持）。

GUI互換は、既存FrameWebforCS.dllの実data serviceに対して
`JsonDataOpen → GetSaveJson / CaptureCalculationSnapshotJson` を実行して確認した。
型別の独立Q変換 `DoubleParse(JsonSerialize(SingleParse(v)))` と意味が一致し、
GUI保存値と独立Q変換値の再解析結果JSON全体が一致した。
元nativeから22数値が変化し、ほぼ零の同値極値で24選択元が変わることも記録した。
正式nativeをSingleへ丸めていない。これは実data serviceの検証であり、
外部ソフトのウィンドウ・ファイルダイアログの手動操作試験ではない。

詳細証跡は `tmp/p7-transverse-frameweb-implementation/acceptance/` の
`acceptance-report.md`、`run-01/acceptance.json`、`review.md`、`review-checks.json`、`manifest.json`。

## レビューで修正した条件

独立レビューで見つかったHigh 1件とMedium 1件は、再現モデルと回帰試験を追加して修正した。
修正後のレビューに未解決のMedium以上はない。

最終共通exporterのSHAは `ef3d01e0a6b3a5f5d18440311843af23a48f8672c0ab47f81aedea09bcc67e3a`。
初回レビュー後の差分は、並行する0610側の名目係数0に対する厳密零検査2箇所のみ。
この2箇所を旧形へ戻したメモリ上のbytesが初回レビューSHAと一致することを独立確認した。
0620部分は不変であり、現コードで37状態・受入候補一致・零候補/投影拒否を再確認した。
追加監査は `acceptance/review-final-delta.json`、製品ファイルと外部ソフトの最終SHAは
更新された `acceptance/manifest.json` に保存している。

1. 使用中Defineの零候補と非零候補の混在は、外部runnerが零候補を落として
   正常終了するため、公開前に拒否する。荷重N=0でもM非零の偶力は零候補ではない。
2. 有効荷重がないCombineをPickupが参照する場合は、外部runnerで利用不能となるため
   load→Define→Combine→Pickupの参照を辿って公開前に拒否する。
   使用性係数0や全列車分担率0が該当する。未使用の零ケースや、非零作用に加わる零成分は許容する。
3. 部材荷重の2桁投影で正規作用が許容差を超えて変わる入力や、非零が零になる入力を拒否する。
   例: 2.625→2.63。架空の微小荷重や許容差の拡大では回避しない。

これらは将来の入力変更時にも適用する互換上の制約。
現在のP7入力は全条件を満たし、拒否条件の追加前後で受入nativeのbytesは変わらない。

## 公開処理・統合の確認

親ディレクトリごとのstaging/backup、旧版復元、最終検証までのbackup保持を実装した。
schema2 sidecarのpublication ID、全非sidecar成果物のパス/SHA、必要sidecar集合を照合する。
通常例外は復元し、強制停止や復元不能時はjournalと `publication-pending` を検出して
未検証の世代を成功扱いしない。複数ファイルのOSレベル同時原子性や自動復旧は保証しない。

ルート担当の通常CLI allを独立した一時出力先で実行し、12成果物・共通publication ID・
10非sidecarのSHAを確認した。直角nativeは受入候補とbytes一致。
既存8帳票のうち7件はbytes一致。0610 PDFだけ作成時刻metadataが変わったが、
全8ページの抽出文字と描画pixelsは一致した。
CLI 0620・CLI all・実CalculationControllerのall再計算で直角nativeが一致することも試験した。

公開処理の独立レビューは未解決High/Medium/Lowなし。
証跡は `tmp/p7-transverse-frameweb-implementation/publication-review/`、
通常all照合は `root-integration/verification.json`。

## 回帰試験・納品

関連329試験PASS、Tkを使う3試験のみ別プロセス実行へ分離したカバレッジは95%
（基準85%、6対象module、1251行中1184行を実行）。
ログは `./.agents/logs/transverse-frameweb-root-coverage-nontk.log`。

初回 `.agents/check.ps1` の全体ゲートはTk初期化/イベント処理の待ち時間を調べて中断した。
停止した実行を全体ゲートPASSとして数えない。全nodeの収集結果に基づく非Tk3144件は
3139 PASS・5失敗となり、5件とも古い統合試験入力のq2.625が新しい投影検査で拒否される条件だった。
`test_report_cli.py` の0500確認2件は対象工程を明示し、全工程確認3件はコピー入力に
B6=1.76、両側先頭2支承のL2=0.5を注記付きで設定した。
元fixtureと数値oracleを変更せず、形状3ケースの節点・接続・偏心等の検証を維持し、
変更したbody断面だけ独立算定した期待値（A11.44、Iz2.95305/40.27833）を使用した。
修正後の同ファイル11件すべてPASS、ID/件数不変。追加の独立レビューもPASS。
したがって非Tk全3144件の最終assertionは、初回と修正対象11件の再実行で確認済み。
旧入力の拒否・旧成果物保持試験も残している。

Tkは新しいPythonプロセス、SHA照合したローカルコピーでも21件PASSを確認した。
線路方向担当の全体ゲートが同時進行していることを確認後、フォーカスやクリップボードの
干渉を避けるため分離実行を安全停止した。停止済み実行に未実行220件のPASSを含めない。
共有全体ゲート `tmp/quality-gates/pytest-20261016-203051-6855558.log` は完了し、
**3379 PASS・5 FAIL・1 SKIP、2130.46秒**だった。この単一コマンドをPASSとは記録しない。
5 FAILは収集時に読み込んだ旧 `test_report_cli.py` の本体であり、修正後の11件PASSで確認した。
1 SKIPはTkライブラリ読込みによる既存画面試験で、同じnodeの新規プロセス実行にて
setup/call/teardownがすべてPASSしている。

全収集node IDと全体ログを突き合わせ、修正対象の再実行・Tk個別実行を根拠付きで結合した結果、
**全3385件に最終PASSの証跡があり、未実行・未解決失敗・未解決skipは0件**。
修正は統合試験入力に限定し、製品コードを変更した後の結果を古い試験結果で代用していない。
各nodeと根拠ログの対応、元のFAIL/SKIP、ログSHAを
`tmp/p7-transverse-frameweb-implementation/final-suite-results.json` に保存した。

通常の納品コマンド:

```powershell
uv run --project . --locked python -X utf8 ./run_design.py --stage 0620 --overwrite
```

exit0、publication ID `811e843be7d04b9f89f496871a0a93dd`。
生成後、独立したSHA・宣言集合・方向・入力世代確認と製品validatorの両方を通した。

| 本番成果物 | SHA-256 |
|---|---|
| `./post/線路直角方向.json` | `b692a9ec5157af8daf0000bd31e70085b2fe697140515e3765322dde1f769dba` |
| `./post/線路直角方向.provenance.json` | `dbbaf75326610adcc5a4d30fc93ae3e4faf271001da515ce3462b788c5db3ce8` |
| `./output/0620_直角方向荷重.pdf` | `64a5ac2380530b4fb1996889b11a375a31fc7b6821669731d022eba1fff3140a` |
| `./output/0620_直角方向荷重.json` | `07f76b318c482d92353a6b037c2bb522fbcdb44158a513322066cbbbe49a2bca` |

nativeは指定runnerの受入候補とbytes一致（18,744 bytes）。
0620 PDF・計算JSONは開始時とbytes一致。
入力・Example原本と、本番生成直前の他stage6帳票・線路方向post2件のSHAはすべて不変。
一時公開ディレクトリの残留なし。証跡と直前バックアップは
`tmp/p7-transverse-frameweb-implementation/production/verification.json` と `production/before/`。

この検証は入力変換・ソフト互換・出力管理の確認であり、橋脚の構造安全性照査の完了を意味しない。
