---
name: webpier-capacita
description: WebPier が Capacita（RcDan、旧名 WebDan）で行う断面照査の実装と決定を扱う。0611・0621 の柱の断面照査（決定48、ADR-0008、webpier/calc/column_check.py・export/capacita/wdj.py・pipeline/capacita.py・reporting/stages/column_check.py、point_index、計算書は Capacita の解説付きの計算書そのもの（決定121：print_commentary_checked、--commentary-chapter、reportSections.heading、0400 の参照番号と 0612・0622 の節番号））、RC標準 R5 への切替（決定73：基準の id、安全係数、水掛かりの程度、使用性（損傷）、行8 と最小鉄筋量及び最大鉄筋量 bending_rebar_amount、省略コード WD-1914〜1926）、0910 の片持ち梁（決定59、cantilever.py）と 0810・0820 のフーチング（決定60、footing_wdj.py）の断面力入力モードの WDJ、代役の runner（tests/fixtures/capacita/fake_runner.py）、受入 accept_capacita_column.py、見本 Example橋脚2 の WebDan.wdj・08_線路.pdf・09_直角.pdf との対応に使う。Capacita そのもの（WDJ の落とし穴、run-rc --pickup、reportSections、WD-19xx の省略）はスキル structural-capacita を使う。
---

# WebPier の Capacita の使い方（0611・0621・0810・0820・0910）

**Capacita 自体（WDJ の項目と落とし穴、`run-rc --pickup`、`reportSections`、断面力0で飛ばされる照査 WD-1901〜1913（H16）・WD-1914〜1926（R5）、R5 の最小鉄筋量・最大鉄筋量の表、断面力入力モード、側方鉄筋の既定、Capacita を直すときのビルドとテスト）はスキル `structural-capacita` を参照**。ここには WebPier の実装・決定・受入・見本との対応だけを書く。照査の式・表・印字桁は Capacita の責務なので、足りなければ Capacita 側を直す。

0611（線路方向）・0621（直角方向）は骨組解析（FEMPython）の `.pik` を設計応答値として、柱下端の1断面を Capacita で照査し、その `report.pdf`（解説付き。8.5・9.5 から番号）の節のページ範囲を順につないで計算書にする（決定48・121、ADR-0008、CONTEXT.md「柱の断面照査」）。2方向の違いは `calc.column_check.Direction`（LONGITUDINAL・TRANSVERSE）と `reporting.stages.column_check.Chapter`（8・9）だけ。WebPier は WDJ を書いて runner を呼ぶだけで、`.pik` の断面力は読まない（着目点の番号だけ並びから求める）。骨組解析は同じ FrameWeb 入力の基礎の照査（0612・0622）と共有し、1回の生成で1回だけ行う（決定54。スキル webpier-foundation）。0612 だけを選んだ生成でも `.pik` は書き換わるが、0611 の `.wdj` は残る。

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
- **解説（決定121）**：`calc.print_commentary_checked: true` で Capacita が各節の照査結果の前に群の見出しと解説を印字し、`run-rc --commentary-chapter 8|9 --commentary-first-section 5`（`reporting.stages.column_check.Chapter.commentary` → `SectionCheck.commentary` → `pipeline.capacita.check_column(commentary=)`）で群の見出しに番号を振る。番号は印字した群に欠番なく振られ、`reportSections[].heading`（群の最初の節だけ、ほかは null）で返る。WebPier は `_headings` で「n.5 から欠番なく」を確かめ、`SectionCheck.finish` で `ColumnCheckResult.headings`（結果JSONの `result.headings`）に入れる。0400 は `StageSpec.reads` で 0611・0621 を読み、`bending_rebar_amount`・`bending_durability` の番号を参照の文に書く（同じ生成にないときは番号なしの文）。0612・0622 は `column_check.following_section`（最後の番号の次。番号がなければ n.11）。
- 本物の runner の Example2（2026-10-29）：0611 は 8.5〜8.10（全群）。0621 は WD-1914（使用性）・WD-1919（耐久性のせん断）で使用性の群がなく、9.8 使用性（損傷）・9.9 最小鉄筋量及び最大鉄筋量、0622 は 9.10。
- `result.json` に照査値も OK/NG もないので、WebPier も「照査を実行した」ことだけを記録する。
- 安全係数表の γi（行6 使用性（損傷）。H16 の復旧性（損傷）地震時以外）は運輸機構・JR各社 1.2。見本の解説 8-25 の「γi＝1.0」は運輸機構では誤り。
- 見本の耐力は今の Capacita と少し違う（Mud 37449.1 → 37426.2、Myd 38260.8 → 38200.7）。見本自身の WDJ を今の Capacita で計算しても同じ差が出るので、見本を作った WebDan との違い。照査値（0.132、0.114）は一致する。

## RC標準 R5 への切替（決定73、2026-10-21）

0611・0621・0810・0820・0910 の WDJ はすべて R5（見本は H16）。計画書 `.claude/docs/plans/phase-0400-detailing.md` の Phase 1・3 の知見が詳しい。

- 基準の id：`export/capacita/wdj.py` の `BODIES`（JR各社→3 R5_Rail、運輸機構→4 R5_Shinkansen、JR東日本→8 R5_JREast）。H16 の id（0・1・2）は `STANDARDS` に残るが使わない。
- 安全係数：`calc/column_check.SAFETY_FACTORS`（WebDanforJS の `default_safety_factor`。H16 と R5 で同じ値で、違いは行6 の名前だけ）。見本の WDJ の値からは T_rbt 行5〜7 1.0→1.3、行2 1.0→空欄、行7 の V_rbs 1.0→1.1。JR東日本は行6 の γi 1.0（`JR_EAST_SAFETY_FACTORS`）。0810・0820・0910 も同じ表。
- 水掛かりの程度：`crack[].con_*` に 1 常時乾燥・2 乾湿繰返し・3 常時湿潤（`choices.WATER_EXPOSURES.index + 1`）。
- 行6 は「使用性（損傷）」（`_MOMENT_TITLES` などの題、抽出ケース・組合せの名前も）。節 ID は `bending_restorability`・`shear_restorability` のまま（本物の runner で確認）なので `REPORT_SECTIONS` は変えていない。行7 は `*_restorability_eq`。
- 行8（最小鉄筋量）：0611・0621 は `MOMENT_CASES` の (8, PERMANENT)、0810・0820 は 0800 の「長期」（`Md8_Md`、Nd＝0、点1）、0910 は永久作用のケース 28。Capacita は `bending_rebar_amount` を最後の節で 3 頁（最小鉄筋量の照査結果 2 頁、最大鉄筋量の照査結果 1 頁）返す。WebPier は見出しだけを置く（0810 は 12.5、0820 は 12.9、0910 は 13.8（外観の照査ありは 13.9）。0611/0621 は決定121 から Capacita の解説の見出しで、全群を印字すれば n.10）。0612・0622 の基礎の照査は n.11 に繰り下がった（決定121 から柱の断面照査の最後の番号の次）。R5 に最小鉄筋量の断面力0の省略コードはないので `OMITTED` に入れない。
- 省略のコード：`pipeline.capacita.SKIPPED` は R5 の WD-1914〜1926。H16 の WD-1901〜1913 のままだと 0621 が「計算書の節が違います」で止まる（本物の runner で確認）。
- 解説の頁：見出しの条文番号は外した（0800 の【ＲＣ標準 13.6.3】は残す）。曲げひび割れの流れ図と方法の文は R5（σb≦σbl かつ σs≦σsl1 で省略、それ以外は Wd を照査）で、`check_text.CRACK_METHOD` を 0810/0820・0910 で共有（0611/0621 は決定121 から Capacita の解説。WebPier の文は Capacita の Rail_R5 の解説の元になった）。Vyd＝Vcd＋Vsd。
- 値：0611 の照査値と耐力、0621 の耐力、0810 の Mud 3670.5 は H16 のときと同じ（受入を取り直した）。

## 手で試す（WebPier）

1. 見本の WDJ を Capacita で試す手順と、頁を画像にする手順は `structural-capacita` の develop.md。
2. WebPier の生成を本物の runner で通すなら、出力先を scratchpad に向ける（`output/` を書き換えない）：
   `uv run --project "." --locked python -X utf8 -m webpier --input tests/fixtures/inputs/current.json --output-dir <dir>/output --post-dir <dir>/post --overwrite`（入力は `outputs` の `transverse_frame_analysis` と使う項目を選んだ current.json の写し。数秒。結果JSON の `section_check.skipped_sections` に飛ばされた節）。
3. WebPier の WDJ を本物の PIK で試すときは、`export_bytes(pier, "0620", "frameweb")` を `fempython.analyze_frame` に渡して PIK を得て、`point_index(pik, check.member)` で番号を求めてから `build_wdj` する。
4. 受入：`uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py 0611`（照査値を見本と比べる）／`… 0621`（Mud を手計算 `tests/acceptance/column_capacity_by_hand.py` と、飛ばされた照査を見本と比べる。Myd は記録だけ。決定103・105）。0611 も Mud は手計算と比べる（決定105）。WDJ が変わると `tests/acceptance/test_capacita_acceptance.py` が落ちるので、そのときにやり直す。

## 直すとき（WebPier 側）

- Capacita の節の ID を変える・足すと、WebPier の `pipeline/capacita.py`（求める節の集合、頁範囲が PDF を順に隙間なく覆うことの検査）と代役の runner も合わせる。
- 代役：Capacita の代役は `FAKE_CAPACITA=skip`（耐久性のせん断・使用性を WD-1919・WD-1914 付きで抜く）と `skipnocode`（コードなしで抜く）で省略を真似る。FEMPython の代役の PIK は1行目が `FAKE PIK <名前> <SHA256>`（見出しの代わり）で、その後に FrameWeb の部材荷重の区間の端から途中点を足した本物と同じ並びの着目点を書くので、`point_index` は本物と同じ番号になる。
- 地震時の照査に使える PIK（まだ使っていない）：0711・0721 は Aggre-SE のピックアップを `post/線路方向_Aggre-SE.pik`・`post/線路直角方向_Aggre-SE.pik` に書く（決定57、スキル webpier-aggrese。書式はスキル structural-aggrese）。ピックアップの番号は 1＝L1地震動・2＝復旧性L2・3＝安全性L2で、抽出ケースの番号（1 安全性（破壊）…）とは対応しない。部材の番号は JRSNAP の骨組（線路方向 1〜6、線路直角方向 1〜7）で、FrameWeb の部材番号ではない（2026-10-19、本物の出力で確認）。Capacita に渡すなら、`point_index` や WDJ の着目点をこの骨組から求め直す必要がある（別の決定）。
- `run-rc` のやり取りを変えたら代役の runner も更新する。本物の runner のテスト（`tests/pipeline/test_capacita.py`）は `.env` があるときだけ走り、その失敗が合図。

## 片持ち梁の断面照査（0910、決定59）

- 0910 は `run-rc` を `--pickup` なしで呼ぶ（`pipeline/capacita.py: check_section`）。WDJ（`export/capacita/cantilever.py`）の `force[0]` に 0900 の採用値を書き（Md0・1・3〜8、Vd0〜7、Mt0・1・5・6・7。Md は負＝上側引張。Md8 は永久作用のケース 28、決定73）、Capacita はそのまま計算して `result.json`・`report.pdf` の2つだけを返す（`model.wdj` は返らないので、公開する `post/片持ち梁.wdj` は WebPier が書いたもの）。
- 返る節の並びと WD-408/409/410 は `structural-capacita` の wdj.md。Md8 を書くようになって（決定73）0910 では WD-408 が出なくなった（それまでは Md8 が空欄で1つ出ていた）。省略コードと節の対応は `pipeline.capacita.SKIPPED`。
- 疲労の ΣN は Capacita が計算する。見本の 10.39 は外部プログラム N-EQUIVALENT の値で、入力 `片持ち梁の照査.疲労` から写す。
- k=0.12 の等価繰返し回数が空欄（決定125）なら NA12・NB12 は null。主鉄筋かスターラップが k=0.12 を選ぶと Capacita は WD-3301 の error で止まる（2026-10-31 から。それより前は 0 として黙って ΣN を求めていた）。`pipeline/capacita.py: _reasons` が `errors` に続けて `messages` の error・fatal を `RunnerError` の本文に足すので、headless では `ENGINE_FAILED` に WD-3301 の本文が載る。代役は `FAKE_CAPACITA=k012`。Example橋脚4 の 0910 は主鉄筋が k=0.06 で、せん断の疲労の行は空なので止まらない（本物の runner で確認）。
- 0910 の疲労の `SA`・`SB`（SA/SC・SB/SC）は入力 `片持ち梁の照査.疲労.最大変動断面力比.{A列車,B列車}` の値（以前はプログラムの定数 1.0）。空欄は 0910 の入力エラーで、WDJ に null を書くことはない。
- せん断スパンは `shear[0].La` に **mm** で書く（`export/capacita/cantilever.py` の `_millimetres`。計算の `calc/cantilever/check.py` の `shear_span` は m のまま）。Capacita は La を mm として読む（スキル `structural-capacita` の wdj.md）。2026-10-19 まで m（`La: 1.55`）で書いていて、1.55 mm として計算され、計算書に「せん断スパン長 (mm) 1.6」「せん断スパン比 0.001」と出て βa が上限 5.000 に張り付き、安全性（破壊）のディープビームの耐力 Vdd を 15179.9 kN と過大に見積もっていた（1550 mm で 11134.6 kN、照査値 0.415 → 0.566）。直した。それより前に作った `post/片持ち梁.wdj` と 0910 の計算書は作り直す。 見本の WDJ の `points[0].La: 1` は「自動算定」（|Md/Vd|）の意味で、今の RcDan は `points` の La を読まず `shear` 表から読む。
- 代役の runner は `--pickup` なしのとき WDJ の `force` の行から節を決める（`tests/fixtures/capacita/fake_runner.py: force_sections`）。0810・0820 のフーチングの WDJ も同じ規則で 6 節（`bending_rebar_amount` を含む）になる。

## 直角方向（0621）と照査の省略

- 解説の文は見本 08 と 09 で同じで、違うのは節の番号だけ（決定121 から解説は Capacita が印字する）。WDJ の `basic`・`safety`・ひび割れの行も 08 と同じ（`column_section_check_09.json` の `same_as_08`）。
- 直角方向は永久作用が左右対称なので Example2 では WD-1914（使用性の曲げ）・WD-1919（耐久性のせん断）が出る（H16 では WD-1901・1906）。見本 09 に 9.7・9.8 がないのはこのため。`pipeline.capacita.SKIPPED` が節とコードの対応で、コードのある欠けだけを認める。計算書には何も印字されず、群ごと欠ければ番号が詰まる（決定121。それまでは省略の理由を印刷していた。0810・0820・0910・杭体は今も `check_text.OMITTED` で理由を印刷する）。
- **直角方向の配筋**（決定103 で見本から変えた）：線路の D32 の隅の鉄筋（両面から 108）は近い面の1段目に入れ、D19 の本数に面積で換算する：D19×9（芯 102）＋D32×2（芯 108）→ D19×14.54、芯 104.3。側方鉄筋は隅を除いた D32 の 300…4200（150 間隔）の 27 本。見本 09_直角/WebDan.wdj は D19×9 と、隅を含む側方鉄筋 29 本を本数だけ（RcDan が等分）。隅の鉄筋の判定は `calc.column_check.corner_bars`、主鉄筋の段と側方鉄筋の形は `column_bars`。Example4 は線路方向 D38 23＋11（34 本を1段目 23 本で分ける）、直角方向 D19×14.96・芯 79.6、側方鉄筋 D38 32 本（250 から 96.8 間隔、内側の段を広げる）。
- **安全性（破壊）の行（id 5）は `range` 3**（決定105）：側方鉄筋を含む全軸方向鉄筋で曲げ耐力とせん断耐力を求める（R5 の見本 Example橋脚4 が数える。WebDanforJS の既定は 2 で数えない）。決定105 より前は数えなかった：見本の WDJ をいまの Capacita で計算すると耐力は見本と 0.2% 未満の差（Mud 29326.7／29334.2、Myd 48634.5／48663.2）。決定103・105 の WDJ では Mud 59170.6・Myd 49516.9（隅の D32 が主鉄筋に入り、安全性（破壊）が側方鉄筋 D32×27 を数える）。Mud は RC標準の応力ひずみ曲線の手計算 59218.0 と 0.08% 差（側方鉄筋は中立軸の近くにあり、等価応力ブロックでは 0.36% ずれる）。Myd の手計算（放物線＋矩形、引張鉄筋の降伏）は見本の鉄筋でも 3% 合わず、Capacita の降伏の定義は未確認。
- 見本 09 の照査値（0.338、0.098）は WebPier と比べられない。WebPier の 0620 の風荷重（決定12・35）は見本と違い、柱下端の Md が違う（安全性（破壊）10939.1／見本 8256.6）。N'd は同じ（13264.1、14404.5）なので受入は耐力で比べる。見本自身の WDJ（`shape` を `"1"` にした複製）を今の Capacita で計算すると 0.338・0.098 が再現するので、WebPier の WDJ との違いは断面力だけと確かめられる。
- 省略の理由の文（0810・0820・0910・杭体）は解説の後に空き1行を置いて組む（`check_text._blocks` はキーが `.omitted` で終わる単位で区切る）。省略した節の後は Capacita のページを挟まず、次の節の文書が新しいページから始まる。

## フーチングの断面照査（0810・0820、決定60）：断面力入力モードの WDJ

- `webpier/calc/footing_check.py` が条件を組み（部材「フーチング」1000×H6 mm、下側の主鉄筋とスターラップ、材料、`柱の断面照査` の条件、Dmax は `鉄筋.フーチング.aggregate_max_mm`（owner 2026-10-19））、`webpier/export/capacita/footing_wdj.py` が WDJ を書く。runner は `pipeline.capacita.check_section`（`--pickup` なし。成果物は result.json と report.pdf だけ。決定59と共用）。代役は `tests/fixtures/capacita/fake_runner.py` の引数7個のモード（6節、1/2/2/1/2/3 頁、warn WD-408/409）。
- 使う id：0 耐久性 応力度、1 耐久性 永久荷重、5 安全性 破壊、7 復旧性 地震時、8 最小鉄筋量（長期の Md、決定73）。せん断スパンは `shear[]` の行の `La`（WebPier は mm の整数で書いている。`FootingCheckResult.la` の注記は mm）。Capacita は La を mm として読むので**正しい**（2026-10-19、本物の runner で m に変えた複製と比べて確認。`MemberGroup.cs:367` の「(m)」のコメントは誤り）。
- **La は着目点ごとに1つ**なので、方向ごとに2点にしている：点1「線路方向」（Md0・Md1・Md5・Vd5、安全性の La）、点2「線路方向（地震時）」（Md7・Vd7、地震時の La）。見本 12 章は安全性 1127・地震時 1819 と別の La を印刷している。
- 上側鉄筋なしは `rebar1` を全部 null で通る。断面力一覧は出ない。見本 p255 の値（Mud 3670.5、0.249）と p258（Vdd 4337.2、0.187）は今の Capacita で再現する。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- Capacita そのものの性質：structural-mcp の `skills/structural-capacita/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0611・0621・0810・0820・0910 の照査の中身の説明は、structural-mcp のスキル `structural-webpier` の checks.md にある（ここには書かない）。差し込む節や省略の扱いを変えたら、そちらも直して structural-mcp で commit する。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
