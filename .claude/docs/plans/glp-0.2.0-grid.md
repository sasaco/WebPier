# WebPier の計算書を GridLayoutPdf 0.2.0 の共通グリッドで組み直す

作成 2026-10-21。依頼「`C:\Users\sasai\AppData\Local\Temp\handoff-webpier-gridlayoutpdf-0.2.0.md` を実装してください」（引き継ぎ：関内 EVピット部と同じ移行を WebPier に行う）。範囲は 2026-10-21 にユーザーに確かめた。手本は関内の `.claude/docs/plans/glp-0.2.0-grid.md` とコミット e6f21d6・3934fe3・38f8644・2ca243c・9df88c5。

## 決まったこと

ユーザーの回答（2026-10-21）：

| 項目 | 決定 |
|---|---|
| 深さ | **共通グリッド（A4、16.08×15.48pt、30列×47行）で組み直す**。本文・見出し 10pt、添字 6.5pt。式は `term_columns="grid"`、罫線は `TableBorders`（外枠 中・内側 極細）。0.12pt の格子はやめる。見本 P7 から測った位置の契約（X・行高・0.12/0.96pt の罫線、`test_report_appearance` の位置の照合）は、グリッド基準の契約に書き直す。 |
| GLP の入れ方 | **今は path 依存、release は後で**：`[tool.uv.sources] gridlayoutpdf = { path = "C:/Users/sasai/Documents/GridLayoutPdf" }`（関内と同じ）。CLAUDE.md の決まり（GitHub Release の wheel の URL 参照。git のない PC で `uv sync --locked` を通すため）とぶつかることを確かめたうえでの判断（2026-10-21 の2つめの回答）。CLAUDE.md は変えず、lock のコミットの説明に一時的と書く。v0.2.0 の Release を作って url に戻すまで push しない。**その後**（2026-10-21）：別のセッションが v0.2.0 の Release を作り url に戻した。0612・0622 の「B′」で見つかった GLP の方眼Excel の不具合（左辺が字形のインクで1列手前に終わる）を GLP で直し（ff276a6）、ユーザーの判断で v0.2.1 を release して WebPier をその wheel にした（4caeaf2）。 |
| 方眼Excel | **成果物にする**（関内 9df88c5 と同じ）。WebPier が組む頁を `export/<stem>.xlsx`（1冊1シート、`render_xlsx(strict=True)`）に出し、PDF・`post/` と一緒にステージングから一括公開する。 |
| structural-mcp | サブモジュールの参照は**更新しない**。 |

ここで決めた進め方（引き継ぎと関内に揃えた。異なれば指摘を受けて直す）：

| 項目 | 決め方 |
|---|---|
| 書体 | MS明朝・MSゴシックを名前（`"MS Mincho"`・`"MS Gothic"`）で引く。補助の役割も名前で引く：記号 `"MS PMincho"`、図題 `"MS PGothic"`、寸法 `"Calibri"`、衝撃係数の記号 `"Times New Roman Italic"`。`FontRegistry.register` は使わない。`runtime.dependency_hashes` は名前から解決した書体ファイルのバイトをハッシュする。 |
| ブランチ | 今の `sasa/glp`（main より9コミット先、アドインの作業）に積む。コミットは `git commit -- <paths>` で自分のファイルだけ。push しない。 |
| lock | `uv lock` で gridlayoutpdf の参照だけを path の 0.2.0 に替える（差分がそれだけであることを確かめる）。 |
| 方眼Excel の対象 | WebPier が組む頁のある段階すべて。0711・0721 は Aggre-SE の report.pdf そのもので WebPier の頁がないので、xlsx を出さない（`grid_documents` を持たない段階）。他のプログラムの頁（FEMPython・Capacita・JRSNAP）は xlsx に入れない。 |
| 合格の条件 | ① 計算値は不変：`output/*.json`・`post/` の値は実装のハッシュ以外が今と同じ。② 各冊の PDF の文字は、空白・改行・改頁を除いて今の PDF と同じ並び（他のプログラムの頁の日付などの差は分けて報告）。③ 頁数の変化は許し、報告する。④ WebPier が組む頁を PNG にして目視し、重なり・はみ出しがない。⑤ 方眼Excel：全段階で strict（ずらし・図形への切替えが0件）、Excel がある環境では GLP の `scripts/compare_xlsx_pdf.py` の検査すべてに合格。例外は GLP で受け入れ済みの制限（幅いっぱいの行・`text_clipped` の行の最後の1字の欠け）だけ。 |
| 品質ゲート | `.claude/check.ps1` の層ごとのカバレッジの下限（reporting 95% ほか）を保つ。 |

## 調べて分かったこと（2026-10-21）

- WebPier は `sasa/glp`、作業ツリーはきれい（引き継ぎにあった未コミットの変更は 402393b までにコミット済み）。
- 0.2.0 では import の時点で止まる：本文 9.9pt、`FontRegistry.register` の廃止、`Table(horizontal_rules=…)` の廃止（関内と同じ）。
- `document.py`・`equations.py`・`tables.py` は関内の移行前の版と同じ中身。関内の 3934fe3 の書き直しをほぼそのまま当てられる。`styles.py`・`assembly.py`・`figures/_draw.py` は少し違う。
- WebPier の位置（pt）は共通グリッドの列にきれいに対応する（原点 x 50.88）：章 58.92→0、節 73.44→1、項 87.96→2、小項 102.48→3、本文 117.00→4。
- 原稿の型は2系統ある。
  - `stages/frame_report.py` の `Manuscript`／`Unit`／`blocks`：0610・0620・0710・0720、0611・0621、0612・0622、0810・0820、0910、荷重モデルの frame・seismic。
  - `stages/reaction/manuscript.py`・`layout.py`：0600、0900、荷重モデルの reaction・cantilever。
  - 0500（`stages/foundation.py`）と 0800（`stages/footing.py`）は独自に組む。
- 差し込みは `stages/insertion.py` の `documents(units, insertions)` が WebPier の文書だけを返すので、`grid_documents` の入口にそのまま使える。
- WebPier はすでに openpyxl に依存している。

## 進め方

### 段階0（lead）準備

1. 今の実装（GLP 0.1.0）で基準を取る：全テストの結果、`output/*.pdf` の頁ごとの文字（空白を除く）と頁数、`output/*.json`・`post/` の値（実装のハッシュを除く）を scratchpad に書き出す照合スクリプトを作る。`output/` が HEAD の実装の出力と同じであることを付帯JSON で確かめる。
2. path 依存に替えて `uv lock`、`uv sync`。

### 段階1（lead・直列）共通部品と方眼Excel の枠（TDD）

Red を先に書く：`tests/reporting/test_grid_excel.py`（関内と同じ形）。全段階を代役の runner で生成し、公開した `export/<stem>.xlsx` が strict の1シートの書き出しと同じバイト列であること、Excel がある環境では Excel 比較に合格することを確かめる。`tests/grid_excel.py` 相当の補助は `tests/reporting/grid_excel_support.py`（`*_support.py` の名前の規則）。

共通部品を移す：

- `styles.py`：`A4_PORTRAIT_REFERENCE`、本文・見出し 10pt、`count`・`columns_pt`・`rows_pt`・`column_x`。`PITCH`・`grid_units`・`BODY_LEADING`・`INDENT`・`BASELINE` をやめる。
- `fonts.py`：書体名の表と、名前から解決した書体ファイル（依存のハッシュ用）。
- `tables.py`：`TableBorders`、列幅・行高は列・行の数。開いた表は `horizontal`/`vertical` の境目ごとの指定。`VerticalLabel` はグリッドに合わせて残すか、GLP の部品に替える。
- `equations.py`：`EquationGroup(term_columns="grid")`、`EquationAnchors` は列番号、形の違う式の群は `Stack` の子。
- `document.py`：字下げ・見出し・出典の位置を列で持つ。`report()` は書体を渡さない。
- `assembly.py`・`stages/insertion.py`：`grid_documents` の入口。
- `reporting/workbook.py`（新規）：`write_workbook(documents, path, sheet)`。
- `stages/frame_report.py` の土台（`Unit.left`・定数・`blocks`）：列の数にする。各段階の中身は段階2の担当。
- `pipeline`：`StageSpec.grid_documents`、`GenerationOptions.export_dir`、CLI の `--export-dir`、headless の出し先、`*.xlsx` の公開と付帯JSON。`runtime.dependency_hashes` の書体。
- `figures/_draw.py`：図の文字の大きさを 10pt に合わせる。図の枠はマスの倍数。

段階1の終わりに、各段階の import が通り、`grid_documents` の枠がある状態にする（中身の体裁がまだ崩れていてよい）。

### 段階2（並行・担当ごとにファイルを分ける）段階の帳票

各担当は `pier-report-style` と自分の段階の `webpier-*` スキルを先に読み、自分の段階の方眼Excel のテストを Red→Green にし、自分の `tests/reporting/` のテストを新しい契約に直して通す。共通部品（段階1）は変えない（要るなら lead に頼む）。コミットはしない。

| 担当 | 段階 | 持つファイル |
|---|---|---|
| A | 0500 | `stages/foundation.py`、そのテスト |
| B | 0600・0900（荷重モデルの reaction・cantilever も） | `stages/reaction/*`、`stages/cantilever/*`、`stages/generic/reaction.py`・`cantilever.py`、そのテスト |
| C | 0610・0620・0710・0720（荷重モデルの frame・seismic も） | `stages/longitudinal.py`・`transverse.py`・`seismic_longitudinal.py`・`seismic_transverse.py`、`stages/generic/frame.py`・`seismic.py`・`common.py`、`figures/model.py`・`figures/loads.py`、そのテスト |
| D | 0611・0621・0612・0622・0800・0810・0820・0910 | `stages/column_check.py`・`foundation_check.py`・`footing.py`・`footing_figures.py`・`footing_check.py`・`cantilever_check.py`、そのテスト |

`frame_report.py`・`insertion.py`・`pipeline/` の変更は lead が行う。

### 段階3（lead）検証と成果物

1. 全テスト（`.claude/check.ps1`、Excel 比較を含む）。
2. 基準との照合：文字の並び・頁数・結果JSON と `post/` の値。
3. WebPier が組む全頁を PNG にして目視する。
4. 本物の runner で `--stage all --frame-analysis --nonlinear-analysis --overwrite`。scratchpad に出して照合してから `output/`・`post/`・`export/` を置き換える。
5. 文書を直す：`.claude/docs/reporting-style.md`（グリッド基準の契約）、`pier-report-style` スキル、`webpier-*` スキルの古い 0.12pt・9.9pt の記述、`CLAUDE.md`（GLP の入れ方・`export/`・GridLayoutPdf の作業ツリーを試す手順）、`README.md`、`refactoring-decisions.md` に決定を足す。`tests/fixtures/reporting/appearance`（見本の測定値）は消さず、位置の照合だけをやめる。

コミットは分ける：lock、共通部品とテストの枠、段階の帳票、成果物・文書。

## 守ること

- 計算（`calc`）・入力・export は変えない。体裁だけを変える。
- 見本（`.claude/docs/Example橋脚*`）・`pre/`・見本の測定値（`tests/fixtures/reporting/appearance`）を変えない。
- テストの実行中に `webpier` のソースを編集しない（実装のハッシュの照合で失敗する）。並行の担当は互いのテストに影響するので、各担当は自分のテストのファイルだけを走らせ、全体は lead が流す。
- 生成を試すときは出し先を scratchpad に向ける。
- push・PR・GLP の release はしない。

## 見込みのリスク

- 行送りが 14.28→15.48pt に広がるので、頁数が増える（許す、報告する）。
- 表の列幅がマスの倍数になり、25列ほどに入らない表が出る。そのときは左へ寄せ、それでも入らなければ報告する。0620 の組合せ係数の表（行高 12.84pt、縦書きの帯）が最も窮屈な見込み。
- 0600 の括り線（`SideRule`）・フローチャート（`TextBox` など）・回転文字が方眼Excel の strict に通るかは試すまで分からない。通らなければ報告し、書き方を変えるか GLP の制限として扱うかを相談する。
- Excel 比較は1冊 20〜60秒。全段階で十数冊あるので、全テストが延びる。

## 結果（2026-10-21）

- コミット：714a796（lock、一時的な path）、4caeaf2（v0.2.1 の url）、ca91e09（共通部品・パイプライン・方眼Excel の枠）、10ffada（段階の帳票）、文書。GridLayoutPdf は ff276a6（方眼Excel の左辺の直し）と b9e86c3（0.2.1）、Release v0.2.1。
- テスト：acceptance 以外の 4098 件が合格。方眼Excel は全21冊（列車の15、荷重モデルの6）で strict と Excel 比較に合格した。`.claude/check.ps1` の層ごとのカバレッジは reporting 99.2%・gui 96.5%・ほか 100% で、すべて下限を超えた。acceptance の 28 件は移行前から落ちている（受入記録が今の入力と合わない。「受入時の入力から変わっています」）。
- 本物の runner での照合（GLP 0.1.0 の実装で出した基準と比べた）
  - 結果JSON・`post/` の値は、実装のハッシュ以外が同じ。`post/` でバイトが違うのは Aggre-SE の総括表（runner が書く日付）と JRSNAP の結果（毎回変わる）だけ。
  - PDF の文字は、空白を除いて16冊で同じ並び。0900 は文字が同じで並びだけが違う（回した表の置き場所）。0610・0620 は、組合せ係数の表を2つに分けたぶん、後半の表のケースの列（No・記号・荷重名称）が増えた。
  - 頁数：0610 19→20、0620 19→21、0612・0622 4→5。ほかは同じ。
- 目視：各担当が自分の段階の全冊の主な頁を、lead が 0500 p1・0600 p12・0610 p17・0612 p2 を PNG で確かめた。重なり・はみ出しは無い。
- 残したこと
  - 項の多い式は、frame_report のアンカー（＝11／22）では結果が次の行に回る（重なりではない。旧版は1行）。0610 p3・0620 p3 の鉛直力 N、0620 p7 のモーメント M、0710 p8・0720 p9 の H_w1〜3 とフーチングの H。アンカーを見直すかは別に決める。
  - 0500 の γ2 は、被りの区間が5つ以上だと30列に入らず LayoutOverflowError になるおそれがある（テストの範囲の4区間では入る）。そういう案件が来たら考える（利用者、2026-10-21）。
  - acceptance の 28 件（受入記録が古い）は放っておく（利用者、2026-10-21）。
  - 0900 の表 13.1 は、片側の桁に支承が8本以上あると30列を超える（移行前から同じ制限）。
