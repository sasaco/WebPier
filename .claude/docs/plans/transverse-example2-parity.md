## Implementation Plan: Transverse Example2 Parity

作成日: 2026-10-16 / slug: transverse-example2-parity / 状態: **✅ 数値実装・帳票体裁復元・検証・公開完了（最終公開2026-10-16 14:17:16 JST）**。13:22:23公開の数値修正版は、p3以降を未依頼の汎用表へ変更したためユーザー受入Failedとなった。追補Step7で見本の式・罫線・章立て・改頁へ復元し、原本との独立直接比較、p1/2 pixel不変、計算/入力/JSON不変、対象回帰を確認して12頁PDFを再公開した。従前の「全頁PNG目視PASS」は可読性・数値表示の検査であり、見本への体裁一致を保証しなかった経緯を残す。数値実装時の全体gate初回失敗は該当module再検証で解消し、全体再実行PASSとは区別する。

### Purpose

追補状況（2026-10-16）: **✅ Step8の帳票renderer整理・検証完了**。4条件のPDFバイト完全一致、入力非破壊、全63関数の型ヒント、全体pytestのbefore=pass/after=passを確認。Step1–7の公開成果物は維持。raw範囲gateは別担当の新規検証ログ1件を検出してexit2を返すため「gate全体PASS」とはしない。出典/SHAを照合した独立範囲監査では、本整理の無断範囲拡大なし。詳細はStep8の最終結果に記録。

.claude/docs/Example橋脚/output/0600_上部工反力.pdfを起点に作られた橋脚アプリを、具体的な.claude/docs/Example橋脚2/09_直角.pdfの非地震荷重定義でブラッシュアップする。シェルターはアプリに追加せず、既存の調整済み入力を維持して、シェルターを独立実装しなくても比較できる荷重・ケース体系・帳票を整える。**風荷重MのExampleとの差はオーナー承認済み許容差**とし、風の現H/Mを今回の修正で変えない。

橋脚用衝撃低減は線路方向計画C05と同様に保持する。材料、支点位置、列車の分担・係数、雪、ケース参照を修正する。構造解析・最大応答・断面照査、シェルター新機能、地震入力の削除は行わない。

#### 最終引継ぎ用の比較表

数値は力kN、MはkN・m。材料はf'ckがN/mm²、EcがkN/m²。N/H/Mは各荷重表の作用点における量で、構造応答ではない。旧値は初回比較snapshot、修正後は最終candidate-manifest.jsonの無係数基本作用を示す。旧の係数適用済み値や不成立な混合集計との倍率比較はしない。

| 項目 | 旧アプリ | 修正後 | Example2との差/判定 |
|---|---|---|---|
| D1 top N/M | 8299.52 / −4929.00 | 8299.52 / 0 | 原本8299.53 / 0。Nの0.01は上流丸め差として残る |
| D2 top N/M | 780.00 / −689.00 | 780.00 / 0 | 一致。C側に自身の位置を使用 |
| 雪 S2/S10/S30 | 0620基本ケースへ未接続 | N710 / 1140 / 1270、各M0 | 3確率すべて一致 |
| 列車 単線 | D2を率へ転記し正常な単線荷重が不成立 | 上下ともN567.39、M±1210.08 | 一致。上下を独立候補として保持 |
| 列車 複線 | N2793.82（上流係数適用済み値を再分担） | N1134.77、M0 | 無係数基本値が一致。分担/係数を一度だけ適用 |
| 車両横荷重 LF | H137.49 / M529.33（ρ適用済み） | H111.69 / M430.01 | 無係数基本値が一致。組合せで有効ρを一度適用 |
| 衝撃 単線/複線 | 単線不成立、複線809.20（重複分担） | 単線N171.70/M±364.43、複線N328.70/M0 | **原本N227.78/428.28とは一致要求しない**。C05の用途別橋脚低減を保持する承認済み差 |
| 風 列車あり H/M | 305.88 / 2124.36 | 305.88 / 2124.36 | Hは原本と同じ。原本M1001.33との差は承認済み許容 |
| 風 列車なし H/M | 611.75 / 4248.64 | 611.75 / 4248.64 | Hは原本と同じ。原本M2002.64との差は承認済み許容 |
| 材料 f'ck/Ec | 25 / 2.50×10⁷ | 現入力27 / 2.65×10⁷ | 一致。部位別入力とRcDan補間を使用し固定27にはしない |
| ケース/係数 | 基本24、Defineなし、組合せ28、抽出なし | 基本17、Define15、組合せ16、抽出8 | 全240係数セルと参照群が一致。荷重実体欠落・公開地震ケースを解消 |

出典: `tmp/pdfs/transverse-example2-20261016/`のexample/app PDF・result.json・比較記録、`tmp/transverse-example2-parity/candidate-manifest.json`。シェルターは追加していない。**全数値一致とは報告しない**。D1の0.01、橋脚衝撃低減、風Mを上表のとおり区別する。

### Scope

- New files: src/transverse_actions.py、transverse_example2_cases.py、transverse_report_example2.py、tests/fixtures/transverse_example2_cases.json、tests/test_transverse_example2_reference.py、test_transverse_example2_cases.py、test_transverse_example2_pipeline.py、専用帳票試験。
- Modified files: src/transverse_calculator.py、transverse_report.py、cli.py、関連tests/test_transverse_*.py、必要なREADME記述。transverse_combinations.pyとtransverse_report_style.pyは旧監査の固定表/旧描画として保持し、新定義/描画は別モジュールに置く。frame_model_report.pyは骨組図の描画のみ再利用し、既存固定注記の材料表は呼ばず共有ファイルも変更しない。
- Reuse/read-only: foundation_springs.py（0500正規値・方向指定）、longitudinal_design_conditions.py（既存部位別強度・RcDan Ec補間）、frame_model.py（形状/断面/剛域は不変）、reaction_calculator.pyのraw_reactionsとtrain.pier用途別衝撃係数、原PDF、旧xls oracle、実入力pre/input.json。longitudinal_actions.pyとlongitudinal_example2_cases.pyは現時点未実装のため依存先にしない。
- Dependencies: 現Python/pytest/ReportLab/PyMuPDF。実行時PDF/Excel読取り、新依存なし。
- Step7の追加範囲: `transverse_report_example2_loads.py`と`transverse_report_example2_cases.py`を専用描画helperとして新設し、`transverse_report_example2.py`と専用帳票試験を更新。計算モジュール・実入力・JSON・共有frame描画は不変。公開変更は0620PDFだけ。
- 保護対象: 進行中のlongitudinal-example2-parity.md実装・共有モデル・方向別支持ばね。git reset/checkout/restore/stash、一括format、無関係な成果物再生成をしない。現入力、原資料、旧oracleの書換え禁止。

### Implementation Steps

| Step | 内容 | 状況 |
|---|---|---|
| 1 | 計画作成、基準世代、独立原本fixture、所有契約 | ✅ 完了 |
| 2 | 支点・分担・材料・用途別荷重の修正 | ✅ 近接相殺I修正を含む専用27件＋旧回帰63件＝90件PASS |
| 3 | Exampleの17基本・15Define・16組合せ・8抽出 | ✅ 定義/検証実装、ケース63＋独立資料14＝77件PASS |
| 4 | 非地震帳票・全荷重実体・工学条件の表示 | ✅ 数値表示実装。先行17頁版の体裁受入FailedはStep7で復元済み |
| 5 | 独立数値・全定義・回帰・PDF視覚検証 | ✅ 最終対象計325件PASS/1skip、初回全体の10失敗は各module再検証で解消 |
| 6 | 世代確認、検証済み0620公開、引継記録 | ✅ 2026-10-16 13:22:23 JST公開、候補bytes/公開後SHA一致 |
| 7 | 帳票体裁復元：p1/2保持、p3以降を原本の式・罫線・章分けへ戻す | ✅ 復元/独立目視QA/不変確認/対象回帰、12頁PDFを14:17:16 JST再公開 |
| 8 | `$simplify`：3 rendererの責務整理・型ヒント、挙動/体裁の完全保持 | ✅ 完了。4条件PDF bytes完全一致、全体3137 passed/2 skipped。raw範囲検出は別担当ログ1件と帰属確認 |

#### Step 1: 基準と実装契約を先に固定
- [x] ✅ 本計画書を指定フォルダに作成。オーナーの開発背景・シェルター非追加・風M許容を明記。
- [x] ✅ 最新コードと線路方向計画を照合し、担当別ファイル所有とAPIを確定。actions key=basic.keyに統一。
- [x] ✅ rootが107ファイルの基準世代を固定（tmp/transverse-example2-parity/baseline/manifest.json、入力SHA先頭fc9cc864）。
- [x] ✅ 修正前対象回帰110件合格（28.61秒、./.agents/logs/transverse-parity-baseline.log）。
- [x] ✅ 原PDFから全係数とDefine/抽出を独立fixture化（17/15/240/8、非ゼロ83セル、品質検査14件合格）。
- [x] ✅ 計画の形式・存在・Codex手順/妥当性レビューを実施（最終PASS、20261016T034751Z）。
**Verification**: 必須5節・ファイル存在検証、15 Define×16組合せ＝240係数セルのゼロを含む原本照合、元入力/原本/旧oracleのSHA保護、レビューPASS。

#### Step 2: 正規荷重を修正
- [x] ✅ C側にC側支承位置を使い、各支承の分担後N×腕からMを算定。
- [x] ✅ 単線上り/下りを両方生成しD2 fallbackを廃止。複線は無係数反力から分担を一度だけ適用。
- [x] ✅ Lと車両横荷重のρを名目係数と区別し、使用性/安全性/復旧性ごとに二重適用を防ぐ。
- [x] ✅ Iは0600用途別橋脚係数c_pを保持し、raw→有効係数→分担→支点0.1kN丸め残差配分の契約で一度だけ算定。Example未低減Iへの一致を求めない。独立レビューで見つかった符号付き率の近接相殺も全率共通式で修正・再検証済み。
- [x] ✅ S2/S10/S30を接続。材料は既存部位別入力と共通Ec補間、支持ばねは既存方向指定アダプターを使用。
**Verification**: 対称D1/D2のM=0、非対称C腕・ゼロ分担のM=0、単線両向き・複線総N、雪3確率、ρ1.231/境界/0、部位別強度と方向別支持を独立期待値で検証。

#### Step 3: 正規ケース体系を移行
- [x] ✅ schemaを明示し、17基本・15Define・16組合せ・8抽出を原PDF由来の意味付きIDで定義。
- [x] ✅ 全参照先に荷重実体を持たせ、未知/欠落/重複参照を明示エラー。単線選択・水平正負をDefineに保持。
- [x] ✅ 名目係数と用途別解決済み成分を分離し二重係数を防ぐ。応答解析器は作らない。
- [x] ✅ 旧Excelセル・旧ケース・地震条件はlegacy専用関数で保持。canonical legacy_auditはその関数/出典の参照情報のみとし、正規経路から旧fallbackや旧計算を呼ばない。旧oracleは変更せず監査検証を保持。
**Verification**: 15 Define×16組合せの240セル、全Define・抽出・ばね番号を独立fixtureで完全比較。全16組合せの参照解決、旧監査回帰を確認。17基本へ直接係数行列を掛けず、Define選択を通す。

#### Step 4: 帳票を新正規結果へ接続
- [x] ✅ 全17基本の荷重表、15Define、16組合せ、8抽出を表示。公開非地震章から地震本文・ケースを除外し、既存地震入力やlegacyデータを削除しない。
- [x] ✅ 荷重・材料・支持表は同じ正規結果を使い、入力再読込みや帳票内再計算をしない。
- [x] ✅ 製品PDFは工学条件・式・結果と必要な橋脚衝撃低減注記のみを表示。風M許容・入力調整・Example比較・旧Excel/VBA/Single/移植監査等の開発背景は本計画/JSON監査/READMEに残し、PDFへ混入させない。シェルター独立荷重を追加しない。
**Verification**: PDF抽出値とJSONを照合し全頁PNGを目視確認。欠落・切れ・重なり・誤った単位/符号/ばね方向がない。

#### Step 5: 回帰と公開条件
- [x] ✅ 個別数値/ケース/PDF/CLI試験、非対称・係数境界・雪0/null・異材料を確認。
- [x] ✅ 0620単独とallの正規結果/入力SHA一致、本作業による実入力改変なし、原本/旧oracle不変、他方向への意図しない変更なしを確認。並行作業の更新は世代記録と区別。
- [x] ✅ 既存成果物を保護する失敗復元を確認し対象試験後に既存全体ゲートを実行。並行変更による失敗を隠さず切り分ける。
**Verification**: 許容差を除く修正対象が独立期待値に一致。風H/Mを維持し、橋脚Iの数値差は式・用途・出典で説明できる。

#### Step 6: 公開と引継
- [x] ✅ 最新入力/コード世代を確認し、検証済み0620 PDF/JSONのみ既存公開機構で公開。他方向の候補を上書きしない。
- [x] ✅ 作業完了を✅で示し、試験結果・公開SHA・新知見・設計思想・Tipsを本書へ追記。
**Verification**: 公開SHAと検証済み候補一致。未解決/許容差/対象外が次担当者に明確。

#### Step 7: 追補・帳票体裁復元（ユーザー受入Failedへの対応）
- [x] ✅ 先行公開の数値実装完了と帳票体裁の受入失敗を区別して本計画を訂正。ユーザーの修正指示で着手済みであり、再承認待ちにしない。
- [x] ✅ 現公開PDFと`.claude/docs/Example橋脚2/09_直角.pdf`を直接目視比較し、原本物理p2–8・p13–15の見出し、式、表の罫線、位置、フォント、改頁を受入基準として固定。独立棚卸しは`tmp/transverse-example2-parity/layout-restoration-review.md`。
- [x] ✅ 現公開p1/2を保持し、p3以降の汎用表を原本の計算書形式へ復元。荷重の式・代入・集計、基本/Define・組合せ・抽出の章分けを保つ。原本のシェルター独立項目や誤った旧計算値は復元しない。
- [x] ✅ 修正前後の計算JSON・入力・計算モジュールの不変を確認。rendererだけでcanonicalの値を表示し、帳票内に新たな荷重計算や係数再適用を加えない。
- [x] ✅ 新候補を原本と並べて全対象頁を直接レビュー。文字切れの有無だけでなく、式主体の配置・罫線・章立て・改頁が見本に沿うことを独立担当が確認。最終PDF SHA64a5ac238053…で残指摘解消PASS。
- [x] ✅ 対象帳票試験と視覚QAを通した同世代PDFを公開し、公開後のPDF一致とJSON/入力/他成果物の不変を記録。表示修正前の関連4module48PASS、最後の表示修正後report+CLI17PASS。14:17:16 JSTにPDFのみ再公開し、入力/0620JSON/他6成果物は体裁復元baselineから公開後までSHA不変。

**所有**: root＝共通layout・試験・QA・公開、荷重/ケース描画＝rootが指定した各helper担当、計画担当＝本書唯一writerと独立目視レビュー。計画担当は製品コードを編集しない。計算/JSON/入力/ケース定義は本追補の編集対象外。

**Verification**: p1/2は現公開版とのpixel比較で不変。p3以降は原本p2–8・p13–15の対応箇所と直接比較し、原本にある式・罫線・章分けを汎用データ一覧へ置換していないことを確認する。承認済みの数値差・橋脚衝撃低減説明は維持し、開発事情を製品PDFへ出さない。

**見本から固定した体裁条件**:
- 原本本文は約9.9pt明朝（衝撃の狭い式は約9pt）、見出し約9.9ptゴシック。A4相当595×842pt、荷重章x76.4pt/小節88.2pt/項目100.0pt/式111.7pt、上端約71.1pt、通常行送り約13.5ptを目安とする。現公開の左48pt・13pt表題・8.2pt一律表へ戻さない。
- 荷重本文は開いた代入式と数値列、等号/単位/総計線を揃える。D1/D2同頁、浮力3水位＋雪3確率同頁、列車上/下/複同頁、衝撃上/下/複同頁、車横＋列車あり風、列車なし風の章分けを復元。原本p2は参考に留め、現p2保持を優先する。
- 基本17＋Define15は原本p13の上下2表で同頁。組合せは原本p14と同じ**A4縦用紙内部90°回転の1表**（16組合せ行×15Define列、全240係数）へ戻す。抽出はNo/荷重名称/C1–C4の小表とし、内部IDやスラッシュ列へ置換しない。
- 20支承等の拡張入力だけは自然改頁を許容し、位置0の有効支承を落とさない。衝撃は現行の丸め残差配分と矛盾する`N_L×i=N`を出さず、ΔI/短注記等で既計算Nを正しく説明する。新たな帳票内計算は禁止。

#### Step 8: 追補・帳票rendererの挙動を変えない整理

- [x] ✅ 編集前に対象を`transverse_report_example2.py`、`transverse_report_example2_loads.py`、`transverse_report_example2_cases.py`と本計画書に固定。担当はそれぞれtransverse_plan、compare_loads、compare_cases、root。Step7の所有契約はその工程限定であり、本Stepではこの契約を適用する。
- [x] ✅ simplify before gateを保存（`.agents/logs/simplify-transverse-report-20261016-baseline.json`、overall_before=pass、pytest=pass、HEAD e1ecdf2921e85e6fb3c7ab7e8f74014473219281）。全体試験は3143 passed / 1 skipped in 1334.38s。skipはtest_editor_formulas.py:536のTk初期化環境。実行ログは`tmp/quality-gates/pytest-20261016-145255-6116122.log`。
- [x] ✅ 通常入力・使用性係数0・20支承・左右異なる載荷土の4条件で、入力非破壊とPDFの基準bytesを保存。通常PDFは公開SHA64a5ac238053…と一致。元3 sourceと本計画書、対象外146ファイルのSHAも`tmp/simplify-transverse-report-20261016/behavior-before.json`と`before/`へ保存。
- [x] ✅ 部材行の生成、荷重章と表行、ケース表の罫線/見出し/本文を意味のある単位へ抽出し、全63関数へ型ヒントを追加（main12/loads31/cases20、AST監査漏れ0）。各担当の既存帳票6試験PASS。同じ6件の重複実行なので合計18件とは表現しない。
- [x] ✅ rootが今回だけの3 source差分を読み、責務分離による読みやすさを確認。各章の構成と表/行描画が分かれ、座標だけを渡す汎用抽象化や機械的20行分割は追加していない。4条件のPDF bytes完全一致・JSON非破壊を確認（behavior-after.json）。保護対象146ファイルのうち143は開始時SHA不変、残3は本編集前の別作業と証跡で識別。
- [x] ✅ 同じbaselineによるafter gateと再実行、差分範囲確認、計画書への完了記録。pytestはbefore=pass/after=pass、regressions=[]。raw gateのexit2は別担当作成ログ1件の範囲検出として保持し、独立範囲監査で本作業の追加範囲外編集なしを確認。出力PDF/JSONを再公開せず、既存の検証済み12頁版を保持。

**背景と設計意図**: 直前に未依頼の体裁変更で受入Failedとなったため、今回は見た目の改善も行わない。ReportLab操作の順、座標、文字列、字体、改頁、数値整形・丸め・条件分岐は維持する。20行目安の機械的分割ではなく、章の組立てと表/行描画など名前に意味のある境界だけを抽出する。循環参照を避ける型参照はTYPE_CHECKINGに限定し、実行時依存を増やさない。テストの変更/skip追加/期待値の弱体化は禁止。

**検証運用のTips**: 初回beforeは全体pytestの91%付近でsimplify_gate.py既定1800秒の実行上限に達し、基準JSONが作成されなかった（`tmp/quality-gates/pytest-20261016-142211-6147217.log`）。その時点では製品sourceを変更せず、ignoredな`tmp/simplify-transverse-report-20261016/run_gate.py`で実行時VERIFY_TIMEOUTだけ7200へ延長して同じgateを再実行した。スキル・check.ps1・テスト内容は変更していない。全体gateを担当ごとに重複実行せずrootの前後各1回を共有する。既存変更が多く、日本語ファイル名がgitの引用表記になるため、gateの範囲判定だけに頼らず元sourceとの差分と`git ls-files -z`由来の保護SHAを併用する。

**並行変更の区別**: 全担当が未編集で待機中の14:42:05 JSTに、対象外`longitudinal_example2_report.py`のSHAがf0fd86c9…から46fc8413…へ変化した。`observed-external-changes.json`へ時刻/両SHAを保存し、本整理の変更として扱わず巻き戻さない。4条件の挙動比較は保存済みJSONを使い、rendererだけを検証する。これ以外の対象外変更を自動で許可せず、検出時に出典を確認する。

**15:21 JSTの統合検証**: 0610 PDF/JSONの変更も保護SHA照合で検出し、線路方向計画と`tmp/longitudinal-example2-parity/candidate/publication.json`を照合。14:44:10 JSTの別担当公開（PDF88aa876d…、JSONad98ba14…）と現在bytesが一致し、本編集開始15:17より前の変更と確認した。観測記録にこの2件を追記し、そのSHA以外の変更は引き続き拒否する。実入力・0620 PDF/JSON・対象試験・計算コードは不変。4条件PDFのSHAは全てbeforeとafterで一致し、通常入力の公開SHA64a5ac238053…も保持。`refactor.patch`に今回だけの差分、`annotation-audit.json`に63関数の監査を保存。after全体gateは15:22 JST開始。

**after gate途中経過（15:30 JST）**: 4%地点に1失敗を検出。収集順から`test_editor_calculation.py::test_real_cli_all_reports_and_same_input_rerun_use_isolated_output`と特定し、既存テストを未変更で単独実行したところ1 passed in 24.33s（failed-cli-diagnostic.log）。全体実行の詳細traceは終了時に確認する。単独PASSだけで全体gateを成功に読み替えず、原因・必要な再検証を確定してからStep8を完了する。

**after gate初回結果（15:57 JST）**: 8 failed / 3134 passed / 2 skipped in 2014.85s。raw gateは`pytest: {before: pass, after: fail}`、regressions=[pytest]であり合格扱いにしない。うち7失敗は、15:23:49の別担当による線路方向11→8頁訂正中のNameError（削除済み_dead_diagrams参照、CLI1件）と旧11頁/図専用試験をロードしたまま新8頁を生成した世代混在（6件）。残1件はtest_pdf_preview_dialogのwm-close後のfocus_getがNoneになるGUIフォーカス検証。2skipはTk読込み環境。今回の3sourceは15:21の検証SHAから不変。

線路方向の訂正完了・関連29試験PASS・15:29公開を当該計画と公開証跡で確認した。元の入力・計算・0620・本担当のテストは維持し、旧線路テストへ巻き戻さない。別担当が更新したrenderer/試験/0610PDFの履歴はobserved-external-changes.json（6履歴、保護対象4パス）へ追記、計画/公開記録を同tmpへ保存。raw範囲gateが追加検出した`./.agents/logs/longitudinal-remove-extra-load-diagrams.log`も別担当の29試験の証跡であり、本担当作成物ではない。baselineを書換えて隠さず、after結果と独立範囲監査を併記する。

**再検証**: 更新済み世代で同じbaselineを用いるafter gateを15:58 JSTに再実行。初回結果は`.agents/logs/simplify-transverse-report-20261016-after.json`、再実行は同`-after-rerun.json`へ分けて保存。スキル・テスト・製品コードの追加変更、失敗試験の削除/skip追加/閾値変更はしていない。

**最終結果（16:22 JST）**: 再実行は**3137 passed / 2 skipped in 1384.52s**（`tmp/quality-gates/pytest-20261016-155811-1380473.log`）。raw値は`gates={"pytest":{"before":"pass","after":"pass"}}`、`regressions=[]`、`pre_existing_failures=[]`。2skipは既存Tk環境初期化条件であり、合格件数へ加算しない。beforeの総3144件→after総3139件は別担当の線路方向図専用5試験削除によるもの。本担当はテストを変更していない。CLIのNameError、旧線路頁/図の6件、GUIフォーカスの1件は最新世代の全体再実行で解消した。

raw gateの`ok=false`/exit2と`out_of_scope_files=[./.agents/logs/longitudinal-remove-extra-load-diagrams.log]`は隠さず保持する。この唯一の検出は別担当が15:26:35に作成した29試験ログ（SHA b0a1e98a…）で、`external-created-files.json`に帰属根拠を保存。元baselineやscopeは拡張/改変していない。`scope-audit.json`は日本語名を復号し、宣言4パス、gate生成patch、当該外部ログを区別して**未帰属の範囲外変更0**を確認した。

全体再実行後に4条件のPDF bytes完全一致とJSON非破壊を再確認✅。3 sourceのSHAは15:21検証時から不変（main acc1f4db… / loads a41aeab9… / cases 851c6c62…）。保護対象146パス中142は開始時SHA不変、4は上記の別担当更新と一致。実入力82d5a276…、0620 JSON07f76b31…、12頁PDF64a5ac23…は開始時のまま。最終根拠は`behavior-after.json`、`scope-audit.json`、`annotation-audit.json`、`refactor.patch`、rootの`review.md`。帳票体裁・荷重計算・シェルター非追加・許容された風M差を保持した。

**次担当者へのTips**: 共有ツリーの全体試験中に他担当がrendererと試験を更新すると、旧試験/新rendererの混在や一時的な参照切れが生じる。まずmtime・SHA・他計画の公開記録で帰属を確定し、別担当の変更やテストを巻き戻さない。更新後の世代で全体試験を取り直し、初回失敗ログも残す。新規の他担当ログはraw scope gateに残り得るので、baselineを後から書換えず、独立のファイルSHA/作成元監査で本作業の範囲を示す。

#### 当初実装分担とAPI契約

担当間の短い共有契約: `tmp/transverse-example2-parity/implementation-contract.md`。ActionLoadsの集中/分布/表合計の位置、17semantic key、resolved_componentsの候補・係数出典を同書で共有し、本計画の方針と一致させる。

| 担当 | sole writerファイル | 責務と境界 |
|---|---|---|
| 荷重計算 | transverse_actions.py、transverse_calculator.py、専用荷重試験 | 荷重物理量、用途別解決、材料の0620への適用、正規/legacy切分け。ケース定義をimportするが定義ファイルを編集しない |
| ケース定義 | transverse_example2_cases.py、独立fixture、reference/cases試験 | 原本由来17基本/15Define/16組合せ/8抽出、定義検証。荷重計算・rendererを編集しない |
| 帳票(rootが兼務可) | 新transverse_report_example2.py、必要時transverse_report.py、専用帳票試験 | 新JSONだけから表示し旧24×28固定/地震本文を公開経路から除く。旧transverse_report_style.pyはlegacy描画に保持。shared frame_model_reportは変更しない |
| 統合(root) | cli.py、統合/CLI試験、README、公開成果物 | 既読JSONから材料を渡す入口、回帰・視覚検証・公開。依存3担当の変更が揃ってから実施 |
| 計画/consumer移行 | 本計画、計画logs/scratch、test_transverse_calculator/report/foundation_routing、test_pier_model_samples、test_moving_load_boundary、test_reaction_snow_integration、test_report_cli | 進捗/新知見/設計背景を随時追記。旧試験をlegacyへ、新publicの材料/ばね/作用契約を明示。製品コード編集なし |

- `build_case_model(*, ultimate_factor, service_factor) -> dict`、`validate_case_model(model)`。戻り値は`basic_cases`17、`define_cases`15、`combinations`16、`extraction_cases`8。係数ベクトルは**Define ID順の15要素**。basic/define/combination/extractionのIDは別名前空間とする。
- Define 1–8は同番号基本のidentity。9はbasic[9,10]（単線上/下）、10は[11]（複線）、11は[12,13]（単線衝撃上/下）、12は[14]（複線衝撃）、13は[15,-15]（車横）、14は[16,-16]（列車あり風）、15は[17,-17]（列車なし風）。`selection_kind=identity/track_alternative/horizontal_sign`と`signed_basic_case_ids`を保持する。
- 単線L/Iは同じ上/下のoptionへ結合し、上りL＋下りIを作らない。代替候補は加算しない。水平符号は当該作用Hとその作用由来Mだけへ適用し、鉛直Nや死荷重偏心Mへ波及しない。候補保持までとし、構造応答の最大化はしない。
- actionsは基本/用途/trackごとのN,H,Mと分布荷重を作り、組合せへ`resolved_components`を渡す。名目係数・有効係数・適用済係数・残乗数を追跡する。rawから解決済L/I/LFへ名目係数を再乗算しない。Iは残乗数1（係数0なら不採用）。一般D/雪/風などは指定係数の一度適用を明示する。
- 集中荷重は`application`（作用部位/節点）を、分布荷重は区間と単位kN/mを保持する。D1のcap_top N8299.52、column分布297.68kN/m、footing重心N4167.45、D2のtop/soil、水の作用点を区別する。異なる作用点を足したN/H/Mを基部応答/全体系応答として表示しない。抽出は参照群までで、最大応答・支配値の計算/表示はしない。
- 荷重構築入口案は`build_transverse_actions(inputs, reactions)`。D1/D2、水、雪S2/S10/S30、trainのsingle_up/single_down/double、impactのultimate/service×3方向、lateral、windを返す。具体keyは3担当が合意してから固定し、JSON consumerへ同時反映する。
- 列車の率は入力L2→上り、L1→下り、L1+L2→複線を各支承へ一度だけ掛ける。上/下方向を符号や「有効な最後の候補」から推測しない。行にraw_N/rounded_N/raw_M/rounded_M/source_trackを保持。総Nはraw行N和を2桁丸め、総Mは2桁行Mの和とする原本表示の丸め境界を固定する（単線N: raw和567.3857→567.39、丸め行N和567.38を採用しない。単線M: raw和1210.0702でなく丸め行M和1210.08）。0分担のN/Mは0、位置nullは荷重0の場合のみ既存空欄規約で扱い、荷重ありの位置欠落を黙ってB側で補完しない。
- **衝撃の丸め順（独立レビュー後の確定規約）**: 支点の無係数反力q、有効係数a、用途別c_p、元支承率r_iから`raw I_i=(q×a×c_p)×r_i`を求める。支点総量は既存0600と同じ演算順で`T=Single(R((q×a×Σr_i)×c_p,1))`を保持する。差`δ=T−Σraw I_i`を絶対率の重み`w_i=abs(r_i)/Σabs(r)`で配り、`I_i=raw I_i+δ×w_i`とする。全率0だけI_i=0。率の符号/和の大きさでthreshold分岐しない。単符号率では従来の`T×r_i/Σr`と代数的に同じで、符号相殺時にも非0偶力を消さず増幅しない。補正絶対和はabs(δ)に限られ、支点0.1kN丸め＋Single量子化以外の補正を加えない。
- Iの総Nは補正後の未丸め行I_i和を2桁、行Mは補正後I_i×各腕を2桁、総Mは行M和。このため支点総I/Nを維持したまま行M末尾が変わる場合がある。旧案「率和が厳密0のみ未丸めunit Iへ分岐」は(-0.5,+0.50001)で偶力を消すため撤回。単線Mの初回候補値は最終受入値に流用せず新規約の独立式と照合する。
- 現0600ρ1.231の支点I114.3/290.3（合計404.6）一致はeffective_aが元ρと**同一の試験条件**で要求する。通常R(ρ,2)=1.23、最大R(1.1ρ,2)=1.35はc_pをそのまま保ちrawから取り直した独立式を期待値とし、404.6固定一致を要求しない。使用性0.75はc_pに含まれるため再乗算しない。
- **車両横荷重LF**: 現0600は輪重160×ρ1.231×0.2を丸めた39.39からH137.49を求める。新0620の基本LFは0620専用に既存moving_load.search_reactionsへ無係数0.2P=32.0を渡した基準反力を持ち、組合せでeffective_aを一度適用する。上流Hをρで割らず、ρ0でも定義可能とする。0600共有経路・風H/Mは変更しない。
- `calculate_transverse(..., *, design_conditions=...)`にCLIが既読dataから`parse_longitudinal_design_conditions(data)`を渡す。parser名は歴史上longitudinalだが既存3部位の同じ入力契約を再利用する。新しい強度欄・暗黙25/27は作らない。0620専用適用部で梁/柱/フーチングを区別し、H2/H3→beam、H1/H4→column、剛域→material_ref null。既存等価body**断面**・形状・節点は変更しない。フーチング材料は表示されても剛域のままとする。
- `calculate_transverse_legacy`と既存transverse_combinationsの旧表で旧source cells/荷重/地震/選択を保持。正規schemaの`legacy_audit`は専用関数名と出典の参照情報のみで、旧cells等を内包せず旧計算を呼ばない。旧oracle試験はlegacy関数で検証し、期待値自体を書換えない。これにより正規経路は旧fallbackとfoundation macroに依存しない。
- 新しいmaterial引数を必須にする場合はCLIだけでなく全calculate_transverse consumer（既存test_pier_model_samples等）を棚卸しする。旧監査試験はlegacyへ向け、新正規試験は既存JSONから明示parseする。0600単独実行を不要な材料未入力で停止させない。
- 現frame_model_report.draw_model_conditionsには旧原表/Single/Double等の固定注記とbody固定説明がある。共有関数をそのまま新0620へ流用せず、新専用モデル表または既存共有関数を変更しない明示注記入力によって、部位材料と正規ばねの工学情報だけを表示する。

#### 原本のケース定義と資料上の例外

原本基本17はD1,D2,WP1（高）,WP2（平）,WP3（低）,S2,S10,S30,L上,L下,L複,I上,I下,I複,LF,W1（列車あり）,W2（列車なし）。原本p13 Define複線記号L3/I3とp14見出しL2/I2は表記揺れのため、意味付きtrack=doubleで同一作用へ対応させ、出典原文を別途保持する。

下表の係数IDはDefine。標準ρ=1.23の非ゼロ名目値を示し、その他のセルは0。現入力ρ=1.231はR(ρ,2)=1.23、R(1.1ρ,2)=1.35の有効係数へ解決する。入力自体を1.23へ書換えない。

| 組合せID | 用途 | Define ID:係数 |
|---|---|---|
| 1 | 破壊・列車最大 | 1:1.1, 2:1.2, 7:1, 10:1.35, 12:1.35, 13:1.23, 14:1 |
| 2 | 破壊・車横最大 | 1:1.1, 2:1.2, 7:1, 10:1.23, 12:1.23, 13:1.35, 14:1 |
| 3 | 破壊・風最大 | 1:1.1, 2:1.2, 6:1, 15:1.2 |
| 4 | 破壊・雪最大 | 1:1.1, 2:1.2, 8:1 |
| 5 | 使用性・永久＋変動 | 1:1, 2:1, 6:1, 10:1, 12:0.75 |
| 6 | 使用性・永久 | 1:1, 2:1, 6:1 |
| 7 | 使用性・変動 | 9:1, 11:0.75 |
| 8 | 復旧性・列車最大 | 1:1, 2:1, 7:1, 10:1.23, 12:1.23, 13:1.23, 14:1 |
| 9 | 復旧性・雪最大 | 1:1, 2:1, 8:1, 14:1 |
| 10 | 安定・列車最大 | 1:1.1, 2:1.2, 5:1, 7:1, 10:1.35, 12:1.35, 13:1.23, 14:1 |
| 11 | 安定・車横最大 | 1:1.1, 2:1.2, 5:1, 7:1, 10:1.23, 12:1.23, 13:1.35, 14:1 |
| 12 | 安定・風最大 | 1:1.1, 2:1.2, 5:1, 6:1, 15:1.2 |
| 13 | 安定・雪最大 | 1:1.1, 2:1.2, 5:1, 8:1 |
| 14 | 長期支持 | 1:1, 2:1, 4:1, 6:1 |
| 15 | 短期支持・低水位 | 1:1, 2:1, 5:1, 6:1, 9:1, 11:0.75 |
| 16 | 短期支持・高水位 | 1:1, 2:1, 3:1, 6:1, 9:1, 11:0.75 |

**組合せ9は列車荷重0でも列車あり風W1=1を含む原資料仕様**。風をW2へ置換したり削除しない。抽出8群は破壊[1,2,3,4]、永久＋変動[5]、永久[6]、変動[7]、損傷[8,9]、安定[10,11,12,13]、長期支持[14]、短期支持[15,16]。

#### コード読取り根拠（2026-10-16調査時点）

- transverse_calculator.py `_dead_environment`: C側もG列(B位置)を使う。`_train_tables`: AD=分担前M列×腕、V総計はV/Z/AD混合集計。これらは正規経路で修正し監査経路へ保持。
- 同`_select_current`: 候補0のときbearing.d2を率へ転記。新正規経路は上/下を残し、D2 fallbackを呼ばない。
- 同`_combinations`: 旧24基本のうち10行がtemplate_row_only。新正規全17基本は作用実体を必須にする。
- 同`calculate_transverse`: foundation_spring_set(foundation,"transverse")接続済み。`calculate_transverse_legacy`が旧Single監査を保持。再実装して巻戻さない。
- longitudinal_design_conditions.py: 既存3部位parser・concrete_ecはRcDan全表と補間/外挿/80以上上限を実装済み。27→26.5e6は固定値でなく補間結果。
- transverse_report_style.py: `_selection`と`_train_notes`が旧fallback、`_basic`が24基本、`_matrix`が28列分割、`render_transverse_report`が旧layoutを参照。新正規結果用の経路へ置換する。

### Risks & Considerations

- 入力は意図的に調整されている。シェルター無しを理由に風のHや入力h4を減らす修正は禁止。風Mの差をバグとして追い続けない。
- 係数表の1.23/1.35と既にρを適用した作用をそのまま掛けない。有効係数R(ρ×名目倍率,2)、raw起点、用途別c_pと0.1丸めを線路方向と共有する。
- 旧基本/組合せの試験期待値を書換えるだけでは旧xls監査と新仕様を混同する。正規とlegacyの契約を分ける。
- 共有ファイルは並行作業中。編集前に最新差分を読み、担当所有を合意し、共有helperを重複実装しない。
- ケース検証は未知/重複ID、係数ベクトル長、上下L/Iの不一致、鉛直負Define、未知抽出、bool/NaN/負の係数を検出する。ρ1.235→通常1.24/最大1.36、ρ0、使用性係数変更も確認し、固定1.23だけで通る実装を防ぐ。
- 数値検証は各ROUND位置の表示桁に対応した期待値で行う。行M/総Mを明記し、小さい浮動小数差だけに厳密な絶対許容差を設ける。風M承認差を広い全体toleranceへ置換しない。
- 梁/柱自重の208.37kNは控除区間変更で相殺されるため過大荷重として削除しない。最終D1差0.01kNと材料修正を分ける。

### Open Questions

- 開発背景、入力維持、シェルター非追加、風M許容、修正開始はオーナーから明示済み。再承認を実装開始の条件にしない。
- 詳細API・符号相殺Iの丸め契約は確定済み。17頁の汎用表構成はユーザー受入Failedとなったため体裁の確定扱いを撤回し、Step7で見本へ復元して12頁版を公開済み。再承認待ちの未決事項はない。原本の表記揺れは意味付きIDとsource aliasで記録し、荷重へ推測を混入しない。

### Planning Validation

- 文書形式: validate_doc.py --contract plan-doc PASS（必須5節、warningsなし）。保存先存在: workspace.py --skill plan --slug transverse-example2-parity --verify PASS。
- 手順相談: .agents/logs/codex/20261016T034517Z-plan-transverse-example2-parity-steps-flat.md。契約先行→作用→分担/候補→ケース接続→帳票→CLI/回帰の順を確認。相談中の「抽出された支配値を表示」は構造応答計算を含むため採用しない。新rendererはtransverse_report_example2.pyに隔離する確定所有を優先する。
- 初回相談はWindows .cmd経由で複数行promptの先頭1行しかCLIへ渡らず、対象不明の回答となった。stderrのuser欄で確認し、自己完結promptを一行化して再実行。wrapperのexit0だけでレビュー合格と判定しない。
- 計画妥当性レビュー: **✅ PASS**。.agents/logs/codex/20261016T034751Z-plan-transverse-example2-parity-validate.md。全定義・独立fixture・作用/材料/ばね・帳票/CLI・回帰/視覚検証・公開・許容差を確認。スキーマ/ID/丸め/成分契約固定後の荷重とケース並行実装を妥当と評価。並行変更の出典識別、全consumer移行、同世代検証済み候補のみ公開を統合条件とする。修正開始はオーナー承認済みであり、承認再要求はしない。

### Progress / Findings / Tips

- 2026-10-16 14:17:16 JST（体裁復元完了）: 最後の表示修正後report+CLIは**17 passed in 34.53s**（./.agents/logs/transverse-layout-restore-final-tests.log）。root/独立担当が原本との直接比較をPASSとし、同世代の0620PDFだけを再公開。公開後SHAは`64a5ac2380530b4fb1996889b11a375a31fc7b6821669731d022eba1fff3140a`、再openで12頁と章/ケースを確認。`tmp/pdfs/transverse-layout-restore-20261016/publication-manifest.json`のbefore/afterを読み、入力82d5…・0620JSON07f76…・他6成果物が**今回体裁復元baselineから公開後まで**完全不変と確認した。生成sourcehashと最初2頁のpixelも一致。数値実装初回公開時の「他成果物は公開操作中のみ不変」とは期間が異なるため区別する。
- 2026-10-16（体裁復元・最終独立QA）: 最終12頁候補SHA`64a5ac2380530b4fb1996889b11a375a31fc7b6821669731d022eba1fff3140a`のp4/p5/p7/p8を原本対応頁と直接比較し、残指摘解消✅PASS。浮力3代入式、列車全行側名、風H/N/腕/Mの開放4列＋実B/C2行＋総計線を確認。既確認p3/p6/p9/ケースp10–12と合わせ全変更対象頁の独立目視QA完了。rootの全12頁bounds/p1・2pixel完全一致/renderer JSON非破壊/生成sourceSHA不変もPASS。修正後report+CLI再検証と公開は後続。風の必要差は行内訳と値に限定され、独自式レイアウトの差は解消した。
- 2026-10-16（体裁復元・風表の最終方針）: rootが原本への書式一致をさらに優先し、風MのHB/HC展開式を原本のH/N/arm/M開放列＋合計線へ戻す方針を確定。行はcanonicalに実在するB/C集計2行だけとし、シェルター/架空支承行は作らない。現在値と必要なモデル差を保持しながら書式差を縮める。最終候補では浮力/列車に加えp7/8も再レビューする。
- 2026-10-16（体裁復元・対象回帰）: 第二候補の関連4module（新帳票6、方向別基礎ばね、旧帳票、CLI11を含む）は**48 passed in 67.72s**（./.agents/logs/transverse-layout-restore-tests.log）。独立目視の浮力3代入式/列車全行側ラベルはrootが採用し担当修正中。最後の2表示修正後に新帳票6件と候補生成/視覚QAを再実行する。風のHB/HC式は現在の集計済み2側を正しく説明する必要な表示差としてrootと合意し、シェルター寄与の架空分解は行わない。
- 2026-10-16（体裁復元・荷重第二候補）: PDF SHA515f327d0bb9…のp3–9を独立目視。D1/D2同頁、W3/載荷土/等価梁の代入式、N/腕/M座標、雪3/列車3/基本I3同頁、使用性I補足を確認。p1/2 pixel一致・全12頁bounds・renderer JSON非破壊・生成前後source一致はroot確認済み。残りはp4浮力がh/U値列に留まり原本の体積×単位水重の代入式を欠くため、担当へ修正依頼。列車p5の側名毎行表示も小差として通知。風はシェルター/元Mに合わせた架空の寄与表を作らず、現モデルのHB/HCと腕の式で説明する必要な構成差として記録する。対象試験/再公開は未完了。
- 2026-10-16（体裁復元・第一統合候補）: 新候補は12頁。rootがp1/2 pixel完全一致、rendererによるJSON非破壊、全頁text boundsを確認。計画担当が候補p10–12を原本p13–15と直接目視比較し、ケース頁の体裁復元を独立PASSとした。基本＋Define同頁、全240セルの90°回転1枚表、抽出C1–C4の小表を確認。係数clip機械検証PASSは`tmp/transverse-example2-parity/cases-layout-qa/verification.md`、独立目視根拠はlayout-restoration-review.md。荷重p3–9は数値列位置/毎行側ラベル/フーチング・載荷土式/D2開始位置をrootが追加指摘し修正中なので、Step7全体完了とはしない。
- 2026-10-16（公開後の受入再対応）: ユーザーからp3以降の汎用表への体裁変更は未依頼としてFailed判定。数値変更と様式変更を分けるべきだった。原本全対象頁と現公開17頁を直接目視し、本文の字体/位置、開いた算式、総計下線、意味ごとの同頁構成、基本＋Define同頁、組合せの向き/1枚構成、抽出C1–C4を復元基準として固定した。可読性/枠外検査の成功は見本への体裁一致を保証しない。Step7で計算/JSON/入力を固定してrendererだけを修正する。
- 2026-10-16（体裁復元基準世代）: rootが`tmp/pdfs/transverse-layout-restore-20261016/baseline/`と`baseline-manifest.json`へ現世代を保存。入力82d5a2769dfb…、JSON07f76b318c48…、PDF632e73114754…を保持。p1/2のpixel不変はrootが検証し、計画担当は公開前の新候補を原本と直接比較して独立レビューする。修正承認はユーザー指示済みであり追加確認を要求しない。
- 2026-10-16: 初版計画を先行保存。線路方向計画は材料専用parserとfoundation_springs共通アダプターを既に採用しているため、新しい同等helperを作らず直角側から再利用する。支持ばね修正は今回の再実装対象ではない。
- 2026-10-16: 原本の組合せ行列は17基本ではなく15Defineを参照するため、独立照合対象は240セル。上/下の列車と衝撃は対応した候補同士に限定。基本1–8のばね1、9–17のばね2を保持する。
- 2026-10-16: 原本p13–15は比較担当がPNGで全頁確認済み。転記根拠はtmp/pdfs/transverse-example2-20261016/agent-cases.txt節2/6/7。fixtureは製品定数のexportで生成しない。原本記号のL3/I3対L2/I2揺れと組合せ9のW1を勝手に補正しない。
- 2026-10-16: rootによるbaseline回帰110件合格。Windows runnerの子プロセス出力で初回decode失敗したため、以後`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`を設定する。PowerShellで日本語をpipeする場合はOutputEncodingもUTF-8にする。Python実行は`./.venv/Scripts/python.exe -X utf8`、作業ディレクトリを明示する。
- 2026-10-16: 独立検証の重要な追加条件は、I支点総量先丸め→支承配分、率和0のsigned作用、LFのρ0/無係数反力。旧の分担率二重適用を直すだけでは丸め差やゼロ除算が残るため先行契約化した。
- 2026-10-16: Step1の独立fixtureとreference試験✅。tests/fixtures/transverse_example2_cases.json、tests/test_transverse_example2_reference.pyを作成し、原PDF SHA b6a7f565…5474de一致を確認。REDは4 failed、GREENは14 passed（transverse-reference-red-1.log / transverse-reference-green-1.log）。製品定数や旧oracleから生成していない。製品のRed/Greenとは分けた基準資料品質検査である。
- 2026-10-16: API契約✅。荷重とcaseの意味付きkeyを統一し、basic.key=actions keyを必須とした。ActionLoadsの作用位置・単位・raw/丸め・I係数を分離し、組合せはDefine候補ごとのresolved_componentsを保持する。rendererはcanonical actions/frameのみを参照する。
- 2026-10-16: 既存consumer試験の移行を計画担当へ分担。旧fixtureには鉄筋強度が無いため原fixtureを編集せず、canonical専用テストで明示の部位材料条件をparseして渡す。旧cells/oracle/混合集計/地震/PDF体裁はlegacyへ移す。C02の「publicとlegacyの全非ばね値一致」は新荷重修正と両立しないため、「正規ばね変更がcanonical actions/definitionsへ影響しない」「macroばね変更がlegacyのばね以外へ影響しない」「publicはmacro欠落/NaN/Infにも非依存」を別々に検証する。
- 2026-10-16: 共有用の当初所有リストにあったtest_reaction_shelter.pyは現ツリーに存在せず、calculate_transverse consumerの全件検索でも該当なし。存在する6試験ファイルを移行対象とした。
- 2026-10-16: Step2荷重担当の初回専用試験11件PASS。独立値D1 cap N8299.52/M0、D2 N780/M0、単線L N567.39/M±1210.08、複線L N1134.77/M0、LF H111.69/M430.01、風H/M不変を確認。境界試験追加中でありStep2全体完了とはまだしない。
- 2026-10-16: Step3ケース担当のサイクル1は7件PASS。標準/ρ1.231/ρ1.235/ρ0/service変更と全240係数の一致を確認。破損参照・符号・上下候補の拒否を次サイクルで確認中。
- 2026-10-16: consumer移行検証は旧帳票/雪26件PASS、モデルsample/列車境界22件PASS。初回canonical consumer100件中4失敗のうち3件は試験側の既存synthetic位置欠落（載荷10支承に位置を明示）とlegacy_nodesの通常加算残差（4e-15で検証）を修正した。残りのpublicばねPDF試験は新renderer接続待ち。元fixture/oracleは不変。
- 2026-10-16: rootの新renderer/facade/CLI材料接続✅。専用帳票3試験PASS（transverse-report-red/greenログ）。全240セル描画、legacy_audit無しでの描画、枠外文字なし、製品禁止語なしを検証。未入力支承行はactive flagを荷重側へ追加し表示を省略する調整中。全頁目視/CLI総合/公開は後続Stepで確認する。
- 2026-10-16: 既存consumer6ファイルの移行✅、最終専用ゲート**126 passed in 39.40s**（./.agents/logs/transverse-consumer-migration-final.log、expected=passed/observed=passed/exit0）。旧oracle/旧PDF/雪地震の監査を保持し、canonicalの部位材料・原形状・正規6ばね・ばねによる作用非変化・macro欠落/毒化非依存・入力非破壊・公開PDF値/工学方向・LF係数一度を検証。旧独立fixture/入力/原PDFには変更なし。
- 2026-10-16: ケース製品検証✅。cases63＋reference14＝77 passed（transverse-cases-green-2.log）。全240係数、係数入力境界、上下候補結合、水平符号、未知/重複/bool ID、係数改変、抽出参照の拒否を確認。coverage90要求の実行はpytest-cov未導入でpytest usage error4/observed=null（transverse-cases-coverage.log）。これはカバレッジ未測定であり合格扱いせず、依存追加もしていない。
- 2026-10-16: 荷重担当Step2✅。最終専用14試験PASS（2.96秒）、旧legacy回帰63件を含む77件PASS（6.28秒）。全雪、C腕、複線一回、単線両方向、I支点丸め後分配/signed率和0、service1.4、ρ0、H1柱/H2H3梁/footing剛域、材料/ばね分離を検証。coefficient_traceにapplied_factorとfactor_applications=1を追加し、service名目0.75と実採用service係数の相違を監査追跡できるようにした。
- 2026-10-16: 独立case/validator/専用試験レビュー✅PASS、Medium以上指摘なし（tmp/transverse-example2-parity/case-validator-review.md）。全定義/240係数・用途/丸め・候補結合/符号・不正型・破損検証と独立fixtureの相互補完を確認。ActionLoads物理検証は荷重/統合試験の責任とし、validatorへ構造応答判定を混入させない。
- 2026-10-16: rootの使用性係数0の帳票境界試験はRED確認後に修正し、帳票＋CLI24件PASS（./.agents/logs/transverse-report-cli-final.log）。初回候補の新17頁PDFをcontact sheetで全頁目視確認済み（I修正/最新入力世代による再生成前の確認）。全体gateを実行中。専用試験の成功だけで全体回帰/公開完了とはしない。
- 2026-10-16: 公開前の世代確認で外部作業による実入力変更を検出。hs、旧シェルター入力の除去、出典が更新され、現入力SHAは**82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b**。root/本作業が変更したものではなく、旧baselineへ戻さない。他出力の変更は外部0600 PDFのみ。詳細はtmp/transverse-example2-parity/prepublication-diff.json。最新入力で最終候補を再生成し、旧SHAの候補を公開しない。
- 2026-10-16: 独立荷重レビューが符号付き率(-0.5,+0.50001)による衝撃M消失を検出。率和が厳密0の場合だけ分岐すると、微小な非0和の支点Iが0.1kN丸めで0となり、両側の非0作用/偶力まで失われる。荷重担当が再開し、近接相殺にも妥当な配分契約と独立試験を追加中。解法/適用条件の確定前に完了扱いや広い許容差での吸収をしない。

- 2026-10-16: 近接相殺Iの解法をroot採用。全符号/全率へ共通する「raw I_i＋絶対率による支点丸め残差δ配分」へ改訂した。thresholdや厳密0だけの特別扱いは使わない。README/帳票の工学的丸め説明も更新。荷重TDDの最終結果を待ってStep2を閉じる。
- 2026-10-16: rootの帳票追加境界（両側20支承すべてactive＋H1非0）がPASS、帳票専用5件PASS。全体gateは継続中。先行17頁contact確認は最終I/最新入力での再生成前のものと区別し、公開候補は再生成後に全頁QAする。
- 2026-10-16: 独立荷重/帳票レビューはMedium2件を検出し、owner修正後に再確認PASS、未解決Medium以上0。1) service_factor0でimpact_up候補がなく帳票KeyError→明示的な0注記。2) near-zero符号率の衝撃偶力消失/増幅→絶対率で支点丸め残差を配分。率差0.00001のMは旧0→358.18、0.00042では旧702.68→358.32となり、独立7境界で安定を確認。新しい契約は現入力だけの特例でなく任意の符号率にも共通適用する。
- 2026-10-16: 近接相殺I修正✅、旧式で独立7試験RED→共通残差配分式でGREEN。最終荷重専用27＋legacy63＝**90 passed in 6.33s**。δはmath.fsum(raw_forces)との差で求め、signed率和による割算とthreshold分岐は除去。非対称C腕[-2,+5]・率[-0.5,0.50049/0.50051]でN0/0.1、M350.17/350.33を確認し、全率符号反転4点も検証。side traceにraw_impact_total/rounding_residual/absolute_rate_sum/distribution_policy、rowにunrounded_impact/rounding_correctionを追加。
- 2026-10-16: 新I規約で現入力の単線M絶対値は、基本I364.42→364.43、使用性272.75→272.73、有効a1.23では448.25→448.26、a1.35では491.97→491.98。支点総I/Nおよび複線は不変。これは符号付き入力の支点丸め補正を安全に局所化した結果で、Example未低減Iへ戻す変更ではない。最終PDFはこれらの変更と最新入力SHAを反映して再生成する。
- 2026-10-16: 全体gate初回は**10 failed / 3083 passed / 1 skipped**（tmp/quality-gates/pytest-20261016-130200-2244597.log）。5件は実行中の並行test_editor_formulas変更（現在legacy呼出へ変更済み）による旧ロード状態の可能性がありrootが最新再検証。残5件はtest_report_cli.pyの旧baselineに部位材料がないconsumer移行漏れで、本作業の修正対象として計画担当へ追加。原fixtureを変更せずテスト用入力コピーだけへ梁/柱/フーチング各27を明示し、全stage実行と単独/all同一SHA・結果一致契約を保持して再検証する。skipを合格に数えない。
- 2026-10-16: test_report_cli consumer追補✅、同module **11 passed in 16.07s**（./.agents/logs/transverse-all-cli-consumer-fix.log、wrapper expected/observed passed/exit0）。新材料条件はテスト入力コピーだけへ付与し、元baseline/モデルfixtureのbytes不変、全4stageの単独/all結果・入力SHA一致、BOM、上書き/失敗復元を保持した。0620の部材material_refだけ新契約へ合わせ、原物理グラフ期待値を変えていない。

- 2026-10-16: root最終対象統合 **255 passed in 40.39s**（./.agents/logs/transverse-final-integration.log）。これは対象統合の成功であり、初回全体gate（10 failed/3083 passed/1 skipped）を全体PASSへ読み替えない。test_report_cliの5失敗は同module11PASSで解消済み。残test_editor_formulasの5失敗は現ソースがlegacy呼出へ変わった後の再検証中。
- 2026-10-16: 最終候補を最新入力SHA82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628bで再生成し、17頁の全PNG目視QA✅PASS。新単線IのM364.43を反映。生成前後および再確認のsourcehashは同一。tmp/transverse-example2-parity/candidate-manifest.jsonへ候補世代を保存。PDF SHA=`632e73114754a6496f1a120fbf7a8691016b3125f0bb393ce8b5aec99954d6c2`、JSON SHA=`07f76b318c482d92353a6b037c2bb522fbcdb44158a513322066cbbbe49a2bca`。候補確認であり、公開完了は公開後SHA照合の記録を待つ。

- 2026-10-16: 最後のtest_editor_formulas再検証は**59 passed / 1 skipped**（Tk環境によるskip、./.agents/logs/transverse-editor-api-recheck.log）。初回全体の5失敗は並行作業が旧API検証をlegacy呼出へ移した現在ソースで解消。最終対象統合255＋report_cli11＋editor59＝**325 passed / 1 skipped**。全体gate初回の10失敗は全て該当module再検証で解消したが、全体gateを再実行してPASSしたとの主張はしない。
- 2026-10-16 13:22:23 JST: **0620 PDF/JSONを公開✅**。既存cli._publish_outputsで2ファイルだけを公開し、公開後のbytes/SHAは検証済み候補と一致。PDF `632e73114754a6496f1a120fbf7a8691016b3125f0bb393ce8b5aec99954d6c2`、JSON `07f76b318c482d92353a6b037c2bb522fbcdb44158a513322066cbbbe49a2bca`、入力 `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b`。生成元source全hashは候補生成/再確認/公開時で同一。tmp/transverse-example2-parity/publication-manifest.jsonに記録。
- 公開時の他6成果物（0500/0600/0610各PDF/JSON）は直前SHAを保持し、本公開で上書きしていない。待機中に外部作業が0500JSON/0600pair/0610pairを更新しているため、「開始時から他成果物不変」とは表現しない。並行変更を戻さず、公開操作の影響をその時点のSHAで確認した。

### Completion / Handoff

- **Step8 `$simplify`完了✅**。renderer3ファイルの責務整理と型ヒント追加。4条件PDF bytes完全一致、63関数型監査、全体pytest pass→pass（最終3137pass/2skip）を確認した。raw scope gateの別担当ログ1件の検出は上記のとおり記録し、gate全体PASSとは表現しない。本作業の未帰属範囲外変更は0。入力・0620 PDF/JSON・計算・本担当のテストは変更せず、再公開なし。

- **Step1–7の実装・検証・公開完了✅**。最新公開成果物は`./output/0620_直角方向荷重.pdf`（12頁、2026-10-16 14:17:16 JST、SHA64a5ac238053…）と計算内容を保持した同名JSON（SHA07f76b318c48…）。先行17頁版の体裁受入Failedを受けて、見本に沿う式・罫線・章分け・改頁へ復元した。数値世代は`tmp/transverse-example2-parity/`のcandidate/publication-manifest、復元版の公開証跡は`tmp/pdfs/transverse-layout-restore-20261016/publication-manifest.json`へ分けて保存。
- 受入済み差は冒頭比較表のD1 N0.01、橋脚衝撃低減、風M。シェルター機能は追加せず、構造解析・最大応答・部材照査も追加していない。
- 正規schema2の17基本/15Define/16組合せ/8抽出と240係数を使用する。旧Excel監査はcalculate_transverse_legacy/旧rendererで保持し、正規legacy_auditは参照metadataのみ。
- 再開時は最新実入力・生成sourceのSHAを確認し、この公開世代と混同しない。Windows UTF-8環境変数、全率共通のI丸め残差配分、材料がない旧fixtureはテスト用コピーへ明示材料条件を付ける運用を継承する。
- 検証の限界: 数値実装時は全体初回10fail/3083pass/1skip→失敗全module再検証で解消。対象325pass/1skip、当時の数値/機能レビュー未解決Medium以上0。**当初は見本体裁の受入基準が不足し、可読性検査だけでは帳票受入を満たさなかった**。復元では原本直接比較を追加し、全変更対象頁の独立目視PASS、p1/2 pixel完全一致、全12頁bounds、全240係数、JSON/入力不変を確認。関連4module48PASS後、最終表示修正後report+CLI17PASS。重複する17件を48件に足した独立件数や全体再実行PASSとは表現しない。pytest-cov未導入によりcoverageは未測定。
- 原本との必要な構成差は現在モデルの等価梁/控除説明、橋脚I低減/丸め説明、風B/C集計2行、使用性I補足、アプリ通常フッターに限定する。シェルターや架空支承を復元せず、全画素・全数値一致は主張しない。次回以降、見本を示された帳票修正は式・罫線・章構成・改頁も受入条件へ含め、汎用表への変更を数値修正へ混ぜない。
