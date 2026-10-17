## Implementation Plan: Train Reaction Joint Boundary

作成日: 2026-10-16 / slug: `train-reaction-joint-boundary`
状態: 2026-10-16 実装・検証・成果物更新完了。

### Purpose

共通の移動荷重計算にある桁継目の所属判定を修正し、Example橋脚2/07_荷重計算.pdf の7-1に示された列車反力 RA/RB/RC/RD = 367.53/272.47/294.92/25.08 kN を再現する。確認済みのユーザー方針に従い、同じ境界判定を使う車両横荷重と後続の0610・0620にも一貫して修正を反映する。

### Scope

- New files:
  - `./tests/test_moving_load_boundary.py`: 小数継目、Example条件、反力釣合い、共通計算と後続転記の回帰試験。
  - `./tests/fixtures/moving_load_boundary_cases.json`: Exampleの寸法・載荷位置・独立算定値、および影響する長支間ケースの根拠。現行の可変input.jsonに依存しない固定試験条件。
  - 診断・候補成果物・PNG・確認記録は `tmp/train-reaction-joint-boundary/` に保存する。
- Modified files:
  - `src/moving_load.py`: 継目の所属比較を既存の0.001 m位置グリッドに統一し、VBA完全一致という説明に境界修正の例外を明記する。
  - `src/reaction_calculator.py`: provenance.methodの計算方式説明に境界補正を明記する（計算・データ形状は変更しない）。
  - `./tests/test_moving_load.py`: 旧Single oracleと意図した境界修正の差を区別する。影響のない比較は引き続き厳密に検証する。
  - `./README.md`: 境界判定の数値精度と旧Excelとの差、Example検証条件を簡潔に記載する。
  - 検証済みの `./output/0600_上部工反力.{json,pdf}`、`0610_線路方向荷重.{json,pdf}`、`0620_直角方向荷重.{json,pdf}` を最終更新する。
- Dependencies: 既存Python、pytest、PyMuPDF、ReportLabを使用。依存追加なし。
- 検証する連携先: `reaction_calculator.py`、`reaction_report.py`、`cli.py`、`longitudinal_calculator.py`、`transverse_calculator.py`。公開データ構造を維持し、上記のprovenance説明変更を除き、これらの計算・帳票実装は変更しない。
- 対象外: 車両横荷重の荷重修正係数、風荷重モデル、重心高、雪・シェルターの扱い、荷重組合せ、構造解析・部材照査の新設。実入力、元Example PDF/Excel、既存のExcel oracle/legacy oracle、帳票レイアウトは変更しない。0500成果物は更新しない。

確定条件と調査根拠（以下の製品相対パスは `./` 基準）:

- `pier_design/moving_load.py:71-104,123-160`: Single演算の継目 `la` と、小数3桁に丸めた候補位置を直接比較している。(.575,18.85,.575)の合計が20.000001907348633となり、位置20.0の軸がB側になる。最大化対象はRB+RC、全軸・全7点を列挙し、同点は先行候補を保持する。継目一致時は大きい反力側、同値ならCを選ぶ。
- `tests/test_moving_load.py:20-47`: 旧独立Single oracleと整数10 m継目の試験はあるが、小数継目の丸め差を網羅していない。長支間(.85,72.6,.85)×2、軸重150 kNの既存ケースは今回の一般修正で変化し得る。
- `tests/test_reaction_calculator.py:55-69`: 保存済み6ケースのcells/public/macroを比較する。事前のメモリ内診断では6ケースは不変だったが、採用実装でも再確認する。`tests/test_reaction_cli.py:84-89` の既存反力期待値も確認する。
- `pier_design/reaction_calculator.py:288-298`: 車両横荷重もsearch_reactionsを使用し、軸重×安全性係数×0.2を小数2桁に丸める。
- `pier_design/longitudinal_calculator.py:3-4,136`: 後段は荷重計算であり、構造解析・部材照査まで完了したとは扱わない。
- 調査時の `pre/input.json` SHA256は `e5fc4d946ebd941489df0d6d290f3aff9d2860d853ac3e73e50c6d3efa1926d6`。安全性係数は現在1.231で、前回比較の1.23から更新されている。既存入力値を保持し、前回条件を復元するために実入力を変更しない。
- 入力、reaction_report.py、reaction_report_pagination.py、test_reaction_report.py、0600/0610/0620成果物等に開始前から差分がある。計画承認後の実装開始時に再採取し、他作業を取り消さない。

### Implementation Steps

計画承認後、以下の4段階を依存順に実施する。

#### Step 1: 基準と独立した期待値を固定する

- [x] 実装開始時の差分、入力・対象コード・ロックファイル・0500/0600/0610/0620成果物のSHA256と既存テスト結果を記録する。外部変更があれば現在状態を正として基準を取り直す。
- [x] Example固定ケースを作る。寸法は(.575,18.85,.575,.375,9.25,.375) m、車長20 m、軸距a1=2.8/a2=2.2 m、軸重160 kN。載荷列は現入力と同じ10両を基本とし、係数は前回比較用1.23と現条件1.231を明示して分離する。
- [x] Exampleの採用位置(22.2,20,17.2,15,2.2,0)とPDFのモーメント釣合い式から4反力を独立に算定する。製品search_reactions/_reactionsの再利用や現在出力のコピーを期待値の根拠にしない。
- [x] 旧長支間oracleの変化を、継目の所属・採用位置・RB+RC最大値から独立に確認する。旧証拠は保持し、新しい期待値の出典と変更理由をfixtureに残す。

**Verification**: Exampleの表示値4点を得る。各桁についてRA+RBおよびRC+RDが所属軸重合計と一致し、全体の総軸重も保存される。長支間の期待値は正規化した製品コードの出力だけで確定しない。現入力の係数と固定ケースの係数が明確に識別できる。

#### Step 2: 境界試験を追加し、比較処理を最小修正する

- [x] 修正前にExampleの反力と継目所属の回帰試験が意図した原因で失敗することを確認する。
- [x] 所属比較に用いる軸位置と継目を、既存と同じ小数3桁・ties-to-evenの座標グリッドにそろえる。判定座標だけを正規化し、反力の腕長に用いる元寸法、Single反力演算、候補生成・列挙順は維持する。Example専用の寸法条件や期待値をコードへ埋め込まない。
- [x] 継目ちょうど、前後0.001 m、継目に対するSingle丸め誤差の正負、非対称支間、張出しゼロ、負の張出し反力、ゼロ荷重を検証する。継目一致でB/Cどちらの反力が大きい場合も試験し、同値時Cを維持する。
- [x] MovingLoadResultの形状、contributions、candidate_count、厳密なscore更新、既存の入力エラー処理を維持する。境界に影響されないケースは厳密一致を維持する。

**Verification**: ExampleのRA/RB/RC/RDが367.53/272.47/294.92/25.08 kNとなり、採用位置と軸の所属も一致する。±1 mmを継目と誤認せず、各軸がちょうど一つの桁に属する。中間Single値を小数第2位表示と混同せず、独立算定との許容差を値ごとに明記する。

#### Step 3: 共通利用と旧oracleへの影響を検証する

- [x] 旧4移動荷重ケースを全て実行する。長支間の境界修正で説明できる変更だけを独立根拠付き期待値へ移し、既存legacy oracleや保存済みExcel fixtureは書き換えない。テストの削除・一括許容差拡大で通さない。
- [x] 保存済み6ケースのcells/public/macro、既存CLI試験を再実行する。差が出た場合は原因を個別に追い、影響なしと事前判断した値の不一致を無条件に受け入れない。
- [x] 車両横荷重の1.23ケースは横軸重39.36でHB/HC=64.83/72.55 kN、1.231ケースは39.39で64.88/72.61 kNを検証する。Exampleの52.71/58.98に合わせるために係数を変えない。
- [x] 0600から0610/0620へ渡す反力・衝撃・水平荷重を独立計算と照合する。少なくとも線路方向の列車反力由来の摩擦候補/採用水平力、直角方向の車両横荷重による基本荷重・組合せを追跡する。転記が両側で同じ誤値でも合格する比較だけにしない。
- [x] 入力、死荷重、雪荷重、桁衝撃係数、地震時列車荷重、風荷重、重心高、荷重組合せの定義を維持する。く体衝撃低減や列車由来の反力値は上流修正に伴い変化し得るため、不変対象と分ける。

**Verification**: 係数ごとの横荷重、4鉛直反力、代表的な後続荷重を独立数値で確認し、JSON公開キーとデータ形状が不変である。旧値との差を「境界修正による派生値」と「不変値」に分けた記録を残す。構造解析や部材照査の検証完了とは報告しない。

#### Step 4: 帳票・全体試験を確認して成果物を更新する

- [x] 実装時点の入力のコピーを一時領域で固定し、0600/0610/0620を候補出力へ生成する。実入力と候補provenanceのSHA256を照合する。
- [x] 0600の列車載荷図・反力式・支点値、車両横荷重図の2軸/2軸所属、線路方向まとめ、および0610/0620の該当荷重・組合せをPDF文字抽出とPNG目視で確認する。見出しでページを特定し、旧31ページ等を固定条件にしない。
- [x] `uv run --project . --locked --group dev python -X utf8 -m pytest ./tests/test_moving_load.py ./tests/test_moving_load_boundary.py ./tests/test_reaction_calculator.py ./tests/test_reaction_cli.py -q` を実行する。
- [x] 最終の全体試験は `.agents/check.ps1 -ProjectRoot 'K:\ニュージャパンコンサルタンツ\26_LRT鉄道照査'` で行う。新しい故障・変更がない限り、同一全体試験を重複実行しない。
- [x] 独立レビューで修正範囲・境界条件・期待値の独立性・既存差分保持を確認する。最終公開前に入力・対象コード等の外部変更を再確認し、更新があれば候補を作り直す。
- [x] CLIには3段階をまとめて指定する選択肢がないため、候補は --stage all --output-dir tmp/train-reaction-joint-boundary/after で生成する。正規公開は一時スクリプトから既存cli._publish_outputsへ対象6ファイルだけを渡し、出力ディレクトリ内stagingと失敗時復元を再利用する。CLIに新しい機能を追加せず、検証済みの0600/0610/0620のPDF/JSONを一式として更新する。0500のバイト列は保持する。更新後のprovenance、候補との内容一致、入力不変、開始前差分の保持を確認する。

**Verification**: 対象試験と全体ゲートが合格し、PDFの数式・図・数値がJSONと一致する。6成果物が同一入力に基づき、0500と入力が不変。最終報告でExample一致4反力、維持した係数、横荷重の派生変化、後段の検証範囲を明示する。

### Risks & Considerations

- グローバルな丸めや全演算の倍精度化は候補選定や既存Single互換性を広く変える。所属比較だけの修正とし、腕長などの幾何演算は維持する。
- 共通修正によりExample以外の小数継目も変わる。特に既存長支間ケースを既知の影響として検証し、旧oracle一致を全ケースへ無条件要求しない。
- 現入力は他作業で変更され得る。Exampleの固定試験と実入力による成果物検証を分離し、係数1.231を1.23へ戻さない。実装時にさらに入力が変わった場合も、その現行値に対する独立期待値を算定する。
- 外部変更と競合する帳票ファイルを変更対象に広げない。入力/表示/組合せの別修正を取り込んだ現在状態を保持し、正規成果物の古い候補による上書きを防ぐ。
- アプリの横荷重をExampleに完全一致させるには別の係数変更が必要だが、今回は行わない。風・桁地震作用高さ・Example7-9/7-11の扱いも変更しない。
- 共通rules/STATE/PROGRESS/DESIGNは未作成。既存README・コード・テストと本計画の確定条件を根拠とする。追加依存や実行時Excel依存は導入しない。
- 計画段階では製品コード、入力、成果物を変更しない。上記Step 1以降の実装作業は計画承認後に開始する。

### Open Questions

- 技術的な未確定事項なし。共通境界判定を修正し、現在の荷重修正係数・風・重心高条件を維持する範囲はユーザー確認済み。
- 2026-10-16 ユーザーが「承認」と回答し、実装を開始した。

検証記録:
- 現状調査: `.agents/logs/codex/scan-plan-train-reaction-joint-boundary.md`。診断値は独立した期待値の代わりにしない。
- 手順分解のCodex相談: `.agents/logs/codex/20261016T011512Z-plan-train-reaction-joint-boundary-steps.md`
- Gate 1: validate_doc.py --contract plan-doc 合格、warnings=[]。
- Gate 2: workspace.py --skill plan --slug train-reaction-joint-boundary --verify 合格。
- Gate 3: Codex PASS。`.agents/logs/codex/20261016T011922Z-plan-train-reaction-joint-boundary-validate.md`。
- Gate 4: 2026-10-16 ユーザー承認済み。team-executeで実行、slug: train-reaction-joint-boundary。




### Execution Evidence (2026-10-16)

- 実装開始時の入力SHA256: `451564d22e112ab0825431785a533b91c509459f216350e4200a3e64d7c0f50b`。係数1.231、現在の風・作用高さを保持。計画調査時のSHAと異なるため開始時点を固定した。
- 基準コード・入力・成果物123ファイルを `tmp/train-reaction-joint-boundary/baseline/` とbaseline-manifest.jsonへ記録。
- 初回全体試験はGUI付近の長時間実行を中断し、合格とは計上しない。`baseline-gate-note.txt`参照。最終全体試験はTcl/Tkパスを明示して完了。
- ExampleのREDを確認後に共通比較だけを修正。追加検証で、正の継目が0.001m丸めにより原点へ潰れる場合にはraw laを保持して既存挙動を維持した。新しい寸法制限はない。
- テスト担当の対象38件合格、実装担当の関連64件合格。極小寸法4ケースも開始前と一致。旧Excel6ケースは不変。
- 候補PDF/JSONを同一入力で再生成。`candidate-verification.json`に0600/0610/0620の全変更葉と不変項目を記録。0500の計算結果は不変。
- 変更PDFページのPNGを確認済み。`visual-qa.md`、`qa/`参照。
- 所有権reconcile: overlaps=[], unowned_changes=[], idle_owners=[]。許可した例外は開始前差分と他作業の生成物のみで、入力・帳票コードのハッシュ不変を別途確認。
- 親担当が計画指定4テストファイルを再検証: **92 passed in 14.83s** (exit 0)。
- 作業範囲のtrackedソースに対するgit diff --checkは合格。リポジトリ全体では既存のsimplify-scope.patchやPDFをテキストとして扱う空白警告があり、本修正対象とは切り分けた。
- 最終全体ゲート: `.agents/check.ps1` exit 0、overall `pass`、**2697 passed, 1 skipped in 682.20s**。ログ `tmp/quality-gates/pytest-20261016-104412-0671900.log`。ツールオブジェクトは `tmp/train-reaction-joint-boundary/integration-report.md` に保存。スキップは既存GUI試験の一時的なTk読込み不可。
- 全体でスキップされたGUI関数を対象に限定して再実行し、4パラメータすべて合格 (**4 passed in 21.99s**, exit 0)。`gui-retry.txt`参照。全体再実行なしでスキップ対象の確認を完了。
- 公開前sourceチェックで別作業の整理3ファイル（longitudinal_calculator.py、reaction_calculator.py、reaction_report_horizontal.py）を検出。新コードを保持して候補を再生成し、4JSON全値および全61ページのPDF文字・1.35倍画素が確認済み候補と完全一致。`concurrent-refactor-verification.json`参照。関連11テストファイルを追加実行して統合を確認する。
- 最新版の関連11テストファイル: **255 passed in 46.98s**, exit 0。外部整理後の計算/帳票/CLI/雪荷重/後続連携を再検証。
- 独立security/quality/testsレビューは全てPASS、Critical/High/Medium/Low指摘0。`.agents/docs/research/review-{security,quality,tests}-train-reaction-joint-boundary.md`。5担当worklogおよびworkspace検証合格。
- cli._publish_outputsで0600/0610/0620のPDF/JSON計6ファイルを正式outputへ更新済み。候補と公開物のSHA256全一致、入力と0500は開始時バイト列を維持。`published-verification.json`参照。
- 検証結果: RA/RB/RC/RD = **367.53 / 272.47 / 294.92 / 25.08 kN**（Example7-1一致）。係数1.231を維持した車両横荷重HB/HC = **64.88 / 72.61 kN**。後段の検証範囲は荷重・基本ケース・組合せ・帳票であり、構造解析/部材照査を新たに実施したものではない。
