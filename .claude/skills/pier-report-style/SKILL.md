---
name: pier-report-style
description: WebPier の計算書（webpier/reporting の帳票・PDF）を、見本 .claude/docs/Example橋脚/output の体裁（MS明朝/ゴシック 9.9pt、行送り14.28pt、空き行、式の列揃え、定義リスト、余白）で新しく作る・直す・確かめる。帳票の追加や変更、式や表の書き方、体裁が見本と違うという指摘、PDF のレイアウト調整のときに使う。計算内容の変更には使わない。
---

# 見本の体裁で計算書を組む

計算書は、整った統一された体裁で、人が読みやすい文章にする。体裁は見本 `.claude/docs/Example橋脚/output/*.pdf` に合わせ、計算内容は calc の結果をそのまま印刷する。

## 1. 正とする文書

- `.claude/docs/reporting-style.md`：体裁の契約（書体・X・等号列・表・フレーム・行送り・式の書き方・検査）。
- `.claude/docs/plans/reporting-layer-conventions.md`：reporting 層の書き方と体裁の部品。
- `docs/adr/0003-calculate-with-printed-digits.md`：印字桁。帳票は丸め直さず、計算しない。

数値や座標がこのスキルと食い違えば、上の文書を正とする。

## 2. 体裁の規則

- 書体：本文 MS明朝 9.9pt、見出し MSゴシック 9.9pt、添字 6.5pt（下付き 1.92pt、上付き 4.92pt）。白黒。
- フレーム：(48,86.28)-(576,792)、基線 offset 11.52pt。どの頁も1行目の基線は 97.80pt。頁番号は印刷しない。
- 行送り：本文・式・数式行とも 14.28pt。添字のはみ出しは `overhang=0.12` で許し、行送りを広げない。`Leading` は厳格（`minimum=False`）で、超える行は `LayoutOverflowError`。
- 空き行：見出しの前後は空き1行（基線差 28.56pt）。見出しが続いても重ねない（42.84pt にしない）。記号式の組・「ここに、」の定義・「・長期」とその式などのまとまりの間、表・図の前後も空き1行。表の題と表の間は空けない。頁頭の空き行は捨てる。
- 見出しの階層：刻み 14.52pt。0600 等は章 58.92／節 73.44／項 87.96／小項 102.48、本文 117.00。0500 は章 93.96 から。
- 代入式：数値右揃え・演算子中央の列、間 `TERM_GAP = 7.44pt`（見本 0500p1 の 9.2〜9.4pt と 0600p16 導出列の 5.8〜8.7pt を1つの値に統一し、0600 の導出列で「T = 1.0 × LR = 1.0 × 200.00」が結果と同じ行に収まる値）。連続する式は行をまたいで列をそろえるが、列を共有するのは項の列の形（列数と揃えの並び）が同じ式だけ。結果の等号・右端・単位は意味構成ごとの列（0500 代入式 184.44／460.32、0600 導出 276.72／436.44）。入らない式は通常の折り返し（4.95pt）に退避。括弧の中で折り返さない。
- 分数は横書き「a/b」。積み分数は使わない。
- 「ここに、」の定義：記号右揃え、全角コロンの列（0500 は x211.0 付近）、「(= 値 単位)」も列。
- 見出しの出典【…】：見出しの右端 +9.9pt 以上で 340.8 + k×14.52 の最小の x。
- 表：細罫 0.12pt、太罫 0.96pt。0610/0620 系の小表は開いた表（外枠・縦罫・見出し下の線なし、「合計」の上に 0.96pt の線1本）。
- 入力票の記号（B1〜B9、H1〜H6、W3〜W9、df1、df2）は印刷しない。風荷重の W1/W2 は設計記号なので可。

## 3. 部品の使い方

`webpier/reporting/equations.py`・`document.py`・`tables.py` の部品を使い、座標や間隔を段階ごとに書き直さない。

- `terms("0.245", "×", "(", "1", "−", "18.850", "/", "200", ")")`：代入式の右辺。括弧は1項にまとまる。
- `over("18.850", "200")`：横書き分数 18.850/200。
- `equation_group(eq1, eq2, first_equal=184.44, result_right=460.32)`：連続する式の列をそろえる。
- `definitions(Definition("k", "地盤反力係数", "12.3", "kN/m³"), ..., left=123, colon=211.0)`：「ここに、」の定義。
- `heading("5.1 支持力の算定", tag="【基礎標準 13.2.2.2】")`：見出しと出典。
- `math_line("・長期")`：14.28pt の行に1行の文や数式。
- 0600 の `Manuscript.pair(key, "・0.8 LR", "[… の組合せ]", left, second_left)`：1行に2つの文を置き、2つめを決まった x（0600p16 は 218.64）から書く。
- 式の左辺の置き方：`wide=True` は左辺をラベルとして左端（`left`）に左寄せし、その後に等号を置く。ラベルは等号の列より約4pt手前で終わらないと「text does not fit」や余分な1行になる。「※ T1」「Rm」のように等号のすぐ前に来る短い記号は、ラベルにせず左辺（右寄せ）にする。等号の列は `equal=` で式ごとに指定できる。
- 「a / b」のような短い行は、下の行と項の形（列数・揃え）が同じだと列を共有して「320.00 /        2」と間延びする。`ratio()`／`over()` で1項の a/b にすれば共有しない。
- `blank(out)`：空き行。頁頭で捨てられ、重ならない（`spacer()` を直接重ねない）。
- `tables.table(widths, rows, horizontal_rules=[...], vertical_rules=[])`：必要な罫線だけを引く開いた表。
- フローチャート：GridLayoutPdf の `TextBox`（`rounded=True` で角丸の端子）・`TextDiamond`（判定）・`Connector`（折れ線＋矢じり）を `Figure` に置き、Yes/No は `Label`。文字は自動縮小せず、はみ出せば `LayoutOverflowError`。例は `reporting/stages/column_check.py` の `flowchart`。見本の箱の中で切れた文字（「σb ≦」だけ等）は再現せず、判定条件を書き切る。
- 括り線：「※ T1 … ※ ∴ H」のように式のまとまりを左の縦線で括るときは、0600 の `Manuscript.rule_start()`／`rule_end()` で印を付け、layout が GridLayoutPdf の `SideRule` で包む（前後の空き行も含め、最初に `top`、最後に `bottom`）。線は空き行を見える部品にするので、まとまりの keep の鎖は空き行も `KeepWithNext` でつなぐ。
- 他のエンジンのページの差し込み（荷重図＝FEMPython、0611 の結果表＝Capacita）：原稿を差し込み位置で文書に分けて描き、`assembly.join` で「WebPier の部品 → エンジンのページ」の順につなぐ。エンジンが返す頁範囲で切るのは `assembly.page_range`。エンジンのページは書き換えず、決定性も求めない。エンジンの中にだけある値（RC標準の制限値の表など）は解説に印刷しない（ADR-0008）。

## 4. 手順

1. 見本の対応頁を画像にして読む。現行と並べるなら次のスクリプト（引数の PDF は書き換えない。100dpi、左が見本・右が現行）。
   `uv run --project "." --locked python -X utf8 .claude/skills/pier-report-style/scripts/compare_pages.py --reference ".claude/docs/Example橋脚/output/0500_直接基礎.pdf" --current output/0500_直接基礎.pdf --pages 1,2 --out <scratchpad>`
2. manuscript（content）に意味の単位（見出し・式の組・定義・表・図）を書く。数値は calc の `Printed` をそのまま使い、帳票で計算しない。足りない値は calc に足す。
3. 組版する。上の部品で書き、空き行は `blank()` で入れる。
4. `render_*` 関数で scratchpad に PDF を出し、`compare_pages.py` で見本と並べて目視する。
5. テストを足す・直す。意味内容（`test_*_semantics.py`）、体裁（`test_*_pdf.py` と `test_report_spacing.py`・`test_report_definitions.py`・`test_report_equation_terms.py`・`test_frame_report_style.py`）、印刷物での検算。
6. `& ".claude/check.ps1"` を通す（reporting は行・分岐カバレッジ 95%）。

見本の使い分け：利用者が「Example橋脚2 のような式の表現に」と言うときは、式の書き方（何を何行で書くか、見出しの構成）を Example橋脚2 に合わせ、座標・列・空き行は体裁の基準 Example橋脚/output の実測を使う。式を1行に収めるために列を動かす前に、`tests/fixtures/reporting/appearance/reference-style.json` の役割（例：`horizontal.first_equals` は 276.72）が固定している列でないか確かめる。固定されている列は動かさず、別の意味の行（例：固定支承の候補）だけに別の列を与える。`TERM_GAP` など全体の値は変えない。

## 5. GridLayoutPdf との責務分界

組版・レイアウト・PDF 描画の汎用機能が足りなければ `C:\Users\sasai\Documents\GridLayoutPdf` を直す。WebPier 側でのモンキーパッチ・コードの複製・内部 API への依存・代替実装はしない。橋脚固有の文言や帳票構成は WebPier に置く。

1. GridLayoutPdf の `AGENTS.md` から辿れる規則に従う（TDD、`run_tests.py`、`update_design.py`、docs/api.md と DESIGN.md の更新、片持ち梁37頁 manifest の SHA 更新）。
2. そのリポジトリのテストを通す。
3. WebPier に取り込み直す：`uv sync --project "." --locked --reinstall-package gridlayoutpdf`（取り込み直さないと実装ハッシュが食い違いテストが失敗する）。

これまでに足した汎用機能：`TermStop`／`EquationGroup(term_gap=)`、`Spacer(discard_at_page_top=True)`、`Leading(overhang=)`、`TextBox`／`TextDiamond`／`Connector`／`Rectangle(corner_radius=)`（DESIGN.md の FR-019）、`SideRule`（式のまとまりを括る左の縦線。FR-020）。

GridLayoutPdf の部品を足すときの注意：`measure_block` は `Line` のインクの範囲を線幅の半分だけ四方に広げて数える（butt cap でも長さの方向にも広げる）。part の高さいっぱいの縦線を `Line` で引くと part からはみ出して `LayoutOverflowError` になるので、part をまたいでつながる線は塗りの `Rectangle(stroke=False)` で描く（範囲がちょうど箱になる）。全体のカバレッジは `run_tests.py --target tests --cov gridlayoutpdf --min-coverage 90` で確かめる。

GridLayoutPdf の描画のソースを変えると、片持ち梁37頁の画素比較テストが固定しているソースの SHA が食い違う。画素が一致することを確かめたうえで、変えたファイルの固定値だけを更新し、`manifest.json` の notes に理由を書く。並行して別のセッションが WebPier を編集しているときは、取り込み直し（`--reinstall-package`）が相手の実装ハッシュの照合も変えるので、区切りを待つか相手に知らせる。

## 6. 落とし穴

- 入力票の記号を式に書かない。値の代入式にするか、計算書内で定義した記号を使う。
- `"("` などを平たく並べると括弧の中で折り返す。`terms` の括弧グループを使う。
- 積み分数は行送りを壊す。`over()` を使う。
- 文字の縮小・伸縮で固定頁数に収めない。まとまりを保って改ページする。
- `tests/fixtures/reporting/appearance` を新しい出力から作り直さない（見本から独立に測った値）。
- テスト実行中に `webpier` のソースを編集しない（実装ハッシュの照合で失敗する）。
- 並行作業中は `python -m webpier` の CLI（`output/` を書き換える）ではなく `render_*` 関数で scratchpad に出す。`output/` を作り直すよう頼まれたら、まず全段階で試し、別の段階が途中の実装で失敗したら（一括公開なので何も変わらない）`--stage 0600 --overwrite` のように直した段階だけ作り直す。
- 並行作業中の `check.ps1` は、相手がファイルを消すと「No source for code」やそのファイルのテストの失敗で止まる。自分の変更の可否は、直した帳票のテスト（例：`-k "reaction or report_equation_terms or report_spacing"`）で判断し、全体の検査は相手の区切りを待って流し直す。
- 線（括り線など）で空き行が見える部品になると、keep の鎖（`KeepWithNext` は次の「見える」部品と同じ頁に置く）が空き行で切れ、まとまりの最後の行だけ次の頁に送られる。線を引く空き行は、前の部品が keep なら `KeepWithNext` で包む。
- TTC を何度も読む検査は遅い。フォント名はモジュールで1回求める。
- 空き行は `blank()` で足し、重ねない。
