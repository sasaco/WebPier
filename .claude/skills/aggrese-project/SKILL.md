---
name: aggrese-project
description: Aggre-SE（structural-mcp の Batch サブモジュール、Docu-SE）のプロジェクトXML（P1_線路.xml や WebPier の post/線路方向.xml）を読む・項目を画面と対応付ける・Aggre-SE の runner で複製を inspect/run する・Aggre-SE 自身の保存し直しで書式を確かめる。XML の項目の意味、DB1 と横に置くファイル、WebPier の書出し（決定49）を直すとき、0711・0721 の計算書（Aggre-SE の report.pdf そのもの、決定56、webpier/pipeline/aggrese.py）とピックアップ・総括表 post/*_Aggre-SE.pik・.xlsx（決定57・58）や見本 10.5・10.6 との対応を扱うとき、Batch の版が変わって書式を追うとき、耐震照査の入力が Aggre-SE で読めるか調べるときに使う。JRSNAP の解析そのものには使わない。
---

# Aggre-SE のプロジェクトXMLを扱う

Aggre-SE（Batch.exe、Docu-SE）は JRSNAP の解析結果（各 Case の `.DB1` と同じ名前のファイル）を、プロジェクトXMLの照査条件で集計・照査する。WebPier は 0711・0721 でこの XML を `post/線路方向.xml`・`post/線路直角方向.xml` に書き（決定49、`webpier/export/aggrese/`、CONTEXT.md「耐震照査の入力」）、同じ生成で Aggre-SE の runner に照査させた `report.pdf` をバイト列のまま 0711・0721 の計算書にする（決定56、ADR-0009、`webpier/pipeline/aggrese.py`、CONTEXT.md「耐震性能照査」）。Batch のソースは `C:\Users\sasai\Documents\structural-mcp\Batch`。**Batch のファイルは変更しない**。試すときは XML と DB1 のフォルダーの複製を使う。

## 読む

- 宣言は `encoding="utf-16"` だが、中身は **Shift-JIS・CRLF**（XmlSerializer の文字列を Shift-JIS の StreamWriter で書くため）。Batch・structural-mcp・runner はどれも Shift-JIS で読む。宣言を信じて UTF-16 で読まない。
- ケースの配列が長いので、同じ行をまとめて読む（字下げと値の空白はそのまま）：
  `iconv -f cp932 -t utf-8 <xml> | tr -d '\r' | uniq -c | sed -E 's/^ +1 //; s/^ +([0-9]+) /[x\1]/'`
- Python で値を取るときは `ET.fromstring(data.decode("cp932").replace('encoding="utf-16"', ""))`。
- クラスは `Batch/Aggre-SE/datas/*.vb`（`InputData.vb` の `Datas` がルート）、画面の文言は `Batch/Aggre-SE/forms/ChildForm*.Designer.vb`、配列の添字と画面の対応は `ChildForm*.vb` の DataLoad/DataSave。VB のファイルは **UTF-8（BOM 付き）**で、Shift-JIS なのはプロジェクトXMLだけ（`datas/`・`forms/` の38件で確認）。`iconv -f cp932` で読まない。

## 項目と画面の対応（2026-10-18 にコードで確認）

| XML | 画面・意味 | 注意 |
|---|---|---|
| `CaseName/dgCaseList_1`〜`_9` | 照査対象 ①復旧性L2 ②安全性L2 ③損傷レベル ④破壊形態 ⑤せん断耐力 ⑥L1 ⑦基礎の安定 ⑧杭の段落し図 ⑨断面力ピックアップ。Case ごとに -1＝チェック | |
| `SNAP/SnapDBPath` | 解析ケースの DB1。XML のフォルダーからの相対パスか絶対パス | ρm・αf は DB1 の中身（`KihonInfo`）から読み、ファイル名から読まない。5.2 と 5.3 の名付けの違いは問題にならない |
| `Element/_dgLimitLevel_type`・`_La`・`_VydType`・`_SIJI` | 非線形部材（MF＋DL）ごとの部材照査タイプ・せん断スパン La・せん断耐力式（1＝①RC標準）・端部支持条件（-1＝なし）。`dgLimitLevel_typeCount`（先頭に `_` なし）は `_dgLimitLevel_type` の件数を返すプロパティ（`ElementSettingClass.vb:51`） | M-θ 部材の La は DB1 の値で画面が上書きする（編集できるのは 540 の M-φ で L=0 のときだけ） |
| `dgLimitLevel_title`、`_dgLimitLevel`、`_dgLimitLevel2` | 部材照査タイプ1〜5の名前と、損傷レベルの制限値（復旧性・安全性） | |
| `Foundation/基礎照査/clsFoundation` | `FoundationType` 0＝杭基礎、1＝直接基礎。`pointNo` の意味は置き場所で違う：`dgDispAtPoints`（杭基礎）・`dgDispAtPoint`（直接基礎）は変位照査の**節点番号**、杭基礎の `dgReactAtPoint` は反力照査の**要素番号**（`reports/ExcelReport.vb:552-584`）。画面の列「着目番号」の見出しは「要素番号」（`ChildFormFoundationSetting.Designer.vb:300`）だが、直接基礎の計算は節点番号として使う。直接基礎の制限値 `dgLimitValue1`（11件）は空欄なら自動計算 | |
| `Requirement/_rbSpec` | **(0)＝Ⅰ,Ⅱ両方**、(1)＝Ⅰ、(2)＝Ⅱ | 画面の並びと添字が違う |
| `_rbChiiki`、`_rbJIban` | 地域 A・B・C、地盤 G0〜G5（添字0〜5）、(9)＝応答塑性率の直接入力（任意スペクトル） | (9) の μ は XML に入らない。runner には `--spectral-ductility` で渡す |
| `_rbEkijo`、`dgEkijoCase*`、`cbM65Area`、`tbAlfa`、`_cbηx` | 液状化 PL、M6.5以上の震源エリア、低減係数α、不整形性 η(x) | |
| `AtPoint` | 着目節点。正の数はその節点。`0` は DB1 の着目点 `JNo` が正ならそれ、そうでなければ増分解析（`KaisekiFlg=1`）なら例外、それ以外は 1。数でない値（空文字を含む）は例外（`reports/CalculationCase.vb:137-156`） | 画面は空文字のとき DB1 の着目点を表示し、保存でその値を書く |
| `Calculation/_rbProduct` | (0)＝標準仕様、(1)＝カスタム仕様 | |
| `Version` | 保存した Batch.exe の FileVersion | `applyVersion` が変換するのは 1.1.0.11 未満だけ |

配列の長さは XML のまま保たれる。新しく作るファイルは `Option_ケース数`（いま50）件。古い見本は101件。

## DB1 の横に要るファイル

- DB1 と同じ名前の全ファイル（`.R10` などは SNAPDBLib が zip から展開する）。`.xlsx`・`.csv` は Batch の出力。
- `<DB1名>_Output_Chokukiso.csv`：直接基礎の照査値。**JRSNAP の基礎照査機能（`S_SubstCheck.exe`）が書く**。NDU に直接基礎の照査のデータ（`ChokuKisoNum`・`CHOKU_KISO`）があり、「基礎照査機能を起動しますか？」に「はい」と答えたときだけできる。ないとき Aggre-SE は DB1 から求める（`SNAPClass.vb`：`SetChokukisoDB` は CSV があれば読むだけで、`GetChokukisoJoint` などは `OutputInfo.OutChokukiso Is Nothing` のとき DB1 の値を使う）。WebPier の 0711 の結果で試すと、作用は見本と一致し、抵抗側は違った。ただし、JRSNAP の基礎照査との差と NDU の `FootInfo` の Df・γ2 の差が混ざっており、原因はまだ切り分けていない（決定49の既知の差）。`_Output_PIC.csv`・`_直接基礎照査No1.csv` も同じ機能の出力だが、Aggre-SE は読まない。
- `Aspect-SE_*.csv`：任意スペクトルのとき。

## Aggre-SE の runner で複製を確かめる

runner は `Batch\Aggre-SE\Headless\bin\Release\AggreSE.Headless.exe`（使い方は `Batch/Aggre-SE/Headless/README.md`）。XML と DB1 のフォルダーを一時フォルダーへ複製し、`--snap-map` に `{"<Case index>": "<DB1 の絶対パス>"}`（XML の `SnapDBPath` の全件と一致）を書く。

```powershell
& $exe inspect --input <copy.xml> --output-dir <空のフォルダー> --snap-map <map.json>
& $exe run --input <copy.xml> --output-dir <空のフォルダー> --snap-map <map.json> --summary-xlsx true --report-pdf true --check-tables false --pik false --pile-anchor-bar-pdf false
```

成功は envelope の `ok: true` と `summary.cases[].aggregated`。`engineeringStatus` は `not_evaluated` で、OK/NG は `report.pdf` で見る。読めることと照査に合格することを混同しない。

## Aggre-SE 自身に保存し直させる（書式の確認）

`scripts/aggrese_project_roundtrip.cs` は、Batch.exe を参照して画面の「開く」「上書き保存」と同じ `Input.SetXmData` → `applyVersion` → `Input.GetXmlData` → Shift-JIS の StreamWriter を行う（画面の DataSave/DataLoad は通らない）。

```powershell
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /platform:x86 /out:<dir>\Roundtrip.exe scripts\aggrese_project_roundtrip.cs
& <dir>\Roundtrip.exe 'C:\Users\sasai\Documents\structural-mcp\Batch\Aggre-SE\Headless\bin\Release' <in.xml> <saved.xml>
```

- csc は **PowerShell から**呼ぶ。Git Bash は `/nologo` などをパスに書き換えて失敗する。
- 保存し直すと、名前空間の宣言の順（`xmlns:xsi` が先）、`Version`、`_dgLimitLevel_SIJI`・`_ParagraphLength` など、いまの Batch の書式に変わる。WebPier の書出しは、保存し直しても**バイト列が変わらない**ことを受入にしている。
- テストの期待値（`tests/fixtures/example2/aggrese/`）は、見本を手で直して（配列50件、DB1 のパス）これで保存し直したもの。手順は同じフォルダーの `notes.md`。

## WebPier の書出しを直すとき

- 入力は `耐震設計条件`（地域別・地盤区分）だけ。ほかの条件は見本 `P1_線路.xml` の通りの WebPier の定め（`webpier/export/aggrese/writer.py` の定数、決定49）。利用者に聞かずに入力を増やさない。
- Batch の版が変わったら：見本を保存し直して書式の差を見る → `writer.py` の `BATCH_VERSION` と並びを合わせる → 期待値を作り直す（`notes.md` の手順）→ `scripts/accept_aggrese_project.py --overwrite` で受入を取り直す（本物の JRSNAP で 0711・0721 を生成するので数分かかり、画面が出る）。
- 受入記録は `tests/fixtures/acceptance/aggrese/record.json`。入力（`current.json`）や生成する XML が変わると `tests/acceptance` が失敗する。

## 0711・0721 の計算書・ピックアップ・総括表（決定56〜58）

- WebPier の生成が `run --input <ステージングした XML> --output-dir <空の一時フォルダー> --snap-map <map> --summary-xlsx true --report-pdf true --check-tables false --pik true --pile-anchor-bar-pdf false` を呼ぶ（決定56〜58。返る成果物は result.json・report.pdf・pickup.pik・summary.xlsx の4つ）（`.env` の `STRUCTURAL_MCP_AGGRESE_RUNNER`）。1方向 4 秒ほど（2026-10-19、実アプリ）。runner は DB1 のフォルダーに何も書かない（実アプリで確認）。WebPier は呼ぶ前後で XML とフォルダーの SHA を比べ、変わっていれば生成を止める。
- `report.pdf` の構成（実アプリで確認、Batch 5.3.0.1）：Case ごとに7ページ（荷重～変位曲線と水平震度の表、非線形応答スペクトル法の算定、変位図、M・S・N 図、損傷状況図）、続けて応答値一覧表、設計総括表（A3 横）、安全率一覧表、直接基礎の照査（A3 横）。線路方向は11ページ、線路直角方向（2 Case）は18ページ。1ページ目の見出しは DB1 の `KihonInfo.Title`（NDU の題名）と `Comment`（空なら DB1 の名前）で、`reports/PDFReport.vb` の `Create荷重変位曲線`（コードで確認）。見本 10.5・10.6 の見出しは作成者が書き込んだもので、WebPier は再現しない。
- 帳票は毎回同じバイトにならない（同じ入力で SHA が変わった。実アプリ）。
- ピックアップ（決定57）：同じ呼び出しを `--pik true` にすると `pickup.pik`（kind `pickup-pik`、`text/plain; charset=shift_jis`）も返り、WebPier は `post/線路方向_Aggre-SE.pik`・`post/線路直角方向_Aggre-SE.pik` にそのまま書く。書式は FEMPython の PIK と同じ行で、先頭行 `Batch ver1.0.0`、Shift-JIS・CRLF。ピックアップは `reports/ExcelReportPickUpFile.vb` の `GetPickUpFile` で、`Option_PickUpFileCase = 0`（既定）なら3つ：1＝L1地震動（`復旧性_L1震度step`）、2＝復旧性L2（`復旧性_最大応答step`）、3＝安全性L2（`安全性_最大応答step`）。どれも照査対象 ⑨断面力ピックアップ（`_解析対象(8)`）の全 Case について、ステップ 0〜そのステップの各部材の両端の M・S・N の最大・最小。`Option_PickUpFileCase > 0` だと普通地盤・液状化・応答変位法に分けた10個になる（コードで確認）。同じ入力で同じバイト（実アプリで確認）。線路方向は109行・11 KB（部材1〜6）、線路直角方向は127行・13 KB（部材1〜7）。部材の番号は JRSNAP の骨組のもので、着目点は ITAN・JTAN だけ。`post/線路方向.pik` は 0611 の FEMPython の PIK なので、名前を分けている。
- 総括表（決定58）：`summary.xlsx`（kind `summary-xlsx`、約27 KB）。シートは応答値一覧表・設計総括表・安全率一覧表・直接基礎の4枚（計算書の最後の4ページと同じ）。zip の中の日時は 1980-01-01 で固定だが、`xl/workbook.xml` の `documentId`、各シート・図の `xr:uid`・`a16:creationId` の GUID と `docProps/core.xml` の `dcterms:modified` が毎回変わるので、同じ入力でもバイトが変わる（2026-10-19、2回作って比べた）。WebPier は `post/線路方向_Aggre-SE.xlsx` に書き、zip であることだけを確かめる。受入はシート名の並びを記録する。
- runner の成果物は引数で決まる：`--report-pdf false --pik true` なら `result.json` と `pickup.pik` だけ、`--summary-xlsx false --report-pdf true --pik false` なら `result.json` と `report.pdf` だけ（実アプリで確認）。`summary.outputs` に作ったものの名前が並ぶ。WebPier は成果物の組（kind と relativePath）が求めたものとちょうど一致しないと止める。
- 見本との対応（2026-10-19、見本を画像にして確認）：`10_線路(耐震).pdf` の 13〜21 ページ（10.5）は Case ごとの上の7ページと設計総括表・直接基礎の照査（A3 を A4 に回転して縮小）、22・23 ページは JRSNAP の基礎照査の出力（地盤反力分布図と「直接基礎底面回転ばねの算定値」のリスト。Aggre-SE の出力ではない）、24〜26 ページ（10.6）は応答値一覧表・設計総括表・直接基礎の照査。`11_直角(耐震).pdf` は 14〜27 ページで、見本は Case1 だけ。見本の Aggre-SE の版は古く、直接基礎の照査の見出しが「1.復旧性（性能レベル1）…3.安全性」（いまの Batch は「1.安定レベル1…3.安定レベル3」）。見本にない安全率一覧表は、いまの Batch が出す。
- 見本の PDF は 13 ページ以降がほぼ画像で、`pdftotext` では読めない。`uv run --project . --locked --group dev python -X utf8` で `pymupdf` を使い、ページを PNG にして見る（文字の取り出しは見出しだけ）。
- `scripts/accept_aggrese_project.py`（決定49の受入）も 0711・0721 を生成するので、いまは Aggre-SE の runner が `.env` に要る。スクリプトを書き換えると記録の helpers の SHA が変わり、受入のやり直しが要る。
- 受入は `scripts/accept_aggrese_report.py --overwrite`（本物の JRSNAP で生成するので数分かかり、画面が出る）。記録は `tests/fixtures/acceptance/aggrese_report/record.json`。応答値は2ページ目の文字（`Ｋheq = …`・`δeq  = … mm`・`μ = …`・`δr = μ・δeq = … = … mm`・`Khr = …`）から読む。線路方向は見本 10-14 と一致する。

## 直接基礎のステップ表（決定60、`--foundation-steps`）

- runner の `run` に省略可の `--foundation-steps true` を足すと（既定 false。`inspect` では拒否）、XML の `Foundation/基礎照査/clsFoundation/FoundationType` が 1（直接基礎）のとき `foundation-steps.csv`（kind `foundation-steps-csv`、`text/csv; charset=utf-8`、UTF-8・CRLF・BOM なし）が返る。杭基礎（PHC 見本は 0）では何も返らず、失敗にもならない。WebPier の 0711・0721 は常に付けて `post/線路方向_Aggre-SE_直接基礎.csv`・`post/線路直角方向_Aggre-SE_直接基礎.csv`（kind `steps`）に書き、付帯JSONに列の並びを記録する（`webpier/pipeline/aggrese.py` の `FOUNDATION_STEPS_COLUMNS`）。
- 列は `case_index`（0 始まり）, `case_name`（DB1 の名前）, `node`, `step`, `V`, `H`, `M`, `qvd`, `qd`, `Rvd`, `Mmd`, `plasticity`。節点は `SNAPClass.GetChokukisoJoint()`（`OutputInfo.OutChokukiso` の `JoNo ≠ 0`）。`V`・`H`・`M` は `CSNAPDBEx.ChokukisoVd/Hd/Md(istep, node, 2)`（支点ばね反力 `JibanHanryoku` の合計。VB の `Single` で足すので 16825.970703125 のような値。`H` は符号付きで線路方向は負、`M` は絶対値）、`qvd`〜`plasticity`（`Sosei`、比）は `ChokuItem(min(istep+1, Count−1))` の JRSNAP の値のまま。数値は `"R"` 形式（丸めない）。
- `step` の番号（本物の DB1 で確認、2026-10-19）：`StepCtrl(istep)` ↔ `ChokuItem(istep+1)` ↔ JRSNAP の出力リストの増分ステップ番号 `istep+1`。`StepCtrl(0)`・`ChokuItem(0)`・`ChokuItem(1)` は初期状態（H=0）。見本 10-23 の「増分ステップ＝31、荷重増分ステップ数 360」は `StepCtrl(30)`（`LoStepNo=360`、H 5747.86・M 52784.78）＝ CSV の step 31 と一致。`IChokukiso.RvdStep`（JRSNAP 自身の Rvd到達ステップ）は、CSV で `V ≧ Rvd` になる最初の `step` と一致する（線路方向 32、直角 Case1・Case2 とも 33。見本の 31 と違うのは Df 4.70／γe2 の既知の差）。Rvd 到達後は JRSNAP が `ChokuItem` を到達ステップの値に固定するので `qvd`〜`plasticity` は変わらず、`V`・`H`・`M` だけ進む。
- DB1 を画面なしで覗くには PowerShell で SNAPDBLib を反射で読める：`[Reflection.Assembly]::LoadFrom('<Headless\bin\Release>\SNAPDBLib.dll')`、`$db = New-Object SNAPDBLib.CSNAPDB; $db.DataRead($db1)`（0 なら成功）、`$db.InputInfo.KihonInfo`（`KisoType`・`LastStep`・`JNo`）、`$db.OutputInfo.StepCtrl[i].LoStepNo`・`.JointItem[n].JibanHanryoku`、`$db.OutputInfo.OutChokukiso[k].RvdStep`・`.ChokuItem[j]`。`.OUT` はパスワード付き zip で読めない。
- Batch 側のテスト（`Batch/tests/Aggre-SE.Test/HeadlessRunnerTests.cs`）は PHC（杭）で CSV が返らないことと、直接基礎（既定 `..\WebPier\post\線路方向.xml`、`AGGRE_SE_TEST_DIRECT_FOUNDATION_XML` で差替え、無ければ skip）で各行を `CSNAPDBEx` から読み直して照合する。`summary.outputs` は result.json を含まず、帳票を作らない呼び出しでは `cases[].aggregated` が false になる（既存仕様）。

## post の出力を作る・最新か確かめる

- 作る：`uv run --project "." --locked python -m webpier --stage 0711 --overwrite`（0721 も同じ。両方なら `--stage all --nonlinear-analysis --overwrite`）。依存段階は内部で計算するだけで、0711 を選んだ生成が書くのは `output/0711_線路方向非線形解析.pdf`・`.json` と `post/` の `線路方向_JRSNAP/`・`線路方向.xml`・`線路方向_Aggre-SE.pik`・`線路方向_Aggre-SE.xlsx` と各付帯JSON。1方向数分かかり、JRSNAP の画面が出る。`.env` に JRSNAP と Aggre-SE の runner が要る。
- 最新か確かめる（作り直す前に）：付帯JSONの `input.sha256` を `pre/input.json` の SHA256 と、`implementation_sha256` を `canonical_sha256({str(p): d for p, d in webpier.pipeline.runtime.dependency_hashes().items()})` と比べる。両方一致すれば、いまの入力と実装で作ったもの（2026-10-19、「出力して」と言われて確かめた手順）。総括表と計算書はバイトが毎回変わるので、ファイルの SHA256 どうしを比べて新旧を判断しない。
- 同じ作業ツリーで別のセッションが `CONTEXT.md` などを編集していることがある。コミットは `git commit --only <自分のファイル>` で、他人の差分を含めない（`git diff -U0` で自分の差分か確かめる）。

## 知見を更新する

新しく確認した項目の意味、画面との対応、Batch の版による書式の違いをこのスキルに反映する。コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
