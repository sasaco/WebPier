---
name: jrsnap-input-open-save
description: この環境のJRSNAP V5.2-L03／V5.3-L01体験版2で既存の .ndu を開き、版別に保存して結果を確認する。NDUの版互換性確認や旧版サンプルの保存にも使う。解析結果の再計算だけには使わない。
---

# JRSNAP InputでNDUを開いて保存する

対象は `C:\RTRI_Program\JRSNAP(Ver5.2-L03).bat` と `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2).bat`。起動引数と解析実行は `../jrsnap-input-launch/SKILL.md` を参照する。二重起動は本体の `MDmain.PrevInstance` が拒否するため、版を切り替えるときは前のJRSNAPを閉じる。

## 操作

1. 保存先の複製 `.ndu` を選ぶ。原本への保存を避けるため、開く前に絶対パスを確認する。`scripts/check-ndu-header.ps1 -Path <ファイルまたはフォルダー> -Version V52|V53` で形式番号の読込可否を調べる。これはヘッダー検査であり、全入力項目の互換性保証ではない。
2. 対応する起動バッチでJRSNAPを起動する。`ファイル > 開く(&O)` で `.ndu` を選ぶ。読込に成功するとウィンドウのタイトルに開いたファイルのパスが入り、`mdlMenu.mnuFileOpen` は `WG_bytSystemDataFlg=3` にする。警告・読込失敗が出たファイルは保存しない。
3. `ファイル > 上書き保存(&S)` を使う。別名が必要なら `名前を付けて保存(&A)` を使う。`mdlMenu.mnuFileSave` は `mdlDataFile.mdl_Wrt_NDUDataFile` で現在の `.ndu` を書く。保存の成功表示に加え、対象ファイルの更新時刻、先頭行の `Virsion=`、必要な入力項目を確認し、同じ版で再読込できるか確認する。複数ファイルでは各ファイルの成功・失敗を個別に記録する。

`開く` と `上書き保存` は `.ndu` の操作である。`.ndt` は別の「解析用データ出力」で生成し、`.OUT` などの計算結果は解析実行で更新する。`.ndu` を保存しただけで、複製済みの計算結果をその版の結果として扱わない。

## 画面操作できない環境での一括保存

`scripts/save-ndu.ps1` はインストール済みの各 `JRSNAP_Input.exe` を読み込み、画面の「開く」「上書き保存」が使う `mdl_Get_NDUDataFile` と `mdl_Wrt_NDUDataFile` を呼ぶ。JRSNAPの入力機能を初期化してから各 `.ndu` を一時領域で読込・保存し、保存済みファイルの再読込・再保存がバイト単位で安定することを検査する。`-Execute` を付けない実行は検査だけで対象を更新しない。画面や起動バッチを実際に操作した記録ではない。

```powershell
& '.claude\skills\jrsnap-input-open-save\scripts\save-ndu.ps1' -Path 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.3-L01体験版2' -Version V53
& '.claude\skills\jrsnap-input-open-save\scripts\save-ndu.ps1' -Path 'C:\Users\sasai\Documents\Batch\Batchテスト\JRSNAP_Ver5.2-L03' -Version V52 -ConvertS6
```

結果の `BeforeHeader`、`AfterHeader`、`ConvertedS6`、`BodyChangedLines`、`Written` を確認する。対象の複製フォルダーを指定し、検査が全件通った後で、同じコマンドに `-Execute` を付けて反映する。保存対象は `.ndu` だけで、解析用データ出力と再計算は別作業になる。

## この2版の形式制限

インストール済み本体の `mdlDataFile.VerCommonNo` を確認した結果、V5.2-L03は読込形式番号が最大 `S.5`、V5.3-L01体験版2は最大 `S.6`。超過時は `mdl_Get_NDUDataFile` が200を返して読込を拒否する。`Virsion=5.3.1.S.6` の `.ndu` はV5.2-L03でそのまま開けない。ヘッダーだけを下げて実作業に使わない。

`-ConvertS6` は対象の原ファイルを直接書き換えず、一時コピーの先頭行だけ `S.6` から `S.5` にしてV5.2本体で読込・保存する。その結果を、同じ原ファイルをV5.3本体で保存した結果と比較し、先頭行以外の全行が一致する場合だけ反映を許す。2026-10-11の対象6件では全件一致し、V5.2・V5.3の保存結果は各11件とも再保存時にバイト単位で一致した。直接基礎3件では両版で同じ1～2行が正規化される。この検証は今回の入力ファイルに限定され、計算結果や工学的な同等性までは確認しない。別のS.6ファイルへ機械的に適用する前に差分を再検査する。

根拠: V5.3本体の `JRSNAP_Input\frmMain.cs` のメニュー表示、`JRSNAP_Input\mdlMenu.cs` の `mnuFileOpen`／`mnuFileSave`／解析用データ出力、`JRSNAP_Input\mdlDataFile.cs` の読込・保存・形式番号判定。V5.2/V5.3の形式上限と変換差分はインストール済み本体を一時ファイルで検証した。
