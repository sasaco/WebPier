---
name: capacita-column-check
description: Capacita（structural-mcp の Capacita サブモジュール、RcDan／WebDanforCS、旧名 WebDan）で柱の RC 断面照査を行う 0611（決定48、ADR-0008）を扱う。WebPier が書く WDJ（webpier/export/capacita）、Headless の run-rc --pickup と節ごとのページ範囲 reportSections、0611 の計算書への差し込み、見本 Example橋脚2 の WebDan.wdj を今の Capacita で読む・計算する・ページを画像にして確かめるときに使う。WDJ が「有効な算出点がありません」や WD-9999 で失敗するとき、照査の条件や安全係数を変えるとき、0621 を足すときにも使う。
---

# Capacita で柱の断面照査を行う（0611）

0611 は骨組解析（FEMPython）の `.pik` を設計応答値として、柱下端の1断面を Capacita（RcDan）で照査し、その `report.pdf` のページを計算書（8.5〜8.9）に差し込む（決定48、ADR-0008、CONTEXT.md「柱の断面照査」）。WebPier は WDJ を書いて runner を呼ぶだけで、`.pik` は読まない。照査の式・表・印字桁は Capacita の責務なので、足りなければ Capacita 側を直す（その `.claude/rules/` に従い、`WebDanforCS/tests/UiTests` を通す）。

## 置き場所

| もの | 場所 |
|---|---|
| WebPier の計算・WDJ・runner・帳票 | `webpier/calc/column_check.py`、`webpier/export/capacita/wdj.py`、`webpier/pipeline/capacita.py`、`webpier/reporting/stages/column_check.py` |
| runner | `C:\Users\sasai\Documents\structural-mcp\Capacita\WebDanforCS\Headless\bin\Release\net8.0\WebDanforCS.Headless.exe`（`.env` の `STRUCTURAL_MCP_WEBDAN_RUNNER`。旧名のまま） |
| runner の契約（引数・`--pickup`・`reportSections` の節の ID） | Capacita の `README.md` の「Headless runner の run-rc」 |
| 代役の runner・期待値・受入 | `tests/fixtures/capacita/fake_runner.py`、`tests/fixtures/example2/column_section_check.json`（注記 `_notes.md`）、`scripts/accept_capacita_column.py` → `tests/fixtures/acceptance/capacita/record.json` |
| 見本 | `.claude/docs/Example橋脚2/08_線路.pdf` の 12〜26 頁、`08_線路/WebDan.wdj`・`frameWebForJS.pik`（直角方向は `09_直角/`） |

## WDJ の落とし穴（2026-10-18 に本物の runner で確認）

- **見本の `WebDan.wdj` はそのままでは計算できない。** 旧 WebDan の形式で `members[].shape` が `"矩形"`。RcDan は 1〜4 の番号しか読まず（`MemberGroup.cs`、1＝矩形）、断面のない部材として飛ばして「有効な算出点がありません」（WD-1001）で失敗する。試すときは複製の `shape` を `"1"` にする。
- **整数の項目は JSON の整数で書く。** RcDan は b・h・鉄筋径・ε'csd・環境条件を int で読み、`300.0` は内部エラー WD-9999 になる（`wdj.py` の `_number`）。
- **RC の WDJ に `steel` キーがあると拒否される**（WDJ-FORMAT-CONFLICT）。見本にはあるが WebPier は書かない。
- **`bar[].position` を書かない。** `--pickup` の取込みは着目点の `position` と照合し、見本の `"6.250"` は不一致になる。
- **着目点の番号**：FEMPython の `.pik` は部材順に ITAN（0）・JTAN（部材長）を並べるので、部材 m の J端は `index`＝2m、`p_id`＝`JTAN`。ずれれば取込みが失敗して生成が止まる。
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
3. WebPier の生成を通すなら `--stage 0611 --frame-analysis` 相当を `render_*` で scratchpad に出し、`output/` を書き換えない。

## 直すとき

- Capacita を直したら Release でビルドし直す（structural-mcp のルートで `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release`）。テストは `dotnet test` で `WebDanforCS/tests/UiTests`（`ReportSectionsTests`・`HeadlessPickupTests`）。`PreviewTests` の `.agents/logs` 未作成、クリップボード、Steel 印刷は以前から落ちることがある（今回の変更と無関係）。`WebDanforCS.Tests` は NU1201 で restore できず、`RcDan/tests` は確認用の WinForms アプリ。
- 節の ID を変える・足すと、WebPier の `pipeline/capacita.py`（求める節の集合、頁範囲が PDF を順に隙間なく覆うことの検査）と代役の runner も合わせる。
- `run-rc` のやり取りを変えたら代役の runner も更新する。本物の runner のテスト（`tests/pipeline/test_capacita.py`）は `.env` があるときだけ走り、その失敗が合図。
- 0621 を足すときは、直角方向の見本（`09_直角.pdf`）が耐久性・使用性を省いている理由をまず決める（決定48）。
