# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

鉄道橋脚の設計計算（0500直接基礎・0600上部工反力・0610線路方向荷重・0620直角方向荷重・0710/0720地震時荷重）を `pre/input.json`（schema 2）から行い、A4白黒の計算書PDFと結果JSON、FEMPython/FrameWeb入力、JRSNAP用NDU、JRSNAP の結果を読む Aggre-SE のプロジェクトXML（決定49）とその耐震性能照査の帳票そのものの計算書（0711・0721、決定56）、柱の断面照査の計算書と WDJ（0611・0621、決定48）、基礎の照査の計算書（0612・0622、決定54）、片持ち梁の応答値と断面照査の計算書と WDJ（0900・0910、決定59）、フーチングの応答値と断面照査の計算書と WDJ（0800・0810・0820、決定60）を生成する。骨組解析は FEMPython、柱の断面照査は Capacita に任せ、基礎の安定計算は WebPier で行う（ADR-0006）。最適化は対象外。仕様の詳細は `README.md`、用語は `CONTEXT.md`、原則は `docs/adr/`、決定事項は `.claude/docs/plans/refactoring-decisions.md` を正とする。

## コマンド

すべてリポジトリのルートで、`uv` の `--locked` 環境を使う。

```powershell
# 計算・PDF生成（既存成果物の更新には --overwrite）。作る計算書は入力の出力項目 outputs（12の true/false）だけで決まり、段階やスイッチの引数はない（決定72、ADR-0011。webpier/inputs/outputs.py・stages.py の OUTPUT_STAGES）
# 項目は、使う項目がすべて true のときだけ true にできる（違反と全 false は入力エラー）。選ばなかった項目の成果物は前回のまま残る
uv run --project "." --locked python -m webpier --overwrite
# ground_model=0500、reactions=0600、longitudinal=0610、transverse=0620：0610/0620 は FrameWeb入力も常に post/ に出力する
# longitudinal_seismic=0710、transverse_seismic=0720：JRSNAP入力（NDU）も常に post/ に出力する
# longitudinal_frame_analysis=0611・0612、transverse_frame_analysis=0621・0622（骨組解析。決定46・54。同じ FrameWeb 入力の解析は1回）：FEMPython のピックアップ（*.pik・*_ピックアップ変位量.csv・*_ピックアップ反力.csv）を post/ に出力
# 0611・0621 はそのピックアップで柱の断面照査も Capacita で行い、計算書（8.5〜8.9・9.5〜9.9）と post/線路方向.wdj・post/線路直角方向.wdj を出力する（決定48）
# 0612・0622 は同じ解析の支点反力で基礎の照査を WebPier で行い、計算書（8.10・9.10）を出力する（決定54）
# longitudinal_nonlinear_analysis=0711、transverse_nonlinear_analysis=0721（静的非線形解析。決定47）：JRSNAP の .NDT と解析結果をフォルダー post/線路方向_JRSNAP/・post/線路直角方向_JRSNAP/ に丸ごと置き換えて出力し、その横に Aggre-SE のプロジェクト post/線路方向.xml・post/線路直角方向.xml を書く（決定49。入力の 耐震設計条件 が必須）。その XML で Aggre-SE の runner が照査した report.pdf をバイト列のまま 0711・0721 の計算書にし（決定56、ADR-0009。見出しや節の番号は足さない）、同じ呼び出しのピックアップ・総括表・直接基礎のステップ表を post/線路方向_Aggre-SE.pik・.xlsx・_直接基礎.csv（線路直角方向も同じ）に出力する（決定57・58・60）
# cantilever=0900・0910（両方向の静的非線形解析が要る。決定59）：0900 は 0600 の結果と 0711・0721 の Aggre-SE の総括表（最大応答震度）から片持ち梁の応答値と 31 ケースの組合せを求め、0910 はその断面力を書いた WDJ を Capacita の run-rc（--pickup なし）で照査して計算書（13.3〜13.6）と post/片持ち梁.wdj を出力する
# footing=0800・0810・0820（両方向の骨組解析と静的非線形解析が要る。決定60）：0800 は 0612・0622 の反力 CSV と 0711・0721 の直接基礎のステップ表からフーチングの応答値（12.1、両方向）を求め、0810・0820 はその断面力を書いた WDJ を Capacita の run-rc（--pickup なし）で照査して計算書（12.2〜12.4／12.5〜12.7）と post/線路方向フーチング.wdj・post/線路直角方向フーチング.wdj を出力する
# run_design.py は python -m webpier と同じ

# headless runner（structural-mcp が起動する。決定61、webpier/pipeline/headless.py）：stdout は protocol v1 の envelope 1つ。runner は環境変数だけ（.env を読まない）
.venv\Scripts\python.exe -X utf8 .\run_headless.py run --input pre\input.json --output-dir <空のフォルダー>   # validate / contract / schema も。summary.outputs に選んだ項目
# 荷重モデルのアドイン（決定70、ADR-0010）：CLI・headless の全コマンドに --addin <フォルダー>。付けなければ列車荷重（成果物は変わらない）。失敗は ADDIN_ERROR
.venv\Scripts\python.exe -X utf8 .\run_headless.py run --input pre\input.json --output-dir <空のフォルダー> --addin tests\fixtures\addin\minimal

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

# 手元の GridLayoutPdf の作業ツリーを試す（GridLayoutPdf は pyproject.toml の URL 参照の wheel で入る。下の「GridLayoutPdf の責務は GridLayoutPdf 側で直す」）
uv pip install --python ".venv" --no-deps --reinstall "C:\Users\sasai\Documents\GridLayoutPdf"
uv run --project "." --no-sync --group dev python -X utf8 -m pytest tests -q
```

Windows専用。帳票は `%WINDIR%/Fonts` の MS明朝・MSゴシック・MS Pゴシック・Calibri（名前で引く。`webpier/reporting/fonts.py`）が必須で、書体がなければ生成を停止する。0610・0620 の荷重図は FEMPython の Headless runner で描くので（ADR-0005、`webpier/pipeline/fempython.py`）、リポジトリのルートの `.env`（追跡しない）に `STRUCTURAL_MCP_FEMPYTHON_RUNNER='<FEMPython>\FrameWebforCS\Headless\bin\Release\net10.0-windows\FrameWebforCS.Headless.exe'` を書く（プロセスの環境変数が優先）。未設定なら 0610・0611・0620・0621 を含む生成は停止する（0611・0621 の骨組解析も同じ runner、ADR-0006）。0711・0721 の静的非線形解析は structural-mcp の JRSNAPHeadless の runner で行い（ADR-0007）、`.env` に `STRUCTURAL_MCP_JRSNAP_RUNNER='<JRSNAPHeadless>\bin\Release\JRSNAP.Headless.exe'` を書く。0710・0720 の計算書に差し込むデータ確認図と荷重図（決定50・51、`figures`）も同じ runner が描くので、未設定なら 0710・0711・0720・0721（と 0900・0910）を含む生成は停止する。JRSNAP のインストール先は runner の横の `jrsnap-headless.json` が持ち、WebPier は JRSNAP を直接起動しない。0611・0621 の柱の断面照査は Capacita の Headless runner（`run-rc --pickup`、ADR-0008、`webpier/pipeline/capacita.py`）で行い、`.env` に `STRUCTURAL_MCP_WEBDAN_RUNNER='<Capacita>\WebDanforCS\Headless\bin\Release\net8.0\WebDanforCS.Headless.exe'` を書く（未設定なら 0611・0621・0810・0820・0910 を含む生成は停止する。Capacita を直したら `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release` を structural-mcp のルートで）。0711・0721 の耐震性能照査は Aggre-SE の Headless runner（`run --snap-map`、ADR-0009、`webpier/pipeline/aggrese.py`）で行い、`.env` に `STRUCTURAL_MCP_AGGRESE_RUNNER='<Batch>\Aggre-SE\Headless\bin\Release\AggreSE.Headless.exe'` を書く（未設定なら 0711・0721・0800・0810・0820・0900・0910 を含む生成は停止する。Batch は Visual Studio の MSBuild でビルドする）。テストは `tests/conftest.py` が4つの代役の runner に置き換える。テストは `webpier` のソースもハッシュするので、テスト実行中にソースを編集しない（生成中の実装変更として失敗する）。

## アーキテクチャ

### 層別パッケージ（ADR-0004）
`webpier/` の下に層を分け、依存は下向きだけにする。`tests/test_layer_boundaries.py` が強制する。

`core ← inputs ← loadmodel ← calc ← reporting / export ← pipeline ← gui`

- `core`: 印字桁つきの値 `Printed`、厳密なJSON読込み、エラー、ハッシュ。
- `inputs`: schema 2 の解析と検証。`fields.py` の項目表（桁・単位・符号・選択肢・予約項目）をparserとエディタが共用する。選択肢は `choices.py`。`parse_input(load_model=True)` は荷重モデルの項目を読まない（決定70）。
- `loadmodel`: 荷重モデルの約束（決定70、ADR-0010）。アドインが import してよいのはここだけで、core にだけ依存する。結果はアプリが `validate` で検査する（違反は `アドイン:` の入力エラー）。
- `calc`: 段階の計算。結果は `Printed` を持つ frozen dataclass で、描画に依存しない。
- `reporting`: GridLayoutPdf で組む帳票（`reporting/stages/`）。工学計算をここに置かない。
- `export`: `frameweb`（FEMPython/FrameWebforCS）、`jrsnap`（JRSNAP 5.2-L03 NDU、CP932/CRLF）、`aggrese`（Aggre-SE のプロジェクトXML。Aggre-SE が保存する書式どおりで、宣言は utf-16・中身は Shift-JIS）。
- `pipeline`: 段階の登録表、生成、公開、CLI。アドインの読み込み（`addin.py`、importlib はここだけ）と、荷重モデルの段階の表 `stages_for`（0600・0610・0620・0710・0711・0720・0721・0900 を汎用のものに替え、残りは共有）。
- `gui`: 入力エディタ（01 下部構造〜05 鉄筋、06 JRSNAPの設定、07 計算・印刷）。「計算・印刷」は出力項目のチェックを入力の `outputs` に書き、pipeline を子プロセス（`python -m webpier`）で実行し、付帯JSONで結果を確かめる。

### 段階の登録表と一括公開
段階の依存・計算・帳票・成果物・外部出力は `webpier/pipeline/stages.py` の `StageSpec` 1か所に定義し、段階ごとの分岐を他に書かない。他のプログラムのページ（FEMPython の荷重図、Capacita の節、JRSNAP のデータ確認図と荷重図）は `webpier/reporting/stages/insertion.py` の1つの仕組みで差し込み、`render` は全段階で `(results, pier, path, pages)` を受け取る（`pages` はページの名前からページへの対応で、各エンジンの pipeline のモジュールが作る）。生成は `webpier/pipeline/generate.py`。

1. 入力を一度だけバイト列で読み、厳密に解析する。そのSHA256を全ての結果JSONと付帯JSONに記録する。
2. 選択した段階と依存段階をすべて計算してから描画する（0610/0620は0500と0600、0710は0610、0720は0620も使う）。保存済みの結果JSONは読まない。
3. 成果物（計算書、WebPier が組む頁の方眼Excel `export/<stem>.xlsx`、結果JSON、外部出力）を出力先の横でステージングし、`publication.py` が退避・置換・復元を伴ってまとめて公開する。外部出力（`post/`）には付帯JSON（`*.provenance.json`）を付け、入力・同じ世代の全成果物・実装のSHAを記録する。0711・0721 の JRSNAP の結果はそれぞれフォルダー1つの成果物で、丸ごと置き換え、SHA は中の全ファイルから求める（`core.integrity.content_sha256`）。

### 決定性と実装の同一性
- PDFは作成日時を含まず、同じ入力・書体・ライブラリから毎回同じバイトになる。テストはこれを前提にしている。例外は 0610・0620 に差し込む FEMPython の荷重図のページと、0710・0720 に差し込む JRSNAP のデータ確認図と荷重図のページで、その中身はそれぞれの責務として決定性を求めない（ADR-0005、決定50・51）。WebPier が描く部分は決定的にし、テストは代役の runner で確かめる。FEMPython の runner は `dependency_hashes` に入れず、付帯JSONに `engineVersion` を記録する。JRSNAP の runner と結果も同じ（決定47）。
- `webpier/pipeline/runtime.py` の `dependency_hashes` は、`webpier` のソースに加えて、インストール済みの GridLayoutPdf・ReportLab・Pillow・書体ファイルのバイトもハッシュし、生成中に実装が変わっていないか照合する。GridLayoutPdf を編集して取り込み直していないと、ハッシュ照合が食い違いテストが失敗する。
- ハッシュするソースと受入記録の補助スクリプトは `.gitattributes` で LF に固定している（`*.py`、`scripts/*.cs`、jrsnap-input-open-save の `scripts/*.ps1`・`*.cs`）。`core.autocrlf` で CRLF になると実装の同一性や受入記録の SHA が変わる。

### 帳票の基準とテスト用データ
- 帳票は GridLayoutPdf 0.2.0 の共通グリッドに組み、位置はマスの数で持つ（2026-10-21、`.claude/docs/plans/glp-0.2.0-grid.md`）。構成・文言・式の書き方の基準は `.claude/docs/Example橋脚/output`、計算内容の見本は `.claude/docs/Example橋脚2`。体裁の契約は `.claude/docs/reporting-style.md`、層ごとの書き方は `.claude/docs/plans/calc-layer-conventions.md` と `reporting-layer-conventions.md`。各段階の `grid_documents` が方眼Excel の頁で、`render` と同じ文書を作る。
- テストは層ごとに `tests/<層>/`。期待値は、Example2 原資料から独立に転記した値（`tests/fixtures/example2/`）と、実装を使わない手計算だけ。入力は `tests/fixtures/inputs/current.json` を基に変えたい項目だけ書き換える。テストの補助モジュール（`*_support.py`）は `from <名前> import` で読むので、層をまたいでも同じ名前にしない（先に読んだほうが使われる）。
- 性質テスト（hypothesis、`tests/*/test_*_properties.py`）は式から言える恒等式・順序だけを確かめる。`tests/conftest.py` のプロファイルで `derandomize=True`（毎回同じ例）にしている。
- `tests/fixtures/reporting/appearance` は見本PDFから独立に測った体裁値（測定器は `scripts/reporting_appearance.py`）。共通グリッドへの移行で位置の基準ではなくなったが、見本の記録として残す。新しい描画結果から作り直さない。
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
- GridLayoutPdf は `pyproject.toml` の `[tool.uv.sources]` の URL 参照で、GitHub Release（`sasaco/grid_layout_pdf` の `v0.1.0` など）に載せた wheel から入る（uv.lock に wheel の SHA-256）。git の参照にしないのは、git のない PC（structural-mcp の MSI の利用先）で `uv sync --locked` が通らないため（uv は git の依存の取得に git の実行ファイルを使う）。structural-mcp の submodule として clone した PC でも同じ版になるように、手元のパスの参照に戻さない。
- 修正中に WebPier で試すときは、上記の `uv pip install ... --reinstall` で手元の作業ツリーを venv に入れ、`uv run --project "." --no-sync ...` で実行する。`--locked` を付けた実行（品質ゲートを含む）は venv を lock の版に戻す。
- 取り込むときは、GridLayoutPdf で commit して push し、その commit にタグ（版の番号）を付けた Release を作って wheel を載せる。wheel は、その commit を `git -c core.autocrlf=false clone` で取り出し、`SOURCE_DATE_EPOCH=315532800` を付けた `uv build --wheel` で作る（付けると同じ commit から同じバイトになる）。`url` をその wheel に変えて `uv lock --project "."` と `uv sync --project "." --locked` を行い、品質ゲートを通してから `pyproject.toml` と `uv.lock` を一緒に commit する。Release の wheel は載せた後に差し替えない（uv.lock の SHA-256 と合わなくなる）。
- wheel の中の GridLayoutPdf のファイルの改行は commit のまま（LF）なので、`dependency_hashes`（`implementation_sha256`）の値は PC の git の設定によらない。
- 橋脚固有の内容（計算、帳票の項目や文言、WebPier 用の帳票構成）は WebPier 側に置き、GridLayoutPdf へ持ち込まない。

## FEMPython の責務は FEMPython 側で直す

荷重図の作図（`FrameWebforCS.Headless` の `load_diagram`、FramePrintPDF）など、`C:\Users\sasai\Documents\structural-mcp\FEMPython` の責務の追加や修正が必要になったら、FEMPython 自体を修正する（ADR-0005）。

- WebPier 側で回避しない。FEMPython が出力した PDF の中身を書き換えたり、作図を WebPier 内で代替したりしない。WebPier が行うのは、runner の呼び出し、返ったページの差し込みだけ。計算書にはページ番号を印刷しない。
- FEMPython を修正するときは、そのrepoの `AGENTS.md` に従い、そのrepoのテストも通す。修正後は Headless を Release でビルドし直す。
- Headless のやり取り（`run` の引数、envelope、`protocolVersion`）を変えたら、WebPier のテストの代役 runner も合わせて更新する。
