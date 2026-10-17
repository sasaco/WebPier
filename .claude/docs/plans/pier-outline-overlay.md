## Implementation Plan: Pier Outline Overlay

### Purpose

線路方向 `./output/0610_線路方向荷重.pdf` と線路直角方向 `./output/0620_直角方向荷重.pdf` の1ページ目で、既存の骨組み図に、現在の入力寸法から作成した橋脚の外形を重ねる。`Example橋脚2/08_線路.pdf` と `Example橋脚2/09_直角.pdf` のように、柱・梁／ハンチ・フーチングを薄い点線または短い破線で表す。

### Scope

**ユーザー確認済みの範囲**

- 両方向の1ページ目の骨組み図が対象。外形を背面に描き、骨組み・節点・番号・既存寸法を前面に維持する。外形は塗りつぶさない。
- 線路方向は B1～B9、直角方向は W1～W9、高さは共通の H2～H6 を使う。見本の形状・寸法値を固定値として流用しない。
- 外形を収めるための図内の縮尺・位置と既存寸法列の最小限の移動を含む。外形と骨組みは同じ縦横比の縮尺で描く。
- 既存の4節点・3部材、節点座標、剛域、寸法値、計算結果を保持する。
- 1ページ目全体の見本への組替え、寸法の追加、ばね記号・ばね表、H1の桁受け／上部工、地盤線、2ページ目以降の変更、GUI・計算式・入力スキーマの変更は含めない。

**New files**

- `src/frame_outline.py` — 方向別の外形座標、図枠へ収める共通座標変換、Canvasへの外形描画。既存ページラッパーには依存させない。
- `./tests/test_frame_outline.py` — 入力からの形状、座標合わせ、非対称寸法、縮尺と描画範囲の小さな検証。

**Modified files**

- `src/longitudinal_report_reference.py` — `_frame` に線路方向の外形と共通変換を組み込む。
- `src/transverse_report_style.py` — `_frame` に直角方向の外形と同じ変換方式を組み込む。
- `./tests/test_longitudinal_report.py`、`./tests/test_transverse_report.py` — 実際のPDF内の外形、骨組みとの位置関係、実線／破線、既存帳票の回帰確認。
- `./README.md` — 外形が現在入力に追従すること、解析モデルとの違いと今回の表示範囲を追記する。
- 最終確認後の再生成対象は0610／0620のPDFと、既存CLIが対で出力する同名JSONのみ。JSONの内容は同一入力の実装前結果と一致させる。

**Dependencies / current-state evidence**

- 既存の ReportLab と PyMuPDF、dev の pytest／pypdf を使い、新規依存は追加しない（`./pyproject.toml:6`）。PDFはベクトル描画を維持する。
- 公開入口は再エクスポートであり、変更は不要（`longitudinal_report.py:3`、`transverse_report.py:2`）。実描画箇所は `longitudinal_report_reference.py:54`、`transverse_report_style.py:65`。
- 形状の根拠は `reaction_report_diagrams.py:134` の `_overall` と `reaction_inputs.py:163` の寸法契約。既存の全体図を直接呼ぶと地盤や追加寸法まで描くため、形状規則だけを再利用する。0600側の描画やその共通化は今回変更しない。
- 帳票が必要とする寸法は計算済み `result["input"]["geometry"]` に存在する（`longitudinal_calculator.py:139`、`transverse_calculator.py:347`）。描画時の入力JSON／見本PDF／Excel再読込は不要。
- 骨組みの節点xは全て0。yは順に `H2+H3+H4+H5+H6`、`H5+H6`、上流0600のフーチング重心高 hG の Single 値、0（`longitudinal_calculator.py:69`、`:159`、`transverse_calculator.py:113`、`:159`）。節点3は物理的なフーチング肩ではない。
- 現在の高さ枠は0610が上232～下676 pt、0620が上200～下610 pt、骨組み軸x=260 pt。寸法列はそれぞれ354／386 pt、348／376 pt（各 `_frame`）。現行寸法のまま単純に外形を追加すると干渉する。
- PDF4点の1ページ目を目視確認済み。現行は骨組みと高さ寸法のみ、見本は薄い点線の外形を併記している。現行は9／17ページ、見本は32／29ページであり、見本の6節点を現行へ移植する作業ではない。
- 共有 `.agents/rules`、`.agents/STATE.md`、`PROGRESS.md`、`.agents/docs/DESIGN.md` は未配置。既存READMEとソースを根拠とし、今回これらの初期化は行わない。

### Implementation Steps

形状と縮尺の不確実性を先に解消し、0610、0620、両方向の回帰確認、実出力更新の順に進める。各段階の検証は一時入力・一時出力を使用する。

#### Step 1: 基準出力を保存し、形状と座標変換を確定する

- [x] ソース変更前に現在入力を `tmp/pier-outline-overlay/` 配下へ同じファイル名 `input.json` でコピーする。同じ入力のバイト列・ファイル名・SHAで既存CLIを0610／0620それぞれ実行し、PDF／JSONと2ページ目以降の比較用画像を一時出力へ保存する。本番outputは変更しない。
- [x] `frame_outline.py` に、入力geometryと方向を受け取る外形座標生成を追加する。単位はmとし、物理高さを底面0、肩H6、基礎天端H6+H5、柱天端+H4、ハンチ天端+H3、梁天端+H2で構成する。H2／H3／H5が0の場合は対応する高さ0の部位を省略し、架空の厚みを作らない。
- [x] 方向別寸法を a1～a9 としたとき、柱幅a6、基礎下面幅a7+a8+a9、基礎上面幅a8、梁上幅a1、梁下幅a1-a4-a5を既存規則から作る。柱偏心 `e=(a7-a9)/2` を用い、既存の基礎中心基準外形をx方向に `-e` 平行移動して、柱中心を解析軸x=0へ合わせる。梁の左右非対称も保持する。
- [x] 骨組みと外形の両方、左の番号欄、右の2列の既存寸法と文字幅を含めて、既存1ページ目の図領域へ収める共通変換を作る。水平は102～535 pt、垂直は0610が232～676 pt、0620が200～610 ptを図の最大領域とし、番号・矢印・寸法文字の実幅と余白を含めて等方縮尺を決定する。基礎底面を下側の基準とし、必要な場合のみ軸を水平移動する。寸法列と補助線の始点は外形右端から余白を空けた位置へ移し、横だけの圧縮や図のクリッピングで収めない。
- [x] 独立に求めた明示的な座標を持つ少数のテスト条件を作る。B／Wで異なる幅、a4≠a5・a7≠a9、H2／H3／H5が0と正の条件、矩形／テーパー基礎、幅広で低い形状を網羅する。H1やhGだけを変えても物理外形の座標が変わらないことを確認する。同じ実装式をテスト側に書き直して正解とはしない。

**Verification**: 新規の形状・変換テストが通る。柱中心0、偏心基礎中心と梁中心の向き、全高さ、入力変更時の座標変化を具体値で確認する。全描画対象が指定領域内に収まり、同じ距離をx／y方向へ変換したときの倍率が一致する。番号・寸法用の余白が残る。本番PDF／JSON・入力は未変更。

#### Step 2: 線路方向の1ページ目へ外形を組み込む

- [x] 共通モジュールにCanvas、外形と変換を受け取る薄い破線描画を追加する。`saveState()`／`restoreState()` で線幅・色・dashを閉じ込める。
- [x] `longitudinal_report_reference.py::_frame` がB方向の外形を先に描き、同じ変換で既存の骨組み、太い剛域、節点、部材番号、高さ寸法を描くようにする。線の濃さは黒いモデルより薄くし、外形は塗りつぶさない。
- [x] 既存の節点番号の間隔調整と補助線を保持する。縮小時に節点・部材番号が近接する場合は、図内で番号の間隔と必要な引出線を調整し、元の節点と対応付ける。見本への節点追加や、外形の肩へ節点3を移す処理は行わない。
- [x] 実際のPDFのベクトル描画から、外形の幅・位置・薄い破線と、モデルの黒い実線が存在することを検証する。テストは既存の公開render入口を通す。0610も0620と同様に、描画時の見本PDF／Excel／入力JSONの読込を禁止する検証を行う。

**Verification**: `test_frame_outline.py` と `test_longitudinal_report.py` が通る。非対称fixtureと既定入力の1ページ目で柱中心・節点1／2／4と物理高さが整合し、節点3は元のhGのままである。既定入力の9ページ、既存寸法文字、SHA表示、結果辞書の不変性を保持し、2ページ目以降がStep 1の同一入力基準と一致する。

#### Step 3: 直角方向の1ページ目へ同じ方式を適用する

- [x] `transverse_report_style.py::_frame` にW方向の外形と共通変換を組み込む。方向の違いは寸法データで表し、別の外形計算式を複製しない。
- [x] 幅広の梁とハンチ、柱・基礎の外形を背面に描き、既存の節点・番号・寸法を前面に保つ。縮小時の番号間隔も0610と同じ基準で確保する。0610／0620の異なるページラッパーは各呼出側でCanvasへ接続する。
- [x] 実PDFでWを使うこと、Bの変更だけでは直角方向の投影外形が変わらないこと、入力幅・偏心・高さの変更が外形へ反映されることを検証する。hGがH6と異なる条件も含める。
- [x] 外形描画の後にdash・灰色がモデル、文字、後続ページへ漏れないことを確認する。

**Verification**: 両方向の帳票テストと形状テストが通る。既定入力の17ページ、595×842 pt、ベクトル描画、外部資料非依存、結果不変、出力決定性を保持する。両方向で縦横比と同じ物理高さへの対応が成立し、0620の2ページ目以降が基準出力と一致する。

#### Step 4: 両方向のPDFを目視確認し、回帰検証と説明を仕上げる

- [x] コピーした入力と一時出力へ既存CLIを再実行する。0610／0620のJSONを同一入力・同一ファイル名の基準JSONと完全比較し、解析値・転記値・provenanceに変更がないことを確認する。
- [x] 既定入力と非対称・幅広の代表入力について両方向の1ページ目を約200 dpiで画像化する。見本と並べ、外形の見分けやすさ、骨組みとの一致、番号・寸法の可読性、図枠・見出し・注記へのはみ出しを目視確認し、必要な図内調整を行う。
- [x] 2ページ目以降は同一入力の基準との画素比較／正規化したベクトル内容の比較で変更がないことを確認する。PDF全体のバイナリ一致を見た目の一致の代用にしない。
- [x] READMEへ両方向の外形表示と入力追従、物理外形と4節点解析モデルの違いを追記する。
- [x] 形状・両方向帳票・両方向計算器の対象テストの後、`& .agents/check.ps1` を実行する。失敗とskipを確認し、今回の変更による失敗を解消する。

**Verification**: 画像確認で意図しない重なり・欠落・外形の変形がなく、黒い骨組みと薄い外形を判別できる。JSON同一、2ページ目以降同一、既定入力9／17ページを確認でき、全体gateが成功する。変更差分がScope内に収まり、計算器・0500／0600・入力・参照資料・他タスクのファイルを変更していない。

#### Step 5: 対象の実出力を更新する

- [x] 全確認後、本番の現在入力で既存CLIの `--stage 0610 --overwrite`、`--stage 0620 --overwrite` を順に実行する。既存のPDF／JSON一括公開・失敗時復旧をそのまま使用する。
- [x] 更新された両PDFの先頭ページを再確認し、同名JSONが今回入力のSHAに一致することを確認する。0500／0600および他PDF／JSONのハッシュが実行前と同じであることを確認する。

**Verification**: ユーザー指定の2 PDFで外形表示を確認でき、対応JSONは同一入力の基準値と一致する。0610／0620以外の成果物は未変更で、最終差分と確認結果を報告できる。

**実装時のコマンド例**

```powershell
# 変更前後の基準生成・検証用。input.jsonは本番入力の同名コピー。
uv run --project "." --locked python "./run_design.py" --input "tmp/pier-outline-overlay/input.json" --output-dir "tmp/pier-outline-overlay/baseline" --stage 0610
uv run --project "." --locked python "./run_design.py" --input "tmp/pier-outline-overlay/input.json" --output-dir "tmp/pier-outline-overlay/baseline" --stage 0620
# 実装後は別のoutput-dir（after）へ出力する。

uv run --project "." --locked --group dev python -m pytest "./tests/test_frame_outline.py" "./tests/test_longitudinal_report.py" "./tests/test_transverse_report.py" "./tests/test_longitudinal_calculator.py" "./tests/test_transverse_calculator.py" -q
& .agents/check.ps1

# 最終確認後の実出力更新。
uv run --project "." --locked python "./run_design.py" --stage 0610 --overwrite
uv run --project "." --locked python "./run_design.py" --stage 0620 --overwrite
```

### Risks & Considerations

- **物理外形と解析モデルの混同**: 見本の節点数やH6肩位置を解析節点へ流用しない。外形は入力geometry、骨組みは計算済みframeを読み、共通変換のみを共有する。
- **偏心の向き・B/W取り違え**: 既存0600の形状規則を根拠に柱中心へ平行移動する。左右対称の現入力だけでは誤りを検出できないため、左右幅が異なる明示fixtureを使う。
- **寸法への干渉と形状の変形**: 実際の左右限界を使用し、番号と寸法列の余白を確保する。図の上下枠・注記・固定フォントサイズを守り、横圧縮や外形の切り取りをしない。極端に幅広の入力も範囲内へ縮小し、少なくとも番号と寸法文字の可読性を維持する。
- **ゼロ高さの部位**: H2／H3／H5を0にできる既存入力契約を保持する。見やすさのために架空の厚みを足さない。
- **線種の漏れと後続帳票の回帰**: Canvasの状態を復元し、背景外形→モデルの順で描く。PDFベクトルと2ページ目以降の比較で検出する。
- **見本との差**: 見本と現在入力は寸法・モデルが異なる。外形の表示方法を参考にし、見本そのものとの画素一致や数値一致は要求しない。
- **検証と納品出力の区別**: 基準生成とテストはtmpで行い、承認された実装の検証完了後だけ本番の対象2帳票を更新する。CLI選択段階の既存動作を変更しない（`cli.py:95`、`:124`）。
- **作業中の他ファイル**: 未追跡の `.agents/docs/plans/p7-pdf-preview-modal-continuous.md` は別作業として保持する。本計画や実装へ取り込まない。
- **計画時の確認限界**: PDF4点の先頭ページの読取・描画確認とコード調査を行った。実装・本番PDFの再生成・実装後テストはまだ行っていない。

### Open Questions

- 対象が「両方向の1ページ目、柱・梁・フーチングの薄い外形重ね描き」であることはユーザー回答で確定済み。技術上の未解決の阻害事項は現時点でない。
- 実装はユーザーの追加指示で承認済み。形状分類を網羅するテストとTDDによる実装・検証・対象出力更新まで完了し、未解決の阻害事項はない。

### Plan Validation

- Status: Complete — ユーザー指定の `$tdd` で実装・検証し、2026-10-15に対象出力を更新済み。
- Codex decomposition: `.agents/logs/codex/20261015T032346Z-plan-pier-outline-overlay-steps.md`。形状・等方縮尺を先行し、0610→0620→回帰確認の依存順、H1／hGからの外形独立性、実PDFの線種と外部読込禁止の検証を採用した。
- Gate 1 — shape: PASS。`plan-doc` の必須5節あり、警告なし。
- Gate 2 — artifact: PASS。下記の解決済みパスに空でない計画書が存在する。
- Gate 3 — adequacy: Codex **PASS**。記録: `.agents/logs/codex/20261015T032931Z-plan-pier-outline-overlay-validate.md`。必須修正・未解決の技術的阻害事項なし。
- Review environment: ネットワークドライブを読めない読み取り専用レビュー環境のため、対象ソース・テスト・計画書の一時ローカルコピーを使用した。レビュー用コピーに含めなかった `.agents/check.ps1` は主担当が原本を確認済みで、P7の全pytestを実行するgateである。
- Gate 4 — user approval: Approved。追加要件は形状パターンの網羅とTDD。証跡は `.agents/logs/pier-outline-overlay-tdd.md`。
- Slug: `pier-outline-overlay`
- Plan path: `.agents/docs/plans/pier-outline-overlay.md`
- Execution: ユーザーの追加指示に従い `$tdd` で完了。証跡 `.agents/logs/pier-outline-overlay-tdd.md`。

### Implementation Verification

- 共通テスト919件（720通りの形状・配置組合せを含む）と両方向帳票テスト35件、合計954件PASS。共通描画処理のカバレッジ99%（基準95%）。`run_tests.py` の最終記録は `outline-green-5-final-coverage`。
- 形状、等方縮尺と配置、Canvas線種・状態復元、Excel互換丸めの桁上がり、節点番号の白下地の5サイクルでRed→Greenを主担当が確認。幅広形状での下地0.5ptはみ出しも既存テストで検出し、余白を修正した。
- `.agents/check.ps1` は overall pass、1597 passed / 1 skipped。Tk初期化でskipした既存GUIケースは単独再実行で1 passed。ログ `tmp/quality-gates/pytest-20261015-130739-9591021.log`、再確認 `outline-final-gui-skip-replay`。
- 既定入力の両PDFと、非対称・幅広／低い・ハンチなしの両方向6例を画像化して目視確認。外形と骨組みは同じ縦横比、番号・寸法は前面に維持した。
- 同一入力の実装前基準と結果JSONが完全一致。両PDFの2ページ目以降は文字・ベクトル内容・画像が完全一致し、9／17ページを維持。証跡 `tmp/pier-outline-overlay/comparison.json`。
- 本番0610／0620のPDF／JSONを既存CLIで更新し、目視確認した一時成果物との一致を検証。他の出力ファイルのハッシュは実行前と同一。証跡 `tmp/pier-outline-overlay/production-verification.json`。
