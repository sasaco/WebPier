---
name: jrsnap-load-diagram
description: この環境の JRSNAP Ver.5.2-L03 の「荷重図」（S_LoadPicture.exe）で、.ndu（の組合せごとの .ndt）から基本ケース（CASE-n）ごとの荷重図を画面操作なしで PDF にする。JRSNAPHeadless の runner の figures --load-diagram と補助 JRSNAP.LoadPicture.exe、WebPier の 0710・0720 の計算書の 10.3・11.3 荷重図（決定51、.claude/docs/plans/jrsnap-load-diagram-plan.md）、S_LoadPicture の読込・作画条件・印刷・終了の内部の手順、どのケースをどの組合せの .ndt から描くか（組合せに使わないケースの荷重は0で書かれる）を扱う。荷重図が描けない・ページ数やケースが合わない・色や向きや体裁が違う・インストール先や TEMP に何か書く・5.3 で落ちるとき、作画条件を変えるときに使う。0610・0620 の FEMPython の荷重図には使わない。補助の共通の仕組み（ReportHost）は jrsnap-data-check。
---

# 荷重図（S_LoadPicture.exe）を PDF にする

対象は `C:\RTRI_Program\JRSNAP(Ver5.2-L03)\S_LoadPicture.exe`（FileVersion・AssemblyVersion 5.2.3.0）。5.3 の逆コンパイルのソースは `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_LoadPicture` にある。
- `frmMain.cs`：起動・新規作成・印刷・終了
- `mdlDataFile.cs`：INI と NDT の読込
- `mdlSystemInfo.cs`：用紙・ケース分け
- `frmSetPaper.cs`：軸線レイアウト
- `frmLoadLayout.cs`：荷重レイアウト
- `frmPreView.cs`：印刷のプレビュー
- `mdlViewControl.cs`・`mdlDrawLoad.cs`：作画

5.2 のソースはない。5.3 のソースで書いた手順は 5.2 でそのまま動いた。関係するメソッドの IL の違いは次の3点だけである。
- `frmMain_Load` の `MDF_DataInit`
- `frmLoadLayout.cmdOK_Click` の `MDC_MenuInit`
- `[Header] Trial`

**S_LoadPicture は `.ndt`（と `.rdt`）しか読まない。** NDT の `LOAD` の `CASE-n`（基本ケース）ごとに1ページを描く。ただし `.ndt` は組合せごとのファイルで、JRSNAP は組合せに使わない基本ケースの荷重を0にして書く。たとえば 0720 では、組合せ1の NDT は CASE-6（下り線）が0、組合せ2の NDT は CASE-5（上り線）が0である。したがって、**基本ケースは、それを使う組合せの NDT のページから取る**。

## 使う：JRSNAPHeadless の figures --load-diagram

使い方・成果物・失敗の種類は、`C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless\README.md` を正とする。

```powershell
& 'C:\Users\sasai\Documents\structural-mcp\JRSNAPHeadless\bin\Release\JRSNAP.Headless.exe' figures `
  --input 'C:\Users\sasai\Documents\structural-mcp\WebPier\post\線路直角方向.ndu' --output-dir 'C:\tmp\ld-out' `
  --load-diagram 1,2
```

- 組合せごとに `load-diagram-<組合せ>.pdf`（kind `load-diagram`）を返す。中身は、その NDT の全ケースを CASE の順に1ケース1ページで描いたものである。
- `summary.loadDiagram[].pages` に `{page, case, title}` が入る。`title` は `CASE-<番号> <タイトル>` の形である。
- どのケースをどの組合せのページから取るかは、呼び出し側が決める（WebPier は NDU のモデルから、ケースを使う最初の組合せを選ぶ）。
- `--data-check …` と一緒に頼めば、NDT の書出しは1回で済む（`../jrsnap-data-check/SKILL.md`）。
- `bin\Release` は 2026-10-18 に作り直した（`JRSNAP.LoadPicture.exe` を含む）。
- 1回の起動は1組合せにつき 6〜7 秒、`figures` 全体で 26〜43 秒（データ確認図5つと荷重図）。画面は一瞬表示される。
- **対応する版は 5.2-L03 だけ。** 5.3-L01体験版2 の `S_LoadPicture.exe` は、単独では起動する。しかし補助の2つ目のドメインでは、`frmMain` ができる前にアクセス違反になり、`LOAD_DIAGRAM_FAILED`（`AccessViolationException`）を返す。段階0の試作でも同じで、IL を比べても違いが見つからず、原因は調べていない。データ確認図は 5.3 でも動く。

## 作画条件（決定51、runner が固定）

A4縦、縮尺は X・Y とも自動、1ケース1ページ、色はすべて黒、ページ番号（「p / N」）なし、同じ部材の要素荷重は段に分けて描く（`AutoRowFlg` 1）。それ以外の枠線・余白・文字の高さ・線幅・単位などは、**プログラムの既定値**を使う。インストール先の `ini\LoadPicture.ini` は、次の理由で読まない。
- 利用者が画面を使うたびに書き換わる（窓の位置、最後のフォルダー、色）。
- 5.2-L03 と 5.3 で中身が違う（`AutoCaseFlg`、`LineWidth4/5` など）。
- 色（`Color7=4` など）や、`Flame 15`・`TextHeight2 7` のように既定と違う値が入っている。

ヘッダーは、データ確認図と共通に `【Ver5.2-L03】<印刷日>『<.ndt の名前>/<データ名>』` の右揃えに固定する（`G_HeaderFlg` = 1,1,1,1,0,2）。印刷日が入るので、PDF のバイト列は日ごとに変わる。

**`AutoRowFlg`（`MSI_Set_LoadRow`）：** 同じ部材で重なる要素荷重を段に分ける。
- 要素荷重の種別 4・5（`MEMBER LOAD` の種別。柱自重は 4）は、0 でも 1 でも段に分けない。
- いまの WebPier の NDT はどのケースも1部材に要素荷重が1つなので、0 と 1 で図はピクセル単位まで同じである。
- 合成の NDT（部材1に要素荷重をもう1つ足したもの）では、0 は値が重なり、1 は2段に分かれた。
- 0710 の CASE-1 で、節点4〜6付近の「297.680」と「4167.450」の文字が重なるのは、種別4の既定の配置である。`AutoRowFlg` では直らず、JRSNAP の描画として受け入れた。

## 手順（`JRSNAPHeadless\src\LoadPicture\LoadPicture.cs` の `LoadPicturePilot`）

補助の起動・ドメイン・操縦・書出し・終わり方の共通部分は、`../jrsnap-data-check/SKILL.md` の「共通の仕組み」のとおり。S_LoadPicture に固有のことは次のとおり。

**起動の条件：** `MDmain.Main` は `new frmMain().ShowDialog()` で、S_DataCheck の `SystemFlg` に当たるものはない（宣言だけで代入されない）。`MdlGlobalProclaim.G_MainFrm` が Visible でハンドルが作られたら `BeginInvoke` する。`frmMain_Shown`（`*.wk0` を探す）は先に済んでいる。

**1. 作画条件を INI から切り離す（UI スレッドの最初）**
- `frmMain` のコンストラクター（`Form_Initialize_Renamed` → `MDF_Get_INIFile`）は、インストール先の INI を読む。読むだけで害はない。
- その後で、`mdlGlobalWorkProclaim.WG_strIniFileName` を作業フォルダーの**存在しない**ファイルに向けて、`mdlDataFile.MDF_Get_INIFile()` を呼び直す。全キーがプログラムの既定値になり、色は Color1〜26 がすべて 0（黒）、`AutoRowFlg` 0 になる。
- 念のため `GT_BOther.bytColor` を 0 で消し、`WG_bytAutoRowFlg` を依頼の値にする。
- 構造体のフィールドは値型である。`FieldInfo.GetValue` は箱詰めの写しを返すが、中の配列（`bytColor`）は共有の参照なので、要素を直接変えられる。
- 一時の INI は最後まで作られない。作られていれば、閉じる経路を通った証拠になる。
- `MDF_Get_INIFile` は主画面の位置も動かし、インストール先の `nrwork.dir`（フォルダーの上書き）と `C:\nwl\Project\Project.ini` を読む。どれも読むだけである。
- ヘッダーを固定する（`FixHeader`）。`frmMain_Load` の `GetIniFileHeader`（`ini\DataInputTool.ini [Header]`）が先に済んでいるので、この後に上書きする。

**2. NDT を読む（「新規作成」の手順を、インストール先への書込みを除いて直接呼ぶ）**

`frmMain.mnuFileNew_Click` は、インストール先の `nrwork.dir` と INI の `NDTInitFolder` を書くので、メニューは使わない。
1. `WG_strNDTFileName = <.ndt>`、`SakugaLoadFlg = 0`、`WB_Flg = 0` にする。
2. `mdlSystemCommon.Mdl_Get_TotalNum(1, ndt)` → `SetRedimArray(1)` → `mdlDataFile.MDF_DataFormat2()` を呼ぶ。
3. `MDF_Get_NDTData(ndt)` を呼ぶ。0 以外は `NDT_READ_FAILED`。
4. `mdlSystemInfo.MSI_Chk_ErrorData()` を呼ぶ。0 より大きければ `NDT_REJECTED`。
   - 画面では「要素荷重が不正です！」の MsgBox が出て、何も読まない。
   - 要素荷重の2つの値（列 36〜55）がともに0の行が1つでもあると、こうなる。
   - いまの WebPier の NDT では起きない（JRSNAP が0にするのは、いまは節点荷重だけ）。
5. `WB_Flg == 1`（土圧の WB ブロック）なら、`frmSakugaOption` を開いて「一般荷重」（`_Option1_0`）→ `Command1` で答える。この経路は実物では確かめていない。
6. `G_bytObjectViewFlg[11] = 1`（要素番号を隠す）にする。
7. **`WG_bytAutoCaseFlg = 0` にする。**
   - `MDF_Get_NDTData` はケースが1以下のときこれを 1 にし、次の `MSI_Chk_NDTData` がそれを使って、種別ごと（固定荷重・死荷重地震・活荷重地震）の最大3ページに分けてしまう。
   - 0 にするのは、この2つの呼出しの**間**でなければならない。読込の後では遅い。
   - INI の `AutoCaseFlg` は、`.ndt` では効かない。
8. `MSI_Chk_NDTData()` を呼ぶ。A4 にし、モデルが横長なら横向きにし、縮尺を自動にする。
9. `WG_bytSystemDataFlg = 0` → `MDF_WorkDispInit()` を呼ぶ。
10. `frmSetPaper`（軸線レイアウト）をモーダルで開く。答え方は次の「画面の答え方」。
11. `WG_bytSystemDataFlg == 2` を確かめる。
12. `mdlDispControl.Set_State_Open` → `mdlUndoRedo.MUR_SetUndo` → `mdlZoom.MZ_Zoom_AllView` を呼ぶ。

**画面の答え方（`Steer`）：**
- **`frmSetPaper`（軸線レイアウト）：**
  - 表示されて2回分待ち、さらに `blnFormLoadFlg` が true になってから答える。
  - `optA4`・`optV` を選び、`cboX`・`cboY` の `SelectedIndex = 0`（自動）にして、`cmdOK`（「次へ」）を押す。
  - `optV` を選ぶと `SetPaperPreview` が縦で縮尺を計算し直す。
  - `cmdOK_Click` の中で `frmLoadLayout` が開く。
  - `frmSetPaper` は、全ケースのタイトルの位置（`MSI_Get_InitPosition`）も決めるので、飛ばさない。
- **`frmLoadLayout`（荷重レイアウト）：** `cmdOK` を押す。`WG_bytSystemDataFlg = 2` になる。FarPoint の表を使うが、評価版の表示は出ない。
- **`frmPreView`：** 下の「3. ページを組む」。
- **それ以外の画面と `#32770`：** 失敗にする。
  - 「データエラー」「読込みエラー」（100〜104）「入力値エラー」が出るはずのものは、手順の中で検査して先に止める。

**3. ページを組む（画面の印刷と同じ経路）**
1. `G_bytObjectViewFlg[3] = 1`（ページ番号を隠す）は、`mnuFilePrint_Click` の直前に設定する。コンストラクターの `MDF_DataFormat` が0に戻すためである。
2. `frmMain.mnuFilePrint_Click` は、`frmPreView` をモーダルで開く。`frmPreView_Load` の `MakePreView` が、1〜`G_intCaseNum` の全ページを `C1PrintDocument_prev` に組んで `Generate()` する。ページの間は `RenderText{BreakBefore = Page}`、各ページは `MVC_ViewControl_ALL(doc, 2, 0)` で描く。印刷のダイアログは、ツールバーのボタンを押さない限り出ない。
3. タイマーで `frmPreView` を見つけ、`IsGenerating` でなくなったら `Export` し、`BeginInvoke(Close)` で閉じる。`frmPreView` には Closing・Closed の処理がない（5.2 のメタデータと 5.3 のソースで確認）。
4. ページ数が `G_intCaseNum` と違えば `PAGE_MISMATCH`。
5. ページとケースの対応は `MdlGlobalProclaim.G_strCaseTitle[1..G_intCaseNum]` から取る。タイトルは `"CASE-" + 番号 + " " + Mid(CASE 行, 40, 80)` の形である。
6. `frmMain.C1PrintDocument_main` は、画面の今のページしか持たないので使わない。

**4. 終わり方：** 結果を書いてから、`frmMain` を閉じずにプロセスを終える（ReportHost）。`frmMain` を閉じると、次の処理が走る。
- `FormClosing`：`WG_bytSystemDataFlg == 2` なら、`<WG_strSystemDataFolder>\<ndt名>.lpd` を黙って書くか、「データが更新されています。保存しますか？」を出す。
- `FormClosed`：次の順に処理する。
  1. `MDF_Wrt_INIFile()` で INI を全部書き出す。
  2. `%TEMP%\RTRI\###.tmp` を消す。
  3. `DataInputTool.ini [Option] Docu-SE = 1` なら `.w09` を書く。
  4. `ProjectData.EndApp()`。このため `ExecuteAssembly` は戻らない。

**BUSY：** S_LoadPicture は起動時に、インストール先の**直下**の `*.wk0` を開く（`frmMain_Shown`。`nrflag.fil` は見ない）。あれば `BUSY`。

## 確かめ方（段階0・1で使った測り方）

- **PDF：** `pypdfium2` で開いて、次を確かめる。
  - 全ページが 595.3×841.9pt（A4縦）であること
  - ページ数がケース数と同じこと
  - 各ページの文字に `CASE-<n> <タイトル>` があること
  - 数字の「/」が日付だけであること（ページ番号がない）
  - ComponentOne・Evaluation・評価・FarPoint・Trial の文字がないこと
  - 0720 の組合せ2の CASE-6 のページに `480.000` があること
- **色：** 150dpi の PNG にして、R・G・B が揃っていない画素を数え、0 であることを確かめる。
- **前後比較：** インストール先（333 項目）、利用者の `%TEMP%\RTRI`・`%TEMP%\C1Pdf` の、パス・サイズ・更新日時・SHA256 を、実行の前後で比べる。
  - 実行中に `JRSNAP_Input`・`S_ANALYSIS`・`S_DataCheck`・`S_LoadPicture` などのプロセスが動いていれば、その回は無効にする（ほかのセッションの runner でも濁る）。
  - 補助の作業用の TEMP に `RTRI\001.tmp` が残ることは、閉じずに終えた証拠になる。
- **出力の同一性：** 補助を作り直したときは、同じ日に出した前の PDF と、全ページの画素を比べる。

## 5.2 を IL で確かめる

5.2 のソースはないので、5.3 のソースで書いた手順に使うメンバーは、5.2 の exe のメタデータで実在とシグネチャを確かめる。メソッドの中身は `MethodBody.GetILAsByteArray()` と `Module.ResolveMember`・`ResolveString` で比べる。読み込みは x86 のプロセスから `Assembly.LoadFile`（リフレクションだけ）で行う。デコンパイラーはなくても、IL のダンプで足りた。

## WebPier での使われ方（決定51）

- 0710 に「10.3 荷重図」、0720 に「11.3 荷重図」の見出しを置き、その後に基本ケースのページを CASE の順に1ケース1ページで挟む。作用の組合せは 10.4・11.4 で、新しいページから始める。荷重が0のケースも省かない。
- WebPier は NDU のモデル（`export/jrsnap/model.NduModel` の `cases` と `combinations[].coefficients`）から、基本ケースごとに「そのケースを使う、番号がいちばん小さい組合せ」を決める（0710 は全ケース 1、0720 は CASE-6 だけ 2）。その組合せを `--load-diagram` に渡し、返ったページから（`summary.loadDiagram[].pages` のページとケースの対応で）1ページずつ取り出す。
- 実装の場所：「基本ケース → 組合せ」は `webpier/export/jrsnap/diagrams.py` の `diagram_combinations`（登録表の `StageSpec.jrsnap_figures` が使う）、runner の呼び出しとページの取り出しは `webpier/pipeline/jrsnap.py` の `draw_figures`（データ確認図と1回の `figures` で頼む）、計算書への差し込みは `webpier/reporting/stages/insertion.py`（`Insertion(LOAD_DIAGRAM, <10.3・11.3 の見出し>)`）。NDU の付帯JSONの `jrsnap_figures.load_diagram` に `[{case, combination}, …]` を記録する。
- 受入：`scripts/accept_jrsnap_figures.py`（本物の runner、5.2-L03。記録 `tests/fixtures/acceptance/jrsnap_figures/record.json`、テスト `tests/acceptance/test_jrsnap_figures_acceptance.py`）。0710 は8ページ・0720 は9ページが CASE の順、A4縦・色の画素0・ページ番号なし、0720 の CASE-5・CASE-6 の両方に 480 を確かめた（2026-10-18）。生成する NDU か「基本ケース → 組合せ」が変わると `tests/acceptance` が失敗するので、`--overwrite` を付けてやり直す。
- 計算書の確かめ方（本物の runner で `--stage 0710`・`0720` を作り直した後）：`uv run --no-project --with pypdfium2 --with pillow python -X utf8 …` でページごとの文字を取り出し、並びを見る。2026-10-18 の `pre/input.json` では、0710 は17ページ（1〜2 10.1、3〜7 データ確認図、8 10.2 の末尾に「10.3 荷重図」、9〜16 CASE-1〜8、17 「10.4 作用の組合せ」）、0720 は19ページ（8〜9 11.2 で9の末尾に「11.3 荷重図」、10〜18 CASE-1〜9、19 「11.4」）。組合せ2から取った 0720 の CASE-6 だけ、ヘッダーの名前が組合せ2の NDT（`『線路直角方向(Case2_…)』`）になる。見出しのページと 10.4・11.4 の改ページは、150dpi の PNG にして目でも確かめる。
- 見本 `.claude/docs/Example橋脚2/10_線路(耐震).pdf` の 10.3（10-9〜10-11）は、Excel で描いた図（1ページに2〜3ケース）で、その体裁は再現しない。
- 詳細と進み具合は `.claude/docs/plans/jrsnap-load-diagram-plan.md` と `refactoring-decisions.md` の決定51。
