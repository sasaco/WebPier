---
name: capacita-column-check
description: Capacita（structural-mcp の Capacita サブモジュール、RcDan／WebDanforCS、旧名 WebDan）で柱の RC 断面照査を行う 0611・0621（決定48、ADR-0008）を扱う。WebPier が書く WDJ（webpier/export/capacita）、Headless の run-rc --pickup と節ごとのページ範囲 reportSections、0611・0621 の計算書への差し込み、断面力0で飛ばされる照査（WD-1901〜1913）、--pickup なしで断面力表つきの WDJ を計算させる 0910・0810・0820、見本 Example橋脚2 の WebDan.wdj を今の Capacita で読む・計算する・ページを画像にして確かめるときに使う。WDJ が「有効な算出点がありません」や WD-9999 で失敗するとき、照査の条件や安全係数を変えるとき、着目点の番号や配筋の写し方が合わないときにも使う。
---

# Capacita で柱の断面照査を行う（0611・0621）

0611（線路方向）・0621（直角方向）は骨組解析（FEMPython）の `.pik` を設計応答値として、柱下端の1断面を Capacita（RcDan）で照査し、その `report.pdf` のページを計算書（8.5〜8.9・9.5〜9.9）に差し込む（決定48、ADR-0008、CONTEXT.md「柱の断面照査」）。2方向の違いは `calc.column_check.Direction`（LONGITUDINAL・TRANSVERSE）と `reporting.stages.column_check.Chapter`（8・9）だけ。WebPier は WDJ を書いて runner を呼ぶだけで、`.pik` の断面力は読まない（着目点の番号だけ並びから求める）。照査の式・表・印字桁は Capacita の責務なので、足りなければ Capacita 側を直す（その `.claude/rules/` に従い、`WebDanforCS/tests/UiTests` を通す）。骨組解析は同じ FrameWeb 入力の基礎の照査（0612・0622）と共有し、1回の生成で1回だけ行う（決定54。スキル foundation-check）。0612 だけを選んだ生成でも `.pik` は書き換わるが、0611 の `.wdj` は残る。

## 置き場所

| もの | 場所 |
|---|---|
| WebPier の計算・WDJ・runner・帳票 | `webpier/calc/column_check.py`、`webpier/export/capacita/wdj.py`、`webpier/pipeline/capacita.py`、`webpier/reporting/stages/column_check.py` |
| runner | `C:\Users\sasai\Documents\structural-mcp\Capacita\WebDanforCS\Headless\bin\Release\net8.0\WebDanforCS.Headless.exe`（`.env` の `STRUCTURAL_MCP_WEBDAN_RUNNER`。旧名のまま） |
| runner の契約（引数・`--pickup`・`reportSections` の節の ID） | Capacita の `README.md` の「Headless runner の run-rc」 |
| 代役の runner・期待値・受入 | `tests/fixtures/capacita/fake_runner.py`、`tests/fixtures/example2/column_section_check.json`・`column_section_check_09.json`（注記 `_notes.md`）、`scripts/accept_capacita_column.py [0611|0621]` → `tests/fixtures/acceptance/capacita/record.json`・`record_0621.json` |
| 見本 | `.claude/docs/Example橋脚2/08_線路.pdf` の 12〜26 頁、`08_線路/WebDan.wdj`・`frameWebForJS.pik`（直角方向は `09_直角.pdf` の 16〜23 頁と `09_直角/`） |

## WDJ の落とし穴（2026-10-18 に本物の runner で確認）

- **見本の `WebDan.wdj` はそのままでは計算できない。** 旧 WebDan の形式で `members[].shape` が `"矩形"`。RcDan は 1〜4 の番号しか読まず（`MemberGroup.cs`、1＝矩形）、断面のない部材として飛ばして「有効な算出点がありません」（WD-1001）で失敗する。試すときは複製の `shape` を `"1"` にする。
- **整数の項目は JSON の整数で書く。** RcDan は b・h・鉄筋径・ε'csd・環境条件を int で読み、`300.0` は内部エラー WD-9999 になる（`wdj.py` の `_number`）。
- **RC の WDJ に `steel` キーがあると拒否される**（WDJ-FORMAT-CONFLICT）。見本にはあるが WebPier は書かない。
- **`bar[].position` を書かない。** `--pickup` の取込みは着目点の `position` と照合し、見本の `"6.250"` は不一致になる。
- **着目点の番号**：Capacita の取込みは、PIK の最初のピックアップ・着目力の行の順に 1 から番号を付け、WDJ の `points`・`bar`・`crack` の `index` と厳密に照合する（`IMPORT-EXISTING-POINT-IDENTITY`）。FEMPython の `.pik` は部材順に ITAN・（部材荷重の区間の端の途中点 `1`, `2`…）・JTAN を並べる。0610 は途中点がないので柱下端は 6 だが、0620 は柱（部材3）に風荷重の区間の端（I端から 2.900m）があるので 7（見本 09 の PIK は 6）。だから番号は `export.capacita.point_index(pik, member)` で PIK から求める。代役の FEMPython も FrameWeb の部材荷重から同じ途中点を書く。
- `calc.print_section_force_checked: true` で断面力一覧表（曲げ・せん断の2頁）が先頭に付く（8.5 になる）。
- `result.json` には照査値も OK/NG もない（`engineeringStatus` は `not_evaluated`）。判定は PDF の頁で見る。WebPier も「照査を実行した」ことだけを記録する。
- `conditions_list`（JR-001・JR-004）は RcDan が読むが計算に使わない。入力しても結果は変わらない。
- 安全係数表：復旧性（損傷）地震時以外の γi は運輸機構・JR各社 1.2、JR東日本だけ 1.0（WebDanforJS の `safety-factors-material-strengths.service.ts` の例外に合わせた）。見本の解説 8-25 の「γi＝1.0」は運輸機構では誤り。
- 見本の耐力は今の Capacita と少し違う（Mud 37449.1 → 37426.2、Myd 38260.8 → 38200.7）。見本自身の WDJ を今の Capacita で計算しても同じ差が出るので、見本を作った WebDan との違い。照査値（0.132、0.114）は一致する。

## 手で試す

1. 見本の複製を作り（`shape` を `"1"`、必要なら `calc.print_section_force_checked: true`）、scratchpad で runner を呼ぶ：
   `dotnet "<Capacita>\WebDanforCS\Headless\bin\Release\net8.0\WebDanforCS.Headless.dll" run-rc --input <wdj> --output-dir <dir> [--pickup <pik>] [--summary-xlsx true]`
   stdout が protocol v1 の envelope。メッセージは `\uXXXX` なので Python で読む。
2. 頁を画像にする（この環境に pdftoppm はない）：
   `uv run --no-project --with pymupdf python -X utf8 -c "import pymupdf; d=pymupdf.open(r'<pdf>'); [p.get_pixmap(dpi=90).save(f'<dir>/p{i+1}.png') for i,p in enumerate(d)]"`
   見本の PDF の頁も同じ方法で読む（解説の頁は文字、結果の頁は表、図は JPEG の埋め込み）。
3. WebPier の生成を本物の runner で通すなら、出力先を scratchpad に向ける（`output/` を書き換えない）：
   `uv run --project "." --locked python -X utf8 -m webpier --input tests/fixtures/inputs/current.json --output-dir <dir>/output --post-dir <dir>/post --stage 0621 --overwrite`（数秒。結果JSON の `section_check.skipped_sections` に飛ばされた節）。
4. WebPier の WDJ を本物の PIK で試すときは、`export_bytes(pier, "0620", "frameweb")` を `fempython.analyze_frame` に渡して PIK を得て、`point_index(pik, check.member)` で番号を求めてから `build_wdj` する。番号を決め打ちすると `IMPORT-EXISTING-POINT-IDENTITY /points/0/p_id` で止まる。返る完成の WDJ は PIK の全着目点を持ち、`points` の番号は PIK の順（先頭は 1）。
5. 受入：`uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py 0611`（照査値を見本と比べる）／`… 0621`（耐力と飛ばされた照査を比べる）。WDJ が変わると `tests/acceptance/test_capacita_acceptance.py` が落ちるので、そのときにやり直す。

## 直すとき

- Capacita を直したら Release でビルドし直す（structural-mcp のルートで `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release`）。テストは `dotnet test` で `WebDanforCS/tests/UiTests`（`ReportSectionsTests`・`HeadlessPickupTests`）。`PreviewTests` の `.agents/logs` 未作成、クリップボード、Steel 印刷は以前から落ちることがある（今回の変更と無関係）。`WebDanforCS.Tests` は NU1201 で restore できず、`RcDan/tests` は確認用の WinForms アプリ。
- 節の ID を変える・足すと、WebPier の `pipeline/capacita.py`（求める節の集合、頁範囲が PDF を順に隙間なく覆うことの検査）と代役の runner も合わせる。
- 代役：Capacita の代役は `FAKE_CAPACITA=skip`（耐久性のせん断・使用性を WD-1906・WD-1901 付きで抜く）と `skipnocode`（コードなしで抜く）で省略を真似る。FEMPython の代役の PIK は1行目が `FAKE PIK <名前> <SHA256>`（見出しの代わり）で、その後に FrameWeb の部材荷重の区間の端から途中点を足した本物と同じ並びの着目点を書くので、`point_index` は本物と同じ番号になる。
- 地震時の照査に使える PIK（まだ使っていない）：0711・0721 は Aggre-SE のピックアップを `post/線路方向_Aggre-SE.pik`・`post/線路直角方向_Aggre-SE.pik` に書く（決定57、スキル aggrese-project）。行の書式は FEMPython の PIK と同じだが、先頭行は `Batch ver1.0.0`。ピックアップの番号は 1＝L1地震動・2＝復旧性L2・3＝安全性L2で、抽出ケースの番号（1 安全性（破壊）…）とは対応しない。部材の番号は JRSNAP の骨組（NDU の MemberInfo。線路方向 1〜6、線路直角方向 1〜7）で、FrameWeb の部材番号ではない。着目点は各部材の ITAN・JTAN だけで途中点はない（2026-10-19、本物の出力で確認）。Capacita に渡すなら、`point_index` や WDJ の着目点をこの骨組から求め直す必要がある（別の決定）。
- `run-rc` のやり取りを変えたら代役の runner も更新する。本物の runner のテスト（`tests/pipeline/test_capacita.py`）は `.env` があるときだけ走り、その失敗が合図。

## 片持ち梁の断面照査（0910、決定59）

- 0910 は `run-rc` を `--pickup` なしで呼ぶ（`pipeline/capacita.py: check_section`）。WDJ（`export/capacita/cantilever.py`）の `force[0]` に 0900 の採用値を書き（Md0・1・3〜7、Vd0〜7、Mt0・1・5・6・7。Md は負＝上側引張）、Capacita はそのまま計算して `result.json`・`report.pdf` の2つだけを返す（`model.wdj` は返らないので、公開する `post/片持ち梁.wdj` は WebPier が書いたもの）。
- 返る節は断面力表の行で決まる（2026-10-19、本物の runner で確認）：bending/shear/torsion_safety_destruction、bending/shear_safety_fatigue、bending/shear/torsion_durability、（外観の照査を行えば bending_serviceability）、bending/shear/torsion_restorability、bending/shear/torsion_restorability_eq の順。`section_forces` は `print_section_force_checked: true` でも出ない。断面力の欠けた行は warn の WD-408/409/410（Md8 最小鉄筋量は空欄なので WD-408 が1つ出る）。
- 断面力0の省略コードは 1901〜1913（`pipeline.capacita.SKIPPED`：1903 疲労曲げ、1905 復旧性地震時曲げ、1909 同せん断、1910 耐久性ねじり、1911 安全性ねじり、1912 復旧性ねじり、1913 同地震時）。
- 疲労は WDJ の `fatigues`（`train_A_count`・`train_B_count`・`service_life` は文字列、`fatigue_list[0]` の M1/V1 に SA・SB・NA06・NB06・NA12・NB12・r1）から Capacita が ΣN を計算する（`RcDan/Calculation/Calc_NRepetition.cs`）。見本の 10.39 は外部プログラム N-EQUIVALENT の値で、入力 `片持ち梁の照査.疲労` から写す。
- せん断スパンは `shear[0].La`（m）。見本の WDJ は `points[0].La: 1` だが、今の RcDan は `shear` 表から読む。
- 代役の runner は `--pickup` なしのとき WDJ の `force` の行から節を決める（`tests/fixtures/capacita/fake_runner.py: force_sections`）。0810・0820 のフーチングの WDJ も同じ規則で 5 節になる。

## 直角方向（0621）と照査の省略

- 解説の文は見本 08 と 09 で同じで、違うのは節の番号（9.5〜9.9）だけ。WDJ の `basic`・`safety`・ひび割れの行も 08 と同じ（`column_section_check_09.json` の `same_as_08`）。
- **断面力0で飛ばされる照査**：RcDan（`VerificationControl.CheckValidation`）は断面力0の照査の節を作らず、info のメッセージで知らせる：WD-1901 使用性の曲げ（永久作用の Md＝0 かつ引張軸力なし）、1902 安全性（破壊）の曲げ、1904 復旧性の曲げ、1906 耐久性のせん断（永久＋変動の Vd＝0）、1907 安全性（破壊）のせん断、1908 復旧性のせん断（コードは `ErrorMessage_1000_1999.cs` の `ZeroForce_RailH16_*`、H16 はどの機関も共通）。耐久性の曲げは省略しない（全断面圧縮なら「省略判定」として頁を出す）。直角方向は永久作用が左右対称なので Example2 では 1901・1906 が出る。見本 09 に 9.7・9.8 がないのはこのため。`pipeline.capacita.SKIPPED` が節とコードの対応で、コードのある欠けだけを認め、計算書は省略の理由を印刷する（`reporting.stages.column_check.OMITTED`）。
- **直角方向の配筋**：表の主鉄筋は直角の面の D19×9（芯 102）。線路の D32 の隅の鉄筋は両面から 108 にあるので側方鉄筋の側になり、その芯は 108, 300…4200, 4392（両端だけ 192）。見本どおり `side_cover`・`side_ss` を空欄にし、RcDan（`DefaultValue.CalcDefaultUedgeAndPitchForSideBar`）が上下の主鉄筋の間に等分（芯 245.2 から 143.2 間隔）、側方の芯かぶりは主鉄筋の芯（102）にする。隅の鉄筋の判定は `calc.column_check.corners`。
- **安全性（破壊）の曲げは側方鉄筋を数えない**（Ase「-」。見本の WebDan も同じ）。復旧性の曲げは数える。直角方向の耐力は見本と 0.2% 未満の差（Mud 29326.7／29334.2、Myd 48634.5／48663.2）。
- 見本 09 の照査値（0.338、0.098）は WebPier と比べられない。WebPier の 0620 の風荷重（決定12・35）は見本と違い、柱下端の Md が違う（安全性（破壊）10939.1／見本 8256.6）。N'd は同じ（13264.1、14404.5）なので受入は耐力で比べる。見本自身の WDJ（`shape` を `"1"` にした複製）を今の Capacita で計算すると 0.338・0.098 が再現するので、WebPier の WDJ との違いは断面力だけと確かめられる。
- 省略の理由の文は解説の後に空き1行を置いて組む（`_blocks` はキーが `.omitted` で終わる単位で区切る）。省略した節の後は Capacita のページを挟まず、次の節の文書が新しいページから始まる。

## フーチングの断面照査（0810・0821 ではなく 0810・0820、決定60）：断面力入力モードの WDJ

- `webpier/calc/footing_check.py` が条件を組み（部材「フーチング」1000×H6 mm、下側の主鉄筋とスターラップ、材料、`柱の断面照査` の条件、Dmax は `鉄筋.フーチング.aggregate_max_mm`（owner 2026-10-19））、`webpier/export/capacita/footing_wdj.py` が WDJ を書く。runner は `pipeline.capacita.check_section`（`--pickup` なし。成果物は result.json と report.pdf だけ。決定59と共用）。代役は `tests/fixtures/capacita/fake_runner.py` の引数7個のモード（5節、1/2/2/1/2 頁、warn WD-408/409）。
- 断面力入力モードの WDJ（2026-10-19、本物の runner で確認）：`pickup_filename` を空にすると Manual モード（`RcConditionEditor.ConditionInputMode`）。断面力は `force[]` の行に `Md<id>_Md`・`Md<id>_Nd`・`Vd<id>_Vd`・`Vd<id>_Md`・`Vd<id>_Nd`（id は `basic.pickup_moment`／`pickup_shear_force` の id：0 耐久性 応力度、1 耐久性 永久荷重、5 安全性 破壊、7 復旧性 地震時。`no` は null でよい）。せん断スパンは `shear[]` の行の `La`（mm、整数）。正の Md が下側引張（`rebar2`）。与えない id の照査は warn WD-408（曲げ）／WD-409（せん断）で印刷されず、`reportSections` にも出ない（info の WD-19xx ではない）。
- **La は着目点ごとに1つ**なので、限界状態ごとに La を変えるには着目点を分ける。フーチングは方向ごとに2点：点1「線路方向」（Md0・Md1・Md5・Vd5、安全性の La）、点2「線路方向（地震時）」（Md7・Vd7、地震時の La）。各節はその節の断面力を持つ点だけを印刷する（1点だけの表になる）。見本 12 章は安全性 1127・地震時 1819 と別の La を印刷しているので、旧 WebDan は照査ごとの La を持っていた。
- 上側鉄筋なしは `rebar1` を全部 null（`enable` は true のまま）で通る。`print_section_force_checked` は Manual モードでは効かない（断面力一覧は出ない）。見本 p255 の値（Mud 3670.5、0.249）と p258（Vdd 4337.2、0.187）は今の Capacita で再現する。
