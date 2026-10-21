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
| 水掛かりの値（2026-10-21 の2回目の回答） | 旧入力の 一般の環境→常時乾燥、腐食性環境→乾湿繰返し で確定（柱 常時乾燥、片持ち梁 上面・側面 乾湿繰返し・下面 常時乾燥） |
| Wd の照査式 | Capacita の R5 に合わせ「Wd / Wlim ≦ 1.0」（γi を外す）。σsl1・σsl2 の記号、k4 0.85、使用性（損傷）のせん断の説明（Vyd）、ねじりの ftd の説明は今のまま |
| Example橋脚2 の梁の段のあき | 32mm ＜ 4/3Dmax 33.3mm で NG のまま印刷する（入力も規則も変えない。例題の 0400 は not_ok） |
| 0400 の未確認の条文番号 | 見本どおりのまま。未確認の一覧は Phase 4 の節に残し、R5 の本文で確かめたら直す |

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
- [x] ✅ 決定48・54・59・60 の「H16」と節番号（8.10・9.10 → 8.11・9.11）を直す（各決定に「決定73で改めたこと」）。決定72 の出力項目の表に `detailing`（13項目）、決定73 に実装で決まった細目（担当 F、2026-10-21）
- [x] ✅ README・CLAUDE.md・CONTEXT.md（フーチングの断面照査に最小鉄筋量・最大鉄筋量、水掛かりの程度のフーチング、使用性（損傷）のねじり）（担当 F）
- [x] ✅ スキル：webpier-capacita・webpier-cantilever・webpier-footing・webpier-foundation・pier-report-style（WebPier）、structural-capacita（structural-mcp の `sasa/glp`）、structural-webpier（structural-mcp の `sasa/webpier-outputs` で書き、ルートの sasa/glp に取り込み済み）（担当 F）
- [x] ✅ 配筋図の組み込み（89857d0）に合わせて、README・CLAUDE.md・決定73・pier-report-style・structural-webpier の「Release の後」「未実装」を実装済みの記述に直し、帳票の基準の GridLayoutPdf の版（共通グリッドは 0.2.0 で導入、lock は v0.3.0）、フーチング上側の芯 79・104 を合わせた（担当 F、2026-10-21）

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
- （統合後 2026-10-21、bb4a2cf の上で）入力（D の `outputs.detailing` とフーチング上面の配筋）が変わったので、受入をすべて取り直した：`check_frameweb_headless.py`、`accept_foundation_check.py 0612/0622`、`accept_jrsnap_ndu.py`、`accept_jrsnap_figures.py`、`accept_aggrese_project.py --batch <絶対パス>`、`accept_aggrese_report.py`、`accept_capacita_column.py 0611/0621`（0.132／0.114、Mud 37426.2、Myd 38200.7／0621 Mud 29326.7、Myd 48634.5）、`accept_footing.py`（accepted）。
- （決め、オーナー 2026-10-21）曲げひび割れ幅の照査式は Capacita に合わせて「Wd / Wlim ≦ 1.0」（γi とその定義を消した。0611/0621・0810/0820・0910、流れ図も）。σsl1・σsl2 の記号、k4 0.85、使用性（損傷）のせん断の解説、ねじりの ftd は今のまま。水掛かりの値の対応（柱 常時乾燥、片持ち梁 上面・側面 乾湿繰返し・下面 常時乾燥）は確定。
- （統合後）0400 が参照する節番号を、それを印刷する帳票の定数から作るようにした（重複を消した）：`column_check.DURABILITY_SECTION`・`REBAR_AMOUNT_SECTION`（7・10）、`footing_check.DURABILITY_SECTION`・`REBAR_AMOUNT_SECTION`（`Chapter.section` の 1・3）、`cantilever_check.Numbering.with_appearance(appearance)`。`detailing.references` はこれらを読む（reporting 同士の import）。
- （事実、失敗の記録）一度 `footing_check` に `DURABILITY` という名前で節の位置を足したところ、限界状態 id の `DURABILITY`（0）を上書きして `_factors` が StopIteration になり、`accept_footing.py` が落ちた。名前を `*_SECTION` に変えて直した（commit 前）。
- （最後の統合後 2026-10-21、89857d0 の上で）入力（フーチング上側の芯かぶり 79・104 など）が変わったので、受入をすべて取り直した：FrameWeb・基礎 0612/0622・JRSNAP の NDU と図・Aggre-SE のプロジェクトと計算書・柱 0611/0621（0.132／0.114、Mud 37426.2、Myd 38200.7／0621 Mud 29326.7、Myd 48634.5）・フーチング（accepted）。

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

- [x] ✅ 部品の API を決めてこの計画書に書く（E が使う）（下の「API」）
- [x] ✅ 実現の方法と xlsx の描き方を DESIGN.md で決める。決定的なバイト列（GridLayoutPdf の DESIGN.md：FR-028、Key Decisions 2件、技術選定 pypdf）
- [x] ✅ テスト、commit（GridLayoutPdf `sasa/pdf-figure` の **f2e618b**、未 push。main 7d60e58 から）
- [x] ✅ Release（tag・wheel、`SOURCE_DATE_EPOCH=315532800`）、WebPier の url・`uv lock`（オーケストレーター）：GridLayoutPdf main 85b0389 を v0.3.0 にしてタグと push、Actions の Release の wheel（sha256 a6e1c8eb…bc）を手元で同じバイトに再現、WebPier 107ca10

### 知見（Phase 5、2026-10-21、f2e618b）

- （事実）実現：`gridlayoutpdf/pdfpages.py` が pypdf で頁を読み、ReportLab の文書に form XObject として直接写す（1回の描画。後から pypdf で書き直さない）。BBox は CropBox、頁の内容は復号して連結し Flate で1本、Resources から辿れるオブジェクトは符号化のバイト列とフィルタのまま。オブジェクトの名前は PDF のバイト列の SHA-256 から作るので、同じ入力から同じバイト列（テストで2回の出力を比べた。ezdxf の `PyMuPdfBackend` の PDF でも同じ）。
- （事実）依存：GridLayoutPdf の実行時の依存に **pypdf>=6,<7** を足した（必須。extra にしない）。ストリームの生のバイト列を pypdf の `StreamObject._data` から取るので 6 系に固定。WebPier は既に `pypdf>=5,<7`（lock は 6.20.1）なので取り込みで衝突しない。GridLayoutPdf の lock は 6.21.1。
- （事実）テスト：新しい 3 ファイル（`tests/unit/test_pdf_figure.py`・`test_pdf_figure_xlsx.py`・`tests/integration/test_pdf_figure_pdf.py`、計74件）。全件 3910 passed・2 failed・4 xfailed、製品のカバレッジ 98%。失敗の2件は main（7d60e58）でも同じ：Excel COM の `test_fit_scale_..._without_much_spare[a3-tall-pages]`（プリンター依存）と、作業ツリーが CRLF（`core.autocrlf`）の `tests/fixtures/cantilever_p01_37/render.py` の SHA-256 で落ちる片持ち梁の golden（commit の LF のバイト列は manifest と一致）。`.claude/check.ps1` も main から PowerShell 5.1 の文字化けで design-doc が false（`validate_doc.py` を直接動かすと ok）。
- （事実）ezdxf の PDF の日本語：試しに ezdxf の既定の設定で「配筋図」を描くと、PDF の時点で豆腐（□）になった（PdfFigure ではなく ezdxf の書体の設定の問題）。E は文字スタイルに日本語の書体を設定すること。
- （事実 2026-10-21）0400 の 4.4「鉄筋のあき」の3行結合セルが PDF で約半行（7.74pt）下がる件は **WebPier の組み方**が原因で、GridLayoutPdf は直さない。`reporting/stages/frame_report.py: _cell` が `first_baseline=CELL_BASELINE + (rows - 1) * PITCH_Y / 2` で行の中央へ先に寄せ、その CellLines（3行の結合では高さ2行）を GLP の `Cell(valign="middle")` がもう一度中央へ寄せるので二重になる。GLP の最小の表で確かめた：今の式で基線 34.55pt、`first_baseline=CELL_BASELINE` だけなら 26.81pt（中の行の基線と同じ）で、方眼Excel はどちらも結合範囲の中央。結合2行は今の式でも合うが、3行は半行、4行は半行、5行は1行ずれる。直し方：`+ (rows - 1) * PITCH_Y / 2` を消す（`valign` は既定の middle のまま。今の式に `valign="top"` を足しても最小の表では PDF・方眼Excel とも中央になったが、中央寄せを WebPier と GLP の二か所で持つことになるので採らない）。結合3行以上の非見出しのセルがある他の表の PDF も同じく直る（期待値が変わり得る）。
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

- [x] ✅ 依存 `ezdxf>=1.4,<2`（1.4.5）、`dependency_hashes` に ezdxf・fontTools・pymupdf（bcb421a）
- [x] ✅ `webpier/export/drawing/`：作図道具 `sheet.py`（画層・MSゴシックの文字スタイル・寸法スタイル・`label`・`arrow_to`・`fan`・`chain`・`dxf_bytes`・`figure_bytes`）（bcb421a）
- [x] ✅ 柱の水平断面（中間帯鉄筋は D の `calc/detailing/ties.py` を 8678729 から取り込み）・梁の柱前面の断面・フーチングの断面（bcb421a）
- [x] ✅ `post/配筋図.dxf`（付帯JSON、`Export("dxf", "配筋図.dxf")`、役割 `0400.dxf`）、4.1 に GLP の `PdfFigure` で図ごとの PDF（preview は PNG）。`reporting/stages/detailing.py: figure_specs`（26 列・頁の縦横比で行数・最大 30 行）、`pipeline/stages.py: _drawings`（7fa0e00、GLP f2e618b が要る：今の lock の GLP 0.2.1 では import できない）
- [x] ✅ 組数は整数なら整数（D22-5組@150）、端数は印字桁（3.5組）。calc の stirrups を公開名に（`cantilever.check.beam_stirrups`、`footing_rebar.stirrups`）（7fa0e00）
- [x] ✅ フーチングの線路方向の鉄筋（切断面に平行）を径の幅の帯（2本の線）で描き、矢印を帯の外側で止める。直角方向は点と扇のまま。梁の段の芯の寸法（108・64、121）を右の隅に移し、左の側方鉄筋の連続寸法と重ならないようにした（0b4dc13）。sasa/glp を取り込み（d235edd、衝突は `reporting/stages/detailing.py` の import だけ）、0400 だけの生成2回で PDF・xlsx・DXF が同じバイト列、4.1 を PNG で目視（2026-10-21）
- [x] ✅ 0400 の Excel 比較（`tests/reporting/test_grid_excel.py::test_excel_prints_the_published_workbook_where_the_pdf_does[train-0400]`）：結合セルの二重の中央寄せを WebPier の `frame_report._cell` で直した（930cc30、Phase 5 の知見）。品質ゲートで合格
- [x] ✅ テスト `tests/export/test_drawing.py`（DXF の円・線・寸法と表記の文字・`audit()`・ハッシュの種によらない同じバイト列、PDF 1頁・PNG の縦横比・決定的）、PNG で目視、`.gitattributes` に `*.dxf -text`（bcb421a）

公開した関数（`webpier.export.drawing`）：

- `drawing_dxf(pier: PierInput) -> bytes`：3図（梁・柱・フーチング）を横に並べた DXF 1つ。図ごとに縮尺（`sheet.scale_for`：長辺が紙の上で 120mm に収まる最小の 1/20〜1/500）で文字と寸法を描き、図の上に「梁（柱前面の断面）　1:25」などの題。
- `drawing_figures(pier: PierInput) -> dict[str, tuple[bytes, bytes]]`：`FIGURES = ("梁", "柱", "フーチング")` の順に (PDF, PNG)。PDF は図1つを1頁に縮尺どおり（GridLayoutPdf の `PdfFigure(col_span, rows, data=PDF, preview=PNG)` にそのまま渡す）、PNG は同じ頁を 200 dpi・白地で（方眼Excel の preview）。
- 入力の空欄はパスを名指しした入力エラー（calc の関数が出す。外巻き帯鉄筋の径だけは export が `鉄筋.柱.column_hoops.enclosing_diameter_mm` を名指しする）。

知見（担当 E）：

- （事実 2026-10-21、bcb421a）ezdxf 1.4.5 の DXF のバイト列は、CLASSES 節の並び（LAYOUT と ACDBPLACEHOLDER）がプロセスの文字列ハッシュの種（PYTHONHASHSEED）で入れ替わる（`ClassesSection.add_required_classes` が `dxf_types_in_use()` の set を回す）。参考の EVピット部のスキルは「import の順」と書いているが原因は set。`dxf_bytes` で書く前に使っている型を名前順に `doc.classes.add_class` して固定した。テストは種 1・2 の子プロセスで同じバイト列を確かめる。
- （事実 2026-10-21、bcb421a）PyMuPdfBackend の `get_pdf_bytes()` は毎回ランダムな /ID を書く。`get_replay(...).doc.tobytes(no_new_id=True)` で /ID なしにして決定的にした（作成日時は書かれない）。PNG は同じ頁の `get_pixmap(dpi=200, alpha=False).tobytes("png")` で決定的。幅は切り上げで 1px 増えることがあるが（476pt → 1323px）、GridLayoutPdf の preview の検査（両軸 ±0.5px で同じ倍率がある）は通る（GLP f2e618b の `PdfFigure` を venv に入れて3図で確かめた。venv は lock の版に戻した）。
- （事実 2026-10-21）文字スタイル「MSゴシック」の font は `msgothic.ttc`。ezdxf のフォントマネージャーが MS Gothic を見つけ、PDF・PNG で日本語が出る（PNG で目視、テストは style と `has_font`）。書体が無い PC では ezdxf は黙って別の書体に替える（未対処、報告済み）。
- （事実 2026-10-21）WebPier の `.gitignore` の `export/` は `webpier/export/` と `tests/export/` の新しいファイルも無視する。新しいファイルは `git add -f` が要る。
- （推定）フーチングの直角方向の鉄筋は入力に始点がないので、ピッチで中央から振り分け、面の最も外側の段の芯の間に置いた。梁のスターラップは外周の1本だけを描き、有効本数は表記（組＝有効本数／2）で示す（中間の脚の位置は入力にない）。
- （事実 2026-10-21、7fa0e00）ezdxf 1.4.5 は import のときに home（`Path("~").expanduser()`）を引き、home のない環境（structural-mcp が headless runner を起動する PATH・SystemRoot・TEMP・TMP だけの環境）では RuntimeError で止まる（`tests/pipeline/test_headless.py::test_run_headless_py_in_a_minimal_environment` が検出）。`export/drawing/sheet.py: home()` が、home が決まらないときだけ USERPROFILE を一時フォルダーの下（`webpier-ezdxf`）にしてから ezdxf を読む。home のない子プロセスでも DXF・PDF・PNG は同じバイト列（テスト）。
- （事実 2026-10-21、7fa0e00）0400 だけを選んだ生成を2回行い、`output/0400_照査の前提.pdf`・`.json`・`export/0400_照査の前提.xlsx`・`post/配筋図.dxf` が同じバイト列。方眼Excel は strict で preview により通る。4.1 は (1) 梁が1頁目、(2) 柱・(3) フーチングが2頁目（19頁）。
- （事実 2026-10-21、7fa0e00）0400 の Excel 比較：4.4 の表「鉄筋のあき」の3行を結合したセル（フーチング（上側）など）の文字が、ライブラリの PDF では結合範囲の中央より半行下、Excel では中央に出る。統合版 bb4a2cf（図なし）でも dy 7.67〜7.70 pt（許容 7.74）で境目にあり、図で頁割りが変わると 7.75 pt で不合格になる（図そのもののずれではない）。D の表（結合セルの縦位置）か GLP の方眼Excel の対応で直す点（未対処）。
- （事実 2026-10-21）品質ゲート（bcb421a の前、(PDF, PNG) への変更の前）：3 failed・21 errors はすべて受入の入力の SHA の不一致（accept_capacita_column・accept_footing・accept_foundation_check・accept_jrsnap_ndu・accept_jrsnap_figures、pre/input.json は変えていない）、pipeline 99.93%（`pipeline/headless.py:221-222` の IO_ERROR）。export 100%。

## 検証（オーケストレーター）

- [x] ✅ WebPier の品質ゲート `& ".claude/check.ps1"`（2026-10-21、担当 C、sasa/glp 89857d0 の上の worktree C:\tmp\wp-r5）：exit 0、4314 passed（54分44秒）。カバレッジ core・inputs・loadmodel・calc・export・pipeline 100%、reporting 99.25%（下限 95）、gui 96.5%（下限 85）
- [x] ✅ Capacita の `.claude/check.ps1`（`sasa/r5-rebar-amount` f385359：`.agents`→`.claude` の参照の直し edee272、UiTests の書体リゾルバー f385359 の後で通し）
- [x] ✅ GridLayoutPdf のテスト（f2e618b：新しい74件を含め、落ちるのは main でも落ちる既存の2件だけ。Phase 5 の知見）
- [x] ✅ 0400 だけを true にした生成で `output/0400_照査の前提.pdf`・`export/0400_照査の前提.xlsx`・`post/配筋図.dxf`、2回で同じバイト列、見本と並べて目視（sasa/glp 89857d0、19頁、4.2 の参照 8.10・8.7）
- [x] ✅ structural-mcp の `npm test`・`npm run smoke:webpier`、サブモジュールのポインタ（2026-10-21、ルート sasa/glp：npm test 69/69。smoke は 0400・0500・0600・0610・0611・0612 を選んだ入力で exit 0、0400 の PDF・JSON・xlsx・`post/配筋図.dxf` は MCP と CLI で同じバイト列、違うのは他のプログラムのページを持つ 0610・0611 の PDF と付帯JSONだけ。ポインタは Capacita f385359・WebPier この commit）

## 知見

- （事実 2026-10-21）`pre/input.json` のフーチングは下面の配筋とスタラップだけで、上面は空欄。`tests/fixtures/inputs/current.json` のフーチングの配筋はすべて空欄。
- （事実 2026-10-21）見本 0400 の柱は current.json の柱と同じ配筋（D32・29本・ピッチ150、帯鉄筋 D22 ctc150）だが、f'ck は見本 24、入力 27。見本の 0.008Ac の値（Ac 524690.5）は f'ck 24・SD390・γb 1.3・γi 1.0、Ac＝γi·γb·N'd/(k1·f'cd＋0.008f'yd)、k1＝min(1−0.003f'ck, 0.85) で再現する（手計算）。
- （事実 2026-10-21）見本 0400 のフーチングの配筋（線路 下側 D29-6.67 など）は `pre/input.json`（線路 D25@125、直角 D29@125）と違う。0400 のフーチングの値は手計算か見本の値の入力で確かめる。
- （事実 2026-10-21）0611 の WebPier の頁（`reporting/stages/column_check.py:118-250`）は H16 の方法（σb≦σbl の流れ図、k4 を含む Wd の式、環境条件の文）を書いている。
