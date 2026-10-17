# Test Review: Train Reaction Joint Boundary

Date: 2026-10-16  
Reviewer: boundary_review_tests  
Verdict: PASS  
Coverage: not measured

## Review Scope

- 承認計画 `.agents/docs/plans/train-reaction-joint-boundary.md`、開始前スナップショット、`tmp/train-reaction-joint-boundary/task-only.patch` を基準にレビューした。他作業を含むHEAD差分を今回の変更と混同していない。
- 対象は `./tests/test_moving_load_boundary.py`、`tests/fixtures/moving_load_boundary_cases.json`、`tests/test_moving_load.py`、`src/moving_load.py`。下流の組合せデータ形状は `src/transverse_calculator.py` でも確認した。
- Coverage: not measured。測定済みの網羅率を示すものではない。

## Findings

None。High / Medium / Low の修正要求なし。

## Assessment

- Exampleの4反力は、固定寸法・固定載荷位置・桁所属からFractionで支点回りのモーメントを計算している。製品の `_reactions` / `search_reactions` を期待値生成へ再利用しておらず、表示4値・桁別釣合い・負の張出し寄与・候補数を別々に検証する。
- 正負Singleノイズ、継目前後1 mm、ties-to-evenの上下、B/Cそれぞれが大きい継目、同値C、張出しゼロ、原点へ丸まる極小継目を確認する。極小桁の既存InputErrorと、極小左桁＋有効右桁の成功を双方保持している。ゼロ荷重・不正入力・探索同点の先行候補維持は既存テストが継続して担う。
- 旧長支間の値はfixtureに証拠として保存し、旧oracleを新出力で上書きしていない。新期待値は有理数の軸列と全支点接触候補から独立に最大値を求める。数学的同点4配置とSingle演算による採用配置を分離し、4反力・36軸の釣合い・所属も確認する。個別0.0003 kN、最大値0.001 kNの絶対許容差は小数2桁の表示精度より厳しく、relative toleranceも0に限定されている。
- 係数1.23と1.231は固定条件として分離され、横軸重39.36/39.39とHB/HCの独立モーメントが確認される。可変の実入力に依存しない。
- 0610は独立算定の局所摩擦64.49/68.98 kN、固定側候補、採用力、転記Single値を検証している。0620は基本荷重H/MとAMの1.1係数を確認する。0620の製品出力は組合せ係数表までであることも確認し、この試験を構造解析や部材照査の検証とは扱わない。
- テスト内の入力は毎回新しくparse/replaceされ、可変グローバルの変更や順序依存は見当たらない。今回の変更範囲には外部サービス依存がない。

## Test Execution Results

- 親の全体ゲート実行ログ `tmp/quality-gates/pytest-20261016-104412-0671900.log` を読み取り確認: **2697 passed, 1 skipped in 682.20s**。親報告のゲートexit 0、overall pass。
- 1 skipはTk初期化環境のため。親が当該関数 `test_editor_formulas.py::test_all_derived_cells_are_bound_but_readonly_and_not_editable_fields` の全4パラメータを再実行し、**4 passed in 21.99s、exit 0** と報告。全体ゲートを重複実行していない。
- 親の計画指定4ファイル試験: **92 passed in 14.83s、exit 0**。実装試験担当の対象2ファイル: **38 passed in 2.97s、exit 0**。
- レビュー中に新たな故障の懸念が出なかったため、本担当による同じ試験の重複実行は行っていない。
- Coverage: not measured。ruffは環境にないため未実行であり、passとは記載しない。

## Context Notes

context-loaderを実行した。rulesは0、STATE未存在。missing=[".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"], unreadable=[], warnings=["DESIGN.md is still the uninitialised /init template; run /init to populate it"], design.placeholder=true, progress.entries=0。承認計画がこれらの未整備を明記しているため、その計画・README・コード・テストを根拠として独立レビューした。
