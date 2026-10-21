---
name: webpier-capacita
description: WebPier が Capacita（RcDan、旧名 WebDan）で行う断面照査の実装と決定を扱う。0611・0621 の柱の断面照査（決定48、ADR-0008、webpier/calc/column_check.py・export/capacita/wdj.py・pipeline/capacita.py・reporting/stages/column_check.py、point_index、計算書 8.5〜8.9・9.5〜9.9 への差し込み、省略の理由の印刷 OMITTED）、0910 の片持ち梁（決定59、cantilever.py）と 0810・0820 のフーチング（決定60、footing_wdj.py）の断面力入力モードの WDJ、代役の runner（tests/fixtures/capacita/fake_runner.py）、受入 accept_capacita_column.py、見本 Example橋脚2 の WebDan.wdj・08_線路.pdf・09_直角.pdf との対応に使う。Capacita そのもの（WDJ の落とし穴、run-rc --pickup、reportSections、WD-19xx の省略）はスキル structural-capacita を使う。
---

# WebPier の Capacita の使い方（0611・0621・0810・0820・0910）

**Capacita 自体（WDJ の項目と落とし穴、`run-rc --pickup`、`reportSections`、断面力0で飛ばされる照査 WD-1901〜1913、断面力入力モード、側方鉄筋の既定、Capacita を直すときのビルドとテスト）はスキル `structural-capacita` を参照**。ここには WebPier の実装・決定・受入・見本との対応だけを書く。照査の式・表・印字桁は Capacita の責務なので、足りなければ Capacita 側を直す。

0611（線路方向）・0621（直角方向）は骨組解析（FEMPython）の `.pik` を設計応答値として、柱下端の1断面を Capacita で照査し、その `report.pdf` のページを計算書（8.5〜8.9・9.5〜9.9）に差し込む（決定48、ADR-0008、CONTEXT.md「柱の断面照査」）。2方向の違いは `calc.column_check.Direction`（LONGITUDINAL・TRANSVERSE）と `reporting.stages.column_check.Chapter`（8・9）だけ。WebPier は WDJ を書いて runner を呼ぶだけで、`.pik` の断面力は読まない（着目点の番号だけ並びから求める）。骨組解析は同じ FrameWeb 入力の基礎の照査（0612・0622）と共有し、1回の生成で1回だけ行う（決定54。スキル webpier-foundation）。0612 だけを選んだ生成でも `.pik` は書き換わるが、0611 の `.wdj` は残る。

## 置き場所

| もの | 場所 |
|---|---|
| WebPier の計算・WDJ・runner・帳票 | `webpier/calc/column_check.py`、`webpier/export/capacita/wdj.py`、`webpier/pipeline/capacita.py`、`webpier/reporting/stages/column_check.py` |
| runner | `.env` の `STRUCTURAL_MCP_WEBDAN_RUNNER`（`<Capacita>\WebDanforCS\Headless\bin\Release\net8.0\WebDanforCS.Headless.exe`。旧名のまま） |
| runner の契約（引数・`--pickup`・`reportSections` の節の ID） | Capacita の `README.md` の「Headless runner の run-rc」（スキル `structural-capacita`） |
| 代役の runner・期待値・受入 | `tests/fixtures/capacita/fake_runner.py`、`tests/fixtures/example2/column_section_check.json`・`column_section_check_09.json`（注記 `_notes.md`）、`scripts/accept_capacita_column.py [0611|0621]` → `tests/fixtures/acceptance/capacita/record.json`・`record_0621.json` |
| 見本 | `.claude/docs/Example橋脚2/08_線路.pdf` の 12〜26 頁、`08_線路/WebDan.wdj`・`frameWebForJS.pik`（直角方向は `09_直角.pdf` の 16〜23 頁と `09_直角/`） |

## WDJ の書き方（WebPier の決め）

- 見本の `WebDan.wdj` は旧 WebDan の形式（`shape: "矩形"`、`steel` キーあり、`bar[].position: "6.250"`）。WebPier は `shape` を番号で、整数の項目を JSON の整数で書き（`wdj.py` の `_number`）、`steel` と `bar[].position` は書かない（理由は `structural-capacita` の「WDJ の落とし穴」）。
- **着目点の番号**：`export.capacita.point_index(pik, member)` で PIK から求める。0610 は途中点がないので柱下端は 6 だが、0620 は柱（部材3）に風荷重の区間の端（I端から 2.900m）があるので 7（見本 09 の PIK は 6）。代役の FEMPython も FrameWeb の部材荷重から同じ途中点を書く。
- `calc.print_section_force_checked: true` で断面力一覧表が先頭に付き、8.5 になる。
- `result.json` に照査値も OK/NG もないので、WebPier も「照査を実行した」ことだけを記録する。
- 安全係数表の γi（復旧性（損傷）地震時以外）は運輸機構・JR各社 1.2。見本の解説 8-25 の「γi＝1.0」は運輸機構では誤り。
- 見本の耐力は今の Capacita と少し違う（Mud 37449.1 → 37426.2、Myd 38260.8 → 38200.7）。見本自身の WDJ を今の Capacita で計算しても同じ差が出るので、見本を作った WebDan との違い。照査値（0.132、0.114）は一致する。

## 手で試す（WebPier）

1. 見本の WDJ を Capacita で試す手順と、頁を画像にする手順は `structural-capacita` の develop.md。
2. WebPier の生成を本物の runner で通すなら、出力先を scratchpad に向ける（`output/` を書き換えない）：
   `uv run --project "." --locked python -X utf8 -m webpier --input tests/fixtures/inputs/current.json --output-dir <dir>/output --post-dir <dir>/post --overwrite`（入力は `outputs` の `transverse_frame_analysis` と使う項目を選んだ current.json の写し。数秒。結果JSON の `section_check.skipped_sections` に飛ばされた節）。
3. WebPier の WDJ を本物の PIK で試すときは、`export_bytes(pier, "0620", "frameweb")` を `fempython.analyze_frame` に渡して PIK を得て、`point_index(pik, check.member)` で番号を求めてから `build_wdj` する。
4. 受入：`uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py 0611`（照査値を見本と比べる）／`… 0621`（耐力と飛ばされた照査を比べる）。WDJ が変わると `tests/acceptance/test_capacita_acceptance.py` が落ちるので、そのときにやり直す。

## 直すとき（WebPier 側）

- Capacita の節の ID を変える・足すと、WebPier の `pipeline/capacita.py`（求める節の集合、頁範囲が PDF を順に隙間なく覆うことの検査）と代役の runner も合わせる。
- 代役：Capacita の代役は `FAKE_CAPACITA=skip`（耐久性のせん断・使用性を WD-1906・WD-1901 付きで抜く）と `skipnocode`（コードなしで抜く）で省略を真似る。FEMPython の代役の PIK は1行目が `FAKE PIK <名前> <SHA256>`（見出しの代わり）で、その後に FrameWeb の部材荷重の区間の端から途中点を足した本物と同じ並びの着目点を書くので、`point_index` は本物と同じ番号になる。
- 地震時の照査に使える PIK（まだ使っていない）：0711・0721 は Aggre-SE のピックアップを `post/線路方向_Aggre-SE.pik`・`post/線路直角方向_Aggre-SE.pik` に書く（決定57、スキル webpier-aggrese。書式はスキル structural-aggrese）。ピックアップの番号は 1＝L1地震動・2＝復旧性L2・3＝安全性L2で、抽出ケースの番号（1 安全性（破壊）…）とは対応しない。部材の番号は JRSNAP の骨組（線路方向 1〜6、線路直角方向 1〜7）で、FrameWeb の部材番号ではない（2026-10-19、本物の出力で確認）。Capacita に渡すなら、`point_index` や WDJ の着目点をこの骨組から求め直す必要がある（別の決定）。
- `run-rc` のやり取りを変えたら代役の runner も更新する。本物の runner のテスト（`tests/pipeline/test_capacita.py`）は `.env` があるときだけ走り、その失敗が合図。

## 片持ち梁の断面照査（0910、決定59）

- 0910 は `run-rc` を `--pickup` なしで呼ぶ（`pipeline/capacita.py: check_section`）。WDJ（`export/capacita/cantilever.py`）の `force[0]` に 0900 の採用値を書き（Md0・1・3〜7、Vd0〜7、Mt0・1・5・6・7。Md は負＝上側引張）、Capacita はそのまま計算して `result.json`・`report.pdf` の2つだけを返す（`model.wdj` は返らないので、公開する `post/片持ち梁.wdj` は WebPier が書いたもの）。
- 返る節の並びと WD-408/409/410 は `structural-capacita` の wdj.md（Md8 最小鉄筋量は空欄なので WD-408 が1つ出る）。省略コードと節の対応は `pipeline.capacita.SKIPPED`。
- 疲労の ΣN は Capacita が計算する。見本の 10.39 は外部プログラム N-EQUIVALENT の値で、入力 `片持ち梁の照査.疲労` から写す。
- せん断スパンは `shear[0].La` に **mm** で書く（`export/capacita/cantilever.py` の `_millimetres`。計算の `calc/cantilever/check.py` の `shear_span` は m のまま）。Capacita は La を mm として読む（スキル `structural-capacita` の wdj.md）。2026-10-19 まで m（`La: 1.55`）で書いていて、1.55 mm として計算され、計算書に「せん断スパン長 (mm) 1.6」「せん断スパン比 0.001」と出て βa が上限 5.000 に張り付き、安全性（破壊）のディープビームの耐力 Vdd を 15179.9 kN と過大に見積もっていた（1550 mm で 11134.6 kN、照査値 0.415 → 0.566）。直した。それより前に作った `post/片持ち梁.wdj` と 0910 の計算書は作り直す。 見本の WDJ の `points[0].La: 1` は「自動算定」（|Md/Vd|）の意味で、今の RcDan は `points` の La を読まず `shear` 表から読む。
- 代役の runner は `--pickup` なしのとき WDJ の `force` の行から節を決める（`tests/fixtures/capacita/fake_runner.py: force_sections`）。0810・0820 のフーチングの WDJ も同じ規則で 5 節になる。

## 直角方向（0621）と照査の省略

- 解説の文は見本 08 と 09 で同じで、違うのは節の番号（9.5〜9.9）だけ。WDJ の `basic`・`safety`・ひび割れの行も 08 と同じ（`column_section_check_09.json` の `same_as_08`）。
- 直角方向は永久作用が左右対称なので Example2 では WD-1901・1906 が出る。見本 09 に 9.7・9.8 がないのはこのため。`pipeline.capacita.SKIPPED` が節とコードの対応で、コードのある欠けだけを認め、計算書は省略の理由を印刷する（`reporting.stages.column_check.OMITTED`）。
- **直角方向の配筋**：表の主鉄筋は直角の面の D19×9（芯 102）。線路の D32 の隅の鉄筋は両面から 108 にあるので側方鉄筋の側になり、その芯は 108, 300…4200, 4392（両端だけ 192）。見本どおり `side_cover`・`side_ss` を空欄にし、RcDan が上下の主鉄筋の間に等分（芯 245.2 から 143.2 間隔）、側方の芯かぶりは主鉄筋の芯（102）にする。隅の鉄筋の判定は `calc.column_check.corners`。
- 安全性（破壊）の曲げは側方鉄筋を数えない。直角方向の耐力は見本と 0.2% 未満の差（Mud 29326.7／29334.2、Myd 48634.5／48663.2）。
- 見本 09 の照査値（0.338、0.098）は WebPier と比べられない。WebPier の 0620 の風荷重（決定12・35）は見本と違い、柱下端の Md が違う（安全性（破壊）10939.1／見本 8256.6）。N'd は同じ（13264.1、14404.5）なので受入は耐力で比べる。見本自身の WDJ（`shape` を `"1"` にした複製）を今の Capacita で計算すると 0.338・0.098 が再現するので、WebPier の WDJ との違いは断面力だけと確かめられる。
- 省略の理由の文は解説の後に空き1行を置いて組む（`_blocks` はキーが `.omitted` で終わる単位で区切る）。省略した節の後は Capacita のページを挟まず、次の節の文書が新しいページから始まる。

## フーチングの断面照査（0810・0820、決定60）：断面力入力モードの WDJ

- `webpier/calc/footing_check.py` が条件を組み（部材「フーチング」1000×H6 mm、下側の主鉄筋とスターラップ、材料、`柱の断面照査` の条件、Dmax は `鉄筋.フーチング.aggregate_max_mm`（owner 2026-10-19））、`webpier/export/capacita/footing_wdj.py` が WDJ を書く。runner は `pipeline.capacita.check_section`（`--pickup` なし。成果物は result.json と report.pdf だけ。決定59と共用）。代役は `tests/fixtures/capacita/fake_runner.py` の引数7個のモード（5節、1/2/2/1/2 頁、warn WD-408/409）。
- 使う id：0 耐久性 応力度、1 耐久性 永久荷重、5 安全性 破壊、7 復旧性 地震時。せん断スパンは `shear[]` の行の `La`（WebPier は mm の整数で書いている。`FootingCheckResult.la` の注記は mm）。Capacita は La を mm として読むので**正しい**（2026-10-19、本物の runner で m に変えた複製と比べて確認。`MemberGroup.cs:367` の「(m)」のコメントは誤り）。
- **La は着目点ごとに1つ**なので、方向ごとに2点にしている：点1「線路方向」（Md0・Md1・Md5・Vd5、安全性の La）、点2「線路方向（地震時）」（Md7・Vd7、地震時の La）。見本 12 章は安全性 1127・地震時 1819 と別の La を印刷している。
- 上側鉄筋なしは `rebar1` を全部 null で通る。断面力一覧は出ない。見本 p255 の値（Mud 3670.5、0.249）と p258（Vdd 4337.2、0.187）は今の Capacita で再現する。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- Capacita そのものの性質：structural-mcp の `skills/structural-capacita/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0611・0621・0810・0820・0910 の照査の中身の説明は、structural-mcp のスキル `structural-webpier` の checks.md にある（ここには書かない）。差し込む節や省略の扱いを変えたら、そちらも直して structural-mcp で commit する。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
