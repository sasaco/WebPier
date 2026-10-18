# Aggre-SE のプロジェクトXML の期待値（決定49）

`線路方向.xml`・`線路直角方向.xml` は、Example2 の Aggre-SE（Docu-SE）のプロジェクトXMLを Aggre-SE 自身に保存し直させたもので、WebPier の書出しを使わずに作った。

## 元

| ファイル | 元 | SHA256 |
|---|---|---|
| `線路方向.xml` | `.claude/docs/Example橋脚2/10_線路(耐震)/P1_線路.xml` | `7eacba3d920e277c67980dc5aaacc067c5ae4d40399be025af57b79a69dfb84d` |
| `線路直角方向.xml` | `.claude/docs/Example橋脚2/11_直角(耐震)/P1_直角.xml` | `a8a3b20adaa37800f9c0b53535a92943e304b3fb26fb36d63364dbc0403ea06e` |

照査条件（スペクトルⅠ,Ⅱ両方・C地域・G2地盤・液状化 5<PL<20・M6.5 なし・α=1.000・η(x) なし、照査項目 ④ 以外、部材照査タイプ 2・せん断耐力式 ①、損傷レベルの制限値、直接基礎の制限値は空欄、カスタム仕様）、せん断スパン La（7600・10350）、直接基礎の照査位置の節点（7・8）は、元の値のまま。

## 手で変えたこと（2026-10-18）

1. ケースごとの配列（`dgCaseList_1`〜`9`、`analysisObject`、`SnapDBPath`、`dgEkijoCase1`・`21`・`2`）を、元の101件から先頭の50件にした。いまの Aggre-SE の `Option_ケース数` は50で、新しく作るファイルの配列は50件になる。
2. `SnapDBPath` を、WebPier の JRSNAP のフォルダーの DB1 の XML からの相対パスにした。
   - 線路方向：`線路方向_JRSNAP/線路方向(Case1_ρm10_αf1_正向).DB1`
   - 線路直角方向：`線路直角方向_JRSNAP/線路直角方向(Case1_ρm10_αf1_正向).DB1`、`…(Case2_ρm10_αf1_正向).DB1`
3. 線路直角方向は WebPier の組合せが2つ（上り線・下り線）で、元は1ケースなので、Case2 の照査項目（`dgCaseList_1`〜`9` の2件目）を Case1 と同じにした。

## Aggre-SE での保存し直し

手で変えたファイルを、`scripts/aggrese_project_roundtrip.cs`（Aggre-SE の `Input.SetXmData` → `applyVersion` → `Input.GetXmlData` → Shift-JIS の `StreamWriter`）で保存し直した。使った Aggre-SE は structural-mcp の `Batch` サブモジュール（コミット `14ed213`）の `Aggre-SE/Headless/bin/Release/Batch.exe`（FileVersion 5.3.0.1）。

保存し直しで変わった書式は次のとおり。
- 名前空間の宣言の順（`xmlns:xsi` が先）
- `Version` が `5.3.0.1`
- `_dgLimitLevel_SIJI`（-1）と `_ParagraphLength`・`ParagraphLength` が加わった
