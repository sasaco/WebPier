---
name: jrsnap-data-check
description: この環境の JRSNAP Ver.5.2-L03／Ver.5.3-L01体験版2 の「データ確認図」（S_DataCheck.exe）で、.ndu（の .ndt）から非線形番号図・断面番号図・要素関連データ一覧表・断面詳細図・節点ばね分布図などを画面操作なしで PDF にする。JRSNAPHeadless の runner の figures --data-check、WebPier の 0710・0720 の計算書に差し込むページ（決定50）、JRSNAP の帳票アプリを補助 exe の中で動かす共通の仕組み（src/ReportHost：ライセンス引数・アプリケーションドメイン・UI スレッドの操縦・ComponentOne の PDF 出力・TEMP の切り分け・終わり方）を扱う。図の追加や作画条件の変更、データ確認図のページが白紙・順序違い・失敗するとき、補助が答えを返さない・終了コードがおかしいとき、JRSNAP の別の帳票アプリを同じ方法で動かすときに使う。荷重図（S_LoadPicture）に固有のことは jrsnap-load-diagram。解析の実行には使わない。
---

# データ確認図（S_DataCheck.exe）を PDF にする

対象はインストール済みの `C:\RTRI_Program\JRSNAP(Ver5.2-L03)\S_DataCheck.exe`（AssemblyVersion 5.2.3.0）と `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_DataCheck.exe`（5.3.1.0）。5.3 の逆コンパイルしたソースは `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_DataCheck` にある。
- `mdlMain.cs`：読込と印刷
- `frmSetPaper.cs`：作画条件
- `frmPrint.cs`：対象図
- `mdlMakePicture.cs`：作画

5.2 のソースはない。5.2 と比べるときは IL を見る（`../jrsnap-load-diagram/SKILL.md` の「5.2 を IL で確かめる」）。

S_DataCheck は `.ndu` ではなく `.ndt`（解析用データ）を読む。`.ndt` の作り方は `../jrsnap-input-open-save/SKILL.md` の「解析用データ出力を画面なしで行う」を参照する。

## 使う：JRSNAPHeadless の figures

実際に PDF が要るときは、`C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless` の runner を使う。使い方・成果物・失敗の種類は、その repo の `README.md` を正とする。runner の動きは次のとおり。
- `.ndu` から `.ndt` を `run` と同じ書出しで作業フォルダーに作る（`.ndt` は返さない）。
- 図ごとに `<名前>.pdf`（kind `data-check`）を、`--data-check` の順に返す。
- 荷重図を一緒に頼むときは `--load-diagram` も付ける（`../jrsnap-load-diagram/SKILL.md`）。

```powershell
& 'C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless\bin\Release\JRSNAP.Headless.exe' figures `
  --input 'C:\Users\sasai\Documents\structural-mcp\WebPier\post\線路方向.ndu' --output-dir 'C:\tmp\fig-out' `
  --data-check 'nonlinear-numbers,section-numbers,element-table,section-detail,node-springs'
```

`bin\Release` は 2026-10-18 に `figures` で作り直した（WebPier が `figures` に切り替えたのと同時）。

- 出力先は空か、ないフォルダーにする。
- 組合せは `--data-check-combination <n>` で選ぶ（既定は 1）。用語は CONTEXT.md に合わせ、「組合せ」と「基本ケース（CASE-n）」を混ぜない。
- `--timeout-seconds` はコマンド全体の時間（既定 600）。
- 版は runner の横の `jrsnap-headless.json`（いまは 5.2-L03）で決まる。別の版で試すときは、`{"installDir": "C:\\RTRI_Program\\JRSNAP(Ver5.3-L01体験版2)"}` を書いた JSON を `--config <絶対パス>` で渡す。設定ファイルそのものは書き換えない。
- 返った PDF の中身は `pypdfium2`（`uv run --no-project --with pypdfium2 --with pillow python -X utf8 …`）などで開いて確かめる。
  - ページのヘッダー `【Ver5.2-L03】<印刷日>『<.ndt の名前>/<データ名>』` に印刷日が入る。同じ入力でもバイト列は日ごとに変わるので、ハッシュで比べない。
  - 比べるときは、同じ日に出したものを PNG にして画素で比べる。
- S_DataCheck の画面は一瞬表示される。インストール先には何も書かない（`.ndt` の横に `.nd3` を書くが、作業フォルダーごと消える）。

| `--data-check` の名前 | 作画条件設定（`frmSetPaper`）の作画帳票(軸線図) | 印刷実行（`frmPrint`）の対象図 |
|---|---|---|
| `nonlinear-numbers` | `_optJIKUSEN_3` 非線形番号図 | `_chkOutput_0` 軸線図 |
| `section-numbers` | `_optJIKUSEN_4` 断面番号図 | `_chkOutput_0` 軸線図 |
| `element-table` | `_optJIKUSEN_5` 要素関連データ一覧表 | `_chkOutput_0` 軸線図 |
| `section-detail` | （どれか1つは要る。`_optJIKUSEN_4`） | `_chkOutput_5` 断面詳細図 |
| `node-springs` | 同上 | `_chkOutput_2` 節点ばね分布図 |

**まだ名前のない図を足すとき：** 次の図がまだ名前を持たない。
- `_optJIKUSEN_1` 節点番号図、`_2` 要素番号図、`_6` 着目点一覧表
- `_chkOutput_1` 要素ばね分布図、`_3`/`_4` 地盤抵抗分布図、`_6` 要素諸元一覧、`_7` 地盤変位図

足すときは、runner の `FiguresOptions.KnownFigures`（`src/JRSNAP.Headless/RunOptions.cs`）と、`src/DataCheck/DataCheck.cs` の `Figure.Known` の両方に足す。その入力で S_DataCheck が無効にする図を選ぶと、印刷実行で「対象図名が選択されていません」が出て `UNKNOWN_DIALOG` になる（例：杭のない直接基礎では地盤抵抗分布図が無効）。

**作画条件：** 全図で同じ（A4縦、各番号図に寸法線あり、着目点なし、節点番号と要素番号は別の帳票、縮尺は自動、出力断面番号は全断面）。変えるときは、`DataCheck.cs` の `Steer` で設定するコントロール（`optA4`・`optV`・`chkSunpo`・`chkTyakumoku`・`chkFlg`・`chkPrintPage`・`Text1`）を直す。

**ヘッダー：** 項目は荷重図と共通に固定する（`Pilot.FixHeader`。版・日付・ファイル名・データ名を表示、データタイトルなし、右揃え）。インストール先の `ini\DataInputTool.ini [Header]` にはよらない。

## WebPier での使われ方（決定50）

0710・0720 の計算書は、検討モデル（10.1・11.1）の後に、見出しも本文も付けずに上の5つの図を表の順で挟み、作用の計算（10.2・11.2）を新しいページから始める。
- 見本は `.claude/docs/Example橋脚2/10_線路(耐震).pdf`・`11_直角(耐震).pdf` の 3〜7 ページ。
- 見本の 1・2 ページ（節点番号図・要素番号図）は、WebPier の骨組図と重なるので入れない。
- 見本の右上の「10 - n」は、計算書全体に後から付けた番号で、S_DataCheck は印刷しない。

いまの WebPier の実装（決定50・51）：
- 呼び出しは `webpier/pipeline/jrsnap.py` の `draw_figures`。データ確認図と荷重図を1回の `figures` で頼む（`--data-check <DATA_CHECK_FIGURES> --data-check-combination 1 --load-diagram <使う組合せ> --timeout-seconds <300＋120×組合せの数>`）。図の順は `DATA_CHECK_FIGURES`、組合せは `DATA_CHECK_COMBINATION = 1`。返った図ごとの PDF のページを図の順に1つにまとめる（荷重図は `../jrsnap-load-diagram/SKILL.md`）。
- 差し込みは、他のエンジンのページと共通の `webpier/reporting/stages/insertion.py`。0710・0720 の帳票は `Insertion(DATA_CHECK, <作用の見出し>, before=True)` で、10.2（11.2）の前にページの名前 `data_check` のページを挟む（`render_with_pages`）。
- 段階の登録表の `StageSpec.jrsnap_figures` が、どの NDU から描くかと「基本ケース → 組合せ」を決める。NDU の付帯JSONの `jrsnap_figures` に、runner の版と報告、データ確認図の組合せと図（`data_check`）を記録する。
- 0711・0721 を選ばない生成でも毎回描く。そのため、0710・0720 を含む生成には `STRUCTURAL_MCP_JRSNAP_RUNNER` が必須。
- 番号図・断面・節点ばねは組合せで変わらないので、組合せ1の `.ndt` だけで描く（0720 は組合せが2つ）。runner が 0710 のために書く `.ndt` は、0711 の `post/線路方向_JRSNAP/` の `.ndt` と SHA256 が同じ。
- テストの代役は `tests/fixtures/jrsnap/fake_runner.py` の `figures`。データ確認図は図ごとに `FAKE DATA CHECK <名前> <NDU の SHA256 の先頭16桁>` の1ページを返す。誤動作は `FAKE_JRSNAP_FIGURES` で選ぶ（`FAKE_JRSNAP` は `run` だけに効く）。

## 帳票アプリを補助の中で動かす共通の仕組み（src/ReportHost、2026-10-18 確認）

JRSNAP の帳票アプリ（S_DataCheck・S_LoadPicture）は、どれも同じ `Protect.Protection` と ComponentOne（C1Report 4.5.2）を持ち、PDF の書出しの機能がない。そこで、2つの補助（`JRSNAP.DataCheck.exe`・`JRSNAP.LoadPicture.exe`、x86、版によらず1つ）が `src/ReportHost/ReportHost.cs` をリンクして、同じ形で動かす。

**ライセンス：** `MDmain.Main` → `Protect.Protection` は、JRSNAP のトップ画面が渡すライセンス引数を `Interaction.Command()`、つまり**プロセスのコマンドライン**から読む。
- 末尾 11 文字が `Ver.<主>.<副>-L<FileBuildPart 2桁>` と一致しないと終了する。
- 値は S_ANALYSIS と同じで、5.2-L03 は `LicenseOptNo111111199999999999999Ver.5.2-L03`、5.3-L01体験版2 は `…Ver.5.3-L00`（帳票アプリの 5.3 の FileVersion は 5.3.0.0）。
- 引数がないと「直接起動は、できません」で終わる。
- ライセンスの確認に失敗すると、アプリ自身が `ProjectData.EndApp()` でプロセスを終える（終了コード 0、答えなし）。補助は `ProcessExit` の処理で失敗の答えを返す。
- ComponentOne・FarPoint の実行時ライセンスは、入口のアセンブリの埋込みライセンスで確かめる。

**流れ（`Host.Serve` → `Pilot`）：**
1. runner が補助を、ライセンス引数だけで起動する。依頼の JSON は標準入力で渡す。
   - `CreateNoWindow` だとコンソールの入力が UTF-8 にならないので、`Console.OpenStandardInput()` を UTF-8 で読む（読まないと日本語のパスで「無効な JSON プリミティブ」）。
   - 環境変数 `TEMP`・`TMP` は、runner の作業フォルダーの下の、起動ごとに別のフォルダーに向ける（下の「一時領域」）。
2. 補助は、インストール先に JRSNAP_Input.exe からの引渡しデータがないことを確かめる（BUSY の判定はアプリごと）。
3. `AppDomain.CreateDomain`（`ApplicationBase` はインストール先、構成は `<アプリ>.exe.config`）の中で `ExecuteAssembly(<アプリ>.exe)` する。
   - これでアプリが入口のアセンブリになり、自身の保護処理と C1・FarPoint のライセンスがそのまま効く。評価版の表示は出ない。
   - 補助の中でアプリの型を直接作ると、C1 のライセンスが補助 exe で確かめられ、保護処理も通らない。この方法は採らない。
4. 同じドメインに `MarshalByRefObject` の操縦役（`Pilot` を継いだクラス）を作る。
   - 操縦役は、2つ目のドメインに `AssemblyResolve` を登録する。補助の exe はインストール先の下にないので、これがないと最初のドメインの `Reporter` の型を解決できない。
   - 主画面（`<GlobalType>.G_MainFrm`）が表示され、アプリごとの起動の条件（`IsStarted`）を満たすのを待ってから、`BeginInvoke` で UI スレッドに入り、`Work()` を行う。
5. モーダルの画面には、UI スレッドの `System.Windows.Forms.Timer` から答える（`Steer`）。このタイマーはモーダルのメッセージループでも動く。
   - 画面が現れてから2回分待って答える（読込の終わりを待つため）。
   - ボタンは `BeginInvoke` で押す。タイマーの中で押すと、開いたモーダル画面がタイマーの中で動いてしまう。
   - 画面の監視は `EnumWindows` とプロセス ID で行う。`EnumThreadWindows` は UI スレッドの画面しか見ないので、別のスレッドに出る表示（評価版の通知など）を見落とす。
   - `#32770` は、アプリが `Expected` で認めたもの（データ確認図ではプリンターの選択「印刷」）だけを取り消して進める。それ以外と知らない画面は記録して閉じ、失敗（`UNKNOWN_DIALOG`）にする。
   - 答えた窓は閉じるまで次のタイマーでも見えるので、窓ごとに1回だけ答える。2回目を未知の画面と数えると、「印刷: プリンター …」で失敗する（実際に起きた）。
6. 組み立てたページを、ComponentOne の PDF 出力（`<C1PrintDocument>.Export("<名前>.pdf")`）で書く。プリンターは使わない。「Microsoft Print to PDF」は、スプールが非同期でファイルが遅れて現れるので使わない。
7. 結果は `Reporter.Answer`（最初のドメイン）で stdout に1回だけ書いて flush する。その後、アプリを閉じずに `TerminateProcess` で即座に終える。
   - 閉じると設定の INI を書き、S_LoadPicture は `.lpd` の保存を問い、`EndApp` で終わる。
   - `Environment.Exit` でも、終了処理の中で S_DataCheck の画面が例外を出し、答えの後に終了コードが変わったことがある（0710 で1回）。
   - アクセス違反のようにプロセスごと落ちる例外も受け止めて、答えを返す。

**一時領域：** 帳票アプリは `Interaction.Environ("TEMP") + "\RTRI\"` を一時領域にする（元に戻す操作用の `001〜010.tmp` を書き、閉じるときに消す）。C1 の PDF 出力は `%TEMP%\C1Pdf\` を作る。
- 補助の `TEMP`・`TMP` を作業フォルダーに向けるのは、利用者が画面で開いている JRSNAP の一時ファイルと干渉しないためである。作業フォルダーと一緒に消える。
- mutex では、利用者の JRSNAP との干渉は防げない。
- `%TEMP%\Rtri\JRSNAP_Main\JRSNAP_Language.ini` がないと言語は 0（日本語）になる。このPCにはもともとない。
- インストール先には書かないので、`figures` は mutex を取らない。

## S_DataCheck に固有のこと（`src/DataCheck/DataCheck.cs`）

- **起動の条件：** 非公開の `SystemFlg` が 1 になる（`frmMain_Activated` が引渡しデータを確かめ終えた）のを待つ。
- **読込：** JRSNAP_Input.exe から引き渡されたデータと同じ経路で行う。`MdlWork.G_strFileName = <.ndt>`、`MdlGlobal.WorkFlg = 1` として `mdlMain.mdl_MENU_FILE_DATA()` を呼ぶ（終われば `WorkFlg = 0`）。
  - `mdl_GET_DATA` だけを呼ぶと、配列の準備（`Mdl_Get_TotalNum`・`SetRedimArray`）がなく `NullReferenceException` になる。
  - この経路は、最後に作画条件設定（`frmSetPaper`）をモーダルで開く。
- **ヘッダーの固定：** 読込の前に行う。`GetIniFileHeader` は `frmMain_Load` で読まれ、`SystemFlg` はその後に立つので、この順で上書きできる（5.2 の IL でも同じ）。
- **印刷：** `mdlMain.mdl_MENU_FILE_PRINT_Click(1)` は、`frmPrint` で選んだ図を `frmMain.C1PrintDocument2` に組み立て、`PrintDialog` を出す。取り消しても `C1PrintDocument2.Generate()` は済んでいるので、それを書き出す。RTF 出力（`pFlg=2`）はあるが、PDF も「Docu-SE」連携もない。
- **順序と図の数：** 1回の印刷の中の順序は S_DataCheck が決める（軸線図の帳票、要素ばね、節点ばね、地盤抵抗、断面詳細、要素諸元、地盤変位、着目点の順）。見本の順（断面詳細の後に節点ばね）にするには、図ごとに作画条件設定と印刷を1回ずつ行う。

**落とし穴：**
- 5.2-L03 は、作画条件設定の「出力断面番号指定」（`Text1`）を空のまま開く。そのままでは `Mdl_YousoSitei` が0件になって、断面詳細図が白紙の1ページになる。`1-<MdlWork.G_intSectNum>` を入れる。5.3 は読込で `1-<断面数>` を入れる。
- S_DataCheck は起動時に、インストール先の `nrflag.fil`（`frmMain_Activated`）と `*.wk0`（`frmMain_Shown`、サブフォルダーも探す）を開こうとする。JRSNAP_Input.exe からの引渡しが残っていれば別のデータを読むので、`BUSY` で止める。
- `Application.StartupPath` は補助 exe のフォルダーになる。
  - `Mdl_NM_Get_IniData` は `SekoJyoken` をそこの `INI\DataInputTool.ini` から読もうとするので、既定値（0）になる。
  - ほかの INI はインストール先（`My.Application.Info.DirectoryPath`）から読む。
- 作図は、WebPier の骨組図と違って部材の外形の枠を描かない（見本 5.1 の図は外形の灰色の枠を描いていた）。違いは JRSNAP の版のもので、直さない。

## 別の帳票アプリを足すとき

`Pilot` を継いで、次をアプリごとに書く。
- `AppName`
- `GlobalType`（`G_MainFrm`・`G_HeaderFlg` のある型。S_DataCheck は `MdlGlobal`、S_LoadPicture は `MdlGlobalProclaim`）
- `IsStarted`
- `Work`
- `Steer`
- `Expected`

あわせて、`Host.Serve` に失敗の種類の名前と BUSY の判定を渡す。読込の経路、画面のコントロール名、起動の条件、閉じるときに何を書くかは、アプリごとに逆コンパイルのソースで確かめ、5.2 は IL で照合する。S_LoadPicture を足したときの手順と違いは `../jrsnap-load-diagram/SKILL.md`。
