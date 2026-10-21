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

- [x] ✅ `export/capacita/wdj.py`：`BODIES` を R5 の id（JR各社→R5_Rail 3、運輸機構→R5_Shinkansen 4、JR東日本→R5_JREast 8）に。`_MOMENT_TITLES`・`_SHEAR_TITLES`・`_TORSION_TITLES` の行6 を「使用性（損傷）」に（0810/0820・0910 の WDJ も同じ表を使う）
- [x] ✅ `calc/column_check.py`：`SAFETY_FACTORS`・`JR_EAST_SAFETY_FACTORS` を WebDanforJS の R5 の既定値に。`environment_number` を水掛かり（1 常時乾燥、2 乾湿繰返し、3 常時湿潤）に
- [x] ✅ `calc/footing_check.py`（0810/0820）・`calc/cantilever/check.py`（0910）も同じ（同じ定数を使う）
- [x] ✅ 入力：`choices.WATER_EXPOSURES`（`CORROSION_ENVIRONMENTS` を置換）、`fields.py`・`parse.py`・`model.py`、GUI `gui/rebar_page.py` の `CHECK_LABELS`・`CANTILEVER_LABELS`、`current.json`・`pre/input.json`（`柱の断面照査`・`片持ち梁の照査` の水掛かりだけ）。後方互換なし
- [x] ✅ 名前「復旧性（損傷）／復旧性（地震時以外）」→「使用性（損傷）」：抽出ケース名（`calc/longitudinal/combinations.py`、FrameWeb の Pickup 名、`frame_report.EXTRACTION_NAMES`）、0610/0620 の組合せの表の 損傷 の列（`longitudinal.py`・`transverse.py` の `_CHECKS`）、片持ち梁の 19〜22（`LimitState.SERVICEABILITY_DAMAGE`「使用性(損傷)」、`ForceRow(6)`、組合せの表）、`loadmodel.contract.CantileverRow.SERVICEABILITY_DAMAGE`、柱の n.9 の見出し
- [x] ✅ 切り替える節の WebPier の頁：条文番号の触を外し（0800 の 13.6.3 は残す）、説明を R5 の方法に（下の知見）
- [x] ✅ R5 で行6 が返す節 ID を本物の runner で確かめた：`bending_restorability`・`shear_restorability` のまま。`REPORT_SECTIONS` は変えない
- [x] ✅ 省略のコード `pipeline.capacita.SKIPPED` を R5 の WD-1914〜1926 に、代役の runner（`skip` は WD-1919・WD-1914）・テストの期待値
- [x] ✅ 受入の取り直し（Phase 1 の範囲）：`check_frameweb_headless.py`、`accept_foundation_check.py 0612/0622`、`accept_jrsnap_ndu.py`、`accept_jrsnap_figures.py`、`accept_aggrese_project.py`、`accept_aggrese_report.py`。`accept_capacita_column.py`・`accept_footing.py` は Phase 3 の後に取り直す

### Phase 1 の知見（2026-10-21、担当 C）

- （事実、本物の runner）R5 の行6 の節 ID は `bending_restorability`・`shear_restorability`（`torsion_restorability`）のまま。Capacita の `VerificationResultPrinter.SectionIds` は基準によらず同じ並びで、R5 の行6 の印刷は「使用性（損傷）…の照査結果」。scratch で current.json の 0611/0621 を本物の FEMPython・Capacita（bin\Release、2026-10-18 ビルド）で生成して確かめた。
- （事実、本物の runner）R5 の断面力0による省略は info の WD-1914〜1926（`ErrorMessage_1000_1999.cs` の `ZeroForce_RailR5_*`、`ErrorHelper.ErrorZeroForce` の R5 の分岐。3基準とも同じ）。H16 の WD-1901〜1913 のままでは 0621 が「計算書の節が違います」で止まった。0621 は R5 でも `shear_durability`（WD-1919）と `bending_serviceability`（WD-1914）を飛ばす。
- （事実、本物の runner）0611 の R5 の値は H16 と同じ（安全性（破壊）γi·Md/Mud 0.132、使用性（損傷）γi·Md/Myd 0.114、Mud 37426.2、Myd 38200.7）。
- （事実、ソース）WebDanforJS の `default_safety_factor` は H16 と R5 で同じ値で、違いは行6 の名前だけ。今までの WebPier（見本 WDJ の値）との違い：T_rbt 行5・6・7 1.0→1.3、行2 1.0→空欄（null。RcDan は既定値を使う）、行7 の V_rbs 1.0→1.1。JR東日本の例外は行6 の γi 1.0（`result[3]`）。WDJ の V_rbv は RcDan では Vdd（と Vod）の γb（`OrganizedInput.cs:562` の S_Gamma_bd）で、Vwcd は Vcd の γb を使う（`CalcResult_ShearCapacityR5.cs:515`）。
- （事実、ソース）水掛かりの程度の値：`CommonDataClass.ConvertToEnvType` の R5 で con 1＝常時乾燥、2＝乾湿繰返し、3＝常時湿潤（空欄は常時乾燥）。σsl（曲げ）・σsl2（せん断）は 140・120・140、Wlim は 0.005c・0.004c・0.004c（`InformationGetter.cs`）。外観の照査は常に常時乾燥。
- （決め、担当 C）入力の値の置換：一般の環境→常時乾燥、腐食性環境→乾湿繰返し。H16 と曲げの制限値（Wlim 0.005c／0.004c、σsl 140／120）が同じになる対応で、常時乾燥は Capacita の R5 の既定。柱は常時乾燥、片持ち梁は上面・側面 乾湿繰返し、下面 常時乾燥。せん断の σsl2 は常時乾燥で 120→140 に変わる。雨掛かりの橋脚を乾湿繰返しとするかはオーナーの判断（未確認）。
- （事実、ソース）R5 の曲げひび割れの流れ（`CalcResult_BendingCrack.cs` `Analyze_WdOmit.Verify`）：σb≦σbl かつ σs≦σsl なら省略、それ以外はひび割れ幅 Wd を照査（H16 は σb≦σbl で σs 超過なら NG）。流れ図を R5 の形（σs≦σsl1 の判定を足し、Yes で「曲げひび割れ幅の検討を省略」）にし、方法の文を `column_check.CRACK_METHOD` に共通化（0611/0621・0810/0820・0910）。Wd の式（k4 を含む）は R5 も同じで、k4 は WebDanforJS の既定 0.85（`crack-settings.service.ts:57`、RcDan `DefaultValue.K4`）のまま。
- （事実、ソース）Vyd＝Vcd＋Vsd（`CalcResult_ShearCapacityR5.cs:509-511`、計算書は Vwsd・Vbsd）。柱と片持ち梁の解説の「Vyd = Vcd + Vwd + Vsd（Vsd：鉄骨部分）」を 0810/0820 と同じ「Vcd + Vsd（Vsd：せん断補強鋼材）」に直した。
- （事実、ソース）R5 の使用性（損傷）・復旧性（地震時）のせん断・ねじりは安全性（破壊）の計算を継承する（`RailR5_Shear_ServiceabilityDamage_Ver : RailR5_Shear_SafetyDestruction_Ver`、H16 の復旧性も同じ）。
- （決め、担当 C）0910 は R5 の名前に合わせて節を分けた：13.6 使用性（損傷）の照査（(1) 曲げ (2) せん断 (3) ねじり）、13.7 復旧性（地震時）の照査（外観の照査ありは 13.6 使用性・13.7 使用性（損傷）・13.8 復旧性（地震時））。見本は H16 の「13.6 復旧性の照査 (1) 地震時以外 (2) 地震時」。
- （事実）worktree では `accept_aggrese_project.py` の既定の `--batch`（`PROJECT.parent/Batch/...`）が `C:\tmp\Batch` を指すので、`--batch C:/Users/sasai/Documents/structural-mcp/Batch/Aggre-SE/Headless/bin/Release` を付けて取り直した。
- （確かめられない点）R5 の RC標準の本文は見ていない。σsl1・σsl2 の記号（Capacita の R5 の計算書は σsl1・σsl2 と印刷、コードの注記は「R5 では σsl」）、ひび割れ幅の照査式の γi（Capacita は Wd/Wlim で γi を掛けない。WebPier は見本どおり γi・Wd/Wlim、γi＝1.0）、R5 の k4 の有無、柱の使用性（損傷）のせん断の解説（Capacita は Vwcd も照査し γi·Vd/Vud を印刷するが、解説は見本どおり Vyd だけ）、0910 のねじりの解説の ftd＝1.25√f'cd（Capacita は ftk/γc＝0.23f'ck^(2/3)/γc）。

## Phase 2　Capacita：R5 の最小鉄筋量と最大鉄筋量（担当 A）

- [ ] 失敗する回帰テスト（`WebDanforCS/tests/UiTests`）：R5 の行8 の WDJ で 0.008Ac の行と最大鉄筋量の表。見本 0400 の手計算：N'd 7592.8 kN、f'ck 24、SD390 → Ac 524690.5 mm²、0.008Ac 4197.5 mm²、pb 1.750%（σ's＝0）
- [ ] `CalcResult_BendingReBarAmount.cs`：(c) 0.008Ac（k1 は `CalcResult_BendingDestruction.cs` の N'oud のものを共用）と最大鉄筋量（pt＝Ast/(b·d) ≦ 0.75pb、σ's は釣合状態のひずみから）
- [ ] `RailR5_Bending_ReBarAmount_Ver.cs`・`RailR5_BendingReBarAmountPrinter.cs` を R5 用に。節 ID `bending_rebar_amount` は変えない。H16 は変えない
- [ ] `.claude/check.ps1`、README（run-rc）、スキル structural-capacita
- [ ] Release ビルド（structural-mcp のルートで `dotnet build .\Capacita\WebDanforCS\Headless\WebDanforCS.Headless.csproj -c Release`）、Capacita で commit

## Phase 3　WebPier：行8 と新しい節（担当 C、A の後）

- [x] ✅ `calc/column_check.py`：`MOMENT_CASES` に (8, PERMANENT)、`REPORT_SECTIONS` の末尾に `bending_rebar_amount`
- [x] ✅ `reporting/stages/column_check.py`：n.10「最小鉄筋量及び最大鉄筋量」（見出しだけ。n.5 と同じ形）、`foundation_check.py`：8.10・9.10 → 8.11・9.11
- [x] ✅ `export/capacita/footing_wdj.py`：行8（Md8_Md・Md8_Nd）に 0800 の `long_term`（Nd＝0、点1）。`calc/footing_check.REPORT_SECTIONS` の末尾に `bending_rebar_amount`、帳票は節を1つ足す：0810 12.2〜12.5、0820 12.6〜12.9（`footing_check.TRANSVERSE` は `Chapter(12, 6)`）
- [x] ✅ 0910：`calc/cantilever/combinations.FORCE_ROWS` に `ForceRow(8, "最小鉄筋量", (曲げ,), _permanent)`（ケース 28）、`export/capacita/cantilever.py` は `MOMENT_ROWS` の Md8 にそれを書く、`calc/cantilever/check.SECTIONS` の末尾に `bending_rebar_amount`、帳票は最後の節 13.8（外観の照査ありは 13.9）。荷重モデル（`calc/generic/cantilever.py`）は行8 に行1（耐久性（永久荷重））の組合せを使う（`POOLED_AS = {8: 1}`。`loadmodel.CantileverRow` は変えない）
- [x] ✅ 代役の runner が `bending_rebar_amount` を返す（`--pickup` は 1 頁、断面力入力は行 Md8 から 3 頁。WD-408/409 は曲げ・せん断の行が欠けるときだけ）
- [x] ✅ 本物の runner の受入を取り直した：`accept_capacita_column.py 0611`・`0621`（`tests/fixtures/acceptance/capacita/record.json`・`record_0621.json`）、`accept_footing.py`（`tests/fixtures/acceptance/footing/record.json`・`input.json`）。片持ち梁の受入スクリプトはないので、scratch で current.json（footing 以外の出力項目）を本物の4つの runner で生成して 0910 を確かめた

### Phase 3 の知見（2026-10-21、担当 C）

- （事実、本物の runner、Capacita 5104588 の bin\Release）R5 の `bending_rebar_amount` は `--pickup`（0611/0621）でも断面力入力（0810/0820・0910）でも最後の節で 3 頁（最小鉄筋量の照査結果 2 頁、最大鉄筋量の照査結果 1 頁）。フーチングの Nd＝0 でも計算する（0.008Ac＝0、pt/0.75pb 0.089）。行8 を書くと 0910 の WD-408 は出なくなる（0810/0820 は他の空の行で出る）。R5 に最小鉄筋量の断面力0の省略コードはないので、`OMITTED` に入れない（省略不可の節）。
- （事実、本物の runner）受入：0611 は照査値 0.132／0.114、Mud 37426.2、Myd 38200.7（見本と同じ判定。H16 のときと同じ値）、0621 は Mud 29326.7、Myd 48634.5、省略は shear_durability・bending_serviceability。フーチングは許容差の範囲で accepted。
- （事実）0910 の生成（本物の FEMPython・JRSNAP・Aggre-SE・Capacita）で 13.6 使用性（損傷）→13.7 復旧性（地震時）→13.8 最小鉄筋量及び最大鉄筋量の順に Capacita の頁が入り、0611 は 8.10 の後に 3 頁、0612 は 8.11。
- （決め、担当 C）新しい節は見出しだけ（説明文なし）。見本に R5 の最小鉄筋量・最大鉄筋量の解説がなく、式と値は Capacita の頁にあるため（スキル pier-report-style の「見本にない説明文は足さない」）。
- （注意）0820 の節番号が 12.5〜12.7 から 12.6〜12.9 に、0910 の最後が 13.6 から 13.8（外観ありは 13.9）に変わった。0400（担当 D）の参照先、決定59・60、スキル webpier-footing・webpier-cantilever・webpier-capacita、structural-webpier の checks.md を合わせる必要がある。

## Phase 4　0400 の計算と計算書（担当 D）

- [ ] 出力項目 `detailing`：`inputs/outputs.py`、`pipeline/stages.py`（`OUTPUT_STAGES`、`StageSpec("0400", "0400_照査の前提", ...)`）、`gui/calculation_page.py`、`current.json`・`pre/input.json` の `outputs`、項目を数えるテスト
- [ ] `current.json`・`pre/input.json` にフーチング上面の配筋
- [ ] 中間帯鉄筋の配置（calc 層。E も使う）
- [ ] `webpier/calc/detailing/`：4.2 柱（1)〜9)）、4.3 梁、4.4 フーチング。印字桁で丸め、frozen dataclass
- [ ] `webpier/reporting/stages/detailing.py`：§4、4.1（図の場所。図は E）〜4.4、`grid_documents`
- [ ] 結果JSON と `engineering_status`
- [ ] テスト：見本の転記と独立の手計算、決定的なバイト列

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
