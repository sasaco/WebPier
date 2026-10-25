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
- 節点は上から・同じ高さでは左から番号を振る（操作説明書 2.1.6、決定67）。`calc/frame` が振り、角の節点を足す NDU の書出しがもう一度振り直す。末尾に足した節点（桁受けなど）があると、JRSNAP は警告なしに読み込み、解析が1回目の変位増分で収斂せず降伏震度 0.0 前後の破綻した結果になる（P7、2026-10-20）。
- 直角方向の制御節点は `NodeRole.CONTROL`（決定81、決定65 を改めた）：両側の桁の節点（それぞれの支承の座から h1＋h2）のうち、桁の水平力（列車荷重の経路は 0600 の桁の慣性力、荷重モデルは増分の直角方向の支承作用の側ごとの和）の大きい側の節点に `calc/frame._girder_levels` が付ける。同じなら高い方。La はそこからフーチング天端。
- La/d＜2 は `NonLinInfo1` の第4欄（破壊形態）を 2（せん断、NDT の AP カードの `S`）にする（決定66、`section.py`・`records.py`、検証器も La/d との組を確かめる）。1.25 未満は入力エラー。見本は Batch の `JRSNAP_Ver5.2-L03/05_参考(V52)：T形両端固定` の地中梁（`NonLinInfo7=1,3,1,2,…`、La/d≈1.4）。P7（La/d 1.73）で実アプリが解析し、Aggre-SE の損傷レベルの制限値が降伏にそろった（θ1＝0.001143）ことを確かめた（2026-10-20）。受入の記録（scripts/accept_*）はまだない。

## 杭基礎の 0711・0721（決定94、P6b。2026-10-25）

- JRSNAP の runner は NDU ごとに `run`（`pipeline/generate.py: _analyze_stage`、`jrsnap.merge_nonlinear`）。0721 は順向と逆向の 2 回で、結果を 1 つのフォルダーにまとめる（ファイル名は NDU の名前から始まるが、S_ANALYSIS の `解析実行Err.log`〔正常なら空〕は名前がなく両方が書くので、同じバイトなら 1 つにし、違えばエラー）。`NonlinearAnalysis.also` が 2 つ目以降の NDU の出力の種類（`jrsnapreverse`）。付帯 JSON の `nonlinear_analysis.also_ndus`、`runner_summary.also`。
- 液状化する地層のある入力は、0710・0720・0711・0721 とも生成の前に入力エラー（`StageSpec.precheck`、`stages._no_liquefaction`）。

## 杭基礎の 0710・0720（決定93、P6a。2026-10-25）

- NDU は `webpier/export/jrsnap/build_pile.py` の `build_pile_ndu(profile, pier, layout, seismic, springs, *, reverse=False)`（部品は `pile_model.py`・`pile_build.py`・`pile_records.py`・`pile_validate.py`、書出しは `writer.write_pile_ndu`）。要素分割とばねは `calc/pile_seismic.py`（厳密な Decimal）、.sdc の読取りは `export/soiljr/sdc_seismic.py`。規則・見本との対応・欄の意味は `.claude/docs/plans/pile-ndu-fields.md`、決定93。
- 段階の配線：`pipeline/stages.py` の `_with_seismic_piles`。0710 は NDU 1つ、0720 は `jrsnapreverse` で逆向の NDU も書き、荷重図は両方の NDU から描いて基本ケース順に合わせる（`FigurePages.also`・`drawn_from`、`jrsnap.add_load_diagrams`）。
- 計算書：杭基礎のとき組合せ Case の表（10.4・11.4）の「地盤抵抗TYPE」の列を省く（`frame.piles is not None`）。杭のための記述は足さない。
- 受入：`scripts/accept_pile_ndu.py`（見本 RC橋脚L の NDT と照合。差は名前・荷重・DataInfo の旗・Kv2 の同値の丸め〔2086.25：JRSNAP は .2、Decimal は .3〕だけ。見本は 5.3 の .sdc に連携しているので、照合だけ固定の 5.3 の .sdc を使い、本番は 5.2 のまま）と `scripts/accept_pile_seismic.py`（`pile_seismic.json`、f'ck 30 の3つの NDU を本物の JRSNAP が全 4 組合せずつ最後まで解析する。記録 `tests/fixtures/acceptance/pile_seismic/`、テスト `tests/acceptance/test_pile_seismic_acceptance.py`）。
- 見本の NDU の `SRenkei`（SOIL の連携）は書かない：絶対パスが決定性を壊し、NDT は連携なしでも同じ。f'ck が範囲外だと解析が `LOGFILE END` なしに止まる（エラー 808）ので、runner は `ANALYSIS_FAILED` を返す。

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
- 番号図・断面・節点ばねは組合せで変わらないので、組合せ1の `.ndt` だけで描く（組合せは照査パターン（ρm, αf）の4つずつで、0710 は4つ、0720 は8つ。決定76）。runner が 0710 のために書く `.ndt` は、0711 の `post/線路方向_JRSNAP/` の `.ndt` と SHA256 が同じ。
- 用語は CONTEXT.md に合わせ、「組合せ」と「基本ケース（CASE-n）」を混ぜない。
- 補助を `Environment.Exit` で終えると、終了処理の中で S_DataCheck の画面が例外を出し、答えの後に終了コードが変わったことが 0710 で1回あった（そのため補助は `TerminateProcess` で終える。`structural-jrsnap-figures` の report-host.md）。
- テストの代役は `tests/fixtures/jrsnap/fake_runner.py` の `figures`。データ確認図は図ごとに `FAKE DATA CHECK <名前> <NDU の SHA256 の先頭16桁>` の1ページを返す。誤動作は `FAKE_JRSNAP_FIGURES` で選ぶ（`FAKE_JRSNAP` は `run` だけに効く）。
- 手で試すとき：`& $env:STRUCTURAL_MCP_JRSNAP_RUNNER figures --input '<WebPier>\post\線路方向.ndu' --output-dir 'C:\tmp\fig-out' --data-check 'nonlinear-numbers,section-numbers,element-table,section-detail,node-springs'`、荷重図は `--input '<WebPier>\post\線路直角方向.ndu' --load-diagram 1,2`。

## 0710・0720 の荷重図 10.3・11.3（決定51）

- 0710 に「10.3 荷重図」、0720 に「11.3 荷重図」の見出しを置き、その後に基本ケースのページを CASE の順に1ケース1ページで挟む。作用の組合せは 10.4・11.4 で、新しいページから始める。荷重が0のケースも省かない。
- WebPier は NDU のモデル（`export/jrsnap/model.NduModel` の `cases` と `combinations[].coefficients`）から、基本ケースごとに「そのケースを使う、番号がいちばん小さい組合せ」を決める（0710 は全ケース 1、0720 は CASE-6 だけ 5。0720 では組合せ1〜4 の NDT は CASE-6（下り線）が0、組合せ5〜8 の NDT は CASE-5（上り線）が0。組合せ5〜8 は逆向だが、逆向は増分の作用（`LOAD 1`）と目標変位の符号だけを変え、固定の CASE-6 の荷重は同じ）。その組合せを `--load-diagram` に渡し、返ったページから（`summary.loadDiagram[].pages` のページとケースの対応で）1ページずつ取り出す。
- 実装の場所：「基本ケース → 組合せ」は `webpier/export/jrsnap/diagrams.py` の `diagram_combinations`（登録表の `StageSpec.jrsnap_figures` が使う）、runner の呼び出しとページの取り出しは `webpier/pipeline/jrsnap.py` の `draw_figures`、計算書への差し込みは `webpier/reporting/stages/insertion.py`（`Insertion(LOAD_DIAGRAM, <10.3・11.3 の見出し>)`）。NDU の付帯JSONの `jrsnap_figures.load_diagram` に `[{case, combination}, …]` を記録する。
- いまの WebPier の NDT はどのケースも1部材に要素荷重が1つなので、`AutoRowFlg` の 0 と 1 で図はピクセル単位まで同じ。0710 の CASE-1 で、節点4〜6付近の「297.680」と「4167.450」の文字が重なるのは、種別4（柱自重）の既定の配置で、`AutoRowFlg` では直らず、JRSNAP の描画として受け入れた。
- 荷重の行が1つもないケースは、JRSNAP の荷重図がページを省いたうえ次のページに前の題名を付ける。WebPier は値0の節点荷重を1行書いて避ける（決定62。2026-10-20、P7 で本物の runner により全ケースの題名と中身が合うことを確認）。雪荷重のない橋脚は雪荷重のケースそのものを作らない（決定69、7・8ケース）ので、いまは入力からこの形はできない。
- 基本ケースの番号は作ったケースの順（`SeismicAction.number`）。`SeismicCase` の値は雪のあるときの番号で、番号に使わない。検証器は `LoadTitle` が profile の名前の順（雪荷重を抜いた順も可）であることを確かめる。
- いまの WebPier の NDT では `NDT_REJECTED`（要素荷重の2つの値がともに0の行）は起きない（JRSNAP が0にするのは、いまは節点荷重だけ）。
- 受入：`scripts/accept_jrsnap_figures.py`（本物の runner、5.2-L03。記録 `tests/fixtures/acceptance/jrsnap_figures/record.json`、テスト `tests/acceptance/test_jrsnap_figures_acceptance.py`）。0710 は8ページ・0720 は9ページが CASE の順、A4縦・色の画素0・ページ番号なし、0720 の CASE-5・CASE-6 の両方に 480（`480.000`）を確かめた（2026-10-18）。生成する NDU か「基本ケース → 組合せ」が変わると `tests/acceptance` が失敗するので、`--overwrite` を付けてやり直す。
- 計算書の確かめ方（本物の runner で 0710・0720（出力項目 `longitudinal_seismic`・`transverse_seismic`）を作り直した後）：`uv run --no-project --with pypdfium2 --with pillow python -X utf8 …` でページごとの文字を取り出し、並びを見る。2026-10-18 の `pre/input.json` では、0710 は17ページ（1〜2 10.1、3〜7 データ確認図、8 10.2 の末尾に「10.3 荷重図」、9〜16 CASE-1〜8、17 「10.4 作用の組合せ」）、0720 は19ページ（8〜9 11.2 で9の末尾に「11.3 荷重図」、10〜18 CASE-1〜9、19 「11.4」）。組合せ5から取った 0720 の CASE-6 だけ、ヘッダーの名前が組合せ5の NDT（`『線路直角方向(Case5_ρm10_αf1_逆向)』`）になる（決定76 の前は組合せ2）。見出しのページと 10.4・11.4 の改ページは、150dpi の PNG にして目でも確かめる。
- 見本 `.claude/docs/Example橋脚2/10_線路(耐震).pdf` の 10.3（10-9〜10-11）は、Excel で描いた図（1ページに2〜3ケース）で、その体裁は再現しない。
- 詳細と進み具合は `.claude/docs/plans/jrsnap-load-diagram-plan.md` と `refactoring-decisions.md` の決定51。

## 知見を更新する

- WebPier の実装・決定・受入・見本との対応：このスキルか `.claude/docs/plans/refactoring-decisions.md`。
- JRSNAP・JRSNAPHeadless そのものの性質：structural-mcp の `skills/structural-jrsnap-*/` を編集し、structural-mcp で commit する（ここには書かない）。
- 計算書を使う人向けの 0710・0720・0711・0721 の説明（差し込む図、JRSNAP への答え方、成果物）：structural-mcp のスキル `structural-webpier` の checks.md・outputs.md（ここには書かない）。
- 案件の判断・見本の読み替え：その案件の repo。
- コードで確かめたこと、実アプリで試したこと、推定を区別して書く。
