# Quality Review: Train Reaction Joint Boundary

Date: 2026-10-16
Reviewer: boundary_review_quality
Verdict: PASS — High 0 / Medium 0 / Low 0

## Review Scope

承認済み計画 `.agents/docs/plans/train-reaction-joint-boundary.md` と、開始時スナップショットとの差分 `tmp/train-reaction-joint-boundary/task-only.patch` を基準にレビューした。

- `P7橋脚/pier_design/moving_load.py`
- `P7橋脚/pier_design/reaction_calculator.py` の provenance.method 変更
- `P7橋脚/README.md` の本修正による追記
- `P7橋脚/tests/test_moving_load.py`
- `P7橋脚/tests/test_moving_load_boundary.py`
- `P7橋脚/tests/fixtures/moving_load_boundary_cases.json`

HEADとの差分に含まれる開始前の入力・帳票・出力変更は本修正に帰属させていない。成果物の公開、PDF表示、入力ファイル不変の最終確認は親担当の責務とした。

## Findings

None. 修正が必要な品質上の問題は見つからなかった。

## Assessment

1. `_reactions` の比較座標だけを `Single(round(value, 3))` に統一している。`left_distance`、`right_position`、`right_distance` には元の `position` / `la` / `lb` が残り、力の加算や反力計算のSingle丸めも変更されていない。Example固有の長さや反力値は製品コードに追加されていない。
2. 正の継目が0へ丸まる場合にraw座標を維持する例外は、原点の軸を誤って右桁へ載せる回帰を防ぐ。公開探索が生成する候補位置は既に同じグリッドで丸められているので、この場合は従来の所属比較に戻る。新しい寸法下限を設けず、既存の極小寸法エラーと有効な小寸法検索の双方を試験している。
3. 継目一致時の大きい反力側、同値C側、軸と7点の列挙順、`score > best.max_rb_rc` による更新規則を維持している。新試験は継目前後1 mm、正負のSingle誤差、偶数丸めの上下、非対称桁、同値C、張出しによる負反力を確認する。
4. Example期待値は小数寸法と載荷位置をFractionへ変換した支点モーメントと荷重総和から求めており、製品反力関数を期待値算定に再利用していない。長支間については独立した有理数のイベント探索で最大値 `330050/121` と4つの数学的最適配置を求め、製品の配置がその集合に含まれること、個別反力・所属・釣合いを確認する。旧Single結果を保存したうえで意図した境界変更を検証しており、全試験の許容差を一括で広げていない。
5. 係数1.23 / 1.231を別ケースとして検証し、0610の摩擦候補・採用水平力、0620の横荷重H/M・組合せ係数も独立数値と比較している。provenanceとREADMEは「元VBAと完全一致」からの限定的な例外を説明し、コードの実挙動と一致する。

## Verification Evidence

- 親担当の全体ゲート: `.agents/check.ps1` exit 0、overall passの報告を受領。`tmp/quality-gates/pytest-20261016-104412-0671900.log` の末尾を直接読み、**2697 passed, 1 skipped in 682.20s** を確認した。Tk初期化に関するskipを合格扱いしていない。
- 親担当の計画指定4ファイル重点試験: **92 passed in 14.83s**、exit 0。
- 本レビューではコード・計画・独立期待値を静的確認し、同一全体試験を重複実行しなかった。
- Coverage: not measured。ruff: not installed。未実施の項目を合格と見なしていない。

## Context and Limitations

context-loaderの結果は rules 0件、STATE未作成、missing=[".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"], unreadable=[], warnings=["DESIGN.md is still the uninitialised /init template; run /init to populate it"], design.placeholder=true, progress.entries=0。承認済み計画がこの欠落を明示しているため、その確定条件と実装・README・テストを根拠にした。

本判定は境界修正の実装品質についてのもの。構造解析・部材照査の安全性判定を意味しない。小規模な比較処理の変更を直接レビューしたため、追加のCodex CLI相談は行っていない。
