---
name: jrsnap-data-check
description: この環境の JRSNAP Ver.5.2-L03／Ver.5.3-L01体験版2 の「データ確認図」（S_DataCheck.exe）で、.ndu（の .ndt）から非線形番号図・断面番号図・要素関連データ一覧表・断面詳細図・節点ばね分布図などを画面操作なしで PDF にする。JRSNAPHeadless の runner の data-check、WebPier の 0710・0720 の計算書に差し込むページ（決定50）、S_DataCheck を補助 exe の中で動かす仕組み（ライセンス引数・アプリケーションドメイン・ComponentOne の PDF 出力）を扱う。図の追加や作画条件の変更、データ確認図のページが白紙・順序違い・失敗するとき、同じ方法で JRSNAP の別の帳票アプリ（S_LoadPicture など）を動かすときに使う。解析の実行には使わない。
---

# データ確認図（S_DataCheck.exe）を PDF にする

対象はインストール済みの `C:\RTRI_Program\JRSNAP(Ver5.2-L03)\S_DataCheck.exe`（AssemblyVersion 5.2.3.0）と `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_DataCheck.exe`（5.3.1.0）。5.3 の逆コンパイルしたソースは `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_DataCheck`（`mdlMain.cs` の読込と印刷、`frmSetPaper.cs` の作画条件、`frmPrint.cs` の対象図、`mdlMakePicture.cs` の作画）。5.2 のソースはない。

S_DataCheck は `.ndu` ではなく `.ndt`（解析用データ）を読む。`.ndt` の作り方は `../jrsnap-input-open-save/SKILL.md` の「解析用データ出力を画面なしで行う」を参照する。

## 使う：JRSNAPHeadless の data-check

実際に PDF が要るときは、`C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless` の runner を使う。使い方・失敗の種類は、その repo の `README.md` を正とする。runner は `.ndu` から `.ndt` を `run` と同じ書出しで一時フォルダーに作り（返さない）、図ごとに `<名前>.pdf` を `--figures` の順に返す。

```powershell
& 'C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless\bin\Release\JRSNAP.Headless.exe' data-check `
  --input 'C:\Users\sasai\Documents\structural-mcp\WebPier\post\線路方向.ndu' --output-dir 'C:\tmp\dc-out' `
  --figures 'nonlinear-numbers,section-numbers,element-table,section-detail,node-springs'
```

- 出力先は空か、ないフォルダーにする。
- 組合せは `--case <n>` で選ぶ（既定は 1）。
- 版は runner の横の `jrsnap-headless.json`（いまは 5.2-L03）で決まる。別の版で試すときは、`{"installDir": "C:\\RTRI_Program\\JRSNAP(Ver5.3-L01体験版2)"}` を書いた JSON を `--config <絶対パス>` で渡す。設定ファイルそのものは書き換えない。
- 返った PDF の中身は `pymupdf` などで開いて確かめる。ページのヘッダー `【Ver5.2-L03】<印刷日>『<.ndt の名前>/<タイトル>』` に印刷日が入るので、同じ入力でもバイト列は日ごとに変わる。ハッシュで比べない。
- S_DataCheck の画面は一瞬表示される。インストール先には何も書かない（`.ndt` の横に `.nd3` を書くが、一時フォルダーごと消える）。

| `--figures` の名前 | 作画条件設定（`frmSetPaper`）の作画帳票(軸線図) | 印刷実行（`frmPrint`）の対象図 |
|---|---|---|
| `nonlinear-numbers` | `_optJIKUSEN_3` 非線形番号図 | `_chkOutput_0` 軸線図 |
| `section-numbers` | `_optJIKUSEN_4` 断面番号図 | `_chkOutput_0` 軸線図 |
| `element-table` | `_optJIKUSEN_5` 要素関連データ一覧表 | `_chkOutput_0` 軸線図 |
| `section-detail` | （どれか1つは要る。`_optJIKUSEN_4`） | `_chkOutput_5` 断面詳細図 |
| `node-springs` | 同上 | `_chkOutput_2` 節点ばね分布図 |

まだ名前のない図（`_optJIKUSEN_1` 節点番号図・`_2` 要素番号図・`_6` 着目点一覧表、`_chkOutput_1` 要素ばね分布図・`_3`/`_4` 地盤抵抗分布図・`_6` 要素諸元一覧・`_7` 地盤変位図）を足すときは、runner の `DataCheckOptions.KnownFigures` と `src/DataCheck/DataCheck.cs` の `Figure.Known` の両方に足す。その入力で S_DataCheck が無効にする図を選ぶと、印刷実行で「対象図名が選択されていません」が出て `UNKNOWN_DIALOG` になる（例：杭のない直接基礎では地盤抵抗分布図が無効）。

作画条件は全図で同じ（A4縦、各番号図に寸法線あり、着目点なし、節点番号と要素番号は別の帳票、縮尺は自動、出力断面番号は全断面）。変えるときは `DataCheck.cs` の `Steer` で設定するコントロール（`optA4`・`optV`・`chkSunpo`・`chkTyakumoku`・`chkFlg`・`chkPrintPage`・`Text1`）を直す。

## WebPier での使われ方（決定50）

0710・0720 の計算書は、検討モデル（10.1・11.1）の後に、見出しも本文も付けずに上の5つの図を表の順で挟み、作用の計算（10.2・11.2）を新しいページから始める。見本は `.claude/docs/Example橋脚2/10_線路(耐震).pdf`・`11_直角(耐震).pdf` の 3〜7 ページ。見本の 1・2 ページ（節点番号図・要素番号図）は WebPier の骨組図と重なるので入れない。見本の右上の「10 - n」は計算書全体に後から付けた番号で、S_DataCheck は印刷しない。

- 呼び出しは `webpier/pipeline/jrsnap.py` の `draw_data_check`（図の順は `DATA_CHECK_FIGURES`、組合せは `DATA_CHECK_CASE = 1`）。返った PDF を図の順に1つにまとめる。
- 差し込みは `webpier/reporting/stages/data_check.py`（作用の見出しの前で文書を2つに分け、`assembly.render_with_pages` で挟む）。
- 段階の登録表の `StageSpec.data_check="jrsnap"` が、どの NDU から描くかを決める。NDU の付帯JSONの `data_check` に runner の版と報告を記録する。
- 0711・0721 を選ばない生成でも毎回描くので、0710・0720 を含む生成には `STRUCTURAL_MCP_JRSNAP_RUNNER` が必須。
- 番号図・断面・節点ばねは組合せで変わらないので、組合せ1の `.ndt` だけで描く（0720 は組合せが2つ）。runner が 0710 のために書く `.ndt` は、0711 の `post/線路方向_JRSNAP/` の `.ndt` と SHA256 が同じ。
- テストの代役は `tests/fixtures/jrsnap/fake_runner.py` の `data-check`。図ごとに `FAKE DATA CHECK <名前> <NDU の SHA256 の先頭16桁>` の1ページを返す。誤動作は `FAKE_JRSNAP_DATA_CHECK` で選ぶ（`FAKE_JRSNAP` は `run` だけに効く）。

## 仕組み（2026-10-18、5.2-L03・5.3-L01体験版2 で確認）

S_DataCheck には PDF の書出しがない。印刷（`mdlMain.mdl_MENU_FILE_PRINT_Click(1)`）は、`frmPrint` で選んだ図を `C1PrintDocument2` に組み立て、`PrintDialog` で選んだプリンターに送る。RTF 出力（`pFlg=2`）はあるが、PDF も「Docu-SE」連携（`.w02` などのテキスト）もない。

**ライセンス：** `MDmain.Main` → `Protect.Protection` は、JRSNAP のトップ画面が渡すライセンス引数を `Interaction.Command()`、つまり**プロセスのコマンドライン**から読む。末尾 11 文字が `Ver.<主>.<副>-L<FileBuildPart 2桁>` と一致しないと終了する。値は S_ANALYSIS と同じで、5.2-L03 は `LicenseOptNo111111199999999999999Ver.5.2-L03`、5.3-L01体験版2 は `…Ver.5.3-L00`（S_DataCheck 5.3 の FileVersion は 5.3.0.0）。引数がないと「直接起動は、できません」で終わる。ComponentOne（C1Report 4.5.2）の実行時ライセンスは、入口のアセンブリの埋込みライセンスで確かめる。

**動かし方（`JRSNAPHeadless\src\DataCheck\DataCheck.cs`）：** 補助の `JRSNAP.DataCheck.exe` をライセンス引数だけで起動し、依頼の JSON は標準入力で渡す。

1. `AppDomain.CreateDomain`（`ApplicationBase` はインストール先、構成は `S_DataCheck.exe.config`）の中で `ExecuteAssembly(S_DataCheck.exe)` する。これで S_DataCheck が入口のアセンブリになり、自身の保護処理と C1 のライセンスがそのまま効き、評価版の表示は出ない。版ごとの補助 exe も要らない。
   - 補助 exe の中で S_DataCheck の型を直接作ると、C1 のライセンスが補助 exe で確かめられ、保護処理も通らない。この方法は採らない。
2. 同じドメインに `MarshalByRefObject` の操縦役を作る。操縦役は `MdlGlobal.G_MainFrm` が表示され、非公開の `SystemFlg` が 1 になる（`frmMain_Activated` が引渡しデータを確かめ終えた）のを待ち、`BeginInvoke` で UI スレッドに入る。
3. 読込は、JRSNAP_Input.exe から引き渡されたデータと同じ経路で行う。`MdlWork.G_strFileName = <.ndt>`、`MdlGlobal.WorkFlg = 1` として `mdlMain.mdl_MENU_FILE_DATA()` を呼ぶ（終われば `WorkFlg = 0`）。
   - `mdl_GET_DATA` だけを呼ぶと、配列の準備（`Mdl_Get_TotalNum`・`SetRedimArray`）がなく `NullReferenceException` になる。
   - この経路は最後に作画条件設定（`frmSetPaper`）をモーダルで開く。
4. モーダルの画面には、UI スレッドの `System.Windows.Forms.Timer`（モーダルのメッセージループでも動く）から答える。
   - `Application.OpenForms` の `frmSetPaper`・`frmPrint` は、コントロールを名前（`Controls.Find`）で設定して `cmdOK.PerformClick()` する。
   - `#32770` の「印刷」（`PrintDialog`）には `IDCANCEL` を送る。取り消しても、`C1PrintDocument2.Generate()` は済んでいる。
   - それ以外の `#32770` は失敗として記録して閉じる。
   - 答えた窓は、閉じるまで次のタイマーでも見えるので、窓ごとに1回だけ答える。2回目を未知の画面と数えると「印刷: プリンター …」で失敗する（実際に起きた）。
5. `frmMain.C1PrintDocument2.Export("<名前>.pdf")`（ComponentOne の PDF 出力）で書く。プリンターは使わない。「Microsoft Print to PDF」でも出力できるが、スプールが非同期で、ファイルが遅れて現れる。
6. 終われば `G_MainFrm.Close()` で `ExecuteAssembly` が戻る。

**順序と図の数：** 1回の印刷の中の順序は S_DataCheck が決める（軸線図の帳票、要素ばね、節点ばね、地盤抵抗、断面詳細、要素諸元、地盤変位、着目点の順）。見本の順（断面詳細の後に節点ばね）にするには、図ごとに作画条件設定と印刷を1回ずつ行う。

**落とし穴：**
- 5.2-L03 は作画条件設定の「出力断面番号指定」（`Text1`）を空のまま開き、そのままでは `Mdl_YousoSitei` が0件になって、断面詳細図が白紙の1ページになる。`1-<MdlWork.G_intSectNum>` を入れる。5.3 は読込で `1-<断面数>` を入れる。
- 補助 exe を `CreateNoWindow` で起動すると、コンソールの入力の文字コードが UTF-8 にならない。日本語のパスを含む JSON は、`Console.OpenStandardInput()` を UTF-8 で読む。読まないと「無効な JSON プリミティブ」で失敗する。
- S_DataCheck は起動時に、インストール先の `nrflag.fil`（`frmMain_Activated`）と `*.wk0`（`frmMain_Shown`、サブフォルダーも探す）を開こうとする。JRSNAP_Input.exe からの引渡しが残っていれば別のデータを読むので、runner は `BUSY` で止める。
- `Application.StartupPath` は補助 exe のフォルダーになる。`Mdl_NM_Get_IniData` は `SekoJyoken` をそこの `INI\DataInputTool.ini` から読もうとするので、既定値（0）になる。ほかの INI はインストール先（`My.Application.Info.DirectoryPath`）から読む。
- 作図は、WebPier の骨組図と違って部材の外形の枠を描かない（見本 5.1 の図は外形の灰色の枠を描いていた）。違いは JRSNAP の版のもので、直さない。

**ほかの帳票アプリへの応用：** S_LoadPicture（荷重図、決定51）など、JRSNAP の帳票アプリは同じ `Protect.Protection` と C1 を持つ。そのため、同じ「ライセンス引数で補助 exe を起動し、2つ目のドメインで入口として実行し、UI スレッドから操縦して C1 の PDF 出力で書く」形がそのまま使える見込み。読込の経路と画面のコントロール名は、アプリごとに逆コンパイルのソースで確かめる。
