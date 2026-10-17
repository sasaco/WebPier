# Operations and artifacts

## Operation selection

| Operation | Required section | Artifacts |
|---|---|---|
| pile | 基本 document | `result.json`、任意の `report.pdf` |
| sdc | 基本 document + `sdcExport` | `result.json`、通常版および条件に応じたL1/L2 `.sdc` |
| ground | 基本 document + `groundDisplacement` | `result.json`、任意の PDF/JOT |

現行 SDC exporter は pileType 4/5/6 を受理する。pileType 5 は工法コード6の回転杭として扱い、鋼管外径・厚さ・腐食代、杭列、羽根径を明示入力から検証する。

## Standalone Headless

runner contract を現行 README または `get_runner_contract` で確認する。代表的な command は次のとおり。

```text
validate --input <json> --output-dir <empty-dir> --operation pile|sdc|ground
run --input <json> --output-dir <empty-dir> --generate-pdf true|false
export-sdc --input <json> --output-dir <empty-dir>
run-ground-displacement --input <json> --output-dir <empty-dir> --generate-pdf true|false --generate-jot true|false
```

各 command は空の出力 directory を要求する。pile と sdc を続けて行う場合も別々の一時 directory を使う。

stdout は protocol v1 の JSON envelope 1個で、`protocolVersion`, `engine`, `engineVersion`, `ok`, `summary`, `artifacts`, `errors` などを持つ。失敗時も stdout の envelope を解析し、exit code だけで理由を推定しない。

## Artifact validation

artifact descriptor の `kind`, `mediaType`, `relativePath`, `bytes`, `sha256` を検査する。

- PDF: kind `report`、media type `application/pdf`、先頭 `%PDF-`
- SDC: kind `sdc`、media type `text/plain; charset=shift_jis`、CP932 strict decode、CRLF
- JSON: UTF-8（BOMなし）

`relativePath` は一時出力 directory 内に解決されることを確認する。全成果物を検証後、同一 volume 内で atomic replace して最終配置する。

## MCP workflow

利用可能なら live schema/capabilitiesを取得し、対象 operation の validation、計算、artifact materialization の順で行う。materialize 前に manifest の bytes と SHA-256 を照合する。MCP job artifact ID は pile PDF が `report`、通常 SDC が `sdc` である。
