# PDF生成のGridLayoutPdf移行台帳

2026-10-17。対象は0500・0600・0610・0620・0710・0720のPDF生成。計算・入力画面・JSON・CLI/GUI操作・成果物名・公開契約を維持し、全帳票を可変ページにする。本文・数値・表は白黒、体裁の参照は `../.claude/docs/Example橋脚/output/*.pdf`。この文書の現段階は移行前基準の確立であり、新rendererの受入完了を意味しない。

## 移行前の固定基準

凍結runは `tmp/reporting-grid-migration/baseline-20261017T035601697852Z/`。HEADは `744e9389fa69c62906d85d42c823940f924a9251`。未コミット/未追跡のJRSNAP実装、編集画面変更、入力変更も含めて230ファイルをコピーし、コピー前後のSHA-256一致を確認した。HEADだけを基準とせず、`freeze-manifest.json` の個々のファイルhashを使う。

| 対象 | SHA-256 |
|---|---|
| 凍結manifest | `65852dac070f03b5c3ba5f24420c9b4b1612cbda5af026ae8e662f4688527bf9` |
| 入力JSON | `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93` |
| 移行前インストール依存manifest | `77a5daace4be5f6bda77e089113fcd1670fcc8c3b28a1c14834a783d7ef1fbb8` |
| テストfixture manifest | `ad1be3c47caa6893578f2bc2104b6a9883fe97fe34e8beef38897aade0825532` |

`tests/fixtures/reporting/baseline/` は32ファイルの固定fixtureである。入力、全6結果JSON、全6旧PDF、各結果のJSON pointer台帳、各PDFのnative span台帳、0600表示値、FrameWeb両方向native JSON、ソース/依存manifest、入口台帳、取得記録を含む。全JSON配列の順序、数値・符号・単位・欠値・空容器を保存し、丸め許容で計算差を隠さない。

| Stage | 旧PDF頁数（観測値） | 結果のleaf/空容器ID | native本文span | 頁番号等の装飾span |
|---|---:|---:|---:|---:|
| 0500 | 3 | 82 | 440 | 0 |
| 0600 | 30 | 2,935 | 3,198 | 30 |
| 0610 | 8 | 37,069 | 1,015 | 16 |
| 0620 | 12 | 30,081 | 1,583 | 12 |
| 0710 | 3 | 650 | 137 | 3 |
| 0720 | 4 | 4,443 | 196 | 4 |
| 合計 | 60 | 75,260 | 6,569 | 65 |

頁数は新出力の固定条件にしない。native spanには字形の元位置・基線・方向・書体・サイズ・色を併記しているが、新帳票のページ位置の正解とは扱わない。書式の独立基準は `reporting-style.md` とappearance fixtureを参照する。

原本4 PDFのhashは凍結manifestの `role=reference` に記録し、元ファイルを変更していない。旧正式output/postも `published/` にコピーした。現入力は並行JRSNAP作業で追加項目を持つため、旧正式6結果JSONと新たに凍結した旧renderer候補は同じ入力世代ではない。`published-result-comparison.json` で全leafを比較したところ、差は6帳票すべて `provenance/input_sha256` だけで、計算内容の差はなかった。この区別を消して「正式出力とbytes一致」とは主張しない。

## 取得方法と正本の区別

`scripts/reporting_baseline.py capture` は、凍結コピーの `src.cli` を新しいPythonプロセスへimportし、`prepare_generation(stage="all", jrsnap=False)` から保持候補を取得した。`candidate.validate_unchanged()` を前後に実行し、`publish()` は呼んでいない。正式output/postと候補の公開先に成果物を書かず、候補bytesをQA fixtureへコピーした。結果dictの非変更も確認した。

このfixtureは**移行前後の同値性基準**である。構造計算が工学的に正しいことの独立oracleを新作したものではない。既存Excel/VBScript由来の数値oracle、地震時の独立期待値、JRSNAP読戻しoracleは元のまま凍結・保持した。新builderの出力でこれらの期待値を更新しない。

`capture` は既存fixtureディレクトリの上書きを拒否する。再調査が必要になった場合は別runを作成し、入力/ソース変更理由と比較結果をレビューしてから基準採否を決める。fixtureの期待値を新rendererへ合わせる自動更新経路は設けない。

## 全PDF入口と互換経路

正確な凍結時の行番号とimport関係は `baseline/renderer-inventory.json` にある。直下ASTから8個のReportLab Canvas生成箇所を記録した。Tkinter CanvasやPDFプレビューの読取りはPDF生成として数えない。

| 公開入口 | 凍結時の実装 | 結果形式 / 呼出し元 |
|---|---|---|
| `report.render_report` | `report.py` | 0500結果 / CLI |
| `reaction_report.render_reaction_report` | 同moduleとlayout/pagination/horizontal/snow/diagrams | 0600結果 / CLI |
| `longitudinal_report.render_longitudinal_report` | `longitudinal_example2_report.py`から再export | 0610 schema2 / CLI |
| `transverse_report.render_transverse_report` | `transverse_report_example2.py`から再export | 0620 schema2 / CLI |
| `seismic_longitudinal_report.render_seismic_longitudinal_report` | 同module | 0710 schema1 / CLI |
| `seismic_transverse_report.render_seismic_transverse_report` | 同module | 0720 schema1 / CLI |
| `longitudinal_report_reference.render_longitudinal_report` | 旧reference renderer | 旧0610結果 / `tests/test_longitudinal_report.py` |
| `transverse_report_style.render_transverse_report` | 旧reference renderer | 旧0620結果 / `tests/test_transverse_report.py` |

すべて `src.` 以下。最初の六つの `(result, output_path)` signatureを維持する。正規0610/0620実装moduleへの直接importも入口である。後二つは旧計算器の検証が使う互換経路で、主CLIは使わない。必要なら新描画へ委譲し、不要なら旧PDF試験を内容同値検証へ移して描画経路を撤去する。旧計算器と独立数値oracleまで削除しない。旧Canvasを選べるfallbackは残さない。

`cli._render_reports` が6公開入口のdispatch。`prepare_generation` が計算/帳票/native/sidecarを一度生成し、`GenerationCandidate` が同じbytesを検証・公開する。`pdf_preview.py` と `pdf_preview_dialog.py` は既存PDFを読むだけである。

## 0600の値評価と配置の分離

`baseline/reaction-display.json` は5シートの全4,601表示値と3,798件の書式付き論理セルを保存する。各セルにシート、元アドレス、値、number format、整形文字列、式、dynamic/blank-zeroを記録し、全formulas/constantsと帳票caption上書きも保持した。これは旧layout全体の座標を新配置へ渡す許可ではない。

`values` と `result_cells_double` / `public_values_double` が表示側の基準、`macro_handoff_single` は後続引継ぎの別基準である。Singleをsentinelに置換しても表示値が変わらない試験を追加した。ROUND/IF/SUM等を含む式依存・number formatは値契約として保ち、罫線・box・旧改頁帯とは別に扱う。

## 新semantic部品への対応規則

旧PDF由来の `stage/display/000001` 等は、旧native描画順序の監査IDである。新しい数式ASTのrun分割や改ページ後も同じspan分割になるとは仮定しない。新builderは、意味部品ごとに `semantic_id`、対応する旧 `source_ids`、対応する結果JSON pointer/0600論理セルID、出力側の意味順序を持つ台帳を追加する。

- 旧本文IDは原則として新意味部品へ一度だけ割り当て、欠落・二重割当・想定外の新本文を検出する。
- 数式は記号式、因子、演算子、結果、単位の役割と順序を保持する。数値集合/Counterの一致だけでは合格しない。
- 行列は行/列IDと係数位置を保持する。再組版によるrun数・頁数の変化と、セル内の数字交換を区別する。
- 旧頁番号とSHA footerは装飾台帳に分離済み。繰り返される章題等は現時点では本文に残す。新しい反復headerへまとめる場合、その旧ID集合と理由を個別に明示し、本文を一括除外しない。
- 図の文字は本文IDに含まれ、元図形の件数も各頁に保存される。幾何・寸法・節点対応は結果snapshotと既存図試験で照合し、文字台帳だけで図の同値を保証しない。

`assert_records_equal` は対応済みの順序付き意味レコードを厳密比較する検査部品である。現段階の34試験は固定基準の完全性、計算/表示値不変、負例感度、入口保全を検証する。新帳票の全本文対応・体裁・目視の合格は後続のstage移行で別に示す。

## 並行JRSNAP実装の再確認

初回計画調査で未存在だった `jrsnap_design_conditions.py`、`jrsnap_export.py`、`jrsnap_ndu.py` は凍結時に存在する。関連6試験moduleも追加済みである。`test_jrsnap_cli.py` は保持候補の変更/競合/復元と単独/allのNDU一致、`test_jrsnap_acceptance.py` は独立oracle・同じbytes公開・receipt失敗/回復を扱う。これらの全試験結果はleadの全体基準実行で判断する。

追加で凍結した実engineを `probe-jrsnap` から動かし、0710+JRSNAPの4候補（PDF、結果JSON、NDU、付帯JSON）を生成・検証した。`run/jrsnap-probe/` にコピーし、公開先は空のまま。0500/0710の計算snapshotは通常all基準と完全一致、NDU SHAは `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`。実JRSNAPアプリの読戻し・解析・正式公開はしていない。

JRSNAP source identityが現在 `src/*.py` の直下だけを追跡する点と、受入receiptも同じ集合を検証する点は今後の移行で修正が必要。入れ子 `reporting/`、実際にimportしたgridlayoutpdf、書体/表示資源を同一の識別契約へ結び付ける。候補stagingへ未宣言grid/trace/PNGを加えず、診断出力はQA領域へ置く。

## 検証記録と更新境界

### 0500 native 移行の検証

`report.render_report` は `reporting/stages/foundation.py` の原稿へ委譲する。旧 `_Page` は未移行帳票の依存が残る間だけ保持する。計算結果の編集、入力 parser の 11 層制限の変更、正式 output/post への公開は行っていない。

旧 native PDF の本文 440 span を、`semantic/0500.json` の 70 意味単位へ一度ずつ対応させた。根号の非文字部分は旧 PDF の 3 本の線を独立した根拠として保存する。新原稿の Fraction/Root/Script の葉をレンダリングせず列挙し、原稿から確定 scene の全文字・数式 vector への順序付き対応を検査する。さらに同じ scene から生成した PDF の 1,489 glyph の文字・座標・書体・size・黒色、および全 Line/Polyline の座標・線幅を照合する。scene と PDF の両方から同じ因子・単位・根号・分数線を削除する負例も拒否する。

標準表の行高は 14.28 pt、見出しは 2 段。長い地層名・土質区分は native `wrap_text` の測定で折返し、縮小せず行高を増やす。直接 renderer は 90 層も改頁して出力し、入力 parser の最大 11 層契約とは分離する。不可分の巨大数値は LayoutError とし、既存出力先の bytes を保持する。長期/短期ラベルは直後の式と同頁に保つ。

方向別の断面二次モーメント Iv と長期/短期 Kr は、方向見出しから最終式までの小節全体を同頁へ保持する。長名称版で境界を検証し、改頁によって見出しと Iv だけが前頁へ残る状態を解消した。v4 全 18 PNG の確認後、v5 の変更 4 PNG を再確認し、残る 14 PNG は SHA-256 が v4 と一致することを確認した。

原本の「一軸圧縮強度」だけは、直接測定した役割 `foundation.table_header_compressive` の MS-Gothic 8.9 pt を採用する。その下の `qu(kN/m` は 9.9 pt、上付 2 は 6.5 pt。これは自動縮小ではなく、当該 caption だけの原本役割であり、他の表見出しを 8.9 pt にした負例は失敗する。顔/size/見出し字下げ/等号位置/行高は独立 appearance fixture と照合した。

公開 Table は隣接する row part の境界を各々の内側へ描く。細線は各 stroke 0.12 pt、共有境界で接する 2 本の実際の塗り幅は 0.24 pt となる。**原本の単一 0.12 pt と一致するとは扱わない。** 帯を union した中点から行高を測り、14.28 ± 0.5 pt を確認する。外周は 0.96 pt。rowspan 内部や改頁端まで細くする一律半減は行わない。この差は lead の review 方針として承認され、QA の `0500-table-ink.json` に実測値を保存する。

最終 QA は `tmp/reporting-grid-migration/0500-v5/`。通常 2 頁、90 層＋長土質名 4 頁、長名称 3 頁。各 normal/overlay PDF、同じ確定 scene の trace、全 18 PNG を生成・目視し、文字欠け/重なりなし。通常 PDF SHA-256 は `a102544dfe23ecabecf5da36fc1be89bb6069e0d53b2037568963189e47f96cd`。`0500-source-native-audit.json` は旧 source IDs、原稿→scene token hash、実 PDF glyph IDs を単位ごとに示す。

再生成は P7 root で `.venv/Scripts/python.exe -X utf8 -m scripts.reporting_semantic_audit --foundation-proof --baseline tests/fixtures/reporting/baseline --destination tmp/reporting-grid-migration/新規QA名`。fixture を新出力で更新しない。最終 native 対象は 27 passed / 18.23秒 (`p7-grid-0500-direction-final.log`)、その前の既存 CLI を含む対象は 31 passed / 213.68秒 (`p7-grid-0500-native-cli.log`)。0600 旧 trace は 3,308 draw call / 全 3,228 span の exact-order 対応を 2 試験で確認済みで、新実装の完了を意味しない。GL check の実 JSON 最上位は `ok: true`、`overall` は存在しない。

- 対象試験: `tests/reporting/test_report_source_parity.py` と `test_renderer_inventory.py`。P7 .venvから共通run_tests.pyを使用し、34 passed / 13.77秒。ログ `.agents/logs/p7-grid-baseline-parity-final.log`。順序交換、符号変更、因子欠落、単位変更、重複ID、0/null/空容器、fixture改変/欠落/余分ファイルの負例を含む。
- REF/元入力/正式output/postは凍結後とprobe後とも変更0。`source-drift-final.json` はその時点の既存ファイル差分を保存し、leadが行ったuv.lockの最小更新と、新規QA scriptを区別する。後続の製品変更は既存基準を更新せず差分として追跡する。
- P7の旧installed manifestはgridlayoutpdf 15ファイルを実体コピーし、ReportLab198/PyMuPDF122/Pillow123/pytest93/pypdf66/tksheet26/xlrd18のhashを保存した。移行開始時のlock不整合とleadによる新wheel同期は旧環境基準へ遡って混ぜない。
- ruffはP7/GL venvおよびPATHで見つからず、今回導入していない。製品コードは変更せず、対象pytestでimport/実行を確認した。
- GL `.agents/check.ps1` は実行結果の最上位 `ok: true`、detect_stack/design-doc/state-docの各exit_code=0。DESIGNには既存warning `section 'アーキテクチャ' is present but has an empty body` がある。これは文書契約検査であり、製品全体受入ではない。

計画の正本: `C:/Users/sasai/Documents/GridLayoutPdf/.agents/docs/plans/pier-report-grid-migration.md`。工程3の先行proofgateが終わるまで帳票製品への展開は進めない。

## 再開後の完了記録（2026-10-17 19:16〜21:47 JST）

クラッシュ後、順次実行で工程6〜10を完了した。

- 0610/0620の公開入口を `reporting/stages/longitudinal.py`・`transverse.py` へ接続。2個目の等号は代入式の結果に限る（「P = …、M = …」は1式）、表の揃えは列単位、数値列の「－」は中央、0620組合せ表の要求性能列を拡幅。
- 0600桁受け図が梁幅を含まない縮尺で枠外へ出て LayoutError となる不具合を修正（全梁幅で縮尺、梁天端線、重心は梁天端基準）。0710/0720は「・」の作用群とKh行を同頁に保持。
- 同一入力から同一bytesのPDF：GridLayoutPdf に `render_pdf(..., invariant=True)` / `Document.render(..., invariant=True)` を追加（既定は従来どおり）。GL 1990件合格・coverage 99%・37頁goldenの画素不変。P7へ強制再導入し、導入済み24ファイルのSHAがsourceと一致。
- 旧Canvas描画を撤去：example2/reference/style系、frame_model_report、reaction_report_{horizontal,pagination,diagrams,snow} と旧0610/0620レイアウトJSON・生成tool。`report.py`/`reaction_report.py` は薄い公開入口。`test_live_package_has_no_legacy_canvas_renderer` で再混入を検出する。旧計算器と数値oracleは保持。
- 旧座標・固定頁数の試験を内容・順序・まとまり・枠内の検査へ移行。0610の320・0620の240係数はnativeセル単位で照合を継続。31桁の雪荷重は縮小せず LayoutError（既存出力保持）とする方針を0600にも明記。
- 回帰：非UI 2,768+1,473件合格（移行した3件を含む）、GUI 96件合格。
- 受入：現在入力は基準入力から `jrsnap_transverse`（計算で未使用）のみ追加。全6結果の葉は `provenance/input_sha256` 以外一致、旧本文→原稿→scene→PDF監査・overlay同一glyph・白黒・FrameWeb native意味不変を全帳票で確認。全44頁を目視。保持候補 publication `46129890fe4b473cbb146a27547b370e` を既存transactionで一度だけ公開し、正式16ファイルが候補bytesと一致（0500=2頁、0600=23、0610=6、0620=8、0710=2、0720=3）。
- QA記録：`tmp/reporting-grid-migration/formal-final-20261017T124701888352Z/`。
