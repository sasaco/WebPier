# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

鉄道橋脚の設計計算（0500直接基礎・0600上部工反力・0610線路方向荷重・0620直角方向荷重・0710/0720地震時荷重）を `pre/input.json` から行い、A4白黒の計算書PDFと結果JSON、FEMPython/FrameWeb入力、JRSNAP用NDUを生成する。構造解析・部材照査・最適化は対象外。仕様の詳細は `README.md`、用語は `CONTEXT.md` を正とする。

## コマンド

すべてリポジトリのルートで、`uv` の `--locked` 環境を使う。

```powershell
# 計算・PDF生成（既定は --stage all。既存成果物の更新には --overwrite）
uv run --project "." --locked python "./run_design.py" --overwrite
uv run --project "." --locked python "./run_design.py" --stage 0610 --overwrite   # 0500/0600/0610/0620/0710/0720/all
uv run --project "." --locked python "./run_design.py" --stage all --jrsnap --overwrite  # NDUも出力

# 入力編集GUI（Tkinter/tksheet。VS CodeのF5でも起動）
uv run --project "." --locked python "./edit_input.py"

# テスト（全件。.claude/check.ps1 も同じ全件ゲート）
uv run --project "." --locked --group dev python -X utf8 -m pytest tests -q
# 単一ファイル／単一テスト
uv run --project "." --locked --group dev python -X utf8 -m pytest tests/test_transverse_calculator.py -q
uv run --project "." --locked --group dev python -X utf8 -m pytest "tests/test_transverse_calculator.py::test_name" -q

# GridLayoutPdf のソースを変更した後の取り込み直し
uv sync --project "." --locked --reinstall-package gridlayoutpdf
```

Windows専用。帳票は `%WINDIR%/Fonts` の MS明朝・MSゴシック・Calibri・Times Italic が必須で、書体がなければ生成を停止する。

## アーキテクチャ

### 計算 → 描画 → 一括公開
`run_design.py` → `src/cli.py`。流れは `prepare_generation` に集約されている。

1. 入力を一度だけバイト列で読み、そのSHA256を全段階の `provenance` に記録する。
2. `_calculate_stages` で依存段階も内部計算する（0610/0620は0500と0600、0710は0610、0720は0600と0620を使用）。保存済みの結果JSONは読まない。
3. 選択した全段階の計算が成功してから描画する。各段階は `src/<段階>_report.py` の公開エントリ → `src/reporting/stages/*.py` で GridLayoutPdf の文書を組む。
4. 成果物を一時領域にステージングし、`src/artifact_publication.py` が退避・置換・復元を伴ってまとめて公開する。FrameWeb入力（`frameweb_*`）とNDU（`jrsnap_*`）も同じ世代として公開し、付帯JSON（provenance）に入力・成果物・実装のSHAを記録する。

### モジュールの分け方
- 入力の解析・検証: `inputs.py`（0500）、`reaction_inputs.py`（0600以降）、`*_design_conditions.py`
- 計算: `calculator.py`（0500）、`reaction_calculator.py`、`longitudinal_*`、`transverse_*`、`seismic_*`。計算モジュールは描画に依存しない。
- 帳票: `src/reporting/`（書体・式・表・図・スタイル）と `src/reporting/stages/`（段階別の組版）。工学計算はここに置かない。
- 外部ソフト向け出力: `frameweb_*`（FEMPython/FrameWebforCS）、`jrsnap_*`（JRSNAP 5.2-L03 NDU、CP932/CRLF）
- GUI: `editor_*`、`rebar_*`、`column_rebar*`、`pdf_preview*`。GUIの「計算・印刷」はCLIと同じ生成・公開処理を使う。

### 決定性と実装の同一性
- PDFは作成日時を含まず、同じ入力・書体・ライブラリから毎回同じバイトになる。テストはこれを前提にしている。
- `src/reporting/runtime.py` の `dependency_hashes` は、自プロジェクトのソースに加えて、インストール済みの GridLayoutPdf・ReportLab・Pillow・書体ファイルのバイトもハッシュし、生成中に実装が変わっていないか照合する。GridLayoutPdf を編集して取り込み直していないと、ハッシュ照合が食い違いテストが失敗する。

### 帳票の基準とテスト用データ
- 体裁の基準は `.claude/docs/Example橋脚/output`、計算内容の見本は `.claude/docs/Example橋脚2`。体裁の契約は `.claude/docs/reporting-style.md`、移行の対応表は `.claude/docs/reporting-migration.md` を参照。
- `tests/fixtures/reporting/` に、見本から測定した体裁値（appearance）、移行前の基準（baseline）、段階別の意味内容（semantic）を置く。これらは見本や旧成果物から作った独立の期待値なので、新しい描画結果から作り直さない（`scripts/reporting_*.py` は測定・監査用で、実行時のフォールバックではない）。
- `tests/fixtures/*_excel_oracle.json` などは元Excelから取った照合値。
- 文字の縮小や伸縮で固定ページ数に収めない。式・表・図のまとまりを保ち、内容に応じて改ページする。

### 入力の扱い
空欄は `null`、`0` は数値、反力表の `-` は適用外の文字列として区別し、欠けている値を固定値や見本値で補わない。不正な値は補完して隠さず、入力エラーにする。

### 計算の原則（docs/adr/ を正とする）
- 元Excelの誤りは再現しない。元式を残すのは README の互換一覧に明示したものだけ（ADR-0001）。元Excelのセル番地や照合値は使わず、物理量で計算し、Example2 の転記と独立の手計算で検証する（ADR-0002）。
- 計算書に印刷する値は内部でも印字桁に丸め、後続の計算はその値を使う。印字桁は計算器が持ち、帳票は丸め直さない（ADR-0003）。
- 開発初期のため後方互換を作らない。入力形式や結果JSONを変えるときは、旧形式の読み替えや互換の経路を残さず書き換える。

## GridLayoutPdf の責務は GridLayoutPdf 側で直す

このrepoの作業中に、`C:\Users\sasai\Documents\GridLayoutPdf` の責務（帳票の組版・レイアウト・PDF描画など、橋脚の設計計算に依存しない汎用機能）の追加や修正が必要になったら、`C:\Users\sasai\Documents\GridLayoutPdf` 自体を修正する。

- WebPier 側で回避しない。モンキーパッチ、ライブラリのコードの複製・同梱、内部APIへの依存、WebPier 内だけの代替実装などで済ませることは禁止。
- GridLayoutPdf を修正するときは、そのrepoの `AGENTS.md` から辿れる規則（`.claude/rules/` など）に従い、そのrepoのテストも通す。
- 修正後は上記の `uv sync ... --reinstall-package gridlayoutpdf` で WebPier に取り込み直す（同じversion番号のままでは置き換わらないことがある）。
- 橋脚固有の内容（計算、帳票の項目や文言、WebPier 用の帳票構成）は WebPier 側に置き、GridLayoutPdf へ持ち込まない。
