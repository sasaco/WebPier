# 0400 照査の前提（構造細目）と配筋図、R5 への切替

作成 2026-10-21。依頼「`%TEMP%\webpier-0400-handoff.md` を実装してください」（grill 済みの計画 `C:\Users\sasai\.claude\plans\cozy-stirring-gray.md` の引継ぎ）。決定は `refactoring-decisions.md` の **決定73**、原則は **ADR-0012**、用語は CONTEXT.md（照査の前提（構造細目）・配筋図・水掛かりの程度・使用性（損傷）・中間帯鉄筋）。

進捗の書き方：終わった項目に ✅、知見には日付と commit、**事実**（コード・本物の runner で確かめた）と**推定**を分けて書く。

## 決まったこと

計画書（cozy-stirring-gray.md）の「Grill で決めたこと」の表に加えて、2026-10-21 の grill（このセッション）で決めたこと：

| 論点 | 決定 |
|---|---|
| 0400 の入力の空欄 | 柱・梁・フーチング（**上面を含む**）の配筋はすべて要る値。空欄はパスを名指しした入力エラー。`pre/input.json`・`current.json` にフーチング上面の配筋を入れる（今は空欄。0800〜0820 は上面を読まない） |
| 帯鉄筋の行 | 0400 の 6)〜9) は柱下端を含む行だけを照査する（`calc/column_check.py: _hoops` と同じ）。2D区間より上の行は照査しない |
| 0400 の判定 | WebPier が判定する項目がすべて OK なら `ok`、1つでも NG なら `not_ok`。参照の項目と 9) は含めない。結果JSONに項目ごとの判定 |
| R5 の節の条文番号 | 0611/0621・0810/0820・0910 の WebPier の頁の見出しの条文番号の触（【ＲＣ標準 7.2.2】など）を**外す**。0800 の【ＲＣ標準 13.6.3】は切替の対象外なので残す |
| R5 の節の説明 | 構成（節・照査式・記号の定義）は保ち、中身を **R5 の方法**（Capacita の R5 の実装と印刷する値が根拠）に書き直す。食い違いは一覧にしてオーナーに尋ねる |
| 0400 の条文番号 | 見本どおり印刷する。見本の誤り（R5 でない番号、Ex2 から足す項目の旧版の番号）は R5 の番号が確かめられれば直し、確かめられなければ一覧にして尋ねる |
| 見本 0440 | 杭の構造細目。直接基礎の WebPier の対象外 |

オーケストレーターが決めたこと（異なれば指摘を受けて直す）：

- 出力項目のキーは `detailing`、画面の表示は「照査の前提（0400）」、12項目の先頭に置く（0400 は 0500 より前）。`requires` は空。
- フーチング上面の配筋の値は、`pre/input.json` のフーチングの出典（Example橋脚2 12_フーチング・06_照査の前提 6.1）から取る。

## 分担（2026-10-21）

| 担当 | 範囲 | 場所 | ブランチ |
|---|---|---|---|
| A | Phase 2 Capacita | `structural-mcp\Capacita` | `sasa/r5-rebar-amount` |
| B | Phase 5 GridLayoutPdf の PDF の図 | `C:\Users\sasai\Documents\GridLayoutPdf` | `sasa/pdf-figure` |
| C | Phase 1 → 3 R5 切替・行8・新しい節 | worktree `C:\tmp\wp-r5` | `sasa/0400-r5` |
| D | Phase 4 0400 の計算と計算書 | worktree `C:\tmp\wp-detailing` | `sasa/0400-detailing` |
| E | Phase 6 配筋図 | worktree `C:\tmp\wp-drawing` | `sasa/0400-drawing` |

- WebPier のブランチはすべて `sasa/glp` の記録の commit から分け、オーケストレーターが `sasa/glp` に統合する。
- 衝突しやすいファイル：`current.json`・`pre/input.json` は C（`柱の断面照査`・`片持ち梁の照査` の水掛かり）と D（`outputs`・`鉄筋.フーチング` の上面）がキーを分けて直す。`pyproject.toml`・`uv.lock` は E（ezdxf）だけが直し、GridLayoutPdf の wheel の url はオーケストレーターが統合時に直す。`refactoring-decisions.md`・`CONTEXT.md`・README・CLAUDE.md・この計画書の「決まったこと」はオーケストレーターだけが直す（担当は自分の Phase の節に書き戻す）。
- 別のセッションが worktree `C:\tmp\webpier-clear`（`sasa/clear-stale`）で `CONTEXT.md`・`refactoring-decisions.md`・README・CLAUDE.md を直している（2026-10-21 に未 commit を確認）。統合のときに衝突を確かめる。

## 記録

- [x] ✅ 決定73（`refactoring-decisions.md`）
- [x] ✅ ADR-0012（`docs/adr/0012-detailing-split-by-section-forces.md`）
- [x] ✅ CONTEXT.md：照査の前提（構造細目）・配筋図・水掛かりの程度（「鋼材の腐食に対する環境条件」を置換）・使用性（損傷）・中間帯鉄筋を足し、帯鉄筋の方向別有効本数・柱の断面照査・片持ち梁の照査を改めた
- [ ] 決定48・54・59・60 の「H16」と節番号（8.10・9.10 → 8.11・9.11）を直す
- [ ] README・CLAUDE.md
- [ ] スキル：webpier-capacita・webpier-cantilever・webpier-footing・webpier-foundation・structural-capacita・structural-webpier・pier-report-style

## Phase 1　R5 への切替（WebPier、担当 C）

- [ ] `export/capacita/wdj.py`：`BODIES` を R5 の id（R5_Rail 3、R5_Shinkansen 4、R5_JREast 8）に。`_MOMENT_TITLES`・`_SHEAR_TITLES` の行6 を「使用性（損傷）」に
- [ ] `calc/column_check.py`：`SAFETY_FACTORS`・`JR_EAST_SAFETY_FACTORS` を WebDanforJS の R5 の既定値に（違いは T_rbt 1.3、行7 の V_rbs 1.1、JR東日本は行6 の γi 1.0）。`environment_number` を水掛かり（1 常時乾燥、2 乾湿繰返し、3 常時湿潤）に
- [ ] `calc/footing_check.py`（0810/0820）・`calc/cantilever/check.py`（0910）も同じ
- [ ] 入力：`choices.py` の `CORROSION_ENVIRONMENTS` → `WATER_EXPOSURES`、`fields.py`・`parse.py`・`model.py`、GUI `gui/rebar_page.py` の `CHECK_LABELS`、`current.json`・`pre/input.json`
- [ ] 名前「復旧性（損傷）／復旧性（地震時以外）」→「使用性（損傷）」：`calc/longitudinal/combinations.py`、`calc/cantilever/combinations.py`、`reporting/stages/column_check.py`・`cantilever_check.py`、`loadmodel` の契約
- [ ] 切り替える節の WebPier の頁：条文番号の触を外し、説明を R5 の方法に書き直す（根拠は Capacita の R5 の実装）
- [ ] R5 で行6 が返す節 ID を本物の runner で確かめ、`REPORT_SECTIONS` を合わせる
- [ ] 代役の runner・テストの期待値

## Phase 2　Capacita：R5 の最小鉄筋量と最大鉄筋量（担当 A）

- [ ] 失敗する回帰テスト（`WebDanforCS/tests/UiTests`）：R5 の行8 の WDJ で 0.008Ac の行と最大鉄筋量の表。見本 0400 の手計算：N'd 7592.8 kN、f'ck 24、SD390 → Ac 524690.5 mm²、0.008Ac 4197.5 mm²、pb 1.750%（σ's＝0）
- [ ] `CalcResult_BendingReBarAmount.cs`：(c) 0.008Ac（k1 は `CalcResult_BendingDestruction.cs` の N'oud のものを共用）と最大鉄筋量（pt＝Ast/(b·d) ≦ 0.75pb、σ's は釣合状態のひずみから）
- [ ] `RailR5_Bending_ReBarAmount_Ver.cs`・`RailR5_BendingReBarAmountPrinter.cs` を R5 用に。節 ID `bending_rebar_amount` は変えない。H16 は変えない
- [ ] `.claude/check.ps1`、README（run-rc）、スキル structural-capacita
- [ ] Release ビルド（structural-mcp のルートで `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release`）、Capacita で commit

## Phase 3　WebPier：行8 と新しい節（担当 C、A の後）

- [ ] `calc/column_check.py`：`MOMENT_CASES` に (8, PERMANENT)、`REPORT_SECTIONS` の末尾に `bending_rebar_amount`
- [ ] `reporting/stages/column_check.py`：n.10「最小鉄筋量及び最大鉄筋量」、`foundation_check.py`：8.10・9.10 → 8.11・9.11
- [ ] `export/capacita/footing_wdj.py`：行8 に 0800 の `long_term`（Nd＝0）、0810/0820 の節の最後に差込み
- [ ] `export/capacita/cantilever.py`：行8 にケース 28、0910 の節の最後に差込み
- [ ] 代役の runner が `bending_rebar_amount` を返す
- [ ] 本物の runner の受入を取り直す：`accept_capacita_column.py`・`accept_footing.py`・片持ち梁

## Phase 4　0400 の計算と計算書（担当 D）

- [x] ✅ 出力項目 `detailing`：`inputs/outputs.py`、`pipeline/stages.py`（`OUTPUT_STAGES`、`StageSpec("0400", "0400_照査の前提", ...)`）、`gui/calculation_page.py`、`current.json`（false）・`pre/input.json`（true）の `outputs`、項目を数えるテスト、`scripts/accept_footing.py`（detailing を除く）
- [x] ✅ `current.json`・`pre/input.json` にフーチング上面の配筋（Ex2 06 6.1・6.2：上 線路 D25@125 芯 78.5、直角 D25@125 芯 103.5、指定。current.json は下面・スターラップ・材質・Dmax 25 も pre/input.json から）
- [x] ✅ 中間帯鉄筋の配置（calc 層。E も使う）：`webpier/calc/detailing/ties.py`（2026-10-21、8678729）
  - `base_hoops(pier, direction) -> BaseHoops`：その方向の帯鉄筋で柱下端を含む行（`start` が空欄か 0、ちょうど1行）。`direction`・`path`（入力のパス）・`diameter`・`legs`（方向別有効本数 n）・`pitch`・`grade`（柱の帯鉄筋の材質）。
  - `column_ties(pier, direction) -> TieLayout`：柱下端の行の脚の位置（`base_hoops` と `column_layout` から）。`tie_layout(layout, direction, legs, path)` が本体。
  - `TieLayout`：`direction`（線路／直角）、`effective_legs`（n）、`span`（面の長さ mm。線路は W6、直角は B6）、`targets`（面を n−1 等分する点 k·span/(n−1)、k=1…n−2、0.1 mm）、`outer`（外巻き帯鉄筋の2本の脚）、`intermediate`（中間帯鉄筋の脚、昇順）、`legs`（全部の脚、昇順。property）、`sets`（n/2 組）、`intermediate_sets`（(n−2)/2 組）、`max_spacing`（隣り合う脚の最大の間隔、48φ の照査に使う）。
  - 座標は `calc/column_rebar.py` と同じ（mm、左上が原点）。線路の脚は x（線路の主鉄筋の面＝Y に垂直な面に沿う）、直角の脚は y。脚は掛ける鉄筋の中心に立てる（使う鉄筋＝配置表の変更の後の `layout.bars`）。外巻きの脚は、その面に沿う方向で断面のいちばん外の鉄筋（どちらの方向の鉄筋でもよい。Ex2 の線路は直角の鉄筋の x＝102・4398、直角は線路の鉄筋の y＝108・2592）。中間帯鉄筋はその方向の1段目の主鉄筋のうち点に最も近いもの（同じ近さなら原点に近いもの）。
  - 入力エラー：n＜2、中間帯鉄筋があるのに1段目の主鉄筋がない、2本の脚が同じ鉄筋に掛かる（本数が足りない）。
- [x] ✅ `webpier/calc/detailing/`：4.2 柱（1)〜9)）、4.3 梁、4.4 フーチング。印字桁で丸め、frozen dataclass（`common.py`・`column.py`・`beam.py`・`footing.py`、入口は `calculate_detailing(pier) -> DetailingResult`）
- [x] ✅ `webpier/reporting/stages/detailing.py`：§4、4.1（図の場所。図は E）〜4.4、`grid_documents`
  - 4.1 の図の差し込み口：`render_detailing(result, path, figures=None)`・`grid_documents(result, figures=None)`・`content(result, figures)` の `figures`（`{"beam"|"column"|"footing": FigureSpec}`、`FIGURES` の名前）。あれば「(1) 梁」などの見出しのすぐ後に置く。E は `pipeline/stages.py` の 0400 の lambda で `figures=` を渡す。
- [x] ✅ 結果JSON と `engineering_status`（`DetailingResult.engineering_status`、各照査の `ok`／`*_ok`。9) は `above` だけで判定に含めない）
- [x] ✅ テスト：見本の転記と独立の手計算、決定的なバイト列（`tests/calc/test_detailing.py`・`test_detailing_ties.py`、`tests/reporting/test_detailing_report.py`、`tests/pipeline/test_generation_detailing.py`、転記 `tests/fixtures/example2/detailing.json`、`test_report_spacing.py` に 0400）

### Phase 4 の知見（担当 D、2026-10-21）

- commit：中間帯鉄筋 8678729、計算と入力 8b6109f、計算書 343540c、出力項目と登録 cc58684、参照先の番号 14aa61f、エディタのテスト bfd0c24・03679ea（ブランチ `sasa/0400-detailing`）。
- （事実）品質ゲート（bfd0c24 の時点、2026-10-21）：カバレッジは全層が下限以上（core・inputs・loadmodel・calc・export・pipeline 100%、reporting 99.25%、gui 96.5%）。失敗は受入テスト（`tests/acceptance`、入力の SHA が受入記録と合わない。sasa/glp の HEAD でも同じ）と `test_gui_rebar_edit.py` の1件（03679ea で直し、そのファイルは通る）。pre/input.json を変えたので、受入を取り直すときはこのブランチの pre/input.json で行う。
- （事実）0400 だけを true にした生成を2回行い、PDF・方眼Excel が同じバイト列（PDF 17頁）。Excel 比較（`test_grid_excel.py -k 0400`）も通る。

- （事実）計画書の「知見」の「見本 0400 の柱は current.json の柱と同じ配筋（D32・29本…）」は誤り。見本 0400 の柱は 3940×1700、D38（線路の面 16本・直角の面 13本で隅を共有、計54本＝61560.0 mm²）、帯鉄筋 D22 線路 10本・直角 6本 ctc150、f'ck 24。見本の値との照合は、その柱とフーチング（H6 1.8、線路 上 D32@150・下 D29@150、直角 D16@200）に合わせた入力で行った（`test_detailing.py: sample_document`）。
- （事実）見本の誤りで再現しないもの：(1) 6) の b＝1140（2.264%。同じ見本の 8) は 3871/(3940×150)＝0.655%）、(2) の `#REF!`、フーチングに柱の N'd と柱のあきの規定、7) の「小判形」の文、9) の崩れた f'cd の行、フーチングの 6) の 794・1.16組。フーチングの 9) は見本 0.126（丸める前の pw）に対し、印字した pw 0.00599 から 0.127（ADR-0003）。
- （事実）参照先の節の番号は担当 C の R5 切替（`sasa/0400-r5` eca5fcd）の番号を 0400 側の表に書いて固定した（`reporting/stages/detailing.py: COLUMN_SECTIONS`・`FOOTING_SECTIONS`・`CANTILEVER_SECTIONS`・`references`、テスト `test_detailing_report.py`）：柱 8.10・8.7／9.10・9.7、フーチング 12.5・12.3（0810）／12.9・12.7（0820）、梁 13.8・13.5（外観の照査ありで 13.9・13.5）。節の名前は「最小鉄筋量及び最大鉄筋量」「耐久性の照査」。0910 の番号のため、0400 は `片持ち梁の照査.外観の照査` も要る（空欄は入力エラー）。番号の付け方を共有の関数にするかは統合で決める（オーケストレーター）。
- （事実）current.json・pre/input.json（Example2）は梁の上側の段のあき 32 mm＜4/3×25＝33.3 mm で 0400 が not_ok になる（Ex2 6.11 は段のあきを照査していない）。ほかの項目はすべて OK。
- （事実）見出しと出典が1行に入らない (b)・(c) は、出典を本文の末尾に置いた（Ex2 6.3(2) の書き方）。6) の2つの出典は列14 から。
- （推定・要確認）条文番号は見本どおり印刷した。R5 の番号は手元で確かめられない（Capacita にも R5 の条文の記載がない）。一覧は最終報告に書いた。


## Phase 5　GridLayoutPdf：ベクター PDF の図（担当 B）

- [ ] 部品の API を決めてこの計画書に書く（E が使う）
- [ ] 実現の方法と xlsx の描き方を DESIGN.md で決める。決定的なバイト列
- [ ] テスト、commit
- [ ] Release（tag・wheel、`SOURCE_DATE_EPOCH=315532800`）、WebPier の url・`uv lock`（オーケストレーター）

## Phase 6　配筋図（担当 E）

- [ ] 依存 `ezdxf>=1.4,<2`、`dependency_hashes` に ezdxf
- [ ] `webpier/export/drawing/`：作図道具（画層・文字スタイル・寸法スタイル・`dxf_bytes`・`pdf_bytes`）
- [ ] 柱の水平断面・梁の柱前面の断面・フーチングの断面
- [ ] `post/配筋図.dxf`（付帯JSON）、4.1 に Phase 5 の部品で図ごとの PDF
- [ ] テスト（DXF の円・文字・`audit()`・決定的、PDF 1頁・決定的）、PNG で目視、`.gitattributes` に `*.dxf -text`

## 検証（オーケストレーター）

- [ ] WebPier の品質ゲート `& ".claude/check.ps1"`
- [ ] Capacita の `.claude/check.ps1`
- [ ] GridLayoutPdf のテスト
- [ ] 0400 だけを true にした生成で `output/0400_照査の前提.pdf`・`export/0400_照査の前提.xlsx`・`post/配筋図.dxf`、2回で同じバイト列、見本と並べて目視
- [ ] structural-mcp の `npm test`・`npm run smoke:webpier`、サブモジュールのポインタ

## 知見

- （事実 2026-10-21）`pre/input.json` のフーチングは下面の配筋とスタラップだけで、上面は空欄。`tests/fixtures/inputs/current.json` のフーチングの配筋はすべて空欄。
- （事実 2026-10-21）見本 0400 の柱は current.json の柱と同じ配筋（D32・29本・ピッチ150、帯鉄筋 D22 ctc150）だが、f'ck は見本 24、入力 27。見本の 0.008Ac の値（Ac 524690.5）は f'ck 24・SD390・γb 1.3・γi 1.0、Ac＝γi·γb·N'd/(k1·f'cd＋0.008f'yd)、k1＝min(1−0.003f'ck, 0.85) で再現する（手計算）。
- （事実 2026-10-21）見本 0400 のフーチングの配筋（線路 下側 D29-6.67 など）は `pre/input.json`（線路 D25@125、直角 D29@125）と違う。0400 のフーチングの値は手計算か見本の値の入力で確かめる。
- （事実 2026-10-21）0611 の WebPier の頁（`reporting/stages/column_check.py:118-250`）は H16 の方法（σb≦σbl の流れ図、k4 を含む Wd の式、環境条件の文）を書いている。
