---
name: pier-report-style
description: WebPier の計算書（webpier/reporting の帳票・PDF と方眼Excel）を、GridLayoutPdf 0.2.0 の共通グリッド（A4、16.08×15.48pt のマス、30列×47行、MS明朝/ゴシック 10pt）で新しく作る・直す・確かめる。見本 .claude/docs/Example橋脚/output の構成・文言・式の書き方に合わせ、位置は列・行の数で持つ。帳票の追加や変更、式や表の書き方、体裁が見本と違うという指摘、PDF や方眼Excel（export/）のレイアウト調整、Excel 比較の不合格のときに使う。計算内容の変更には使わない。
---

# 共通グリッドで計算書を組む

計算書は、整った統一された体裁で、人が読みやすい文章にする。構成・文言・式の書き方は見本 `.claude/docs/Example橋脚/output/*.pdf` に合わせ、計算内容は calc の結果をそのまま印刷する。位置は GridLayoutPdf の共通グリッドのマスの数で持ち、同じ頁を方眼Excel（`export/<stem>.xlsx`）にも書く。

## 1. 正とする文書

- `.claude/docs/reporting-style.md`：体裁の契約（マス・書体・列・式・表・方眼Excel・検査）。
- `.claude/docs/plans/glp-0.2.0-grid.md`：共通グリッドへの移行の決定（2026-10-21）。
- `.claude/docs/plans/reporting-layer-conventions.md`：reporting 層の書き方。
- `docs/adr/0003-calculate-with-printed-digits.md`：印字桁。帳票は丸め直さず、計算しない。
- GridLayoutPdf の `docs/api.md` の「方眼Excelで重ならない書き方」。

数値や列がこのスキルと食い違えば、上の文書を正とする。

## 2. 体裁の規則

- 書体：本文 MS明朝 10pt、見出し MSゴシック 10pt、添字 6.5pt（下付き 1.92pt、上付き 4.92pt）。名前で引く（`styles.BODY_FONT` など）。白黒。字を縮めない。0.5pt 刻みでない大きさは使えない。
- 版面：`A4_PORTRAIT_REFERENCE`。位置は本文の左端からの列（0〜30）、高さは行。pt の座標を帳票に書かない（図の中の線と座標だけは pt）。頁番号は印刷しない。
- 行：本文・式・数式行とも1行が1グリッド行。超える行は `LayoutOverflowError`。
- 空き行：見出しの前後は空き1行。見出しが続いても重ねない。まとまりの間、表・図の前後も空き1行。表の題と表の間は空けない。頁頭の空き行は捨てる。
- 見出しの階層：章0・節1・項2・小項3、本文と細目4、字下げ5。全帳票（0500 も）同じ。出典【…】は列18から（長い見出しでは全角1字空けて入る最小の列）。
- 代入式：グリッドの項の列（`term_columns="grid"`）。各項は整数の列を占める。等号・結果の等号は列の境目に中心を置き、結果は境目で右揃え、単位は次の列から。帳票ごとのアンカーは reporting-style.md の表。項が列に入らない式は退避しないので、アンカーを見直すか式を分ける。
- 分数は横書き「a/b」。積み分数と分子の上付きは使わない。
- 「ここに、」の定義：記号右揃え、全角コロンの列、「(= 値 単位)」も列。
- 表：列幅・行高はマスの数で、左端＋列幅の合計が30以下。罫線は外枠 中・内側 極細。0610/0620 系の小表は開いた表（外枠・縦罫・見出し下の線なし、「合計」の上に中の線1本）。入らない表は左へ寄せる、分ける、回す。
- 見本にない説明の文、「ここに、」の記号の定義、記号の式の段（`N = ΣV × γ = …` の `ΣV × γ`）を足さない。式は「左辺 = 数値 = 結果」で書き、記号の行は見本が書いている式だけに残す。見本にある文は見本の文言で書く（決定55）。
- 入力票の記号（B1〜B9、H1〜H6、W3〜W9、df1、df2）は印刷しない。風荷重の W1/W2 は設計記号なので可。

## 3. 部品の使い方

`webpier/reporting/equations.py`・`document.py`・`tables.py`・`stages/frame_report.py` の部品を使い、列や間隔を段階ごとに作り直さない。

- `terms("0.245", "×", "(", "1", "−", "18.850", "/", "200", ")")`：代入式の右辺。括弧は1項にまとまる。
- `over("18.850", "200")`：横書き分数 18.850/200。
- `equation_group(eq1, eq2, left=4, first_equal=11, second_equal=22, result_right=26, unit_start=27, keep=…)`：アンカーは本文の列。形の同じ式は項の列を共有し、形の違う式は別の群になる。式の左のことばは `Equation(label=…)`。
- `definitions(Definition("k", "地盤反力係数", "12.3", "kN/m³"), ..., left=4, colon=8, value_equal=21, value_right=25, unit_start=26)`：「ここに、」の定義。
- `heading("5.1 支持力の算定", left=1, tag="【基礎標準 13.2.2.2】")`：見出しと出典。
- `math_line("・長期", left=4)`：1グリッド行に1行の文や数式。
- `paragraph(text, left=4, align=…)`：列の境目の手前で終わる行は Excel の印刷で最後の1字が欠けるので、1マス空けるか `align="justify"`。
- `tables.table(widths=(列…), rows, row_heights=(行…), inner=None, outer=None, horizontal={境目: tables.OUTER})`：必要な罫線だけを引く開いた表。縦書きのセルは `tables.VerticalLabel(text, 行の数)`。
- 0600 の `Manuscript.pair(...)`：1行に2つの文。2つめを決まった列から書く。
- 0600 の `Manuscript.formula`／`value`／`equation(..., checked=False)`：数値だけの式・値だけの段・記号の行（決定55）。
- フローチャート：GridLayoutPdf の `TextBox`（`rounded=True` で角丸の端子）・`TextDiamond`（判定）・`Connector`（折れ線＋矢じり）を `Figure` に置き、Yes/No は `Label`。図の枠はマスの数（`styles.columns_for`・`rows_for`）。方眼Excel では図形になる。例は `reporting/stages/column_check.py`。
- 括り線：0600 の `Manuscript.rule_start()`／`rule_end()`、layout が GridLayoutPdf の `SideRule`（中の線、行全体）で包む。
- 回した表：0600・0900 の `_rotated`（縦横を入れ替えた局所グリッドの `QuarterTurn`。方眼Excel では回転したセルになる）。
- ベクターの図（0400 の 4.1 配筋図、決定73）：GridLayoutPdf の `PdfFigure(col_span, rows, data, *, page=0, preview=…, align="center", valign="middle", block_id=…)` で、別に描いた PDF の頁をベクターのまま枠に置く（2026-10-21 は GridLayoutPdf `sasa/pdf-figure` の f2e618b で未 Release。API は計画書 `phase-0400-detailing.md` の Phase 5）。`data` は PDF のバイト列、`preview` は同じ頁の PNG（方眼Excel はそれを画像で置く。WebPier は `render_xlsx(strict=True)` なので `preview` がないと止まる）。`QuarterTurn` には入れられない。図は `webpier.export.drawing.drawing_figures(pier)` の (PDF, PNG) をそのまま渡し、WebPier で PDF を重ね書きしない。
- 0400 照査の前提（`reporting/stages/detailing.py`）：文言・式・表は見本 `0400_照査の前提.pdf`、見本にない項目は Example2 06 6.3〜6.8。見出しの条文番号（出典）は見本どおり印刷する。見出しと出典が1行に入らない (b)・(c) は出典を本文の末尾に置く（Ex2 6.3(2) の書き方）、6) の2つの出典は列14 から。断面力を使う照査は参照先の節の文だけ（番号は `COLUMN_SECTIONS`・`FOOTING_SECTIONS`・`CANTILEVER_SECTIONS` の表）。4.1 の図は `render_detailing`・`grid_documents`・`content` の `figures`（`{"beam"|"column"|"footing": FigureSpec}`）で渡し、なければ見出しだけ。
- 他のエンジンのページの差し込み（0610・0620 の荷重図＝FEMPython、0611・0621・0810・0820・0910 の節＝Capacita、0710・0720 のデータ確認図と荷重図＝JRSNAP）：`reporting/stages/insertion.py` の1つの仕組みで行う。段階は差し込む場所を `Insertion(<ページの名前>, <単位のキー>, before=…, optional=…)` で宣言し、`render_with_pages` が原稿をその位置で文書に分けて描き、`assembly.join` でつなぐ。`documents(...)` は同じ分け方で WebPier の文書だけを返し、各段階の `grid_documents` が方眼Excel に使う。`render_*` と `grid_documents` は同じ原稿を作ること（Capacita が飛ばした節で原稿が変わる段階は、`pages` を両方に渡す）。エンジンのページは書き換えず、決定性も求めない。エンジンの中にだけある値は解説に印刷しない（ADR-0008）。

## 4. 手順

1. 見本の対応頁を画像にして読む。現行と並べるなら次のスクリプト（引数の PDF は書き換えない。100dpi、左が見本・右が現行）。
   `uv run --project "." --locked python -X utf8 .claude/skills/pier-report-style/scripts/compare_pages.py --reference ".claude/docs/Example橋脚/output/0500_直接基礎.pdf" --current output/0500_直接基礎.pdf --pages 1,2 --out <scratchpad>`
2. manuscript（content）に意味の単位（見出し・式の組・定義・表・図）を書く。数値は calc の `Printed` をそのまま使い、帳票で計算しない。足りない値は calc に足す。
3. 組版する。上の部品で書き、空き行は `blank()` で入れる。
4. `render_*` 関数で scratchpad に PDF を出し、`compare_pages.py` で見本と並べて目視する。方眼Excel は `tests/reporting/test_grid_excel.py -k "train-0600"` のように段階を選んで確かめる（strict と Excel 比較。Excel 比較は1冊 20〜60秒）。
5. テストを足す・直す。意味内容（`test_*_semantics.py`）、体裁（`test_*_pdf.py` と `test_report_spacing.py`・`test_report_definitions.py`・`test_report_equation_terms.py`・`test_frame_report_style.py`・`test_grid_excel.py`）、印刷物での検算。
6. `& ".claude/check.ps1"` を通す（reporting は行・分岐カバレッジ 95%）。
7. 帳票だけを直したときは、直す前の結果 JSON を scratchpad に写しておき、入力の `outputs` でその段階の出力項目（と使う項目）だけを選んだ写しから `--overwrite` で作り直した結果 JSON と比べる（決定72）。違うのが `implementation_sha256` だけなら計算は変わっていない。

見本の使い分け：利用者が「Example橋脚2 のような式の表現に」と言うときは、式の書き方（何を何行で書くか、見出しの構成）を Example橋脚2 に合わせ、列・空き行は reporting-style.md の契約を使う。`tests/fixtures/reporting/appearance` の見本の実測は、共通グリッドへの移行（2026-10-21）で位置の基準ではなくなった。式を1行に収めるために列を動かすときは、その帳票の同じ意味の行のアンカーをそろえて動かす。

## 5. GridLayoutPdf との責務分界

組版・レイアウト・PDF 描画の汎用機能が足りなければ `C:\Users\sasai\Documents\GridLayoutPdf` を直す。WebPier 側でのモンキーパッチ・コードの複製・内部 API への依存・代替実装はしない。橋脚固有の文言や帳票構成は WebPier に置く。

1. GridLayoutPdf の `AGENTS.md` から辿れる規則に従う（TDD、`run_tests.py`、`update_design.py`、docs/api.md と DESIGN.md の更新、片持ち梁37頁 manifest の SHA 更新）。
2. そのリポジトリのテストを通す。
3. 試すときは、手元の作業ツリーを venv に入れて `--no-sync` で走らせる（CLAUDE.md の「手元の GridLayoutPdf の作業ツリーを試す」）。`--locked` の実行は venv を lock の版に戻す。
4. 取り込むときは、GridLayoutPdf の版を上げてコミット・push し、タグと再現できる wheel の Release を作ってから、WebPier の `url` を差し替えて `uv lock`・`uv sync --locked` する（CLAUDE.md の手順。v0.2.1 の例：版上げ b9e86c3、wheel を2回作って SHA-256 が同じことを確かめてから載せる）。Release の作成は外への公開なので利用者の承認を得る。手元の path 依存は一時的なもので、push しない。

これまでに足した汎用機能：`TermStop`／`EquationGroup(term_columns="grid")`、`Spacer(discard_at_page_top=True)`、`Leading(overhang=)`、`TextBox`／`TextDiamond`／`Connector`／`Rectangle(corner_radius=)`（DESIGN.md の FR-019）、`SideRule`（式のまとまりを括る左の縦線。FR-020）、方眼Excel `render_xlsx`（FR-021）、罫線の種類 `BorderStyle`／`TableBorders`（FR-022）、書体を名前で引く（FR-024）。方眼Excel の左辺を等号の境目の左の列まで届かせる直し（「B′」のように字形が左に寄った記号。2026-10-21）。ベクター PDF の図 `PdfFigure`（FR-028、依存に pypdf>=6,<7。2026-10-21 は未 Release）。

GridLayoutPdf の部品を足すときの注意：`measure_block` は `Line` のインクの範囲を線幅の半分だけ四方に広げて数える（butt cap でも長さの方向にも広げる）。part の高さいっぱいの縦線を `Line` で引くと part からはみ出して `LayoutOverflowError` になるので、part をまたいでつながる線は塗りの `Rectangle(stroke=False)` で描く（範囲がちょうど箱になる）。全体のカバレッジは `run_tests.py --target tests --cov gridlayoutpdf --min-coverage 90` で確かめる。

GridLayoutPdf の描画のソースを変えると、片持ち梁37頁の画素比較テストが固定しているソースの SHA が食い違う。画素が一致することを確かめたうえで、変えたファイルの固定値だけを更新し、`manifest.json` の notes に理由を書く。並行して別のセッションが WebPier を編集しているときは、取り込み直し（`--reinstall-package`）が相手の実装ハッシュの照合も変えるので、区切りを待つか相手に知らせる。

## 6. 落とし穴

- 入力票の記号を式に書かない。値の代入式にするか、計算書内で定義した記号を使う。
- `"("` などを平たく並べると括弧の中で折り返す。`terms` の括弧グループを使う。
- 括弧グループが1行に入らないほど長いときだけ `open_groups` で中を折り返させる。0600 の列車反力 RB＝P×(a1＋…)/l は9軸以上で折り返す（`reporting/stages/reaction/train.INLINE_AXLES`。P7橋脚の 61.39 m の桁に12軸で 509.85 pt＞406.32 pt、2026-10-20）。`open_groups` は短い式の項の間の空白も変えるので、いつも付けない。
- 積み分数は1行のグリッド行を壊す。`over()` を使う。
- 先頭の全角空白で字下げしない。方眼Excel で位置がずれる。字下げは `left=` の列で行う。
- 群にまとめた式の項がグリッドの列に入らなくなると、`equation_group` はその式を群に入れない。それでも1式が入らなければ `LayoutOverflowError`（`term_fallback`）なので、行を分ける（0600 の `layout.py` は続きの行の先頭の演算子を等号の列に置く）。
- 方眼Excel の Excel 比較の不合格は、比較の `result.json` の `outside`（`no_cell`・`clipped` など）で原因を読む。受け入れ済みの制限は「幅いっぱいの行・`texts_clipped` の行の最後の1字の欠け」だけ（`tests/reporting/grid_excel_support.py`）。
- 文字の縮小・伸縮で固定頁数に収めない。まとまりを保って改ページする。
- `tests/fixtures/reporting/appearance` を新しい出力から作り直さない（見本から独立に測った値）。
- テスト実行中に `webpier` のソースを編集しない（実装ハッシュの照合で失敗する）。
- 並行作業中は `python -m webpier` の CLI（`output/` を書き換える）ではなく `render_*` 関数で scratchpad に出す。`output/` を作り直すよう頼まれたら、まず全段階で試し、別の段階が途中の実装で失敗したら（一括公開なので何も変わらない）入力の写しの `outputs` を直した段階の出力項目（と使う項目）だけにして作り直す（決定72。段階を選ぶ引数はない）。
- 並行作業中の `check.ps1` は、相手がファイルを消すと「No source for code」やそのファイルのテストの失敗で止まる。自分の変更の可否は、直した帳票のテスト（例：`-k "reaction or report_equation_terms or report_spacing"`）で判断し、全体の検査は相手の区切りを待って流し直す。
- 線（括り線など）で空き行が見える部品になると、keep の鎖（`KeepWithNext` は次の「見える」部品と同じ頁に置く）が空き行で切れ、まとまりの最後の行だけ次の頁に送られる。線を引く空き行は、前の部品が keep なら `KeepWithNext` で包む。
- TTC を何度も読む検査は遅い。フォント名はモジュールで1回求める。
- 空き行は `blank()` で足し、重ねない。
- 文や段を消す前に、その段だけが印刷している結果の値がないか確かめる。結果の全値が計算書に出ることをテストが確かめる（0600 の 6.3 2) の「（安全性（疲労破壊））iF(単線)・iF(複線)」は見本にない重複に見えるが、`train.fatigue.*_impact` を印刷する唯一の段なので残す）。
- 組合せの名前の数値（「0.8 LR」）は値ではなく名前。係数の印字値から名前を作ると 0.8 LR が「1.0 LR」になるので、名前は表（0600 の `CASES`）に持ち、値から作るのは γB のような係数の部分だけにする。
- 体裁のテスト（`test_*_pdf.py` の ROLES など）は行を文言で選ぶ。文言を変えたり消したりしたら、同じ役割（同じ x）の残る行の文言に選び直す（StopIteration で落ちる）。

## 7. 共通グリッドへの移行で踏んだこと（2026-10-21、決定71）

移行の記録は `.claude/docs/plans/glp-0.2.0-grid.md`。手本は関内 EVピット部の同じ移行（`evpit-design` スキルの同名の節）。

**式**
- アンカーの境目は厳密に増える。等号は列の境目に中心を置くので、左辺は「左端の列〜等号の列の1つ手前」に、ことばのラベル（`Equation(label=)`、自動の幅は最大 96.48pt）と左辺と間 4pt が入らないといけない。入らないとラベルが折り返して「leading of 1 rows is smaller than a measured line of 2 rows」になる。等号の列を右へ動かすか、左辺を短い記号にする。
- 項は1つずつ整数の列を取るので、見本より横に長い。結果の等号まで右辺が入らない式は、結果が次の行の結果の列に回る（重なりではない）。frame_report の＝11／22 で回っている式：0610 p3・0620 p3 の鉛直力 N、0620 p7 のモーメント M、0710 p8・0720 p9 の H_w1〜3 とフーチングの H。1行に戻すなら、frame_report のアンカーを帳票ぐるみで見直す（0600 は結果の等号を23にしている）。
- 右辺そのものが30列に入らないと `term_fallback` で `LayoutOverflowError`。0600 は `layout.py` で「=」「+」「−」（だめなら「×」「/」）の前で行を分け、続きの行の先頭の演算子を等号の列に置く。照査系は原稿の単位を2つに分けて `left=` で字下げする。どちらも文字と並びは変えない。
- 被りの層が多い 0500 の γ2 は、区間が5つ以上だと30列に入らないおそれがある（4区間までは入る）。起きたら考える（2026-10-21、利用者）。
- 形の違う式は別の群（`Stack` の子）になる。群は1つの part で、改頁は群の境目のうち keep でない式の後だけ。群に加えると項が入らなくなる式は加えない（`equations.py`）。
- 先頭の全角空白で字下げしない。方眼Excel で位置がずれる（0611 の「× (Vpd+Vcd)…」、0910 の Mtud2・Mtud3 で 35pt）。字下げは `left=` の列で。

**表・図**
- 列幅は中身の字数から見積もる：全角 10pt、半角 約5pt、左右の余白 3pt ずつ。1列（16.08pt）に「1.35」は入らない。30列に入らない表は左へ寄せ、それでも入らなければ分ける（0610・0620 の組合せ係数の表は `TableParts` で要求性能の変わり目で2つに分け、後半にもケースの列を出す）か回す。
- 回す表は縦横を入れ替えた局所グリッド（`GridSpec(0, 0, PITCH_Y, PITCH_X, …)`）で `QuarterTurn`。こうしないと方眼Excel で図形への切替え（`quarter_turn`）になり strict に落ちる。縦書きのセルは `tables.VerticalLabel`。
- 添字のあるセルは、セルごとに上下中央に置くと同じ行の数値より 0.7pt 上に出る。frame_report の1行の本文のセルは `CELL_BASELINE` で行の基線をそろえる。上付きのある見出しのセル（N/mm²）に固定の基線を渡すと「content lacks clearance」になるので、見出しは中央のまま。
- 図の枠は `columns_for`・`rows_for`。図題が図の上端に近いと、図が頁の先頭に来たとき方眼Excel が前の頁にも描いて切る（0800 の地盤反力形状）。図題を下げる。
- 括り線（`SideRule`）の上下を行の途中で縮めると `border_off_grid` で strict に落ちる。行全体に引く。

**方眼Excel と Excel 比較**
- 本文の右端まで届く行・列の境目の手前で終わる行は、Excel の印刷で最後の1字が欠ける（`texts_clipped`、受け入れ済みの制限）。「[… の組合せ]」の「]」のように落としたくない字は、1マス空けるか行を分ける。
- 添字の多い項は Excel が PDF より狭く描く（1字あたり約2pt）。記号式は項を左寄せにし、括弧の中を「+」で分けて項を短くする（0500 の γ2）。
- 「B′：」のように字形が送り幅の左に寄った左辺は、GridLayoutPdf 0.2.0 では1列手前で終わって Excel 比較の `no_cell` になった。0.2.1 で直した（左辺は等号の境目の左の列まで）。似た症状は GridLayoutPdf を直す。
- 比較の不合格は `result.json` の `pages[].outside`（`failures`：`clipped`・`no_cell` など、`dx_pt`・`dy_pt`）で読む。`tests/reporting/grid_excel_support.py` は比較スクリプトを GridLayoutPdf のチェックアウト（`GRIDLAYOUTPDF_CHECKOUT`、既定は手元）から読む（Release の wheel にスクリプトは無い）。

**テストと作業の進め方**
- `test_grid_excel.py` は段階ごとに代役の runner で単独生成し、生成が `write_workbook` に渡した文書を記録して、その文書で strict と Excel 比較を行う（Capacita が飛ばした節で原稿が変わる 0611・0621・0910 も、公開物と同じ文書で調べられる）。入力は current.json にフーチングの鉄筋を足したもの（0800〜0820 に要る）。`-k "train-0610"`・`-k "addin-0600"` で段階を選ぶ。Excel 比較は1冊 20〜60秒、全体のテストは約20分、`check.ps1` は約35分。
- 開いた表には上の線が無いので、空き行の検査は罫線ではなく配置の metadata（parts の "cells"）で表の範囲を取る（`test_report_spacing.py`）。
- 帳票の作り直しでは、文字の並び（空白を除く）と結果JSON・`post/` の値（実装のハッシュを除く）を前の実装の出力と比べる。並びが違うときは文字の多重集合も比べ、並べ替えか増減かを見分ける。比べる基準は今の実装で出し直す（`output/` は古いことがある）。
- 並行で担当を分けると、別の担当の編集で生成テストが「生成中にプログラム・描画依存が変更されました」で落ちる。重なっただけなので走らせ直す。共通部品は担当が終わってから直す。
- Python の `Path.write_text` は Windows で CRLF にする。`.py` は LF なので `write_bytes` か Edit を使う。引用符の多い Python を Bash の heredoc で渡さない（ファイルに書いて動かす）。
