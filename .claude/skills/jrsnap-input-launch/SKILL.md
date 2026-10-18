---
name: jrsnap-input-launch
description: この環境の JRSNAP Ver.5.3 または Ver.5.2 を選んで JRSNAP_Input.exe を起動・確認し、既存の .NDT を単一または複数で入力画面なしに解析実行する。.ndu から .ndt の作成と解析までを画面なしで行う JRSNAPHeadless の runner への案内と、解析エンジンの画面・結果ファイルの性質も含む。JRSNAP Input の起動や解析の自動実行方法を調べるときに使用する。
---

# JRSNAP Input の起動

スキルは WebPier の `.claude\skills\jrsnap-input-launch` に置く。実行ファイルと解析用制御ファイルは選択した JRSNAP のインストール先に置く。既定は `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)`、Ver.5.2 を指定するときは `C:\RTRI_Program\JRSNAP(Ver5.2-L03)` を使う。スキルの配置場所からインストール先を推定しない。

入力画面の起動は、選択したバージョンに対応する次の **コマンドプロンプト（cmd.exe）用**の一行を使う。

```bat
rem 既定: Ver.5.3
start "" "C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\JRSNAP_Input.exe" %LicenseOptNo111111199999999999999Ver.5.3-L00
rem Ver.5.2 を指定するとき
start "" "C:\RTRI_Program\JRSNAP(Ver5.2-L03)\JRSNAP_Input.exe" %LicenseOptNo111111199999999999999Ver.5.2-L03
```

- PowerShell からは選択した行を `cmd.exe /d /c 'start "" "...\JRSNAP_Input.exe" %LicenseOptNo...'` として実行する。`start` を PowerShell の別名として実行しない。
- 引数は先頭に `%` があり、末尾に `%` はない。各バージョンの `.bat` に記載された文字列をそのまま渡す。
- 起動前に選択したインストール先の `JRSNAP_Input.exe` プロセスを確認する。既に開いている場合、重複起動が必要な依頼でなければそのウィンドウを使用する。
- 起動後はプロセスの `ExecutablePath` が選択したインストール先を指し、`CommandLine` に対応する引数が含まれること、および `MainWindowTitle` が空でなく `Responding` が `True` であることを確認する。これらは起動確認であり、アプリ内の計算やファイル操作の成功までは示さない。

2026-10-11 に両バージョンの `.bat` から起動したプロセスと応答中のウィンドウを確認した。

## 入力画面を起動せずに解析する

既存の `.NDT` がある場合、[scripts/run-analysis.ps1](scripts/run-analysis.ps1) で `JRSNAP_Input.exe` を起動せずに `S_ANALYSIS.exe` の単一または複数解析経路を使用できる。`-InstallDir` を省略すると Ver.5.3、Ver.5.2 で実行するときは `-InstallDir 'C:\RTRI_Program\JRSNAP(Ver5.2-L03)'` を指定する。スクリプトは選択したインストール先に対応するライセンス引数を渡す。最初は `-NdtPath <ファイル>` だけで事前確認し、実行するときに `-Execute` を加える。複数解析は同じフォルダーの異なる `.NDT` を2件以上指定する。スクリプトは件数に応じた `work.wk3` と `renzoku.flg` をインストール先に用意して解析エンジンを起動する。共用の作業ファイルを使うため、同じインストール先の関連アプリが起動中なら実行を拒否する。

以下の例は WebPier のルートから実行する。サンプルデータは `C:\Users\sasai\Documents\Batch\Batchテスト` にある。

```powershell
& '.claude\skills\jrsnap-input-launch\scripts\run-analysis.ps1' -NdtPath 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2\01_サンプル(V53)：RC橋脚L：PHC\01_サンプル(V53)：RC橋脚L(Case1_ρm10_αf1_正向).ndt'
& '.claude\skills\jrsnap-input-launch\scripts\run-analysis.ps1' -NdtPath 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2\01_サンプル(V53)：RC橋脚L：PHC\01_サンプル(V53)：RC橋脚L(Case1_ρm10_αf1_正向).ndt' -Execute -TimeoutSeconds 300
& '.claude\skills\jrsnap-input-launch\scripts\run-analysis.ps1' -NdtPath 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.2-L03\04_参考(V52)：RC橋脚L\01_サンプル(V52)：RC橋脚L(Case1_ρm10_αf1_正向).ndt' -InstallDir 'C:\RTRI_Program\JRSNAP(Ver5.2-L03)'
& '.claude\skills\jrsnap-input-launch\scripts\run-analysis.ps1' -NdtPath 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.2-L03\04_参考(V52)：RC橋脚L\01_サンプル(V52)：RC橋脚L(Case1_ρm10_αf1_正向).ndt' -InstallDir 'C:\RTRI_Program\JRSNAP(Ver5.2-L03)' -Execute -TimeoutSeconds 300
& '.claude\skills\jrsnap-input-launch\scripts\run-analysis.ps1' -NdtPath 'C:\path\to\case1.ndt', 'C:\path\to\case2.ndt' -Execute -TimeoutSeconds 300
```

`-Execute` はエンジンの既知の確認も自動で進める。単一解析では、`Nrail.exe` のコンソールに「エンターキーを押して画面を閉じて下さい」が出たときだけ Enter を送り、「耐力と変形性能の自動算定」では画面の初期チェック状態のまま「実行」を押し、「基礎照査機能を起動しますか？」には「いいえ」を選ぶ。後者の基礎照査機能まで必要な依頼にはこのスクリプトをそのまま使わない。複数解析の実機試験では途中の2種類の確認は出ず、最後の「解析が全て終了しました。」だけを自動で閉じた。エラーがあるという完了通知ならスクリプトは失敗として報告する。`S_ANALYSIS.exe` の画面は表示されるため、これは非対話の自動操作であり、エンジン自体の headless モードではない。未知の確認画面では自動選択せず、タイムアウト時は起動中のエンジンと制御ファイルを残す。

「基礎照査機能」は `S_SubstCheck.exe`（増分解析は `E_SubstCheck.exe`）で、直接基礎の照査値 `<DB1名>_Output_Chokukiso.csv`、算定値 `_Output_PIC.csv`、判定 `_直接基礎照査No1.csv` を結果の横に書く（2026-10-18、両 exe の文字列で確認）。NDU に直接基礎の照査のデータ（`ChokuKisoNum`・`CHOKU_KISO`・`CHOKU_KISO_Link`）がなければ確認自体が出ない。WebPier の NDU はこのデータを持たないので、この CSV はできない。Aggre-SE が `_Output_Chokukiso.csv` を読む関係は [aggrese-project](../aggrese-project/SKILL.md) を参照。

`S_ANALYSIS.exe` のライセンス処理は引数の先頭 12 文字が `LicenseOptNo` であることを確認する。スクリプトは選択したバージョンの `start` コマンドの `%` を含めず、同じライセンス文字列をエンジンへ渡す。対応するインストール先は上記2件のみで、それ以外は実行前に拒否する。

根拠: `JRSNAP_Input/frmMain.cs` の解析実行は `mdlMenu.RunANALYSIS` に進み、`JRSNAP_Input/mdlMenu.cs` は単一を `intFlg=1`、複数を `intFlg=2` として制御ファイルを作り `S_ANALYSIS.exe` を起動する。インストール済み `S_ANALYSIS.exe` の入口は `.wk3` があればファイルを読んで解析に進む。エンジンの `mdlRenkei.RunANALYSIS2` は自動算定画面と基礎照査の起動確認を `NdataEx == 1` の場合に限定している。`.NDT` の生成は入力画面側の別処理なので、このスクリプトには含まれない。2026-10-11 に Ver.5.3 の Case1 単一と Case1・Case2 複数で全確認の自動処理、終了コード 0、各 `.OUT` と `.LOG` の更新、`work.wk3` の削除と `renzoku.flg` の復元を確認した。計算ログには高軸方向圧縮力を受ける要素の警告があるため、結果の技術的な妥当性はログと成果物で別途判断する。

## .ndu から解析まで画面なしで行う（JRSNAPHeadless）

`.ndt` がなく `.ndu` だけがあるとき、または結果を protocol v1 の envelope で受け取りたいときは、`C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless` の runner `bin\Release\JRSNAP.Headless.exe` を使う。使い方・失敗の種類・成果物は、その repo の `README.md` を正とする（ローカルの git だけで、リモートとサブモジュールはまだない）。WebPier の 0711・0721 はこの runner を `STRUCTURAL_MCP_JRSNAP_RUNNER` から呼ぶ（決定47、ADR-0007）。

- `.ndt` は「解析用データ出力」と同じ処理（`mdlDATA_NDT.mdl_Wrt_NDTDataFile`）を直接呼んで作る。全組合せを画面と同じ名前で出し、画面が書出しの前に MsgBox で行う入力検査は通らない。仕組みは `../jrsnap-input-open-save/SKILL.md` の「解析用データ出力を画面なしで行う」を参照する。
- `--analyze false` は `.ndt` を作るだけで、インストール先に何も書かない。画面で出力した `.ndt` との突き合わせに使う。
- 解析の自動応答は `run-analysis.ps1` と同じ。違いは、タイムアウトや未知の確認（標準のメッセージボックス、または基礎照査以外の「解析機能」の窓が約3秒続く）のとき、`S_ANALYSIS.exe` とその子プロセスを終了させ、`renzoku.flg`・`nrwork.dir` を元のバイト列に戻すこと。`run-analysis.ps1` はタイムアウト時に残す。
- インストール先は runner の横の `jrsnap-headless.json`（`{"installDir": ...}`）で決め、版は `JRSNAP_Input.exe` の AssemblyVersion で判定する。同じインストール先の解析は `Global\structural-mcp-jrsnap` の mutex と起動中のプロセスの検査で直列にする。
- `figures` は、同じ書出しの `.ndt` から、計算書に差し込むページを PDF にする（WebPier の 0710・0720 の計算書）。解析はしない。
  - `--data-check`：「データ確認図」（`S_DataCheck.exe`）の図を図ごとに PDF にする（決定50）。詳しくは `../jrsnap-data-check/SKILL.md`。
  - `--load-diagram`：「荷重図」（`S_LoadPicture.exe`）を組合せごとに PDF にする（決定51、5.2-L03 だけ）。詳しくは `../jrsnap-load-diagram/SKILL.md`。
  - インストール先に書かないので、mutex は取らない。
  - 2026-10-18 に古い `data-check` から置き換えた（JRSNAPHeadless 2374a5b）。`bin\Release` も 2026-10-18 に作り直した。

## 解析エンジンの画面と結果ファイル（2026-10-18 確認）

- `S_ANALYSIS.exe` の窓（「解析結果の保管中・・・」「耐力と変形性能の自動算定」「Vepp（耐力・変形性能算定）」「解析状況」「解析機能」）は WinForms（クラス `WindowsForms10.Window.8.app...`）で、`#32770` ではない。標準のメッセージボックスは、複数解析の完了通知「解析が全て終了しました。」（題名 `解析実行`）で、5.2・5.3 とも同じ。
- 自動算定の窓のチェックボックスは `BM_GETCHECK` に答えない。状態を読むには UI Automation の `TogglePattern` を使う。初期状態では「ＲＣ・ＰＨＣ部材」だけがオン。
- 複数解析では、5.2-L03 でも 5.3 と同じく「Vepp」「解析状況」の窓と完了通知だけが出て、自動算定と基礎照査の確認は出なかった。結果の横に 0 バイトの `解析実行Err.log` もできる。
- `.OUT`・`.DSP`・`.KG*`・`.R10` など結果ファイルの多くは暗号化された zip（先頭が `PK`）で、同じ入力でも毎回バイト列が変わる。結果の同一性をハッシュで比べない。
- `S_ANALYSIS.exe` は実行のたびにインストール先の共用ファイル（`danmen.fil`・`nrwork.dir`・`JikuFact.INI`・`exit_flg*.out` など）を書き換える。同じインストール先では解析を同時に走らせない。
- 組合せごとの `.ndt` では、その組合せが使わない基本ケースの荷重が 0 になる（例：WebPier 0720 の Case1 の `.ndt` は CASE-6 下り線が 0）。基本ケースごとの荷重を `.ndt` から読むときは、そのケースを使う組合せの `.ndt` を選ぶ（決定51）。
