---
name: soilstructure-input
description: Create, edit, explain, or validate SoilStructure schemaVersion 1 JSON inputs for pile calculations, SNAP SDC export, and ground-displacement calculations. Use when mapping design conditions into soilstructure.json or preparing structural-mcp SoilStructure operations. Do not use for parsing or modifying arbitrary .sdc/.ndu files or post-processing solver results.
---

# SoilStructure Input

SoilStructure GUI/headless 共通の `schemaVersion: 1` JSON を、明示された設計条件から作成・検証する。計算式や成果物形式を再実装しない。

## Reference routing

- JSON field、単位、杭種別の条件を扱うときは [references/document-schema-v1.md](references/document-schema-v1.md) を読む。
- pile / sdc / ground の選択、runner、成果物配置では [references/operations-and-artifacts.md](references/operations-and-artifacts.md) を読む。
- 知識更新、根拠の競合、確度判定では [references/evidence-source-map.md](references/evidence-source-map.md) を読む。

## Required workflow

1. 対象リポジトリの `AGENTS.md` と入力・生成物の配置規則を確認する。
2. SoilStructure の live schema または現行 source を確認してから、pile、sdc、ground の対象 operation と必要 section を決める。
3. 不足する杭・地盤・配置・地震条件を推測しない。信頼できる設計入力またはユーザー確認からだけ補う。
4. 設計入力と中間 JSON を分離する場合、設計条件を権威ある入力側へ置き、`soilstructure.json` は再生成可能な中間データとして扱う。
5. 対象 operation の validation を通した入力だけを計算・出力へ渡す。
6. artifact の種類、bytes、SHA-256、文字コードを検証してから最終配置し、生成済み成果物を手編集しない。

## Hard constraints

- `pileType` は 4=鋼管ソイルセメント杭、5=回転杭、6=場所打ち杭。
- `pile.unitWeight` と `pile.stiffness` の単位・意味は杭種で変わる。
- `soilRows` 等の GUI セルは数値でも文字列または `null` とする。
- 現行 SDC 出力は杭種 4・5・6 に対応する。杭種 5 は回転杭として出力し、別杭種へ読み替えない。
- 回転杭の SDC では、鋼管外径を杭径と一致させ、鋼管厚と腐食代を根拠ある設計入力として明示する。過去の SDC から未確認値を逆輸入しない。
- 任意の SDC/NDU のレコード解析、方言対応、変換、既存ファイル修正には `sdc-ndu-format` を使う。
