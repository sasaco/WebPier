---
name: webpier-aggrese
description: WebPier が Aggre-SE（Batch、Docu-SE）のプロジェクトXML post/線路方向.xml・post/線路直角方向.xml を書く実装（決定49、webpier/export/aggrese/writer.py）を直すとき、0711・0721 の計算書（Aggre-SE の report.pdf そのもの、決定56、webpier/pipeline/aggrese.py）・ピックアップ・総括表・直接基礎のステップ表 post/*_Aggre-SE.pik・.xlsx・_直接基礎.csv（決定57・58・60）の取り込みと検査、見本 10.5・10.6 との対応、受入（accept_aggrese_project.py・accept_aggrese_report.py）の取り直し、テストの期待値 tests/fixtures/example2/aggrese/、post の出力を作る・最新か確かめるときに使う。Aggre-SE そのもの（XML の項目の意味、DB1 の横のファイル、runner の引数と成果物、保存し直し）はスキル structural-aggrese を使う。
---

# WebPier の Aggre-SE の書出しと 0711・0721

**Aggre-SE 自体（XML の文字コードと項目の意味、DB1 の横に要るファイル、runner の引数と成果物、report.pdf・pickup.pik・summary.xlsx の構成、`--foundation-steps` の列と step の番号、保存し直しの道具）はスキル `structural-aggrese` を参照**。ここには WebPier の実装・決定・受入・見本との対応だけを書く。

WebPier は 0711・0721 で Aggre-SE のプロジェクトXMLを `post/線路方向.xml`・`post/線路直角方向.xml` に書き（決定49、`webpier/export/aggrese/`、CONTEXT.md「耐震照査の入力」）、同じ生成で Aggre-SE の runner に照査させた `report.pdf` をバイト列のまま 0711・0721 の計算書にする（決定56、ADR-0009、`webpier/pipeline/aggrese.py`、CONTEXT.md「耐震性能照査」）。Batch のソースは structural-mcp の repo のルートから `Batch/`。Batch のファイルは、WebPier の都合で変える必要があるとき（決定94 の runner の `--sdr`）だけ変え、Batch の規則（MSBuild でビルド、`tests/Aggre-SE.Test` のテスト）に従って Batch の repo にコミットする。試すときは XML と DB1 のフォルダーの複製を使う。

## WebPier の書出しを直すとき

- 入力は `耐震設計条件`（地域別・地盤区分）だけ。ほかの条件は見本 `P1_線路.xml` の通りの WebPier の定め（`webpier/export/aggrese/writer.py` の定数、決定49）。ただし損傷レベルの制限値の柱の復旧性は、見本の 2 でなく 3（決定115、`DAMAGE_RECOVERY`）。利用者に聞かずに入力を増やさない。
- 照査項目 ①〜⑨（`dgCaseList_1`〜`9`）は Case ごとに、その組合せの照査パターン（ρm, αf）から `project.CHECKS` で引く（決定76。載荷の向きによらない）：①②全部、③ (1.0, 2.0) 以外、④ ρm 1.2、⑤なし、⑥ (1.0, 1.0)、⑦⑧⑨ αf 1.0。Case は 0711 が4つ、0721 が8つ（Case5〜8 は逆向）。owner が手で直して Aggre-SE で保存した `post/線路直角方向.xml`（2026-10-22）が見本。
- WebPier の書出しは、Aggre-SE 自身に保存し直させても**バイト列が変わらない**ことを受入にしている。保存し直しは `scripts/aggrese_project_roundtrip.cs`（WebPier の repo のもの。受入の `scripts/accept_aggrese_project.py` の `HELPER` が使い、`tests/fixtures/acceptance/aggrese/record.json` が SHA を記録しているので動かさない。同じ道具の複製が `structural-aggrese` の `scripts/` にあり、違いは1行目のコメントの決定番号だけ）。コンパイルと実行の手順は `structural-aggrese`。
- テストの期待値（`tests/fixtures/example2/aggrese/`）は、見本を手で直して（配列50件、DB1 のパス）これで保存し直したもの。手順は同じフォルダーの `notes.md`。
- Batch の版が変わったら：見本を保存し直して書式の差を見る → `writer.py` の `BATCH_VERSION` と並びを合わせる → 期待値を作り直す（`notes.md` の手順）→ `scripts/accept_aggrese_project.py --overwrite` で受入を取り直す（本物の JRSNAP で 0711・0721 を生成するので数分かかり、画面が出る）。
- 受入記録は `tests/fixtures/acceptance/aggrese/record.json`。入力（`current.json`）や生成する XML が変わると `tests/acceptance` が失敗する。
- 直接基礎の照査値の既知の差（決定49）：WebPier の NDU は直接基礎の照査のデータを持たないので `_Output_Chokukiso.csv` ができず、Aggre-SE は DB1 から求める。0711 の結果で試すと、作用は見本と一致し、抵抗側は違った。ただし、JRSNAP の基礎照査との差と NDU の `FootInfo` の Df・γ2 の差が混ざっており、原因はまだ切り分けていない。

## 杭基礎の 0711・0721（決定94、P6b。2026-10-25）

- プロジェクトは `export/aggrese/project.py: build_pile_project(models, pier)`（杭の NDU のモデルから。順向の NDU、逆向の NDU の順に Case を並べる）と `writer.py: _foundation`。非線形部材は柱（タイプ 柱）と杭の断面ごと（タイプ 杭、せん断スパン 0）、反力は杭の各列の最初の要素の i 節点（杭頭、`_Direction` は奥行き本数）、変位は柱の下端の節点（`dgDispAtPoints` の先頭）、`FoundationType` 0、制限値 `dgLimitValue0` は空。照査項目は `CHECKS` から ⑧ を除く。`Project.pile_rows`・`pile_sections`。見本 `Batch/tests/JRSNAP_Ver5.2-L03/01_サンプル(V53)：RC橋脚L：RC/` のプロジェクト（`tests/fixtures/aggrese/pile_s.xml`）とは、書式の版・照査項目・柱のタイプ・スペクトルなど決定49・76 の既定だけが違う（`tests/export/test_aggrese_pile_project.py`）。
- DB1 の名前は `ndu_databases(folder, names, [(NDU の名前, Case の数), …])`：JRSNAP は `<NDU>(Case<n>_…).DB1` と NDU ごとに Case を 1 から数える。
- 制限値は runner が `--sdr <.sdr> --sdr-direction axial|transverse` で読む（`pipeline/aggrese.py: Limits`、`check_seismic(..., limits=)`）。`.sdr` は 0500 の結果（`PileGroundModel.sdr_source`）を一時ファイル `foundation.sdr` で渡す。杭基礎の runner の成果物は 4 つ（ステップ表なし）。
- 受入：`scripts/accept_pile_nonlinear.py`（`pile_seismic.json` の 0711・0721 を本物の runner で生成、計算書の制限値が `.sdr` と同じことと、見本 RC橋脚L の結果に見本のプロジェクトと WebPier のプロジェクトを当てて安定レベル1が同じことを確かめる。記録 `tests/fixtures/acceptance/pile_nonlinear/`、テスト `tests/acceptance/test_pile_nonlinear_acceptance.py`）。

## 鋼管ソイルセメント杭の 0711・0721（決定122、P10a。2026-10-29）

- `build_pile_project`：柱は杭列の範囲（`KGInfo`）の外の M-θ 要素 1 つ（結合部の材端回転ばねは柱に数えない）。杭の断面は結合部（501）と鋼管（62）の 2 つで、どちらも部材照査タイプ 杭。杭頭反力の節点は杭列の最初の要素（材端回転ばね）の i 端＝杭頭。⑧ 杭の段落しは `杭基礎.鋼管ソイルセメント杭.段落し` の段落し後の鋼管厚があるときだけ（決定126、`_steel_anchor_bar`）。Aggre-SE は鋼管杭（62・501）の `clsPileAnchorBar` を D1＝杭径・n1＝厚・D2＝fsy、PileHeadLength＝杭頭埋込長、ParagraphLength＝上杭長（0 なら自分で決める）、Upward／Downward＝施工余裕長の低止まり／高止まり、ReductionCoefficient＝継手低減係数として読み、PileMidLength・DesignMarginLength・Aw・Ss・余裕率は使わない（Mud 係数は 1 に固定）。WebPier は D1＝D−2c、n1＝t2−c、D2＝特性値（235・315）、50、0.9 を書き、使わない項目は初期値。段落し後の Myd は Aggre-SE が γs 1.1 の My0·(1−N/Ny) で、DB1 を dgMemberNumber で割った杭1本当りの軸力から求める（Example4 の線路方向で 427.04 kN·m を手計算で再現）。計算書は report.pdf の後ろに付ける。
- 段階（`stages._with_nonlinear_piles`）：鋼管ソイルセメント杭は `complete` が `PileSeismicResult(None, response)`（杭頭反力の最大値から定める最小鉄筋量を作らない）。計算書は応答変位法の頁（G3〜G5）と Aggre-SE の report.pdf だけ（`render_pile_seismic_check` の `minimum is None`）。

## 杭基礎の液状化時の Case（決定95、P6c。2026-10-25）

- プロジェクトの Case は、通常の Case のあとに液状化時の NDU ごとに 1 Case（`build_pile_project(models, pier, liquefied=[...])`、`Project.liquefaction_cases`・`liquefaction_index`）。その Case は `dgEkijoCase21`・`dgEkijoCase2`（L2 のスペクトルⅠ・Ⅱ。`_rbSpec` が両方なので両方の旗。片方だけだと、その Case の応答値は片方のスペクトルだけで求まる）に -1、照査項目は `LIQUEFACTION_CHECKS`（②③⑤⑦⑨）、`_rbEkijo` は入力の液状化指数。`dgEkijoCase1`（L1 の液状化）は使わない。
- 制限値：runner の `--sdr-liquefied`（`aggrese.Limits.liquefied`、一時ファイル名は `foundation(液状化時用).sdr`）が `dgLimitValue0` の行 10〜16 を埋める。Aggre-SE の規則で、行 10〜13 が L1 の液状化、14〜16 が復旧性L2 の液状化に使われ、安全性は液状化用の行 17〜30 が空なら通常の値（0〜9）に戻る（`CalculationFoundation.vb` の `GetLimit`）。そのため、液状化時の Case の基礎の安定の照査が計算書に出ても、液状化時用の `.sdr` の値が使われるのは復旧性（①）を ON にしたときだけ。受入はその Case だけを ① と ⑦ にして確かめる。
- 計算書の杭基礎の照査には、各安定レベルの決定ケースの行だけが出る（液状化時の Case が決定ケースでなければ出ない）。

## 杭基礎の応答変位法の Case（決定97、P6d。2026-10-26）

- 0711・0721 は Aggre-SE を 2 回走らせる。1 回目（慣性力と液状化時の Case）の総括表の応答値一覧表から、ρm 1.0・αf 1.0・正向の Case の 全体系折曲点震度・等価固有周期・復旧性の最大応答震度と L1地震動・安全性の最大応答震度を読む（`calc/response_displacement.read_inertia`。行は列 A のブロック名と列 B の見出しで探す。ρm 1.2 の Case は '-----'）。
- 2 回目のプロジェクトは、ほかの Case のあとに応答変位法の Case を 1 つずつ（`build_pile_project(..., response=[(level, model)])`、照査項目 `RESPONSE_CHECKS`：L1 は ③⑤⑥⑦⑨、L2 は ①②③⑤⑦⑨）。Aggre-SE は荷重増分の DB1（`KaisekiFlg≠1`）を応答変位法とみなし、⑥ の印で L1、無ければ L2 にする（`ExcelReportPickUpFile.vb`）。応答値は最終ステップ、杭基礎の水平変位から地盤変位（`DeltaG`）を引く。
- 計算書は WebPier の「応答変位法による設計応答値の算定」の頁のあとに 2 回目の report.pdf（`seismic_check.render_response_check`）。この頁の方眼Excel は作らない（役割 `0711.xlsx` が総括表と重なる）。

## 0711・0721 の計算書・ピックアップ・総括表（決定56〜58）

- WebPier の生成が `run --input <ステージングした XML> --output-dir <空の一時フォルダー> --snap-map <map> --summary-xlsx true --report-pdf true --check-tables false --pik true --pile-anchor-bar-pdf false --foundation-steps true` を呼ぶ（返る成果物は result.json・report.pdf・pickup.pik・summary.xlsx と、直接基礎なら foundation-steps.csv）（`.env` の `STRUCTURAL_MCP_AGGRESE_RUNNER`）。1方向 4 秒ほど（2026-10-19、実アプリ）。WebPier は呼ぶ前後で XML とフォルダーの SHA を比べ、変わっていれば生成を止める。成果物の組（kind と relativePath）が求めたものとちょうど一致しないと止める。
- `--foundation-steps` は Batch 9c70f54 以降の runner にしかない（structural-mcp が固定している Batch にはまだない。`structural-aggrese` の `references/foundation-steps.md`）。
- `report.pdf` の見出しは DB1 の題名から来るので、見本 10.5・10.6 の作成者が書き込んだ見出しを WebPier は再現しない。決定76 の前は線路方向（1 Case）が11ページ、線路直角方向（2 Case）が18ページ（いまは4 Case・8 Case）。
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

- 作る：入力の `outputs` で `longitudinal_nonlinear_analysis`（0721 は `transverse_nonlinear_analysis`）と、それが使う項目（`ground_model`・`reactions`・`longitudinal`・`longitudinal_seismic`）を選び、`uv run --project "." --locked python -m webpier --overwrite`（決定72。段階を選ぶ引数はない）。使う項目の段階（0500・0600・0610・0710）も作り直して公開する。0711 が書くのは `output/0711_線路方向非線形解析.pdf`・`.json` と `post/` の `線路方向_JRSNAP/`・`線路方向.xml`・`線路方向_Aggre-SE.pik`・`線路方向_Aggre-SE.xlsx`・`線路方向_Aggre-SE_直接基礎.csv` と各付帯JSON。1方向数分かかり、JRSNAP の画面が出る。`.env` に JRSNAP と Aggre-SE の runner が要る。
- 最新か確かめる（作り直す前に）：付帯JSONの `input.sha256` を `pre/input.json` の SHA256 と、`implementation_sha256` を `canonical_sha256({str(p): d for p, d in webpier.pipeline.runtime.dependency_hashes().items()})` と比べる。両方一致すれば、いまの入力と実装で作ったもの（2026-10-19、「出力して」と言われて確かめた手順）。総括表と計算書はバイトが毎回変わるので、ファイルの SHA256 どうしを比べて新旧を判断しない。
- 同じ作業ツリーで別のセッションが `CONTEXT.md` などを編集していることがある。コミットは `git commit --only <自分のファイル>` で、他人の差分を含めない（`git diff -U0` で自分の差分か確かめる）。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- Aggre-SE そのものの性質（項目の意味、画面との対応、runner の挙動、Batch の版による書式の違い）：structural-mcp の `skills/structural-aggrese/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0711・0721 の説明（計算書は Aggre-SE の帳票そのもの、判定の読み方、既知の差）：structural-mcp のスキル `structural-webpier` の checks.md（ここには書かない）。
- 案件の判断・見本の読み替え：その案件の repo。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
