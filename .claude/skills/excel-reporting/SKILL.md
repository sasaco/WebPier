---
name: excel-reporting
description: Create or revise this repository's editable graph-paper Excel calculation reports with renderer.GridReport. Use when matching a reference workbook's calculation layout, improving equations or explanatory rows, or checking the Excel-to-PDF result. Do not use for changing design inputs or solver calculations.
---

# 方眼Excel計算書の組版

このリポジトリの `AGENTS.md` を先に読み、対象章の生成コードで配置を変更する。`04_post/*.xlsx` と `05_output/*.pdf` は再生成する成果物であり、手編集しない。計算値と断面力選定は表示変更から独立させる。

## 見本から学ぶ配置

`02_pre/07_床版の照査/フーチングの計算.xlsm` の「C」「L」シート4～19行と、`slab_effective_width.py` の有効幅ページを比較した例：

- 見出しは「(1) 曲げモーメントに対する有効幅」→「1) く体前面位置…」→「(a) く体から決まる有効幅」の順に一段ずつ字下げする。出典は見出し付近に置く。
- 基本式の直後に「ここに」を置き、記号・コロン・定義・代入式・単位を列で揃える。定義行を無条件に1行おきにせず、関連する4行を続けて読めるようにする。
- 基本式、数値代入、比較、採用値を縦に追える順に置く。数値・演算子・単位は別セルにし、数値は数値型と表示形式を使う。長い式も幅が足りる限り横1行にする。
- 記号や短い数値のセルを広く結合しすぎない。見本の各項と生成後の結合範囲を比べ、表示に足りる最小限の列数を選ぶ。例えば有効幅ページの `O211` の「2」、`P251` の「d」、`V254` の「400」は2列、`N213` の「1808」は3列で足りる。幅を変えたら後続の項の開始列も確認する。
- 図の前に注記と寸法計算の場所を確保し、図とキャプションを離す。図だけ画像を使い、文章・式・表はExcelセルで編集できる状態を保つ。

見本の行列番号や式そのものを他章へ機械的にコピーしない。章の内容、32列×48行の印刷領域、必要な注記・図の高さに合わせて配置する。見本中の計算式と生成側の設計値が異なる場合は、正しい入力・計算ロジックを確認し、見た目を合わせるために値を変えない。

## 実装と確認

`GridPage.text` は見出し・文章の幅から必要行数を自動判定する。独立した項・数値・単位は `GridPage.grid` / `equation_grid` か個別セルで配置し、領域の重なりと折り返しを確認する。共通 `renderer/` を変えた場合は床版・柱・杭を再生成する。

再生成後は対象セルの値・型・結合、変更前後の計算値、印刷用PDFの文字切れ・折り返し・重なり・改ページを確認する。最終レイアウトはExcelから出力したPDFで判定し、描画が疑わしいときは別の描画エンジンでも照合する。
