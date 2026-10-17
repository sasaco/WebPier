# Evidence source map

## Confidence labels

- `observed`: 現行 source、live schema、実入力、実成果物から直接確認。根拠パスまたは tool 名を付ける。
- `verified`: 回帰 test、live validation、再現可能な実行で確認。commit 済みか current worktree 検証かを区別する。
- `inferred`: 複数の observed / verified 事実から導出。設計値、単位、enum、必須性の補完には使わない。
- `unknown`: 根拠不足。推測で昇格させない。

## Priority

契約は次の順で判断する。

1. 現在の live schema / validation / runner contract
2. 現行 SoilStructure 実装と回帰 test
3. この skill に保存した snapshot
4. sample JSON と過去成果物

設計値は次の順で判断する。

1. 対象リポジトリの `AGENTS.md` が指定する authoritative input
2. ユーザーが明示した値
3. 根拠付きの既存入力
4. 不明なら確認。過去成果物から逆算しない

## Primary source files

- `SoilPile/Execution/SoilStructureDocument.cs`
- `SoilPile/Execution/SoilStructureRequestFactory.cs`
- `SoilPile/Execution/SoilStructureFeatureRequestFactory.cs`
- `SoilPile/Reporting/Validation.cs`
- `SoilPile/Reporting/Sdc/SdcFileExporter.cs`
- `SoilStructure/Headless/Program.cs`
- `SoilStructure/Headless/README.md`
- `SoilStructure/Headless/tests/*.cs`

2026-09-30時点の `validate` command、回転杭 SDC 出力、関連 schema は current worktree で検証された変更を含む。回転杭出力は SoilStructure Release build と22件の回帰テスト、および実Headless生成で確認した。コミット済み仕様と表現せず、更新時は live contract と tests を再確認する。
