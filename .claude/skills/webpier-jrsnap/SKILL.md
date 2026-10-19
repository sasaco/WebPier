---
name: webpier-jrsnap
description: WebPier が JRSNAP を使う実装と決定を扱う。0710・0720 の NDU の書出し（webpier/export/jrsnap/、records.py・profile.py）と実アプリでの受入（accept_jrsnap_ndu.py）、0711・0721 の静的非線形解析で JRSNAPHeadless の runner を呼ぶこと（決定47、ADR-0007）、0710・0720 の計算書に差し込むデータ確認図（決定50）と荷重図 10.3・11.3（決定51、diagrams.py の基本ケース→組合せ、pipeline/jrsnap.py の draw_figures、insertion.py）、受入 accept_jrsnap_figures.py、テストの代役 tests/fixtures/jrsnap/fake_runner.py、見本 Example橋脚2 の NDU と PDF の照合に使う。JRSNAP そのもの（画面、NDU の項目、解析エンジン、figures の仕組み）はスキル structural-jrsnap-input・structural-jrsnap-figures・structural-jrsnap-ndu・structural-jrsnap-soil を使う。
---

# WebPier の JRSNAP の使い方（決定47・50・51）

**JRSNAP 自体はグローバルのスキルを参照**：画面の起動・NDU の保存・解析・JRSNAPHeadless の `run` は `structural-jrsnap-input`、データ確認図・荷重図と `figures` の仕組みは `structural-jrsnap-figures`、NDU のキーとフィールドは `structural-jrsnap-ndu`、SOIL-JR は `structural-jrsnap-soil`。ここには WebPier の実装・決定・受入・見本との対応だけを書く。

- JRSNAPHeadless はいま structural-mcp の作業ツリーの `JRSNAPHeadless/`（git 管理外、リモートなし）。WebPier は `.env` の `STRUCTURAL_MCP_JRSNAP_RUNNER`（`<JRSNAPHeadless>\bin\Release\JRSNAP.Headless.exe`）から呼ぶ。版は runner の横の `jrsnap-headless.json`（いまは 5.2-L03）で決まる。
- `bin\Release` は 2026-10-18 に `figures` で作り直した（WebPier が `figures` に切り替えたのと同時。`JRSNAP.LoadPicture.exe` を含む。JRSNAPHeadless 2374a5b で古い `data-check` から置き換え）。

## NDU の書出しと受入

- WebPier が書くレコードと根拠は `webpier/export/jrsnap/records.py`・`profile.py` と README「JRSNAP（5.2-L03 NDU）」。2026-10-17 に 5.2-L03 の読込・保存処理で確かめた形式の制約（行の順、`Tisou=` の空行、`DataInfo` 第20、`TanbuShiji`、`SectJikuNum` の段の選び方）は `structural-jrsnap-ndu` の `references/ndu-format.md`。
- WebPier の生成では、意図する線路主筋と先頭／末尾 N 段の芯位置・径・本数・材質を照合し、一致しない配置は v1 未対応として拒否する。主筋段数を自動で増やして辻褄を合わせない。公式 5.2 説明書 90・530頁と DRTU/DRTL/DRTUV/DRTLV の対応を根拠表に記録した。
- WebPier の候補では 166 レコード・623 項目と8荷重の合力・基礎底面回りモーメントを独立期待値と照合し、2回目保存のバイト安定を確認した（件数はこのモデル固有）。
- 一般の生成結果に実アプリ検証済みと書かない。生成時の付帯情報と、実際に読み込んだ同一候補を特定する受入記録を分ける。
- WebPier で採用した Vcd=2.0・Vsd=1.3・Vdd=1.8・Dmax=25 mm は、利用者が入力欄の初期値として明示指定した値。JRSNAP 共通の既定値に一般化せず、入力値として保持する。
- WebPier の NDU は直接基礎の照査のデータを持たない（`ChokuKisoNum=0`）ので、解析で `_Output_Chokukiso.csv` はできず、Aggre-SE は DB1 から求める（決定49 の既知の差。スキル `webpier-aggrese`）。
- 実アプリでの受入：`scripts/accept_jrsnap_ndu.py`（記録 `tests/fixtures/acceptance/jrsnap_v52/`）。補助に `.claude/skills/jrsnap-input-open-save/scripts/save-ndu.ps1`・`roundtrip.cs` を使い、記録がその SHA を持ち、`.gitattributes` が LF に固定している。**このフォルダーは動かさない**（同じ道具の正は `structural-jrsnap-input` の scripts。WebPier の複製はスキルではなく受入の補助として残している）。
- 見本 `Example橋脚2` の NDU と PDF の照合の記録は `references/example-pier2-seismic-verification.md`。

## 0711・0721 の静的非線形解析（決定47）

- 生成が JRSNAPHeadless の `run` を呼び、JRSNAP の `.NDT` と解析結果をフォルダー `post/線路方向_JRSNAP/`・`post/線路直角方向_JRSNAP/` に丸ごと置き換えて出力する。1方向数分かかり、JRSNAP の画面が出る。
- 組合せごとの `.ndt` では使わない基本ケースの荷重が 0 になる（例：0720 の Case1 の `.ndt` は CASE-6 下り線が 0）。基本ケースごとの荷重を `.ndt` から読むときは、そのケースを使う組合せの `.ndt` を選ぶ（決定51）。

## 0710・0720 のデータ確認図（決定50）

0710・0720 の計算書は、検討モデル（10.1・11.1）の後に、見出しも本文も付けずに `structural-jrsnap-figures` の表の5つの図（`nonlinear-numbers,section-numbers,element-table,section-detail,node-springs`）を表の順で挟み、作用の計算（10.2・11.2）を新しいページから始める。

- 見本は `.claude/docs/Example橋脚2/10_線路(耐震).pdf`・`11_直角(耐震).pdf` の 3〜7 ページ。見本の 1・2 ページ（節点番号図・要素番号図）は WebPier の骨組図と重なるので入れない。見本の右上の「10 - n」は計算書全体に後から付けた番号で、S_DataCheck は印刷しない。見本 5.1 の図は部材の外形の灰色の枠を描いていたが、いまの S_DataCheck は描かない（JRSNAP の版の違いで、直さない）。
- 呼び出しは `webpier/pipeline/jrsnap.py` の `draw_figures`。データ確認図と荷重図を1回の `figures` で頼む（`--data-check <DATA_CHECK_FIGURES> --data-check-combination 1 --load-diagram <使う組合せ> --timeout-seconds <300＋120×組合せの数>`）。図の順は `DATA_CHECK_FIGURES`、組合せは `DATA_CHECK_COMBINATION = 1`。返った図ごとの PDF のページを図の順に1つにまとめる。
- 差し込みは、他のエンジンのページと共通の `webpier/reporting/stages/insertion.py`。0710・0720 の帳票は `Insertion(DATA_CHECK, <作用の見出し>, before=True)` で、10.2（11.2）の前にページの名前 `data_check` のページを挟む（`render_with_pages`）。
- 段階の登録表の `StageSpec.jrsnap_figures` が、どの NDU から描くかと「基本ケース → 組合せ」を決める。NDU の付帯JSONの `jrsnap_figures` に、runner の版と報告、データ確認図の組合せと図（`data_check`）を記録する。
- 0711・0721 を選ばない生成でも毎回描く。そのため、0710・0720 を含む生成には `STRUCTURAL_MCP_JRSNAP_RUNNER` が必須。
- 番号図・断面・節点ばねは組合せで変わらないので、組合せ1の `.ndt` だけで描く（0720 は組合せが2つ）。runner が 0710 のために書く `.ndt` は、0711 の `post/線路方向_JRSNAP/` の `.ndt` と SHA256 が同じ。
- 用語は CONTEXT.md に合わせ、「組合せ」と「基本ケース（CASE-n）」を混ぜない。
- 補助を `Environment.Exit` で終えると、終了処理の中で S_DataCheck の画面が例外を出し、答えの後に終了コードが変わったことが 0710 で1回あった（そのため補助は `TerminateProcess` で終える。`structural-jrsnap-figures` の report-host.md）。
- テストの代役は `tests/fixtures/jrsnap/fake_runner.py` の `figures`。データ確認図は図ごとに `FAKE DATA CHECK <名前> <NDU の SHA256 の先頭16桁>` の1ページを返す。誤動作は `FAKE_JRSNAP_FIGURES` で選ぶ（`FAKE_JRSNAP` は `run` だけに効く）。
- 手で試すとき：`& $env:STRUCTURAL_MCP_JRSNAP_RUNNER figures --input '<WebPier>\post\線路方向.ndu' --output-dir 'C:\tmp\fig-out' --data-check 'nonlinear-numbers,section-numbers,element-table,section-detail,node-springs'`、荷重図は `--input '<WebPier>\post\線路直角方向.ndu' --load-diagram 1,2`。

## 0710・0720 の荷重図 10.3・11.3（決定51）

- 0710 に「10.3 荷重図」、0720 に「11.3 荷重図」の見出しを置き、その後に基本ケースのページを CASE の順に1ケース1ページで挟む。作用の組合せは 10.4・11.4 で、新しいページから始める。荷重が0のケースも省かない。
- WebPier は NDU のモデル（`export/jrsnap/model.NduModel` の `cases` と `combinations[].coefficients`）から、基本ケースごとに「そのケースを使う、番号がいちばん小さい組合せ」を決める（0710 は全ケース 1、0720 は CASE-6 だけ 2。0720 では組合せ1の NDT は CASE-6（下り線）が0、組合せ2の NDT は CASE-5（上り線）が0）。その組合せを `--load-diagram` に渡し、返ったページから（`summary.loadDiagram[].pages` のページとケースの対応で）1ページずつ取り出す。
- 実装の場所：「基本ケース → 組合せ」は `webpier/export/jrsnap/diagrams.py` の `diagram_combinations`（登録表の `StageSpec.jrsnap_figures` が使う）、runner の呼び出しとページの取り出しは `webpier/pipeline/jrsnap.py` の `draw_figures`、計算書への差し込みは `webpier/reporting/stages/insertion.py`（`Insertion(LOAD_DIAGRAM, <10.3・11.3 の見出し>)`）。NDU の付帯JSONの `jrsnap_figures.load_diagram` に `[{case, combination}, …]` を記録する。
- いまの WebPier の NDT はどのケースも1部材に要素荷重が1つなので、`AutoRowFlg` の 0 と 1 で図はピクセル単位まで同じ。0710 の CASE-1 で、節点4〜6付近の「297.680」と「4167.450」の文字が重なるのは、種別4（柱自重）の既定の配置で、`AutoRowFlg` では直らず、JRSNAP の描画として受け入れた。
- いまの WebPier の NDT では `NDT_REJECTED`（要素荷重の2つの値がともに0の行）は起きない（JRSNAP が0にするのは、いまは節点荷重だけ）。
- 受入：`scripts/accept_jrsnap_figures.py`（本物の runner、5.2-L03。記録 `tests/fixtures/acceptance/jrsnap_figures/record.json`、テスト `tests/acceptance/test_jrsnap_figures_acceptance.py`）。0710 は8ページ・0720 は9ページが CASE の順、A4縦・色の画素0・ページ番号なし、0720 の CASE-5・CASE-6 の両方に 480（`480.000`）を確かめた（2026-10-18）。生成する NDU か「基本ケース → 組合せ」が変わると `tests/acceptance` が失敗するので、`--overwrite` を付けてやり直す。
- 計算書の確かめ方（本物の runner で `--stage 0710`・`0720` を作り直した後）：`uv run --no-project --with pypdfium2 --with pillow python -X utf8 …` でページごとの文字を取り出し、並びを見る。2026-10-18 の `pre/input.json` では、0710 は17ページ（1〜2 10.1、3〜7 データ確認図、8 10.2 の末尾に「10.3 荷重図」、9〜16 CASE-1〜8、17 「10.4 作用の組合せ」）、0720 は19ページ（8〜9 11.2 で9の末尾に「11.3 荷重図」、10〜18 CASE-1〜9、19 「11.4」）。組合せ2から取った 0720 の CASE-6 だけ、ヘッダーの名前が組合せ2の NDT（`『線路直角方向(Case2_…)』`）になる。見出しのページと 10.4・11.4 の改ページは、150dpi の PNG にして目でも確かめる。
- 見本 `.claude/docs/Example橋脚2/10_線路(耐震).pdf` の 10.3（10-9〜10-11）は、Excel で描いた図（1ページに2〜3ケース）で、その体裁は再現しない。
- 詳細と進み具合は `.claude/docs/plans/jrsnap-load-diagram-plan.md` と `refactoring-decisions.md` の決定51。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- JRSNAP・JRSNAPHeadless そのものの性質：structural-mcp の `skills/structural-jrsnap-*/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0710・0720・0711・0721 の説明（差し込む図、JRSNAP への答え方、成果物）：structural-mcp のスキル `structural-webpier` の checks.md・outputs.md（ここには書かない）。
- 案件の判断・見本の読み替え：その案件の repo。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
