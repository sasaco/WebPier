# 0710・0720 の荷重図（決定51）の実装計画

決定51（`refactoring-decisions.md`）を実装する。0710 に「10.3 荷重図」、0720 に「11.3 荷重図」を置き、JRSNAP の `S_LoadPicture.exe` が描いた基本ケースごとのページを挟む。作用の組合せは 10.4・11.4 に繰り下げる。

データ確認図（決定50）は実装済みで、コミットもしてある（WebPier 09c49f5、JRSNAPHeadless 31af7b7。runner は `data-check`）。0710・0720 の 3〜7 ページに入っている。

## 始める条件

- **0611 の作業（決定48の続き）がコミットされてから始める。** その作業はいま、次のファイルを編集している。

  | ファイル | 段階2・3で触る箇所 |
  |---|---|
  | `pipeline/generate.py` | 計算書に渡すページの選び方 |
  | `pipeline/stages.py` | `StageSpec` の検査 |
  | `reporting/assembly.py` | `page_range` を追加した |
  | `reporting/stages/frame_report.py` | — |

  段階2・3も同じ箇所を触るので、重ねて編集しない。段階0・1（JRSNAPHeadless）は WebPier を触らないので、先に進めてよい。
- **品質ゲートの受入：** 決定48の入力の形式を変えたことで、受入8件（JRSNAP・FrameWeb・Aggre-SE の記録）が落ちている。やり直しは、それを壊した 0611 の作業に含める（推奨）。0611 がやり直さずにコミットされた場合は、この計画の段階4の前に行う。どちらにするかはユーザーが決める。

## 前提（調べた事実）

S_LoadPicture（5.3 の逆コンパイル `C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\S_LoadPicture`。メンバー名は 5.2-L03 の exe のメタデータにもある）について。

- **起動とライセンス：** S_DataCheck と同じ `Protect.Protection` を持つ。プロセスのコマンドラインの末尾 11 文字を `Ver.<主>.<副>-L<FileBuildPart>` と照合する。5.2 は FileVersion 5.2.3.0 で `Ver.5.2-L03`、5.3 は 5.3.0.0 で `Ver.5.3-L00`。runner の版ごとのライセンス引数で通り、Output-JR の購入フラグ（[2]）も 1 になる。失敗すると `EndApp` でプロセスが終わり、終了コードは 0 で答えも返らない。
- **読込：** `frmMain_Shown` はインストール先の直下の `*.wk0` を探し、あれば中の NDT を自動で開く。「新規作成」（`mnuFileNew_Click`）は次の2つを書く。
  - インストール先の `nrwork.dir`
  - INI の `NDTInitFolder`

  メニューを通さずに同じ処理を順に呼べば、どちらも書かない。手順は次のとおり。
  1. `Mdl_Get_TotalNum`、`SetRedimArray`、`MDF_DataFormat2`、`MDF_Get_NDTData`、`MSI_Chk_ErrorData`
  2. `MSI_Chk_NDTData`、`MDF_WorkDispInit`
  3. `frmSetPaper`（軸線レイアウト）。「次へ」で `frmLoadLayout`（荷重レイアウト）が開くので、OK を押す。
  4. `WG_bytSystemDataFlg == 2` になったことを確かめる。
- **起動を待つ条件：** `MDmain.Main` は `frmMain.ShowDialog()` で、S_DataCheck の `SystemFlg` に当たるものはない（宣言だけで代入されない）。`G_MainFrm` が Visible でハンドルが作られたのを待ってから `BeginInvoke` する。
- **ページ：** NDT の `CASE-n` ごとに1ページ（自動ケース分けがオフのとき）。ケース数が1以下の NDT だと、`MDF_Get_NDTData` が `WG_bytAutoCaseFlg` を 1 にし、続く `MSI_Chk_NDTData` がそれを使って、種別で3ページに分ける。0 にするのは**この2つの呼出しの間**でなければならない（読込の後では遅い）。
  - 画面の印刷（`mnuFilePrint_Click` → モーダルの `frmPreView`、`frmPreView_Load` の `MakePreView`）は、1〜`G_intCaseNum` の全ページを `frmPreView.C1PrintDocument_prev` に組んで `Generate()` する。印刷のダイアログは、ツールバーのボタンを押さない限り出ない。
  - 各ページのケースは `G_strCaseTitle[p]`（`CASE-<番号> <タイトル>`）でわかる。
  - PDF は `C1PrintDocument.Export("x.pdf")` で書ける（ComponentOne の PDF 出力。データ確認図と同じ）。
- **作画条件：** INI のキーがないときの既定値は、すべて黒（Color1〜26 = 0）、`AutoRowFlg` 0、`LineWidth1〜5` = 1,2,0,0,0 など。インストール済みの INI は多くの値がこの既定と違う（Color7=4、Flame 15、TextHeight2 7 など）。
  - `WG_strIniFileName` を一時フォルダーの存在しないファイルに向けて `MDF_Get_INIFile()` を呼び直せば、全項目が既定になる。閉じるときの INI の書出しもその一時ファイルに向かう。
  - A4縦にするには、`MSI_Chk_NDTData` が横長のモデルで自動的に横向きにするので、`frmSetPaper` で `optA4`・`optV`・縮尺「自動」を選ぶ。
- **ヘッダー：** 項目は `G_HeaderFlg[0..5]` で決まり、`DataInputTool.ini [Header]` から読む。S_DataCheck も同じ配列を同じ INI から読む（`mdlMain.GetIniFileHeader`、`MdlGlobal.G_HeaderFlg`。S_LoadPicture は `MdlGlobalProclaim.G_HeaderFlg`）。いまの2つのインストールの値は 1,1,1,1,0,2。
  - ページ番号「p / N」は `G_bytObjectViewFlg[3]` で消せる。
- **一時領域：** ComponentOne の PDF 出力は `%TEMP%\C1Pdf\` を作る（利用者の `%TEMP%\C1Pdf\1` は、データ確認図の補助がすでに作っていた）。また、両アプリとも `Interaction.Environ("TEMP") + "\RTRI\"` を使う（S_LoadPicture `mdlSystemInfo.cs:32`、S_DataCheck `frmMain.cs:1627`）。元に戻す操作用の `001〜010.tmp` もここに書き、閉じるときに消す。`JRSNAP_Language.ini`（`%TEMP%\Rtri\JRSNAP_Main\`）はなければ言語 0（日本語）になる。このPCにはもともとない。
- **終了：** `frmMain_FormClosed` が次のことをする。
  - INI の書出し
  - 一時ファイルの削除
  - `ProjectData.EndApp()`（`Environment.Exit`）。このため `ExecuteAssembly` は戻らない。

  また `FormClosing` は、`WG_bytSystemDataFlg == 2` のとき `.lpd` を黙って書くか、保存を問う MsgBox を出す。
- **データ検査：** 要素荷重の2つの値がともに0の行が1つでもあると、`MSI_Chk_ErrorData` が「要素荷重が不正です！」を出し、NDT 全体を読まない。いまの 0710・0720 の NDT の要素荷重（柱自重、自重慣性力）は該当しない。組合せに使わないケースを JRSNAP が0にして書くのは、いまは節点荷重だけ（0720 の CASE-5・6）。

WebPier 側について。

- **計算書にページを差し込む形が3通りある。** どれも「原稿を単位のキーで分け、各位置にページを挟む」同じ形である。

  | 段階 | 差し込むもの | 位置 | いまの実装 |
  |---|---|---|---|
  | 0610・0620 | FEMPython の荷重図 | 見出しの後、1か所 | `load_diagrams.py`・`render_with_pages`、引数は bytes |
  | 0710・0720 | データ確認図 | 10.2 の前、1か所 | `data_check.py` |
  | 0611（作業中） | Capacita のページ | 節ごと | `column_check.parts`・`page_range`、引数は `ColumnCheckPages` |

  計算書に渡す引数の型がばらばらで、`generate.py` に段階ごとの分岐が増えかけている。
- 「基本ケース → 組合せ番号」は、NDU のモデル（`export/jrsnap/model.NduModel`）から決まる。`cases` の順と、`combinations[j].coefficients`（ケースごとに 1・0）を使う。

## 決めたこと

1. **`data-check` は `figures` に置き換え、残さない。** 開発初期で後方互換を作らない（CLAUDE.md）。runner を使うのは WebPier だけである。
2. **荷重図のページから、ページ番号「p / N」を消す。** 計算書にはページ番号を印刷しない（決定44）。
3. **ページのヘッダーの項目を、データ確認図と荷重図で同じ値に固定する。** いまのインストールの値（版・日付・ファイル名・データ名を表示、データタイトルを非表示、揃え 2）を使う。固定は両アプリ共通の部分（ReportHost）に置き、INI が変わっても2種類のページの見た目がずれないようにする。日付が入るので、ページのバイトは日ごとに変わる（決定50と同じ）。
4. **`AutoRowFlg`（同じ部材の要素荷重を段に分けて重ならないように描く）は 1 にする。** 段階0の結果は次のとおり。
   - いまの入力では 0 と 1 で荷重図がピクセル単位まで同じ。どのケースも1部材に要素荷重が1つで、要素荷重の種別 4・5（柱自重など）はもともと段に分けない。
   - 同じ部材に要素荷重を重ねた合成の入力では、0 は値が重なり、1 は2段に分かれて読めた。
   - 0710 の CASE-1 で節点4〜6付近の「297.680」と「4167.450」が重なるのは、種別 4 の既定の配置で、`AutoRowFlg` では変わらない。JRSNAP の描画として受け入れる（ADR-0005 と同じ）。
5. **始める時期：** 0611 の作業のコミットを待つ（上の「始める条件」）。

## 段階

### 0. 試作（JRSNAPHeadless、5.2-L03） — 済み

JRSNAPHeadless 4a92316（`src/LoadPicture/`）。5.2-L03 の実物で、下のチェック項目はすべて合格した。補助は8回実行し、すべて終了コード 0、5.8〜7.2 秒。

- インストール先（333件）と `%TEMP%\RTRI`（31件）は、実行の前後でサイズ・更新日時・SHA256 が一致した。
- 0720 の組合せ2の CASE-6 に N=480.000・M=1028.620 が描かれた。
- 5.2 と 5.3 で関係するメソッドの IL の違いは3点だけで、どれも影響しない。
  - `frmMain_Load` の `MDF_DataInit`
  - `frmLoadLayout.cmdOK_Click` の `MDC_MenuInit`
  - `[Header] Trial`
- 確かめていない経路：WB ブロックの `frmSakugaOption`、`NDT_REJECTED`、ケースが1以下の NDT、5.3 のインストール。

以下は試作の前に立てたチェック項目（記録として残す）。

既存の `post/線路方向_JRSNAP/…ndt`・`post/線路直角方向_JRSNAP/…ndt` で、S_LoadPicture の補助 exe を試作し、ページを PNG にして確かめる。確かめることは次のとおり。

- 評価版の表示が出ないこと（`frmLoadLayout` の FarPoint も含む）
- 結果を返してからプロセスが終わること
- インストール先に何も書かないこと（`ini\LoadPicture.ini`・`nrwork.dir`・`.lpd`）
- 利用者の `%TEMP%\RTRI` に何も書かないこと
- 日本語で表示されること（言語の INI がない状態で）
- A4縦であること
- 1ケース1ページであること
- すべて黒であること
- 「p / N」が消えていること
- `AutoRowFlg` 0 と 1 の見た目の違い

0720 の組合せ2の NDT から CASE-6 を描けることも確かめる。決定4（`AutoRowFlg`）は、ここで画像を見てもらって決める。

### 1. runner：`figures` コマンド（JRSNAPHeadless） — 済み

JRSNAPHeadless 2374a5b。`-c Stage1`（`bin\Stage1`）でビルドし、テスト 56 件がすべて合格した。本物の 5.2-L03 では、0710・0720 の NDU で `figures` を各3回実行し、すべて成功した。以下の書いたときの計画から、次の点を変えた。
- **引数・失敗の種類：** `--data-check-combination`（`--data-check-case` ではない。組合せと基本ケースを混ぜない）、`COMBINATION_NOT_FOUND`・`LOAD_DIAGRAM_FAILED`・`HOST_MISSING`・`PAGE_MISMATCH`・`UNEXPECTED_OUTPUT`。
- **時間：** `--timeout-seconds` はコマンド全体の時間（既定 600）。
- **終わり方：** 補助は答えを書いたら `TerminateProcess` で終える。`Environment.Exit` では、終了処理の中の S_DataCheck の画面の例外で、答えの後に終了コードが変わったことがあった。
- **5.3 の荷重図：** 荷重図は 5.2-L03 だけ対応。5.3-L01体験版2 の S_LoadPicture は、補助の中で起動の途中にアクセス違反になる（原因は未調査）。
- **データ確認図の出力：** `bin\Release` の古い runner の出力と、全ページの画素が同じだった。
- **`bin\Release`：** 古い `data-check` のまま残した。WebPier の段階2で `figures` に替えるときに作り直す。
- 手順と仕組みは、スキル `jrsnap-data-check`（共通の仕組み）と `jrsnap-load-diagram` に書いた。

0611 の作業を待たずに進めてよい。

- **共通部分の切出し：** `src/DataCheck/DataCheck.cs` から、帳票アプリを動かす共通部分を `src/ReportHost/`（共有ソース、両方の csproj にリンク）に切り出す。共通部分は次のとおり。
  - 標準入力の JSON
  - 監視用のスレッド
  - 2つ目のドメインで `ExecuteAssembly`
  - `#32770` に1回だけ答える処理
  - `Check`・`Find`
  - C1 の Export
  - ヘッダーの固定（`G_HeaderFlg` を決定3の値にする。アプリごとに配列のある型の名前だけを渡す）
  - 結果の書出し

  データ確認図の補助（`JRSNAP.DataCheck.exe`）は、ヘッダーの固定以外の振る舞いを変えずにこれを使う形にする。

  段階0で確かめた注意：
  - 起動を待つ条件はアプリごとに違うので、ReportHost に入れない。S_DataCheck は `SystemFlg`、S_LoadPicture は `G_MainFrm` が Visible になるのを待つ。
  - 結果の書出しの口（最初のドメインの `MarshalByRefObject`）を2つ目のドメインから使うには、操縦役が2つ目のドメインに `AssemblyResolve` を登録する。補助の exe がインストール先の下にないためである。
  - 最初のドメインに `ProcessExit` の処理を置く。アプリがライセンスの失敗で `EndApp` しても、失敗の答えを返せる。
  - ボタンは `BeginInvoke` で押す。タイマーの中で押すと、開いたモーダル画面がタイマーの中で動く。画面が現れてから2回分待って答える（`frmSetPaper` は `blnFormLoadFlg` も待つ）。
  - 画面の監視は、`EnumWindows` とプロセス ID で行う。`EnumThreadWindows` は UI スレッドの画面しか見ないので、別のスレッドに出る表示を見落とす。
  - ヘッダーの固定は `frmMain_Load` の後に行う。`GetIniFileHeader` が後から上書きするためである。配列のある型は、S_LoadPicture が `MdlGlobalProclaim`、S_DataCheck が `MdlGlobal`。
  - 終わり方は、データ確認図も `Environment.Exit` にそろえる（いまは `main.Close()`）。
- **結果の書出し：** 補助は、終了の処理に入る前に結果の JSON を標準出力に書いて flush する。書き出す処理は、操縦役から最初のドメインの `MarshalByRefObject` を通して呼ぶ。版の違いで `EndApp` が残っても答えは返り、`ExecuteAssembly` が戻らなくてもよい。結果を書いた後は、閉じずにプロセスを終える（`Environment.Exit`）。こうすると、INI の書出しも `.lpd` の問合せも通らない。データ確認図の補助も同じ終え方にそろえる。
- **一時領域の分離：** runner が補助 exe を起動するとき、環境変数 `TEMP`・`TMP` を runner の作業フォルダーの下に向ける（`ProcessStartInfo.EnvironmentVariables`）。
  - `%TEMP%\RTRI\001〜010.tmp` の書込みと削除が、利用者が画面で開いている JRSNAP と干渉しない。
  - 作業フォルダーごと消えるので、後片付けも要らない。
  - データ確認図の補助にも同じことをする。
- **`src/LoadPicture/`（`JRSNAP.LoadPicture.exe`、x86、版によらず1つ）：** 1回の起動で NDT を1つ読み、画面の印刷と同じ経路で全ページを組んで、PDF を1つ書く。手順は次のとおり。
  1. 起動時の確認：インストール先の直下に `*.wk0` があれば BUSY で止める。これは利用者の JRSNAP_Input.exe からの引渡しで、待っても消えない。
  2. 作画条件を INI から切り離す：INI を一時ファイルに向けて既定値を読み直し、色をすべて0、ヘッダーを固定（ReportHost）、`G_bytObjectViewFlg[3]=1`（ページ番号なし）、`AutoRowFlg` を決定4の値にする。
  3. 読込：前提の手順で読む（`nrwork.dir` を書かない経路）。画面には次のように答え、それ以外の `#32770` は失敗にする。
     - `frmSakugaOption`（WB ブロックがあるとき）：「一般荷重」
     - `frmSetPaper`：A4・縦・縮尺自動
     - `frmLoadLayout`：OK
  4. 読込後の確認：`WG_bytSystemDataFlg == 2` であることを確かめる。`WG_bytAutoCaseFlg = 0` は手順3の中、`MDF_Get_NDTData` と `MSI_Chk_NDTData` の間で行う。
  5. ページを組む：`mnuFilePrint_Click` の直前に `G_bytObjectViewFlg[3]=1` にする（コンストラクターの `MDF_DataFormat` が0に戻すため）。`frmPreView` を開き、`C1PrintDocument_prev` の生成が終わってページ数がケース数と同じになったら `Export` し、`frmPreView` を閉じる。閉じてよい根拠：5.2 のメタデータにも 5.3 のソースにも、`frmPreView` の Closing・Closed の処理はない。試作でも問題なかった。アプリ自身の文書と画面の印刷の経路だけを使うので、頼る内部の処理が少なく、画面で印刷したものと同じページになる。
  6. 結果を返す：ページごとのケースを `G_strCaseTitle[1..G_intCaseNum]` から返す（`[{page, case, title}]`）。
- **`figures` のコマンド：**

  ```text
  figures --input <ndu> --output-dir <dir> [--data-check <図,…> [--data-check-case <n>]]
          [--load-diagram <組合せ>,…] [--timeout-seconds <n>] [--config <json>]
  ```

  - どちらか一方は必ず指定する。
  - 処理：NDT を1回だけ書き（`WriteNdt`）、データ確認図の補助を1回、荷重図の補助を指定された組合せごとに1回起動する。
  - 成果物：
    - データ確認図：`<図>.pdf`（kind `data-check`）
    - 荷重図：組合せごとに `load-diagram-<組合せ>.pdf`（kind `load-diagram`、その NDT の全ケースのページ）
  - `summary.loadDiagram`：組合せごとの NDT の名前・SHA256・ページとケースの対応。ページの選び方（どのケースをどの組合せから取るか）は WebPier が持つ。
  - 排他：mutex は取らない。インストール先に書かず（INI は一時ファイル、`.lpd` を書かない、メニューの経路を使わない）、一時領域（`RTRI`・`C1Pdf`）も分けたので、要らない。段階0で、インストール先に何も書かないことを確かめた。
  - `data-check` コマンドと `DataCheckOptions` は消す。
- **テスト：** `UnitTests` に引数の解析（組合せの重複、どちらもないとき）を加える。`RunnerProcessTests` にインストールがあるときの実行を加える（0720 で組合せ1・2、CASE-6 が組合せ2のページにあること）。
- **README：** コマンド・成果物・失敗の種類を書く。
- **ビルド：** `dotnet build JRSNAPHeadless.slnx -c Release` で、`bin\Release` に `JRSNAP.LoadPicture.exe` が入るようにする。

### 2〜5 の結果 — 済み（2026-10-18）

HEAD d26c394（決定54）の上で、作業ツリーにある。

- **品質ゲート：** `.claude/check.ps1` は `overall: pass`、3132 passed。カバレッジは core・inputs・calc・export・pipeline が 100%、reporting 99.45%、gui 94.55%。
- **作り直し：** `pre/input.json` から `--stage all --overwrite` で作り直した（本物の runner）。
  - 0710 は 17 ページ：10.1 → データ確認図5 → 10.2（末尾に 10.3 の見出し）→ 荷重図8 → 10.4（新しいページ）。
  - 0720 は 19 ページ：同じ形で、荷重図は9ページ。CASE-6 だけ組合せ2の NDT から描き、CASE-5・6 の両方に N=480 がある。
- **受入：** `scripts/accept_jrsnap_figures.py` → `tests/fixtures/acceptance/jrsnap_figures/record.json`（本物の 5.2-L03 runner、engineVersion `1.0.0+2374a5b…`）。
- **`bin\Release`：** 22:41 に `figures` へ作り直した（`JRSNAP.LoadPicture.exe` を含む）。
- **差し込みの仕組み：** `reporting/stages/insertion.py` に1つにまとめた（`Insertion(name, key, before, optional)`）。計算書は、全段階で `pages: Mapping[str, bytes]` を受け取る。

以下は、書いたときの計画（記録として残す）。

### 2. WebPier：ページの差し込みを1つの仕組みにまとめる（0611 のコミットの後）

- **reporting（assembly）：** 「原稿を単位のキーで分け、各位置にページを挟む」関数を1つ置き、0610・0620、0611、0710・0720 で共有する。
  - 差し込みの指定は「どの単位のキーの前、または見出しの後か」と「ページ（bytes）」の組の並び。
  - 見出しの後に挟む場合は、その見出しを見出しの書体の段落として前の文書の最後に置く。いまの `load_diagrams.documents` の処理を、この関数の中に入れる。
  - 0611 のセッションが `page_range` と `column_check.parts` で作った形に合わせ、その形を一般化する。
  - `render_with_pages`・`load_diagrams.documents`・`data_check.py` は、この関数に置き換えて消す。
- **計算書に渡すページの型をそろえる：** `StageSpec.render` は `(results, pier, path, pages)` を受け取り、`pages` は差し込みの名前からページの bytes への対応にする。
  - 0610・0620：`load_diagram`
  - 0710・0720：`data_check`・`load_diagram`
  - 0611：節の ID

  各エンジンの結果（FEMPython の荷重図、JRSNAP の `figures`、Capacita の節とページ範囲）をこの対応に直すのは、pipeline の各エンジンのモジュールで行う。`generate.py` には、段階ごとの分岐を置かない。
- **`export/jrsnap`：** 純粋な関数 `diagram_combinations(model: NduModel) -> tuple[tuple[int, int], ...]` を加える。基本ケースごとに、そのケースを使う最初の組合せの番号を返す。どの組合せにも使われないケースがあれば `ValueError` にする（いまの 0710・0720 では起きない）。
- **`pipeline/stages.py`：** `data_check: str` を `jrsnap_figures: JrsnapFigures | None` に替える。`JrsnapFigures` は2つの値を持つ。
  - `export="jrsnap"`
  - `load_cases`：results から、NDU を書くのと同じ `NduModel` を作って上の関数を通す。

  登録表の検査（出力がある、計算書がある、FEMPython の `load_diagram` と併用しない）は、0611 の形に合わせて直す。
- **`pipeline/jrsnap.py`：** `draw_data_check` を `draw_figures(name, document, runner, load_cases)` に替える。
  - 使う組合せ（`load_cases` の組合せの集合）を `--load-diagram` に渡す。
  - 成果物の名前・順序・kind が依頼どおりかを確かめる。
  - 返ったページとケースの対応から、ケースの順に `page_range` で1ページずつ取り出して、荷重図を1つの PDF にまとめる。依頼したケースがないとき、または1ケースが1ページでないときは失敗にする。
  - 結果は差し込みの対応（`data_check`・`load_diagram`）と `engine_version`・`summary`。
  - 待ち時間は、データ確認図の分に荷重図の分を足す。
- **`pipeline/generate.py`：** NDU の付帯JSONの `data_check` を `jrsnap_figures` に替え、次の4つを記録する。
  - 計算書
  - `engine_version`
  - データ確認図（組合せ、図）と荷重図（`[{case, combination}]`）
  - `runner_summary`

### 3. WebPier：帳票（0611 のコミットの後）

- **`reporting/stages/seismic_longitudinal.py`：**
  - `_combinations` の前に「10.3 荷重図」の見出しを置き、作用の組合せを「10.4 作用の組合せ」にする。
  - 差し込みは段階2の関数で2か所に行う。
    - 10.2 の前：データ確認図（新しいページから）
    - 10.3 の見出しの後：荷重図（10.4 は新しいページから）
  - モジュールの説明文も書き直す。
- **`seismic_transverse.py`：** 0710 と同じ形にする（11.3 荷重図、11.4 作用の組合せ）。
- GridLayoutPdf は変えない（必要な機能はない）。

### 4. テスト（品質ゲート `.claude/check.ps1` を通す）

- **代役の runner（`tests/fixtures/jrsnap/fake_runner.py`）：** `data-check` を `figures` に替える。
  - 荷重図は組合せごとに1つの PDF を返す。各ページは `FAKE LOAD DIAGRAM COMB <k> CASE <n> <SHA256の先頭16桁>` で、ページとケースの対応も返す。
  - 誤動作の種類は `FAKE_JRSNAP_FIGURES` で選ぶ。いまの `FAKE_JRSNAP_DATA_CHECK` と同じ種類に、次の3つを足す。
    - ケースが欠ける
    - 対応とページ数が合わない
    - 組合せが欠ける
- **export：** `diagram_combinations`。
  - 例のテスト：0710 は全ケース 1、0720 は CASE-6 だけ 2、どの組合せにも使われないケースは誤り。
  - 性質テスト：返る組合せが「そのケースを使う組合せのうち、番号がいちばん小さいもの」であること。
- **pipeline：**
  - `test_jrsnap.py`：引数（0720 は `--load-diagram 1,2`）、成果物の検査、ケースの順のページの取り出し。
  - `test_generation_data_check.py` → `test_generation_jrsnap_figures.py`：付帯JSONの `jrsnap_figures`、runner の失敗で何も公開しないこと。
  - 登録表のテスト。
- **reporting：**
  - 共有した差し込みの関数のテスト（1か所、2か所、見出しの後、キーの前）。0610・0620・0611 の既存のテストもそのまま通ること。
  - 0710・0720 の意味のテスト：見出しの番号と順。
  - PDF のテスト：ページの順（10.1 → データ確認図 → 10.2・10.3 見出し → 荷重図 → 10.4 が新しいページの先頭）。
- **受入：** `tests/acceptance/test_jrsnap_acceptance.py` の形にそろえ、本物の runner（`.env` があるとき）で確かめて記録する。確かめることは次のとおり。
  - 0710 の荷重図が8ページ、0720 が9ページで、CASE の順であること（各ページのケースのタイトル）
  - 0720 の CASE-5・CASE-6 にどちらも N=480 が描かれていること
  - 白黒の A4縦で、ページ番号がないこと

  記録は `tests/fixtures/acceptance/` の下に置く。決定48で落ちた受入8件のやり直しは、「始める条件」のとおり。

### 5. 生成と文書

- `pre/input.json` から `--stage all --overwrite` で 0710・0720 を作り直し、ページを目で確かめる。
- **決定50・51の書換え：** `figures` の名前、C1 の Export（決定51の「Microsoft Print to PDF」を直す）、画面の印刷の経路でページを組むこと、ページ番号なし、ヘッダーの固定（両方の図）、一時領域の分離、`AutoRowFlg` の値。
- **README（WebPier）：** 0710・0720 の計算書の構成と、付帯JSONの `jrsnap_figures`。
- **CLAUDE.md：** `data-check` を `figures` に。荷重図も同じ runner が描く。
- **スキル `jrsnap-data-check`：** `figures` に合わせ、S_LoadPicture の動かし方（前提の節）を加える。荷重図の分が長くなるなら、`jrsnap-load-picture` として分ける。
- **JRSNAPHeadless の README。**
- **メモリー：** `jrsnap-datacheck-hosting`・`jrsnap-runner-plan`（どちらも `data-check` に触れている）と `jrsnap-ndt-headless` を直す。

## 危険と対策

| 危険 | 対策 |
|---|---|
| 5.2 の挙動が 5.3 のソースと違う（自動ケース分けの強制、`EndApp`、「次へ」の流れ） | 段階0で 5.2-L03 の実物で確かめる。違えば IL で追う |
| 評価版の表示（C1・FarPoint） | アプリ自身の文書と画面だけを使う。出たら画面の自動操作に替える（決定50と同じ方針） |
| 終了の処理で答えが返らない | 終了の処理の前に結果を書いて flush し、閉じずにプロセスを終える |
| 要素荷重の値がともに0の行で NDT 全体が読めない | runner は「要素荷重が不正です」を `NDT_REJECTED` として返す。WebPier は生成を止める。いまの入力では起きない |
| 利用者の JRSNAP との共用（インストール先、`%TEMP%\RTRI`） | `TEMP`・`TMP` を分ける。INI は一時ファイルに向ける。メニューの経路と `.lpd` の書出しを避ける。`*.wk0` があれば BUSY |
| 0611 の作業と同じ箇所の編集が衝突する | 段階2・3は 0611 のコミットの後に始め、その形に合わせる |
| 0720 の組合せの増減（将来の上下線同時載荷など） | 対応を NDU のモデルから求めるので、自動で追う |
