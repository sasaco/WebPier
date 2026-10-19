---
name: cantilever-check
description: WebPier の 0900・0910 片持ち梁の照査（決定59、CONTEXT.md「片持ち梁の照査」「最大応答震度」）を扱う。0900 の応答値（左右の張出しの幾何、B/C/B+C 支点最大の3載荷と各シューの列車荷重・衝撃、車両横荷重・風・地震時のトルクによる鉛直反力、ゴム支承とストッパーの水平荷重、自重、集計、31 ケースの組合せ、両側のケースから照査ごとに採る規則、Mcrd と ε'csd、Aggre-SE の総括表からの最大応答震度、webpier/calc/cantilever/）、`鉄筋.梁`・`支承データ`・`片持ち梁の照査` の入力、0910 の断面力入力モードの WDJ（export/capacita/cantilever.py、`run-rc` を --pickup なしで）、計算書 13.1〜13.6（reporting/stages/cantilever/・cantilever_check.py、横置きの組合せ表）、見本 13_片持ち梁照査.pdf との既知の差、代役 runner の挙動に使う。見本 13-1〜13-67 と値が合わない、総括表が読めない、Capacita が返す節が合わない、横置きの表が収まらないときにも使う。柱の断面照査は webpier-capacita（Capacita そのものは structural-capacita）、Aggre-SE の runner と総括表は structural-aggrese（WebPier の取り込みは webpier-aggrese）、フーチングは footing-check。
---

# 片持ち梁の照査（0900・0910）

0900 は左右の張出し（|支承位置| > W6/2 の支承枠が載る側）について 13.1 応答値の算定と 13.2 設計作用の組合せを WebPier が計算して印刷し、0910 はその採用値を断面力表に書いた WDJ を Capacita に計算させ、13.3〜13.6 の見出し・解説の後にページを差し込む（決定59、ADR-0008）。2段階とも `--nonlinear-analysis` の段階で、0711・0721 の Aggre-SE の総括表（最大応答震度）を同じ世代で読む。見本 Example2 13 章はロジックと体裁の移植元で、値の一致は求めない（下の「既知の差」）。

## 置き場所

| もの | 場所 |
|---|---|
| 幾何（片持ち梁上の支承 X＝|支承位置|−W6/2、e＝∓f、Y＝(H2+H3)/2、自重 ①②、ΣXi²） | `webpier/calc/cantilever/geometry.py`（`Side.LEFT`＝支承位置が負＝W4、`RIGHT`＝W5） |
| 3載荷と各シューの列車荷重・衝撃、トルクによる鉛直反力 | `loads.py`（`search_reactions(..., objective=Objective.ORIGIN/END/PIER)`、`train_loadings`、`lateral_torques`・`wind_torques`・`seismic_girder_torques`・`seismic_train_torques`） |
| ゴム支承・ストッパーの水平荷重 | `bearings.py`（`bearing_cases`：0600 の安全性4ケース＋地震時、`Device.each`＝桁全体/箇所数、`force`＝片持ち梁上の個数分、`inertia`＝Kh×0600 の桁慣性力） |
| 集計の表（N・X・Md・H・e/Y・Mt） | `actions.py`（`ActionKey(kind, variant)`、行の見出しは全角空白なし：上部工反力・上部工慣性力・列車慣性力） |
| 31 ケース、WDJ の行への採用 | `combinations.py`（`DEFINITIONS`、`evaluate_all`、`FORCE_ROWS`、`adopt`：曲げ |Md|・せん断 Vd・ねじり Mt の最大、同値は左側・先のケース） |
| Mcrd と ε'csd | `crack.py`（`cracking_moment`、`cracking`：自重→450、永久→350、永久＋変動／割れない→300） |
| 総括表の最大応答震度 | `response.py`（`read_max_response(xlsx_bytes, file)`：シート `応答値一覧表`、B列「最大応答震度」をA列「復旧性」「安全性」の区画で、Case 列は D 列から、値は文字列。行番号では探さない） |
| 入口と結果型 | `__init__.py`（`calculate_cantilever`＝runner 前、`complete_cantilever(pier, reaction, basis, longitudinal, transverse)`＝総括表の後、`CantileverResult`） |
| 0910 の照査データ（配筋の写し、環境条件、疲労、断面力） | `check.py`（`calculate_cantilever_section`、`SECTIONS` 15 節）、WDJ は `webpier/export/capacita/cantilever.py`（`build_cantilever_wdj`） |
| 登録表・生成 | `webpier/pipeline/stages.py` の `_cantilever`（0900、依存 0600・0711・0721、`complete` が `seismic_file("0711","xlsx")` 等を受ける）と `_cantilever_check`（0910、`calculate=None`、`complete` で 0900 の完成結果から、`section_check` は骨組解析なし）、`generate.py` の `_completion_files`・`_check_section` |
| runner | `webpier/pipeline/capacita.py` の `check_section`（`--pickup` なし、成果物は result.json と report.pdf の2つ、`ColumnCheckPages.wdj` は渡した WDJ）、`SKIPPED` は WD-1901〜1913 |
| 帳票 0900 | `webpier/reporting/stages/cantilever/`（`__init__`・`vertical`・`horizontal`・`summary`・`combinations`。0600 の manuscript を `Manuscript(prefix="0900/")` で共用。`rotated_table` → `reaction/layout.py` の `_rotated`＝GridLayoutPdf `QuarterTurn`） |
| 帳票 0910 | `webpier/reporting/stages/cantilever_check.py`（`Numbering`：外観の照査を行えば 13.6 使用性・13.7 復旧性） |
| 見本の転記 | `tests/fixtures/example2/cantilever.json`・`cantilever_notes.md`（差の注記も） |
| テスト | `tests/calc/test_cantilever_*.py`（`cantilever_support.py`：`response()`・`workbook()`・`result_of()`）、`tests/export/test_cantilever_wdj.py`、`tests/reporting/test_cantilever_report.py`・`test_cantilever_check_report.py`、`tests/pipeline/test_generation_cantilever.py`、`tests/inputs/test_cantilever_check_parse.py`、`tests/gui/test_gui_cantilever.py` |
| 見本と原資料 | `.claude/docs/Example橋脚2/13_片持ち梁照査.pdf`（13-1〜13-37 応答値と組合せ、13-38〜13-67 解説と WebDan の結果）、`13_片持ち梁照査/WebDan.wdj`（断面力表つき。今の Capacita では `shape` を `"1"` に、`steel` を外して計算できる）、`07_荷重計算/朝里川Bv_P1_荷重計算.xlsm` のシート `§13.鉛直荷重`・`水平荷重`・`片持梁の自重`・`荷重の集計`・`作用の組合せ`（係数とセル参照の読み方はここ） |

## 見本との既知の差（決定59で決めたもの。見本に合わせない）

- スノーシェルターを持たない：風荷重・地震時上部工慣性力のトルクは 0600 の直角方向の力・高さ・モーメント（S2 を含む、hs）から。見本の `+ 1/2 × 120` や `+ 0.552 × 530` の項は出ない。
- 終点側の X は支承位置から 0.700（見本は 0.645 を手打ち）。
- 最大応答震度は総括表の 復旧性・安全性 × 全 Case の最大（線路 0.386、直角 0.571。見本は Case1 安全性の 0.552）。地震時列車荷重の Kh（線路 0.20・直角 0.30）はプログラム定数。
- 使用性の衝撃は安全性の 0.75 倍（見本 13-26 (b) は安全性の値を写した Excel の誤り、ADR-0001）。
- 車両横荷重：B支点最大・C支点最大はその載荷の桁の反力×0.2 を最大化した桁だけに、B+C は 0600 の1両分の載荷（52.71／58.98）を両桁に（見本のとおり）。
- 可動支承の水平力は 13 章のモデル μ·Rm（上限なし）で、0600（7 章）の `min(T/n, max(μRm, μT/n))` とは別。0600 は変えない。
- 組合せの表の値は印刷した部分の和（ADR-0003）で、見本の未丸めの和と末位が違うことがある（Mt 1058.28／見本 1058.29 など）。
- 13.1 (1)(2) は左右共通なので1回、(3)(4)・13.2 は左側→右側。組合せの表は横置き3枚ずつ（1〜9・10〜18・19〜31）、まとめは係数を省いた縦置きで 13.2 の先頭、末尾に採用表。見本の 13-46 の列車通過図・反力推移・ΣN の数値行、支承配置・はり断面のスケッチは描かない。ΣN は Capacita が計算する（WDJ の `fatigues`）。

## 落とし穴（2026-10-19 に確認）

- **総括表は同じ世代の runner の返したバイト列を読む。** post/ の .xlsx は読まない。0900 を単独で選んでも 0711・0721（JRSNAP・Aggre-SE）が走る。3つの runner（JRSNAP・Aggre-SE・Capacita）が要り、本物での生成は数分。
- **`complete` の順序**：Aggre-SE の照査 → 依存段階の `complete`（登録表の順。0900 は総括表、0910 は 0900 の完成結果）→ Capacita。`_completion_files` は依存段階の閉包の耐震性能照査のファイルを `"<stage>/<kind>"` で渡す（0910 にも 0711 のファイルが渡るが使わない）。
- **Capacita（`--pickup` なし）**：`section_forces` は出ない。返る節は断面力表の行で決まる。Md8（最小鉄筋量）を空欄にすると warn WD-408 が1つ出るが問題ない。せん断スパンは `shear[0].La` で、片持ち梁上の最も遠い支承の X。いまは m で書いているが、Capacita は mm として読むので耐力を過大に見積もる（2026-10-19 に見つけた未修正の不具合。詳細はスキル webpier-capacita の「片持ち梁の断面照査」）。`fatigues.train_A_count` 等は文字列。
- **横置きの表**：`QuarterTurn` は1部で分割不可。表の幅（＝回転後の高さ）は本文の高さ 705.72 pt 以下、高さは幅 528 pt 以下。見出しとは同じページに入らないので、見出しの直後には縦置きの表を置く。セルの幅・行の高さは 0.12 pt の倍数（`grid_units`）。全角の文字は約 9.9 pt、半角は約 5.5 pt、クリアランスは 0600 の表が左右 6.99 pt、`compact=True` の表（組合せ）が 4.11 pt。2行のセルは行の高さ 28.56 pt が要る。セルが収まらないと `LayoutOverflowError: line n exceeds available width` で止まるので、幅は文字数から見積もって決める。
- **0600 の manuscript の `wide=True`** は左辺を文字列のラベルにし「ラベル ＝ 記号 ＝ 数値」と組む。記号を左辺にするなら `medium=True`。
- **reporting は計算しない**：ΣR や地震時の桁慣性力など帳票に要る値は calc の結果に持たせる（`SupportLoads` の合計、`GirderDevices.inertia`）。
- **sed で `\n` を含む Python を編集しない**（改行に化ける）。置換は Python のスクリプトで。
- **代役の runner**：Aggre-SE の代役は `応答値一覧表` を持つ本物の形のワークブック（Case n の 最大応答震度 0.385/0.386＋0.01(n−1)、設計総括表 A1 に `FAKE XLSX <sha>`）、Capacita の代役は `--pickup` なしのとき WDJ の `force` の行から節を決める（`force_sections`）。

## 手で試す

1. 計算だけ：`parse_input` → `calculate_reaction` → `calculate_cantilever` → `read_max_response(Path("post/線路方向_Aggre-SE.xlsx").read_bytes(), ...)`（直角も）→ `complete_cantilever`。`result.sides[Side.LEFT].actions`・`.cases`・`result.selections`・`result.cracking` を見る（`tests/calc/cantilever_support.py` の `result_of` が同じ）。
2. 帳票だけ：`render_cantilever(result, reaction, pier, path)`／`calculate_cantilever_section` → `render_cantilever_check(section, pier, path, pages)`。ページは `pymupdf` で画像にして確かめる。
3. WDJ を本物の Capacita で：`write_wdj(build_cantilever_wdj(section))` を scratchpad に書き、`WebDanforCS.Headless.exe run-rc --input <wdj> --output-dir <dir> --output-format pdf`（`--pickup` なし）。envelope の `summary.reportSections` が `SECTIONS` の順で返るか、`messages` に error がないかを見る。
4. 全体：`uv run --project "." --locked python -X utf8 -m webpier --stage all --nonlinear-analysis --overwrite`（本物の JRSNAP・Aggre-SE・Capacita。数分）。

## 直すとき

- 入力を増やしたら `fields.py`・`parse.py`・`model.py`（`CantileverCheck`・`Span` の箇所数）・`pre/input.json`・`tests/fixtures/inputs/current.json`・エディタ（`gui/pages.py` の支承データの表、`gui/rebar_page.py` の 梁「断面照査の条件」）・README の入力の節を一緒に。受入記録（`tests/fixtures/acceptance/*`）は入力の SHA を持つので、`scripts/accept_*.py` でやり直す。
- 組合せを変えるなら `combinations.DEFINITIONS` と `FORCE_ROWS`、見本の `作用の組合せ` シート（係数の列と参照先）を突き合わせる。
- Capacita の節の集合を変えたら `check.SECTIONS`、`pipeline/capacita.SKIPPED`、`reporting/stages/cantilever_check.py` の `OMITTED`、代役の `FORCE_SECTIONS`/`SECTION_OF_ROW` を合わせる。
