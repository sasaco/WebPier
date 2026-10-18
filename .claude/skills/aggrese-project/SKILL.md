---
name: aggrese-project
description: Aggre-SE（structural-mcp の Batch サブモジュール、Docu-SE）のプロジェクトXML（P1_線路.xml や WebPier の post/線路方向.xml）を読む・項目を画面と対応付ける・Aggre-SE の runner で複製を inspect/run する・Aggre-SE 自身の保存し直しで書式を確かめる。XML の項目の意味、DB1 と横に置くファイル、WebPier の書出し（決定49）を直すとき、Batch の版が変わって書式を追うとき、耐震照査の入力が Aggre-SE で読めるか調べるときに使う。JRSNAP の解析そのものには使わない。
---

# Aggre-SE のプロジェクトXMLを扱う

Aggre-SE（Batch.exe、Docu-SE）は JRSNAP の解析結果（各 Case の `.DB1` と同じ名前のファイル）を、プロジェクトXMLの照査条件で集計・照査する。WebPier は 0711・0721 でこの XML を `post/線路方向.xml`・`post/線路直角方向.xml` に書く（決定49、`webpier/export/aggrese/`、CONTEXT.md「耐震照査の入力」）。Batch のソースは `C:\Users\sasai\Documents\structural-mcp\Batch`。**Batch のファイルは変更しない**。試すときは XML と DB1 のフォルダーの複製を使う。

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

## 知見を更新する

新しく確認した項目の意味、画面との対応、Batch の版による書式の違いをこのスキルに反映する。コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
