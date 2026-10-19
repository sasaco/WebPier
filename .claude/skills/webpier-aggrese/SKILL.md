---
name: webpier-aggrese
description: WebPier が Aggre-SE（Batch、Docu-SE）のプロジェクトXML post/線路方向.xml・post/線路直角方向.xml を書く実装（決定49、webpier/export/aggrese/writer.py）を直すとき、0711・0721 の計算書（Aggre-SE の report.pdf そのもの、決定56、webpier/pipeline/aggrese.py）・ピックアップ・総括表・直接基礎のステップ表 post/*_Aggre-SE.pik・.xlsx・_直接基礎.csv（決定57・58・60）の取り込みと検査、見本 10.5・10.6 との対応、受入（accept_aggrese_project.py・accept_aggrese_report.py）の取り直し、テストの期待値 tests/fixtures/example2/aggrese/、post の出力を作る・最新か確かめるときに使う。Aggre-SE そのもの（XML の項目の意味、DB1 の横のファイル、runner の引数と成果物、保存し直し）はスキル structural-aggrese を使う。
---

# WebPier の Aggre-SE の書出しと 0711・0721

**Aggre-SE 自体（XML の文字コードと項目の意味、DB1 の横に要るファイル、runner の引数と成果物、report.pdf・pickup.pik・summary.xlsx の構成、`--foundation-steps` の列と step の番号、保存し直しの道具）はスキル `structural-aggrese` を参照**。ここには WebPier の実装・決定・受入・見本との対応だけを書く。

WebPier は 0711・0721 で Aggre-SE のプロジェクトXMLを `post/線路方向.xml`・`post/線路直角方向.xml` に書き（決定49、`webpier/export/aggrese/`、CONTEXT.md「耐震照査の入力」）、同じ生成で Aggre-SE の runner に照査させた `report.pdf` をバイト列のまま 0711・0721 の計算書にする（決定56、ADR-0009、`webpier/pipeline/aggrese.py`、CONTEXT.md「耐震性能照査」）。Batch のソースは structural-mcp の repo のルートから `Batch/`。**Batch のファイルは変更しない**。試すときは XML と DB1 のフォルダーの複製を使う。

## WebPier の書出しを直すとき

- 入力は `耐震設計条件`（地域別・地盤区分）だけ。ほかの条件は見本 `P1_線路.xml` の通りの WebPier の定め（`webpier/export/aggrese/writer.py` の定数、決定49）。利用者に聞かずに入力を増やさない。
- WebPier の書出しは、Aggre-SE 自身に保存し直させても**バイト列が変わらない**ことを受入にしている。保存し直しは `scripts/aggrese_project_roundtrip.cs`（WebPier の repo のもの。受入の `scripts/accept_aggrese_project.py` の `HELPER` が使い、`tests/fixtures/acceptance/aggrese/record.json` が SHA を記録しているので動かさない。同じ道具の複製が `structural-aggrese` の `scripts/` にあり、違いは1行目のコメントの決定番号だけ）。コンパイルと実行の手順は `structural-aggrese`。
- テストの期待値（`tests/fixtures/example2/aggrese/`）は、見本を手で直して（配列50件、DB1 のパス）これで保存し直したもの。手順は同じフォルダーの `notes.md`。
- Batch の版が変わったら：見本を保存し直して書式の差を見る → `writer.py` の `BATCH_VERSION` と並びを合わせる → 期待値を作り直す（`notes.md` の手順）→ `scripts/accept_aggrese_project.py --overwrite` で受入を取り直す（本物の JRSNAP で 0711・0721 を生成するので数分かかり、画面が出る）。
- 受入記録は `tests/fixtures/acceptance/aggrese/record.json`。入力（`current.json`）や生成する XML が変わると `tests/acceptance` が失敗する。
- 直接基礎の照査値の既知の差（決定49）：WebPier の NDU は直接基礎の照査のデータを持たないので `_Output_Chokukiso.csv` ができず、Aggre-SE は DB1 から求める。0711 の結果で試すと、作用は見本と一致し、抵抗側は違った。ただし、JRSNAP の基礎照査との差と NDU の `FootInfo` の Df・γ2 の差が混ざっており、原因はまだ切り分けていない。

## 0711・0721 の計算書・ピックアップ・総括表（決定56〜58）

- WebPier の生成が `run --input <ステージングした XML> --output-dir <空の一時フォルダー> --snap-map <map> --summary-xlsx true --report-pdf true --check-tables false --pik true --pile-anchor-bar-pdf false --foundation-steps true` を呼ぶ（返る成果物は result.json・report.pdf・pickup.pik・summary.xlsx と、直接基礎なら foundation-steps.csv）（`.env` の `STRUCTURAL_MCP_AGGRESE_RUNNER`）。1方向 4 秒ほど（2026-10-19、実アプリ）。WebPier は呼ぶ前後で XML とフォルダーの SHA を比べ、変わっていれば生成を止める。成果物の組（kind と relativePath）が求めたものとちょうど一致しないと止める。
- `--foundation-steps` は Batch 9c70f54 以降の runner にしかない（structural-mcp が固定している Batch にはまだない。`structural-aggrese` の `references/foundation-steps.md`）。
- `report.pdf` の見出しは DB1 の題名から来るので、見本 10.5・10.6 の作成者が書き込んだ見出しを WebPier は再現しない。線路方向（1 Case）は11ページ、線路直角方向（2 Case）は18ページ。
- ピックアップ（決定57）：`pickup.pik` を `post/線路方向_Aggre-SE.pik`・`post/線路直角方向_Aggre-SE.pik` にそのまま書く。線路方向は109行・11 KB（部材1〜6）、線路直角方向は127行・13 KB（部材1〜7）。`post/線路方向.pik` は 0611 の FEMPython の PIK なので、名前を分けている。
- 総括表（決定58）：`summary.xlsx` を `post/線路方向_Aggre-SE.xlsx` に書き、zip であることだけを確かめる（毎回バイトが変わるため）。受入はシート名の並びを記録する。
- 見本との対応（2026-10-19、見本を画像にして確認）：`10_線路(耐震).pdf` の 13〜21 ページ（10.5）は Case ごとの7ページと設計総括表・直接基礎の照査（A3 を A4 に回転して縮小）、22・23 ページは JRSNAP の基礎照査の出力（地盤反力分布図と「直接基礎底面回転ばねの算定値」のリスト。Aggre-SE の出力ではない）、24〜26 ページ（10.6）は応答値一覧表・設計総括表・直接基礎の照査。`11_直角(耐震).pdf` は 14〜27 ページで、見本は Case1 だけ。見本の Aggre-SE の版は古く、直接基礎の照査の見出しが「1.復旧性（性能レベル1）…3.安全性」（いまの Batch は「1.安定レベル1…3.安定レベル3」）。見本にない安全率一覧表は、いまの Batch が出す。
- 見本の PDF は 13 ページ以降がほぼ画像で、`pdftotext` では読めない。`uv run --project . --locked --group dev python -X utf8` で `pymupdf` を使い、ページを PNG にして見る（文字の取り出しは見出しだけ）。
- `scripts/accept_aggrese_project.py`（決定49の受入）も 0711・0721 を生成するので、いまは Aggre-SE の runner が `.env` に要る。スクリプトを書き換えると記録の helpers の SHA が変わり、受入のやり直しが要る。
- 受入は `scripts/accept_aggrese_report.py --overwrite`（本物の JRSNAP で生成するので数分かかり、画面が出る）。記録は `tests/fixtures/acceptance/aggrese_report/record.json`。応答値は2ページ目の文字（`Ｋheq = …`・`δeq  = … mm`・`μ = …`・`δr = μ・δeq = … = … mm`・`Khr = …`）から読む。線路方向は見本 10-14 と一致する。

## 直接基礎のステップ表（決定60）

- 列・step の番号・SNAPDBLib での確かめ方は `structural-aggrese` の `references/foundation-steps.md`。
- WebPier の 0711・0721 は常に `--foundation-steps true` を付けて `post/線路方向_Aggre-SE_直接基礎.csv`・`post/線路直角方向_Aggre-SE_直接基礎.csv`（kind `steps`）に書き、付帯JSONに列の並びを記録する（`webpier/pipeline/aggrese.py` の `FOUNDATION_STEPS_COLUMNS`）。
- 見本との対応（本物の DB1 で確認、2026-10-19）：見本 10-23 の「増分ステップ＝31、荷重増分ステップ数 360」は `StepCtrl(30)`（`LoStepNo=360`、H 5747.86・M 52784.78）＝ CSV の step 31 と一致。JRSNAP 自身の Rvd到達ステップ（`IChokukiso.RvdStep`＝CSV で `V ≧ Rvd` になる最初の `step`）は線路方向 32、直角 Case1・Case2 とも 33。見本の 31 と違うのは Df 4.70／γe2 の既知の差。
- Batch 側のテスト（`Batch/tests/Aggre-SE.Test/HeadlessRunnerTests.cs`）は、直接基礎の XML の既定に WebPier の `post/線路方向.xml` を使う（なければ skip）。

## post の出力を作る・最新か確かめる

- 作る：`uv run --project "." --locked python -m webpier --stage 0711 --overwrite`（0721 も同じ。両方なら `--stage all --nonlinear-analysis --overwrite`）。依存段階は内部で計算するだけで、0711 を選んだ生成が書くのは `output/0711_線路方向非線形解析.pdf`・`.json` と `post/` の `線路方向_JRSNAP/`・`線路方向.xml`・`線路方向_Aggre-SE.pik`・`線路方向_Aggre-SE.xlsx`・`線路方向_Aggre-SE_直接基礎.csv` と各付帯JSON。1方向数分かかり、JRSNAP の画面が出る。`.env` に JRSNAP と Aggre-SE の runner が要る。
- 最新か確かめる（作り直す前に）：付帯JSONの `input.sha256` を `pre/input.json` の SHA256 と、`implementation_sha256` を `canonical_sha256({str(p): d for p, d in webpier.pipeline.runtime.dependency_hashes().items()})` と比べる。両方一致すれば、いまの入力と実装で作ったもの（2026-10-19、「出力して」と言われて確かめた手順）。総括表と計算書はバイトが毎回変わるので、ファイルの SHA256 どうしを比べて新旧を判断しない。
- 同じ作業ツリーで別のセッションが `CONTEXT.md` などを編集していることがある。コミットは `git commit --only <自分のファイル>` で、他人の差分を含めない（`git diff -U0` で自分の差分か確かめる）。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- Aggre-SE そのものの性質（項目の意味、画面との対応、runner の挙動、Batch の版による書式の違い）：structural-mcp の `skills/structural-aggrese/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0711・0721 の説明（計算書は Aggre-SE の帳票そのもの、判定の読み方、既知の差）：structural-mcp のスキル `structural-webpier` の checks.md（ここには書かない）。
- 案件の判断・見本の読み替え：その案件の repo。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
