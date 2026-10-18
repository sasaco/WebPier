# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

鉄道橋脚の設計計算（0500直接基礎・0600上部工反力・0610線路方向荷重・0620直角方向荷重・0710/0720地震時荷重）を `pre/input.json`（schema 2）から行い、A4白黒の計算書PDFと結果JSON、FEMPython/FrameWeb入力、JRSNAP用NDUを生成する。骨組解析は FEMPython に任せ、結果を解釈せずに出力する（ADR-0006）。部材照査・最適化は対象外。仕様の詳細は `README.md`、用語は `CONTEXT.md`、原則は `docs/adr/`、決定事項は `.claude/docs/plans/refactoring-decisions.md` を正とする。

## コマンド

すべてリポジトリのルートで、`uv` の `--locked` 環境を使う。

```powershell
# 計算・PDF生成（既定は --stage all。既存成果物の更新には --overwrite）
uv run --project "." --locked python -m webpier --overwrite
uv run --project "." --locked python -m webpier --stage 0610 --overwrite   # 0500/0600/0610/0620/0710/0720/all
# 0610/0620 は FrameWeb入力、0710/0720 は JRSNAP入力（NDU）も常に post/ に出力する
# run_design.py は python -m webpier と同じ

# 入力エディタ（Tkinter/tksheet。edit_input.py も同じ。VS CodeのF5でも起動）
uv run --project "." --locked python -m webpier.gui

# 品質ゲート（全件をカバレッジ付きで実行し、層ごとの行・分岐カバレッジの下限も照合する。決定15）
# core/inputs/calc/export/pipeline 100%、reporting 95%、gui 85%。下回れば exit 2。JSON の tools.coverage に層ごとの値
& ".claude/check.ps1"
# テスト（全件。カバレッジなし）
uv run --project "." --locked --group dev python -X utf8 -m pytest tests -q
# 単一ファイル／単一テスト
uv run --project "." --locked --group dev python -X utf8 -m pytest tests/calc/test_foundation.py -q
uv run --project "." --locked --group dev python -X utf8 -m pytest "tests/calc/test_foundation.py::test_name" -q

# GridLayoutPdf のソースを変更した後の取り込み直し
uv sync --project "." --locked --reinstall-package gridlayoutpdf
```

Windows専用。帳票は `%WINDIR%/Fonts` の MS明朝・MSゴシック・Calibri・Times Italic が必須で、書体がなければ生成を停止する。0610・0620 の荷重図は FEMPython の Headless runner で描くので（ADR-0005、`webpier/pipeline/fempython.py`）、リポジトリのルートの `.env`（追跡しない）に `STRUCTURAL_MCP_FEMPYTHON_RUNNER='<FEMPython>\FrameWebforCS\Headless\bin\Release\net10.0-windows\FrameWebforCS.Headless.exe'` を書く（プロセスの環境変数が優先）。未設定なら 0610・0620 を含む生成は停止する。テストは `tests/conftest.py` が代役の runner に置き換える。テストは `webpier` のソースもハッシュするので、テスト実行中にソースを編集しない（生成中の実装変更として失敗する）。

## アーキテクチャ

### 層別パッケージ（ADR-0004）
`webpier/` の下に層を分け、依存は下向きだけにする。`tests/test_layer_boundaries.py` が強制する。

`core ← inputs ← calc ← reporting / export ← pipeline ← gui`

- `core`: 印字桁つきの値 `Printed`、厳密なJSON読込み、エラー、ハッシュ。
- `inputs`: schema 2 の解析と検証。`fields.py` の項目表（桁・単位・符号・選択肢・予約項目）をparserとエディタが共用する。選択肢は `choices.py`。
- `calc`: 段階の計算。結果は `Printed` を持つ frozen dataclass で、描画に依存しない。
- `reporting`: GridLayoutPdf で組む帳票（`reporting/stages/`）。工学計算をここに置かない。
- `export`: `frameweb`（FEMPython/FrameWebforCS）、`jrsnap`（JRSNAP 5.2-L03 NDU、CP932/CRLF）。
- `pipeline`: 段階の登録表、生成、公開、CLI。
- `gui`: 入力エディタ。「計算・印刷」は pipeline を子プロセス（`python -m webpier`）で実行し、付帯JSONで結果を確かめる。

### 段階の登録表と一括公開
段階の依存・計算・帳票・成果物・外部出力は `webpier/pipeline/stages.py` の `StageSpec` 1か所に定義し、段階ごとの分岐を他に書かない。生成は `webpier/pipeline/generate.py`。

1. 入力を一度だけバイト列で読み、厳密に解析する。そのSHA256を全ての結果JSONと付帯JSONに記録する。
2. 選択した段階と依存段階をすべて計算してから描画する（0610/0620は0500と0600、0710は0610、0720は0620も使う）。保存済みの結果JSONは読まない。
3. 成果物を出力先の横でステージングし、`publication.py` が退避・置換・復元を伴ってまとめて公開する。外部出力（`post/`）には付帯JSON（`*.provenance.json`）を付け、入力・同じ世代の全成果物・実装のSHAを記録する。

### 決定性と実装の同一性
- PDFは作成日時を含まず、同じ入力・書体・ライブラリから毎回同じバイトになる。テストはこれを前提にしている。例外は 0610・0620 に差し込む FEMPython の荷重図のページで、その中身は FEMPython の責務として決定性を求めない（ADR-0005）。WebPier が描く部分は決定的にし、テストは代役の runner で確かめる。FEMPython の runner は `dependency_hashes` に入れず、付帯JSONに `engineVersion` を記録する。
- `webpier/pipeline/runtime.py` の `dependency_hashes` は、`webpier` のソースに加えて、インストール済みの GridLayoutPdf・ReportLab・Pillow・書体ファイルのバイトもハッシュし、生成中に実装が変わっていないか照合する。GridLayoutPdf を編集して取り込み直していないと、ハッシュ照合が食い違いテストが失敗する。
- ハッシュするソースと受入記録の補助スクリプトは `.gitattributes` で LF に固定している（`*.py`、`scripts/*.cs`、jrsnap-input-open-save の `scripts/*.ps1`・`*.cs`）。`core.autocrlf` で CRLF になると実装の同一性や受入記録の SHA が変わる。

### 帳票の基準とテスト用データ
- 体裁の基準は `.claude/docs/Example橋脚/output`、計算内容の見本は `.claude/docs/Example橋脚2`。体裁の契約は `.claude/docs/reporting-style.md`、層ごとの書き方は `.claude/docs/plans/calc-layer-conventions.md` と `reporting-layer-conventions.md`。
- テストは層ごとに `tests/<層>/`。期待値は、Example2 原資料から独立に転記した値（`tests/fixtures/example2/`）と、実装を使わない手計算だけ。入力は `tests/fixtures/inputs/current.json` を基に変えたい項目だけ書き換える。
- 性質テスト（hypothesis、`tests/*/test_*_properties.py`）は式から言える恒等式・順序だけを確かめる。`tests/conftest.py` のプロファイルで `derandomize=True`（毎回同じ例）にしている。
- `tests/fixtures/reporting/appearance` は見本PDFから独立に測った体裁値（測定器は `scripts/reporting_appearance.py`）。新しい描画結果から作り直さない。
- 文字の縮小や伸縮で固定ページ数に収めない。式・表・図のまとまりを保ち、内容に応じて改ページする。

### 入力の扱い（schema 2）
- 空欄は `null`、`0` は数値。欠けている値を固定値や見本値で補わず、計算に要る値が空欄なら入力エラーにする。全項目が空欄の支承枠だけは空き支承枠。
- 知らないキーは入力エラー。選択肢（車両名・土質区分・杭種など）はプログラムが持ち、入力JSONには選んだ値だけを保存する。
- 派生値（表層厚、排除した土の単位体積重量、B・C支点の合計）は入力にしない。計算器が求めて印刷する。
- 入力値は入力時に印字桁へ丸める。エディタは入力した時点で丸め、手で書いたJSONに印字桁より細かい値があれば入力エラーにする。
- 杭・斜角・遠心の作用方向などは予約項目として形式と桁だけを検証する（決定19）。

### 計算の原則（docs/adr/ を正とする）
- 元Excelの誤りは再現しない。元式を残すのは README の互換一覧に明示したものだけで、いまは空（ADR-0001）。元Excelのセル番地や照合値は使わず、物理量で計算し、Example2 の転記と独立の手計算で検証する（ADR-0002）。
- 計算書に印刷する値は内部でも印字桁に丸め、後続の計算はその値を使う。合計は印刷された部分の和。丸めは四捨五入（0.5は絶対値の大きい側）だけ。印字桁は計算器が持ち、帳票は丸め直さない（ADR-0003）。
- 開発初期のため後方互換を作らない。入力形式や結果JSONを変えるときは、旧形式の読み替えや互換の経路を残さず書き換える。

## GridLayoutPdf の責務は GridLayoutPdf 側で直す

このrepoの作業中に、`C:\Users\sasai\Documents\GridLayoutPdf` の責務（帳票の組版・レイアウト・PDF描画など、橋脚の設計計算に依存しない汎用機能）の追加や修正が必要になったら、`C:\Users\sasai\Documents\GridLayoutPdf` 自体を修正する。

- WebPier 側で回避しない。モンキーパッチ、ライブラリのコードの複製・同梱、内部APIへの依存、WebPier 内だけの代替実装などで済ませることは禁止。
- GridLayoutPdf を修正するときは、そのrepoの `AGENTS.md` から辿れる規則（`.claude/rules/` など）に従い、そのrepoのテストも通す。
- 修正後は上記の `uv sync ... --reinstall-package gridlayoutpdf` で WebPier に取り込み直す（同じversion番号のままでは置き換わらないことがある）。
- 橋脚固有の内容（計算、帳票の項目や文言、WebPier 用の帳票構成）は WebPier 側に置き、GridLayoutPdf へ持ち込まない。

## FEMPython の責務は FEMPython 側で直す

荷重図の作図（`FrameWebforCS.Headless` の `load_diagram`、FramePrintPDF）など、`C:\Users\sasai\Documents\structural-mcp\FEMPython` の責務の追加や修正が必要になったら、FEMPython 自体を修正する（ADR-0005）。

- WebPier 側で回避しない。FEMPython が出力した PDF の中身を書き換えたり、作図を WebPier 内で代替したりしない。WebPier が行うのは、runner の呼び出し、返ったページの差し込みだけ。計算書にはページ番号を印刷しない。
- FEMPython を修正するときは、そのrepoの `AGENTS.md` に従い、そのrepoのテストも通す。修正後は Headless を Release でビルドし直す。
- Headless のやり取り（`run` の引数、envelope、`protocolVersion`）を変えたら、WebPier のテストの代役 runner も合わせて更新する。
