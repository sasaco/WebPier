# calc 層の規約

`webpier/calc/` に段階ごとの計算を書くときの約束。原則は docs/adr/0001〜0004 と
`.claude/docs/plans/refactoring-decisions.md`（決定事項）を正とする。手本は `webpier/calc/foundation.py`。

## 値

- 計算書に印刷する値は、すべて `webpier.core.printed.Printed` にする。`Precision(digits, unit)` で作る。
  桁は Example2 の計算書（.claude/docs/Example橋脚2）が印刷している桁に合わせる。共通の桁は `core/printed.py` の
  `LENGTH`・`FORCE`・`MOMENT` などを使い、段階固有の桁はそのモジュールの先頭に `Precision` として定義する。
- 後続の式は、印刷された値（`.value`）から計算する。丸める前の値を後続に渡さない。
- 合計は `Precision.total(parts)` で、印刷された部分の和にする。
- 印刷しない中間値は作らない。反復探索（移動荷重）だけは内部を丸めず、採用した結果を丸める。
- 元Excelのセル番地、`cells`、`macro_handoff_single`、VBA Single、Excel ROUND、偶数丸めは使わない。
- 係数や式の定数（0.27、1/3 など）は名前付きの定数にし、出典（基準の条番号や Example2 の頁）をコメントに書く。

## 結果

- 結果は `@dataclass(frozen=True)` の型で返す。辞書を受け渡さない。意味のある英語名を付け、日本語の
  ラベルや文言は持たない（印刷の文言は reporting の責務）。
- 前段の結果は型のまま受け取る（例：0610 は 0600 の結果型と `FoundationResult` を引数に取る）。
  前段の結果を検証し直したり、ラベル文字列で照合したりしない。
- 骨組（節点・部材）は計算の一部として型で返す。描画用の座標や文字配置は持たない。

## 入力とエラー

- 入力は `webpier.inputs.PierInput` だけを受け取る。入力の欠落や形式の誤りは parse で済んでいる。
- 計算中に成立しない条件（0除算、適用範囲外、非有限）は `InputError` にし、原因の入力パスか式を文言に含める。
- 欠けた値を補ったり、既定値で置き換えたりしない。

## テスト（TDD）

- 先に失敗するテストを書き、失敗を確認してから実装する。テストは `tests/calc/test_<段階>.py`。
- 期待値は二種類だけを使う。
  1. Example2 原資料から独立に転記した値（`tests/fixtures/example2/*.json`）。実装の出力から作らない。
  2. 実装の関数を使わない手計算（`Decimal` と `ROUND_HALF_UP` で丸め）。
- 入力は `tests/fixtures/inputs/current.json` を基に、変えたい項目だけを書き換えて作る。
- 境界、ゼロ、符号の反転、上下線の入替え、非対称な形状、適用範囲外のエラーを含める。
- 層の境界テスト（`tests/test_layer_boundaries.py`）を通す。calc は core と inputs 以外を import しない。

## 旧実装の扱い

- `src/` の旧実装は工学的な手順の参考として読んでよい。ただし、元Excelの誤りや互換のための分岐は持ち込まない。
  README の互換一覧は決定20で空になった。元式の互換動作として残すものはない。
- 決定事項で直すと決めた点（ハンチ重心、桁受けの重量集計、直角方向モーメントへの桁受け、上載土の xL、
  可動支承の下限 μ·T/n、風の受風幅と地表面、複線衝撃の適用範囲、欠けた値の補完の廃止）は新実装で直す。
- 旧実装と新実装で値が違う場合、どちらが正しいかを Example2 と手計算で判断し、判断を報告する。
