---
name: webdan-wdj
description: Create, edit, inspect, or validate Capacita/WebDan RC input files in .wdj JSON format. Use when translating engineering conditions into a WDJ, changing section/rebar/material/force settings, checking WDJ consistency, or preparing input for structural-mcp webdan_calculate. Do not use for .sdc/.ndu files or for post-processing solver results.
---

# WebDan WDJ

Capacita（旧 WebDan2）の RC 断面照査入力 `.wdj` を、根拠のある既存 WDJ またはバージョン固定テンプレートから作成・更新する。
`.wdj` は JSON だが、単なる JSON パッチではなく、部材・算出点・配筋・材料・断面力の参照関係を保つ。

## Reference routing

- 新規作成、更新、入力不足の判定では [references/input-contract.md](references/input-contract.md) を読む。
- request JSON の作成・検査では [references/request.schema.json](references/request.schema.json) を正とし、未定義フィールドを通さない。
- この案件の base 継承例には [references/fastening-device-request.json](references/fastening-device-request.json) を使う。この例は上下配筋を既存 WDJ から踏襲し、芯かぶり・鉄筋間隔・断面力など未記載値を変更しない。
- `structural-mcp` の不足機能を評価・提案するときだけ [references/structural-mcp-request.md](references/structural-mcp-request.md) を読む。

## Required workflow

1. 対象リポジトリの `AGENTS.md` と生成物ルールを確認する。`05_output/` のような生成先は手編集しない。
2. 計算またはエンジン検証の前に `structural-mcp.get_capabilities` を呼び、Capacita の readiness を確認する。
3. 既存 WDJ を基にする場合は JSON として読み、トップレベル構造、モード、適用・仕様、対象部材、算出点、断面力、配筋、材料、計算対象を要約する。大きな WDJ の判定に PowerShell `ConvertFrom-Json` を使わない。
4. 入力条件を [input-contract.md](references/input-contract.md) に沿って整理する。工学的に必要な値が欠け、信頼できる base WDJ にも無い場合は推測せず、欠けている値をまとめて確認する。
5. base WDJ と request JSON を用意し、`scripts/build_wdj.py` で別の出力先へ生成する。生の文字列置換や無差別な JSON merge は行わない。
6. 同じスクリプトの `--check-only` で構造・参照・主要値を検査する。サマリーの `validation.requestComparison` が全依頼 leaf を `matched` とし、コンクリート・断面力・計算項目・継承値も表示されることを確認する。可能なら `webdan_calculate` でも検証し、`executionStatus` と `engineeringStatus` を分けて確認する。
7. 変更した意味項目、base から継承した条件、未確認事項、エンジン検証の有無を報告する。

実行例:

```powershell
.venv\Scripts\python.exe -X utf8 .agents\skills\webdan-wdj\scripts\build_wdj.py `
  --base "path\to\base.wdj" `
  --request "path\to\request.json" `
  --output "path\to\new.wdj"
```

## Mutation invariants

- base と output を同じパスにしない。既存ファイルの上書きは、ユーザーが対象を明示した場合だけ別途行う。
- output が既に存在する場合は既定で失敗させる。明示的な置換指示がある場合に限り `--overwrite` を付ける。
- 未知のトップレベル・入れ子フィールドを保持する。WDJ バージョンを勝手に変更しない。
- 対象部材・算出点は `m_no` と `index` で一意に選び、曖昧なら中止する。
- 断面寸法変更時は `members.B/H` だけでなく、対応する `bar.b/h` と `fatigues.fatigue_list[].b/h` の表示用重複値も同期する。
- 算出点名変更時は、同じ `index` を参照して名称を保持する `bar`、`shear`、`crack`、`fatigues` の名称も同期する。
- `D19-2本(SD345)` から、上下両面配筋、芯かぶり、鉄筋間隔、コンクリート強度、照査断面力を推測しない。
- 矩形断面の軸方向鉄筋本数は片側 2 本以上とする。鉄筋径は選択中の適用でサポートされる径だけを受け付ける。
- 断面力モードと pickup モードを混在させない。`pickup_filename` が空なら断面力モードとして `force` を使う。
- Capacita が unavailable の場合、JSON/意味検査までを完了として扱い、「エンジン検証未実施」を明記する。

## Script request scope

`build_wdj.py` は、既存 WDJ の次の意味項目を安全に変更する。

- 適用・仕様
- 矩形部材の B/H と部材名
- 算出点名、軸、上下・曲げ・せん断・ねじり照査フラグ
- 上下の軸方向鉄筋（径、本数、芯かぶり、段・間隔、斜率）
- 軸方向鉄筋材種、コンクリート強度・最大骨材寸法
- 断面力モードの `force` 値
- 計算・帳票選択

別形状、preview 配筋 (`input_mode` / `rebar0`)、pickup ファイル取込み、行追加・削除は未対応。これらは Capacita の意味 API または専用 MCP 機能を使い、JSON を推測生成しない。
