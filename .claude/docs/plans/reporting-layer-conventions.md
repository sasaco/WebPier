# reporting 層の規約

`webpier/reporting/` に帳票を書くときの約束。原則は docs/adr/ と `.claude/docs/plans/refactoring-decisions.md`、
体裁の契約は `.claude/docs/reporting-style.md` を正とする。

## 値の印刷

- 帳票は calc の結果（`Printed` を持つ型）を受け取り、`Printed.value` を `Printed.digits` の桁でそのまま書く。
  丸め直し、桁の探索、`round`・`format` による桁の決定はしない（ADR-0003）。
- 桁区切り（3桁ごとのカンマ）や負号の書き方、単位の表記は表示の責務なので帳票が決めてよい。桁数は決めない。
  書式は `webpier/reporting/numbers.py` の1か所にまとめる。
- 式の行は、印刷される値だけで検算できる形にする（`0.245 × (1 − 18.850 / 200) = 0.222` のように、
  右辺の値は calc の結果の値をそのまま書く）。帳票の中で式を計算しない。
- 工学的な計算（合計・積・係数・単位換算）を帳票に書かない。必要な値が calc の結果にないときは、calc に足す。

## 文言と構成

- 帳票の見出し・項目名・文言は帳票側に置く。calc の結果は英語名だけを持ち、文言を持たない。
- 段階ごとの組版は `webpier/reporting/stages/<段階>.py`。1ファイルが大きくなる場合は、図・表・本文で分ける。
- 汎用の組版機能が足りなければ GridLayoutPdf に追加する（CLAUDE.md）。WebPier 側で回避しない。

## 決定性とテスト

- PDF は同じ入力・書体・ライブラリから同じバイト列になる（作成日時を含めない）。
- テストは三つ。
  1. 意味内容：印刷された数値と文字列が、calc の結果の値と印字桁に一致する。
  2. 体裁：`tests/fixtures/reporting/appearance` の、見本から測定した値（書体・大きさ・罫線・余白）に一致する。
     この fixture は見本から独立に作ったもので、新しい描画結果から作り直さない。
  3. 印刷物での検算：PDF から読み取った数値だけで、各式の右辺と合計が再現できる（決定15）。
- 層の境界テストを通す。reporting は core・inputs・calc 以外の webpier パッケージを import しない。
