---
name: foundation-check
description: WebPier の 0612・0622 基礎の照査（決定54、CONTEXT.md「基礎の照査」）を扱う。FEMPython の骨組解析の反力 CSV（*_ピックアップ反力.csv）から基礎中心の Vd・Hd・Md を読む仕組み（support_reactions、支点の節点、抽出ケースと4列の対応、符号）、鉛直支持・水平支持・回転の式と印字桁（webpier/calc/foundation_check.py）、水位ごとの γe2、長期の上限値と土質区分、計算書 8.10・9.10（webpier/reporting/stages/foundation_check.py）、0611 と骨組解析を共有する登録表（StageSpec.complete）、独立の手計算と本物の FEMPython での受入に使う。見本 08_線路.pdf 8-27〜8-32・09_直角.pdf 9-24〜9-29 と値が合わない、反力が読めない、列の組合せが違う、照査の式や定数を変えるときにも使う。柱の断面照査（Capacita）は webpier-capacita。
---

# 基礎の照査（0612・0622）

0612（線路方向）・0622（直角方向）は、直接基礎の鉛直支持・水平支持・回転を WebPier の `calc` で照査し、計算書（8.10・9.10）をすべて WebPier が描く（決定54、ADR-0006）。設計応答値は FEMPython の骨組解析の支点反力で、WebPier は荷重から断面力を組み立て直さない。2方向の違いは `calc.foundation_check.Direction`（B と L の入れ替え）と `reporting.stages.foundation_check.Chapter`（8・9）だけ。

## 置き場所

| もの | 場所 |
|---|---|
| 計算（2段階：`prepare` は入力から、`check` は反力で） | `webpier/calc/foundation_check.py`、水位ごとの γe2 は `webpier/calc/embedment.py` の `cover_weight` |
| 反力 CSV の読込み | `webpier/pipeline/fempython.py` の `support_reactions(csv, node)` |
| 登録表・生成 | `webpier/pipeline/stages.py` の `_foundation_check`（`complete=`）、`generate.py` の `_analysis_key`・`_complete` |
| 帳票 | `webpier/reporting/stages/foundation_check.py` |
| 独立の手計算（期待値） | `tests/fixtures/example2/foundation_check.json` と `foundation_check_notes.md`（実装を見ずに作った。見本の抵抗側の再現も確かめてある） |
| 受入（本物の FEMPython） | `scripts/accept_foundation_check.py [0612|0622]` → `tests/fixtures/acceptance/foundation_check/record_*.json` と反力 CSV、テスト `tests/acceptance/test_foundation_check_acceptance.py` |
| 見本と原資料 | `.claude/docs/Example橋脚2/08_線路.pdf` 27〜32 頁、`09_直角.pdf` 24〜29 頁、`08_線路/安定計算.xls`（シート「鉛直」「水平」。`uv run --no-project --with xlrd==2.0.1 python -I` で値を読める。式は残っていない） |

## 反力の読み方（2026-10-18 に本物の FEMPython で確認）

- 骨組はフーチング底面の中心（`NodeRole.FOOTING_BOTTOM`）にばね支点を置く。その節点の反力がそのまま見本の「基礎中心の断面力」。Example2 は両方向とも節点 6。番号で決め打ちせず骨組の役割から求める。
- CSV の列：`pickup_id,focus_component,node_id,max_combine_id,min_combine_id,max_fx (unspecified),…,min_mz (unspecified*unspecified)`。抽出ケース×着目成分（fx・fy・mz）×節点ごとに1行で、最大・最小それぞれに、その組合せの fx・fy・mz が同時に入る。列は単位の前の名前で引く。
- 符号：y が下向きなので Vd ＝ −fy（鉛直反力が最大の組合せは fy が最小の側）。Hd ＝ |fx|、Md ＝ |mz|。読むときに2桁へ丸める。
- 4列：長期支持＝抽出ケース 7、短期支持＝8（組合せ 15 低水位と 16 高水位があり、Vd の大きい 15）、安全性 鉛直力最大＝6 の fy 最小（組合せ 10）、曲げ最大＝6 の |mz| 最大（線路方向 11、直角方向 12）。どれも見本と同じ組合せになる。
- 見本との差：線路方向は長期が一致、短期は Vd＋0.22・Md −0.09、安全性は 0.03 以内（見本の隠れた桁）。直角方向は 0620 の風荷重が見本と違う（決定12・35）ので Hd・Md は比べない（Vd は一致）。
- 代役の FEMPython（`tests/fixtures/fempython/fake_runner.py`）は本物と同じ列で反力 CSV を書き、支点（`fix_node`）にだけ `reaction(c)` の値を入れる。テストは `tests/pipeline/pipeline_support.py` の `fake_reactions(frameweb)` で期待値を作る。
- `pick`（極値の選び方）と `bearing_capacity`／`Capacity`（qvd・qd・Mmd）は 0800 フーチングの応答値（決定60、footing-check スキル）と共用。`pick` は fy が max 行と min 行で同値のとき |mz| の大きい行、さらに同じなら |fx| の大きい行を採る（owner 2026-10-19。断面照査用のピックアップ 2・3 で起きる。0612・0622 の受入記録の列は変わらない）。式を変えるときは両方のテストを回す。

## 式と見本の扱い

- qvd は見本の「砂質土の場合」の式だけ（粘性土の式は見本・原資料に出どころがない）。支持層が粘性土・互層なら `prepare` が入力エラー。長期の上限値は土質区分から：砂質土 300＋γe2・Df、砂礫 500＋γe2・Df（owner 2026-10-18）。
- Df は 0500 の表層厚（Example2 は 4.700）。見本の 3.78 は地盤調査の表層厚で、見本自身の載荷土の土かぶり 2.00 と矛盾するので使わない。γe2 は長期が平水位、短期・安全性が高水位（hw は基礎下面から。hw ≧ Df は全部水中、≦ 0 は全部湿潤）。
- Mmd は見本に式がない。原資料の値から逆算して Mmd ＝ Vd・B/2・(1 − Vd／(qd・B・L)) と確かめた（8-30 の4列が合う）。
- 水平支持は見本どおり全列 γi＝1.0、γa なし（シートが独立に 1.0 と置いている）。frs＝0.33。Rhb ＝ frs・Vd・tanφ。
- 再現しない見本の誤り：ex の丸めが頁で違う（印字した3桁で統一）、9-27 の Be が B′＞L でも B′（min(B′, L)）、長期の qd が丸める前の γe2、「γi･Pd／qd」が実は pd1、Pd の単位 kN/m3、Rhb を 0.1 に丸める。
- 合力の作用位置がフーチングの外（ex ≧ B/2）や上向きの Vd は照査できないので入力エラー。Mmd ≦ 0 は照査値なし（「－」）で NG。

## 生成

- `uv run --project "." --locked python -m webpier --stage 0612 --frame-analysis --overwrite`（0622 も同じ）。`--frame-analysis` がないと選べない（`all` にも入らない）。runner は `.env` の `STRUCTURAL_MCP_FEMPYTHON_RUNNER`。0611 も選ぶと解析は1回で済むが、Capacita の runner も要る。
- `--stage` で1つの段階を直接選ぶと、依存のうち runner を動かす段階も一緒に生成して公開する（決定60の規則、2026-10-19）。`--stage 0612` 自体は依存に runner の段階がないので変わらないが、0800 を選ぶと 0612・0622 の計算書も公開される。
- `current.json` を変えると受入記録（`record_0612.json`・`record_0622.json`）の SHA が合わなくなり `tests/acceptance` が落ちる。`scripts/accept_foundation_check.py 0612`／`0622` を回し直す（工学値は変わらないはず。2026-10-19 に確認）。
- 並行して別のセッションが作業しているときは CLI（`output/` と `post/` を書き換える）を避け、`render_foundation_check` で scratchpad に出す。
- Example2（`pre/input.json`、2026-10-18）は両方向とも全項目 OK、照査値の最大は長期の鉛直支持の 0.743。

## 骨組解析の共有

- 0611 と 0612（0621 と 0622）は同じ FrameWeb 入力を解析する。`FrameAnalysis` の (stage, export) が同じ段階は、登録表が同じファイルの宣言を求め、生成は FEMPython を1回だけ呼び、ピックアップのファイルを先の段階の役割で1組だけ公開する（付帯JSONの `frame_analysis.stages` に使った段階）。
- `StageSpec.complete(result, files)` は、`calculate` が入力から作った結果を解析のファイルで仕上げる口。入力エラーは解析の前に出る。`ReactionError`（CSV を読めない・ピックアップが欠ける）は生成のエラーにして何も公開しない。

## 帳票の落とし穴（GridLayoutPdf の部品）

- 「ここに、」の定義（`equations.definitions`）には続きの行がない。記号を空にすると「：」だけが出る。長い説明は式の行（`m.line`）にして定義の前に置き、定義は1行に収める（コロンの列 211 から本文の右端まで約 355pt）。
- `m.equation` の式の見出し（「平水位」など）は記号の左に収まる長さまで（`_LabelledBlock` が重なりを `LayoutOverflowError` にする）。
- 表で縦に結合したセル（`Span(rowspan=…)`）の下の行はそのセルを省くので、列の番号がずれて `TableSpec.numeric` の右揃えが外れる。数値のセルは `Span(値, align="right")` で揃えを明示する。
- 決定55（見本にない説明の文・「ここに、」・記号の式の段を書かない）より前に書いた帳票なので、見本にない文（γe2 の使い分けの文、回転の照査式など）が残っている。直すときは見本 8-27〜8-32 と並べて決定55に合わせる。
