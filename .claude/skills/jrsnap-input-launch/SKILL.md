---
name: jrsnap-input-launch
description: この環境の JRSNAP Ver.5.3 または Ver.5.2 を選んで JRSNAP_Input.exe を起動・確認し、既存の .NDT を単一または複数で入力画面なしに解析実行する。JRSNAP Input の起動や解析の自動実行方法を調べるときに使用する。
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

`S_ANALYSIS.exe` のライセンス処理は引数の先頭 12 文字が `LicenseOptNo` であることを確認する。スクリプトは選択したバージョンの `start` コマンドの `%` を含めず、同じライセンス文字列をエンジンへ渡す。対応するインストール先は上記2件のみで、それ以外は実行前に拒否する。

根拠: `JRSNAP_Input/frmMain.cs` の解析実行は `mdlMenu.RunANALYSIS` に進み、`JRSNAP_Input/mdlMenu.cs` は単一を `intFlg=1`、複数を `intFlg=2` として制御ファイルを作り `S_ANALYSIS.exe` を起動する。インストール済み `S_ANALYSIS.exe` の入口は `.wk3` があればファイルを読んで解析に進む。エンジンの `mdlRenkei.RunANALYSIS2` は自動算定画面と基礎照査の起動確認を `NdataEx == 1` の場合に限定している。`.NDT` の生成は入力画面側の別処理なので、このスクリプトには含まれない。2026-10-11 に Ver.5.3 の Case1 単一と Case1・Case2 複数で全確認の自動処理、終了コード 0、各 `.OUT` と `.LOG` の更新、`work.wk3` の削除と `renzoku.flg` の復元を確認した。計算ログには高軸方向圧縮力を受ける要素の警告があるため、結果の技術的な妥当性はログと成果物で別途判断する。
