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

- [x] ✅ 失敗する回帰テスト（`WebDanforCS/tests/UiTests`）：R5 の行8 の WDJ で 0.008Ac の行と最大鉄筋量の表。見本 0400 の手計算：N'd 7592.8 kN、f'ck 24、SD390 → Ac 524690.5 mm²、0.008Ac 4197.5 mm²、pb 1.750%（σ's＝0）
- [x] ✅ `CalcResult_BendingReBarAmount.cs`：(c) 0.008Ac（k1 は `CalcResult_BendingDestruction.cs` の N'oud のものを共用）と最大鉄筋量（pt＝Ast/(b·d) ≦ 0.75pb、σ's は釣合状態のひずみから）
- [x] ✅ `RailR5_Bending_ReBarAmount_Ver.cs`・`RailR5_BendingReBarAmountPrinter.cs` を R5 用に。節 ID `bending_rebar_amount` は変えない。H16 は変えない
- [x] ✅ `.claude/check.ps1`（exit 0、`overall: pass`。edee272・f385359 で直した後）、README（run-rc）、スキル structural-capacita
- [x] ✅ Release ビルド（structural-mcp のルートで `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release`）、Capacita で commit（`sasa/r5-rebar-amount` 5104588、push なし。ルートのポインタは未更新）

### Phase 2 の知見（2026-10-21、Capacita 5104588）

- （事実：コードと本物の Release runner）R5 系（id 3 R5_Rail・4 R5_Shinkansen・8 R5_JREast）の `bending_rebar_amount` は、同じ節に2つの表を新しいページから印刷する。
  - 「最小鉄筋量の照査結果」：H16 と同じ Mcrd/Myd の行のあとに、N'd・f'ck・γc・f'cd・f'yd・kc・γi・γb・Ac・0.008Ac・As・0.008Ac/As、最後に照査結果（Mcrd/Myd と 0.008Ac/As の両方が OK で OK）。行が多いので PDF では2ページ（Part 1・2）になる。
  - 「最大鉄筋量の照査結果」：共通の行（f'ck・f'cd は ρm を掛けない値）、γc・γs・fsyd・Es、0.88−0.004f'ck・α・(155−f'ck)/30000・ε'cu・εsy、N'd・b・d・xb・ε's・σ's、pb・0.75pb・pt、pt/0.75pb、照査結果。脚注「pt=Ast/(b･d)」。
  - 強度の低減係数の記号は kc（見本 0400 と Capacita の N'oud の表に合わせた。計画の k1 と同じもの）。H16 系の表は変わらない（テストで確認）。
- （事実：コード）固定の係数：γi 1.0・γb 1.3・γc 1.3・γs 1.0（WDJ の安全係数は使わない。行8 の Mcrd 側の γc 1.0・γs 1.0・γb 1.1・ρm 1.3 も従来どおり固定）。N'd は行8 の断面力の最大圧縮を部材数で割った値（引張なら 0、軸力の考慮方針 `axisforce_condition` によらない。N'oud と同じ）。f'ck は ρm を掛けない値（杭の低減は N'oud と同じく掛かる）。As は側方鉄筋を含む全軸方向鉄筋（N'oud と共用の `Analyze_Noud.AxialBarTotals`）。f'yd・fsyd は引張鉄筋の fsy、σ's の上限は圧縮鉄筋の fsy。b は換算矩形の幅（T形はウェブ幅）、d は引張鉄筋の有効高さ、d' は圧縮鉄筋の縁端距離（表の dsc）。
- （事実：本物の Release runner、`WebDanforCS/tests/WdjForTest/R5RebarAmountColumn.wdj`：B 3940・H 1700・D38-16 を 141.6、行8 Md 1150.0・Nd 7592.8）N'd 7592.8、Ac 524690.5、0.008Ac 4197.5、As 18240.0、pb 1.750 %、0.75pb 1.313 %、pt 0.297 %、`reportSections` は `bending_rebar_amount` 1〜3 ページ。手計算と一致。圧縮鉄筋 D38-16 を 141.6 に足すと σ's＝390.0（f'syd で頭打ち）、pb 2.047 %。600 に置くと σ's 280.3、pb 1.964 %（テストで確認）。
- （事実：テスト）Nd＝0（フーチング）でも落ちない：N'd 0.0、Ac 0.0、0.008Ac 0.0、0.008Ac/As 0.000 ≦ 1.0 で OK、pb は N'd の項なし（例の断面で 2.067 %）。Nd 45000 kN では 0.008Ac 24877.3 > As で NG、pb 0.188 % で最大鉄筋量も NG。
- （事実：本物の Release runner）`--pickup` でも動く：PickupColumn.wdj を R5_Rail にし、`pickup_moment` の id 8 の `no` を 3 にして取り込むと `bending_rebar_amount` が 13〜15 ページに出る。行6 は `bending_restorability`（10 ページ）・`shear_restorability` に出る。
- （事実：コード）行6 の名前：R5 系の行6 は `RailR5_*_ServiceabilityDamage`（JR東日本は `JREastR5_*_Restorability`）で、節 ID は `bending_restorability`・`shear_restorability`・`torsion_restorability`、見出しは「使用性（損傷）曲げモーメントの照査結果」「使用性（損傷）せん断力の照査結果」「使用性（損傷）ねじりモーメントの照査結果」（`RcDan/Translation/ja.json` の `*-restorability-R5`、印刷は `Printers/VerificationResultPrinters/RailR5/RailR5_BendingRestorabilityPrinter.cs` など、節 ID の対応は `VerificationResultPrinter.cs` の配列の位置）。行7 は `*_restorability_eq`「復旧性（損傷）…」。
- （事実：コード）R5 の耐久性（C が WebPier の説明の頁を書き直す根拠）：
  - 節と見出しは H16 と同じ `bending_durability`「耐久性　曲げひび割れの照査結果」・`shear_durability`「耐久性 せん断ひび割れの照査結果」。表の環境の行は「水掛かりの程度」（常時乾燥・乾湿繰返し・常時湿潤、`RailR5_BendingDurabilityPrinter.cs:30-36`、`crack[].con_u/con_l/con_s` の 1・2・3 を `CommonDataClass.cs:1881` の `ConvertToEnvType` が Dry・WetDryCycle・Wet に）。
  - 流れ（`CalcResult/CalcResult_BendingCrack.cs:175-226`）：永久作用で σc ≦ 0.4f'cd（311行目）→ 省略判定：σct（永久＋変動の縁引張応力度）≦ σbl（RcSolver の値、なければ `ConcreteInformation.GetSigmaCtl` の表）かつ σs（永久作用の鉄筋応力度）≦ σsl なら省略。R5 は σct OK・σs NG でも「省略不可」としてひび割れ幅を計算する（H16 は「省略判定外」で NG、`CalcResult_BendingCrack.cs:620-645`）。運輸機構は pt > 0.5 % なら省略不可。
  - ひび割れ幅（`CalcResult_BendingCrack.cs:814`）：Wd＝1.1·k1·k2·k3·k4·{4c＋0.7(cs−φ)}·(σse/Es＋ε'csd)。H16 と同じ式で、**R5 でも `crack[].k4` が掛かる**（k1 異形 1.0、k2＝0.7＋15/(f'cd＋20)、k3 段数、c は 1段目のかぶり（運輸機構は 100 上限）、ε'csd は `crack[].ecsd_u/ecsd_l`、JR東日本は k3＝1 と ε'csd 150/300 の自動）。表に k4 の行がある（`RailH16_BendingDurabilityPrinter.cs:207`、R5 はこの表を継承）。
  - 制限値（`General/InformationGetter.cs`）：σsl（曲げ）・σsl2（せん断）とも常時乾燥 140・乾湿繰返し 120・常時湿潤 140 N/mm²（125-180行目）。Wlim は常時乾燥 0.005c、乾湿繰返し・常時湿潤 0.004c（c は 100 上限、352-375行目）。
  - せん断の耐久性（`CalcResult/CalcResult_ShearCrack.cs`）：Vcd の 0.7 倍で省略判定（341行目）、せん断補強鉄筋の応力度 σwpd（kr＝`crack[].kr`）≦ σsl2（590-610行目、R5 では σsl と同じ値）。
- （事実）Capacita の `.claude/check.ps1` を通した（2026-10-21、Capacita の `sasa/r5-rebar-amount` は 5104588 → edee272 → f385359、push なし）。最後の実行は exit 0・`overall: pass`、ログ `Capacita/.claude/logs/check-20261021T044331709Z-11700.log`：scope-isolation・agent pytest（17件）・repository detector・STATE/DESIGN contract・`git diff --check`・live references・SteelDan.Tests（160件）・desktop-ui-tests（595件）・desktop-build がすべて pass。
  - edee272：b8db0ad で `.agents` を `.claude` に移した残り。check.ps1（オーケストレーターの置換を含む）・`repository.toml`（テストの結果の置き場は `.claude/logs/check-tests`）・`.claude/tests`・`.claude/skills`・`.claude/rules` の `.agents` を `.claude` に直した（`docs`・`checkpoints` の記録は直していない）。check.ps1 はコマンドを PATH の最初の一致で起動するようにした（git が PATH に2つあると `Get-Command` が配列を返し、pytest の子プロセスから `git diff --check` が起動できなかった）。空だった `AGENTS.md` に短い Codex の契約を書いた（repository detector は空の AGENTS.md を `agents_md` の不正として exit 2 にする）。
  - f385359：UiTests の 15 件の「Must not change font resolver after is was once used.」は、RcDan を直接 PDF で呼ぶテスト（`ReportSectionsTests`・`R5RebarAmountTests`）が先に走ると RcDan の `JapaneseFontResolver` が使われ、その後の `CalculationCoordinator` の `SharedPdfFonts.EnsureInitialized` が替えられずに落ちていた（テストの順序で出たり出なかったりした）。テストのアセンブリの `[ModuleInitializer]`（`WebDanforCS/tests/UiTests/TestAssemblyInitializer.cs`）でデスクトップのアプリと同じく SharedPdfFonts を先に入れる。製品のコードは変えていない。回帰テスト `PdfFontResolverTests`（RcDan の PDF を直接作ってから coordinator で計算）は、直す前に単独で2回とも落ち、直した後は R5RebarAmountTests・ReportSectionsTests・Steel*・LegacyCalculationWorkflowTests・InputCalculationBaselineTests をまとめた実行と全件で通る。
  - 残る不安定さ（事実）：クリップボードを使う UiTests（`InputSpreadInventoryTests`・`LegacySteelUiSurfaceTests`・`RcShearInteractionTests`・`WebDanParityTests`・`SteelWorkspaceControlTests` などのいずれか）が、全件の実行で 1〜3 件「要求されたクリップボード操作に成功しませんでした」やクリップボードの中身が空になって落ちることがある。アセンブリは並列実行を止めている（`WebDanParityTests.cs:13`）ので、同じ PC の別のプロセス（並行するほかの作業のテストなど）がクリップボードを使うためと推定。落ちたテストは単独で再実行すると pass。ゲートは1回目がこの1件で exit 2、2回目が pass。
  - Release の runner は 5104588 のビルドのまま（edee272・f385359 は `.claude`・AGENTS.md・テストだけで、RcDan・Headless を変えていないので再ビルドしていない）。
- （事実）総括表 `summary.xlsx` と検討結果一覧 `safety_ratios` の最小鉄筋量は今も Mcrd/Myd だけ（0.008Ac と最大鉄筋量は計算書の表にだけある）。WebPier が判定を計算書から読まないなら影響はない（推定）。
- （事実）スキル structural-capacita（structural-mcp の `skills/structural-capacita/SKILL.md`）を直したが、structural-mcp のルートでは commit していない（オーケストレーターが行う）。

## Phase 3　WebPier：行8 と新しい節（担当 C、A の後）

- [ ] `calc/column_check.py`：`MOMENT_CASES` に (8, PERMANENT)、`REPORT_SECTIONS` の末尾に `bending_rebar_amount`
- [ ] `reporting/stages/column_check.py`：n.10「最小鉄筋量及び最大鉄筋量」、`foundation_check.py`：8.10・9.10 → 8.11・9.11
- [ ] `export/capacita/footing_wdj.py`：行8 に 0800 の `long_term`（Nd＝0）、0810/0820 の節の最後に差込み
- [ ] `export/capacita/cantilever.py`：行8 にケース 28、0910 の節の最後に差込み
- [ ] 代役の runner が `bending_rebar_amount` を返す
- [ ] 本物の runner の受入を取り直す：`accept_capacita_column.py`・`accept_footing.py`・片持ち梁

## Phase 4　0400 の計算と計算書（担当 D）

- [ ] 出力項目 `detailing`：`inputs/outputs.py`、`pipeline/stages.py`（`OUTPUT_STAGES`、`StageSpec("0400", "0400_照査の前提", ...)`）、`gui/calculation_page.py`、`current.json`・`pre/input.json` の `outputs`、項目を数えるテスト
- [ ] `current.json`・`pre/input.json` にフーチング上面の配筋
- [ ] 中間帯鉄筋の配置（calc 層。E も使う）
- [ ] `webpier/calc/detailing/`：4.2 柱（1)〜9)）、4.3 梁、4.4 フーチング。印字桁で丸め、frozen dataclass
- [ ] `webpier/reporting/stages/detailing.py`：§4、4.1（図の場所。図は E）〜4.4、`grid_documents`
- [ ] 結果JSON と `engineering_status`
- [ ] テスト：見本の転記と独立の手計算、決定的なバイト列

## Phase 5　GridLayoutPdf：ベクター PDF の図（担当 B）

- [x] ✅ 部品の API を決めてこの計画書に書く（E が使う）（下の「API」）
- [x] ✅ 実現の方法と xlsx の描き方を DESIGN.md で決める。決定的なバイト列（GridLayoutPdf の DESIGN.md：FR-028、Key Decisions 2件、技術選定 pypdf）
- [x] ✅ テスト、commit（GridLayoutPdf `sasa/pdf-figure` の **f2e618b**、未 push。main 7d60e58 から）
- [ ] Release（tag・wheel、`SOURCE_DATE_EPOCH=315532800`）、WebPier の url・`uv lock`（オーケストレーター）

### 知見（Phase 5、2026-10-21、f2e618b）

- （事実）実現：`gridlayoutpdf/pdfpages.py` が pypdf で頁を読み、ReportLab の文書に form XObject として直接写す（1回の描画。後から pypdf で書き直さない）。BBox は CropBox、頁の内容は復号して連結し Flate で1本、Resources から辿れるオブジェクトは符号化のバイト列とフィルタのまま。オブジェクトの名前は PDF のバイト列の SHA-256 から作るので、同じ入力から同じバイト列（テストで2回の出力を比べた。ezdxf の `PyMuPdfBackend` の PDF でも同じ）。
- （事実）依存：GridLayoutPdf の実行時の依存に **pypdf>=6,<7** を足した（必須。extra にしない）。ストリームの生のバイト列を pypdf の `StreamObject._data` から取るので 6 系に固定。WebPier は既に `pypdf>=5,<7`（lock は 6.20.1）なので取り込みで衝突しない。GridLayoutPdf の lock は 6.21.1。
- （事実）テスト：新しい 3 ファイル（`tests/unit/test_pdf_figure.py`・`test_pdf_figure_xlsx.py`・`tests/integration/test_pdf_figure_pdf.py`、計74件）。全件 3910 passed・2 failed・4 xfailed、製品のカバレッジ 98%。失敗の2件は main（7d60e58）でも同じ：Excel COM の `test_fit_scale_..._without_much_spare[a3-tall-pages]`（プリンター依存）と、作業ツリーが CRLF（`core.autocrlf`）の `tests/fixtures/cantilever_p01_37/render.py` の SHA-256 で落ちる片持ち梁の golden（commit の LF のバイト列は manifest と一致）。`.claude/check.ps1` も main から PowerShell 5.1 の文字化けで design-doc が false（`validate_doc.py` を直接動かすと ok）。
- （事実）ezdxf の PDF の日本語：試しに ezdxf の既定の設定で「配筋図」を描くと、PDF の時点で豆腐（□）になった（PdfFigure ではなく ezdxf の書体の設定の問題）。E は文字スタイルに日本語の書体を設定すること。
- Release の注意（オーケストレーター）：CLAUDE.md の手順どおり、f2e618b を main に入れて版を上げ（今 0.2.1）、`git -c core.autocrlf=false clone` した木で `SOURCE_DATE_EPOCH=315532800` の `uv build --wheel`（GridLayoutPdf の DESIGN.md の決定では v* タグの push で GitHub Actions が作る）。wheel の依存に pypdf が入るので、WebPier の `uv lock` で pypdf の制約（>=6,<7）が効く。

### API（GridLayoutPdf `sasa/pdf-figure`、2026-10-21）

```python
from gridlayoutpdf import PdfFigure   # 低水準の描画命令は VectorPage

PdfFigure(col_span, rows, data, *, page=0, preview=None, align="center", valign="middle", block_id="")
```

- `col_span`・`rows`：枠のマス数（正の整数。`Figure`・`Image` と同じ）。枠の幅が利用幅を超えれば計測時に `LayoutOverflowError`。分割しない（1つの part、`keep_together`）。`QuarterTurn` には入れられない（`ValueError`）。
- `data`：PDF のバイト列（`bytes`・`bytearray`・`memoryview`。作った時に `bytes` に固定）。`page` は 0 から数える頁。
- 枠の規則：頁の表示範囲（CropBox、なければ MediaBox）を、縦横比を保って枠に内接するよう**拡大・縮小**し、`align`（left/center/right）・`valign`（top/middle/bottom）で寄せる。既定は中央。CropBox の外は切り取られる。注釈・フォームは描かない。
- PDF：頁の内容を1つの form XObject にして `Do` で描く（ベクターのまま。文字が線ならそのまま線）。同じ `data` の同じ頁を何度置いても PDF には1つだけ書く。`render_pdf(..., invariant=True)`（WebPier の生成と同じ）で同じ入力から同じバイト列。
- 方眼Excel：ベクターの頁を持てないので、`preview`（同じ図の **PNG か JPEG** のバイト列）を同じ箱に画像として置く。`preview` の画素数の縦横比は頁の縦横比と各軸 ±0.5 pixel で合うこと（合わなければ `ValueError`）。`preview` がなければ枠線だけを置き、`XlsxResult.fallbacks` に `pdf_figure_frame` を記録する。**WebPier は `render_xlsx(..., strict=True)` なので、`preview` がないと `XlsxStrictError` で止まる。必ず渡す。**
- 例外（作った時に `ValueError`、`block_id` を前に付ける。`block_id` が空なら `PdfFigure: `）：PDF として読めない（`not a readable PDF`）、暗号化、その頁がない（`has no page N`。頁のない PDF も）、頁が回転している（`/Rotate` が 0 でない）、表示範囲の面積が 0、`page` が負・整数でない、`preview` が読めない・PNG/JPEG でない・縦横比が違う、`align`・`valign` が選択肢にない。
- 例（E）：`PdfFigure(30, 20, pdf_bytes, preview=png_bytes, block_id="配筋図_柱")`。`pdf_bytes`・`png_bytes` は同じ `layout.Page` で ezdxf の `PyMuPdfBackend` の `get_pdf_bytes` と `get_pixmap_bytes(fmt="png", dpi=...)` から作れる（縦横比は同じ頁なので合う）。

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
