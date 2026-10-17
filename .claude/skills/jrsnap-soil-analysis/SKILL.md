---
name: jrsnap-soil-analysis
description: JRSNAP Ver.5.3-L01体験版2のSOIL-JR.exeで既存の.sdtを計算し、基礎照査連携用.sdrと解析連携用.sdcを指定名で出力する。SOIL-JRの地盤反力特性計算と連携ファイル作成に使う。
---

# SOIL-JRでSDTを計算し、SDR・SDCを出力する

対象は `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\SOIL-JR.exe`。ソースは同じインストール先の `SOIL-JR\SOIL-JR.csproj` 以下にある。この版は `.sdt` をコマンドライン引数として受け取らない。[自動実行スクリプト](scripts/run-analysis.ps1)が、必要なライセンス引数で起動して画面から読込・計算・連携出力を行う。

## 自動実行

WebPier のルートから、次を実行する。`powershell.exe -STA` を使う。入力と出力は絶対パスに解決され、既存の SOIL-JR プロセスがある場合は別件への干渉を避けるため停止する。

```powershell
$folder = (Resolve-Path -LiteralPath 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2\01_サンプル(V53)：RC橋脚L：PHC').Path
$inputFile = Join-Path $folder 'RC橋脚（杭基礎）サンプルデータE.sdt'
$sdrFile = Join-Path $folder 'RC橋脚（杭基礎）サンプルデータS.sdr'
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File '.claude\skills\jrsnap-soil-analysis\scripts\run-analysis.ps1' `
  -InputPath $inputFile -SdrPath $sdrFile
```

スクリプトは計算完了メッセージと保存ダイアログを処理し、既存 SDR の上書き確認に応答する。実行後、SDR・SDC の更新時刻、サイズ、版情報、入力 SDT と一致するタイトルを確認する。入力 SDT は保存せずに SOIL-JR を閉じる。結果のパスとサイズが出力され、失敗時はエラーになる。

## 画面で実行する場合

1. 入力 `.sdt` の絶対パスと、出力の共通ベース名を確定する。既存の `.sdc`・`.sdr` がある場合は、両ファイルの更新時刻とハッシュを控える。SOIL-JR の既存プロセスがあれば、別件の作業中でないか確認してから対象ウィンドウを選ぶ。
2. 起動していなければ、PowerShell から以下のように起動する。作業ディレクトリはインストール先にする。引数の先頭の `LicenseOptNo` と末尾の `Ver.5.3-L00` を省かない。

   ```powershell
   $install = 'C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)'
   Start-Process -FilePath (Join-Path $install 'SOIL-JR.exe') `
     -ArgumentList 'LicenseOptNo111111199999999999999Ver.5.3-L00' `
     -WorkingDirectory $install
   ```

3. `地盤反力特性算定プログラム(Ver.5.3-L01体験版2)` の画面で **ファイル → 開く** を選び、入力 `.sdt` を開く。ウィンドウのタイトルに入力パスが表示され、データが読まれたことを確かめる。
4. **計算実行 → 計算実行** を選ぶ。入力エラーや「計算中にエラーが発生しました」が出た場合は止め、表示内容を報告する。入力 `.sdt` を修正して再試行することは別途依頼がある場合だけ行う。
5. **「計算が終了しました。連携ファイルを作成しますか？」** には **はい** を選ぶ。**「基礎照査連携用データの保存」** ダイアログで、希望する出力ベース名に `.sdr` を付けた絶対パスを指定する。既存ファイルへの上書きが依頼されている場合は上書き確認を進める。SOIL-JR は同じベース名の `.sdr` と `.sdc` を続けて書き出す。
6. 両方のファイルが存在し、サイズが正で、今回の実行後に更新されたことを確認する。先頭の `Ver.` と SDR のタイトル、SDC の `【バージョン情報】`・`【杭情報】` を読み、表示された入力のタイトルと一致するか確認する。既存ファイルが残っているだけの場合は成功としない。異常時は元ファイルを保持し、エラーと更新状況を報告する。

## Batch ワークスペースのサンプル

入力は `C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2\01_サンプル(V53)：RC橋脚L：PHC\RC橋脚（杭基礎）サンプルデータE.sdt`。保存ダイアログで `C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2\01_サンプル(V53)：RC橋脚L：PHC\RC橋脚（杭基礎）サンプルデータS.sdr` の**絶対パス**を指定する。対応する `RC橋脚（杭基礎）サンプルデータS.sdc` も同じフォルダーに生成される。入力の `E` と出力の `S` は異なるため、保存ダイアログの既定名をそのまま使わない。

## 根拠

- `Protect.cs` の `Protection` は `LicenseOptNo` と版番号を確認し、引数なしの直接起動を拒否する。
- `MDIfrmMain.cs` の `FileMenu` は、ファイルを開くときに `Common.DataFileRead`、計算時に `Calc.ResultFile` を呼ぶ。計算成功後の保存ダイアログで出力ベース名を決め、`Output.OutPut_Shousa` と `Output.OutPut_Renkei` を順に呼ぶ。
- `Output.cs` では `OutPut_Shousa` が `.sdr`、`OutPut_Renkei` が `.sdc` を出力ベース名に追加する。
