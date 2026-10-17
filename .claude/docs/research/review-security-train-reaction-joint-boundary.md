---
reviewer: boundary_review_security
date: 2026-10-16
scope: train-reaction-joint-boundary
status: pass
---

# Security / Data Preservation Review

## Verdict

承認された境界修正の製品差分に、Critical / High / Medium / Lowの指摘はない。公開スクリプトも対象6成果物・入力・0500の保持を適切に扱う。レビュー中に検出した候補生成後の別作業によるソース変更3件は、親担当が現ソースで候補を再生成して解消した。レビュー担当が現ソース39件と保護対象11件のハッシュ一致、再生成4JSONの全値一致を再確認し、公開前条件は合格となった。

## Review Scope

- 承認計画、`tmp/train-reaction-joint-boundary/task-only.patch`、`moving_load.py`、`reaction_calculator.py`の本修正provenance文、README、境界試験・固定fixture・既存移動荷重試験。
- `publish_candidate.py`、既存`cli._publish_outputs`、候補before/afterのJSON、開始時manifest、候補生成時sourceハッシュ、親の監査スクリプト・検証結果。
- 入力検証、公開データ形状、依存・外部アクセス・秘密情報の追加、他作業と既存成果物の保持、公開失敗時復元、一時ディレクトリ削除の範囲。

## Findings

None。製品差分についてCritical 0 / High 0 / Medium 0 / Low 0。

## Evidence

- 本修正は所属比較用座標の0.001 m偶数丸めと、丸め後0となる正の継目の原座標保持に限定。公開dataclass・結果キー・入力バリデーション・候補列挙・最大値更新条件・腕長計算は変更されていない。新たな入力下限もない。
- 不正寸法・非有限値・車両数・荷重underflow等の既存試験を保持。極小寸法の既存InputErrorも残り、有効右桁の原点所属を追加試験で確認する構成になっている。
- 4段階のbefore/after JSONを独立に再帰走査し、値の型・辞書キー・リスト長が一致し、浮動小数値が有限であることを確認した。
- レビュー時点で入力、正式output全体、assets、pyproject.toml、uv.lockは開始時manifestと一致。正式成果物をレビュー作業で変更していない。依存・ネットワーク・外部実行・認証情報を追加する製品差分はない。
- 公開前にcandidate-source-hashesの全ソース・入力、開始時manifestの入力・0500・公開先6成果物、JSONのinput_sha256を検証する。候補は0600/0610/0620のPDF/JSONだけを選び、6件を要求する。
- 公開先は現在通常ディレクトリで、既存`_publish_outputs`が公開先symlink・非通常ファイルを拒否する。旧成果物を全てstagingへ退避してから新成果物を移し、OSError時は復元する。復元にも失敗した場合は`_RecoveryError`を捕捉してstagingを保持する。
- stagingは公開先の下でmkdtempしてresolveし、削除直前にも`staging.parent == output`を確認する。0500は公開対象に含まず、公開後に入力・0500ハッシュを再確認する。新成果物は候補とのバイト一致を検証して記録する。
- 親の全体ゲートログを読み、2697 passed / 1 skippedを確認。Tk環境依存のskipが残る。全体試験は指示どおり再実行していない。

## Concurrent Change Detected

候補生成時のソースハッシュと現在値が次の3件で不一致だった。公開スクリプトの事前検証はこの状態を拒否するので、既存成果物の上書きは起きていない。

- `longitudinal_calculator.py`: 雪handoff検証と組合せ追加を関数抽出。
- `reaction_calculator.py`: ブレーキ/始動計算・係数計算を関数抽出し、通常行と雪行の支承荷重ループを統合。本修正のprovenance文は保持。
- `reaction_report_horizontal.py`: 支承・地震説明、表罫線・数値セルを関数抽出し、Callable型を追加。

これは本境界修正の欠陥ではなく、同一作業領域の別作業による公開前条件の変化である。親担当へ即時通知し、他作業を維持した再生成・再照合が必要であることを共有した。

再確認結果: `candidate-source-hashes.json`の現ソース・入力39件が全て一致し、入力・正式output・assets・依存ファイルからなる保護対象11件も開始時manifestと一致。`after-first-verified`と再生成後`after`の4JSONは全値・形状・有限性・input_sha256が一致した。親の`concurrent-refactor-verification.json`では4PDF計61ページの文字と1.35倍描画の全画素一致も確認されている。公開停止の理由は解消済みである。公開直前・直後の再確認は引き続き既存公開スクリプトが実施する。

## Context

context-loader: rules 0、STATE未作成、missing=[".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]、unreadable=[]、warnings=["DESIGN.md is still the uninitialised /init template; run /init to populate it"]、design.placeholder=true、progress.entries=0。承認計画に記載済みの条件としてレビューを進めた。
